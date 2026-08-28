"""Menü yönetimi — kategoriler ve ürünler.
Fiyatlar API'de de KURUŞ (int) taşınır; TL'ye çevirme arayüzde yapılır."""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
import database as db
import auth

router = APIRouter()


# Yüklenen görsel data URI olarak saklanır. Üst sınır: tarayıcı zaten 500 px'e
# küçültüp JPEG'e çeviriyor (~30 KB); 400 KB kötü niyetli/kazara yüklemeye karşı tampon.
GORSEL_AZAMI = 400_000


def _gorsel_dogrula(gorsel: str) -> str:
    g = (gorsel or "").strip()
    if not g:
        return ""
    if len(g) > GORSEL_AZAMI:
        raise HTTPException(400, "Görsel çok büyük (en fazla 400 KB). Daha küçük bir dosya seçin.")
    if not (g.startswith("data:image/") or g.startswith("gorseller/")):
        raise HTTPException(400, "Geçersiz görsel biçimi")
    return g


class KategoriForm(BaseModel):
    ad: str
    renk: str = "#F97316"
    ikon: str = "utensils"
    sira: int = 0
    aktif: int = 1


class UrunForm(BaseModel):
    kategori_id: int
    ad: str
    fiyat_kurus: int
    aciklama: str = ""
    gorsel: str = ""
    mutfak: int = 1
    sira: int = 0
    aktif: int = 1


@router.get("")
def menu(mevcut: dict = Depends(auth.token_dogrula), hepsi: int = 0):
    """Sipariş ekranının kullandığı tam menü. hepsi=1 → pasifler de gelir (yönetim)."""
    conn = db.get_conn()
    kosul = "" if hepsi else " WHERE aktif=1"
    kats = [dict(x) for x in conn.execute(
        f"SELECT * FROM kategoriler{kosul} ORDER BY sira, ad")]
    urun_kosul = "" if hepsi else " WHERE aktif=1"
    urunler = [dict(x) for x in conn.execute(
        f"SELECT * FROM urunler{urun_kosul} ORDER BY sira, ad")]
    conn.close()
    for k in kats:
        k["urunler"] = [u for u in urunler if u["kategori_id"] == k["id"]]
    return kats


@router.post("/kategori")
def kategori_ekle(form: KategoriForm, mevcut: dict = Depends(auth.yonetici_gerektir)):
    if not form.ad.strip():
        raise HTTPException(400, "Kategori adı boş olamaz")
    conn = db.get_conn()
    cur = conn.execute(
        "INSERT INTO kategoriler (ad, renk, ikon, sira, aktif) VALUES (?,?,?,?,?)",
        (form.ad.strip(), form.renk, form.ikon.strip() or "utensils", form.sira, form.aktif))
    db.kayit_log(conn, mevcut, "kategori_eklendi", form.ad)
    conn.commit()
    kid = cur.lastrowid
    conn.close()
    return {"id": kid, "mesaj": "Kategori eklendi"}


@router.patch("/kategori/{kid}")
def kategori_guncelle(kid: int, form: KategoriForm,
                      mevcut: dict = Depends(auth.yonetici_gerektir)):
    conn = db.get_conn()
    if not conn.execute("SELECT 1 FROM kategoriler WHERE id=?", (kid,)).fetchone():
        conn.close()
        raise HTTPException(404, "Kategori bulunamadı")
    conn.execute("UPDATE kategoriler SET ad=?, renk=?, ikon=?, sira=?, aktif=? WHERE id=?",
                 (form.ad.strip(), form.renk, form.ikon.strip() or "utensils",
                  form.sira, form.aktif, kid))
    # Kategori pasife alınırsa altındaki ürünler de menüden düşer.
    if not form.aktif:
        conn.execute("UPDATE urunler SET aktif=0 WHERE kategori_id=?", (kid,))
    db.kayit_log(conn, mevcut, "kategori_guncellendi", form.ad)
    conn.commit()
    conn.close()
    return {"mesaj": "Kategori güncellendi"}


@router.delete("/kategori/{kid}")
def kategori_sil(kid: int, mevcut: dict = Depends(auth.yonetici_gerektir)):
    """Geçmiş adisyonlarda ürünü geçen kategori SİLİNMEZ, pasife alınır."""
    conn = db.get_conn()
    kullanim = conn.execute(
        "SELECT COUNT(*) n FROM adisyon_satir s JOIN urunler u ON u.id=s.urun_id "
        "WHERE u.kategori_id=?", (kid,)).fetchone()["n"]
    if kullanim:
        conn.execute("UPDATE kategoriler SET aktif=0 WHERE id=?", (kid,))
        conn.execute("UPDATE urunler SET aktif=0 WHERE kategori_id=?", (kid,))
        db.kayit_log(conn, mevcut, "kategori_pasif", f"id={kid} (geçmiş kayıt var)")
        conn.commit()
        conn.close()
        return {"mesaj": "Geçmiş adisyonlarda kullanıldığı için silinmedi, pasife alındı"}
    conn.execute("DELETE FROM urunler WHERE kategori_id=?", (kid,))
    conn.execute("DELETE FROM kategoriler WHERE id=?", (kid,))
    db.kayit_log(conn, mevcut, "kategori_silindi", f"id={kid}")
    conn.commit()
    conn.close()
    return {"mesaj": "Kategori silindi"}


@router.post("/urun")
def urun_ekle(form: UrunForm, mevcut: dict = Depends(auth.yonetici_gerektir)):
    if not form.ad.strip():
        raise HTTPException(400, "Ürün adı boş olamaz")
    if form.fiyat_kurus < 0:
        raise HTTPException(400, "Fiyat eksi olamaz")
    conn = db.get_conn()
    if not conn.execute("SELECT 1 FROM kategoriler WHERE id=?", (form.kategori_id,)).fetchone():
        conn.close()
        raise HTTPException(400, "Kategori bulunamadı")
    cur = conn.execute(
        "INSERT INTO urunler (kategori_id, ad, fiyat_kurus, aciklama, gorsel, mutfak, sira, aktif) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (form.kategori_id, form.ad.strip(), form.fiyat_kurus, form.aciklama,
         _gorsel_dogrula(form.gorsel), form.mutfak, form.sira, form.aktif))
    db.kayit_log(conn, mevcut, "urun_eklendi", f"{form.ad} / {form.fiyat_kurus}kr")
    conn.commit()
    uid = cur.lastrowid
    conn.close()
    return {"id": uid, "mesaj": "Ürün eklendi"}


@router.patch("/urun/{uid}")
def urun_guncelle(uid: int, form: UrunForm, mevcut: dict = Depends(auth.yonetici_gerektir)):
    conn = db.get_conn()
    eski = conn.execute("SELECT * FROM urunler WHERE id=?", (uid,)).fetchone()
    if not eski:
        conn.close()
        raise HTTPException(404, "Ürün bulunamadı")
    conn.execute(
        "UPDATE urunler SET kategori_id=?, ad=?, fiyat_kurus=?, aciklama=?, gorsel=?, "
        "mutfak=?, sira=?, aktif=? WHERE id=?",
        (form.kategori_id, form.ad.strip(), form.fiyat_kurus, form.aciklama,
         _gorsel_dogrula(form.gorsel), form.mutfak, form.sira, form.aktif, uid))
    if eski["fiyat_kurus"] != form.fiyat_kurus:
        # Fiyat değişikliği açık adisyonları ETKİLEMEZ: satırlar fiyatı anlık kopyalar.
        db.kayit_log(conn, mevcut, "fiyat_degisti",
                     f"{form.ad}: {eski['fiyat_kurus']} -> {form.fiyat_kurus} kr")
    db.kayit_log(conn, mevcut, "urun_guncellendi", form.ad)
    conn.commit()
    conn.close()
    return {"mesaj": "Ürün güncellendi"}


@router.delete("/urun/{uid}")
def urun_sil(uid: int, mevcut: dict = Depends(auth.yonetici_gerektir)):
    conn = db.get_conn()
    kullanim = conn.execute("SELECT COUNT(*) n FROM adisyon_satir WHERE urun_id=?",
                            (uid,)).fetchone()["n"]
    if kullanim:
        conn.execute("UPDATE urunler SET aktif=0 WHERE id=?", (uid,))
        db.kayit_log(conn, mevcut, "urun_pasif", f"id={uid} (geçmiş kayıt var)")
        conn.commit()
        conn.close()
        return {"mesaj": "Geçmiş adisyonlarda kullanıldığı için silinmedi, pasife alındı"}
    conn.execute("DELETE FROM urunler WHERE id=?", (uid,))
    db.kayit_log(conn, mevcut, "urun_silindi", f"id={uid}")
    conn.commit()
    conn.close()
    return {"mesaj": "Ürün silindi"}
