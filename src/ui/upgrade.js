/**
 * UNIQUE UI upgrade — appearance, sale flow, search, reports, day close, daily backup.
 * Loaded after the main app script; overrides page renderers only.
 */
(function () {
  'use strict';

  var fix = document.createElement('style');
  fix.textContent = '.content{padding-bottom:128px}.sale-fast .modal-actions{position:sticky;bottom:92px;z-index:40;background:color-mix(in srgb,var(--surface,#fff) 94%,transparent);padding:8px 0}';
  document.head.appendChild(fix);

  try {
    var theme = localStorage.getItem('younique_theme') || localStorage.getItem('yq_theme');
    if (theme === 'dark' || theme === 'light') document.documentElement.dataset.theme = theme;
  } catch (e) {}

  function $(s) { return document.querySelector(s); }
  function moneySafe(n) { return typeof money === 'function' ? money(n) : String(n); }
  function todaySafe() { return typeof today === 'function' ? today() : new Date().toISOString().slice(0, 10); }
  function n(x) { return typeof num === 'function' ? num(x) : (Number(x) || 0); }

  function inLastDays(dateStr, days) {
    var d = String(dateStr || '').slice(0, 10);
    if (!d) return false;
    var end = new Date(todaySafe() + 'T12:00:00');
    var start = new Date(end);
    start.setDate(end.getDate() - (days - 1));
    var cur = new Date(d + 'T12:00:00');
    return cur >= start && cur <= end;
  }

  function chip(id, label, on) {
    return '<button type="button" class="chip' + (on ? ' on' : '') + '" data-chip="' + id + '">' + label + '</button>';
  }

  function installThemeButton() {
    var actions = document.querySelector('.top-actions');
    if (!actions || $('#themeBtn')) return;
    var b = document.createElement('button');
    b.type = 'button';
    b.className = 'iconbtn';
    b.id = 'themeBtn';
    b.title = 'حالت تیره';
    b.setAttribute('aria-label', 'تغییر حالت روشن و تیره');
    var dark = document.documentElement.dataset.theme === 'dark';
    b.textContent = dark ? '☀' : '☾';
    b.onclick = function () {
      var next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
      document.documentElement.dataset.theme = next;
      try { localStorage.setItem('younique_theme', next); localStorage.setItem('yq_theme', next); } catch (e) {}
      b.textContent = next === 'dark' ? '☀' : '☾';
    };
    actions.prepend(b);
  }

  if (typeof bindShell === 'function' && !bindShell.__yqUi) {
    var prevBind = bindShell;
    bindShell = function () {
      prevBind();
      installThemeButton();
    };
    bindShell.__yqUi = 1;
  }

  window.dashboard = function () {
    var t = totals();
    var cash = 0;
    try {
      if (typeof activeCashSession === 'function' && typeof cashSessionExpected === 'function') {
        var cs = activeCashSession();
        if (cs) cash = cashSessionExpected(cs);
      }
    } catch (e) {}
    if (!cash) {
      var day = todaySafe();
      cash = (db.payments || []).filter(function (p) {
        return String(p.date || '').slice(0, 10) === day && (p.account === 'cash' || !p.account);
      }).reduce(function (a, p) { return a + (p.direction === 'out' ? -n(p.amount) : n(p.amount)); }, 0);
    }
    var low = (typeof activeVariants === 'function' ? activeVariants() : []).filter(function (v) {
      return n(v.stock) <= n(v.minStock);
    });
    var soon = (db.checks || []).filter(function (c) {
      var st = c.status || 'pending';
      if (['cashed', 'paid', 'passed', 'void', 'voided', 'returned', 'bounced'].indexOf(st) >= 0) return false;
      if (!c.dueDate) return false;
      var diff = (new Date(c.dueDate + 'T12:00:00') - new Date(todaySafe() + 'T12:00:00')) / 86400000;
      return diff <= 7 && diff >= -7;
    }).slice(0, 6);

    var backupDone = false;
    try { backupDone = localStorage.getItem('yq_backup_done_' + todaySafe()) === '1'; } catch (e) {}

    var alerts = '';
    if (low.length) {
      alerts += '<button type="button" class="alert alert-amber" data-page="inventory"><b>' + low.length.toLocaleString('fa-IR') + ' کالا</b> به حداقل موجودی رسیده</button>';
    }
    if (soon.length) {
      alerts += '<button type="button" class="alert alert-red" data-page="checks"><b>' + soon.length.toLocaleString('fa-IR') + ' چک</b> سررسید نزدیک یا گذشته</button>';
    }
    if (!backupDone) {
      alerts += '<button type="button" class="alert" id="yqBackupNow"><b>پشتیبان امروز</b> هنوز دانلود نشده</button>';
    }

    $('#content').innerHTML = pageHead('داشبورد', 'چهار عدد امروز؛ جزئیات در گزارش‌ها', '<button class="btn primary" data-page="sale">＋ فروش جدید</button>') +
      (alerts ? '<div class="alerts" id="yqKp">' + alerts + '</div>' : '<div id="yqKp" hidden></div>') +
      '<div class="grid" id="yqAt">' +
        metricCard('فروش امروز', moneySafe(t.revenue), (t.invoices || 0).toLocaleString('fa-IR') + ' فاکتور', 'green') +
        metricCard('صندوق', moneySafe(cash), 'موجودی مورد انتظار', '') +
        metricCard('بدهی مشتریان', moneySafe(t.receivable), 'مانده دریافتنی', 'red') +
        metricCard('کالای کم', String(low.length.toLocaleString('fa-IR')), 'زیر حداقل موجودی', 'amber') +
      '</div>' +
      '<div class="card section yq-install"><b>میانبر صفحهٔ اصلی</b><p class="muted">در گوشی از منوی مرورگر «افزودن به صفحهٔ اصلی» را بزنید تا برنامه آفلاین و تمام‌صفحه باز شود.</p></div>';

    if ($('#yqBackupNow')) $('#yqBackupNow').onclick = function () { window.yqDownloadDailyBackup(true); };
    bindShell();
  };

  window.sale = function () {
    saleCart = [];
    var warehouses = (db.warehouses || []).filter(function (w) { return w.active !== false; });
    $('#content').innerHTML = pageHead('فروش جدید', 'جستجو، تعداد، ثبت.') +
      '<div class="card sale-fast">' +
      '<div class="toolbar"><div class="searchbox"><span>⌕</span><input id="saleSearch" autofocus placeholder="نام، بارکد یا SKU"></div><button class="btn" id="scanSale" type="button">اسکن</button></div>' +
      '<div id="saleResults"></div>' +
      '<div class="tablewrap"><table><thead><tr><th>کالا</th><th>تعداد</th><th>قیمت</th><th>جمع</th><th></th></tr></thead><tbody id="saleRows"></tbody></table></div>' +
      '<div id="saleSummary" class="section"></div>' +
      '<div class="modal-actions"><button class="btn primary sale-save" id="saveSale" type="button">ثبت فروش</button></div>' +
      '<details class="sale-more"><summary>مشتری، پرداخت، تخفیف و انبار</summary>' +
      '<div class="formgrid section">' +
      '<label class="field span2">مشتری<select id="saleCustomer"><option value="">مشتری متفرقه</option>' +
      db.customers.map(function (c) { return '<option value="' + c.id + '">' + esc(c.name) + '</option>'; }).join('') +
      '</select></label>' +
      '<label class="field">پرداخت<select id="salePay"><option value="cash">نقدی</option><option value="card">کارتخوان</option><option value="bank">بانک</option><option value="credit">نسیه</option></select></label>' +
      '<label class="field">مبلغ دریافتی<input id="salePaid" type="number" min="0" value="0"></label>' +
      '<label class="field">تخفیف فاکتور<input id="saleDiscount" type="number" value="0"></label>' +
      '<label class="field">انبار<select id="saleWarehouse">' +
      (warehouses.map(function (w) { return '<option value="' + esc(w.id) + '">' + esc(w.name) + '</option>'; }).join('') || '<option value="MAIN">انبار اصلی</option>') +
      '</select></label></div></details></div>';

    $('#saleSearch').oninput = function () { showSaleResults($('#saleSearch').value); };
    $('#saleSearch').onkeydown = function (e) {
      if (e.key === 'Enter') {
        var a = productSearch(e.target.value);
        if (a[0]) addSale(a[0].id);
      }
    };
    $('#saleDiscount').oninput = renderSaleCart;
    $('#salePay').onchange = function () {
      $('#salePaid').value = $('#salePay').value === 'credit' ? 0 : saleTotal(saleCart, n($('#saleDiscount').value));
    };
    $('#saleCustomer').onchange = function () {
      saleCart.forEach(function (x) { x.price = resolveSaleUnitPrice(x.id, $('#saleCustomer').value || ''); });
      renderSaleCart();
    };
    $('#saleWarehouse').onchange = function () {
      var wid = saleWarehouseId();
      saleCart.forEach(function (x) {
        var available = warehouseAvailable(wid, x.id);
        if (x.qty > available) x.qty = Math.max(0, Math.floor(available));
      });
      saleCart = saleCart.filter(function (x) { return x.qty > 0; });
      renderSaleCart();
    };
    $('#scanSale').onclick = function () { scanBarcode('sale'); };
    $('#saveSale').onclick = saveSale;
    renderSaleCart();
  };

  function listFilters(kind) {
    return '<div class="chips" id="' + kind + 'Chips">' +
      chip('all', 'همه', true) + chip('today', 'امروز', false) + chip('week', '۷ روز', false) +
      chip('open', 'مانده‌دار', false) + chip('settled', 'تسویه‌شده', false) +
      '</div>';
  }

  window.sales = function () {
    var all = db.sales.slice().reverse();
    $('#content').innerHTML = pageHead('فروش‌ها', 'فیلتر تاریخ و وضعیت تسویه', '<button class="btn primary" data-page="sale">＋ فروش جدید</button>') +
      '<div class="card"><div class="toolbar"><div class="searchbox"><span>⌕</span><input id="salesSearch" placeholder="شماره فاکتور یا مشتری"></div></div>' +
      listFilters('sales') +
      '<div class="tablewrap"><table><thead><tr><th>شماره</th><th>تاریخ</th><th>مشتری</th><th>مبلغ</th><th>مانده</th><th></th></tr></thead><tbody id="salesTable"></tbody></table></div></div>';
    var cmap = new Map(db.customers.map(function (c) { return [c.id, c.name || '']; }));
    var mode = 'all';
    function draw() {
      var q = ($('#salesSearch').value || '').trim();
      var rows = all.filter(function (s) {
        if (q && String(s.number).indexOf(q) < 0 && (cmap.get(s.customerId) || '').indexOf(q) < 0) return false;
        if (mode === 'today' && String(s.date).slice(0, 10) !== todaySafe()) return false;
        if (mode === 'week' && !inLastDays(s.date, 7)) return false;
        if (mode === 'open' && (!(n(s.due) > 0) || s.status === 'voided')) return false;
        if (mode === 'settled' && (n(s.due) > 0 || s.status === 'voided')) return false;
        return true;
      });
      var cut = rows.length > 200;
      var view = cut ? rows.slice(0, 200) : rows;
      $('#salesTable').innerHTML = view.map(function (s) {
        return '<tr><td>' + esc(s.number) + '</td><td>' + String(s.date).slice(0, 10) + '</td><td>' + esc(cmap.get(s.customerId) || 'متفرقه') + '</td><td>' + moneySafe(s.total) + '</td><td><span class="pill ' + (n(s.due) ? 'red' : 'green') + '">' + moneySafe(s.due) + '</span></td><td><button class="btn" data-inv="' + s.id + '">جزئیات</button></td></tr>';
      }).join('') || '<tr><td colspan="6"><div class="empty">موردی نیست.</div></td></tr>';
      if (cut) $('#salesTable').insertAdjacentHTML('beforeend', '<tr><td colspan="6"><div class="empty">۲۰۰ مورد اول. برای بقیه جستجو کنید.</div></td></tr>');
      document.querySelectorAll('[data-inv]').forEach(function (b) { b.onclick = function () { saleDetail(b.dataset.inv); }; });
    }
    $('#salesSearch').oninput = draw;
    $('#salesChips').onclick = function (e) {
      var btn = e.target.closest('[data-chip]');
      if (!btn) return;
      mode = btn.dataset.chip;
      $('#salesChips').querySelectorAll('.chip').forEach(function (c) { c.classList.toggle('on', c === btn); });
      draw();
    };
    draw();
    bindShell();
  };

  window.purchases = function () {
    var all = db.purchases.slice().reverse();
    $('#content').innerHTML = pageHead('خریدها', 'فیلتر تاریخ و مانده', '<button class="btn primary" data-page="purchase">＋ خرید جدید</button>') +
      '<div class="card"><div class="toolbar"></div>' + listFilters('pur') +
      '<div class="tablewrap"><table><thead><tr><th>شماره</th><th>تاریخ</th><th>تأمین‌کننده</th><th>مبلغ</th><th>مانده</th><th></th></tr></thead><tbody id="purTable"></tbody></table></div></div>';
    var mode = 'all';
    function draw() {
      var rows = all.filter(function (p) {
        if (mode === 'today' && String(p.date).slice(0, 10) !== todaySafe()) return false;
        if (mode === 'week' && !inLastDays(p.date, 7)) return false;
        if (mode === 'open' && !(n(p.due) > 0)) return false;
        if (mode === 'settled' && n(p.due) > 0) return false;
        return true;
      }).slice(0, 200);
      $('#purTable').innerHTML = rows.map(function (p) {
        var sup = (db.suppliers || []).find(function (s) { return s.id === p.supplierId; });
        var actions = p.status === 'voided' ? '<span class="pill red">باطل</span>' : '<button class="btn" data-pvoid="' + esc(p.number) + '">ابطال</button>';
        return '<tr><td>' + esc(p.number) + '</td><td>' + String(p.date).slice(0, 10) + '</td><td>' + esc((sup && sup.name) || 'متفرقه') + '</td><td>' + moneySafe(p.total) + '</td><td>' + moneySafe(p.due) + '</td><td>' + actions + '</td></tr>';
      }).join('') || '<tr><td colspan="6"><div class="empty">موردی نیست.</div></td></tr>';
      document.querySelectorAll('[data-pvoid]').forEach(function (b) {
        b.onclick = function () {
          var r = prompt('دلیل ابطال؟');
          if (!r) return;
          try { Fin.voidPurchase(b.dataset.pvoid, r); toast('خرید باطل شد'); purchases(); }
          catch (err) { toast(err.message, true); }
        };
      });
    }
    $('#purChips').onclick = function (e) {
      var btn = e.target.closest('[data-chip]');
      if (!btn) return;
      mode = btn.dataset.chip;
      $('#purChips').querySelectorAll('.chip').forEach(function (c) { c.classList.toggle('on', c === btn); });
      draw();
    };
    draw();
    bindShell();
  };

  window.reports = function () {
    var sales = db.sales.filter(function (x) { return x.status === 'confirmed'; });
    var purchases = db.purchases.filter(function (x) { return x.status === 'confirmed'; });
    var rev = sales.reduce(function (a, x) { return a + n(x.total); }, 0);
    var buy = purchases.reduce(function (a, x) { return a + n(x.total); }, 0);
    var profit = sales.reduce(function (a, x) { return a + n(x.profit); }, 0);
    var by = new Map();
    sales.forEach(function (s) {
      (s.items || []).forEach(function (id) {
        var it = (db.saleItems || []).find(function (x) { return x.id === id; });
        if (!it) return;
        var row = by.get(it.variantId) || { name: variantName(variantBy(it.variantId)), qty: 0, revenue: 0, cost: 0 };
        row.qty += n(it.qty);
        row.revenue += n(it.total);
        row.cost += n(it.costTotal) || n(it.cost) * n(it.qty);
        by.set(it.variantId, row);
      });
    });
    var rows = Array.from(by.values()).map(function (r) {
      r.profit = r.revenue - r.cost;
      return r;
    }).sort(function (a, b) { return b.profit - a.profit; }).slice(0, 40);

    $('#content').innerHTML = pageHead('گزارش‌ها', 'سود هر کالا بر اساس بهای تمام‌شدهٔ ثبت‌شده', '<button class="btn" id="csv" type="button">خروجی CSV</button>') +
      '<div class="grid">' +
      metricCard('فروش کل', moneySafe(rev), sales.length.toLocaleString('fa-IR') + ' فاکتور', 'green') +
      metricCard('خرید کل', moneySafe(buy), purchases.length.toLocaleString('fa-IR') + ' فاکتور') +
      metricCard('سود ناخالص', moneySafe(profit), 'جمع فاکتورها', 'green') +
      metricCard('ارزش موجودی', moneySafe((typeof activeVariants === 'function' ? activeVariants() : []).reduce(function (a, v) { return a + n(v.stock) * n(v.buyPrice); }, 0)), 'قیمت خرید', 'amber') +
      '</div>' +
      '<div class="card section"><div class="section-title"><h3>سود به تفکیک کالا</h3></div><div class="tablewrap"><table><thead><tr><th>کالا</th><th>تعداد</th><th>فروش</th><th>بهای تمام‌شده</th><th>سود</th></tr></thead><tbody>' +
      (rows.map(function (r) {
        return '<tr><td>' + esc(r.name) + '</td><td>' + r.qty.toLocaleString('fa-IR') + '</td><td>' + moneySafe(r.revenue) + '</td><td>' + moneySafe(r.cost) + '</td><td><span class="pill ' + (r.profit >= 0 ? 'green' : 'red') + '">' + moneySafe(r.profit) + '</span></td></tr>';
      }).join('') || '<tr><td colspan="5"><div class="empty">فروش تأییدشده‌ای نیست.</div></td></tr>') +
      '</tbody></table></div></div>';

    $('#csv').onclick = function () {
      var lines = [['کالا', 'تعداد', 'فروش', 'بها', 'سود']].concat(rows.map(function (r) { return [r.name, r.qty, r.revenue, r.cost, r.profit]; }));
      download('سود-کالا-' + todaySafe() + '.csv', lines.map(function (r) { return r.map(function (v) { return '"' + String(v).replaceAll('"', '""') + '"'; }).join(','); }).join('\n'), 'text/csv;charset=utf-8');
    };
    bindShell();
  };

  window.globalSearch = function () {
    modal('<div class="modalhead"><h2>جستجو</h2><button class="close" data-close>×</button></div>' +
      '<input id="gq" placeholder="کالا، مشتری، شماره فاکتور فروش یا خرید" autofocus>' +
      '<div id="glist" class="rowlist section"></div>');
    function paint() {
      var q = ($('#gq').value || '').trim();
      var ql = q.toLowerCase();
      if (!q) { $('#glist').innerHTML = '<div class="empty">عبارتی بنویسید.</div>'; return; }
      var html = '';
      productSearch(q).slice(0, 8).forEach(function (v) {
        html += '<button type="button" class="listrow" data-go="sale" data-add="' + v.id + '"><div class="grow"><b>' + esc(variantName(v)) + '</b><small>کالا · موجودی ' + n(v.stock).toLocaleString('fa-IR') + '</small></div></button>';
      });
      (db.customers || []).filter(function (c) { return (c.name || '').toLowerCase().indexOf(ql) >= 0 || String(c.phone || '').indexOf(q) >= 0; }).slice(0, 5).forEach(function (c) {
        html += '<button type="button" class="listrow" data-go="customers"><div class="grow"><b>' + esc(c.name) + '</b><small>مشتری</small></div></button>';
      });
      (db.sales || []).filter(function (s) { return String(s.number).indexOf(q) >= 0; }).slice(0, 5).forEach(function (s) {
        html += '<button type="button" class="listrow" data-sale="' + s.id + '"><div class="grow"><b>' + esc(s.number) + '</b><small>فاکتور فروش · ' + moneySafe(s.total) + '</small></div></button>';
      });
      (db.purchases || []).filter(function (p) { return String(p.number).indexOf(q) >= 0; }).slice(0, 5).forEach(function (p) {
        html += '<button type="button" class="listrow" data-go="purchases"><div class="grow"><b>' + esc(p.number) + '</b><small>فاکتور خرید</small></div></button>';
      });
      $('#glist').innerHTML = html || '<div class="empty">چیزی پیدا نشد.</div>';
      $('#glist').querySelectorAll('[data-go]').forEach(function (b) {
        b.onclick = function () {
          closeModal();
          page = b.dataset.go;
          render();
          if (b.dataset.add && typeof addSale === 'function') setTimeout(function () { addSale(b.dataset.add); }, 30);
        };
      });
      $('#glist').querySelectorAll('[data-sale]').forEach(function (b) {
        b.onclick = function () { closeModal(); saleDetail(b.dataset.sale); };
      });
    }
    $('#gq').oninput = paint;
    $('#gq').focus();
    paint();
  };

  function expectedCash() {
    try {
      if (typeof activeCashSession === 'function' && typeof cashSessionExpected === 'function') {
        var cs = activeCashSession();
        if (cs) return cashSessionExpected(cs);
      }
    } catch (e) {}
    return (db.payments || []).filter(function (p) { return p.account === 'cash' || !p.account; }).reduce(function (a, p) {
      return a + (p.direction === 'out' ? -n(p.amount) : n(p.amount));
    }, 0);
  }

  var prevFinance = window.finance;
  window.finance = function () {
    if (typeof prevFinance === 'function') prevFinance();
    var exp = expectedCash();
    var host = $('#content');
    if (!host || $('#dayClose')) return;
    host.insertAdjacentHTML('beforeend',
      '<div class="card section" id="dayClose"><div class="section-title"><h3>بستن روز صندوق</h3></div>' +
      '<p class="muted">مبلغ شمارش‌شده را با موجودی سیستم مقایسه کنید. این ثبت فقط یادداشت روز است و سند حسابداری جدا نمی‌سازد.</p>' +
      '<div class="formgrid"><label class="field">موجودی سیستم<input value="' + exp + '" readonly></label>' +
      '<label class="field">شمارش‌شده<input id="countedCash" type="number" min="0" placeholder="ریال"></label></div>' +
      '<div id="closeDiff" class="section"></div><button class="btn primary" id="saveClose" type="button">ثبت شمارش</button></div>');
    function diff() {
      var c = n($('#countedCash').value);
      var d = c - exp;
      $('#closeDiff').innerHTML = '<b>اختلاف: </b><span class="pill ' + (d === 0 ? 'green' : 'red') + '">' + moneySafe(d) + '</span>';
    }
    $('#countedCash').oninput = diff;
    $('#saveClose').onclick = function () {
      db.pro = db.pro || {};
      db.pro.dayCloses = db.pro.dayCloses || [];
      db.pro.dayCloses.push({ date: now(), expected: exp, counted: n($('#countedCash').value) });
      saveDB(true);
      toast('شمارش صندوق ثبت شد');
      diff();
    };
  };

  window.yqShowReceipt = function (s) {
    if (!s) return;
    var items = (s.items || []).map(function (i) { return db.saleItems.find(function (x) { return x.id === i; }); }).filter(Boolean);
    var cust = (db.customers || []).find(function (c) { return c.id === s.customerId; });
    modal('<div class="receipt" id="receiptSheet">' +
      '<div class="modalhead"><h2>رسید ' + esc(s.number) + '</h2><button class="close" data-close>×</button></div>' +
      '<p class="muted">' + esc((db.settings && db.settings.shopName) || '') + ' · ' + String(s.date).slice(0, 16).replace('T', ' ') + '</p>' +
      '<p>' + esc((cust && cust.name) || 'مشتری متفرقه') + '</p>' +
      '<div class="tablewrap"><table><thead><tr><th>کالا</th><th>تعداد</th><th>مبلغ</th></tr></thead><tbody>' +
      items.map(function (i) { return '<tr><td>' + esc(variantName(variantBy(i.variantId))) + '</td><td>' + i.qty + '</td><td>' + moneySafe(i.total) + '</td></tr>'; }).join('') +
      '</tbody></table></div>' +
      '<p><b>جمع ' + moneySafe(s.total) + '</b> · پرداخت ' + moneySafe(s.paid) + ' · مانده ' + moneySafe(s.due) + '</p>' +
      '<div class="modal-actions"><button class="btn" id="receiptPrint" type="button">چاپ</button><button class="btn primary" id="receiptShare" type="button">اشتراک‌گذاری</button></div></div>');
    $('#receiptPrint').onclick = function () { window.print(); };
    $('#receiptShare').onclick = function () {
      var text = 'رسید ' + s.number + '\nجمع ' + s.total + '\nپرداخت ' + s.paid;
      if (navigator.share) navigator.share({ title: 'رسید ' + s.number, text: text }).catch(function () {});
      else if (navigator.clipboard) navigator.clipboard.writeText(text).then(function () { toast('متن رسید کپی شد'); });
    };
  };

  function hookSave() {
    if (typeof window.saveSale !== 'function' || window.saveSale.__yqReceipt) return;
    var orig = window.saveSale;
    var wrapped = function () {
      var last = (db.sales && db.sales.length) ? db.sales[db.sales.length - 1].id : null;
      var result = orig.apply(this, arguments);
      setTimeout(function () {
        try {
          var sales = db.sales || [];
          var newest = null;
          if (result && result.number && result.items) newest = result;
          else if (result && result.sale && result.sale.number) newest = result.sale;
          else if (sales.length && sales[sales.length - 1].id !== last) newest = sales[sales.length - 1];
          if (newest) window.yqShowReceipt(newest);
        } catch (e) {}
      }, 40);
      return result;
    };
    wrapped.__yqReceipt = 1;
    window.saveSale = wrapped;
  }

  window.yqDownloadDailyBackup = function (force) {
    try {
      var key = 'yq_backup_done_' + todaySafe();
      if (!force && localStorage.getItem(key) === '1') return;
      if (typeof exportData !== 'function' || typeof download !== 'function') return;
      download('unique-pro-backup-' + todaySafe() + '.json', exportData());
      localStorage.setItem(key, '1');
      toast('پشتیبان امروز دانلود شد');
      if (page === 'dashboard' && typeof render === 'function') render();
    } catch (err) {
      toast((err && err.message) || 'پشتیبان ساخته نشد', true);
    }
  };

  hookSave();
  setTimeout(function () {
    hookSave();
    try {
      if ((localStorage.getItem('younique_theme') || localStorage.getItem('yq_theme')) === 'dark') document.documentElement.dataset.theme = 'dark';
    } catch (e) {}
    try { if (typeof render === 'function') render(); } catch (e) {}
    installThemeButton();
  }, 0);
  setTimeout(hookSave, 1600);
})();
