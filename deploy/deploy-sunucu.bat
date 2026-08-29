@echo off
chcp 65001 >nul 2>&1
title Adfix Deploy

set SUNUCU=sagunmed@sagunmed.com
set PORT=22667
set REPO=/home/sagunmed/SagunMedBeta

set /p BRANCH=Branch (bos birak = master):
if "%BRANCH%"=="" set BRANCH=master

echo.
echo Git pull (%BRANCH%)...
ssh -p %PORT% %SUNUCU% "cd %REPO% && git fetch origin %BRANCH% && git merge origin/%BRANCH% --no-edit"
if %errorlevel% neq 0 goto hata

echo PM2 restart...
ssh -p %PORT% %SUNUCU% "pm2 restart adfix"
if %errorlevel% neq 0 goto hata

echo Durum kontrolu...
ping -n 3 127.0.0.1 >nul
ssh -p %PORT% %SUNUCU% "pm2 status adfix"

echo.
echo Deploy tamamlandi - https://adfixapp.com.tr
echo.
pause
exit /b 0

:hata
echo.
echo HATA olustu!
pause
exit /b 1
