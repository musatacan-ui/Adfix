"""
Raporlar ve gün sonu (Z raporu).

GÜN SONU MANTIĞI
  Kapanmış ama henüz bir gün sonuna bağlanmamış (gun_sonu_id IS NULL) adisyonlar
  tek bir gün sonu kaydına mühürlenir. Böylece bir adisyon İKİ kez ciroya
  girmez — gece yarısını aşan servis (00:30'da kapanan masa) da doğru güne yazılır.
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
import database as db
import auth

router = APIRouter()


class GunSonuForm(BaseModel):
    zorla: int = 0          # 1 → açık adisyon olsa da gün sonu al


def _tarih_kosul(bas: str, bit: str, alan: str = "a.kapanis"):
    kosul, par = [], []
    if bas:
        kosul.append(f"date({alan}) >= ?"); par.append(bas)
    if bit:
        kosul.append(f"date({alan}) <= ?"); par.append(bit)
    return (" AND " + " AND ".join(kosul) if kosul else ""), par


@router.get("/ozet")
def ozet(bas: str = "", bit: str = "", mevcut: dict = Depends(auth.token_dogrula)):
    """Tarih aralığı raporu. bas/bit boşsa bugün."""
    if not bas and not bit:
        conn0 = db.get_conn()
        bugun = conn0.execute("SELECT date('now','localtime') g").fetchone()["g"]
        conn0.close()
        bas = bit = bugun
    ek, par = _tarih_kosul(bas, bit)
    conn = db.get_conn()

    genel = conn.execute(f"""
        SELECT COUNT(*) AS adisyon,
               COALESCE(SUM(a.kisi),0) AS kisi
        FROM adisyonlar a WHERE a.durum='kapali'{ek}""", par).fetchone()

    satir = conn.execute(f"""
        SELECT
          COALESCE(SUM(CASE WHEN s.durum IN ('bekliyor','hazir')
                            THEN s.birim_kurus*s.adet END),0) AS brut,
          COALESCE(SUM(CASE WHEN s.durum='ikram' THEN s.birim_kurus*s.adet END),0) AS ikram,
          COALESCE(SUM(CASE WHEN s.durum='iptal' THEN s.birim_kurus*s.adet END),0) AS iptal
        FROM adisyon_satir s JOIN adisyonlar a ON a.id=s.adisyon_id
        WHERE a.durum='kapali'{ek}""", par).fetchone()

    iskonto = conn.execute(f"""
        SELECT COALESCE(SUM(a.iskonto_kurus),0) t
        FROM adisyonlar a WHERE a.durum='kapali'{ek}""", par).fetchone()["t"]

    odeme = {r["tur"]: r["t"] for r in conn.execute(f"""
        SELECT o.tur, COALESCE(SUM(o.tutar_kurus),0) t
        FROM odemeler o JOIN adisyonlar a ON a.id=o.adisyon_id
        WHERE a.durum='kapali'{ek} GROUP BY o.tur""", par)}

    urunler = [dict(r) for r in conn.execute(f"""
        SELECT s.ad, SUM(s.adet) adet, SUM(s.birim_kurus*s.adet) tutar
        FROM adisyon_satir s JOIN adisyonlar a ON a.id=s.adisyon_id
        WHERE a.durum='kapali' AND s.durum IN ('bekliyor','hazir'){ek}
        GROUP BY s.ad ORDER BY adet DESC, tutar DESC LIMIT 20""", par)]

    kategoriler = [dict(r) for r in conn.execute(f"""
        SELECT COALESCE(k.ad,'(silinmiş)') ad, SUM(s.adet) adet,
               SUM(s.birim_kurus*s.adet) tutar
        FROM adisyon_satir s
        JOIN adisyonlar a ON a.id=s.adisyon_id
        LEFT JOIN urunler u ON u.id=s.urun_id
        LEFT JOIN kategoriler k ON k.id=u.kategori_id
        WHERE a.durum='kapali' AND s.durum IN ('bekliyor','hazir'){ek}
        GROUP BY k.ad ORDER BY tutar DESC""", par)]

    personel = [dict(r) for r in conn.execute(f"""
        SELECT COALESCE(k.ad_soyad,'-') ad, COUNT(DISTINCT a.id) adisyon,
               COALESCE(SUM(s.birim_kurus*s.adet),0) tutar
        FROM adisyonlar a
        LEFT JOIN kullanicilar k ON k.id=a.acan_id
        LEFT JOIN adisyon_satir s ON s.adisyon_id=a.id
             AND s.durum IN ('bekliyor','hazir')
        WHERE a.durum='kapali'{ek}
        GROUP BY a.acan_id ORDER BY tutar DESC""", par)]

    saatler = [dict(r) for r in conn.execute(f"""
        SELECT strftime('%H', a.kapanis) saat, COUNT(*) adisyon
        FROM adisyonlar a WHERE a.durum='kapali'{ek}
        GROUP BY saat ORDER BY saat""", par)]

    gunler = [dict(r) for r in conn.execute(f"""
        SELECT date(a.kapanis) gun, COUNT(*) adisyon,
               COALESCE(SUM((SELECT SUM(tutar_kurus) FROM odemeler o
                             WHERE o.adisyon_id=a.id)),0) tutar
        FROM adisyonlar a WHERE a.durum='kapali'{ek}
        GROUP BY gun ORDER BY gun""", par)]

    iptaller = conn.execute(f"""
        SELECT COUNT(*) n FROM adisyonlar a WHERE a.durum='iptal'{ek}""", par).fetchone()["n"]
    conn.close()

    brut, ikram_t = satir["brut"], satir["ikram"]
    net = brut - iskonto
    return {
        "bas": bas, "bit": bit,
        "adisyon_sayisi": genel["adisyon"], "kisi_sayisi": genel["kisi"],
        "brut_kurus": brut, "iskonto_kurus": iskonto, "ikram_kurus": ikram_t,
        "iptal_kurus": satir["iptal"], "net_kurus": net,
        "iptal_adisyon": iptaller,
        "odeme": {t: odeme.get(t, 0) for t in
                  ("nakit", "kart", "yemek_ceki", "acik_hesap")},
        "ortalama_adisyon": net // genel["adisyon"] if genel["adisyon"] else 0,
        "kisi_basi": net // genel["kisi"] if genel["kisi"] else 0,
        "urunler": urunler, "kategoriler": kategoriler,
        "personel": personel, "saatler": saatler, "gunler": gunler,
    }


@router.get("/gun-sonu/onizleme")
def gun_sonu_onizleme(mevcut: dict = Depends(auth.token_dogrula)):
    """Gün sonu alınırsa neyin mühürleneceğini gösterir — kapatmadan önce kontrol."""
    conn = db.get_conn()
    r = _bekleyen_toplamlar(conn)
    acik = [dict(x) for x in conn.execute("""
        SELECT a.id, a.kod, a.tip, m.ad AS masa_ad, a.acilis
        FROM adisyonlar a LEFT JOIN masalar m ON m.id=a.masa_id
        WHERE a.durum='acik' ORDER BY a.id""")]
    son = conn.execute("SELECT * FROM gun_sonu ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    return {**r, "acik_adisyonlar": acik,
            "son_gun_sonu": dict(son) if son else None}


def _bekleyen_toplamlar(conn) -> dict:
    """Henüz gün sonuna bağlanmamış kapalı adisyonların toplamları."""
    kosul = "a.durum='kapali' AND a.gun_sonu_id IS NULL"
    sayi = conn.execute(f"SELECT COUNT(*) n FROM adisyonlar a WHERE {kosul}").fetchone()["n"]
    s = conn.execute(f"""
        SELECT COALESCE(SUM(CASE WHEN s.durum IN ('bekliyor','hazir')
                                 THEN s.birim_kurus*s.adet END),0) brut,
               COALESCE(SUM(CASE WHEN s.durum='ikram' THEN s.birim_kurus*s.adet END),0) ikram
        FROM adisyon_satir s JOIN adisyonlar a ON a.id=s.adisyon_id
        WHERE {kosul}""").fetchone()
    isk = conn.execute(
        f"SELECT COALESCE(SUM(a.iskonto_kurus),0) t FROM adisyonlar a WHERE {kosul}"
    ).fetchone()["t"]
    od = {r["tur"]: r["t"] for r in conn.execute(f"""
        SELECT o.tur, COALESCE(SUM(o.tutar_kurus),0) t
        FROM odemeler o JOIN adisyonlar a ON a.id=o.adisyon_id
        WHERE {kosul} GROUP BY o.tur""")}
    return {
        "adisyon_sayisi": sayi,
        "brut_kurus": s["brut"], "ikram_kurus": s["ikram"], "iskonto_kurus": isk,
        "net_kurus": s["brut"] - isk,
        "nakit_kurus": od.get("nakit", 0), "kart_kurus": od.get("kart", 0),
        "ceki_kurus": od.get("yemek_ceki", 0), "acik_kurus": od.get("acik_hesap", 0),
    }


@router.post("/gun-sonu")
def gun_sonu_al(form: GunSonuForm, mevcut: dict = Depends(auth.yonetici_gerektir)):
    conn = db.get_conn()
    acik = conn.execute("SELECT COUNT(*) n FROM adisyonlar WHERE durum='acik'").fetchone()["n"]
    if acik and not form.zorla:
        conn.close()
        raise HTTPException(400, f"{acik} adet açık adisyon var. Kapatın ya da "
                                 f"'yine de al' ile devam edin (açıklar yarına devreder).")
    t = _bekleyen_toplamlar(conn)
    if t["adisyon_sayisi"] == 0:
        conn.close()
        raise HTTPException(400, "Gün sonuna girecek kapanmış adisyon yok")
    cur = conn.execute("""
        INSERT INTO gun_sonu (tarih, adisyon_sayisi, brut_kurus, iskonto_kurus,
                              ikram_kurus, net_kurus, nakit_kurus, kart_kurus,
                              ceki_kurus, acik_kurus, kapatan_id)
        VALUES (date('now','localtime'),?,?,?,?,?,?,?,?,?,?)""",
        (t["adisyon_sayisi"], t["brut_kurus"], t["iskonto_kurus"], t["ikram_kurus"],
         t["net_kurus"], t["nakit_kurus"], t["kart_kurus"], t["ceki_kurus"],
         t["acik_kurus"], mevcut["id"]))
    gid = cur.lastrowid
    conn.execute("UPDATE adisyonlar SET gun_sonu_id=? "
                 "WHERE durum='kapali' AND gun_sonu_id IS NULL", (gid,))
    db.kayit_log(conn, mevcut, "gun_sonu",
                 f"#{gid}: {t['adisyon_sayisi']} adisyon / {t['net_kurus']} kr")
    conn.commit()
    kayit = dict(conn.execute("SELECT * FROM gun_sonu WHERE id=?", (gid,)).fetchone())
    conn.close()
    return {**kayit, "devreden_acik": acik}


@router.get("/gun-sonu/liste")
def gun_sonu_liste(limit: int = 60, mevcut: dict = Depends(auth.token_dogrula)):
    conn = db.get_conn()
    r = [dict(x) for x in conn.execute("""
        SELECT g.*, k.ad_soyad AS kapatan_ad FROM gun_sonu g
        LEFT JOIN kullanicilar k ON k.id=g.kapatan_id
        ORDER BY g.id DESC LIMIT ?""", (min(limit, 500),))]
    conn.close()
    return r


@router.get("/gun-sonu/{gid}")
def gun_sonu_detay(gid: int, mevcut: dict = Depends(auth.token_dogrula)):
    conn = db.get_conn()
    g = conn.execute("""
        SELECT g.*, k.ad_soyad AS kapatan_ad FROM gun_sonu g
        LEFT JOIN kullanicilar k ON k.id=g.kapatan_id WHERE g.id=?""", (gid,)).fetchone()
    if not g:
        conn.close()
        raise HTTPException(404, "Gün sonu kaydı bulunamadı")
    adisyonlar = [dict(x) for x in conn.execute("""
        SELECT a.id, a.kod, a.tip, a.kapanis, m.ad AS masa_ad,
               (SELECT COALESCE(SUM(tutar_kurus),0) FROM odemeler o
                WHERE o.adisyon_id=a.id) AS tahsilat
        FROM adisyonlar a LEFT JOIN masalar m ON m.id=a.masa_id
        WHERE a.gun_sonu_id=? ORDER BY a.id""", (gid,))]
    urunler = [dict(x) for x in conn.execute("""
        SELECT s.ad, SUM(s.adet) adet, SUM(s.birim_kurus*s.adet) tutar
        FROM adisyon_satir s JOIN adisyonlar a ON a.id=s.adisyon_id
        WHERE a.gun_sonu_id=? AND s.durum IN ('bekliyor','hazir')
        GROUP BY s.ad ORDER BY adet DESC LIMIT 30""", (gid,))]
    conn.close()
    return {**dict(g), "adisyonlar": adisyonlar, "urunler": urunler}
