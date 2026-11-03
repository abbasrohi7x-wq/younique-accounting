# استخراج موتور حسابداری/انبار — گزارش امکان‌سنجی (فاز ۱)

## اندازه‌گیری‌های واقعی (از کد فعلی، نه تخمین)
| تابع | وابستگی به UI (DOM/toast/modal/render) |
|---|---|
| postJournal, atomic, cashMove, openCashSession, closeCashSession, accountBalance, transferFunds | ۰ |
| stockMoveV21, stockMove, costingMethod, yqVatCfg, saleTotal | ۰ |
| شیء `Fin` (برگشت، ابطال، اصلاح فروش/خرید) — ~۱۱ کیلوبایت | ۰ |
| validateBackupData, normalize | ۰ |
| `__saveSaleCore` | ۱۶ (به DOM وابسته) |
| `savePurchaseV18` | ۵ (به DOM وابسته) |
- کل برنامه ۹۴۲ بار به شیء سراسری `db` ارجاع می‌دهد؛ این مهم‌ترین مانع استخراج است.

## آزمایش اجرای بی‌مرورگر (`node tests/headless_probe.js`)
- ۳۲ از ۳۲ اسکریپت با DOM ساختگی در Node بارگذاری شد.
- `db`, `Fin`, `postJournal`, `accountBalance`, `stockMoveV21`, `atomic`, `cashMove`, `openCashSession`, `costingMethod`, `validateBackupData` در دسترس بودند.
- سند نامتوازن (۱۰۰ ≠ ۹۰) رد شد و هیچ ردیفی در دفتر نماند؛ سند متوازن ثبت شد؛ `atomic` پس از خطا، دفتر را به حالت قبل برگرداند.
- **محدودیت:** این فقط «اثبات امکان» است. DOM ساختگی (Proxy) طراحی نهایی نیست. مسیر ساخت فروش/خرید، ذخیره‌سازی (IndexedDB در Node وجود ندارد) و همگام‌سازی هنوز بدون مرورگر آزمایش نشده‌اند.

## نتیجه
موتور هستهٔ مالی/انباری قابل اجرا روی سرور است؛ بازنویسی لازم نیست. کار لازم:
1. شکستن `__saveSaleCore` و `savePurchaseV18` به «تابع خالص `createSale(payload)` / `createPurchase(payload)`» + آداپتر UI که فرم را به payload تبدیل می‌کند.
2. تزریق `db` به‌جای متغیر سراسری (یا اجرای هر درخواست سرور در یک context مستقل با `db` خودش).
3. جدا کردن لایه‌های wrapper (ظاهر) از لایهٔ منطق قبل از بسته‌بندی ماژول.
4. حفظ آزمون‌های `tests/run_tests.py` به‌عنوان تور ایمنی: هر مرحله فقط با سبز بودن همهٔ آن‌ها پذیرفته می‌شود.

## آنچه هنوز انجام نشده
بیرون‌کشیدن واقعی کد به فایل ماژول؛ آزمون ساخت فروش/خرید بی‌مرورگر؛ ماژول ذخیره‌سازی سرور.
