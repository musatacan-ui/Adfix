"""
Yerel ağ adresi tespiti.

Amaç: yöneticinin `ipconfig` çalıştırıp IP'yi elle yazmasını gerektirmemek.
QR menüsünün müşterinin telefonunda açılabilmesi için karekodun `localhost`
değil, kasadaki bilgisayarın YEREL AĞ adresini işaret etmesi şarttır.
"""
import socket

# Yerel ağ (RFC 1918) blokları — QR için sadece bunlar işe yarar.
_OZEL_ONEKLER = ("192.168.", "10.")


def _ozel_mi(ip: str) -> bool:
    if ip.startswith(_OZEL_ONEKLER):
        return True
    if ip.startswith("172."):
        try:
            return 16 <= int(ip.split(".")[1]) <= 31
        except (IndexError, ValueError):
            return False
    return False


def yerel_adresler() -> list[str]:
    """Bu makinenin yerel ağdaki IPv4 adresleri; en olası olan başta.

    İki yöntem birleştirilir:
      1) UDP soketi ile varsayılan rota arayüzünü sorma (paket GÖNDERİLMEZ,
         internet bağlantısı gerekmez — çekirdek yalnızca rotayı çözer)
      2) Makine adının çözümlenmesi (birden çok arayüz varsa yakalar)
    """
    bulunan, sirali = set(), []

    for hedef in ("10.255.255.255", "192.168.1.1", "8.8.8.8"):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.25)
            try:
                s.connect((hedef, 9))
                ip = s.getsockname()[0]
                if ip not in bulunan and not ip.startswith("127."):
                    bulunan.add(ip)
                    sirali.append(ip)
            finally:
                s.close()
        except OSError:
            continue

    try:
        for bilgi in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = bilgi[4][0]
            if ip not in bulunan and not ip.startswith("127."):
                bulunan.add(ip)
                sirali.append(ip)
    except OSError:
        pass

    # Yerel ağ adresleri önce: QR için kullanılabilir olanlar listenin başında olsun
    return sorted(sirali, key=lambda ip: (not _ozel_mi(ip), ip))


def onerilen_taban(port: int) -> str:
    """QR karekodlarının işaret etmesi gereken adres. Bulunamazsa boş döner.

    Önce yerel ağ (RFC 1918) adresi aranır; yoksa bağlantısız kalmamak için
    ilk kullanılabilir adres önerilir (169.254 otomatik-yapılandırma hariç —
    o adres ağ bağlantısının kurulamadığı anlamına gelir)."""
    adresler = [ip for ip in yerel_adresler() if not ip.startswith("169.254.")]
    if not adresler:
        return ""
    ozel = [ip for ip in adresler if _ozel_mi(ip)]
    return f"http://{(ozel or adresler)[0]}:{port}"


if __name__ == "__main__":
    print("Yerel adresler:", yerel_adresler())
    print("Önerilen QR tabanı:", onerilen_taban(8002) or "(bulunamadı)")
