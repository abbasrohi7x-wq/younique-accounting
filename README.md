# Unique Pro — یونیک

برنامهٔ مدیریت فروشگاه، انبار و حسابداری — کاملاً آفلاین (PWA)، بدون سرور اجباری.

## اجرای محلی

```bash
# هر سرور استاتیک
python3 -m http.server 8080
# سپس: http://localhost:8080
```

یا با Node:

```bash
npx serve .
```

> برای OCR و PWA باید از `http`/`https` باز شود، نه `file://`.

## انتشار روی GitHub Pages (رایگان)

1. یک مخزن GitHub بسازید (مثلاً `unique-pro`).
2. محتویات همین پوشه را در **ریشه** مخزن بگذارید (نه داخل زیرپوشه).
3. در GitHub: **Settings → Pages → Deploy from a branch → `main` → `/ (root)`**.
4. بعد از یک دقیقه آدرس شبیه این فعال می‌شود:
   `https://<username>.github.io/<repo>/`

### نکات Pages
- Service Worker و مسیرهای نسبی (`src/engine/...`) روی Pages درست کار می‌کنند.
- برای به‌روزرسانی: push جدید روی `main`.
- اگر نام مخزن با یوزرنیم یکی باشد، سایت روی `https://<username>.github.io/` هم در دسترس است.

## موتور استخراج‌شده (آزمایشی)

```js
// فعال‌سازی موتور جدید
localStorage.setItem('yq_use_new_engine', '1');
location.reload();

// خاموش
localStorage.removeItem('yq_use_new_engine');
location.reload();
```

فایل‌ها: `src/engine/core.js`, `src/engine/fin.js`

## تست

```bash
pip install playwright
python -m playwright install chromium
python3 -m http.server 8765   # ترمینال جدا
python3 tests/run_tests.py
```

## سرور / بک‌اند رایگان (فاز بعد)

الان برنامه **بدون سرور** کامل کار می‌کند. برای همگام‌سازی چنددستگاهی بعداً:

| سرویس | طرح رایگان | کاربرد |
|--------|------------|--------|
| **GitHub Pages** | بله | میزبانی همین PWA |
| **Supabase** | بله (پروژه pause بعد از بی‌فعالیتی) | PostgreSQL + Auth + API |
| **Cloudflare Pages** | بله | جایگزین Pages |
| **Railway / Render** | محدود | اگر Node API جدا بخواهید |

پیشنهاد مسیر:
1. الان → GitHub Pages (استاتیک)
2. بعد → Supabase فقط برای sync اختیاری (طبق تصمیم پروژه)

## ساختار

```
index.html          # برنامه اصلی
service-worker.js   # آفلاین
src/engine/         # موتور خالص (فاز ۱)
tests/              # آزمون رگرسیون
vendor/tesseract/   # OCR آفلاین
```

## مجوز

استفاده شخصی / تجاری مطابق تصمیم مالک پروژه.


## موتور
پیش‌فرض فعال. صفحه: سیستم → موتور برنامه.
