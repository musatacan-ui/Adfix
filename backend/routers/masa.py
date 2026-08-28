"""Masa planı — salonlar, masalar ve canlı doluluk durumu."""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
import database as db
import auth
import hesap

router = APIRouter()


class SalonForm(BaseModel):
    ad: str
    sira: int = 0
    aktif: int = 1


class MasaForm(BaseModel):
    salon_id: int
    ad: str
    kapasite: int = 4
    sira: int = 0
    aktif: int = 1


@router.get("/plan")
def plan(mevcut: dict = Depends(auth.token_dogrula)):
    """Masa planı ekranı: salon > masa > (varsa) açık adisyon özeti."""
    conn = db.get_conn()
    salonlar = [dict(x) for x in conn.execute(
        "SELECT * FROM salonlar WHERE aktif=1 ORDER BY sira, ad")]
    masalar = [dict(x) for x in conn.execute(
        "SELECT * FROM masalar WHERE aktif=1 ORDER BY sira, ad")]
    acik = conn.execute("""
        SELECT a.*, k.ad_soyad AS acan_ad
        FROM adisyonlar a LEFT JOIN kullanicilar k ON k.id=a.acan_id
        WHERE a.durum='acik'
    """).fetchall()

    masa_adisyon = {}
    paketler = []
    for a in acik:
        o = hesap.ozet(conn, a["id"])
        kayit = {
            "adisyon_id": a["id"], "kod": a["kod"], "tip": a["tip"],
            "kisi": a["kisi"], "acilis": a["acilis"], "acan_ad": a["acan_ad"] or "",
            "musteri_ad": a["musteri_ad"], "musteri_tel": a["musteri_tel"],
            "net_toplam": o["net_toplam"], "odenen": o["odenen"],
            "kalan": o["kalan"], "urun_adet": o["urun_adet"],
            "bekleyen": conn.execute(
                "SELECT COUNT(*) n FROM adisyon_satir WHERE adisyon_id=? AND durum='bekliyor'",
                (a["id"],)).fetchone()["n"],
        }
        if a["masa_id"]:
            masa_adisyon[a["masa_id"]] = kayit
        else:
            paketler.append(kayit)
    conn.close()

    for m in masalar:
        m["adisyon"] = masa_adisyon.get(m["id"])
    for s in salonlar:
        s["masalar"] = [m for m in masalar if m["salon_id"] == s["id"]]

    return {
        "salonlar": salonlar,
        "paket": sorted(paketler, key=lambda x: x["adisyon_id"], reverse=True),
        "ozet": {
            "dolu": len(masa_adisyon),
            "toplam_masa": len(masalar),
            "acik_tutar": sum(v["kalan"] for v in masa_adisyon.values())
                          + sum(v["kalan"] for v in paketler),
        },
    }


@router.get("/salonlar")
def salon_listesi(mevcut: dict = Depends(auth.token_dogrula)):
    conn = db.get_conn()
    salonlar = [dict(x) for x in conn.execute("SELECT * FROM salonlar ORDER BY sira, ad")]
    masalar = [dict(x) for x in conn.execute("SELECT * FROM masalar ORDER BY sira, ad")]
    conn.close()
    for s in salonlar:
        s["masalar"] = [m for m in masalar if m["salon_id"] == s["id"]]
    return salonlar


@router.post("/salon")
def salon_ekle(form: SalonForm, mevcut: dict = Depends(auth.yonetici_gerektir)):
    if not form.ad.strip():
        raise HTTPException(400, "Salon adı boş olamaz")
    conn = db.get_conn()
    cur = conn.execute("INSERT INTO salonlar (ad, sira, aktif) VALUES (?,?,?)",
                       (form.ad.strip(), form.sira, form.aktif))
    db.kayit_log(conn, mevcut, "salon_eklendi", form.ad)
    conn.commit()
    sid = cur.lastrowid
    conn.close()
    return {"id": sid, "mesaj": "Salon eklendi"}


@router.patch("/salon/{sid}")
def salon_guncelle(sid: int, form: SalonForm, mevcut: dict = Depends(auth.yonetici_gerektir)):
    conn = db.get_conn()
    if not conn.execute("SELECT 1 FROM salonlar WHERE id=?", (sid,)).fetchone():
        conn.close()
        raise HTTPException(404, "Salon bulunamadı")
    if not form.aktif:
        acik = conn.execute(
            "SELECT COUNT(*) n FROM adisyonlar a JOIN masalar m ON m.id=a.masa_id "
            "WHERE m.salon_id=? AND a.durum='acik'", (sid,)).fetchone()["n"]
        if acik:
            conn.close()
            raise HTTPException(400, f"Bu salonda {acik} açık adisyon var, önce kapatın")
    conn.execute("UPDATE salonlar SET ad=?, sira=?, aktif=? WHERE id=?",
                 (form.ad.strip(), form.sira, form.aktif, sid))
    db.kayit_log(conn, mevcut, "salon_guncellendi", form.ad)
    conn.commit()
    conn.close()
    return {"mesaj": "Salon güncellendi"}


@router.post("/masa")
def masa_ekle(form: MasaForm, mevcut: dict = Depends(auth.yonetici_gerektir)):
    if not form.ad.strip():
        raise HTTPException(400, "Masa adı boş olamaz")
    conn = db.get_conn()
    if not conn.execute("SELECT 1 FROM salonlar WHERE id=?", (form.salon_id,)).fetchone():
        conn.close()
        raise HTTPException(400, "Salon bulunamadı")
    cur = conn.execute(
        "INSERT INTO masalar (salon_id, ad, kapasite, sira, aktif) VALUES (?,?,?,?,?)",
        (form.salon_id, form.ad.strip(), form.kapasite, form.sira, form.aktif))
    db.kayit_log(conn, mevcut, "masa_eklendi", form.ad)
    conn.commit()
    mid = cur.lastrowid
    conn.close()
    return {"id": mid, "mesaj": "Masa eklendi"}


@router.patch("/masa/{mid}")
def masa_guncelle(mid: int, form: MasaForm, mevcut: dict = Depends(auth.yonetici_gerektir)):
    conn = db.get_conn()
    if not conn.execute("SELECT 1 FROM masalar WHERE id=?", (mid,)).fetchone():
        conn.close()
        raise HTTPException(404, "Masa bulunamadı")
    if not form.aktif and conn.execute(
            "SELECT 1 FROM adisyonlar WHERE masa_id=? AND durum='acik'", (mid,)).fetchone():
        conn.close()
        raise HTTPException(400, "Masada açık adisyon var, önce hesabı kapatın")
    conn.execute("UPDATE masalar SET salon_id=?, ad=?, kapasite=?, sira=?, aktif=? WHERE id=?",
                 (form.salon_id, form.ad.strip(), form.kapasite, form.sira, form.aktif, mid))
    db.kayit_log(conn, mevcut, "masa_guncellendi", form.ad)
    conn.commit()
    conn.close()
    return {"mesaj": "Masa güncellendi"}


@router.delete("/masa/{mid}")
def masa_sil(mid: int, mevcut: dict = Depends(auth.yonetici_gerektir)):
    conn = db.get_conn()
    if conn.execute("SELECT 1 FROM adisyonlar WHERE masa_id=? AND durum='acik'",
                    (mid,)).fetchone():
        conn.close()
        raise HTTPException(400, "Masada açık adisyon var, önce hesabı kapatın")
    gecmis = conn.execute("SELECT COUNT(*) n FROM adisyonlar WHERE masa_id=?",
                          (mid,)).fetchone()["n"]
    if gecmis:
        conn.execute("UPDATE masalar SET aktif=0 WHERE id=?", (mid,))
        mesaj = "Geçmiş adisyonları olduğu için silinmedi, pasife alındı"
    else:
        conn.execute("DELETE FROM masalar WHERE id=?", (mid,))
        mesaj = "Masa silindi"
    db.kayit_log(conn, mevcut, "masa_silindi", f"id={mid}")
    conn.commit()
    conn.close()
    return {"mesaj": mesaj}
