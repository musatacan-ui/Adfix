"""
Adfix — Adisyon & Masa Yonetim Sistemi
"Adisyonu hallet."

Multi-tenant: /i/{slug}/ on eki ile isletmeye ozel DB secilir.
On ek yoksa varsayilan adfix.db kullanilir (geriye uyumlu).

Calistirma:
    export ADFIX_JWT_SECRET=$(python3 -c 'import secrets;print(secrets.token_urlsafe(48))')
    python3 main.py
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.types import ASGIApp, Receive, Scope, Send
from contextlib import asynccontextmanager
import os
import uvicorn

import database as db
import tenant
import ag
from routers import kullanici, menu, masa, adisyon, rapor, ayar, acik, merkez

PORT = int(os.environ.get("ADFIX_PORT", "8002"))
FRONTEND = os.path.join(os.path.dirname(__file__), "..", "frontend")


# ─── Multi-tenant ASGI Middleware ───

class IsletmeMiddleware:
    """URL'den /i/{slug}/ on ekini cikarir, slug'a ait DB'yi aktif eder."""

    def __init__(self, inner: ASGIApp):
        self.inner = inner

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] not in ("http", "websocket"):
            await self.inner(scope, receive, send)
            return

        path: str = scope["path"]
        if not path.startswith("/i/"):
            await self.inner(scope, receive, send)
            return

        parts = path.split("/", 3)
        if len(parts) < 3 or not parts[2]:
            await self.inner(scope, receive, send)
            return

        slug = parts[2]
        if not db.isletme_slug_kontrol(slug):
            r = JSONResponse({"detail": "Isletme bulunamadi"}, status_code=404)
            await r(scope, receive, send)
            return

        rest = "/" + parts[3] if len(parts) > 3 else "/"
        scope = dict(scope)
        scope["path"] = rest
        raw_path = scope.get("raw_path", b"")
        prefix_bytes = f"/i/{slug}".encode()
        if raw_path.startswith(prefix_bytes):
            scope["raw_path"] = raw_path[len(prefix_bytes):] or b"/"

        tok = tenant.isletme_slug.set(slug)
        try:
            await self.inner(scope, receive, send)
        finally:
            tenant.isletme_slug.reset(tok)


# ─── Lifespan ───

@asynccontextmanager
async def lifespan(_a: FastAPI):
    db.init_merkez_db()
    db.init_db()
    db.seed_data()
    print(f"\nAdfix hazir (multi-tenant)")
    print(f"  Adres            : http://localhost:{PORT}")
    taban = ag.onerilen_taban(PORT)
    if taban:
        print(f"  Telefon / tablet : {taban}")
    print(f"  Varsayilan DB    : {db.DB_PATH}")
    print(f"  Isletme DB dizini: {db.DATA_DIR}")
    isletmeler = db.isletme_listesi()
    if isletmeler:
        print(f"  Kayitli isletme  : {len(isletmeler)}")
        for isl in isletmeler:
            durum = "aktif" if isl["aktif"] else "pasif"
            print(f"    /i/{isl['slug']}/ — {isl['ad']} ({durum})")
    print()
    yield


# ─── FastAPI App ───

_app = FastAPI(title="Adfix API", version="1.4.0",
               description="Adisyon & masa yonetimi (multi-tenant)",
               lifespan=lifespan)

_app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("ADFIX_CORS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_app.include_router(kullanici.router, prefix="/api/kullanici", tags=["Kullanici"])
_app.include_router(menu.router,      prefix="/api/menu",      tags=["Menu"])
_app.include_router(masa.router,      prefix="/api/masa",      tags=["Masa"])
_app.include_router(adisyon.router,   prefix="/api/adisyon",   tags=["Adisyon"])
_app.include_router(rapor.router,     prefix="/api/rapor",     tags=["Rapor"])
_app.include_router(ayar.router,      prefix="/api/ayar",      tags=["Ayar"])
_app.include_router(acik.router,      prefix="/api/acik",      tags=["Acik (QR menu)"])
_app.include_router(merkez.router,    prefix="/api/merkez",    tags=["Merkez Yonetim"])


@_app.get("/saglik", include_in_schema=False)
def saglik():
    conn = db.get_conn()
    n = conn.execute("SELECT COUNT(*) n FROM adisyonlar WHERE durum='acik'").fetchone()["n"]
    conn.close()
    return {"durum": "ayakta", "acik_adisyon": n}


@_app.get("/api/acik/isletmeler", include_in_schema=False)
def acik_isletmeler():
    """Aktif işletmelerin listesi (auth gerektirmez, anasayfa için)."""
    liste = db.isletme_listesi()
    return [{"ad": i["ad"], "slug": i["slug"]} for i in liste if i["aktif"]]


@_app.get("/", include_in_schema=False)
def anasayfa():
    slug = tenant.isletme_slug.get(None)
    if slug:
        return FileResponse(os.path.join(FRONTEND, "adfix.html"))
    return FileResponse(os.path.join(FRONTEND, "anasayfa.html"))


@_app.get("/menu", include_in_schema=False)
@_app.get("/menu/", include_in_schema=False)
def qr_menu_sayfasi():
    return FileResponse(os.path.join(FRONTEND, "menu.html"))


@_app.get("/merkez", include_in_schema=False)
@_app.get("/merkez/", include_in_schema=False)
def merkez_sayfasi():
    return FileResponse(os.path.join(FRONTEND, "merkez.html"))


if os.path.isdir(FRONTEND):
    _app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")

# Dis katman: isletme middleware'i FastAPI'yi sarar
app = IsletmeMiddleware(_app)


if __name__ == "__main__":
    yeniden = os.environ.get("ADFIX_RELOAD", "1") == "1"
    uvicorn.run("main:app" if yeniden else app, host="0.0.0.0", port=PORT, reload=yeniden)
