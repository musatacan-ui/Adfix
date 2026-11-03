#!/bin/bash
# Adfix — Sunucuda git pull ile güncelleme (SagunMed'e dokunmaz)
# Kullanım (sunucuda): bash /home/sagunmed/Adfix-yeni/deploy/guncelle.sh [branch]
set -euo pipefail

REPO="/home/sagunmed/Adfix-yeni"
BRANCH="${1:-main}"

echo "═══ Adfix Güncelleme ═══"
echo "Branch: $BRANCH"
echo

cd "$REPO"

echo "[1/3] Git pull…"
git pull --ff-only origin "$BRANCH"

echo "[2/3] PM2 restart…"
pm2 restart adfix

echo "[3/3] Durum kontrolü…"
sleep 2
pm2 status adfix

echo
echo "✓ Güncelleme tamamlandı."
echo "  Log: pm2 logs adfix --lines 20"
echo "  Adres: https://adfixapp.com.tr"
