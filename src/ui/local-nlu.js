/**
 * Local-only colloquial layer for the Unique assistant.
 * Rewrites everyday shop speech into commands the on-device engine already runs.
 * Writes still go through the existing confirmation step. No network, no model.
 */
(function () {
  'use strict';

  function boot() {
    var U = window.UAI;
    if (!U || !U.NLU || typeof U.NLU.understand !== 'function' || !U.chat || U.NLU.understand.__yqColloq) return false;
    var orig = U.NLU.understand;
    var prevHandle = U.chat.handle;

    function norm(s) {
      try { return U.normalize(s); }
      catch (e) {
        return String(s || '').replace(/\u200c/g, ' ').replace(/\s+/g, ' ').trim();
      }
    }

    var EXACT = {
      'صندوق': 'موجودی صندوق چقدره',
      'صندوق چنده': 'موجودی صندوق چقدره',
      'صندوق چقدر': 'موجودی صندوق چقدره',
      'صندوق چقدره': 'موجودی صندوق چقدره',
      'پول صندوق': 'موجودی صندوق چقدره',
      'پول تو صندوق': 'موجودی صندوق چقدره',
      'نقد چقدره': 'موجودی صندوق چقدره',
      'بانک': 'بانک چقدر داریم',
      'بانک چنده': 'بانک چقدر داریم',
      'کارت': 'کارتخوان چقدره',
      'پوز': 'کارتخوان چقدره',
      'کارتخوان': 'کارتخوان چقدره',
      'بدهکارا': 'بدهکارها',
      'بدهکارن': 'بدهکارها',
      'بدهکاران': 'بدهکارها',
      'کیا بدهکارن': 'بدهکارها',
      'کی بدهکاره': 'بدهکارها',
      'کی بهم بدهکاره': 'بدهکارها',
      'طلب ها': 'بدهکارها',
      'طلبا': 'بدهکارها',
      'طلبام': 'بدهکارها',
      'مطالبات': 'بدهکارها',
      'کم موجود': 'کالاهای کم موجود',
      'کمموجود': 'کالاهای کم موجود',
      'کم موجودی': 'کالاهای کم موجود',
      'چی تموم شده': 'کالاهای کم موجود',
      'چیا تموم شدن': 'کالاهای کم موجود',
      'جنس تموم شده': 'کالاهای کم موجود',
      'چی نداریم': 'کالاهای کم موجود',
      'چی بخرم': 'لیست سفارش پیشنهادی کالاهای کم موجود',
      'چی سفارش بدم': 'لیست سفارش پیشنهادی کالاهای کم موجود',
      'پرفروشا': 'پرفروش ترین کالاها این ماه',
      'چی بیشتر فروخته': 'پرفروش ترین کالاها این ماه',
      'چی خوب فروخته': 'پرفروش ترین کالاها این ماه',
      'سود': 'سود این ماه',
      'سودم': 'سود این ماه',
      'سودمون': 'سود این ماه',
      'سود امروز': 'سود و زیان امروز',
      'ضرر امروز': 'سود و زیان امروز',
      'خرج امروز': 'هزینه های امروز رو نشون بده',
      'خرج این ماه': 'هزینه های این ماه رو نشون بده',
      'هزینه ها': 'هزینه های این ماه رو نشون بده',
      'چک': 'چک های در جریان',
      'چکا': 'چک های در جریان',
      'چک ها': 'چک های در جریان',
      'فاکتور امروز': 'فاکتورهای امروز',
      'فاکتورهای امروز': 'فاکتورهای امروز',
      'فاکتور اخر': 'اخرین فروش ها',
      'اخرین فاکتور': 'اخرین فروش ها',
      'تامین کننده': 'به تامین کننده ها چقدر بدهکاریم',
      'چقدر بدهکاریم': 'به تامین کننده ها چقدر بدهکاریم',
      'بدهی تامین کننده': 'به تامین کننده ها چقدر بدهکاریم',
      'فروش امروز': 'فروش امروز چقدره',
      'امروز چقدر فروختیم': 'فروش امروز چقدره',
      'امروز چی فروختیم': 'فروش امروز چقدره',
      'دخل امروز': 'فروش امروز چقدره'
    };

    var RULES = [
      [/^چند(?:\s*تا)?\s+(.+?)\s+(?:مونده|داریم|دارم|هست|موجوده)$/, function (m) { return 'موجودی ' + m[1]; }],
      [/^موجودی\s+(.+?)\s+(?:چنده|چقدره|چقدر)$/, function (m) { return 'موجودی ' + m[1]; }],
      [/^بدهی\s+(.+?)(?:\s+چنده|\s+چقدره|\s+چقدر است|\s+چقدر)?$/, function (m) { return 'بدهی ' + m[1] + ' چقدره'; }],
      [/^مانده(?:\s+حساب)?\s+(.+)$/, function (m) { return 'بدهی ' + m[1] + ' چقدره'; }],
      [/^برای\s+(.+?)\s+(\d+)\s*(?:تا|عدد|جفت)\s+(.+?)(?:\s+بزن|\s+بفروش|\s+فاکتور کن|\s+فاکتور)?$/, function (m) { return /میلیون|هزار|تومان|تومن|ریال/.test(m[3]) ? null : 'فاکتور فروش بساز برای ' + m[1] + ' ' + m[2] + ' تا ' + m[3]; }],
      [/^(\d+)\s*(?:تا|عدد|جفت)\s+(.+?)\s+به\s+(.+?)(?:\s+بزن|\s+بفروش|\s+بده)?$/, function (m) { return /میلیون|هزار|تومان|تومن|ریال/.test(m[2]) ? null : 'فاکتور فروش بساز برای ' + m[3] + ' ' + m[1] + ' تا ' + m[2]; }],
      [/^(\d+)\s*(?:تا|عدد|جفت)\s+(.+?)\s+(?:رو|را)\s+(?:اضافه کن|اضافه|بزن به موجودی|ببر تو انبار)$/, function (m) { return 'موجودی ' + m[2] + ' رو ' + m[1] + ' تا اضافه کن'; }],
      [/^قیمت\s+(.+?)\s+(?:رو|را)\s+(?:بکن|کن)\s+(\d+)(?:\s*(تومان|تومن|ریال))?$/, function (m) { return 'قیمت ' + m[1] + ' رو بکن ' + m[2] + ' ' + (m[3] || 'تومان'); }],
      [/^قبض\s+(.+?)\s+(\d+)(?:\s*(تومان|تومن|ریال))?$/, function (m) { return 'هزینه ' + m[1] + ' ' + m[2] + ' ' + (m[3] || 'تومان'); }],
      [/^(?:خرج|هزینه)\s+(.+?)\s+(\d+)(?:\s*(تومان|تومن|ریال))?$/, function (m) { return 'هزینه ' + m[1] + ' ' + m[2] + ' ' + (m[3] || 'تومان'); }]
    ];

    function rewrite(text) {
      var n = norm(text);
      if (!n) return null;
      if (EXACT[n]) return EXACT[n];
      for (var i = 0; i < RULES.length; i++) {
        var m = n.match(RULES[i][0]);
        if (m) {
          var next = RULES[i][1](m);
          if (next && norm(next) !== n) return next;
        }
      }
      return null;
    }

    function shopFix(text) {
      var n = norm(text);
      var fixed = {
        'امروز چقدر کار کردیم': 'فروش امروز چقدره',
        'کدوم کالا ضرر داده': 'کدوم کالاها نسبت به ماه قبل افت فروش داشتن',
        'کدوم جنس ضرر داده': 'کدوم کالاها نسبت به ماه قبل افت فروش داشتن',
        'حقوق این ماه': 'هزینه های این ماه رو نشون بده',
        'حقوق ماه': 'هزینه های این ماه رو نشون بده'
      };
      if (fixed[n]) return fixed[n];
      var m;
      if ((m = n.match(/^پول\s+(.+?)\s+رسید$/))) return 'از ' + m[1] + ' پول بگیر';
      if ((m = n.match(/^(.+?)\s+(\d+)\s*(?:تا|جفت|عدد)\s+(.+?)\s+برد$/))) return 'فاکتور فروش بساز برای ' + m[1] + ' ' + m[2] + ' تا ' + m[3];
      if ((m = n.match(/^بارکد\s*(\d{6,})$/))) return 'موجودی ' + m[1];
      if ((m = n.match(/^مشتری جدید(?: به نام)?\s+(.+)$/))) return m[1] + ' را به عنوان مشتری ثبت کن';
      if ((m = n.match(/^(.+?) رو مشتری کن$/))) return m[1] + ' را به عنوان مشتری ثبت کن';
      if ((m = n.match(/^شماره(?:\s+تلفن|\s+موبایل)?\s+(.+?)\s+چنده?$/))) return 'اطلاعات ' + m[1] + ' را پیدا کن';
      if ((m = n.match(/^کالاهای (?:زیر|کمتر از)\s+(\d+)(?:\s*تا|\s*عدد)?$/))) return 'موجودی کالاهایی که کمتر از ' + m[1] + ' عدد دارن پیدا کن';
      return null;
    }

    var depth = 0;
    function understand(text, ctx) {
      if (depth) return orig(text, ctx);
      depth++;
      try {
        var info = orig(text, ctx);
        var alt = shopFix(text) || rewrite(text);
        if (!alt) return info;
        var info2 = orig(alt, ctx);
        if (!info2 || info2.unknown) return info;
        if (shopFix(text) || !info || info.unknown) { info2.colloquial = true; return info2; }
        var write = { create_sale: 1, create_purchase: 1, update_price: 1, adjust_stock: 1, create_expense: 1, party_payment: 1, create_product: 1, create_customer: 1 };
        if (write[info2.intent] && !write[info.intent]) { info2.colloquial = true; return info2; }
        return info;
      } finally { depth--; }
    }
    understand.__yqColloq = 1;
    U.NLU.understand = understand;

    var NAV = [
      [/فروش جدید|فاکتور جدید|ثبت فروش/, 'sale', 'فروش جدید'],
      [/فاکتورها|لیست فروش|فروش ها/, 'sales', 'فروش‌ها'],
      [/خرید جدید|ثبت خرید/, 'purchase', 'خرید جدید'],
      [/خریدها|لیست خرید/, 'purchases', 'خریدها'],
      [/کالاها|محصولات|تعریف کالا/, 'products', 'کالاها'],
      [/انبار/, 'inventory', 'انبار'],
      [/مشتری ها|مشتریان|مشتریا/, 'customers', 'مشتریان'],
      [/تامین/, 'suppliers', 'تأمین‌کنندگان'],
      [/گزارش/, 'reports', 'گزارش‌ها'],
      [/چک/, 'checks', 'چک‌ها'],
      [/دستیار|هوش مصنوعی/, 'ai', 'دستیار'],
      [/پشتیبان/, 'backup', 'پشتیبان'],
      [/تنظیمات/, 'settings', 'تنظیمات'],
      [/داشبورد|خانه/, 'dashboard', 'داشبورد'],
      [/مالی|صندوق و بانک/, 'finance', 'مالی']
    ];

    function summaryText() {
      var t = window.totals ? window.totals() : {};
      var lines = [];
      lines.push('فروش امروز: ' + (window.money ? window.money(t.revenue || 0) : (t.revenue || 0)) + ' · ' + (t.invoices || 0) + ' فاکتور');
      lines.push('سود امروز: ' + (window.money ? window.money(t.profit || 0) : (t.profit || 0)));
      try {
        if (typeof window.accountBalance === 'function') lines.push('صندوق: ' + window.money(window.accountBalance('cash')) + ' · بانک: ' + window.money(window.accountBalance('bank')));
      } catch (e) {}
      lines.push('بدهی مشتریان: ' + (window.money ? window.money(t.receivable || 0) : 0));
      lines.push('بدهی به تأمین‌کننده: ' + (window.money ? window.money(t.payable || 0) : 0));
      try {
        var day = typeof window.today === 'function' ? window.today() : new Date().toISOString().slice(0, 10);
        var spent = (db.expenses || []).filter(function (e) { return String(e.date || '').slice(0, 10) === day; }).reduce(function (a, e) { return a + (Number(e.amount) || 0); }, 0);
        lines.push('هزینهٔ امروز: ' + (window.money ? window.money(spent) : spent));
      } catch (e) {}
      lines.push('کالای کم: ' + (t.low || 0));
      var soon = (window.db && db.checks || []).filter(function (c) {
        var st = c.status || 'pending';
        if (['cashed', 'paid', 'passed', 'void', 'voided', 'returned', 'bounced'].indexOf(st) >= 0) return false;
        var due = Date.parse(c.dueDate || c.due || '');
        return due && Math.abs(due - Date.now()) < 8 * 86400000;
      }).length;
      if (soon) lines.push('چک نزدیک سررسید: ' + soon);
      lines.push('اگر کار مشخصی می‌خواهید بگویید؛ مثلاً «برای علی دو تا کفش فاکتور کن» یا «قیمت کفش را بکن ۵۰۰ هزار تومان». ثبت‌ها قبل از اجرا تأیید می‌شوند.');
      return lines.join('\n');
    }

    function isWrite(info) {
      var steps = info && info.plan && info.plan.steps || [];
      return steps.some(function (st) {
        var t = U.Tools && U.Tools.get && U.Tools.get(st.tool);
        return t && t.mode === 'write';
      });
    }

    U.chat.handle = async function (text, opts) {
      opts = opts || {};
      try {
        if (window.db && db.settings) {
          db.settings.ai = db.settings.ai || {};
          db.settings.ai.mode = 'local';
          db.settings.ai.provider = 'local';
        }
      } catch (e) {}
      var n = norm(text);
      if (!opts._part && /^(چی داره میخوابه|جنس راکد|کالای راکد|چی فروش نرفته)$/.test(n)) {
        return [{ text: 'گزارش جدا برای کالای راکد ندارم. بگویید «پرفروش‌ترین کالاها این ماه» تا معلوم شود چه جنسی کم فروخته شده.', kind: 'ai' }];
      }
      var credit = n.match(/^نسیه برای (.+)$/);
      if (!opts._part && credit) {
        return [{ text: 'برای نسیهٔ ' + credit[1] + ' کالا و تعداد را بگویید. مثلاً: برای ' + credit[1] + ' ۲ تا کفش نسیه.', kind: 'ai' }];
      }
      var buy = n.match(/^خرید از (.+)$/);
      if (!opts._part && buy && !/\d/.test(n)) {
        return [{ text: 'از ' + buy[1] + ' چه کالا و چند تا خریده شده؟ مثلاً: از ' + buy[1] + ' ۱۰ تا کفش بخر.', kind: 'ai' }];
      }
      if (!opts._part && /^(مشتری ها|مشتریان|مشتریا)$/.test(n)) {
        try { window.page = 'customers'; if (typeof window.render === 'function') window.render(); } catch (e) {}
        return [{ text: 'فهرست مشتریان باز شد.', kind: 'ai' }];
      }
      if (!opts._part && /^(خلاصه|خلاصه امروز|وضعیت|وضعیت امروز|وضعیت فروشگاه|صبح بخیر|امروز چی شد|امروز چیکار کردیم|امروز چقدر کار کردیم|دخل و خرج امروز|دخل و خرج|گزارش صبح)$/.test(n)) {
        var sm = [{ text: summaryText(), kind: 'ai' }];
        try { U.ctx.history.push({ role: 'user', text: String(text) }); U.ctx.history.push({ role: 'assistant', text: sm[0].text }); } catch (e) {}
        return sm;
      }
      var nav = n.match(/^(?:برو|ببر|باز کن|بازکن|صفحه|نشون بده)\s+(.+)$/);
      if (nav) {
        for (var i = 0; i < NAV.length; i++) {
          if (NAV[i][0].test(nav[1])) {
            try { window.page = NAV[i][1]; if (typeof window.render === 'function') window.render(); } catch (e) {}
            return [{ text: 'صفحهٔ ' + NAV[i][2] + ' باز شد.', kind: 'ai' }];
          }
        }
      }
      if (!opts._part) {
        var parts = String(text || '').split(/\s+(?:و بعد|بعدش|سپس|و همچنین)\s+/).map(function (x) { return x.trim(); }).filter(Boolean);
        if (parts.length >= 2 && parts.length <= 3) {
          var infos = parts.map(function (p) { return understand(p, U.ctx); });
          if (infos.every(function (info) { return info && !info.unknown && !info.ambiguousIntents && !isWrite(info); })) {
            var all = [];
            for (var j = 0; j < parts.length; j++) {
              var chunk = await prevHandle.call(U.chat, parts[j], Object.assign({}, opts, { _part: 1 }));
              all = all.concat(chunk || []);
            }
            return all;
          }
        }
      }
      var out = await prevHandle.call(U.chat, text, opts);
      if (!opts._part) {
        var bits = String(text || '').split(/\s+(?:و بعد|بعدش|سپس|و همچنین)\s+/).map(function (x) { return x.trim(); }).filter(Boolean);
        if (bits.length >= 2) {
          var infos = bits.map(function (p) { return understand(p, U.ctx); });
          if (infos.some(isWrite)) out = (out || []).concat([{ text: 'در هر نوبت فقط یک کارِ ثبتی پرسیده می‌شود. کار بعدی را بعد از جواب این یکی، جدا بگویید.', kind: 'ai' }]);
        }
      }
      return (out || []).map(function (m) {
        if (m && /متوجه نشدم/.test(m.text || '')) {
          return Object.assign({}, m, { text: m.text + '\n\nاگر این جمله را زیاد می‌گویید، یادم بدهید: «یاد بگیر: همین جمله یعنی فروش امروز». عملیات مالی بدون تأیید شما ثبت نمی‌شود.' });
        }
        return m;
      });
    };

    return true;
  }

  if (!boot()) {
    var n = 0;
    var t = setInterval(function () {
      if (boot() || ++n > 40) clearInterval(t);
    }, 200);
  }
})();
