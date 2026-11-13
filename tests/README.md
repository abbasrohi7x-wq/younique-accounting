# آزمون‌های UNIQUE
- `run_tests.py` — ۱۶ آزمون شامل حسابداری/انبار/امنیت و سه آزمون ذخیره‌سازی (بازیابی پس از reload، مهاجرت localStorage و مسدودسازی بازنویسی دادهٔ ناقص) روی برنامهٔ واقعی در Chromium بدون سر. نیاز: `pip install playwright numpy opencv-python-headless` و `python -m playwright install chromium`. اجرا: `python3 tests/run_tests.py [بخشی از نام]`.
- `helpers.js` — ابزار تزریق‌شده به صفحه؛ فقط داده ساختگی.
- `headless_probe.js` — آزمایش اجرای موتور در Node (`node tests/headless_probe.js`).
- QR با OpenCV راستی‌آزمایی می‌شود؛ اگر نصب نباشد آن ادعا رد می‌شود (SKIP) و چاپ می‌شود.
- اعتبار آزمون‌ها با «آزمون جهش» سنجیده شد: بازگرداندن عمدی دو باگ قدیمی، هر دو را شکست داد.
