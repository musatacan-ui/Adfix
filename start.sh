#!/bin/bash
# Adfix — yerel/sunucu başlatma
set -e
cd "$(dirname "$0")/backend"

command -v python3 >/dev/null || { echo "[HATA] python3 bulunamadı."; exit 1; }

# Bağımlılıklar
if ! python3 -c "import fastapi, uvicorn, jwt, bcrypt" 2>/dev/null; then
  echo "[1/2] Gerekli paketler kuruluyor…"
  python3 -m pip install -q -r ../requirements.txt
fi

# JWT anahtarı: bir kez üretilir, .env'de saklanır.
# Her açılışta yeni anahtar üretilirse açık oturumlar düşer.
if [ -z "$ADFIX_JWT_SECRET" ]; then
  if [ ! -f .env ]; then
    echo "[2/2] Güvenlik anahtarı üretiliyor → backend/.env"
    python3 -c "import secrets;print('ADFIX_JWT_SECRET='+secrets.token_urlsafe(48))" > .env
    chmod 600 .env
  fi
  set -a; . ./.env; set +a
fi

echo
echo "  Adres    : http://localhost:${ADFIX_PORT:-8002}"
echo "  Hesaplar : admin / kasa / garson    Şifre: ${ADFIX_ILK_SIFRE:-adfix2026}"
echo "  Kapatmak : Ctrl+C"
echo
exec python3 main.py
