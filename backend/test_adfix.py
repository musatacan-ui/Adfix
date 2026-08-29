"""Adfix uçtan uca iş kuralı testi — gerçek HTTP katmanı üzerinden."""
import os, sys, tempfile

TMP = tempfile.mkdtemp()
os.environ["ADFIX_DB"] = os.path.join(TMP, "test.db")
os.environ["ADFIX_JWT_SECRET"] = "test-" + "x" * 40
os.environ["ADFIX_ILK_SIFRE"] = "adfix2026"
sys.path.insert(0, "/home/user/SagunMed/Adfix/backend")

from fastapi.testclient import TestClient
import main

ok, hata = 0, []
def kontrol(ad, sart, ek=""):
    global ok
    if sart: ok += 1; print(f"  ✓ {ad}")
    else: hata.append(f"{ad} {ek}"); print(f"  ✗ {ad}  {ek}")

with TestClient(main.app) as c:
    def giris(k):
        r = c.post("/api/kullanici/giris", json={"kullanici_adi": k, "sifre": "adfix2026"})
        assert r.status_code == 200, r.text
        return {"Authorization": "Bearer " + r.json()["token"]}

    print("\n[1] Kimlik ve yetki")
    admin, kasa, garson = giris("admin"), giris("kasa"), giris("garson")
    kontrol("hatalı şifre reddedildi",
            c.post("/api/kullanici/giris",
                   json={"kullanici_adi": "admin", "sifre": "yanlis"}).status_code == 401)
    kontrol("tokensiz istek 403",
            c.get("/api/masa/plan").status_code in (401, 403))

    print("\n[2] Menü")
    menu = c.get("/api/menu", headers=garson).json()
    kontrol("menü kategorili geldi", len(menu) == 8, f"kategori={len(menu)}")
    urun = {u["ad"]: u for k in menu for u in k["urunler"]}
    kontrol("ürünler yüklü", len(urun) == 29, f"urun={len(urun)}")
    adana, cay, kunefe = urun["Adana Kebap"], urun["Çay"], urun["Künefe"]
    kontrol("çay mutfağa düşmez", cay["mutfak"] == 0)

    print("\n[3] Adisyon açma / masa tekliği")
    plan = c.get("/api/masa/plan", headers=garson).json()
    m1 = plan["salonlar"][0]["masalar"][0]
    a = c.post("/api/adisyon/ac", headers=garson,
               json={"tip": "masa", "masa_id": m1["id"], "kisi": 4}).json()
    kontrol("adisyon açıldı", a["durum"] == "acik" and a["kod"] == "001", a.get("kod"))
    r2 = c.post("/api/adisyon/ac", headers=garson,
                json={"tip": "masa", "masa_id": m1["id"], "kisi": 2})
    kontrol("aynı masaya 2. adisyon engellendi (HC1)", r2.status_code == 400, r2.text[:90])
    aid = a["id"]

    print("\n[4] Sipariş")
    d = c.post(f"/api/adisyon/{aid}/siparis", headers=garson, json={"satirlar": [
        {"urun_id": adana["id"], "adet": 2, "notu": "acılı"},
        {"urun_id": cay["id"],   "adet": 4},
        {"urun_id": kunefe["id"],"adet": 1},
    ]}).json()
    beklenen = 2*32000 + 4*2000 + 14500
    kontrol("ara toplam doğru", d["ozet"]["ara_toplam"] == beklenen,
            f"{d['ozet']['ara_toplam']} != {beklenen}")
    kontrol("mutfak kuyruğu sadece mutfak ürünleri",
            len(c.get("/api/adisyon/mutfak", headers=garson).json()) == 2)

    print("\n[5] Fiyat değişikliği açık adisyonu bozmuyor")
    c.patch(f"/api/menu/urun/{adana['id']}", headers=admin, json={
        "kategori_id": adana["kategori_id"], "ad": "Adana Kebap",
        "fiyat_kurus": 99000, "mutfak": 1, "sira": 0, "aktif": 1})
    d = c.get(f"/api/adisyon/{aid}", headers=garson).json()
    kontrol("açık adisyon eski fiyatı koruyor", d["ozet"]["ara_toplam"] == beklenen,
            str(d["ozet"]["ara_toplam"]))

    print("\n[6] İkram / iptal yetkileri")
    cay_satir = [s for s in d["satirlar"] if s["ad"] == "Çay"][0]
    kunefe_satir = [s for s in d["satirlar"] if s["ad"] == "Künefe"][0]
    r = c.patch(f"/api/adisyon/satir/{cay_satir['id']}", headers=garson,
                json={"durum": "ikram"})
    kontrol("garson ikram yapamaz", r.status_code == 403, r.text[:70])
    d = c.patch(f"/api/adisyon/satir/{cay_satir['id']}", headers=kasa,
                json={"durum": "ikram"}).json()
    kontrol("kasiyer ikram yaptı, tutardan düştü",
            d["ozet"]["ara_toplam"] == beklenen - 8000 and d["ozet"]["ikram"] == 8000,
            str(d["ozet"]))
    r = c.patch(f"/api/adisyon/satir/{kunefe_satir['id']}", headers=kasa,
                json={"durum": "iptal"})
    kontrol("sebepsiz iptal reddedildi", r.status_code == 400, r.text[:70])
    d = c.patch(f"/api/adisyon/satir/{kunefe_satir['id']}", headers=kasa,
                json={"durum": "iptal", "sebep": "müşteri vazgeçti"}).json()
    kontrol("iptal tutardan düştü", d["ozet"]["ara_toplam"] == 64000,
            str(d["ozet"]["ara_toplam"]))

    print("\n[7] İskonto")
    r = c.post(f"/api/adisyon/{aid}/iskonto", headers=garson,
               json={"tip": "yuzde", "deger": 10})
    kontrol("garson iskonto yapamaz", r.status_code == 403)
    d = c.post(f"/api/adisyon/{aid}/iskonto", headers=kasa,
               json={"tip": "yuzde", "deger": 10}).json()
    kontrol("%10 iskonto = 6400 kr", d["ozet"]["iskonto"] == 6400, str(d["ozet"]))
    kontrol("net toplam 57600", d["ozet"]["net_toplam"] == 57600, str(d["ozet"]))
    r = c.post(f"/api/adisyon/{aid}/iskonto", headers=kasa,
               json={"tip": "tutar", "deger": 999999})
    kontrol("aşırı iskonto engellendi", r.status_code == 400)
    c.post(f"/api/adisyon/{aid}/iskonto", headers=kasa, json={"tip": "yuzde", "deger": 10})

    print("\n[8] Ödeme")
    r = c.post(f"/api/adisyon/{aid}/kapat", headers=kasa)
    kontrol("ödenmemiş adisyon kapanmıyor", r.status_code == 400, r.text[:70])
    d = c.post(f"/api/adisyon/{aid}/odeme", headers=kasa,
               json={"tur": "nakit", "tutar_kurus": 20000}).json()
    kontrol("kısmi ödeme kaydedildi", d["ozet"]["kalan"] == 37600, str(d["ozet"]))
    r = c.post(f"/api/adisyon/{aid}/odeme", headers=kasa,
               json={"tur": "kart", "tutar_kurus": 50000})
    kontrol("fazla tahsilat engellendi", r.status_code == 400, r.text[:70])
    d = c.post(f"/api/adisyon/{aid}/odeme", headers=kasa,
               json={"tur": "kart", "tutar_kurus": 37600}).json()
    kontrol("hesap kapandı (kalan 0)", d["ozet"]["kalan"] == 0)

    print("\n[9] Hesap bölme (kuruş kaybı yok)")
    b = c.get(f"/api/adisyon/{aid}/bol?kisi=7", headers=kasa).json()
    kontrol("7'ye bölüm tam tutuyor",
            b["kontrol_toplam"] == b["net_toplam"] == 57600, str(b))

    print("\n[10] Kapatma")
    d = c.post(f"/api/adisyon/{aid}/kapat", headers=kasa).json()
    kontrol("adisyon kapandı", d["durum"] == "kapali")
    plan = c.get("/api/masa/plan", headers=garson).json()
    kontrol("masa boşaldı", plan["salonlar"][0]["masalar"][0]["adisyon"] is None)
    r = c.post(f"/api/adisyon/{aid}/siparis", headers=garson,
               json={"satirlar": [{"urun_id": cay["id"], "adet": 1}]})
    kontrol("kapalı adisyona sipariş eklenemiyor", r.status_code == 400, r.text[:70])

    print("\n[11] Taşıma ve birleştirme")
    m2, m3 = plan["salonlar"][0]["masalar"][1], plan["salonlar"][0]["masalar"][2]
    a2 = c.post("/api/adisyon/ac", headers=garson,
                json={"tip": "masa", "masa_id": m2["id"], "kisi": 2}).json()
    c.post(f"/api/adisyon/{a2['id']}/siparis", headers=garson,
           json={"satirlar": [{"urun_id": cay["id"], "adet": 2}]})
    a3 = c.post("/api/adisyon/ac", headers=garson,
                json={"tip": "masa", "masa_id": m3["id"], "kisi": 3}).json()
    c.post(f"/api/adisyon/{a3['id']}/siparis", headers=garson,
           json={"satirlar": [{"urun_id": kunefe["id"], "adet": 2}]})
    r = c.post(f"/api/adisyon/{a2['id']}/tasi", headers=garson,
               json={"hedef_masa_id": m3["id"]})
    kontrol("dolu masaya taşıma engellendi", r.status_code == 400, r.text[:70])
    d = c.post(f"/api/adisyon/{a3['id']}/birlestir", headers=kasa,
               json={"kaynak_adisyon_id": a2["id"]}).json()
    kontrol("birleşme tutarı doğru", d["ozet"]["ara_toplam"] == 2*2000 + 2*14500,
            str(d["ozet"]["ara_toplam"]))
    kontrol("kişi sayısı toplandı", d["kisi"] == 5, str(d["kisi"]))
    plan = c.get("/api/masa/plan", headers=garson).json()
    kontrol("kaynak masa boşaldı", plan["salonlar"][0]["masalar"][1]["adisyon"] is None)
    d = c.post(f"/api/adisyon/{a3['id']}/tasi", headers=garson,
               json={"hedef_masa_id": m2["id"]}).json()
    kontrol("boş masaya taşındı", d["masa_ad"] == m2["ad"], d.get("masa_ad"))

    print("\n[12] Paket adisyon")
    p = c.post("/api/adisyon/ac", headers=garson, json={
        "tip": "paket", "musteri_ad": "Ayşe Y.", "musteri_tel": "0555",
        "musteri_adres": "Atatürk Cad. 5"}).json()
    kontrol("paket adisyon masasız açıldı", p["masa_id"] is None and p["tip"] == "paket")
    kontrol("paket masa planında listeleniyor",
            len(c.get("/api/masa/plan", headers=garson).json()["paket"]) == 1)

    print("\n[13] Gün sonu")
    on = c.get("/api/rapor/gun-sonu/onizleme", headers=admin).json()
    kontrol("önizleme 1 kapalı adisyon gösteriyor", on["adisyon_sayisi"] == 1, str(on["adisyon_sayisi"]))
    kontrol("önizleme net = 57600", on["net_kurus"] == 57600, str(on["net_kurus"]))
    kontrol("açık adisyonlar uyarısı var", len(on["acik_adisyonlar"]) == 2,
            str(len(on["acik_adisyonlar"])))
    r = c.post("/api/rapor/gun-sonu", headers=admin, json={"zorla": 0})
    kontrol("açık adisyon varken gün sonu bloke", r.status_code == 400, r.text[:80])
    r = c.post("/api/rapor/gun-sonu", headers=kasa, json={"zorla": 1})
    kontrol("kasiyer gün sonu alamaz", r.status_code == 403)
    g = c.post("/api/rapor/gun-sonu", headers=admin, json={"zorla": 1}).json()
    kontrol("gün sonu alındı", g["net_kurus"] == 57600 and g["adisyon_sayisi"] == 1, str(g))
    kontrol("nakit+kart = net", g["nakit_kurus"] + g["kart_kurus"] == g["net_kurus"], str(g))
    r = c.post("/api/rapor/gun-sonu", headers=admin, json={"zorla": 1})
    kontrol("aynı adisyon 2. kez ciroya girmiyor", r.status_code == 400, r.text[:80])

    print("\n[14] Rapor")
    rp = c.get("/api/rapor/ozet", headers=admin).json()
    kontrol("rapor net = 57600", rp["net_kurus"] == 57600, str(rp["net_kurus"]))
    kontrol("ikram raporda", rp["ikram_kurus"] == 8000, str(rp["ikram_kurus"]))
    kontrol("ödeme kırılımı", rp["odeme"]["nakit"] == 20000 and rp["odeme"]["kart"] == 37600,
            str(rp["odeme"]))
    kontrol("en çok satan ürün listesi dolu", len(rp["urunler"]) >= 1)


    print("\n[16] İşletme ayarları ve logo")
    ayar = c.get("/api/ayar", headers=admin).json()
    kontrol("varsayılan ayarlar geldi — işletme adı boş, kullanıcı kendisi girer",
            ayar["isletme_adi"] == "" and ayar["logo"] == "")
    r = c.patch("/api/ayar", headers=garson, json={"isletme_adi": "Korsan"})
    kontrol("garson ayar değiştiremez", r.status_code == 403)
    LOGO = ("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
            "AAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
    y = c.patch("/api/ayar", headers=admin, json={
        "isletme_adi": "Sofra Restoran", "slogan": "Ev yemeği",
        "adres": "Atatürk Cad. 12", "telefon": "0324 000 00 00", "logo": LOGO}).json()
    kontrol("logo ve işletme bilgileri kaydedildi",
            y["logo"] == LOGO and y["isletme_adi"] == "Sofra Restoran", y["isletme_adi"])
    r = c.patch("/api/ayar", headers=admin, json={"logo": "javascript:alert(1)"})
    kontrol("logo olmayan içerik reddedildi", r.status_code == 400, r.text[:70])
    r = c.patch("/api/ayar", headers=admin, json={"logo": "data:image/png;base64," + "A" * 700_000})
    kontrol("aşırı büyük logo reddedildi", r.status_code == 400, r.text[:70])
    r = c.patch("/api/ayar", headers=admin, json={"qr_taban_url": "192.168.1.20:8002"})
    kontrol("şemasız QR adresi reddedildi", r.status_code == 400, r.text[:70])
    y = c.patch("/api/ayar", headers=admin,
                json={"qr_taban_url": "http://192.168.1.20:8002/"}).json()
    kontrol("QR adresi normalize edildi (sondaki / atıldı)",
            y["qr_taban_url"] == "http://192.168.1.20:8002", y["qr_taban_url"])

    print("\n[17] Ürün görseli ve kategori ikonu")
    FOTO = "data:image/jpeg;base64," + "A" * 400
    c.patch(f"/api/menu/urun/{kunefe['id']}", headers=admin, json={
        "kategori_id": kunefe["kategori_id"], "ad": "Künefe", "fiyat_kurus": 14500,
        "gorsel": FOTO, "mutfak": 1, "sira": 0, "aktif": 1})
    menu2 = c.get("/api/menu", headers=garson).json()
    kunefe2 = [u for k in menu2 for u in k["urunler"] if u["ad"] == "Künefe"][0]
    kontrol("ürün görseli kaydedildi", kunefe2["gorsel"] == FOTO)
    r = c.patch(f"/api/menu/urun/{kunefe['id']}", headers=admin, json={
        "kategori_id": kunefe["kategori_id"], "ad": "Künefe", "fiyat_kurus": 14500,
        "gorsel": "http://kotu.example/x.png", "mutfak": 1, "sira": 0, "aktif": 1})
    kontrol("dış bağlantılı görsel reddedildi", r.status_code == 400, r.text[:70])
    r = c.patch(f"/api/menu/urun/{kunefe['id']}", headers=admin, json={
        "kategori_id": kunefe["kategori_id"], "ad": "Künefe", "fiyat_kurus": 14500,
        "gorsel": "data:image/jpeg;base64," + "A" * 500_000, "mutfak": 1, "sira": 0, "aktif": 1})
    kontrol("aşırı büyük ürün görseli reddedildi", r.status_code == 400, r.text[:70])
    kontrol("kategori ikonları seed'de atanmış",
            {k["ad"]: k["ikon"] for k in menu2}["Çorbalar"] == "soup")

    print("\n[18] QR menü — kimlik doğrulaması olmayan müşteri uçları")
    am = c.get("/api/acik/menu").json()          # başlıksız = kimliksiz istek
    kontrol("açık menü tokensiz erişilebiliyor", "kategoriler" in am)
    kontrol("işletme kartviziti geliyor",
            am["isletme"]["ad"] == "Sofra Restoran" and am["isletme"]["logo"] == LOGO)
    acik_urunler = {u["ad"]: u for k in am["kategoriler"] for u in k["urunler"]}
    kontrol("ürün görseli müşteriye geliyor", acik_urunler["Künefe"]["gorsel"] == FOTO)
    kontrol("açık menüde ciro/adisyon SIZMIYOR",
            not any(x in str(am) for x in ("adisyon", "ciro", "odenen", "kasa")), "sızıntı!")
    c.patch(f"/api/menu/urun/{cay['id']}", headers=admin, json={
        "kategori_id": cay["kategori_id"], "ad": "Çay", "fiyat_kurus": 2000,
        "mutfak": 0, "sira": 0, "aktif": 0})
    am2 = c.get("/api/acik/menu").json()
    kontrol("pasif ürün müşteri menüsünde görünmüyor",
            "Çay" not in {u["ad"] for k in am2["kategoriler"] for u in k["urunler"]})
    ai = c.get("/api/acik/isletme").json()
    kontrol("açık işletme ucu çalışıyor", ai["ad"] == "Sofra Restoran")
    m1_ad = c.get(f"/api/acik/masa/{m1['id']}").json()
    kontrol("QR masa adı çözülüyor", m1_ad["ad"] == m1["ad"], str(m1_ad))
    kontrol("olmayan masa 404", c.get("/api/acik/masa/99999").status_code == 404)

    print("\n[19] QR üretimi")
    q = c.get("/api/acik/qr?veri=http://192.168.1.20:8002/menu")
    kontrol("QR SVG üretildi", q.status_code == 200
            and q.headers["content-type"].startswith("image/svg+xml")
            and b"<svg" in q.content, str(q.status_code))
    kontrol("QR içeriği makul boyutta", 500 < len(q.content) < 60000, str(len(q.content)))
    kontrol("boş QR verisi reddedildi", c.get("/api/acik/qr?veri=").status_code == 400)
    kontrol("aşırı uzun QR verisi reddedildi",
            c.get("/api/acik/qr?veri=" + "x" * 950).status_code == 400)

    print("\n[20] Ağ tespiti (QR adresinin kendiliğinden bulunması)")
    r = c.get("/api/ayar/ag", headers=garson)
    kontrol("garson ağ bilgisini göremez", r.status_code == 403)
    agb = c.get("/api/ayar/ag", headers=admin).json()
    kontrol("port bildiriliyor", agb["port"] == 8002, str(agb["port"]))
    kontrol("adres listesi ve adaylar tutarlı",
            len(agb["adaylar"]) == len(agb["adresler"]), str(agb))
    kontrol("loopback aday olarak sunulmuyor",
            not any(a.startswith("127.") for a in agb["adresler"]), str(agb["adresler"]))
    if agb["adresler"]:
        kontrol("öneri http:// ile başlıyor ve port içeriyor",
                agb["onerilen"].startswith("http://") and ":8002" in agb["onerilen"],
                agb["onerilen"])
        kontrol("adaylar tam URL biçiminde",
                all(a.startswith("http://") and a.endswith(":8002") for a in agb["adaylar"]),
                str(agb["adaylar"]))
    import ag as _ag
    kontrol("özel ağ blokları doğru tanınıyor",
            _ag._ozel_mi("192.168.1.20") and _ag._ozel_mi("10.0.0.5")
            and _ag._ozel_mi("172.16.0.1") and not _ag._ozel_mi("172.32.0.1")
            and not _ag._ozel_mi("8.8.8.8"))


    print("\n[21] QR ile müşteri siparişi (masa QR)")
    # Diğer test bölümleri M1-M3'ü kirletti; QR akışı için bakir bir masa lazım
    plan = c.get("/api/masa/plan", headers=admin).json()
    qr_masa = next(m for s in plan["salonlar"] for m in s["masalar"] if not m["adisyon"])

    # Müşteri karekodu okuyup çorba, çay ve ayran seçti (Çay v1'de pasife alındı;
    # açık menüden çekelim ki test durumu sızmasın)
    acik = c.get("/api/acik/menu").json()
    urun_acik = {u["ad"]: u for k in acik["kategoriler"] for u in k["urunler"]}
    corba_id = urun_acik["Mercimek Çorbası"]["id"]
    ayran_id = urun_acik["Ayran"]["id"]
    kebap_id = urun_acik["Adana Kebap"]["id"]

    r = c.post(f"/api/acik/masa/{qr_masa['id']}/siparis", json={"satirlar": [
        {"urun_id": corba_id, "adet": 2, "notu": "az tuz"},
        {"urun_id": ayran_id, "adet": 2},
    ]})
    kontrol("QR ile sipariş kabul edildi", r.status_code == 200, r.text[:100])
    y = r.json()
    kontrol("yeni adisyon otomatik açıldı", y.get("yeni_adisyon") is True, str(y)[:100])
    kontrol("adisyon numarası döndü", y["kod"].isdigit() and len(y["kod"]) == 3, y.get("kod"))
    kontrol("toplam doğru hesaplandı", y["toplam"] == 2*8500 + 2*3500, y.get("toplam"))

    # Aynı masaya ikinci sipariş — mevcut adisyona eklenmeli
    r = c.post(f"/api/acik/masa/{qr_masa['id']}/siparis", json={"satirlar": [
        {"urun_id": kebap_id, "adet": 1}]})
    y2 = r.json()
    kontrol("aynı masaya 2. sipariş mevcut adisyona eklendi", y2["yeni_adisyon"] is False)
    kontrol("adisyon numarası aynı", y2["kod"] == y["kod"], f"{y2['kod']} != {y['kod']}")
    # Adana Kebap fiyatı Test 5'te 99000 kuruşa çekildi
    kontrol("toplam güncellendi", y2["toplam"] == 2*8500 + 2*3500 + 99000,
            f"{y2['toplam']} beklenen {2*8500 + 2*3500 + 99000}")

    # Yönetim tarafından adisyona bakılırsa müşteri satırları görünmeli
    detay = c.get(f"/api/adisyon/{y['adisyon_id']}", headers=admin).json()
    kontrol("yönetim ekranında adisyon açık ve satırlar var",
            detay["durum"] == "acik" and len(detay["satirlar"]) == 3)
    kontrol("müşteri satırları ekleyen_id boş (Müşteri işareti)",
            all(s["ekleyen_id"] is None for s in detay["satirlar"]),
            str([s["ekleyen_id"] for s in detay["satirlar"]]))

    # Mutfak ekranında müşteri siparişleri görünmeli (mutfak=1 ürünler için)
    mutfak = c.get("/api/adisyon/mutfak", headers=admin).json()
    kontrol("müşteri siparişleri mutfağa düştü",
            len([x for x in mutfak if x["adisyon_id"] == y["adisyon_id"]]) >= 2,
            f"{len(mutfak)} kalem")

    # Müşteri kendi durumunu görebilir (ödeme/personel görmeden)
    d = c.get(f"/api/acik/masa/{qr_masa['id']}/durum").json()
    kontrol("müşteri kendi masasının durumunu görüyor", d["adisyon_id"] == y["adisyon_id"])
    kontrol("durum ekranı ciro/personel sızdırmıyor",
            not any(k in str(d) for k in ("odenen", "ikram_kurus", "iskonto", "kapatan",
                                          "acan_id", "ekleyen_id", "kasiyer")),
            "sızıntı!")

    print("\n[22] QR sipariş güvenlik sınırları")
    r = c.post(f"/api/acik/masa/{qr_masa['id']}/siparis", json={"satirlar": []})
    kontrol("boş sepet reddedildi", r.status_code == 400, r.text[:80])

    r = c.post("/api/acik/masa/99999/siparis", json={"satirlar":
        [{"urun_id": ayran_id, "adet": 1}]})
    kontrol("olmayan masa reddedildi", r.status_code == 404)

    bakir2 = next(m for s in plan["salonlar"] for m in s["masalar"]
                  if not m["adisyon"] and m["id"] != qr_masa["id"])
    # Adet üst sınırı: SATIR_UST_SINIR aşımı 400
    r = c.post(f"/api/acik/masa/{bakir2['id']}/siparis",
               json={"satirlar": [{"urun_id": ayran_id, "adet": 1}] * 31})
    kontrol("aşırı satır sayısı reddedildi", r.status_code == 400, r.text[:80])

    # Aşırı adet sessizce atlanır — hepsi atlanırsa "menüde yok" hatası
    r = c.post(f"/api/acik/masa/{bakir2['id']}/siparis", json={"satirlar":
        [{"urun_id": ayran_id, "adet": 9999}]})
    kontrol("aşırı adet reddedildi (sepet boş kaldı)", r.status_code == 400, r.text[:80])

    # Pasif ürün sessizce atlanır (Çay Test 5'te pasife alınmıştı)
    r = c.post(f"/api/acik/masa/{bakir2['id']}/siparis", json={"satirlar":
        [{"urun_id": cay["id"], "adet": 1}]})
    kontrol("pasif ürün sessizce atlandı", r.status_code == 400)

    # Yönetici QR siparişi kapattı — artık kabul edilmemeli
    c.patch("/api/ayar", headers=admin, json={"qr_siparis_acik": "0"})
    r = c.post(f"/api/acik/masa/{bakir2['id']}/siparis", json={"satirlar":
        [{"urun_id": kebap_id, "adet": 1}]})
    kontrol("QR sipariş kapalıyken 403", r.status_code == 403, r.text[:80])
    kontrol("kullanıcıya anlamlı mesaj", "sipariş almıyor" in r.text or "garson" in r.text, r.text[:80])
    c.patch("/api/ayar", headers=admin, json={"qr_siparis_acik": "1"})

    # Açık menüde siparis_acik bayrağı görünüyor mu
    m = c.get("/api/acik/menu").json()
    kontrol("açık menüde siparis_acik bayrağı var", "siparis_acik" in m and m["siparis_acik"] is True)

    print("\n[23] Son yönetici koruması")

    r = c.patch("/api/kullanici/1", headers=admin, json={
        "ad_soyad": "Sistem Yöneticisi", "kullanici_adi": "admin",
        "rol": "garson", "aktif": 1})
    kontrol("son yönetici rolü düşürülemiyor", r.status_code == 400, r.text[:70])

print(f"\n{'='*54}\n{ok} test geçti, {len(hata)} hata")
for h in hata: print("  ! " + h)
sys.exit(1 if hata else 0)
