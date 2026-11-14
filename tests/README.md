# آزمون‌های Unique Pro

- `run_tests.py` — ۳۰ آزمون رگرسیون مرورگر و ۱۵۳ assertion با Chromium؛ شامل فروش/خرید و حسابداری، پرداخت چندروش، موجودی و انبار، ذخیره‌سازی IndexedDB، اعتبارسنجی پشتیبان، انتقال فایل‌محور، امنیت PIN، OCR واقعی Tesseract، بارگذاری مدل فارسی Vosk، تشخیص بی‌صدایی میکروفون، تطبیق گزارش مدیریتی، چیدمان موبایل، ناوبری همهٔ بخش‌ها و ثبت دستی/سریع تأمین‌کننده.
- `helpers.js` — ابزارهای آزمون با داده‌های ساختگی؛ هیچ دادهٔ واقعی فروشگاه استفاده نمی‌شود.
- `headless_probe.js` — بررسی مستقل اجرای موتور در Node.
- GitHub Actions، OpenCV را نصب می‌کند تا رمزگشایی مستقل QR نیز در CI اجرا شود؛ در اجرای محلی بدون OpenCV فقط همان بررسی QR رد می‌شود.

## اجرا

```bash
python -m pip install playwright opencv-python-headless
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
