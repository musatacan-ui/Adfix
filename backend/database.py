"""
Adfix — Adisyon & Masa Yönetim Sistemi
Veritabanı: tablolar, indeksler, migration ve seed verisi.

PARA BİRİMİ KURALI (KRİTİK):
  Tüm parasal değerler veritabanında ve API'de KURUŞ (int) tutulur.
  12,50 TL  ->  1250
  Float kullanılmaz: 0.1+0.2 hatası bir kasa programında gün sonu tutmaz.
  TL'ye çevirme sadece arayüzde (adfix.html -> tl()) yapılır.
"""
import sqlite3, os

DB_PATH = os.environ.get(
    "ADFIX_DB",
    os.path.join(os.path.dirname(__file__), "adfix.db")
)

ROLLER = ("garson", "kasiyer", "yonetici")


def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=60, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 60000")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS kullanicilar (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        ad_soyad      TEXT NOT NULL,
        kullanici_adi TEXT UNIQUE NOT NULL,
        sifre_hash    TEXT NOT NULL,
        rol           TEXT NOT NULL CHECK(rol IN ('garson','kasiyer','yonetici')),
        aktif         INTEGER DEFAULT 1,
        olusturma     TEXT DEFAULT (datetime('now','localtime'))
    );

    CREATE TABLE IF NOT EXISTS salonlar (
        id     INTEGER PRIMARY KEY AUTOINCREMENT,
        ad     TEXT NOT NULL,
        sira   INTEGER DEFAULT 0,
        aktif  INTEGER DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS masalar (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        salon_id  INTEGER NOT NULL REFERENCES salonlar(id),
        ad        TEXT NOT NULL,
        kapasite  INTEGER DEFAULT 4,
        sira      INTEGER DEFAULT 0,
        aktif     INTEGER DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS kategoriler (
        id    INTEGER PRIMARY KEY AUTOINCREMENT,
        ad    TEXT NOT NULL,
        renk  TEXT DEFAULT '#F97316',
        ikon  TEXT DEFAULT 'utensils',   -- lucide ikon adı (görseli olmayan ürünlerde kullanılır)
        sira  INTEGER DEFAULT 0,
        aktif INTEGER DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS urunler (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        kategori_id  INTEGER NOT NULL REFERENCES kategoriler(id),
        ad           TEXT NOT NULL,
        fiyat_kurus  INTEGER NOT NULL CHECK(fiyat_kurus >= 0),
        aciklama     TEXT DEFAULT '',
        gorsel       TEXT DEFAULT '',     -- data URI (yüklenen fotoğraf) ya da dosya yolu; boşsa kategori ikonu
        mutfak       INTEGER DEFAULT 1,   -- 1: mutfak ekranına düşer, 0: (içecek vb.) düşmez
        sira         INTEGER DEFAULT 0,
        aktif        INTEGER DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS adisyonlar (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        kod            TEXT NOT NULL,
        tip            TEXT NOT NULL CHECK(tip IN ('masa','paket','gel_al')),
        masa_id        INTEGER REFERENCES masalar(id),
        kisi           INTEGER DEFAULT 1,
        durum          TEXT NOT NULL DEFAULT 'acik' CHECK(durum IN ('acik','kapali','iptal')),
        iskonto_kurus  INTEGER DEFAULT 0 CHECK(iskonto_kurus >= 0),
        iskonto_not    TEXT DEFAULT '',
        aciklama       TEXT DEFAULT '',
        musteri_ad     TEXT DEFAULT '',
        musteri_tel    TEXT DEFAULT '',
        musteri_adres  TEXT DEFAULT '',
        acan_id        INTEGER REFERENCES kullanicilar(id),
        acilis         TEXT DEFAULT (datetime('now','localtime')),
        kapatan_id     INTEGER REFERENCES kullanicilar(id),
        kapanis        TEXT,
        iptal_sebep    TEXT DEFAULT '',
        gun_sonu_id    INTEGER REFERENCES gun_sonu(id)
    );

    CREATE TABLE IF NOT EXISTS adisyon_satir (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        adisyon_id   INTEGER NOT NULL REFERENCES adisyonlar(id) ON DELETE CASCADE,
        urun_id      INTEGER REFERENCES urunler(id),
        ad           TEXT NOT NULL,              -- ürün adı anlık kopyalanır (fiyat/ad değişse de fiş bozulmaz)
        birim_kurus  INTEGER NOT NULL CHECK(birim_kurus >= 0),
        adet         INTEGER NOT NULL CHECK(adet > 0),
        notu         TEXT DEFAULT '',
        durum        TEXT NOT NULL DEFAULT 'bekliyor'
                     CHECK(durum IN ('bekliyor','hazir','ikram','iptal')),
        mutfak       INTEGER DEFAULT 1,
        ekleyen_id   INTEGER REFERENCES kullanicilar(id),
        eklenme      TEXT DEFAULT (datetime('now','localtime')),
        iptal_sebep  TEXT DEFAULT ''
    );

    CREATE TABLE IF NOT EXISTS odemeler (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        adisyon_id   INTEGER NOT NULL REFERENCES adisyonlar(id) ON DELETE CASCADE,
        tur          TEXT NOT NULL CHECK(tur IN ('nakit','kart','yemek_ceki','acik_hesap')),
        tutar_kurus  INTEGER NOT NULL CHECK(tutar_kurus > 0),
        alan_id      INTEGER REFERENCES kullanicilar(id),
        zaman        TEXT DEFAULT (datetime('now','localtime'))
    );

    CREATE TABLE IF NOT EXISTS gun_sonu (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        tarih           TEXT NOT NULL,
        kapanis         TEXT DEFAULT (datetime('now','localtime')),
        adisyon_sayisi  INTEGER DEFAULT 0,
        brut_kurus      INTEGER DEFAULT 0,
        iskonto_kurus   INTEGER DEFAULT 0,
        ikram_kurus     INTEGER DEFAULT 0,
        net_kurus       INTEGER DEFAULT 0,
        nakit_kurus     INTEGER DEFAULT 0,
        kart_kurus      INTEGER DEFAULT 0,
        ceki_kurus      INTEGER DEFAULT 0,
        acik_kurus      INTEGER DEFAULT 0,
        kapatan_id      INTEGER REFERENCES kullanicilar(id)
    );

    CREATE TABLE IF NOT EXISTS ayarlar (
        anahtar TEXT PRIMARY KEY,
        deger   TEXT DEFAULT ''
    );

    CREATE TABLE IF NOT EXISTS log (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        kullanici_id  INTEGER,
        kullanici_ad  TEXT DEFAULT '',
        islem         TEXT NOT NULL,
        detay         TEXT DEFAULT '',
        zaman         TEXT DEFAULT (datetime('now','localtime'))
    );

    -- HC1: Bir masada aynı anda EN FAZLA 1 açık adisyon olabilir.
    -- Kısmi tekil indeks — veritabanı seviyesinde garanti, uygulama hatası bile bunu delemez.
    CREATE UNIQUE INDEX IF NOT EXISTS ux_masa_tek_acik
        ON adisyonlar(masa_id) WHERE durum='acik' AND masa_id IS NOT NULL;

    -- Günlük adisyon numarası (001, 002, ...) gün içinde tekrar edemez.
    CREATE UNIQUE INDEX IF NOT EXISTS ux_gunluk_kod
        ON adisyonlar(date(acilis), kod);

    CREATE INDEX IF NOT EXISTS ix_satir_adisyon ON adisyon_satir(adisyon_id);
    CREATE INDEX IF NOT EXISTS ix_odeme_adisyon ON odemeler(adisyon_id);
    CREATE INDEX IF NOT EXISTS ix_adisyon_durum ON adisyonlar(durum);
    CREATE INDEX IF NOT EXISTS ix_adisyon_kapanis ON adisyonlar(kapanis);
    CREATE INDEX IF NOT EXISTS ix_urun_kategori ON urunler(kategori_id);
    """)
    conn.commit()
    _gocler(conn)
    conn.close()


def _gocler(conn):
    """Mevcut veritabanlarına sonradan eklenen sütunları güvenle ekler.
    Yeni kurulumda hiçbir şey yapmaz; veri kaybı riski yoktur."""
    yeni = [
        ("urunler",     "gorsel", "TEXT DEFAULT ''"),
        ("kategoriler", "ikon",   "TEXT DEFAULT 'utensils'"),
    ]
    for tablo, sutun, tanim in yeni:
        mevcut = {r["name"] for r in conn.execute(f"PRAGMA table_info({tablo})")}
        if mevcut and sutun not in mevcut:
            conn.execute(f"ALTER TABLE {tablo} ADD COLUMN {sutun} {tanim}")
            print(f"[göç] {tablo}.{sutun} eklendi")
    conn.commit()


# ─────────────────────────── AYARLAR ───────────────────────────

AYAR_VARSAYILAN = {
    # Boş bırakılır — kullanıcı ilk kurulumda kendi adını girer. Arayüz
    # boş adda "Adfix" / fişte "ADFIX" göstererek geçici bir marka basar,
    # böylece kullanıcının kendi adında Türkçe büyük harf kuralı (i→İ) doğru
    # işler; sabit yazsak "Adfix" özel-adı da "ADFİX" olurdu.
    "isletme_adi":  "",
    "slogan":       "",
    "adres":        "",
    "telefon":      "",
    "logo":         "",       # data URI
    "fis_alt_not":  "Afiyet olsun · Teşekkür ederiz",
    "qr_taban_url": "",       # QR'ların işaret edeceği adres, ör. http://192.168.1.20:8002
}


def ayarlari_al(conn) -> dict:
    d = dict(AYAR_VARSAYILAN)
    for r in conn.execute("SELECT anahtar, deger FROM ayarlar"):
        if r["anahtar"] in d:
            d[r["anahtar"]] = r["deger"]
    return d


def ayar_yaz(conn, anahtar: str, deger: str):
    if anahtar not in AYAR_VARSAYILAN:
        raise KeyError(anahtar)
    conn.execute("INSERT INTO ayarlar (anahtar, deger) VALUES (?,?) "
                 "ON CONFLICT(anahtar) DO UPDATE SET deger=excluded.deger",
                 (anahtar, deger))


def kayit_log(conn, kullanici: dict | None, islem: str, detay: str = ""):
    """Her para/iptal hareketi loglanır — kasa farkı çıkarsa kim ne yaptı görünsün."""
    conn.execute(
        "INSERT INTO log (kullanici_id, kullanici_ad, islem, detay) VALUES (?,?,?,?)",
        ((kullanici or {}).get("id"), (kullanici or {}).get("ad_soyad", ""), islem, detay)
    )


# ─────────────────────────── SEED ───────────────────────────

def seed_data():
    """Boş veritabanına örnek kurulum basar. Var olan veriye dokunmaz."""
    import auth
    conn = get_conn()
    c = conn.cursor()

    if c.execute("SELECT COUNT(*) n FROM kullanicilar").fetchone()["n"] == 0:
        ilk_sifre = os.environ.get("ADFIX_ILK_SIFRE", "adfix2026")
        c.executemany(
            "INSERT INTO kullanicilar (ad_soyad, kullanici_adi, sifre_hash, rol) VALUES (?,?,?,?)",
            [
                ("Sistem Yöneticisi", "admin",  auth.hash_sifre(ilk_sifre), "yonetici"),
                ("Kasa",              "kasa",   auth.hash_sifre(ilk_sifre), "kasiyer"),
                ("Garson 1",          "garson", auth.hash_sifre(ilk_sifre), "garson"),
            ])

    if c.execute("SELECT COUNT(*) n FROM salonlar").fetchone()["n"] == 0:
        c.executemany("INSERT INTO salonlar (ad, sira) VALUES (?,?)",
                      [("İç Salon", 1), ("Bahçe", 2), ("Teras", 3)])
        masalar = []
        for salon_id, adet, on_ek in ((1, 12, "M"), (2, 8, "B"), (3, 6, "T")):
            for i in range(1, adet + 1):
                masalar.append((salon_id, f"{on_ek}{i}", 4, i))
        c.executemany("INSERT INTO masalar (salon_id, ad, kapasite, sira) VALUES (?,?,?,?)", masalar)

    if c.execute("SELECT COUNT(*) n FROM kategoriler").fetchone()["n"] == 0:
        kats = [
            ("Çorbalar",    "#F59E0B", "soup",     1),
            ("Ara Sıcaklar","#EF4444", "sandwich", 2),
            ("Ana Yemek",   "#DC2626", "utensils", 3),
            ("Izgara",      "#B91C1C", "beef",     4),
            ("Salatalar",   "#16A34A", "salad",    5),
            ("Tatlılar",    "#DB2777", "cake",     6),
            ("Sıcak İçecek","#7C3AED", "coffee",   7),
            ("Soğuk İçecek","#0284C7", "wine",     8),
        ]
        c.executemany("INSERT INTO kategoriler (ad, renk, ikon, sira) VALUES (?,?,?,?)", kats)
        # (kategori_sira, ad, fiyat_kurus, mutfak)
        urun = [
            (1, "Mercimek Çorbası", 8500,  1), (1, "Ezogelin Çorbası", 8500, 1),
            (1, "İşkembe Çorbası", 11000, 1),
            (2, "Sigara Böreği",   9500,  1), (2, "Kalamar Tava", 21000, 1),
            (2, "Paçanga Böreği", 14000, 1),
            (3, "Karnıyarık",     18500, 1), (3, "Etli Kuru Fasulye", 16000, 1),
            (3, "Mantı",          19500, 1), (3, "Fırın Makarna", 15000, 1),
            (4, "Adana Kebap",    32000, 1), (4, "Urfa Kebap", 32000, 1),
            (4, "Tavuk Şiş",      27500, 1), (4, "Kuzu Pirzola", 46000, 1),
            (4, "Köfte",          26000, 1),
            (5, "Çoban Salata",   9000,  1), (5, "Mevsim Salata", 9500, 1),
            (5, "Gavurdağı",      11000, 1),
            (6, "Künefe",         14500, 1), (6, "Sütlaç", 9000, 1),
            (6, "Baklava (porsiyon)", 16000, 1),
            (7, "Çay",            2000,  0), (7, "Türk Kahvesi", 7500, 0),
            (7, "Filtre Kahve",   8500,  0),
            (8, "Ayran",          3500,  0), (8, "Su (0.5 lt)", 1500, 0),
            (8, "Soda",           3000,  0), (8, "Kola",  5500, 0),
            (8, "Limonata",       6500,  0),
        ]
        kat_id = {r["sira"]: r["id"] for r in c.execute("SELECT id, sira FROM kategoriler")}
        c.executemany(
            "INSERT INTO urunler (kategori_id, ad, fiyat_kurus, mutfak, sira) VALUES (?,?,?,?,?)",
            [(kat_id[k], ad, f, m, i) for i, (k, ad, f, m) in enumerate(urun, 1)])

    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()
    seed_data()
    print(f"Adfix veritabanı hazır: {DB_PATH}")
