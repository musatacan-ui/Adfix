@echo off
chcp 65001 >nul
title Adfix Deploy

set SUNUCU=sagunmed@sagunmed.com
set PORT=22667
set REPO=/home/sagunmed/SagunMedBeta

echo ══════════════════════════════
echo   Adfix — Sunucu Güncelleme
echo ══════════════════════════════
echo.

set /p BRANCH="Branch (bos birak = master): "
if "%BRANCH%"=="" set BRANCH=master

echo.
echo [1/3] Git pull (%BRANCH%)...
ssh -p %PORT% %SUNUCU% "cd %REPO% && git fetch origin %BRANCH% && git merge origin/%BRANCH% --no-edit"
if errorlevel 1 (
    echo.
    echo [HATA] Git pull basarisiz!
    pause
    exit /b 1
)

echo [2/3] PM2 restart...
ssh -p %PORT% %SUNUCU% "pm2 restart adfix"
if errorlevel 1 (
    echo.
    echo [HATA] PM2 restart basarisiz!
    pause
    exit /b 1
)

echo [3/3] Durum kontrolu...
timeout /t 2 /nobreak >nul
ssh -p %PORT% %SUNUCU% "pm2 status adfix"

echo.
echo ✓ Deploy tamamlandi!
echo   Adres: https://adfixapp.com.tr
echo.
pause
