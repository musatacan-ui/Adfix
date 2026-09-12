"""
Merkez yonetim — isletme CRUD + istatistik + admin sifre sifirlama.
Super yonetici sifresiyle erisilir (ADFIX_SUPER_SIFRE ortam degiskeni).
"""
from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import os, re, jwt, datetime

import database as db

router = APIRouter()

SUPER_SIFRE = os.environ.get("ADFIX_SUPER_SIFRE", "")
JWT_SECRET = os.environ.get("ADFIX_JWT_SECRET", "nosecret")
ALGORITHM = "HS256"

security = HTTPBearer(auto_error=False)


class MerkezGirisForm(BaseModel):
    sifre: str


class IsletmeForm(BaseModel):
    slug: str
    ad: str
    ilk_sifre: str = "adfix2026"


class SifreSifirlaForm(BaseModel):
    yeni_sifre: str


def super_gerektir(kimlik: HTTPAuthorizationCredentials = Depends(security)):
    if not kimlik:
        raise HTTPException(401, "Oturum gerekli")
    try:
        payload = jwt.decode(kimlik.credentials, JWT_SECRET, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Oturum suresi doldu")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Gecersiz oturum")
    if payload.get("rol") != "super":
        raise HTTPException(403, "Super yonetici yetkisi gerekli")
    return payload


@router.post("/giris")
def merkez_giris(form: MerkezGirisForm):
    if not SUPER_SIFRE:
        raise HTTPException(503, "Super yonetici sifresi tanimlanmamis (ADFIX_SUPER_SIFRE)")
    if form.sifre != SUPER_SIFRE:
        raise HTTPException(401, "Hatali sifre")
    payload = {
        "rol": "super",
        "exp": datetime.datetime.now(datetime.timezone.utc)
               + datetime.timedelta(hours=16),
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=ALGORITHM)
    return {"token": token, "rol": "super"}


@router.get("/isletme/liste")
def isletme_liste(_=Depends(super_gerektir)):
    return db.isletme_listesi()


@router.get("/isletme/{slug}/istatistik")
def isletme_istatistik(slug: str, _=Depends(super_gerektir)):
    mc = db.merkez_conn()
    isl = mc.execute("SELECT id FROM isletmeler WHERE slug=?", (slug,)).fetchone()
    mc.close()
    if not isl:
        raise HTTPException(404, "Isletme bulunamadi")
    import tenant
    tok = tenant.isletme_slug.set(slug)
    try:
        conn = db.get_conn()
        masa_sayisi = conn.execute(
            "SELECT COUNT(*) n FROM masalar WHERE aktif=1").fetchone()["n"]
        acik_adisyon = conn.execute(
            "SELECT COUNT(*) n FROM adisyonlar WHERE durum='acik'").fetchone()["n"]
        bugun_ciro = conn.execute(
            "SELECT COALESCE(SUM(tutar_kurus),0) n FROM odemeler "
            "WHERE date(zaman)=date('now','localtime')").fetchone()["n"]
        bugun_siparis = conn.execute(
            "SELECT COUNT(*) n FROM adisyonlar WHERE durum='kapali' "
            "AND date(kapanis)=date('now','localtime')").fetchone()["n"]
        kullanici_sayisi = conn.execute(
            "SELECT COUNT(*) n FROM kullanicilar WHERE aktif=1").fetchone()["n"]
        conn.close()
    except Exception:
        try: conn.close()
        except Exception: pass
        raise
    finally:
        tenant.isletme_slug.reset(tok)
    return {
        "masa_sayisi": masa_sayisi,
        "acik_adisyon": acik_adisyon,
        "bugun_ciro_kurus": bugun_ciro,
        "bugun_siparis": bugun_siparis,
        "kullanici_sayisi": kullanici_sayisi,
    }


@router.post("/isletme/{slug}/admin-sifre-sifirla")
def admin_sifre_sifirla(slug: str, form: SifreSifirlaForm, _=Depends(super_gerektir)):
    if len(form.yeni_sifre) < 4:
        raise HTTPException(400, "Sifre en az 4 karakter olmali")
    mc = db.merkez_conn()
    isl = mc.execute("SELECT id FROM isletmeler WHERE slug=?", (slug,)).fetchone()
    mc.close()
    if not isl:
        raise HTTPException(404, "Isletme bulunamadi")
    import auth as auth_mod
    import tenant
    hash_ = auth_mod.hash_sifre(form.yeni_sifre)
    tok = tenant.isletme_slug.set(slug)
    try:
        conn = db.get_conn()
        c = conn.execute(
            "UPDATE kullanicilar SET sifre_hash=? WHERE rol='yonetici'", (hash_,))
        count = c.rowcount
        conn.commit()
        conn.close()
    except Exception:
        try: conn.close()
        except Exception: pass
        raise
    finally:
        tenant.isletme_slug.reset(tok)
    return {"mesaj": f"{count} yonetici sifresi guncellendi"}


@router.post("/isletme/olustur")
def isletme_olustur(form: IsletmeForm, _=Depends(super_gerektir)):
    slug = form.slug.strip().lower()
    slug = re.sub(r'[^a-z0-9-]', '-', slug)
    slug = re.sub(r'-+', '-', slug).strip('-')
    if len(slug) < 2 or len(slug) > 50:
        raise HTTPException(400, "Slug: 2-50 karakter, kucuk harf/rakam/tire")
    if slug.startswith('_'):
        raise HTTPException(400, "Slug alt cizgiyle baslayamaz")
    try:
        db.isletme_olustur(slug, form.ad.strip(), form.ilk_sifre or "adfix2026")
    except Exception as e:
        if "UNIQUE" in str(e):
            raise HTTPException(400, f"'{slug}' zaten kullaniliyor")
        raise
    return {"mesaj": f"Isletme olusturuldu: {form.ad}", "slug": slug,
            "url": f"/i/{slug}/"}


@router.patch("/isletme/{slug}")
def isletme_guncelle(slug: str, ad: str = None, aktif: int = None,
                     _=Depends(super_gerektir)):
    mc = db.merkez_conn()
    isl = mc.execute("SELECT * FROM isletmeler WHERE slug=?", (slug,)).fetchone()
    if not isl:
        mc.close()
        raise HTTPException(404, "Isletme bulunamadi")
    if ad is not None:
        mc.execute("UPDATE isletmeler SET ad=? WHERE slug=?", (ad.strip(), slug))
    if aktif is not None:
        mc.execute("UPDATE isletmeler SET aktif=? WHERE slug=?", (aktif, slug))
    mc.commit()
    mc.close()
    return {"mesaj": "Guncellendi"}


@router.delete("/isletme/{slug}")
def isletme_sil(slug: str, _=Depends(super_gerektir)):
    mc = db.merkez_conn()
    isl = mc.execute("SELECT * FROM isletmeler WHERE slug=?", (slug,)).fetchone()
    mc.close()
    if not isl:
        raise HTTPException(404, "Isletme bulunamadi")
    db.isletme_sil(slug)
    return {"mesaj": f"'{isl['ad']}' silindi"}
