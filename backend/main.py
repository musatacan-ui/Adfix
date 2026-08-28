"""
Adfix — Adisyon & Masa Yönetim Sistemi
"Adisyonu hallet."

Çalıştırma:
    export ADFIX_JWT_SECRET=$(python3 -c 'import secrets;print(secrets.token_urlsafe(48))')
    python3 main.py            # http://localhost:8002
"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import os
import uvicorn

import database as db
import ag
from routers import kullanici, menu, masa, adisyon, rapor, ayar, acik

PORT = int(os.environ.get("ADFIX_PORT", "8002"))
FRONTEND = os.path.join(os.path.dirname(__file__), "..", "frontend")


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    db.seed_data()
    print(f"\nAdfix hazır")
    print(f"  Bu bilgisayarda : http://localhost:{PORT}")
    taban = ag.onerilen_taban(PORT)
    if taban:
        print(f"  Telefon / tablet: {taban}      <- QR menüsü bu adresi kullanmalı")
    else:
        print("  Telefon / tablet: yerel ağ adresi bulunamadı (ağ bağlantısını kontrol edin)")
    print(f"  Veritabanı      : {db.DB_PATH}\n")
    yield


app = FastAPI(title="Adfix API", version="1.2.0",
              description="Adisyon & masa yönetimi", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("ADFIX_CORS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(kullanici.router, prefix="/api/kullanici", tags=["Kullanıcı"])
app.include_router(menu.router,      prefix="/api/menu",      tags=["Menü"])
app.include_router(masa.router,      prefix="/api/masa",      tags=["Masa"])
app.include_router(adisyon.router,   prefix="/api/adisyon",   tags=["Adisyon"])
app.include_router(rapor.router,     prefix="/api/rapor",     tags=["Rapor"])
app.include_router(ayar.router,      prefix="/api/ayar",      tags=["Ayar"])
# Kimlik doğrulaması OLMAYAN müşteri uçları — sadece menü okuma ve QR üretimi
app.include_router(acik.router,      prefix="/api/acik",      tags=["Açık (QR menü)"])


@app.get("/saglik", include_in_schema=False)
def saglik():
    conn = db.get_conn()
    acik = conn.execute("SELECT COUNT(*) n FROM adisyonlar WHERE durum='acik'").fetchone()["n"]
    conn.close()
    return {"durum": "ayakta", "acik_adisyon": acik}


@app.get("/", include_in_schema=False)
def anasayfa():
    return FileResponse(os.path.join(FRONTEND, "adfix.html"))


@app.get("/menu", include_in_schema=False)
@app.get("/menu/", include_in_schema=False)
def qr_menu_sayfasi():
    """Karekod ile açılan müşteri menüsü."""
    return FileResponse(os.path.join(FRONTEND, "menu.html"))


if os.path.isdir(FRONTEND):
    app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")


if __name__ == "__main__":
    # Geliştirmede otomatik yeniden yükleme açık; testte ADFIX_RELOAD=0 ile kapatılır
    # (reload alt süreç doğurur, testin sunucuyu temiz kapatmasını zorlaştırır).
    yeniden = os.environ.get("ADFIX_RELOAD", "1") == "1"
    uvicorn.run("main:app" if yeniden else app, host="0.0.0.0", port=PORT, reload=yeniden)
