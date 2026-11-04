@echo off
chcp 65001 >nul 2>&1
title Adfix Deploy

rem GitHub main dalini sunucudaki klona ceker ve adfix servisini yeniden baslatir.
rem Yerel dosyalar kopyalanmaz: once degisiklikleri GitHub'da main'e birlestir.
set SUNUCU=sagunmed@sagunmed.com
set PORT=22667
set HEDEF=/home/sagunmed/Adfix-yeni

echo Adfix Deploy
echo.

ssh -p %PORT% %SUNUCU% "cd %HEDEF% && git pull --ff-only origin main && pm2 restart adfix && sleep 3 && pm2 logs adfix --lines 15 --nostream"
if %errorlevel% neq 0 goto hata

echo.
echo Deploy tamamlandi - https://adfixapp.com.tr
echo Sayfayi Ctrl+F5 ile yenile.
echo.
pause
exit /b 0

:hata
echo.
echo HATA olustu!
pause
exit /b 1
