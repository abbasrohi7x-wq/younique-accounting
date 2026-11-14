# آزمون‌های Unique Pro

- `run_tests.py` — ۲۸ آزمون رگرسیون مرورگر با Chromium؛ شامل فروش/خرید و حسابداری، پرداخت چندروش، موجودی و انبار، ذخیره‌سازی IndexedDB، اعتبارسنجی پشتیبان، انتقال فایل‌محور، امنیت PIN، OCR واقعی Tesseract، بارگذاری مدل فارسی Vosk، تشخیص بی‌صدایی میکروفون، تطبیق گزارش مدیریتی و چیدمان موبایل.
- `helpers.js` — ابزارهای آزمون با داده‌های ساختگی؛ هیچ دادهٔ واقعی فروشگاه استفاده نمی‌شود.
- `headless_probe.js` — بررسی مستقل اجرای موتور در Node.
- برای QR، در صورت نصب نبودن OpenCV، فقط آزمون رمزگشایی مستقل QR رد می‌شود؛ سایر آزمون‌ها اجرا می‌شوند.

## اجرا

```bash
python -m pip install playwright
python -m playwright install chromium
python -m http.server 8765
# در ترمینال دیگر:
python tests/run_tests.py
```

برای اجرای یک آزمون مشخص:

```bash
python tests/run_tests.py offline_ocr
```

GitHub Actions علاوه بر آزمون‌های مرورگر، صحت ساخت برنامه و بسته‌های محلی OCR/Vosk را کنترل می‌کند.
