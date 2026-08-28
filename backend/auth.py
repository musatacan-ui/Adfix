"""
Adfix — kimlik doğrulama.
JWT secret ortam değişkeninden okunur, kaynağa asla gömülmez.
  export ADFIX_JWT_SECRET=$(python3 -c 'import secrets;print(secrets.token_urlsafe(48))')
"""
import os, datetime
import jwt
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

SECRET = os.environ.get("ADFIX_JWT_SECRET")
if not SECRET:
    raise RuntimeError(
        "ADFIX_JWT_SECRET ortam değişkeni tanımlı değil. En az 32 karakter olmalı.\n"
        "Üretmek için: python3 -c 'import secrets; print(secrets.token_urlsafe(48))'"
    )
if len(SECRET) < 32:
    raise RuntimeError("ADFIX_JWT_SECRET çok kısa (en az 32 karakter olmalı).")

ALGORITHM = "HS256"
EXPIRE_HOURS = 16          # bir vardiya + devir payı

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


def token_olustur(kullanici) -> str:
    payload = {
        "id": kullanici["id"],
        "kullanici_adi": kullanici["kullanici_adi"],
        "ad_soyad": kullanici["ad_soyad"],
        "rol": kullanici["rol"],
        "exp": datetime.datetime.now(datetime.timezone.utc)
               + datetime.timedelta(hours=EXPIRE_HOURS),
    }
    return jwt.encode(payload, SECRET, algorithm=ALGORITHM)


def token_dogrula(kimlik: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    try:
        return jwt.decode(kimlik.credentials, SECRET, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Oturum süresi doldu, tekrar giriş yapın")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Geçersiz oturum")


def kasiyer_gerektir(kullanici: dict = Depends(token_dogrula)) -> dict:
    """Para hareketi: ödeme, iskonto, ikram, satır iptali, adisyon kapatma."""
    if kullanici["rol"] not in ("kasiyer", "yonetici"):
        raise HTTPException(403, "Bu işlem için kasiyer yetkisi gerekli")
    return kullanici


def yonetici_gerektir(kullanici: dict = Depends(token_dogrula)) -> dict:
    """Menü, masa düzeni, kullanıcı ve gün sonu işlemleri."""
    if kullanici["rol"] != "yonetici":
        raise HTTPException(403, "Bu işlem için yönetici yetkisi gerekli")
    return kullanici
