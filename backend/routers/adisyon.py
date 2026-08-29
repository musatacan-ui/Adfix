"""
Adisyon işlemleri — açma, sipariş, ikram/iptal, taşıma, birleştirme, ödeme, kapatma.

YETKİ ÖZETİ
  garson  : adisyon açar, ürün ekler, KENDİ eklediği "bekliyor" satırı iptal eder
  kasiyer : + ikram, her satırın iptali, iskonto, ödeme alma, adisyon kapatma
  yonetici: + adisyonun tamamen iptali, ödeme silme

PARA KURALI: tüm tutarlar kuruş (int). Hesaplama tek yerde: hesap.py
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List
import sqlite3
import database as db
import auth
import hesap

router = APIRouter()

ODEME_TURLERI = ("nakit", "kart", "yemek_ceki", "acik_hesap")


# ─────────────────────────── formlar ───────────────────────────

class AcForm(BaseModel):
    tip: str = "masa"                  # masa | paket | gel_al
    masa_id: Optional[int] = None
    kisi: int = 1
    musteri_ad: str = ""
    musteri_tel: str = ""
    musteri_adres: str = ""


class SatirGirdi(BaseModel):
    urun_id: int
    adet: int = 1
    notu: str = ""


class SiparisForm(BaseModel):
    satirlar: List[SatirGirdi]


class SatirGuncelleForm(BaseModel):
    adet: Optional[int] = None
    notu: Optional[str] = None
    durum: Optional[str] = None        # bekliyor | hazir | ikram | iptal
    sebep: str = ""


class TasiForm(BaseModel):
    hedef_masa_id: int


class BirlestirForm(BaseModel):
    kaynak_adisyon_id: int


class IskontoForm(BaseModel):
    tip: str = "tutar"                 # tutar | yuzde
    deger: int = 0                     # tutar ise kuruş, yüzde ise 0-100
    aciklama: str = ""


class OdemeForm(BaseModel):
    tur: str
    tutar_kurus: int


class BilgiForm(BaseModel):
    kisi: Optional[int] = None
    aciklama: Optional[str] = None
    musteri_ad: Optional[str] = None
    musteri_tel: Optional[str] = None
    musteri_adres: Optional[str] = None


class IptalForm(BaseModel):
    sebep: str = ""


# ─────────────────────────── yardımcılar ───────────────────────────

def _adisyon_al(conn, aid: int, acik_olmali: bool = True):
    a = conn.execute("SELECT * FROM adisyonlar WHERE id=?", (aid,)).fetchone()
    if not a:
        conn.close()
        raise HTTPException(404, "Adisyon bulunamadı")
    if acik_olmali and a["durum"] != "acik":
        conn.close()
        durum = "kapatılmış" if a["durum"] == "kapali" else "iptal edilmiş"
        raise HTTPException(400, f"Bu adisyon {durum}, üzerinde işlem yapılamaz")
    return a


def _detay(conn, aid: int) -> dict:
    a = conn.execute("""
        SELECT a.*, m.ad AS masa_ad, s.ad AS salon_ad,
               ka.ad_soyad AS acan_ad, kk.ad_soyad AS kapatan_ad
        FROM adisyonlar a
        LEFT JOIN masalar m       ON m.id = a.masa_id
        LEFT JOIN salonlar s      ON s.id = m.salon_id
        LEFT JOIN kullanicilar ka ON ka.id = a.acan_id
        LEFT JOIN kullanicilar kk ON kk.id = a.kapatan_id
        WHERE a.id=?""", (aid,)).fetchone()
    if not a:
        raise HTTPException(404, "Adisyon bulunamadı")
    satirlar = [dict(x) for x in conn.execute("""
        SELECT s.*, k.ad_soyad AS ekleyen_ad
        FROM adisyon_satir s LEFT JOIN kullanicilar k ON k.id=s.ekleyen_id
        WHERE s.adisyon_id=? ORDER BY s.id""", (aid,))]
    odemeler = [dict(x) for x in conn.execute("""
        SELECT o.*, k.ad_soyad AS alan_ad
        FROM odemeler o LEFT JOIN kullanicilar k ON k.id=o.alan_id
        WHERE o.adisyon_id=? ORDER BY o.id""", (aid,))]
    for s in satirlar:
        s["tutar_kurus"] = s["birim_kurus"] * s["adet"]
    return {**dict(a), "satirlar": satirlar, "odemeler": odemeler,
            "ozet": hesap.ozet(conn, aid)}


def _satir_yetki(conn, satir, mevcut: dict):
    """Garson yalnız kendi eklediği ve henüz mutfağa gitmemiş satıra dokunabilir."""
    if mevcut["rol"] in ("kasiyer", "yonetici"):
        return
    if satir["ekleyen_id"] != mevcut["id"]:
        conn.close()
        raise HTTPException(403, "Bu satırı başka bir kullanıcı ekledi, kasiyere iletin")
    if satir["durum"] != "bekliyor":
        conn.close()
        raise HTTPException(403, "Hazırlanmış satırı ancak kasiyer değiştirebilir")


# ─────────────────────────── açma / listeleme ───────────────────────────

@router.post("/ac")
def adisyon_ac(form: AcForm, mevcut: dict = Depends(auth.token_dogrula)):
    if form.tip not in ("masa", "paket", "gel_al"):
        raise HTTPException(400, "Geçersiz adisyon tipi")
    conn = db.get_conn()
    if form.tip == "masa":
        if not form.masa_id:
            conn.close()
            raise HTTPException(400, "Masa seçilmedi")
        masa = conn.execute("SELECT * FROM masalar WHERE id=? AND aktif=1",
                            (form.masa_id,)).fetchone()
        if not masa:
            conn.close()
            raise HTTPException(404, "Masa bulunamadı")
        dolu = conn.execute("SELECT id, kod FROM adisyonlar WHERE masa_id=? AND durum='acik'",
                            (form.masa_id,)).fetchone()
        if dolu:
            conn.close()
            raise HTTPException(400, f"{masa['ad']} masasında {dolu['kod']} nolu "
                                     f"adisyon zaten açık")
    else:
        form.masa_id = None

    # Günlük sıra numarası. Eşzamanlı açılışta tekil indeks çakıştırır → tekrar dener.
    for _ in range(6):
        n = conn.execute(
            "SELECT COUNT(*) n FROM adisyonlar WHERE date(acilis)=date('now','localtime')"
        ).fetchone()["n"]
        kod = f"{n + 1:03d}"
        try:
            cur = conn.execute("""
                INSERT INTO adisyonlar (kod, tip, masa_id, kisi, acan_id,
                                        musteri_ad, musteri_tel, musteri_adres)
                VALUES (?,?,?,?,?,?,?,?)""",
                (kod, form.tip, form.masa_id, max(1, form.kisi), mevcut["id"],
                 form.musteri_ad.strip(), form.musteri_tel.strip(),
                 form.musteri_adres.strip()))
            break
        except sqlite3.IntegrityError as e:
            if "ux_gunluk_kod" in str(e):
                continue
            conn.close()
            raise HTTPException(400, "Bu masada zaten açık bir adisyon var")
    else:
        conn.close()
        raise HTTPException(500, "Adisyon numarası üretilemedi, tekrar deneyin")

    aid = cur.lastrowid
    db.kayit_log(conn, mevcut, "adisyon_acildi", f"#{kod} ({form.tip})")
    conn.commit()
    d = _detay(conn, aid)
    conn.close()
    return d


@router.get("/acik")
def acik_listesi(mevcut: dict = Depends(auth.token_dogrula)):
    conn = db.get_conn()
    rows = conn.execute("""
        SELECT a.*, m.ad AS masa_ad FROM adisyonlar a
        LEFT JOIN masalar m ON m.id=a.masa_id
        WHERE a.durum='acik' ORDER BY a.id DESC""").fetchall()
    sonuc = [{**dict(r), "ozet": hesap.ozet(conn, r["id"])} for r in rows]
    conn.close()
    return sonuc


@router.get("/gecmis")
def gecmis(bas: str = "", bit: str = "", limit: int = 200,
           mevcut: dict = Depends(auth.token_dogrula)):
    """Kapanmış/iptal adisyonlar. bas/bit: YYYY-AA-GG (dahil)."""
    conn = db.get_conn()
    kosul, par = ["a.durum <> 'acik'"], []
    if bas:
        kosul.append("date(COALESCE(a.kapanis, a.acilis)) >= ?"); par.append(bas)
    if bit:
        kosul.append("date(COALESCE(a.kapanis, a.acilis)) <= ?"); par.append(bit)
    par.append(min(limit, 1000))
    rows = conn.execute(f"""
        SELECT a.*, m.ad AS masa_ad, k.ad_soyad AS kapatan_ad
        FROM adisyonlar a
        LEFT JOIN masalar m ON m.id=a.masa_id
        LEFT JOIN kullanicilar k ON k.id=a.kapatan_id
        WHERE {' AND '.join(kosul)}
        ORDER BY a.id DESC LIMIT ?""", par).fetchall()
    sonuc = [{**dict(r), "ozet": hesap.ozet(conn, r["id"])} for r in rows]
    conn.close()
    return sonuc


@router.get("/mutfak")
def mutfak(mevcut: dict = Depends(auth.token_dogrula)):
    """Mutfak ekranı — hazırlanmayı bekleyen siparişler (en eski üstte)."""
    conn = db.get_conn()
    rows = [dict(x) for x in conn.execute("""
        SELECT s.id, s.adisyon_id, s.ad, s.adet, s.notu, s.eklenme, s.mutfak,
               a.kod, a.tip, m.ad AS masa_ad, k.ad_soyad AS ekleyen_ad,
               CAST((julianday('now','localtime') - julianday(s.eklenme)) * 1440 AS INTEGER)
                   AS bekleme_dk
        FROM adisyon_satir s
        JOIN adisyonlar a  ON a.id = s.adisyon_id
        LEFT JOIN masalar m ON m.id = a.masa_id
        LEFT JOIN kullanicilar k ON k.id = s.ekleyen_id
        WHERE s.durum='bekliyor' AND a.durum='acik'
        ORDER BY s.id""")]
    conn.close()
    return rows


@router.get("/{aid}")
def detay(aid: int, mevcut: dict = Depends(auth.token_dogrula)):
    conn = db.get_conn()
    d = _detay(conn, aid)
    conn.close()
    return d


# ─────────────────────────── sipariş satırları ───────────────────────────

@router.post("/{aid}/siparis")
def siparis_ekle(aid: int, form: SiparisForm, mevcut: dict = Depends(auth.token_dogrula)):
    if not form.satirlar:
        raise HTTPException(400, "Sipariş boş")
    conn = db.get_conn()
    _adisyon_al(conn, aid)
    eklendi = []
    for s in form.satirlar:
        if s.adet < 1:
            continue
        u = conn.execute("SELECT * FROM urunler WHERE id=?", (s.urun_id,)).fetchone()
        if not u:
            conn.close()
            raise HTTPException(400, f"Ürün bulunamadı (id={s.urun_id})")
        if not u["aktif"]:
            conn.close()
            raise HTTPException(400, f"'{u['ad']}' menüden kaldırılmış, eklenemez")
        # Ad ve fiyat SATIRA KOPYALANIR: menüde fiyat değişse bile açık adisyon bozulmaz.
        conn.execute("""
            INSERT INTO adisyon_satir (adisyon_id, urun_id, ad, birim_kurus, adet,
                                       notu, mutfak, ekleyen_id)
            VALUES (?,?,?,?,?,?,?,?)""",
            (aid, u["id"], u["ad"], u["fiyat_kurus"], s.adet,
             s.notu.strip(), u["mutfak"], mevcut["id"]))
        eklendi.append(f"{s.adet}x {u['ad']}")
    db.kayit_log(conn, mevcut, "siparis_eklendi", f"#{aid}: " + ", ".join(eklendi))
    conn.commit()
    d = _detay(conn, aid)
    conn.close()
    return d


@router.patch("/satir/{sid}")
def satir_guncelle(sid: int, form: SatirGuncelleForm,
                   mevcut: dict = Depends(auth.token_dogrula)):
    conn = db.get_conn()
    s = conn.execute("SELECT * FROM adisyon_satir WHERE id=?", (sid,)).fetchone()
    if not s:
        conn.close()
        raise HTTPException(404, "Satır bulunamadı")
    _adisyon_al(conn, s["adisyon_id"])

    if form.durum is not None:
        if form.durum not in ("bekliyor", "hazir", "ikram", "iptal"):
            conn.close()
            raise HTTPException(400, "Geçersiz satır durumu")
        # Para etkisi olan durumlar (ikram/iptal) kasiyer yetkisi ister.
        if form.durum in ("ikram", "iptal"):
            if form.durum == "ikram" and mevcut["rol"] not in ("kasiyer", "yonetici"):
                conn.close()
                raise HTTPException(403, "İkram için kasiyer yetkisi gerekli")
            if form.durum == "iptal":
                _satir_yetki(conn, s, mevcut)
                if not form.sebep.strip():
                    conn.close()
                    raise HTTPException(400, "İptal sebebi zorunlu")
        conn.execute("UPDATE adisyon_satir SET durum=?, iptal_sebep=? WHERE id=?",
                     (form.durum, form.sebep.strip(), sid))
        db.kayit_log(conn, mevcut, f"satir_{form.durum}",
                     f"#{s['adisyon_id']} {s['adet']}x {s['ad']} {form.sebep}".strip())

    if form.adet is not None:
        if form.adet < 1:
            conn.close()
            raise HTTPException(400, "Adet en az 1 olmalı (kaldırmak için iptal edin)")
        _satir_yetki(conn, s, mevcut)
        conn.execute("UPDATE adisyon_satir SET adet=? WHERE id=?", (form.adet, sid))
        db.kayit_log(conn, mevcut, "satir_adet",
                     f"#{s['adisyon_id']} {s['ad']}: {s['adet']} -> {form.adet}")

    if form.notu is not None:
        conn.execute("UPDATE adisyon_satir SET notu=? WHERE id=?", (form.notu.strip(), sid))

    conn.commit()
    d = _detay(conn, s["adisyon_id"])
    conn.close()
    return d


@router.post("/satir/{sid}/hazir")
def satir_hazir(sid: int, mevcut: dict = Depends(auth.token_dogrula)):
    """Mutfak ekranından 'hazırlandı' işaretleme."""
    conn = db.get_conn()
    s = conn.execute("SELECT * FROM adisyon_satir WHERE id=?", (sid,)).fetchone()
    if not s:
        conn.close()
        raise HTTPException(404, "Satır bulunamadı")
    if s["durum"] != "bekliyor":
        conn.close()
        raise HTTPException(400, "Bu satır zaten işlem görmüş")
    conn.execute("UPDATE adisyon_satir SET durum='hazir' WHERE id=?", (sid,))
    conn.commit()
    conn.close()
    return {"mesaj": "Hazır olarak işaretlendi"}


# ─────────────────────────── masa işlemleri ───────────────────────────

@router.post("/{aid}/tasi")
def tasi(aid: int, form: TasiForm, mevcut: dict = Depends(auth.token_dogrula)):
    conn = db.get_conn()
    a = _adisyon_al(conn, aid)
    masa = conn.execute("SELECT * FROM masalar WHERE id=? AND aktif=1",
                        (form.hedef_masa_id,)).fetchone()
    if not masa:
        conn.close()
        raise HTTPException(404, "Hedef masa bulunamadı")
    if conn.execute("SELECT 1 FROM adisyonlar WHERE masa_id=? AND durum='acik'",
                    (form.hedef_masa_id,)).fetchone():
        conn.close()
        raise HTTPException(400, f"{masa['ad']} dolu. Boşaltın ya da birleştirin.")
    eski = conn.execute("SELECT ad FROM masalar WHERE id=?", (a["masa_id"],)).fetchone()
    conn.execute("UPDATE adisyonlar SET masa_id=?, tip='masa' WHERE id=?",
                 (form.hedef_masa_id, aid))
    db.kayit_log(conn, mevcut, "adisyon_tasindi",
                 f"#{a['kod']}: {eski['ad'] if eski else 'paket'} -> {masa['ad']}")
    conn.commit()
    d = _detay(conn, aid)
    conn.close()
    return d


@router.post("/{aid}/birlestir")
def birlestir(aid: int, form: BirlestirForm, mevcut: dict = Depends(auth.kasiyer_gerektir)):
    """Kaynak adisyonun tüm satır ve ödemeleri hedefe aktarılır, kaynak kapanır."""
    if aid == form.kaynak_adisyon_id:
        raise HTTPException(400, "Adisyon kendisiyle birleştirilemez")
    conn = db.get_conn()
    hedef = _adisyon_al(conn, aid)
    kaynak = _adisyon_al(conn, form.kaynak_adisyon_id)
    conn.execute("UPDATE adisyon_satir SET adisyon_id=? WHERE adisyon_id=?",
                 (aid, kaynak["id"]))
    conn.execute("UPDATE odemeler SET adisyon_id=? WHERE adisyon_id=?", (aid, kaynak["id"]))
    # Kaynağın iskontosu hedefe eklenir; hesap.ozet ara toplamı aşmasını zaten engeller.
    conn.execute("UPDATE adisyonlar SET iskonto_kurus = iskonto_kurus + ? WHERE id=?",
                 (kaynak["iskonto_kurus"] or 0, aid))
    conn.execute("""UPDATE adisyonlar
                    SET durum='iptal', kapanis=datetime('now','localtime'),
                        kapatan_id=?, iptal_sebep=?, iskonto_kurus=0
                    WHERE id=?""",
                 (mevcut["id"], f"#{hedef['kod']} nolu adisyona birleştirildi", kaynak["id"]))
    conn.execute("UPDATE adisyonlar SET kisi = kisi + ? WHERE id=?", (kaynak["kisi"], aid))
    db.kayit_log(conn, mevcut, "adisyon_birlestirildi",
                 f"#{kaynak['kod']} -> #{hedef['kod']}")
    conn.commit()
    d = _detay(conn, aid)
    conn.close()
    return d


@router.patch("/{aid}/bilgi")
def bilgi_guncelle(aid: int, form: BilgiForm, mevcut: dict = Depends(auth.token_dogrula)):
    conn = db.get_conn()
    _adisyon_al(conn, aid)
    alanlar, par = [], []
    for ad, deger in (("kisi", form.kisi), ("aciklama", form.aciklama),
                      ("musteri_ad", form.musteri_ad), ("musteri_tel", form.musteri_tel),
                      ("musteri_adres", form.musteri_adres)):
        if deger is not None:
            alanlar.append(f"{ad}=?")
            par.append(max(1, deger) if ad == "kisi" else str(deger).strip())
    if alanlar:
        par.append(aid)
        conn.execute(f"UPDATE adisyonlar SET {', '.join(alanlar)} WHERE id=?", par)
        conn.commit()
    d = _detay(conn, aid)
    conn.close()
    return d


# ─────────────────────────── para işlemleri ───────────────────────────

@router.post("/{aid}/iskonto")
def iskonto(aid: int, form: IskontoForm, mevcut: dict = Depends(auth.kasiyer_gerektir)):
    conn = db.get_conn()
    _adisyon_al(conn, aid)
    o = hesap.ozet(conn, aid)
    if form.tip == "yuzde":
        if not 0 <= form.deger <= 100:
            conn.close()
            raise HTTPException(400, "Yüzde 0-100 aralığında olmalı")
        tutar = o["ara_toplam"] * form.deger // 100
        aciklama = f"%{form.deger} iskonto"
    else:
        tutar = max(0, form.deger)
        aciklama = "Tutar iskontosu"
    if tutar > o["ara_toplam"]:
        conn.close()
        raise HTTPException(400, "İskonto ara toplamdan büyük olamaz")
    if tutar and o["odenen"] > o["ara_toplam"] - tutar:
        conn.close()
        raise HTTPException(400, "İskonto sonrası tutar, alınan ödemenin altına düşüyor. "
                                 "Önce ödemeyi silin.")
    conn.execute("UPDATE adisyonlar SET iskonto_kurus=?, iskonto_not=? WHERE id=?",
                 (tutar, (form.aciklama or aciklama).strip(), aid))
    db.kayit_log(conn, mevcut, "iskonto", f"#{aid}: {tutar} kr ({aciklama})")
    conn.commit()
    d = _detay(conn, aid)
    conn.close()
    return d


@router.post("/{aid}/odeme")
def odeme_al(aid: int, form: OdemeForm, mevcut: dict = Depends(auth.kasiyer_gerektir)):
    if form.tur not in ODEME_TURLERI:
        raise HTTPException(400, "Geçersiz ödeme türü")
    if form.tutar_kurus <= 0:
        raise HTTPException(400, "Ödeme tutarı sıfırdan büyük olmalı")
    conn = db.get_conn()
    _adisyon_al(conn, aid)
    o = hesap.ozet(conn, aid)
    # Fazla tahsilat kaydedilmez: para üstü kasa hareketi değildir, arayüzde gösterilir.
    if form.tutar_kurus > o["kalan"]:
        conn.close()
        raise HTTPException(400, f"Kalan tutardan fazla ödeme kaydedilemez "
                                 f"(kalan: {o['kalan'] / 100:.2f} TL)")
    conn.execute("INSERT INTO odemeler (adisyon_id, tur, tutar_kurus, alan_id) VALUES (?,?,?,?)",
                 (aid, form.tur, form.tutar_kurus, mevcut["id"]))
    db.kayit_log(conn, mevcut, "odeme_alindi", f"#{aid}: {form.tutar_kurus} kr / {form.tur}")
    conn.commit()
    d = _detay(conn, aid)
    conn.close()
    return d


@router.delete("/odeme/{oid}")
def odeme_sil(oid: int, mevcut: dict = Depends(auth.yonetici_gerektir)):
    conn = db.get_conn()
    o = conn.execute("SELECT * FROM odemeler WHERE id=?", (oid,)).fetchone()
    if not o:
        conn.close()
        raise HTTPException(404, "Ödeme kaydı bulunamadı")
    a = conn.execute("SELECT * FROM adisyonlar WHERE id=?", (o["adisyon_id"],)).fetchone()
    if a["durum"] == "kapali":
        conn.close()
        raise HTTPException(400, "Kapanmış adisyonun ödemesi silinemez")
    conn.execute("DELETE FROM odemeler WHERE id=?", (oid,))
    db.kayit_log(conn, mevcut, "odeme_silindi",
                 f"#{a['kod']}: {o['tutar_kurus']} kr / {o['tur']}")
    conn.commit()
    d = _detay(conn, o["adisyon_id"])
    conn.close()
    return d


@router.get("/{aid}/bol")
def hesap_bol(aid: int, kisi: int = 0, mevcut: dict = Depends(auth.token_dogrula)):
    """Hesabı eşit böler. Kuruş artığı ilk kişilere dağıtılır — toplam TAM tutar eder."""
    conn = db.get_conn()
    a = _adisyon_al(conn, aid, acik_olmali=False)
    o = hesap.ozet(conn, aid)
    conn.close()
    n = kisi if kisi > 0 else a["kisi"]
    paylar = hesap.bol_dagit(o["net_toplam"], n)
    return {"kisi": n, "net_toplam": o["net_toplam"], "paylar": paylar,
            "kontrol_toplam": sum(paylar)}


# ─────────────────────────── kapatma / iptal ───────────────────────────

@router.post("/{aid}/kapat")
def kapat(aid: int, mevcut: dict = Depends(auth.kasiyer_gerektir)):
    conn = db.get_conn()
    a = _adisyon_al(conn, aid)
    o = hesap.ozet(conn, aid)
    if o["ara_toplam"] == 0 and o["ikram"] == 0:
        conn.close()
        raise HTTPException(400, "Adisyonda ürün yok. Kapatmak yerine iptal edin.")
    if o["kalan"] > 0:
        conn.close()
        raise HTTPException(400, f"Ödenmemiş {o['kalan'] / 100:.2f} TL var, "
                                 f"adisyon kapatılamaz")
    conn.execute("""UPDATE adisyonlar SET durum='kapali',
                    kapanis=datetime('now','localtime'), kapatan_id=? WHERE id=?""",
                 (mevcut["id"], aid))
    db.kayit_log(conn, mevcut, "adisyon_kapandi",
                 f"#{a['kod']}: {o['net_toplam']} kr")
    conn.commit()
    d = _detay(conn, aid)
    conn.close()
    return d


@router.post("/{aid}/iptal")
def iptal(aid: int, form: IptalForm, mevcut: dict = Depends(auth.yonetici_gerektir)):
    if not form.sebep.strip():
        raise HTTPException(400, "İptal sebebi zorunlu")
    conn = db.get_conn()
    a = _adisyon_al(conn, aid)
    o = hesap.ozet(conn, aid)
    if o["odenen"] > 0:
        conn.close()
        raise HTTPException(400, "Ödeme alınmış adisyon iptal edilemez, "
                                 "önce ödemeleri silin")
    conn.execute("""UPDATE adisyonlar SET durum='iptal', iptal_sebep=?,
                    kapanis=datetime('now','localtime'), kapatan_id=? WHERE id=?""",
                 (form.sebep.strip(), mevcut["id"], aid))
    conn.execute("UPDATE adisyon_satir SET durum='iptal', iptal_sebep=? "
                 "WHERE adisyon_id=? AND durum IN ('bekliyor','hazir')",
                 (form.sebep.strip(), aid))
    db.kayit_log(conn, mevcut, "adisyon_iptal", f"#{a['kod']}: {form.sebep}")
    conn.commit()
    d = _detay(conn, aid)
    conn.close()
    return d
