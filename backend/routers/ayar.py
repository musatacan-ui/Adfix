"""İşletme ayarları — ad, logo, adres, telefon, fiş notu, QR taban adresi.

Logo veritabanında data URI olarak saklanır. Böylece tek bir adfix.db dosyası
yedeklendiğinde logo da yedeklenmiş olur (ayrı dosya yönetimi gerekmez).
"""
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from typing import Optional
import os
import database as db
import auth
import ag

router = APIRouter()

# Tarayıcı logoyu 400 px'e küçültüp PNG'ye çeviriyor (~40 KB).
# 600 KB, kazara yüklenen dev dosyaya karşı tampon.
LOGO_AZAMI = 600_000


class AyarForm(BaseModel):
    isletme_adi:  Optional[str] = None
    slogan:       Optional[str] = None
    adres:        Optional[str] = None
    telefon:      Optional[str] = None
    logo:         Optional[str] = None
    fis_alt_not:  Optional[str] = None
    qr_taban_url: Optional[str] = None


@router.get("/ag")
def ag_bilgisi(request: Request, mevcut: dict = Depends(auth.yonetici_gerektir)):
    """QR menüsünün çalışması için gereken ağ bilgisi.

    Yönetici `ipconfig` çalıştırmak zorunda kalmasın diye sunucu kendi yerel ağ
    adresini bulur ve doğrudan önerir."""
    port = int(os.environ.get("ADFIX_PORT", "8002"))
    adresler = ag.yerel_adresler()
    istek_host = request.headers.get("host", "")
    return {
        "port": port,
        "adresler": adresler,
        "adaylar": [f"http://{ip}:{port}" for ip in adresler],
        "onerilen": ag.onerilen_taban(port),
        # Yöneticinin tarayıcısı sunucuya hangi adresle ulaştı?
        # localhost ise karekodlar telefonda ÇALIŞMAZ.
        "istek_host": istek_host,
        "yerelden_acilmis": istek_host.split(":")[0] in ("localhost", "127.0.0.1", "::1"),
    }


@router.get("")
def ayarlar(mevcut: dict = Depends(auth.token_dogrula)):
    conn = db.get_conn()
    a = db.ayarlari_al(conn)
    conn.close()
    return a


@router.patch("")
def guncelle(form: AyarForm, mevcut: dict = Depends(auth.yonetici_gerektir)):
    veri = form.model_dump(exclude_none=True)
    if not veri:
        raise HTTPException(400, "Güncellenecek alan yok")

    if "logo" in veri:
        logo = veri["logo"].strip()
        if logo and not logo.startswith("data:image/"):
            raise HTTPException(400, "Logo geçersiz biçimde")
        if len(logo) > LOGO_AZAMI:
            raise HTTPException(400, "Logo çok büyük (en fazla 600 KB)")
        veri["logo"] = logo

    if "qr_taban_url" in veri:
        u = veri["qr_taban_url"].strip().rstrip("/")
        if u and not (u.startswith("http://") or u.startswith("https://")):
            raise HTTPException(400, "QR adresi http:// veya https:// ile başlamalı")
        veri["qr_taban_url"] = u

    conn = db.get_conn()
    for anahtar, deger in veri.items():
        db.ayar_yaz(conn, anahtar, str(deger).strip() if anahtar != "logo" else deger)
    db.kayit_log(conn, mevcut, "ayar_guncellendi", ", ".join(veri.keys()))
    conn.commit()
    yeni = db.ayarlari_al(conn)
    conn.close()
    return yeni
