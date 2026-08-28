@echo off
chcp 65001 >nul
title Adfix - Adisyon Sistemi
cd /d "%~dp0backend"

echo ============================================
echo   ADFIX - Adisyon ve Masa Yonetim Sistemi
echo ============================================
echo.

REM ---- Python var mi? ----
python --version >nul 2>&1
if errorlevel 1 (
  echo [HATA] Python bulunamadi. python.org adresinden kurun ve kurulumda
  echo        "Add Python to PATH" kutusunu isaretleyin. Zaten kuruluysa
  echo        bu dosyadaki "python" komutlarini "py" ile degistirin.
  pause
  exit /b 1
)

REM ---- Bagimliliklar kurulu mu? ----
python -c "import fastapi, uvicorn, jwt, bcrypt" >nul 2>&1
if errorlevel 1 (
  echo [1/2] Gerekli paketler kuruluyor, bir kereye mahsus...
  python -m pip install -q -r "..\requirements.txt"
  if errorlevel 1 (
    echo [HATA] Paketler kurulamadi. Internet baglantisini kontrol edin.
    pause
    exit /b 1
  )
)

REM ---- JWT anahtari: bir kez uretilir, .env dosyasinda saklanir ----
REM     (her acilista yeni anahtar uretilirse acik oturumlar duser)
if not exist .env (
  echo [2/2] Guvenlik anahtari uretiliyor...
  python -c "import secrets;print('ADFIX_JWT_SECRET='+secrets.token_urlsafe(48))" > .env
)
for /f "usebackq tokens=1,* delims==" %%a in (".env") do set "%%a=%%b"

echo.
echo   Adres    : http://localhost:8002
echo   Hesaplar : admin / kasa / garson      Sifre: adfix2026
echo   Kapatmak : bu pencerede Ctrl+C
echo.

start "" /b python -c "import time,webbrowser;time.sleep(4);webbrowser.open('http://localhost:8002')"
python main.py

echo.
echo Sunucu durdu.
pause
