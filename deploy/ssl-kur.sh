#!/bin/bash
# Adfix — Let's Encrypt SSL sertifikası kurulumu
# Kullanım: sudo bash ssl-kur.sh
# Ön koşul: DNS A kayıtları sunucu IP'sine işaret etmeli
set -euo pipefail

DOMAINLER=(
  "adfixapp.com.tr"
  "www.adfixapp.com.tr"
  "adfixapp.info"
  "www.adfixapp.info"
  "adfixapp.online"
  "www.adfixapp.online"
)

echo "═══ Adfix SSL Kurulumu ═══"

# 1) certbot kur
echo "[1/4] certbot kontrol ediliyor…"
if ! command -v certbot &>/dev/null; then
  apt-get update -qq
  apt-get install -y -qq certbot python3-certbot-nginx
fi

# 2) certbot doğrulama dizini
echo "[2/4] Doğrulama dizini hazırlanıyor…"
mkdir -p /var/www/certbot

# 3) nginx config kopyala (SSL olmadan ilk çalıştırma)
echo "[3/4] nginx yapılandırması kuruluyor…"
cp /tmp/nginx-adfix.conf /etc/nginx/sites-available/adfix 2>/dev/null || true
ln -sf /etc/nginx/sites-available/adfix /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx

# 4) Sertifika al
echo "[4/4] Sertifika alınıyor…"
DOMAIN_ARGS=""
for d in "${DOMAINLER[@]}"; do
  DOMAIN_ARGS="$DOMAIN_ARGS -d $d"
done

certbot --nginx $DOMAIN_ARGS \
  --non-interactive \
  --agree-tos \
  --email musatacan@gmail.com \
  --redirect

echo
echo "✓ SSL kurulumu tamamlandı."
echo "  Otomatik yenileme: certbot renew (cron/timer zaten aktif)"
echo "  Test: curl -I https://adfixapp.com.tr"
