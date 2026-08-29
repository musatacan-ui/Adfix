#!/bin/bash
# Adfix — Sunucuya deploy
# Kullanım: bash deploy.sh
set -euo pipefail

SUNUCU="sagunmed@sagunmed.com"
PORT=22667
HEDEF="/home/sagunmed/SagunMedBeta/Adfix"
SSH="ssh -p $PORT $SUNUCU"
SCP="scp -P $PORT"

echo "═══ Adfix Deploy ═══"

# 1) Yerel commit kontrolü
if [ -n "$(git status --porcelain Adfix/)" ]; then
  echo "[!] Adfix/ altında commit'lenmemiş değişiklik var."
  echo "    Önce commit et: git add Adfix/ && git commit -m '...'"
  exit 1
fi

# 2) Sunucuda dizin yapısı
echo "[1/5] Dizin yapısı kontrol ediliyor…"
$SSH "mkdir -p $HEDEF/backend $HEDEF/frontend /home/sagunmed/logs"

# 3) Backend dosyaları
echo "[2/5] Backend yükleniyor…"
$SCP Adfix/backend/*.py "$SUNUCU:$HEDEF/backend/"
$SCP Adfix/backend/routers/*.py "$SUNUCU:$HEDEF/backend/routers/"
$SCP Adfix/requirements.txt "$SUNUCU:$HEDEF/"

# 4) Frontend dosyaları
echo "[3/5] Frontend yükleniyor…"
$SCP Adfix/frontend/*.html "$SUNUCU:$HEDEF/frontend/"

# 5) Deploy dosyaları (nginx, ecosystem, start.sh)
echo "[4/5] Deploy dosyaları yükleniyor…"
$SCP Adfix/deploy/nginx-adfix.conf "$SUNUCU:/tmp/"
$SCP Adfix/deploy/ecosystem.config.js "$SUNUCU:$HEDEF/"
$SCP Adfix/start.sh "$SUNUCU:$HEDEF/"
$SSH "chmod +x $HEDEF/start.sh"

# 6) Bağımlılıklar + restart
echo "[5/5] Bağımlılıklar kuruluyor ve yeniden başlatılıyor…"
$SSH "cd $HEDEF && pip3 install -q -r requirements.txt"
$SSH "cd $HEDEF && pm2 restart adfix 2>/dev/null || pm2 start ecosystem.config.js"
$SSH "pm2 save"

echo
echo "✓ Deploy tamamlandı."
echo "  Kontrol: $SSH \"pm2 logs adfix --lines 20\""
echo "  Adres  : https://adfixapp.com.tr"
