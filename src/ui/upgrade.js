/**
 * UNIQUE UI upgrade — appearance, sale flow, search, reports, day close, daily backup.
 * Loaded after the main app script; overrides page renderers only.
 */
(function () {
  'use strict';

  var fix = document.createElement('style');
  fix.textContent = '.content{padding-bottom:128px}.sale-fast .modal-actions{position:sticky;bottom:92px;z-index:40;background:color-mix(in srgb,var(--surface,#fff) 94%,transparent);padding:8px 0}#yqCam{width:100%;max-height:220px;background:#111;border-radius:12px;object-fit:cover}';
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

    var debtors = (db.customers || []).filter(function (c) {
      try { return typeof customerBalance === 'function' && customerBalance(c.id) > 0; } catch (e) { return false; }
    });
    var checkLines = soon.slice(0, 3).map(function (c) {
      var who = c.partyName || c.owner || c.bank || c.number || 'چک';
      var when = c.dueDate || '';
      var amt = c.amount != null ? ' · ' + moneySafe(c.amount) : '';
      return '<div class="listrow"><span>' + esc(who) + '</span><small>' + esc(when) + esc(amt) + '</small></div>';
    }).join('');

    $('#content').innerHTML = pageHead('داشبورد', 'سود، بدهی، موجودی و چکِ نزدیک', '<button class="btn" id="yqMatrix" type="button">ماتریس</button><button class="btn primary" data-page="sale">＋ فروش جدید</button>') +
      (alerts ? '<div class="alerts" id="yqKp">' + alerts + '</div>' : '<div id="yqKp" hidden></div>') +
      '<div class="grid" id="yqAt">' +
        metricCard('سود امروز', moneySafe(t.profit), (t.invoices || 0).toLocaleString('fa-IR') + ' فاکتور', 'green') +
        metricCard('فروش امروز', moneySafe(t.revenue), 'پس از برگشت', '') +
        metricCard('بدهی مشتریان', moneySafe(t.receivable), debtors.length.toLocaleString('fa-IR') + ' نفر', 'red') +
        metricCard('کالای کم', String(low.length.toLocaleString('fa-IR')), 'زیر حداقل موجودی', 'amber') +
      '</div>' +
      (checkLines ? '<div class="card section"><div class="section-title"><h3>چک‌های هفت روز</h3></div>' + checkLines + '</div>' : '') +
      '<div class="card section yq-install"><b>میانبر صفحهٔ اصلی</b><p class="muted">در گوشی از منوی مرورگر «افزودن به صفحهٔ اصلی» را بزنید تا برنامه آفلاین و تمام‌صفحه باز شود.</p></div>';

    if ($('#yqBackupNow')) $('#yqBackupNow').onclick = function () { window.yqDownloadDailyBackup(true); };
    if ($('#yqMatrix')) $('#yqMatrix').onclick = function () { yqOpenMatrix('view'); };
    bindShell();
  };

  window.sale = function () {
    saleCart = [];
    var warehouses = (db.warehouses || []).filter(function (w) { return w.active !== false; });
    $('#content').innerHTML = pageHead('فروش جدید', 'جستجو، تعداد، ثبت.') +
      '<div class="card sale-fast">' +
      '<div id="yqHeld" class="toolbar"></div>' +
      '<div class="toolbar"><div class="searchbox"><span>⌕</span><input id="saleSearch" autofocus placeholder="نام، بارکد یا بگویید دو تا کفش"></div><button class="btn" id="scanSale" type="button">دوربین</button><button class="btn" id="voiceSale" type="button">صدا</button><button class="btn" id="yqSaleMatrix" type="button">ماتریس</button><button class="btn" id="holdSale" type="button">پارک</button></div>' +
      '<div id="saleResults"></div>' +
      '<div class="tablewrap"><table><thead><tr><th>کالا</th><th>تعداد</th><th>قیمت</th><th>جمع</th><th></th></tr></thead><tbody id="saleRows"></tbody></table></div>' +
      '<div id="saleSummary" class="section"></div>' +
      '<div id="yqCust"></div>' +
      '<div class="modal-actions"><button class="btn" id="exchangeSale" type="button">تعویض</button><button class="btn primary sale-save" id="saveSale" type="button">ثبت فروش</button></div>' +
      '<details class="sale-more"><summary>مشتری، پرداخت، تخفیف و انبار</summary>' +
      '<div class="formgrid section">' +
      '<label class="field span2">مشتری<select id="saleCustomer"><option value="">مشتری متفرقه</option>' +
      db.customers.map(function (c) { return '<option value="' + c.id + '">' + esc(c.name) + '</option>'; }).join('') +
      '</select></label>' +
      '<label class="field">پرداخت<select id="salePay"><option value="cash">نقدی</option><option value="card">کارتخوان</option><option value="bank">بانک</option><option value="credit">نسیه</option></select></label>' +
      '<label class="field">مبلغ دریافتی<input id="salePaid" type="number" min="0" value="0"></label>' +
      '<label class="field">نقد<input id="yqPayCash" type="number" min="0" value="0"></label>' +
      '<label class="field">کارت<input id="yqPayCard" type="number" min="0" value="0"></label>' +
      '<label class="field">بانک<input id="yqPayBank" type="number" min="0" value="0"></label>' +
      '<label class="field">نسیه<input id="yqPayCredit" type="number" min="0" value="0"></label>' +
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
    $('#salePay').onchange = function () { yqFillPayFromMethod(); };
    $('#saleCustomer').onchange = function () {
      saleCart.forEach(function (x) { x.price = resolveSaleUnitPrice(x.id, $('#saleCustomer').value || ''); });
      renderSaleCart();
      yqCustomerCard();
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
    $('#yqSaleMatrix').onclick = function () { yqOpenMatrix('sale'); };
    $('#voiceSale').onclick = function () { window.yqVoiceDraft('sale'); };
    $('#holdSale').onclick = function () { yqHoldSale(); };
    $('#exchangeSale').onclick = function () { yqOpenExchange(); };
    $('#saveSale').onclick = saveSale;
    yqPaintHeld();
    yqCustomerCard();
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

  function yqBeep() {
    try {
      var Ctx = window.AudioContext || window.webkitAudioContext;
      if (!Ctx) return;
      var ctx = new Ctx();
      var o = ctx.createOscillator();
      var g = ctx.createGain();
      o.frequency.value = 880;
      o.connect(g);
      g.connect(ctx.destination);
      g.gain.value = 0.06;
      o.start();
      o.stop(ctx.currentTime + 0.07);
      setTimeout(function () { try { ctx.close(); } catch (e) {} }, 200);
    } catch (e) {}
  }

  function yqFindCode(code) {
    code = String(code || '').trim();
    if (!code || typeof activeVariants !== 'function') return null;
    return activeVariants().find(function (v) {
      return String(v.barcode || '') === code || String(v.sku || '') === code;
    }) || null;
  }

  function yqTakeScan(type, code) {
    var v = yqFindCode(code);
    if (!v) { toast('بارکد پیدا نشد', true); return false; }
    yqBeep();
    if (type === 'purchase' && typeof addPurchase === 'function') addPurchase(v.id);
    else if (typeof addSale === 'function') addSale(v.id);
    toast((typeof variantName === 'function' ? variantName(v) : 'کالا') + ' به پیش‌نویس اضافه شد');
    return true;
  }

  if (typeof closeModal === 'function' && !closeModal.__yqCam) {
    var prevClose = closeModal;
    window.closeModal = function () {
      if (typeof window.yqStopScan === 'function') {
        try { window.yqStopScan(); } catch (e) {}
        window.yqStopScan = null;
      }
      return prevClose.apply(this, arguments);
    };
    window.closeModal.__yqCam = 1;
  }

  window.scanBarcode = function (type) {
    if (typeof window.yqStopScan === 'function') window.yqStopScan();
    modal(
      '<div class="modalhead"><h2>اسکن بارکد</h2><button class="close" data-close>×</button></div>' +
      '<video id="yqCam" playsinline muted autoplay></video>' +
      '<p class="muted" id="yqCamMsg">دوربین را روی بارکد بگیرید. اگر نشد، کد را بنویسید.</p>' +
      '<input id="scan" autofocus placeholder="بارکد یا SKU" autocomplete="off">' +
      '<div class="modal-actions"><button class="btn primary" id="scanOk" type="button">افزودن</button></div>'
    );
    var video = $('#yqCam');
    var msg = $('#yqCamMsg');
    var stream = null;
    var dead = false;
    var last = '';
    var lastAt = 0;
    function stop() {
      dead = true;
      if (stream) stream.getTracks().forEach(function (t) { t.stop(); });
      stream = null;
    }
    window.yqStopScan = stop;
    function apply(code) {
      code = String(code || '').trim();
      var nowMs = Date.now();
      if (!code || (code === last && nowMs - lastAt < 1400)) return;
      last = code;
      lastAt = nowMs;
      yqTakeScan(type, code);
    }
    $('#scanOk').onclick = function () { apply($('#scan').value); };
    $('#scan').onkeydown = function (e) {
      if (e.key === 'Enter') { e.preventDefault(); apply($('#scan').value); }
    };
    var Detector = window.BarcodeDetector;
    if (!Detector || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      if (msg) msg.textContent = 'این مرورگر بارکد را با دوربین نمی‌خواند. کد را تایپ کنید؛ بارکدخوان USB هم در همین جعبه کار می‌کند.';
      if (video) video.hidden = true;
      return;
    }
    navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } }).then(function (s) {
      if (dead) { s.getTracks().forEach(function (t) { t.stop(); }); return; }
      stream = s;
      video.srcObject = s;
      return video.play();
    }).then(function () {
      if (dead) return;
      var det = new Detector({ formats: ['ean_13', 'ean_8', 'code_128', 'code_39', 'qr_code', 'upc_a', 'upc_e', 'itf'] });
      (function loop() {
        if (dead || !video || !document.body.contains(video)) { stop(); return; }
        det.detect(video).then(function (codes) {
          if (codes && codes[0] && codes[0].rawValue) apply(codes[0].rawValue);
        }).catch(function () {}).then(function () {
          if (!dead) requestAnimationFrame(loop);
        });
      })();
    }).catch(function () {
      if (msg) msg.textContent = 'دوربین باز نشد. اجازهٔ دوربین را بدهید یا بارکد را تایپ کنید.';
      if (video) video.hidden = true;
    });
  };

  var QTY_WORD = { یک: 1, یه: 1, دو: 2, سه: 3, چهار: 4, پنج: 5, شش: 6, هفت: 7, هشت: 8, نه: 9, ده: 10 };

  function yqMatchVariant(phrase) {
    var tokens = String(phrase || '').toLowerCase().split(/\s+/).filter(function (t) { return t && t !== 'سایز'; });
    if (!tokens.length || typeof activeVariants !== 'function') return null;
    var full = [];
    activeVariants().forEach(function (v) {
      var blob = ((typeof variantName === 'function' ? variantName(v) : '') + ' ' + (v.color || '') + ' ' + (v.size || '') + ' ' + (v.barcode || '') + ' ' + (v.sku || '')).toLowerCase();
      var hit = 0;
      tokens.forEach(function (t) { if (blob.indexOf(t) >= 0) hit++; });
      if (hit === tokens.length) full.push(v);
    });
    if (full.length === 1) return full[0];
    if (full.length > 1) return { ambiguous: true, name: phrase };
    return null;
  }

  window.yqApplyVoiceDraft = function (text) {
    if (window.page !== 'sale' || !$('#saleRows')) {
      toast('اول صفحهٔ فروش جدید را باز کنید', true);
      return { ok: false };
    }
    var norm = (window.UAI && UAI.normalize) ? function (s) { return UAI.normalize(s); } : function (s) { return String(s || '').trim(); };
    var src = norm(text);
    var cust = '';
    var cm = src.match(/\s+برای\s+(.+)$/);
    if (cm) { cust = cm[1].trim(); src = src.slice(0, cm.index).trim(); }
    if (cust && $('#saleCustomer')) {
      var hit = (db.customers || []).find(function (c) {
        var name = norm(c.name);
        return name && (name.indexOf(cust) >= 0 || cust.indexOf(name) >= 0);
      });
      if (hit) {
        $('#saleCustomer').value = hit.id;
        if ($('#saleCustomer').onchange) $('#saleCustomer').onchange();
      } else toast('مشتری «' + cust + '» پیدا نشد؛ کالا به فاکتور متفرقه می‌رود', true);
    }
    var parts = src.split(/\s+و\s+/).map(function (s) { return s.trim(); }).filter(Boolean);
    var added = 0;
    var missed = [];
    var before = (db.sales || []).length;
    parts.forEach(function (p) {
      var qm = p.match(/^(?:(\d+)|(یک|یه|دو|سه|چهار|پنج|شش|هفت|هشت|نه|ده))\s*(?:تا|عدد|جفت)?\s+(.+)$/);
      var qty = 1;
      var name = p;
      if (qm) {
        qty = Math.max(1, qm[1] ? (parseInt(qm[1], 10) || 1) : (QTY_WORD[qm[2]] || 1));
        name = String(qm[3] || '').trim();
      }
      if (!name) return;
      var hit = yqMatchVariant(name);
      if (!hit) { missed.push(name); return; }
      if (hit.ambiguous) { missed.push(name + ' (چند کالا)'); return; }
      var have = saleCart.filter(function (x) { return x.id === hit.id; }).reduce(function (a, x) { return a + n(x.qty); }, 0);
      for (var i = 0; i < qty; i++) addSale(hit.id);
      var nowQty = saleCart.filter(function (x) { return x.id === hit.id; }).reduce(function (a, x) { return a + n(x.qty); }, 0);
      if (nowQty > have) added++;
    });
    if (missed.length) toast('پیدا نشد: ' + missed.join('، '), true);
    if (added) toast(added.toLocaleString('fa-IR') + ' قلم به پیش‌نویس اضافه شد. تا «ثبت فروش» چیزی در دفتر نوشته نمی‌شود.');
    else if (!missed.length) toast('کالایی از این جمله فهمیده نشد', true);
    return { ok: added > 0, added: added, saved: (db.sales || []).length !== before };
  };

  window.yqVoiceDraft = function () {
    var R = window.SpeechRecognition || window.webkitSpeechRecognition;
    var supported = !!(R && R.prototype && ('processLocally' in R.prototype) &&
      typeof R.available === 'function' && typeof R.install === 'function' &&
      location.protocol !== 'file:');
    function askText(message) {
      modal(
        '<div class="modalhead"><h2>پیش‌نویس گفتاری</h2><button class="close" data-close>×</button></div>' +
        '<p class="muted">' + esc(message || 'در این مرورگر موتور تشخیص گفتار فارسیِ آفلاین در دسترس نیست. صدا به سرویس آنلاین ارسال نمی‌شود؛ می‌توانید جمله را تایپ کنید.') + '</p>' +
        '<textarea id="yqSay" rows="3" placeholder="مثال: دو جفت کتونی مشکی سایز ۴۲ برای علی"></textarea>' +
        '<div class="modal-actions"><button class="btn primary" id="yqSayOk" type="button">افزودن به پیش‌نویس</button></div>'
      );
      $('#yqSayOk').onclick = function () {
        var v = $('#yqSay').value;
        closeModal();
        if (v && v.trim()) window.yqApplyVoiceDraft(v);
      };
    }
    if (!supported) {
      askText('این مرورگر قابلیت تشخیص گفتار محلیِ فارسی را ارائه نمی‌کند (در Chrome اندروید معمولاً پشتیبانی نمی‌شود). هیچ صدایی به اینترنت فرستاده نمی‌شود؛ فعلاً جمله را تایپ کنید.');
      return;
    }
    var opts = { langs: ['fa-IR'], processLocally: true };
    Promise.resolve().then(function () { return R.available(opts); }).then(function (state) {
      if (state === 'unavailable') {
        askText('بستهٔ زبان فارسی برای تشخیص آفلاین این دستگاه در دسترس نیست. هیچ مسیر آنلاین جایگزینی فعال نمی‌شود.');
        return;
      }
      function startLocal() {
        var r = new R();
        r.processLocally = true;
        r.lang = 'fa-IR';
        r.interimResults = false;
        r.continuous = false;
        r.onresult = function (e) {
          var t = '';
          for (var i = 0; i < e.results.length; i++) t += e.results[i][0].transcript;
          if (t.trim()) window.yqApplyVoiceDraft(t);
        };
        r.onerror = function (e) {
          var code = e && e.error;
          if (code === 'not-allowed') toast('دسترسی میکروفون داده نشد', true);
          else askText('تشخیص آفلاین شروع نشد (' + esc(code || 'خطای نامشخص') + '). صدا به سرویس آنلاین ارسال نمی‌شود؛ متن را وارد کنید.');
        };
        r.onend = function () {};
        try { r.start(); toast('تشخیص محلی فعال شد؛ بگویید چه چیزی و برای چه کسی. ثبت نهایی جداگانه است.'); }
        catch (err) { askText('شروع تشخیص گفتار محلی ناموفق بود. می‌توانید متن را وارد کنید.'); }
      }
      if (state === 'available') { startLocal(); return; }
      if (state === 'downloadable') {
        modal(
          '<div class="modalhead"><h2>آماده‌سازی گفتار آفلاین</h2><button class="close" data-close>×</button></div>' +
          '<p class="muted">مرورگر می‌تواند بستهٔ زبان فارسی را برای تشخیص روی همین دستگاه دریافت کند. این کار فقط با تأیید شما شروع می‌شود؛ پس از نصب، تشخیص بدون ارسال صدا به سرور انجام می‌شود.</p>' +
          '<div class="modal-actions"><button class="btn" id="yqVoiceInstall" type="button">دریافت بستهٔ فارسی</button><button class="btn" id="yqVoiceText" type="button">ورود متن</button></div>'
        );
        $('#yqVoiceText').onclick = function () { closeModal(); askText(); };
        $('#yqVoiceInstall').onclick = function () {
          var b = $('#yqVoiceInstall');
          b.disabled = true;
          b.textContent = 'در حال آماده‌سازی…';
          Promise.resolve().then(function () { return R.install(opts); }).then(function (ok) {
            closeModal();
            if (ok) startLocal();
            else askText('نصب بستهٔ فارسی انجام نشد. برای حفظ حریم خصوصی، مسیر آنلاین فعال نمی‌شود.');
          }).catch(function () {
            closeModal();
            askText('دریافت بستهٔ فارسی ناموفق بود. می‌توانید متن را وارد کنید؛ صدا به اینترنت ارسال نمی‌شود.');
          });
        };
        return;
      }
      askText('بستهٔ زبان فارسی هنوز برای تشخیص آفلاین آماده نیست. می‌توانید متن را وارد کنید؛ مسیر آنلاین فعال نمی‌شود.');
    }).catch(function () {
      askText('وضعیت موتور گفتار آفلاین قابل بررسی نیست. برای جلوگیری از ارسال صدا به سرویس آنلاین، ورودی متنی فعال شد.');
    });
  };

  if (typeof purchase === 'function' && !purchase.__yqScan) {
    var prevPurchase = purchase;
    window.purchase = function () {
      prevPurchase();
      var box = document.querySelector('#purSearch');
      var bar = box && box.closest('.toolbar');
      if (bar && !$('#scanPur')) {
        var b = document.createElement('button');
        b.type = 'button';
        b.className = 'btn';
        b.id = 'scanPur';
        b.textContent = 'دوربین';
        b.onclick = function () { scanBarcode('purchase'); };
        bar.appendChild(b);
      }
    };
    window.purchase.__yqScan = 1;
  }

  function yqSaleDue() {
    return typeof saleTotal === 'function' ? saleTotal(saleCart, n($('#saleDiscount') && $('#saleDiscount').value)) : 0;
  }

  function yqFillPayFromMethod() {
    var method = ($('#salePay') && $('#salePay').value) || 'cash';
    var total = yqSaleDue();
    ['yqPayCash', 'yqPayCard', 'yqPayBank', 'yqPayCredit'].forEach(function (id) {
      if ($('#' + id)) $('#' + id).value = 0;
    });
    var map = { cash: 'yqPayCash', card: 'yqPayCard', bank: 'yqPayBank', credit: 'yqPayCredit' };
    if ($('#' + map[method])) $('#' + map[method]).value = total;
    if ($('#salePaid')) $('#salePaid').value = method === 'credit' ? 0 : total;
  }

  function yqReadPays() {
    return {
      cash: n($('#yqPayCash') && $('#yqPayCash').value),
      card: n($('#yqPayCard') && $('#yqPayCard').value),
      bank: n($('#yqPayBank') && $('#yqPayBank').value),
      credit: n($('#yqPayCredit') && $('#yqPayCredit').value)
    };
  }

  function yqWritePays(p) {
    p = p || {};
    if ($('#yqPayCash')) $('#yqPayCash').value = p.cash || 0;
    if ($('#yqPayCard')) $('#yqPayCard').value = p.card || 0;
    if ($('#yqPayBank')) $('#yqPayBank').value = p.bank || 0;
    if ($('#yqPayCredit')) $('#yqPayCredit').value = p.credit || 0;
    if ($('#salePaid')) $('#salePaid').value = n(p.cash) + n(p.card) + n(p.bank);
  }

  function yqCustomerCard() {
    var box = $('#yqCust');
    if (!box) return;
    var id = $('#saleCustomer') && $('#saleCustomer').value;
    if (!id) { box.innerHTML = '<p class="muted">مشتری متفرقه — بدهی و سابقه ندارد.</p>'; return; }
    var bal = typeof customerBalance === 'function' ? customerBalance(id) : 0;
    var last = (db.sales || []).filter(function (s) { return s.customerId === id && s.status !== 'voided'; }).slice(-3).reverse();
    var rows = last.map(function (s) {
      return '<div class="listrow"><b>' + esc(s.number) + '</b><small>' + esc(String(s.date || '').slice(0, 10)) + '</small><em>' + moneySafe(s.total) + '</em></div>';
    }).join('') || '<p class="muted">خرید قبلی ندارد.</p>';
    box.innerHTML = '<div class="card"><b>مانده این مشتری: ' + moneySafe(bal) + '</b>' + rows + '</div>';
  }

  function yqHeldStore() {
    var fromDb = Array.isArray(db.heldTickets) ? db.heldTickets : [];
    var fromLs = [];
    try { fromLs = JSON.parse(localStorage.getItem('yq_held_v1') || '[]'); } catch (e) { fromLs = []; }
    if (!Array.isArray(fromLs)) fromLs = [];
    var map = {};
    fromDb.concat(fromLs).forEach(function (h) {
      if (h && h.id && Array.isArray(h.cart)) map[h.id] = h;
    });
    var list = Object.keys(map).map(function (k) { return map[k]; }).slice(-20);
    db.heldTickets = list;
    window.__yqHeld = list;
    return list;
  }

  function yqHeldSave() {
    var list = window.__yqHeld || [];
    db.heldTickets = list;
    try { localStorage.setItem('yq_held_v1', JSON.stringify(list)); } catch (e) {}
    if (typeof saveDB === 'function') saveDB(true);
  }

  yqHeldStore();

  function yqPaintHeld() {
    var box = $('#yqHeld');
    if (!box) return;
    box.innerHTML = window.__yqHeld.map(function (h) {
      return '<button type="button" class="btn" data-held="' + esc(h.id) + '">ادامه: ' + esc(h.label) + '</button>';
    }).join('');
    box.querySelectorAll('[data-held]').forEach(function (b) {
      b.onclick = function () { yqResumeHeld(b.getAttribute('data-held')); };
    });
  }

  function yqHoldSale() {
    if (!saleCart.length) { toast('سبد خالی است', true); return; }
    var cust = ($('#saleCustomer') && $('#saleCustomer').value) || '';
    var person = (db.customers || []).find(function (c) { return c.id === cust; });
    yqHeldStore().push({
      id: 'h' + Date.now(),
      at: new Date().toISOString(),
      cart: JSON.parse(JSON.stringify(saleCart)),
      customerId: cust,
      discount: $('#saleDiscount') ? $('#saleDiscount').value : 0,
      pays: yqReadPays(),
      label: (person ? person.name : 'متفرقه') + ' · ' + saleCart.length + ' قلم'
    });
    saleCart = [];
    if ($('#saleCustomer')) $('#saleCustomer').value = '';
    if ($('#saleDiscount')) $('#saleDiscount').value = 0;
    yqWritePays({});
    renderSaleCart();
    yqCustomerCard();
    yqPaintHeld();
    yqHeldSave();
    toast('فاکتور پارک شد و بعد از بستن صفحه هم می‌ماند. تا ثبت فروش در دفتر نوشته نمی‌شود.');
  }

  function yqResumeHeld(id) {
    if (saleCart.length) { toast('اول سبد فعلی را ثبت یا پارک کنید', true); return; }
    var i = window.__yqHeld.findIndex(function (h) { return h.id === id; });
    if (i < 0) return;
    var h = window.__yqHeld.splice(i, 1)[0];
    h.cart.forEach(function (x) { saleCart.push(x); });
    if ($('#saleCustomer')) $('#saleCustomer').value = h.customerId || '';
    if ($('#saleDiscount')) $('#saleDiscount').value = h.discount || 0;
    yqWritePays(h.pays);
    renderSaleCart();
    yqCustomerCard();
    yqPaintHeld();
    yqHeldSave();
  }

  function yqReturnable(sale) {
    var items = (sale.items || []).map(function (id) {
      return (db.saleItems || []).find(function (x) { return x.id === id; });
    }).filter(Boolean);
    return items.map(function (i) {
      var done = 0;
      (db.returns || []).forEach(function (r) {
        if (r.type !== 'sale' || r.ref !== sale.number) return;
        (r.items || []).forEach(function (it) { if (it.saleItemId === i.id) done += n(it.qty); });
      });
      return { item: i, left: Math.max(0, n(i.qty) - done) };
    }).filter(function (x) { return x.left > 0; });
  }

  function yqExchangePreview(sale, qtys) {
    var rows = yqReturnable(sale);
    var sumNet = (sale.items || []).reduce(function (a, id) {
      var it = (db.saleItems || []).find(function (x) { return x.id === id; });
      return a + (it ? n(it.total) : 0);
    }, 0);
    var refund = 0;
    rows.forEach(function (row) {
      var q = n(qtys[row.item.id]);
      if (!q) return;
      var net = n(row.item.total) - (sumNet ? n(sale.discount) * n(row.item.total) / sumNet : 0);
      refund += net * (q / n(row.item.qty));
    });
    return Math.round(refund);
  }

  window.yqPostExchange = function (ref, qtys) {
    if (!saleCart.length) throw new Error('کالای جدید در سبد نیست');
    var engine = window.__YQ_ENGINE;
    var fin = window.Fin;
    if (!engine || !engine.atomic || !engine.createSale || !fin || !fin.saleReturn) throw new Error('مسیر تعویض آماده نیست');
    var sale = (db.sales || []).find(function (s) { return s.number === ref || s.id === ref; });
    if (!sale) throw new Error('فاکتور پیدا نشد');
    if (!sale.customerId) throw new Error('تعویض فقط برای فاکتور دارای مشتری است');
    var total = yqSaleDue();
    var pay = yqReadPays();
    var entered = n(pay.cash) + n(pay.card) + n(pay.bank);
    var refund = yqExchangePreview(sale, qtys);
    var cash = entered > 0 ? n(pay.cash) : Math.max(0, total - refund);
    var card = entered > 0 ? n(pay.card) : 0;
    var bank = entered > 0 ? n(pay.bank) : 0;
    var credit = Math.round((total - cash - card - bank) * 100) / 100;
    if (credit < -0.01) throw new Error('مبلغ دریافتی از جمع کالای جدید بیشتر است');
    return engine.atomic('تعویض', function () {
      var ret = fin.saleReturn({ ref: sale.number, qtys: qtys, method: 'credit', note: 'تعویض کالا' });
      var created = engine.createSale({
        items: saleCart.map(function (x) {
          return { variantId: x.id, qty: n(x.qty), unitPrice: n(x.price), discount: n(x.discount) };
        }),
        customerId: sale.customerId,
        payments: { cash: cash, card: card, bank: bank, credit: Math.max(0, credit) },
        note: 'تعویض به‌جای ' + sale.number
      });
      return { returnRow: ret, sale: created.sale };
    });
  };

  function yqOpenExchange() {
    if (!saleCart.length) { toast('اول کالای جدید را به سبد اضافه کنید', true); return; }
    var sales = (db.sales || []).filter(function (s) { return s.status === 'confirmed' && s.customerId; }).slice(-20).reverse();
    if (!sales.length) { toast('فاکتور فروشِ دارای مشتری برای تعویض نیست', true); return; }
    modal(
      '<div class="modalhead"><h2>تعویض کالا</h2><button class="close" data-close>×</button></div>' +
      '<p class="muted">کالای برگشتی از فاکتور قبلی برمی‌گردد و سبد فعلی فاکتور جدید می‌شود. تا تأیید، چیزی ثبت نمی‌شود.</p>' +
      '<label class="field">فاکتور قبلی<select id="yqExRef">' + sales.map(function (s) {
        var who = (db.customers || []).find(function (c) { return c.id === s.customerId; });
        return '<option value="' + esc(s.number) + '">' + esc(s.number) + ' · ' + esc(who ? who.name : '') + '</option>';
      }).join('') + '</select></label><div id="yqExLines"></div><p id="yqExDiff" class="muted"></p>' +
      '<div class="modal-actions"><button class="btn primary" id="yqExOk" type="button">ثبت تعویض</button></div>'
    );
    function draw() {
      var sale = (db.sales || []).find(function (s) { return s.number === $('#yqExRef').value; });
      var rows = sale ? yqReturnable(sale) : [];
      $('#yqExLines').innerHTML = rows.map(function (row) {
        var v = variantBy(row.item.variantId);
        return '<label class="field">' + esc(v ? variantName(v) : 'کالا') + ' — حداکثر ' + row.left +
          '<input type="number" min="0" max="' + row.left + '" value="' + row.left + '" data-exq="' + esc(row.item.id) + '"></label>';
      }).join('') || '<p class="muted">قلم قابل برگشتی نمانده.</p>';
      function paint() {
        var qtys = {};
        document.querySelectorAll('[data-exq]').forEach(function (el) { qtys[el.getAttribute('data-exq')] = n(el.value); });
        var refund = sale ? yqExchangePreview(sale, qtys) : 0;
        var neu = yqSaleDue();
        var diff = neu - refund;
        $('#yqExDiff').textContent = 'برگشت حدود ' + moneySafe(refund) + ' · کالای جدید ' + moneySafe(neu) + ' · ' + (diff > 0 ? 'دریافت مابه‌التفاوت ' + moneySafe(diff) : 'باقی‌مانده به حساب مشتری ' + moneySafe(-diff));
      }
      document.querySelectorAll('[data-exq]').forEach(function (el) { el.oninput = paint; });
      paint();
    }
    $('#yqExRef').onchange = draw;
    draw();
    $('#yqExOk').onclick = function () {
      var qtys = {};
      document.querySelectorAll('[data-exq]').forEach(function (el) {
        var q = n(el.value);
        if (q > 0) qtys[el.getAttribute('data-exq')] = q;
      });
      if (!Object.keys(qtys).length) { toast('تعداد برگشت را وارد کنید', true); return; }
      try {
        var result = window.yqPostExchange($('#yqExRef').value, qtys);
        closeModal();
        saleCart = [];
        toast('تعویض ثبت شد. فاکتور جدید ' + (result.sale && result.sale.number ? result.sale.number : ''));
        page = 'sales';
        if (typeof render === 'function') render();
      } catch (err) {
        toast((err && err.message) || 'تعویض ثبت نشد', true);
      }
    };
  }

  window.yqLabelHtml = function (ids, size, copies) {
    copies = Math.max(1, Math.min(50, copies || 1));
    var shop = (db.settings && db.settings.shopName) || '';
    var items = [];
    ids.forEach(function (id) {
      var v = variantBy(id);
      if (!v) return;
      for (var i = 0; i < copies; i++) items.push(v);
    });
    var thermal = size === '40' || size === '50';
    var w = size === '50' ? '50mm' : '40mm';
    var h = '30mm';
    var css = thermal
      ? ('@page{size:' + w + ' ' + h + ';margin:0}body{margin:0}.l{width:' + w + ';height:' + h + ';box-sizing:border-box;padding:2mm;text-align:center;page-break-after:always;overflow:hidden}.bc{width:100%;height:12mm}')
      : 'body{font-family:Arial;display:grid;grid-template-columns:repeat(3,1fr);gap:10px;padding:15px}.l{border:1px solid #222;padding:8px;text-align:center}.bc{display:block;width:100%;height:46px;margin:6px 0 2px}';
    var body = items.map(function (v) {
      var svg = v.barcode && typeof yqBarcodeSvg === 'function' ? yqBarcodeSvg(v.barcode) : '';
      return '<div class="l"><div>' + esc(shop) + '</div><b>' + esc(variantName(v)) + '</b><div>' + esc(v.color || '') + ' ' + esc(v.size || '') + '</div>' +
        (svg || '') + '<div class="code">' + esc(v.barcode || '') + '</div><div>' + moneySafe(v.sellPrice) + '</div></div>';
    }).join('');
    return '<html dir="rtl"><head><title>چاپ بارکد</title><style>' + css + '.code{font-family:monospace;font-size:12px}@media print{.l{break-inside:avoid}}</style></head><body>' + body + '</body></html>';
  };

  if (typeof barcode === 'function' && !barcode.__yqLabel) {
    var prevBarcode = barcode;
    window.barcode = function () {
      prevBarcode();
      var printBtn = $('#print');
      if (!printBtn || $('#yqLabelSize')) return;
      var sel = document.createElement('select');
      sel.id = 'yqLabelSize';
      sel.innerHTML = '<option value="a4">A4 سه‌ستونه</option><option value="40">حرارتی ۴۰×۳۰</option><option value="50">حرارتی ۵۰×۳۰</option>';
      var copies = document.createElement('input');
      copies.id = 'yqLabelCopies';
      copies.type = 'number';
      copies.min = '1';
      copies.max = '50';
      copies.value = '1';
      copies.title = 'تعداد هر برچسب';
      copies.style.width = '72px';
      printBtn.before(sel, copies);
      printBtn.onclick = function () {
        var ids = Array.prototype.map.call(document.querySelectorAll('[data-b]:checked'), function (x) { return x.dataset.b; });
        if (!ids.length) { toast('حداقل یک مورد انتخاب کنید', true); return; }
        var win = open('', '_blank');
        if (!win) { toast('پنجرهٔ چاپ باز نشد', true); return; }
        win.document.write(window.yqLabelHtml(ids, sel.value, parseInt(copies.value, 10) || 1));
        win.document.close();
      };
    };
    window.barcode.__yqLabel = 1;
  }

  function yqCsv(rows) {
    var body = rows.map(function (r) {
      return r.map(function (v) { return '"' + String(v == null ? '' : v).replace(/"/g, '""') + '"'; }).join(',');
    }).join('\n');
    return '\uFEFF' + body;
  }

  function yqParseCsv(text) {
    text = String(text || '').replace(/^\uFEFF/, '').replace(/\r\n/g, '\n').replace(/\r/g, '\n');
    var rows = [], row = [], cur = '', q = false;
    for (var i = 0; i < text.length; i++) {
      var c = text[i];
      if (q) {
        if (c === '"') { if (text[i + 1] === '"') { cur += '"'; i++; } else q = false; }
        else cur += c;
      } else if (c === '"') q = true;
      else if (c === ',') { row.push(cur); cur = ''; }
      else if (c === '\n') { row.push(cur); rows.push(row); row = []; cur = ''; }
      else cur += c;
    }
    if (cur.length || row.length) { row.push(cur); rows.push(row); }
    return rows.filter(function (r) { return r.some(function (x) { return String(x).trim(); }); });
  }

  function yqPickCsv(done) {
    var input = document.createElement('input');
    input.type = 'file';
    input.accept = '.csv,text/csv';
    input.onchange = function () {
      var file = input.files && input.files[0];
      if (!file) return;
      var reader = new FileReader();
      reader.onload = function () { done(String(reader.result || '')); };
      reader.readAsText(file, 'utf-8');
    };
    input.click();
  }

  window.yqProductCsv = function () {
    var rows = [['نام', 'برند', 'دسته', 'رنگ', 'سایز', 'موجودی', 'قیمت خرید', 'قیمت فروش', 'بارکد', 'SKU']];
    activeVariants().forEach(function (v) {
      var m = modelBy(v.modelId) || {};
      rows.push([m.name || '', m.brand || '', m.category || '', v.color || '', v.size || '', v.stock, v.buyPrice, v.sellPrice, v.barcode || '', v.sku || '']);
    });
    download('کالاها-' + todaySafe() + '.csv', yqCsv(rows), 'text/csv;charset=utf-8');
  };

  window.yqImportProducts = function (text) {
    var rows = yqParseCsv(text);
    if (!rows.length) throw new Error('فایل خالی است');
    var start = /نام/.test(rows[0][0] || '') ? 1 : 0;
    var created = 0, priced = 0;
    for (var i = start; i < rows.length; i++) {
      var r = rows[i];
      var name = String(r[0] || '').trim();
      if (!name) continue;
      var brand = String(r[1] || '').trim();
      var category = String(r[2] || '').trim() || 'سایر';
      var color = String(r[3] || '').trim();
      var size = String(r[4] || '').trim();
      var stock = Math.max(0, Math.floor(n(r[5])));
      var buy = Math.max(0, n(r[6]));
      var sell = Math.max(0, n(r[7]));
      var barcode = String(r[8] || '').trim();
      var sku = String(r[9] || '').trim();
      var found = barcode ? activeVariants().find(function (v) { return String(v.barcode) === barcode; }) : null;
      if (!found && sku) found = activeVariants().find(function (v) { return String(v.sku) === sku; });
      if (!found) {
        found = activeVariants().find(function (v) {
          var m = modelBy(v.modelId) || {};
          return m.name === name && String(v.color || '') === color && String(v.size || '') === size;
        });
      }
      if (found) {
        found.buyPrice = buy;
        found.sellPrice = sell;
        priced++;
        continue;
      }
      var model = (db.models || []).find(function (m) { return m.name === name && String(m.brand || '') === brand; });
      if (!model) {
        model = { id: uid(), name: name, brand: brand, category: category, modelCode: '', description: '', active: true };
        db.models.push(model);
      }
      var variant = { id: uid(), modelId: model.id, color: color, size: size, barcode: barcode, sku: sku, buyPrice: buy, sellPrice: sell, minStock: 1, stock: 0, active: true };
      db.variants.push(variant);
      if (stock > 0 && typeof stockMove === 'function') stockMove(variant.id, stock, 'opening', 'IMPORT', buy);
      else variant.stock = stock;
      created++;
    }
    if (typeof saveDB === 'function') saveDB(true);
    return { created: created, priced: priced };
  };

  window.yqCustomerCsv = function () {
    var rows = [['نام', 'تلفن', 'یادداشت']];
    (db.customers || []).forEach(function (c) { rows.push([c.name || '', c.phone || '', c.note || '']); });
    download('مشتریان-' + todaySafe() + '.csv', yqCsv(rows), 'text/csv;charset=utf-8');
  };

  window.yqImportCustomers = function (text) {
    var rows = yqParseCsv(text);
    if (!rows.length) throw new Error('فایل خالی است');
    var start = /نام/.test(rows[0][0] || '') ? 1 : 0;
    var created = 0, updated = 0;
    for (var i = start; i < rows.length; i++) {
      var name = String(rows[i][0] || '').trim();
      if (!name) continue;
      var phone = String(rows[i][1] || '').trim();
      var note = String(rows[i][2] || '').trim();
      var found = phone ? (db.customers || []).find(function (c) { return String(c.phone || '') === phone; }) : null;
      if (!found) found = (db.customers || []).find(function (c) { return c.name === name; });
      if (found) { if (phone) found.phone = phone; if (note) found.note = note; updated++; }
      else { db.customers.push({ id: uid(), name: name, phone: phone, note: note }); created++; }
    }
    if (typeof saveDB === 'function') saveDB(true);
    return { created: created, updated: updated };
  };

  function yqOpenMatrix(mode) {
    var models = (db.models || []).filter(function (m) {
      return (db.variants || []).some(function (v) { return v.modelId === m.id && v.active !== false; });
    });
    if (!models.length) { toast('کالایی برای ماتریس نیست', true); return; }
    modal(
      '<div class="modalhead"><h2>' + (mode === 'sale' ? 'انتخاب از ماتریس' : 'ماتریس رنگ و سایز') + '</h2><button class="close" data-close>×</button></div>' +
      '<label class="field">مدل<select id="yqMxModel">' + models.map(function (m) { return '<option value="' + esc(m.id) + '">' + esc(m.name) + '</option>'; }).join('') + '</select></label>' +
      '<div id="yqMxGrid"></div><p class="muted">عدد خانه موجودی است. قرمز ناموجود است. در فروش، زدن خانه یک عدد به پیش‌نویس اضافه می‌کند.</p>'
    );
    function draw() {
      var id = $('#yqMxModel').value;
      var vs = (db.variants || []).filter(function (v) { return v.modelId === id && v.active !== false; });
      var sizes = [], colors = [];
      vs.forEach(function (v) {
        var s = String(v.size || '—'), c = String(v.color || '—');
        if (sizes.indexOf(s) < 0) sizes.push(s);
        if (colors.indexOf(c) < 0) colors.push(c);
      });
      sizes.sort(function (a, b) { return (parseFloat(a) || 0) - (parseFloat(b) || 0); });
      var html = '<div class="tablewrap"><table><thead><tr><th>سایز</th>' + colors.map(function (c) { return '<th>' + esc(c) + '</th>'; }).join('') + '</tr></thead><tbody>';
      sizes.forEach(function (sz) {
        html += '<tr><th>' + esc(sz) + '</th>';
        colors.forEach(function (co) {
          var v = vs.find(function (x) { return String(x.size || '—') === sz && String(x.color || '—') === co; });
          if (!v) html += '<td class="muted">·</td>';
          else html += '<td><button type="button" class="btn" data-mx="' + esc(v.id) + '"' + (n(v.stock) <= 0 ? ' disabled' : '') + '>' + n(v.stock) + '</button></td>';
        });
        html += '</tr>';
      });
      $('#yqMxGrid').innerHTML = html + '</tbody></table></div>';
      $('#yqMxGrid').querySelectorAll('[data-mx]').forEach(function (b) {
        b.onclick = function () {
          if (mode !== 'sale' || window.page !== 'sale') return;
          addSale(b.getAttribute('data-mx'));
          draw();
        };
      });
    }
    $('#yqMxModel').onchange = draw;
    draw();
  }

  function yqSaleLines() {
    var out = [];
    (db.sales || []).forEach(function (s) {
      if (s.status === 'voided') return;
      (s.items || []).forEach(function (id) {
        var item = typeof id === 'string' ? (db.saleItems || []).find(function (x) { return x.id === id; }) : id;
        if (!item) return;
        var cost = n(item.costTotal != null ? item.costTotal : n(item.cost) * n(item.qty));
        out.push({ sale: s, item: item, profit: n(item.total) - cost });
      });
    });
    return out;
  }

  function yqSellerName(id) {
    var u = (db.users || []).find(function (x) { return x.id === id; });
    return u && u.name ? u.name : (id ? 'کاربر حذف‌شده' : 'ثبت‌نشده');
  }

  function yqCashierRows() {
    var day = todaySafe();
    var by = {};
    (db.sales || []).forEach(function (s) {
      if (!s || s.status === 'voided') return;
      var id = s.userId || '';
      if (!by[id]) by[id] = { name: yqSellerName(id), todayCount: 0, todayTotal: 0, count: 0, total: 0 };
      by[id].count += 1;
      by[id].total += n(s.total);
      if (String(s.date || '').slice(0, 10) === day) {
        by[id].todayCount += 1;
        by[id].todayTotal += n(s.total);
      }
    });
    return Object.keys(by).map(function (k) { return by[k]; }).sort(function (a, b) { return b.todayTotal - a.todayTotal || b.total - a.total; });
  }

  window.yqShopReportCsv = function (kind) {
    var lines = yqSaleLines();
    var rows;
    if (kind === 'cashier') {
      rows = [['فروشنده', 'تعداد امروز', 'مبلغ امروز', 'تعداد کل', 'مبلغ کل']].concat(yqCashierRows().map(function (r) {
        return [r.name, r.todayCount, Math.round(r.todayTotal), r.count, Math.round(r.total)];
      }));
    } else if (kind === 'customer') {
      var byC = {};
      lines.forEach(function (x) {
        var id = x.sale.customerId || '';
        if (!byC[id]) byC[id] = { name: id ? ((db.customers || []).find(function (c) { return c.id === id; }) || {}).name || id : 'متفرقه', revenue: 0, profit: 0 };
        byC[id].revenue += n(x.item.total);
        byC[id].profit += x.profit;
      });
      rows = [['مشتری', 'فروش', 'سود']].concat(Object.keys(byC).map(function (k) { return [byC[k].name, Math.round(byC[k].revenue), Math.round(byC[k].profit)]; }));
    } else if (kind === 'dead') {
      var sold = {};
      var limit = Date.now() - 60 * 86400000;
      lines.forEach(function (x) { if (Date.parse(x.sale.date) >= limit) sold[x.item.variantId] = 1; });
      rows = [['کالا', 'موجودی']].concat(activeVariants().filter(function (v) { return n(v.stock) > 0 && !sold[v.id]; }).map(function (v) { return [variantName(v), v.stock]; }));
    } else {
      var byV = {};
      lines.forEach(function (x) {
        var id = x.item.variantId;
        if (!byV[id]) byV[id] = { name: variantName(variantBy(id)), qty: 0, revenue: 0, profit: 0 };
        byV[id].qty += n(x.item.qty);
        byV[id].revenue += n(x.item.total);
        byV[id].profit += x.profit;
      });
      rows = [['کالا', 'تعداد', 'فروش', 'سود']].concat(Object.keys(byV).map(function (k) { return [byV[k].name, byV[k].qty, Math.round(byV[k].revenue), Math.round(byV[k].profit)]; }));
    }
    download((kind === 'cashier' ? 'فروشنده-' : kind === 'customer' ? 'سود-مشتری-' : kind === 'dead' ? 'راکد-' : 'سود-کالا-') + todaySafe() + '.csv', yqCsv(rows), 'text/csv;charset=utf-8');
    return rows;
  };

  function yqAttachShopReport() {
    var host = $('#content');
    if (!host || $('#yqShopReport')) return;
    var lines = yqSaleLines();
    var byV = {};
    lines.forEach(function (x) {
      var id = x.item.variantId;
      if (!byV[id]) byV[id] = { name: variantName(variantBy(id)), profit: 0 };
      byV[id].profit += x.profit;
    });
    var top = Object.keys(byV).map(function (k) { return byV[k]; }).sort(function (a, b) { return b.profit - a.profit; }).slice(0, 5);
    var sold = {};
    var limit = Date.now() - 60 * 86400000;
    lines.forEach(function (x) { if (Date.parse(x.sale.date) >= limit) sold[x.item.variantId] = 1; });
    var dead = activeVariants().filter(function (v) { return n(v.stock) > 0 && !sold[v.id]; });
    var cashiers = yqCashierRows();
    var box = document.createElement('div');
    box.className = 'card section';
    box.id = 'yqShopReport';
    box.innerHTML = '<div class="section-title"><h3>سود کالا، سود مشتری، راکد، صندوق‌دار</h3></div>' +
      '<div class="toolbar"><button class="btn" id="yqCsvVar" type="button">اکسل سود کالا</button><button class="btn" id="yqCsvCus" type="button">اکسل سود مشتری</button><button class="btn" id="yqCsvDead" type="button">اکسل راکد</button><button class="btn" id="yqCsvUser" type="button">اکسل فروشنده</button></div>' +
      '<p>پنج کالای سودآور: ' + (top.map(function (x) { return esc(x.name) + ' ' + moneySafe(x.profit); }).join(' · ') || 'هنوز فروشی نیست') + '</p>' +
      '<p class="muted">' + dead.length.toLocaleString('fa-IR') + ' کالا بیش از ۶۰ روز فروش نداشته و هنوز موجودی دارد.</p>' +
      '<p>فروش امروز صندوق‌داران: ' + (cashiers.filter(function (r) { return r.todayCount; }).map(function (r) { return esc(r.name) + ' ' + r.todayCount.toLocaleString('fa-IR') + ' فاکتور · ' + moneySafe(r.todayTotal); }).join(' — ') || 'امروز فروشی ثبت نشده') + '</p>';
    host.appendChild(box);
    $('#yqCsvVar').onclick = function () { window.yqShopReportCsv('product'); };
    $('#yqCsvCus').onclick = function () { window.yqShopReportCsv('customer'); };
    $('#yqCsvDead').onclick = function () { window.yqShopReportCsv('dead'); };
    $('#yqCsvUser').onclick = function () { window.yqShopReportCsv('cashier'); };
  }

  if (typeof products === 'function' && !products.__yqIo) {
    var prevProducts = products;
    window.products = function () {
      prevProducts();
      var head = document.querySelector('.pagehead');
      if (head && !$('#yqProdCsv')) {
        var bar = document.createElement('div');
        bar.className = 'toolbar';
        bar.innerHTML = '<button class="btn" id="yqProdMatrix" type="button">ماتریس</button><button class="btn" id="yqProdCsv" type="button">خروجی اکسل</button><button class="btn" id="yqProdIn" type="button">ورود اکسل</button>';
        head.after(bar);
        $('#yqProdMatrix').onclick = function () { yqOpenMatrix('view'); };
        $('#yqProdCsv').onclick = function () { window.yqProductCsv(); };
        $('#yqProdIn').onclick = function () {
          yqPickCsv(function (text) {
            try {
              var r = window.yqImportProducts(text);
              toast(r.created + ' کالای جدید، ' + r.priced + ' قیمت به‌روز شد. موجودی کالاهای قبلی عوض نشد.');
              products();
            } catch (err) { toast((err && err.message) || 'ورود ناموفق بود', true); }
          });
        };
      }
    };
    window.products.__yqIo = 1;
  }

  if (typeof people === 'function' && !people.__yqIo) {
    var prevPeople = people;
    window.people = function (type) {
      prevPeople(type);
      if (type !== 'customer') return;
      var head = document.querySelector('.pagehead');
      if (!head || $('#yqCusCsv')) return;
      var bar = document.createElement('div');
      bar.className = 'toolbar';
      bar.innerHTML = '<button class="btn" id="yqCusCsv" type="button">خروجی اکسل</button><button class="btn" id="yqCusIn" type="button">ورود اکسل</button>';
      head.after(bar);
      $('#yqCusCsv').onclick = function () { window.yqCustomerCsv(); };
      $('#yqCusIn').onclick = function () {
        yqPickCsv(function (text) {
          try {
            var r = window.yqImportCustomers(text);
            toast(r.created + ' مشتری جدید، ' + r.updated + ' نفر به‌روز شد.');
            people('customer');
          } catch (err) { toast((err && err.message) || 'ورود ناموفق بود', true); }
        });
      };
    };
    window.people.__yqIo = 1;
  }

  if (typeof reports === 'function' && !reports.__yqShop) {
    var prevReports = reports;
    window.reports = function () {
      prevReports();
      yqAttachShopReport();
    };
    window.reports.__yqShop = 1;
  }

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
