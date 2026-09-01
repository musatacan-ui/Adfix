# ⚡ Adfix — Adisyon & Masa Yönetim Sistemi

> **"Adisyonu hallet."**

Restoran / kafe / lokanta için masa planı, adisyon, mutfak ekranı, kasa ve gün sonu
(Z raporu) içeren tek parça bir satış noktası (POS) uygulaması.

**Ad nereden geliyor?** *Ad*isyon + *fix* (hallet/kapat) — kısa, iki heceli,
akılda kalıcı.

| | |
|---|---|
| **Sürüm** | 1.2.0 |
| **Port** | 8002 (SagunMed 8000, WorkPlus 8001) |
| **Tema** | Turuncu (SagunMed mavi, WorkPlus yeşil) |
| **Backend** | FastAPI + SQLite (`adfix.db`, WAL) |
| **Frontend** | `frontend/adfix.html` (yönetim) + `frontend/menu.html` (müşteri QR menüsü) — bağımlılık yok |
| **İkonlar** | Lucide v1.34 (ISC), SVG sprite olarak gömülü — CDN yok, çevrimdışı çalışır |
| **Bağımsızlık** | SagunMed ve WorkPlus ile sıfır bağlantı (ayrı DB, ayrı JWT, ayrı port) |

---

## Yerelde deneme (en kolay yol)

### Windows

```
git fetch origin claude/adisyon-programi-tasarimi-qxc7pq
git checkout claude/adisyon-programi-tasarimi-qxc7pq
```

Sonra **`Adfix\start.bat`** dosyasına çift tıklayın. Betik sırasıyla:
Python'u kontrol eder → eksik paketleri bir kereye mahsus kurar →
güvenlik anahtarını üretip `backend\.env` içinde saklar → sunucuyu başlatır →
tarayıcıyı açar.

### Linux / macOS

```bash
./Adfix/start.sh
```

Her iki durumda da adres **http://localhost:8002**, kapatmak için pencerede `Ctrl+C`.

> **Not:** Anahtar `.env`'de saklandığı için her açılışta yenilenmez —
> yeniden başlattığınızda açık oturumlar düşmez. `.env` git'e girmez.

### Elle kurulum (betik kullanmak istemezseniz)

```bash
cd Adfix/backend
pip install -r ../requirements.txt

# JWT anahtarı ZORUNLU (en az 32 karakter) — kaynağa asla gömülmez
export ADFIX_JWT_SECRET=$(python3 -c 'import secrets;print(secrets.token_urlsafe(48))')
python3 main.py           # http://localhost:8002
```

### İlk denemede sırayla şunu yapın

1. `admin` / `adfix2026` ile girin
2. **Masalar** → boş bir masaya tıklayın → kişi sayısı → *Adisyon Aç*
3. Soldan birkaç ürün seçin → **Siparişi Gönder**
4. Sol menü → **Mutfak** — siparişin düştüğünü görün, *Hazır* deyin
5. **Masalar** → aynı masa → **Ödeme Al** → *Tam tutar* → *Tahsil Et* → *Hesabı Kapat*
6. **Raporlar** — cironun düştüğünü ve **Gün Sonu (Z Raporu)** bölümünü görün

Denemeyi bitirip temiz başlamak isterseniz `Adfix/backend/adfix.db` dosyasını
silin; uygulama açılışta örnek kurulumu yeniden yükler.

---

## Kurulum notları

İlk açılışta örnek kurulum yüklenir: 3 salon / 26 masa, 8 kategori / 29 ürün ve
üç hesap — `admin`, `kasa`, `garson` (şifre `adfix2026`).
**İlk girişten sonra Yönetim → Hesabım'dan şifreleri değiştirin.**

### Ortam değişkenleri

| Değişken | Varsayılan | Açıklama |
|---|---|---|
| `ADFIX_JWT_SECRET` | — | **Zorunlu.** 32+ karakter. Yoksa uygulama açılmaz. |
| `ADFIX_PORT` | `8002` | Dinlenecek port |
| `ADFIX_DB` | `backend/adfix.db` | Veritabanı yolu |
| `ADFIX_ILK_SIFRE` | `adfix2026` | Seed hesaplarının ilk şifresi |
| `ADFIX_CORS` | `*` | Virgülle ayrılmış izinli kaynaklar |
| `ADFIX_RELOAD` | `1` | `0` → otomatik yeniden yükleme kapalı (üretim/test) |

### Sunucuda (pm2)

```bash
pm2 start "python3 main.py" --name adfix --cwd /home/sagunmed/Adfix/backend
pm2 logs adfix | pm2 restart adfix | pm2 stop adfix
sudo ufw allow 8002/tcp
```

---

## Roller ve yetkiler

| İşlem | Garson | Kasiyer | Yönetici |
|---|:--:|:--:|:--:|
| Adisyon açma, sipariş girme | ✅ | ✅ | ✅ |
| Kendi girdiği **bekleyen** satırı iptal | ✅ | ✅ | ✅ |
| Başkasının / hazırlanmış satırını iptal | — | ✅ | ✅ |
| İkram, iskonto | — | ✅ | ✅ |
| Ödeme alma, hesabı kapatma, birleştirme | — | ✅ | ✅ |
| Menü, salon/masa, kullanıcı yönetimi | — | — | ✅ |
| Ödeme silme, adisyon iptali, **gün sonu** | — | — | ✅ |

---

## Değişmez kurallar (bunlar bozulursa kasa tutmaz)

| # | Kural | Nerede zorlanıyor |
|---|---|---|
| **HC1** | Bir masada aynı anda **en fazla 1 açık adisyon** | Veritabanı: `ux_masa_tek_acik` kısmi tekil indeks — uygulama hatası bile delemez |
| **HC2** | Para her yerde **kuruş (int)**; float yok | `database.py` şeması + `hesap.py` + arayüzde `tl()` |
| **HC3** | Adisyon tutarı **tek yerde** hesaplanır | `hesap.py::ozet()` — masa planı, fiş ve rapor hep bunu çağırır |
| **HC4** | Satır fiyatı ve adı **anlık kopyalanır** | Menüde fiyat değişse açık adisyon bozulmaz (`adisyon_satir.birim_kurus`) |
| **HC5** | **Kalan > 0 iken adisyon kapanmaz** | `adisyon.py::kapat` |
| **HC6** | **Kalandan fazla tahsilat kaydedilmez** | Para üstü kasa hareketi değildir; arayüzde gösterilir, kaydedilmez |
| **HC7** | İptal edilen satır **silinmez** | `durum='iptal'` + zorunlu sebep → kim, ne zaman, neden iptal etti izlenir |
| **HC8** | İskonto ara toplamı **aşamaz**, alınan ödemenin altına düşüremez | `adisyon.py::iskonto` + `hesap.ozet` kırpması |
| **HC9** | Bir adisyon **iki kez ciroya girmez** | `gun_sonu_id` mühürü — gün sonu sadece `gun_sonu_id IS NULL` olanları alır |
| **HC10** | Sistemde **en az bir aktif yönetici** kalır | `kullanici.py::guncelle` |
| **HC11** | Geçmişte kullanılmış ürün/kategori/masa **silinmez**, pasife alınır | `menu.py`, `masa.py` |
| **HC12** | Her para ve iptal hareketi **loglanır** | `log` tablosu → Yönetim → İşlem Kaydı |

### Kuruş bölme
Hesabı kişiye bölerken `hesap.bol_dagit()` artık kuruşları ilk kişilere dağıtır;
payların toplamı **tam olarak** hesabın tutarını verir. (100,00 ₺ / 3 kişi →
33,34 + 33,33 + 33,33 — klasik yuvarlama 1 kuruş kaybeder.)

### Gece yarısını aşan servis
Gün sonu, tarihe değil **mühre** bakar: 00:30'da kapanan masa hâlâ o günün gün
sonuna girer, çünkü henüz `gun_sonu_id` almamıştır.

---

## Ekranlar

| Ekran | İçerik |
|---|---|
| **Masalar** | Salon sekmeleri, canlı doluluk, masa başına tutar/süre/bekleyen sipariş, paket & gel-al |
| **Adisyon** | Kategori sekmeleri + ürün arama, sepet, ikram/iptal, iskonto, taşı/birleştir, hesabı böl, 80 mm fiş |
| **Ödeme** | Dokunmatik tuş takımı, 4 ödeme türü, parçalı ödeme, otomatik para üstü |
| **Mutfak** | Bekleyen siparişler, bekleme süresine göre renk (10 dk sarı, 20 dk kırmızı), "Hazır" işaretleme |
| **Adisyonlar** | Tarih aralığında kapanmış/iptal adisyonlar + detay + fiş |
| **Raporlar** | Ciro, ödeme dağılımı, en çok satanlar, kategori, personel, günlük ciro, gün sonu (Z) |
| **Menü** | Kategori ve ürün yönetimi, mutfağa düşme ayarı |
| **Yönetim** | İşletme & logo, salon & masa (toplu ekleme), **QR menü**, kullanıcılar, işlem kaydı, şifre |
| **QR Menü** (müşteri) | Telefonda açılan menü: fotoğraflar, arama, kategori, karanlık mod desteği |

---

## Logo, görseller ve QR menü

### Logo
**Yönetim → İşletme & Logo.** Yüklenen logo tarayıcıda 400 px'e küçültülür ve
veritabanında saklanır — ayrı dosya yönetimi yok, `adfix.db` yedeği logoyu da içerir.

Logo şurada görünür: giriş ekranı · sol üst köşe · **fiş çıktısı** · QR menüsü.
Aynı ekrandan işletme adı, slogan, adres, telefon ve fiş alt notu girilir;
sağdaki canlı fiş önizlemesi çıktının nasıl görüneceğini gösterir.

### Ürün fotoğrafları
**Menü → ürün → Fotoğraf Seç.** Telefonla çekilmiş 4 MB'lık bir fotoğraf tarayıcıda
500 px'e küçültülüp JPEG'e çevrilir (~30 KB) — sunucuya ham dosya gitmez.

Fotoğrafı olmayan ürünlerde **kategorinin renkli ikonu** görünür; kategori ikonu
Menü → kategori düzenle ekranından 12 seçenek arasından seçilir. Yani menü fotoğraf
yüklemeden de dolu ve düzenli görünür.

> Adfix hazır yemek fotoğrafı ile gelmez — stok fotoğraf yerine işletmenin kendi
> tabağının görünmesi hem daha doğru hem telif açısından temizdir. Ayrıntı:
> `UCUNCU-TARAF.md`

### Menü arka plan videosu (isteğe bağlı)
`menu.html` tam ekran bir arka plan videosu gösterir. Dosya **repoda yoktur**
(fotoğraflarla aynı telif ilkesi, `.gitignore`'da) — sunucuya elle yüklenir:

```
/home/sagunmed/SagunMedBeta/Adfix/frontend/bg.mp4
```

Sayfa önce `/bg.mp4`, bulamazsa `/i/<slug>/bg.mp4` adresini dener. Dosya hiç
yoksa video yerine koyu mor degrade görünür — sayfa bozulmaz. Yükleme
başarısız olursa tarayıcı konsoluna sebebi yazılır:

```
[adfix] arka plan videosu yuklenemedi: kaynak acilamadi (404 / yanlis yol / sunulmuyor) · https://…/bg.mp4
[adfix] #bg-wrap yok — menu.html guncel degil      ← dosya deploy edilmemiş
```

Önerilen dönüştürme (web için küçültülmüş, sessiz, hızlı açılan):

```bash
ffmpeg -i kaynak.mp4 -vf "scale=1280:720,fps=24" -c:v libx264 -crf 28 \
       -preset slow -an -movflags +faststart bg.mp4
```

Videonun üstünde %32–60 arası koyulaştırma katmanı var; kartlar da yarı
saydam (`--kart-cam`) olduğu için video aralardan okunur. Bembeyaz bir
videoda bile metin kontrastı korunur.

### QR menü
**Yönetim → QR Menü.** İki tür karekod üretilir:

1. **Genel karekod** → `/menu` — kapıya, vitrine, menü tutucuya
2. **Masa karekodu** → `/menu?masa=<id>` — müşteri hangi masada olduğunu görür

Karekodlar sunucuda yerel olarak üretilir (`qrcode` paketi, SVG) — dış servise
istek gitmez, internet kesikken de basılabilir. "Tümünü Yazdır" ile hepsi tek
sayfada çıkar.

**QR adresi kendiliğinden bulunur.** Sunucu açılışta kendi yerel ağ adresini tespit
edip konsola yazar:

```
Adfix hazır
  Bu bilgisayarda : http://localhost:8002
  Telefon / tablet: http://192.168.1.20:8002      <- QR menüsü bu adresi kullanmalı
```

Aynı adresler **Yönetim → QR Menü** ekranında tıklanabilir düğmeler olarak listelenir;
birine basıp kaydetmeniz yeterli — `ipconfig` çalıştırmanıza gerek yok. Adres
`localhost` kalırsa ekran kırmızı uyarı verir:

```
http://192.168.1.20:8002        ✔  müşterinin telefonu açabilir
http://localhost:8002           ✘  her cihazın "kendisi" demektir, telefonda çalışmaz
```

### Telefonda açılmıyorsa — sırayla kontrol edin

| # | Sebep | Çözüm |
|---|---|---|
| 1 | **Windows Güvenlik Duvarı** (en sık) | `Adfix\guvenlik-duvari.bat` → sağ tık → **Yönetici olarak çalıştır** |
| 2 | Telefon mobil veride | Wi-Fi'ı açın, kasayla aynı ağa bağlanın |
| 3 | Misafir Wi-Fi / cihaz yalıtımı | Modemin "Misafir ağı" cihazların birbirini görmesini engeller — ana ağa geçin |
| 4 | QR okuyucu `http://` açmıyor | Telefonun tarayıcısına adresi elle yazıp deneyin; açılıyorsa sorun okuyucudadır |

Adresi telefonda elle denemek en hızlı teşhis yöntemidir: tarayıcıya
`http://192.168.1.20:8002/menu` yazın. Açılıyorsa karekodlar da açılır.

### Müşteri tarafının güvenlik sınırı
Müşteri menüsü yalnızca `/api/acik/*` uçlarını kullanır ve bunlar **salt okunurdur**:
menü, işletme kartviziti ve masa adı. Ciro, adisyon, personel ve ayar yazma
işlemleri bu uçlardan **erişilemez** — testte ayrıca doğrulanır.

---

## API

```
POST   /api/kullanici/giris          POST   /api/adisyon/ac
GET    /api/kullanici/ben            GET    /api/adisyon/acik | /gecmis | /mutfak
POST   /api/kullanici/sifre          GET    /api/adisyon/{id}
GET    /api/kullanici/liste | /log   POST   /api/adisyon/{id}/siparis
POST   /api/kullanici/ekle           PATCH  /api/adisyon/satir/{sid}
PATCH  /api/kullanici/{id}           POST   /api/adisyon/satir/{sid}/hazir
                                     POST   /api/adisyon/{id}/tasi | /birlestir
GET    /api/menu?hepsi=0|1           PATCH  /api/adisyon/{id}/bilgi
POST   /api/menu/kategori | /urun    POST   /api/adisyon/{id}/iskonto | /odeme
PATCH  /api/menu/kategori/{id}       DELETE /api/adisyon/odeme/{oid}
PATCH  /api/menu/urun/{id}           GET    /api/adisyon/{id}/bol?kisi=N
DELETE /api/menu/kategori|urun/{id}  POST   /api/adisyon/{id}/kapat | /iptal

GET    /api/masa/plan | /salonlar    GET    /api/rapor/ozet?bas=&bit=
POST   /api/masa/salon | /masa       GET    /api/rapor/gun-sonu/onizleme | /liste | /{id}
PATCH  /api/masa/salon|masa/{id}     POST   /api/rapor/gun-sonu
DELETE /api/masa/masa/{id}           GET    /saglik

GET    /api/ayar                     PATCH  /api/ayar          (yönetici)

── kimlik doğrulaması YOK, salt okunur (müşteri QR menüsü) ──
GET    /api/acik/menu                GET    /api/acik/isletme
GET    /api/acik/masa/{id}           GET    /api/acik/qr?veri=<metin>   → SVG
```

Etkileşimli dokümantasyon: `http://localhost:8002/docs`

---

## Test protokolü — değişiklik yaptıktan sonra DAİMA çalıştır

```bash
cd Adfix/backend
export ADFIX_JWT_SECRET=$(python3 -c 'import secrets;print(secrets.token_urlsafe(48))')
python3 test_adfix.py        # 69 uçtan uca iş kuralı testi, geçici DB kullanır
```

Test şunları doğrular: yetki sınırları, masa tekliği (HC1), fiyat değişikliğinin
açık adisyonu bozmaması, ikram/iptal muhasebesi, iskonto sınırları, fazla
tahsilat engeli, kuruş kaybetmeyen bölme, taşıma/birleştirme, paket adisyon,
gün sonu mührü ve çift sayım engeli, rapor toplamları, logo/görsel boyut ve
biçim doğrulaması, QR üretimi ve **müşteri uçlarından ciro sızmadığı**.

Arayüz değişikliğinden sonra ek olarak: giriş → masa aç → sipariş → mutfak →
ödeme → kapat → rapor akışını tarayıcıda bir kez elle geçin.

---

## Veri modeli

```
kullanicilar ─┐
salonlar ──── masalar ──┐
kategoriler ── urunler ─┼─ adisyonlar ─┬─ adisyon_satir
   (ikon)      (gorsel) │              ├─ odemeler
                        │              └─ gun_sonu (mühür)
                        ├─ ayarlar (isletme_adi, logo, adres, qr_taban_url…)
                        └─ log
```

`urunler.gorsel` ve `kategoriler.ikon` sütunları v1.1'de eklendi; `init_db()`
içindeki `_gocler()` mevcut veritabanlarına bunları otomatik ekler — eski bir
`adfix.db` ile açtığınızda veri kaybı olmaz.

Yedekleme: `adfix.db` WAL modunda. Yedek alırken üç dosyayı birlikte kopyalayın
(`adfix.db`, `adfix.db-wal`, `adfix.db-shm`) ya da
`sqlite3 adfix.db ".backup yedek.db"` kullanın.
