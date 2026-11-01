# vendor/tesseract — موتور OCR محلی

این پوشه فقط شامل فایل‌هایی است که برنامه **واقعاً** از آن‌ها استفاده می‌کند.

| فایل | نقش |
|---|---|
| `tesseract.min.js`, `worker.min.js` | پوستهٔ tesseract.js نسخهٔ 5.1.1 (بدون تغییر) |
| `core/tesseract-core-simd-lstm.wasm.js` | موتور WebAssembly با SIMD (مرورگرهای امروزی) |
| `core/tesseract-core-lstm.wasm.js` | موتور بدون SIMD (مرورگرهای قدیمی) |
| `lang/fas.traineddata.gz`, `lang/eng.traineddata.gz` | داده‌های زبان فارسی و انگلیسی (فشرده) |

- فایل‌های حذف‌شده (`*.wasm` جدا، glue، نسخه‌های غیر-LSTM و relaxedsimd) هرگز توسط این نسخهٔ پوسته درخواست نمی‌شدند؛ درخواست‌ها در اجرای واقعی ثبت و بررسی شد، و حالت بدون-SIMD هم جداگانه تست شد.
- این فایل‌ها کتابخانهٔ کامپایل‌شدهٔ شخص ثالث‌اند و دست‌نخورده نگه داشته شده‌اند. اثر انگشت SHA-256 همه در `INTEGRITY.json` است.
- مجوزها: `LICENSE-tesseract.js.md` و `LICENSE-tesseract.js-core.txt` (Apache-2.0).
