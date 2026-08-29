"""
Multi-tenant context: aktif işletme slug'ını tutar.

Her HTTP isteği başında middleware tarafından ayarlanır.
Slug ayarlıysa get_conn() o işletmenin DB'sine bağlanır;
yoksa varsayılan adfix.db kullanılır (geriye uyumlu).
"""
import contextvars

isletme_slug: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "isletme_slug", default=None
)
