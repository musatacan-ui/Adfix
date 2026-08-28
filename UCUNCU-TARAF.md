# Üçüncü Taraf Lisanslar

Adfix'in içinde gömülü olarak dağıtılan açık kaynak varlıklar ve lisansları.

---

## Lucide (ikon paketi) — v1.34.0

`frontend/adfix.html` ve `frontend/menu.html` içine SVG sprite olarak gömülüdür
(67 ikon). CDN'e bağlanmaz; internet kesikken de çalışır.

Kaynak: https://lucide.dev · https://github.com/lucide-icons/lucide

```
ISC License

Copyright (c) 2026 Lucide Icons and Contributors

Permission to use, copy, modify, and/or distribute this software for any
purpose with or without fee is hereby granted, provided that the above
copyright notice and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
```

### Sprite'ı güncellemek

```bash
npm pack lucide-static && tar xzf lucide-static-*.tgz
# package/icons/<ad>.svg dosyalarının içeriği <symbol id="i-<ad>"> olarak sarılır
```

---

## qrcode (Python) — BSD 3-Clause

Karekod üretimi (`backend/routers/acik.py`). Dış servise istek gitmez,
kodlar sunucuda yerel olarak üretilir.

Kaynak: https://github.com/lincolnloop/python-qrcode

---

## Ürün fotoğrafları

Adfix **hiçbir hazır yemek fotoğrafı ile dağıtılmaz.** Fotoğrafı olmayan ürünlerde
kategorinin renkli Lucide ikonu gösterilir. Gerçek fotoğrafları işletme kendisi
yükler (Menü → ürün → Fotoğraf Seç); yüklenen görsel tarayıcıda 500 px'e
küçültülüp veritabanına yazılır.

Böylece dağıtımda telifli/atıf gerektiren üçüncü taraf fotoğraf bulunmaz ve
müşteri menüsünde stok fotoğraf yerine işletmenin **kendi tabağı** görünür.
