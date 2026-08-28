"""
Müşteri tarafı — karekod ile erişilen HERKESE AÇIK uçlar (kimlik doğrulama yok).

Güvenlik sınırı: buradan SADECE menü ve işletme kartviziti okunur.
Ciro, adisyon, personel, ayar yazma gibi hiçbir şey bu router'dan görünmez.
Yazma işlemi yoktur; tüm uçlar salt okunurdur.
"""
from fastapi import APIRouter, HTTPException, Response
import database as db

router = APIRouter()


@router.get("/menu")
def acik_menu():
    """QR menüsünün gösterdiği veri: işletme kartviziti + aktif menü."""
    conn = db.get_conn()
    ayar = db.ayarlari_al(conn)
    kategoriler = [dict(x) for x in conn.execute(
        "SELECT id, ad, renk, ikon FROM kategoriler WHERE aktif=1 ORDER BY sira, ad")]
    urunler = [dict(x) for x in conn.execute(
        "SELECT id, kategori_id, ad, fiyat_kurus, aciklama, gorsel "
        "FROM urunler WHERE aktif=1 ORDER BY sira, ad")]
    conn.close()
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
