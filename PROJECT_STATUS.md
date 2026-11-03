# PROJECT_STATUS — UNIQUE

## تست رگرسیون
| حالت | نتیجه |
|------|--------|
| Flag خاموش (مسیر اصلی) | **13/13 PASS** |
| Flag روشن (موتور استخراج‌شده) | **13/13 PASS** |

## موتور v1.3 + Fin v0.4
- createSale / createPurchase + VAT
- FIFO و میانگین موزون
- warehouseStocks همگام
- void با reverseJournal
- cashMove صندوق روی فروش نقدی
- Bridge opt-in در index.html

## GitHub Pages
آماده — README و workflow موجود است.

## سرور رایگان
1. GitHub Pages برای PWA
2. بعداً Supabase Free برای sync

## فعال‌سازی موتور جدید
```js
localStorage.setItem('yq_use_new_engine','1'); location.reload();
```
