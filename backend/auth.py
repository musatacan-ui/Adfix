"""
Adfix — kimlik dogrulama.
JWT secret ortam degiskeninden okunur, kaynaga asla gomulmez.
  export ADFIX_JWT_SECRET=$(python3 -c 'import secrets;print(secrets.token_urlsafe(48))')
"""
import os, datetime
import jwt
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import tenant

SECRET = os.environ.get("ADFIX_JWT_SECRET")
if not SECRET:
    raise RuntimeError(
        "ADFIX_JWT_SECRET ortam degiskeni tanimli degil. En az 32 karakter olmali.\n"
        "Uretmek icin: python3 -c 'import secrets; print(secrets.token_urlsafe(48))'"
    )
if len(SECRET) < 32:
    raise RuntimeError("ADFIX_JWT_SECRET cok kisa (en az 32 karakter olmali).")

ALGORITHM = "HS256"
EXPIRE_HOURS = 16

security = HTTPBearer()


def hash_sifre(sifre: str) -> str:
    import bcrypt
    return bcrypt.hashpw(sifre.encode(), bcrypt.gensalt(rounds=12)).decode()


def sifre_dogrula(sifre: str, kayitli_hash: str) -> bool:
    import bcrypt
    try:
        return bcrypt.checkpw(sifre.encode(), kayitli_hash.encode())
    except ValueError:
        return False


def token_olustur(kullanici, isletme: str | None = None) -> str:
    payload = {
        "id": kullanici["id"],
        "kullanici_adi": kullanici["kullanici_adi"],
        "ad_soyad": kullanici["ad_soyad"],
        "rol": kullanici["rol"],
        "exp": datetime.datetime.now(datetime.timezone.utc)
               + datetime.timedelta(hours=EXPIRE_HOURS),
    }
    if isletme:
        payload["isletme"] = isletme
    return jwt.encode(payload, SECRET, algorithm=ALGORITHM)


def token_dogrula(kimlik: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    try:
        payload = jwt.decode(kimlik.credentials, SECRET, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Oturum suresi doldu, tekrar giris yapin")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Gecersiz oturum")
    slug = tenant.isletme_slug.get()
    token_isletme = payload.get("isletme")
    if slug != token_isletme:
        raise HTTPException(401, "Bu token bu isletmeye ait degil")
    return payload


def kasiyer_gerektir(kullanici: dict = Depends(token_dogrula)) -> dict:
    """Para hareketi: odeme, iskonto, ikram, satir iptali, adisyon kapatma."""
    if kullanici["rol"] not in ("kasiyer", "yonetici"):
        raise HTTPException(403, "Bu islem icin kasiyer yetkisi gerekli")
    return kullanici


def yonetici_gerektir(kullanici: dict = Depends(token_dogrula)) -> dict:
    """Menu, masa duzeni, kullanici ve gun sonu islemleri."""
    if kullanici["rol"] != "yonetici":
        raise HTTPException(403, "Bu islem icin yonetici yetkisi gerekli")
    return kullanici
