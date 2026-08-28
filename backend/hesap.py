"""
Adfix — adisyon hesap motoru (TEK DOĞRULUK KAYNAĞI).

Bir adisyonun tutarı SADECE burada hesaplanır. Masa planı, adisyon ekranı,
fiş çıktısı ve gün sonu raporu hep bu fonksiyonları çağırır; böylece
"ekranda başka, fişte başka, raporda başka" durumu oluşamaz.

Satır durumlarının tutara etkisi:
  bekliyor / hazir : tutara SAYILIR
  ikram            : tutara SAYILMAZ (ikram toplamında ayrıca raporlanır)
  iptal            : tutara SAYILMAZ (kayıt silinmez — kim iptal etti izi kalır)
"""

SAYILAN_DURUMLAR = ("bekliyor", "hazir")


def satir_toplamlari(conn, adisyon_id: int) -> dict:
    r = conn.execute("""
        SELECT
          COALESCE(SUM(CASE WHEN durum IN ('bekliyor','hazir') THEN birim_kurus*adet END),0) AS ara,
          COALESCE(SUM(CASE WHEN durum='ikram' THEN birim_kurus*adet END),0)                 AS ikram,
          COALESCE(SUM(CASE WHEN durum='iptal' THEN birim_kurus*adet END),0)                 AS iptal,
          COALESCE(SUM(CASE WHEN durum IN ('bekliyor','hazir') THEN adet END),0)              AS adet
        FROM adisyon_satir WHERE adisyon_id=?
    """, (adisyon_id,)).fetchone()
    return {"ara": r["ara"], "ikram": r["ikram"], "iptal": r["iptal"], "adet": r["adet"]}


def odeme_toplami(conn, adisyon_id: int) -> int:
    return conn.execute(
        "SELECT COALESCE(SUM(tutar_kurus),0) t FROM odemeler WHERE adisyon_id=?",
        (adisyon_id,)).fetchone()["t"]


def ozet(conn, adisyon_id: int) -> dict:
    """Adisyonun tam mali özeti. Tüm değerler kuruş (int)."""
    ad = conn.execute("SELECT * FROM adisyonlar WHERE id=?", (adisyon_id,)).fetchone()
    if not ad:
        return {}
    t = satir_toplamlari(conn, adisyon_id)
    # İskonto ara toplamı aşamaz — eksi tutarlı adisyon oluşmasın.
    iskonto = min(max(ad["iskonto_kurus"] or 0, 0), t["ara"])
    net = t["ara"] - iskonto
    odenen = odeme_toplami(conn, adisyon_id)
    return {
        "ara_toplam": t["ara"],
        "ikram":      t["ikram"],
        "iptal":      t["iptal"],
        "urun_adet":  t["adet"],
        "iskonto":    iskonto,
        "net_toplam": net,
        "odenen":     odenen,
        "kalan":      net - odenen,
    }


def kisi_basi(net_kurus: int, kisi: int) -> int:
    """Hesabı kişiye bölerken kuruş kaybı olmasın diye YUKARI yuvarlar.
    Son kişiye kalan düşürülür (bkz. adisyon.py -> hesap_bol)."""
    kisi = max(1, kisi)
    return -(-net_kurus // kisi)


def bol_dagit(net_kurus: int, kisi: int) -> list[int]:
    """net_kurus'u kisi kadar parçaya böler; toplamları TAM olarak net_kurus eder.
    Artan kuruşlar ilk kişilere dağıtılır (1 kuruş bile kaybolmaz)."""
    kisi = max(1, kisi)
    taban, artan = divmod(max(0, net_kurus), kisi)
    return [taban + (1 if i < artan else 0) for i in range(kisi)]
