from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from typing import Optional
from collections import defaultdict
import time
import database as db
import auth
import tenant

router = APIRouter()

# ── Giriş hız sınırı (kaba kuvvet koruması) ──
_denemeler = defaultdict(list)
_LIMIT, _PENCERE = 10, 60


def _hiz_siniri(request: Request):
    ip = request.client.host if request.client else "bilinmiyor"
    simdi = time.time()
    _denemeler[ip] = [t for t in _denemeler[ip] if simdi - t < _PENCERE]
    if len(_denemeler[ip]) >= _LIMIT:
        raise HTTPException(429, "Çok fazla giriş denemesi. 1 dakika bekleyin.")
    _denemeler[ip].append(simdi)


class GirisForm(BaseModel):
    kullanici_adi: str
    sifre: str


class KullaniciForm(BaseModel):
    ad_soyad: str
    kullanici_adi: str
    sifre: Optional[str] = None
    rol: str
    aktif: int = 1


class SifreForm(BaseModel):
    eski: str
    yeni: str


@router.post("/giris")
def giris(request: Request, form: GirisForm):
    _hiz_siniri(request)
    conn = db.get_conn()
    k = conn.execute("SELECT * FROM kullanicilar WHERE kullanici_adi=?",
                     (form.kullanici_adi.strip(),)).fetchone()
    if not k or not auth.sifre_dogrula(form.sifre, k["sifre_hash"]):
        conn.close()
        raise HTTPException(401, "Kullanıcı adı veya şifre hatalı")
    if not k["aktif"]:
        conn.close()
        raise HTTPException(403, "Bu hesap pasif durumda")
    db.kayit_log(conn, dict(k), "giris", k["kullanici_adi"])
    conn.commit()
    conn.close()
    slug = tenant.isletme_slug.get()
    return {
        "token": auth.token_olustur(k, isletme=slug),
        "kullanici": {"id": k["id"], "ad_soyad": k["ad_soyad"],
                      "kullanici_adi": k["kullanici_adi"], "rol": k["rol"]},
    }


@router.get("/ben")
def ben(mevcut: dict = Depends(auth.token_dogrula)):
    return {"id": mevcut["id"], "ad_soyad": mevcut["ad_soyad"],
            "kullanici_adi": mevcut["kullanici_adi"], "rol": mevcut["rol"]}


@router.post("/sifre")
def sifre_degistir(form: SifreForm, mevcut: dict = Depends(auth.token_dogrula)):
    if len(form.yeni) < 6:
        raise HTTPException(400, "Yeni şifre en az 6 karakter olmalı")
    conn = db.get_conn()
    k = conn.execute("SELECT * FROM kullanicilar WHERE id=?", (mevcut["id"],)).fetchone()
    if not k or not auth.sifre_dogrula(form.eski, k["sifre_hash"]):
        conn.close()
        raise HTTPException(401, "Mevcut şifre hatalı")
    conn.execute("UPDATE kullanicilar SET sifre_hash=? WHERE id=?",
                 (auth.hash_sifre(form.yeni), mevcut["id"]))
    db.kayit_log(conn, mevcut, "sifre_degisti", k["kullanici_adi"])
    conn.commit()
    conn.close()
    return {"mesaj": "Şifre güncellendi"}


@router.get("/liste")
def liste(mevcut: dict = Depends(auth.yonetici_gerektir)):
    conn = db.get_conn()
    r = [dict(x) for x in conn.execute(
        "SELECT id, ad_soyad, kullanici_adi, rol, aktif, olusturma "
        "FROM kullanicilar ORDER BY aktif DESC, ad_soyad")]
    conn.close()
    return r


@router.post("/ekle")
def ekle(form: KullaniciForm, mevcut: dict = Depends(auth.yonetici_gerektir)):
    if form.rol not in db.ROLLER:
        raise HTTPException(400, f"Geçersiz rol. Roller: {', '.join(db.ROLLER)}")
    if not form.sifre or len(form.sifre) < 6:
        raise HTTPException(400, "Şifre en az 6 karakter olmalı")
    conn = db.get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO kullanicilar (ad_soyad, kullanici_adi, sifre_hash, rol, aktif) "
            "VALUES (?,?,?,?,?)",
            (form.ad_soyad.strip(), form.kullanici_adi.strip(),
             auth.hash_sifre(form.sifre), form.rol, form.aktif))
        db.kayit_log(conn, mevcut, "kullanici_eklendi", form.kullanici_adi)
        conn.commit()
        yid = cur.lastrowid
    except db.sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(400, "Bu kullanıcı adı zaten kayıtlı")
    conn.close()
    return {"id": yid, "mesaj": "Kullanıcı eklendi"}


@router.patch("/{kid}")
def guncelle(kid: int, form: KullaniciForm, mevcut: dict = Depends(auth.yonetici_gerektir)):
    if form.rol not in db.ROLLER:
        raise HTTPException(400, "Geçersiz rol")
    conn = db.get_conn()
    var = conn.execute("SELECT * FROM kullanicilar WHERE id=?", (kid,)).fetchone()
    if not var:
        conn.close()
        raise HTTPException(404, "Kullanıcı bulunamadı")
    # Son aktif yöneticinin yetkisi düşürülemez / pasife alınamaz → sisteme kilitlenme olmasın.
    if var["rol"] == "yonetici" and (form.rol != "yonetici" or not form.aktif):
        kalan = conn.execute(
            "SELECT COUNT(*) n FROM kullanicilar WHERE rol='yonetici' AND aktif=1 AND id<>?",
            (kid,)).fetchone()["n"]
        if kalan == 0:
            conn.close()
            raise HTTPException(400, "Sistemde en az bir aktif yönetici kalmalı")
    conn.execute("UPDATE kullanicilar SET ad_soyad=?, kullanici_adi=?, rol=?, aktif=? WHERE id=?",
                 (form.ad_soyad.strip(), form.kullanici_adi.strip(), form.rol, form.aktif, kid))
    if form.sifre:
        if len(form.sifre) < 6:
            conn.close()
            raise HTTPException(400, "Şifre en az 6 karakter olmalı")
        conn.execute("UPDATE kullanicilar SET sifre_hash=? WHERE id=?",
                     (auth.hash_sifre(form.sifre), kid))
    db.kayit_log(conn, mevcut, "kullanici_guncellendi", form.kullanici_adi)
    conn.commit()
    conn.close()
    return {"mesaj": "Kullanıcı güncellendi"}


@router.get("/log")
def log_listesi(limit: int = 200, mevcut: dict = Depends(auth.yonetici_gerektir)):
    conn = db.get_conn()
    r = [dict(x) for x in conn.execute(
        "SELECT * FROM log ORDER BY id DESC LIMIT ?", (min(limit, 1000),))]
    conn.close()
    return r
