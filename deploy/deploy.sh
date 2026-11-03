#!/bin/bash
# Adfix — Sunucuya deploy: GitHub main dalını sunucudaki klona çeker, servisi yeniden başlatır.
# Önce değişiklikleri GitHub'da main'e birleştir. Kullanım: bash deploy/deploy.sh
set -euo pipefail

SUNUCU="sagunmed@sagunmed.com"
PORT=22667
HEDEF="/home/sagunmed/Adfix-yeni"

echo "═══ Adfix Deploy ═══"
ssh -p $PORT $SUNUCU "cd $HEDEF && git pull --ff-only origin main && pm2 restart adfix && sleep 3 && pm2 logs adfix --lines 15 --nostream"

echo
echo "✓ Deploy tamamlandı — https://adfixapp.com.tr"
