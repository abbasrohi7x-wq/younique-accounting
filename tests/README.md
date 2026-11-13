# آزمون‌های UNIQUE

- `run_tests.py` — مجموعهٔ مرورگری روی برنامهٔ واقعی در Chromium.
- پوشش: مالیات، فروش/خرید، پرداخت ترکیبی، برگشت و ابطال، FIFO و میانگین موزون، صندوق، چک و وام، انتقال و انبارگردانی، نقش‌ها و PIN، QR، IndexedDB، مهاجرت، رمزگذاری و پشتیبان‌گیری، تأیید دستیار هوشمند و کنترل صندوق.
- آخرین نتیجهٔ CI: **۲۹ آزمون، ۱۷۵ Assertion — همگی موفق** (۱۳ نوامبر ۲۰۲۶).
- `helpers.js` — ابزار تزریق‌شده به صفحه؛ فقط دادهٔ ساختگی.
- `headless_probe.js` — آزمایش اجرای موتور در Node.
- نیازمندی‌ها: `pip install playwright numpy opencv-python-headless` و `python -m playwright install chromium`.
- اجرا: `python3 tests/run_tests.py [بخشی از نام آزمون]`.
- QR با OpenCV راستی‌آزمایی می‌شود؛ اگر نصب نباشد آن بررسی SKIP می‌شود.
