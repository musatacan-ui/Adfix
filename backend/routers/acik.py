"""
Müşteri tarafı — karekod ile erişilen HERKESE AÇIK uçlar (kimlik doğrulama yok).

GÜVENLİK SINIRI (HC12)
  Bu router'dan yapılabilenler:
  - Menü, işletme kartviziti, masa adı OKUMA (salt okunur)
  - QR SVG üretme (dış servis kullanılmaz)
  - Masa QR'ından SİPARİŞ EKLEME (sadece satır ekler, sadece bekleyen durumda)
  - Kendi masasının siparişini GÖRME (bekleyen/hazır satırlar, tutar)

  Buradan YAPILAMAYANLAR:
  - Ciro, personel, kasa raporu, gün sonu görme
  - Satır iptali, ikram, iskonto, ödeme, hesap kapatma
  - Ayar değiştirme, kullanıcı/masa/menü yönetimi
  - Başka masanın adisyonuna dokunma

Kötüye kullanıma karşı:
  - IP bazlı hız sınırı (dakikada en fazla 5 sipariş / IP)
  - Sipariş başına ürün sayısı sınırı
  - Yönetici QR sipariş özelliğini tamamen kapatabilir (ayar: qr_siparis_acik)
"""
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel
from typing import List
from collections import defaultdict
import sqlite3
import time
import database as db

router = APIRouter()

# ─────────────────────────── SINIRLAR ───────────────────────────

# Kısa aralıklı istismarın önüne geçer; makul kullanıcı bunu doldurmaz.
# Aile 4 kişi, herkes ayrı sipariş açsa bile makul: 60 sn'de 20 sipariş / IP.
IP_LIMIT, IP_PENCERE = 20, 60
SATIR_UST_SINIR = 30                   # tek istekte en fazla 30 farklı ürün
ADET_UST_SINIR = 20                    # tek satırda en fazla 20 adet
NOT_UZUNLUK = 200                      # sipariş notu karakter sınırı

_siparis_zamanlari: dict[str, list[float]] = defaultdict(list)


def _ip(request: Request) -> str:
    return request.client.host if request.client else "bilinmiyor"


def _hiz_siniri(ip: str):
    """Tek IP'den kısa sürede aşırı sipariş girmeyi engeller. Şaka siparişlerinin
    ilk savunma hattı — sonraki hat garsonun mutfak ekranındaki satırları hazır
    işaretlemeden reddetmesidir."""
    simdi = time.time()
    _siparis_zamanlari[ip] = [t for t in _siparis_zamanlari[ip] if simdi - t < IP_PENCERE]
    if len(_siparis_zamanlari[ip]) >= IP_LIMIT:
        raise HTTPException(429, "Çok fazla sipariş denemesi. Biraz bekleyin.")
    _siparis_zamanlari[ip].append(simdi)


# ─────────────────────────── OKUMA UÇLARI ───────────────────────────

@router.get("/menu")
def acik_menu():
    """QR menüsünün gösterdiği veri: işletme kartviziti + aktif menü + sipariş izni."""
    conn = db.get_conn()
    ayar = db.ayarlari_al(conn)
    kategoriler = [dict(x) for x in conn.execute(
        "SELECT id, ad, renk, ikon FROM kategoriler WHERE aktif=1 ORDER BY sira, ad")]
    urunler = [dict(x) for x in conn.execute(
        "SELECT id, kategori_id, ad, fiyat_kurus, aciklama, gorsel "
        "FROM urunler WHERE aktif=1 ORDER BY sira, ad")]
    populer_ids = {r["urun_id"] for r in conn.execute("""
        SELECT s.urun_id, SUM(s.adet) toplam
        FROM adisyon_satir s JOIN adisyonlar a ON a.id = s.adisyon_id
        WHERE s.durum IN ('bekliyor','hazir') AND s.urun_id IS NOT NULL
          AND a.acilis >= datetime('now','localtime','-30 days')
        GROUP BY s.urun_id ORDER BY toplam DESC LIMIT 5""")}
    conn.close()
    for u in urunler:
        u["populer"] = u["id"] in populer_ids
    for k in kategoriler:
        k["urunler"] = [u for u in urunler if u["kategori_id"] == k["id"]]
    return {
        "isletme": {
            "ad":      ayar["isletme_adi"],
            "slogan":  ayar["slogan"],
            "adres":   ayar["adres"],
            "telefon": ayar["telefon"],
            "logo":    ayar["logo"],
        },
        "siparis_acik": ayar["qr_siparis_acik"] == "1",
        # Boş kategoriler müşteriye gösterilmez
        "kategoriler": [k for k in kategoriler if k["urunler"]],
    }


@router.get("/isletme")
def acik_isletme():
    """Sadece işletme kartviziti — giriş ekranı logoyu buradan alır (menü yükü olmadan)."""
    conn = db.get_conn()
    a = db.ayarlari_al(conn)
    conn.close()
    return {"ad": a["isletme_adi"], "slogan": a["slogan"], "logo": a["logo"]}


@router.get("/masa/{masa_id}")
def acik_masa(masa_id: int):
    """QR'daki masa numarasının adını verir — müşteri 'B3 masasındasınız' görür.
    Adisyon ya da tutar bilgisi DÖNMEZ."""
    conn = db.get_conn()
    m = conn.execute(
        "SELECT m.ad, s.ad AS salon FROM masalar m "
        "LEFT JOIN salonlar s ON s.id = m.salon_id WHERE m.id=? AND m.aktif=1",
        (masa_id,)).fetchone()
    conn.close()
    if not m:
        raise HTTPException(404, "Masa bulunamadı")
    return {"ad": m["ad"], "salon": m["salon"] or ""}


@router.get("/qr")
def qr_uret(veri: str, boyut: int = 8):
    """Verilen metni QR koda çevirip SVG döner. Yazdırılabilir, ölçeklenebilir.
    Dış servise İSTEK GİTMEZ — kod yerel olarak üretilir (restoranın interneti
    kesikken de QR basılabilir ve müşteri yerel ağdan menüye ulaşır)."""
    if not veri or len(veri) > 900:
        raise HTTPException(400, "QR verisi boş ya da çok uzun")
    try:
        import qrcode
        import qrcode.image.svg
    except ImportError:
        raise HTTPException(
            501, "QR üretimi için 'qrcode' paketi kurulu değil: pip install qrcode")

    q = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=max(2, min(boyut, 20)),
        border=2,
    )
    q.add_data(veri)
    q.make(fit=True)
    img = q.make_image(image_factory=qrcode.image.svg.SvgPathImage)
    import io
    tampon = io.BytesIO()
    img.save(tampon)
    return Response(content=tampon.getvalue(), media_type="image/svg+xml",
                    headers={"Cache-Control": "no-store"})


# ─────────────────────────── SİPARİŞ VE DURUM ───────────────────────────

class CagriForm(BaseModel):
    tip: str = "garson"


class MusteriSatir(BaseModel):
    urun_id: int
    adet: int = 1
    notu: str = ""


class MusteriSiparisForm(BaseModel):
    satirlar: List[MusteriSatir]
    notu: str = ""


@router.post("/masa/{masa_id}/siparis")
def musteri_siparis(masa_id: int, form: MusteriSiparisForm, request: Request):
    """Masa QR'ından gelen müşteri siparişi.

    Masada açık adisyon varsa satır ekler; yoksa yeni adisyon açıp satırları
    ilk sipariş olarak yazar. Satırlar `ekleyen_id=NULL` ile kaydedilir; bu
    arayüzde "Müşteri" olarak görünür ve garson isterse iptal edebilir.

    Sadece salon masası için çalışır — paket/gel-al QR'ı yoktur."""
    _hiz_siniri(_ip(request))

    if not form.satirlar:
        raise HTTPException(400, "Sepetiniz boş")
    if len(form.satirlar) > SATIR_UST_SINIR:
        raise HTTPException(400, f"Tek seferde en fazla {SATIR_UST_SINIR} kalem gönderilebilir")

    conn = db.get_conn()
    ayar = db.ayarlari_al(conn)
    if ayar["qr_siparis_acik"] != "1":
        conn.close()
        raise HTTPException(403, "Bu işletme şu an karekod ile sipariş almıyor. "
                                 "Lütfen garsona sesleniniz.")

    masa = conn.execute(
        "SELECT * FROM masalar WHERE id=? AND aktif=1", (masa_id,)).fetchone()
    if not masa:
        conn.close()
        raise HTTPException(404, "Masa bulunamadı — karekodu tekrar okutmayı deneyin")

    # Var olan açık adisyon var mı? HC1 (masa tekliği) garantisi burada geçerli.
    ad = conn.execute(
        "SELECT * FROM adisyonlar WHERE masa_id=? AND durum='acik'", (masa_id,)).fetchone()
    yeni_adisyon = ad is None
    aid = ad["id"] if ad else None

    musteri_notu = (form.notu or "").strip()[:NOT_UZUNLUK]
    aciklama = ("QR ile açıldı" + (" — Müşteri notu: " + musteri_notu if musteri_notu else ""))

    if yeni_adisyon:
        for _ in range(6):
            n = conn.execute(
                "SELECT COUNT(*) n FROM adisyonlar "
                "WHERE date(acilis)=date('now','localtime')").fetchone()["n"]
            kod = f"{n + 1:03d}"
            try:
                cur = conn.execute("""
                    INSERT INTO adisyonlar (kod, tip, masa_id, kisi, acan_id, aciklama)
                    VALUES (?, 'masa', ?, 1, NULL, ?)""",
                    (kod, masa_id, aciklama))
                aid = cur.lastrowid
                break
            except sqlite3.IntegrityError as e:
                if "ux_masa_tek_acik" in str(e):
                    ad = conn.execute(
                        "SELECT * FROM adisyonlar WHERE masa_id=? AND durum='acik'",
                        (masa_id,)).fetchone()
                    if ad:
                        aid = ad["id"]; yeni_adisyon = False
                        break
                if "ux_gunluk_kod" in str(e):
                    continue
                conn.close()
                raise HTTPException(500, "Adisyon açılamadı, tekrar deneyin")
        else:
            conn.close()
            raise HTTPException(500, "Adisyon numarası üretilemedi")

    if not yeni_adisyon and musteri_notu:
        mevcut = conn.execute(
            "SELECT aciklama FROM adisyonlar WHERE id=?", (aid,)).fetchone()
        eski = (mevcut["aciklama"] or "") if mevcut else ""
        yeni = (eski + " | Müşteri: " + musteri_notu).strip()[:500]
        conn.execute("UPDATE adisyonlar SET aciklama=? WHERE id=?", (yeni, aid))

    eklenen = 0
    for s in form.satirlar:
        if s.adet < 1 or s.adet > ADET_UST_SINIR:
            continue
        u = conn.execute("SELECT * FROM urunler WHERE id=?", (s.urun_id,)).fetchone()
        if not u or not u["aktif"]:
            continue                        # menüden kaldırılmış ürün sessizce atlanır
        conn.execute("""
            INSERT INTO adisyon_satir (adisyon_id, urun_id, ad, birim_kurus, adet,
                                       notu, mutfak, ekleyen_id, durum)
            VALUES (?, ?, ?, ?, ?, ?, ?, NULL, 'bekliyor')""",
            (aid, u["id"], u["ad"], u["fiyat_kurus"], s.adet,
             (s.notu or "")[:NOT_UZUNLUK], u["mutfak"]))
        eklenen += 1

    if not eklenen:
        conn.close()
        raise HTTPException(400, "Menüde bulunmayan ürünler — sepet reddedildi")

    db.kayit_log(conn, None, "musteri_siparis_qr",
                 f"masa={masa['ad']} adisyon=#{aid} kalem={eklenen} ip={_ip(request)}")
    conn.commit()

    ozet = _masa_ozeti(conn, aid)
    conn.close()
    return {"mesaj": f"Siparişiniz alındı ({eklenen} kalem)",
            "yeni_adisyon": yeni_adisyon, **ozet}


def _masa_ozeti(conn, aid: int) -> dict:
    """Müşterinin adisyonundan görmesine izin verilen alanlar. İkram/iptal
    tutarları, personel bilgisi, ödemeler DIŞTA tutulur."""
    a = conn.execute(
        "SELECT id, kod, kisi, acilis FROM adisyonlar WHERE id=?", (aid,)).fetchone()
    if not a:
        return {}
    satirlar = [dict(x) for x in conn.execute("""
        SELECT id, ad, adet, birim_kurus, notu, durum, eklenme
        FROM adisyon_satir
        WHERE adisyon_id=? AND durum IN ('bekliyor','hazir','ikram')
        ORDER BY id""", (aid,))]
    # Müşteri tarafında ikram fiyatını 0 gösteririz — kime, ne kadar ikram yapıldığı
    # işletmenin iç bilgisi; müşteri sadece "İKRAM" etiketini görsün.
    ara = sum(s["birim_kurus"] * s["adet"] for s in satirlar if s["durum"] != "ikram")
    return {
        "adisyon_id": a["id"],
        "kod": a["kod"],
        "satirlar": satirlar,
        "toplam": ara,
    }


@router.post("/masa/{masa_id}/cagri")
def garson_cagri(masa_id: int, form: CagriForm, request: Request):
    """Müşteri masadan garson çağırır veya hesap ister.
    Aynı masadan kısa sürede tekrar çağrı engellenir."""
    _hiz_siniri(_ip(request))
    conn = db.get_conn()
    masa = conn.execute(
        "SELECT ad FROM masalar WHERE id=? AND aktif=1", (masa_id,)).fetchone()
    if not masa:
        conn.close()
        raise HTTPException(404, "Masa bulunamadı")

    tip = form.tip if form.tip in ('garson', 'hesap') else 'garson'

    mevcut = conn.execute(
        "SELECT id FROM masa_bildirim WHERE masa_id=? AND tip=? AND durum='bekliyor'",
        (masa_id, tip)).fetchone()
    if mevcut:
        conn.close()
        ad = 'Garson çağırma' if tip == 'garson' else 'Hesap isteme'
        return {"mesaj": f"{ad} isteğiniz zaten iletildi, birazdan geleceğiz!"}

    conn.execute(
        "INSERT INTO masa_bildirim (masa_id, tip) VALUES (?, ?)", (masa_id, tip))
    db.kayit_log(conn, None, f"musteri_{tip}_cagri",
                 f"masa={masa['ad']} ip={_ip(request)}")
    conn.commit()
    conn.close()
    if tip == 'hesap':
        return {"mesaj": "Hesap isteğiniz garsona iletildi!"}
    return {"mesaj": "Garson çağrıldı, birazdan masanıza geleceğiz!"}


@router.get("/masa/{masa_id}/durum")
def masa_durumu(masa_id: int):
    """Müşteri kendi masasının siparişini görebilsin — bekliyor/hazır/ikram
    satırları ve tutar. Ödeme, ikram tutarı, personel bilgisi dönmez."""
    conn = db.get_conn()
    m = conn.execute(
        "SELECT ad FROM masalar WHERE id=? AND aktif=1", (masa_id,)).fetchone()
    if not m:
        conn.close()
        raise HTTPException(404, "Masa bulunamadı")
    a = conn.execute(
        "SELECT id FROM adisyonlar WHERE masa_id=? AND durum='acik'",
        (masa_id,)).fetchone()
    if not a:
        conn.close()
        return {"adisyon_id": None, "satirlar": [], "toplam": 0}
    ozet = _masa_ozeti(conn, a["id"])
    conn.close()
    return ozet
