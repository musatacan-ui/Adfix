#!/bin/bash
# Adfix — Sunucuda git pull ile güncelleme
# Kullanım (sunucuda): bash /home/sagunmed/SagunMedBeta/Adfix/deploy/guncelle.sh [branch]
# Örnek: bash guncelle.sh
#         bash guncelle.sh claude/adisyon-programi-tasarimi-qxc7pq
set -euo pipefail

REPO="/home/sagunmed/SagunMedBeta"
BRANCH="${1:-master}"

echo "═══ Adfix Güncelleme ═══"
echo "Branch: $BRANCH"
echo

cd "$REPO"

echo "[1/3] Git pull…"
git fetch origin "$BRANCH"
git merge "origin/$BRANCH" --no-edit

echo "[2/3] PM2 restart…"
pm2 restart adfix

echo "[3/3] Durum kontrolü…"
sleep 2
pm2 status adfix

echo
echo "✓ Güncelleme tamamlandı."
echo "  Log: pm2 logs adfix --lines 20"
echo "  Adres: https://adfixapp.com.tr"
