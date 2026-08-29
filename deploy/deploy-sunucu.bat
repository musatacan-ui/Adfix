@echo off
chcp 65001 >nul 2>&1
title Adfix Deploy

set SUNUCU=sagunmed@sagunmed.com
set PORT=22667
set HEDEF=/home/sagunmed/SagunMedBeta/Adfix
set ADFIX=%~dp0..

echo Adfix Deploy
echo.

echo [1/3] Backend yukleniyor...
scp -P %PORT% "%ADFIX%\backend\*.py" %SUNUCU%:%HEDEF%/backend/
scp -P %PORT% "%ADFIX%\backend\routers\*.py" %SUNUCU%:%HEDEF%/backend/routers/
if %errorlevel% neq 0 goto hata

echo [2/3] Frontend yukleniyor...
scp -P %PORT% "%ADFIX%\frontend\*.html" %SUNUCU%:%HEDEF%/frontend/
if %errorlevel% neq 0 goto hata

echo [3/3] PM2 restart...
ssh -p %PORT% %SUNUCU% "pm2 restart adfix"
if %errorlevel% neq 0 goto hata

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
