# Adfix — Sunucu Kurulum Rehberi

**Sunucu:** sagunmed.com (SSH port 22667)
**Domainler:** adfixapp.com.tr (ana) · adfixapp.info · adfixapp.online

---

## 1. DNS Ayarları

Domain sağlayıcının panelinden her üç domain için A kayıtları ekle:

| Kayıt | İsim | Değer |
|-------|------|-------|
| A | @ | `SUNUCU_IP` |
| A | www | `SUNUCU_IP` |

Sunucu IP'sini öğrenmek için:
```bash
ssh sagunmed@sagunmed.com -p 22667 "curl -s ifconfig.me"
```

6 kayıt toplam (3 domain × 2). Yayılım 5 dk – 48 saat sürebilir.

Kontrol:
```bash
dig +short adfixapp.com.tr
dig +short adfixapp.info
dig +short adfixapp.online
```

---

## 2. Sunucuya Deploy

```bash
cd ~/SagunMed
bash Adfix/deploy/deploy.sh
```

Bu script:
- Backend + frontend dosyalarını yükler
- pip bağımlılıklarını kurar
- PM2 ile adfix servisini başlatır

---

## 3. Firewall

```bash
ssh sagunmed@sagunmed.com -p 22667 "sudo ufw allow 80/tcp && sudo ufw allow 443/tcp"
```

Port 8002 dışarıdan erişime AÇILMAZ — nginx proxy arkasında kalır.

---

## 4. nginx Kurulumu

```bash
ssh sagunmed@sagunmed.com -p 22667
sudo cp /tmp/nginx-adfix.conf /etc/nginx/sites-available/adfix
sudo ln -sf /etc/nginx/sites-available/adfix /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

---

## 5. SSL Sertifikası

DNS yayılımı tamamlandıktan sonra:

```bash
ssh sagunmed@sagunmed.com -p 22667
sudo bash /tmp/ssl-kur.sh    # deploy.sh ile yüklenmişse
# veya manuel:
sudo certbot --nginx \
  -d adfixapp.com.tr -d www.adfixapp.com.tr \
  -d adfixapp.info -d www.adfixapp.info \
  -d adfixapp.online -d www.adfixapp.online \
  --agree-tos --email musatacan@gmail.com
```

certbot nginx config'i otomatik günceller ve yenileme cron'u kurar.

---

## 6. JWT Anahtarı (Üretim)

```bash
ssh sagunmed@sagunmed.com -p 22667
cd /home/sagunmed/SagunMedBeta/Adfix/backend

# Güçlü anahtar üret
python3 -c "import secrets;print('ADFIX_JWT_SECRET='+secrets.token_urlsafe(48))" > .env
echo "ADFIX_PORT=8002" >> .env
chmod 600 .env

# PM2'ye de ekle
pm2 restart adfix
```

---

## 7. Doğrulama

```bash
# Sunucu durumu
ssh sagunmed@sagunmed.com -p 22667 "pm2 status adfix"

# SSL testi
curl -I https://adfixapp.com.tr

# Yönlendirmeler
curl -I http://adfixapp.com.tr        # → 301 https
curl -I https://adfixapp.info         # → 301 adfixapp.com.tr
curl -I https://adfixapp.online       # → 301 adfixapp.com.tr

# API çalışıyor mu
curl -s https://adfixapp.com.tr/api/acik/menu | head -c 200
```

---

## 8. QR Menü URL Ayarı

Yönetim panelinden (https://adfixapp.com.tr → giriş → Yönetim → QR Menü):

**QR Taban URL:** `https://adfixapp.com.tr`

Bu değer QR kodlara basılır. Müşteriler bu URL'yi telefonla tarar.

---

## PM2 Komutları

```bash
pm2 status           # tüm servisler
pm2 logs adfix       # canlı loglar
pm2 restart adfix    # yeniden başlat
pm2 stop adfix       # durdur
pm2 delete adfix     # sil
```

---

## Sorun Giderme

| Sorun | Çözüm |
|-------|-------|
| 502 Bad Gateway | `pm2 status adfix` — çalışıyor mu kontrol et |
| SSL sertifika hatası | DNS yayılımını bekle, `certbot renew` dene |
| QR telefondan açılmıyor | Taban URL'de `https://adfixapp.com.tr` olmalı |
| Giriş çalışmıyor | `.env` dosyasında JWT anahtarı var mı kontrol et |
| 413 Entity Too Large | nginx'te `client_max_body_size` artır |
