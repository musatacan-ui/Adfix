@echo off
chcp 65001 >nul
title Adfix - Guvenlik Duvari Izni
REM Windows Guvenlik Duvari'nda 8002 portunu yerel aga acar.
REM QR menusunun musterinin telefonunda acilabilmesi icin gereklidir.

net session >nul 2>&1
if errorlevel 1 (
  echo.
  echo   [!] Bu dosya YONETICI yetkisiyle calistirilmali.
  echo.
  echo       Dosyaya SAG TIK  ^>  "Yonetici olarak calistir"
  echo.
  pause
  exit /b 1
)

echo.
echo   Adfix icin 8002 portu aciliyor...
echo.

netsh advfirewall firewall delete rule name="Adfix 8002" >nul 2>&1
netsh advfirewall firewall add rule name="Adfix 8002" dir=in action=allow ^
  protocol=TCP localport=8002 profile=private,domain

if errorlevel 1 (
  echo   [HATA] Kural eklenemedi.
  pause
  exit /b 1
)

echo.
echo   [OK] 8002 portu yerel aga acildi.
echo.
echo   Bu bilgisayarin ag adresleri:
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4"') do echo       http://%%a:8002
echo.
echo   Telefonda bu adreslerden birini deneyin (sonuna /menu ekleyerek).
echo   Kural yalnizca OZEL ve ETKI ALANI aglari icin gecerlidir; genel
echo   (kafe/otel gibi) aglarda kapali kalir - bu kasitlidir.
echo.
pause
