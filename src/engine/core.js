/**
 * UNIQUE Engine Core v1.2
 */
'use strict';
function createEngine(db, h) {
  if (!db) throw new Error('db is required');
  if (!h) throw new Error('helpers are required');
  const {
    uid, now, num,
    roundMoney = (x) => Math.round(num(x) * 100) / 100,
    cloneDB, normalize, saveDB = () => true, invalidate = () => {},
    audit = () => {}, variantBy, variantName = (v) => v?.name || v?.id || '?',
    nextNumber, paymentAccount = (m) => m === 'card' ? 'card' : m === 'bank' ? 'bank' : 'cash',
  } = h;

  function postJournal(ref, desc, lines, meta = {}) {
    const clean = lines.map(x => ({ ...x, debit: roundMoney(x.debit || 0), credit: roundMoney(x.credit || 0) })).filter(x => x.debit || x.credit);
    const debit = roundMoney(clean.reduce((a, x) => a + x.debit, 0));
    const credit = roundMoney(clean.reduce((a, x) => a + x.credit, 0));
    if (Math.abs(debit - credit) > 0.01) throw new Error('سند حسابداری نامتوازن است: ' + debit + ' ≠ ' + credit);
    const entry = { id: uid(), date: now(), ref, description: desc, lines: clean, debit, credit, ...meta };
    db.journal = db.journal || []; db.journal.push(entry); invalidate(); return entry;
  }


  function ensureCostingState() {
    db.costing = db.costing || { method: 'weighted_average' };
    db.costLayers = db.costLayers || {};
  }
  function costingMethod() {
    ensureCostingState();
    return db.costing.method === 'fifo' ? 'fifo' : 'weighted_average';
  }
  function layerList(id) {
    ensureCostingState();
    return db.costLayers[id] || (db.costLayers[id] = []);
  }
  function layerVal(l) {
    return l.value !== undefined && l.value !== null
      ? num(l.value)
      : roundMoney(Math.max(0, num(l.remaining)) * Math.max(0, num(l.unitCost)));
  }
  function layerValue(id) {
    return roundMoney(layerList(id).reduce((a, l) => a + layerVal(l), 0));
  }
  function addCostLayer(variantId, qty, unitCost, source, ref, totalValue) {
    ensureCostingState();
    const q = Math.max(0, num(qty));
    if (!q) return;
    const cost = Math.max(0, num(unitCost));
    const value = totalValue !== undefined && totalValue !== null
      ? roundMoney(Math.max(0, num(totalValue)))
      : roundMoney(q * cost);
    if (costingMethod() === 'weighted_average') {
      const v = variantBy(variantId);
      const oldQty = Math.max(0, num(v && v.stock));
      const oldValue = layerValue(variantId);
      const newQty = oldQty + q;
      const newValue = roundMoney(oldValue + value);
      db.costLayers[variantId] = [{
        id: uid(), date: now(), qty: newQty, remaining: newQty,
        unitCost: newQty ? newValue / newQty : 0, value: newValue,
        source: 'weighted_balance', ref: ref || ''
      }];
      return;
    }
    layerList(variantId).push({
      id: uid(), date: now(), qty: q, remaining: q,
      unitCost: value / q, value, source: source || 'purchase', ref: ref || ''
    });
  }
  function consumeCost(variantId, qty, fallbackCost) {
    ensureCostingState();
    let need = Math.max(0, num(qty));
    let cost = 0;
    const layers = layerList(variantId);
    if (costingMethod() === 'weighted_average') {
      const unit = layers[0] ? num(layers[0].unitCost) : num(fallbackCost);
      const value = roundMoney(need * unit);
      if (layers[0]) {
        layers[0].remaining = Math.max(0, num(layers[0].remaining) - need);
        layers[0].qty = layers[0].remaining;
        layers[0].value = roundMoney(layers[0].remaining * unit);
      }
      return { unitCost: unit, cost: value };
    }
    // FIFO
    for (const layer of layers) {
      if (need <= 0) break;
      const take = Math.min(need, Math.max(0, num(layer.remaining)));
      if (take <= 0) continue;
      const part = roundMoney(take * num(layer.unitCost));
      cost = roundMoney(cost + part);
      layer.remaining = roundMoney(num(layer.remaining) - take);
      layer.value = roundMoney(layer.remaining * num(layer.unitCost));
      need = roundMoney(need - take);
    }
    if (need > 0) {
      const unit = num(fallbackCost);
      cost = roundMoney(cost + need * unit);
    }
    db.costLayers[variantId] = layers.filter(l => num(l.remaining) > 0.0001);
    const unitCost = qty ? roundMoney(cost / num(qty)) : 0;
    return { unitCost, cost };
  }

  function ensureWarehouseState() {
    db.warehouses = Array.isArray(db.warehouses) && db.warehouses.length
      ? db.warehouses
      : [{ id: 'MAIN', name: 'انبار اصلی', active: true }];
    db.warehouseStocks = db.warehouseStocks && typeof db.warehouseStocks === 'object' ? db.warehouseStocks : {};
  }

  function stockMove(variantId, qty, type, ref, cost = 0, warehouseId, totalValue) {
    const v = variantBy(variantId); if (!v) throw new Error('تنوع کالا پیدا نشد');
    const q = num(qty);
    const next = num(v.stock) + q;
    if (next < 0) throw new Error('موجودی «' + variantName(v) + '» کافی نیست');

    // Keep warehouseStocks in sync (required by assertNewTransactionState)
    ensureWarehouseState();
    const defaultWh = db.warehouses.find(w => w.id === 'MAIN') || db.warehouses[0];
    const targetWh = db.warehouses.find(w => w.id === warehouseId && w.active !== false) || defaultWh;
    db.warehouseStocks[targetWh.id] = db.warehouseStocks[targetWh.id] || {};
    if (db.warehouseStocks[targetWh.id][variantId] === undefined) {
      db.warehouseStocks[targetWh.id][variantId] = targetWh.id === 'MAIN' ? Math.max(0, num(v.stock)) : 0;
    }
    const targetQty = num(db.warehouseStocks[targetWh.id][variantId]);
    if (q < 0 && type !== 'stocktake' && targetQty + q < -0.0001) {
      throw new Error('موجودی انبار «' + targetWh.name + '» برای این گردش کافی نیست.');
    }
    db.warehouseStocks[targetWh.id][variantId] = targetQty + q;

    let actualCost = Math.max(0, num(cost));
    let totalCost = 0;
    if (q > 0) {
      const addedValue = totalValue !== undefined && totalValue !== null
        ? roundMoney(Math.max(0, num(totalValue)))
        : roundMoney(q * (actualCost || num(v.buyPrice)));
      addCostLayer(variantId, q, actualCost || num(v.buyPrice), type, ref, addedValue);
      totalCost = addedValue;
      actualCost = q ? addedValue / q : 0;
      // for weighted avg buyPrice is updated inside addCostLayer path via stock later
    } else if (q < 0) {
      const info = consumeCost(variantId, Math.abs(q), actualCost || num(v.buyPrice));
      actualCost = info.unitCost;
      totalCost = info.cost;
    }

    v.stock = next;
    if (q > 0 && costingMethod() === 'weighted_average') {
      const lv = layerValue(variantId);
      v.buyPrice = next > 0 ? roundMoney(lv / next) : 0;
    } else if (q < 0 && costingMethod() === 'weighted_average') {
      const lv = layerValue(variantId);
      v.buyPrice = next > 0 ? roundMoney(lv / next) : num(v.buyPrice);
    }

    db.stockMoves = db.stockMoves || [];
    db.stockMoves.push({
      id: uid(), date: now(), variantId, qty: q, type, ref,
      cost: actualCost, totalCost, warehouseId: targetWh.id
    });
    invalidate();
    return { unitCost: actualCost, totalCost };
  }

  function accountBalance(account, partyType = '', partyId = '') {
    let n = 0;
    for (const j of (db.journal || [])) for (const l of (j.lines || [])) {
      if (l.account !== account) continue;
      if (partyType && l.partyType !== partyType) continue;
      if (partyId && l.partyId !== partyId) continue;
      n += num(l.debit) - num(l.credit);
    }
    return n;
  }

  function atomic(label, fn) {
    if (typeof cloneDB !== 'function' || typeof normalize !== 'function') return fn();
    const before = cloneDB();
    try {
      const result = fn();
      if (saveDB(true) === false) throw new Error('ذخیره اطلاعات ناموفق بود');
      return result;
    } catch (e) {
      const restored = normalize(before);
      Object.keys(db).forEach(k => delete db[k]); Object.assign(db, restored);
      saveDB(true); audit('rollback', label, e?.message || String(e)); throw e;
    }
  }

  function cashMove(sessionId, amount, type, ref, note) {
    const delta = num(amount);
    db.cashMovements = db.cashMovements || [];
    db.cashMovements.push({ id: uid(), date: now(), sessionId, amount: Math.abs(delta), delta, type, ref: ref || '', note: note || '' });
  }

  function activeCashSession() { return (db.cashSessions || []).find(x => x.status === 'open') || null; }
  function cashSessionExpected(s) {
    if (!s) return 0;
    const deltaSum = (db.cashMovements || []).filter(m => m.sessionId === s.id).reduce((a, m) => a + num(m.delta), 0);
    return roundMoney(num(s.openingCash) + deltaSum);
  }

  function openCashSession(amount, note = '', source = 'local') {
    if (activeCashSession()) throw new Error('صندوق دیگری باز است');
    const openingCash = roundMoney(num(amount));
    if (!Number.isFinite(openingCash) || openingCash < 0) throw new Error('موجودی اولیه نامعتبر است');
    db.cashSessions = db.cashSessions || [];
    const first = db.cashSessions.length === 0;
    const number = 'CS-' + Date.now().toString().slice(-6);
    const row = { id: uid(), number, date: now(), status: 'open', openingCash, opening: openingCash, openedBy: source === 'ai' ? 'ai' : 'local', openedAt: now(), note: String(note || '').trim() };
    db.cashSessions.push(row);
    if (first && openingCash > 0 && Math.abs(accountBalance('cash')) < 0.005) {
      postJournal(number + '-OPENING', 'ثبت موجودی افتتاحیه صندوق', [
        { account: 'cash', debit: openingCash, credit: 0 }, { account: 'equity', debit: 0, credit: openingCash }
      ], { cashSessionId: row.id, entryType: 'cash_opening' });
    }
    audit('باز کردن صندوق', number, String(openingCash)); saveDB(true); return row;
  }

  function closeCashSession(actualAmount, note = '', source = 'local') {
    const s = activeCashSession(); if (!s) throw new Error('صندوق بازی وجود ندارد');
    const expected = cashSessionExpected(s), actual = roundMoney(num(actualAmount)), diff = roundMoney(actual - expected), n = String(note || '').trim();
    if (!Number.isFinite(actual) || actual < 0) throw new Error('موجودی شمارش‌شده نامعتبر است');
    if (Math.abs(diff) >= 0.005 && !n) throw new Error('برای اختلاف صندوق، شرح وارد کنید');
    if (Math.abs(diff) >= 0.005) {
      const amount = Math.abs(diff);
      const lines = diff < 0
        ? [{ account: 'cashShortage', debit: amount, credit: 0 }, { account: 'cash', debit: 0, credit: amount }]
        : [{ account: 'cash', debit: amount, credit: 0 }, { account: 'cashOverage', debit: 0, credit: amount }];
      postJournal(s.number + '-CASH-VARIANCE', diff < 0 ? 'ثبت کسری صندوق' : 'ثبت اضافه صندوق', lines, { cashSessionId: s.id, entryType: 'cash_variance', variance: diff });
    }
    s.status = 'closed'; s.closedAt = now(); s.closing = actual; s.actualCash = actual; s.expectedCash = expected; s.difference = diff; s.variance = diff; s.closeNote = n;
    audit('بستن صندوق', s.number, 'diff ' + diff); saveDB(true);
    return { number: s.number, expected, actual, diff };
  }

  function createSale(payload) {
    const { items = [], customerId = '', payment = 'cash', paid: rawPaid = 0, discount = 0, note = '', warehouseId = '' } = payload;
    if (!items.length) throw new Error('فاکتور خالی است');
    ensureWarehouseState();
    const defaultWarehouse = db.warehouses.find(function (w) { return w.id === 'MAIN' && w.active !== false; }) || db.warehouses.find(function (w) { return w.active !== false; });
    const selectedWarehouseId = warehouseId || (defaultWarehouse && defaultWarehouse.id);
    const selectedWarehouse = db.warehouses.find(function (w) { return w.id === selectedWarehouseId && w.active !== false; });
    if (!selectedWarehouse) throw new Error('انبار مبدأ معتبر نیست');
    const selectedWarehouseStocks = db.warehouseStocks[selectedWarehouseId] || {};
    const saleItems = []; let cost = 0, subTotal = 0;
    for (const x of items) {
      const v = variantBy(x.variantId); if (!v) throw new Error('یکی از کالاها پیدا نشد');
      const qty = num(x.qty), unitPrice = num(x.unitPrice), itemDiscount = num(x.discount || 0);
      if (!Number.isFinite(qty) || qty <= 0) throw new Error('تعداد باید مثبت باشد');
      if (!Number.isInteger(qty)) throw new Error('تعداد باید عدد صحیح باشد');
      if (!Number.isFinite(unitPrice) || unitPrice < 0) throw new Error('قیمت فروش نامعتبر است');
      if (!Number.isFinite(itemDiscount) || itemDiscount < 0 || itemDiscount > qty * unitPrice) throw new Error('تخفیف ردیف نامعتبر است');
      const warehouseQty = selectedWarehouseStocks[x.variantId] !== undefined
        ? Math.max(0, num(selectedWarehouseStocks[x.variantId]))
        : (selectedWarehouseId === 'MAIN' ? Math.max(0, num(v.stock)) : 0);
      if (qty > warehouseQty) throw new Error('موجودی کالا در انبار انتخاب‌شده کافی نیست: ' + variantName(v));
      const lineTotal = roundMoney(qty * unitPrice - itemDiscount);
      saleItems.push({ id: uid(), variantId: x.variantId, qty, unitPrice, discount: itemDiscount, total: lineTotal, cost: num(v.buyPrice || 0) });
      cost += qty * num(v.buyPrice || 0); subTotal += lineTotal;
    }
    const invoiceDiscount = num(discount);
    if (!Number.isFinite(invoiceDiscount) || invoiceDiscount < 0 || invoiceDiscount > subTotal) throw new Error('تخفیف فاکتور نامعتبر است');
    let netTotal = roundMoney(subTotal - invoiceDiscount);
    if (netTotal <= 0) throw new Error('مبلغ فاکتور معتبر نیست');

    // VAT from taxProfile (closer to original app)
    const tax = db.taxProfile || {};
    const vatRate = tax.enabled ? num(tax.vatRate) : 0;
    const vatMode = tax.vatMode || 'exclusive';
    let vat = 0;
    let total = netTotal;
    if (vatRate > 0) {
      if (vatMode === 'inclusive') {
        vat = roundMoney(netTotal - netTotal / (1 + vatRate / 100));
        total = netTotal;
        netTotal = roundMoney(total - vat);
      } else {
        vat = roundMoney(netTotal * vatRate / 100);
        total = roundMoney(netTotal + vat);
      }
    }

    let paid;
    let due;
    let payMethod = payment;
    let splitRows = null;
    if (payload.payments && typeof payload.payments === 'object') {
      const cash = roundMoney(num(payload.payments.cash));
      const card = roundMoney(num(payload.payments.card));
      const bank = roundMoney(num(payload.payments.bank));
      const credit = roundMoney(num(payload.payments.credit));
      [cash, card, bank, credit].forEach(function (a) { if (a < 0) throw new Error('مبلغ پرداخت نامعتبر است'); });
      paid = roundMoney(cash + card + bank);
      due = credit;
      if (Math.abs(roundMoney(paid + due) - total) > 0.01) throw new Error('پرداخت و نسیه باید دقیقاً برابر جمع فاکتور باشد');
      if (due > 0 && !customerId) throw new Error('برای نسیه باید مشتری انتخاب شود');
      splitRows = [
        { account: 'cash', amount: cash },
        { account: 'card', amount: card },
        { account: 'bank', amount: bank },
        { account: 'credit', amount: credit }
      ].filter(function (x) { return x.amount > 0; });
      payMethod = splitRows.length > 1 ? 'mixed' : (splitRows[0] ? splitRows[0].account : 'credit');
    } else {
      paid = Math.min(total, Math.max(0, num(rawPaid)));
      due = roundMoney(total - paid);
      if (due > 0 && !customerId) throw new Error('برای ایجاد مانده باید مشتری انتخاب شود');
      if (payment === 'credit' && (!customerId || paid >= total)) throw new Error('برای نسیه باید مشتری انتخاب شود و مانده باقی بماند');
    }
    const cashReceived = splitRows
      ? roundMoney(num(payload.payments.cash))
      : (paid > 0 && paymentAccount(payment) === 'cash' ? paid : 0);
    if (cashReceived > 0 && !activeCashSession()) throw new Error('برای دریافت وجه نقد ابتدا صندوق را باز کنید');
    const no = typeof nextNumber === 'function' ? nextNumber('sale') : ('S-' + Date.now());
    const profit = roundMoney(saleItems.reduce((a, i) => a + i.total - i.qty * i.cost, 0) - num(discount));
    const seller = db.currentUserId || (Array.isArray(db.users) && db.users[0] && db.users[0].id) || '';
    const sale = { id: uid(), number: no, date: now(), customerId: customerId || '', userId: seller, warehouseId: selectedWarehouseId, status: 'confirmed', payment: payMethod, total, paid, due, discount: num(discount), profit, vat, vatMode, items: saleItems.map(i => i.id), note: note || '', payments: splitRows || (paid > 0 ? [{ account: paymentAccount(payment), amount: paid }] : []) };
    db.sales = db.sales || []; db.saleItems = db.saleItems || []; db.payments = db.payments || [];
    db.sales.push(sale);
    let actualCogs = 0;
    saleItems.forEach(i => {
      db.saleItems.push(i);
      const moved = stockMove(i.variantId, -i.qty, 'sale', no, i.cost, selectedWarehouseId);
      const lineCost = moved && moved.totalCost !== undefined ? moved.totalCost : roundMoney(i.qty * i.cost);
      i.costTotal = lineCost;
      i.cost = i.qty ? roundMoney(lineCost / i.qty) : i.cost;
      actualCogs = roundMoney(actualCogs + lineCost);
    });
    sale.profit = roundMoney(netTotal - actualCogs);
    sale._cogs = actualCogs;
    const payRows = (sale.payments || []).filter(function (x) { return x.account !== 'credit' && num(x.amount) > 0; });
    payRows.forEach(function (x) {
      db.payments.push({ id: uid(), date: now(), direction: 'in', partyType: customerId ? 'customer' : 'other', partyId: customerId || '', amount: x.amount, account: x.account, ref: no, embedded: true, note: 'پرداخت همراه فروش' });
      if (x.account === 'cash') {
        const cs = activeCashSession();
        if (cs) cashMove(cs.id, x.amount, 'sale', no, 'دریافت نقدی فروش');
      }
    });
    const lines = [];
    payRows.forEach(function (x) { lines.push({ account: x.account, debit: x.amount, credit: 0 }); });
    if (due > 0) lines.push({ account: 'receivable', debit: due, credit: 0, partyType: 'customer', partyId: customerId });
    lines.push({ account: 'sales', debit: 0, credit: netTotal });
    if (vat > 0) lines.push({ account: 'vatPayable', debit: 0, credit: vat });
    const cogsAmount = sale._cogs !== undefined ? sale._cogs : cost;
    if (cogsAmount > 0) { lines.push({ account: 'cogs', debit: cogsAmount, credit: 0 }); lines.push({ account: 'inventory', debit: 0, credit: cogsAmount }); }
    postJournal(no, 'فروش', lines, { saleId: sale.id });
    audit('ثبت فروش', no, ''); saveDB(true);
    return { sale, items: saleItems, number: no };
  }

  function createPurchase(payload) {
    const { items = [], supplierId = '', warehouseId = '', payments = { cash: 0, card: 0, bank: 0, credit: 0 } } = payload;
    if (!items.length) throw new Error('خرید خالی است');
    const cash = num(payments.cash || 0), card = num(payments.card || 0), bank = num(payments.bank || 0), credit = num(payments.credit || 0);
    const paymentParts = [cash, card, bank, credit];
    if (paymentParts.some(function (amount) { return !Number.isFinite(amount) || amount < 0; })) throw new Error('مبلغ یکی از روش‌های پرداخت نامعتبر است');
    const paymentTotal = roundMoney(cash + card + bank + credit);
    if (paymentTotal <= 0) throw new Error('مبلغ خرید معتبر نیست');
    if (credit > 0 && !supplierId) throw new Error('برای ثبت بدهی، تأمین‌کننده را انتخاب کنید');
    if (cash > 0 && !activeCashSession()) throw new Error('برای پرداخت نقدی ابتدا صندوق را باز کنید');

    ensureWarehouseState();
    const defaultWarehouse = db.warehouses.find(function (w) { return w.id === 'MAIN' && w.active !== false; }) || db.warehouses.find(function (w) { return w.active !== false; });
    const selectedWarehouseId = warehouseId || (defaultWarehouse && defaultWarehouse.id);
    const selectedWarehouse = db.warehouses.find(function (w) { return w.id === selectedWarehouseId && w.active !== false; });
    if (!selectedWarehouse) throw new Error('انبار مقصد معتبر نیست');

    const tax = db.taxProfile || {};
    const taxRate = tax.enabled ? num(tax.vatRate) : 0;
    const taxOn = taxRate > 0 && taxRate < 100;
    const taxMode = tax.vatMode === 'inclusive' ? 'inclusive' : 'exclusive';
    const purchaseItems = [];
    let enteredTotal = 0;
    for (const x of items) {
      const v = variantBy(x.variantId); if (!v) throw new Error('یکی از کالاها پیدا نشد');
      const qty = num(x.qty), unitPrice = num(x.unitPrice);
      if (!Number.isFinite(qty) || qty <= 0 || !Number.isInteger(qty)) throw new Error('تعداد خرید باید عدد صحیح و مثبت باشد');
      if (!Number.isFinite(unitPrice) || unitPrice < 0) throw new Error('قیمت خرید نامعتبر است');
      const enteredLine = roundMoney(qty * unitPrice);
      enteredTotal = roundMoney(enteredTotal + enteredLine);
      const netLine = taxOn && taxMode === 'inclusive'
        ? roundMoney(enteredLine * 100 / (100 + taxRate))
        : enteredLine;
      purchaseItems.push({
        id: uid(), variantId: x.variantId, qty,
        unitPrice: qty ? roundMoney(netLine / qty) : 0,
        enteredUnitPrice: unitPrice, total: netLine
      });
    }

    let netTotal = enteredTotal, vat = 0, grossTotal = enteredTotal;
    if (taxOn) {
      if (taxMode === 'inclusive') {
        vat = roundMoney(enteredTotal - enteredTotal * 100 / (100 + taxRate));
        netTotal = roundMoney(enteredTotal - vat);
        grossTotal = enteredTotal;
      } else {
        vat = roundMoney(enteredTotal * taxRate / 100);
        netTotal = enteredTotal;
        grossTotal = roundMoney(netTotal + vat);
      }
    }
    const netItemsTotal = roundMoney(purchaseItems.reduce(function (sum, item) { return sum + item.total; }, 0));
    const adjustment = roundMoney(netTotal - netItemsTotal);
    if (purchaseItems.length && Math.abs(adjustment) > 0.0001) {
      const last = purchaseItems[purchaseItems.length - 1];
      last.total = roundMoney(last.total + adjustment);
      last.unitPrice = roundMoney(last.total / last.qty);
    }
    if (Math.abs(roundMoney(grossTotal - paymentTotal)) > 0.01) {
      throw new Error('جمع اقلام به‌همراه مالیات با مجموع پرداخت و بدهی فاکتور خرید برابر نیست');
    }

    const no = typeof nextNumber === 'function' ? nextNumber('purchase') : ('P-' + Date.now());
    const paymentMethodCount = paymentParts.filter(function (amount) { return amount > 0; }).length;
    const paymentType = paymentMethodCount > 1 ? 'mixed' : cash ? 'cash' : card ? 'card' : bank ? 'bank' : 'credit';
    const row = {
      id: uid(), number: no, date: now(), supplierId: supplierId || '', warehouseId: selectedWarehouseId,
      status: 'confirmed', payment: paymentType, total: grossTotal, netTotal, vat,
      vatMode: vat ? taxMode : '', vatRate: vat ? taxRate : 0,
      paid: cash + card + bank, due: credit, items: purchaseItems.map(function (x) { return x.id; }),
      payments: [
        { account: 'cash', amount: cash }, { account: 'card', amount: card },
        { account: 'bank', amount: bank }, { account: 'credit', amount: credit }
      ].filter(function (x) { return x.amount > 0; })
    };
    db.purchases = db.purchases || []; db.purchaseItems = db.purchaseItems || []; db.payments = db.payments || [];
    db.purchases.push(row);
    purchaseItems.forEach(function (item) {
      db.purchaseItems.push(item);
      const v = variantBy(item.variantId);
      const oldQty = Math.max(0, num(v.stock)), oldCost = Math.max(0, num(v.buyPrice));
      const moved = stockMove(item.variantId, item.qty, 'purchase', no, item.unitPrice, selectedWarehouseId, item.total);
      if (costingMethod() !== 'weighted_average') {
        v.buyPrice = oldQty + item.qty > 0
          ? roundMoney(((oldQty * oldCost) + moved.totalCost) / (oldQty + item.qty))
          : item.unitPrice;
      }
    });
    [
      { account: 'cash', amount: cash }, { account: 'card', amount: card }, { account: 'bank', amount: bank }
    ].filter(function (x) { return x.amount > 0; }).forEach(function (x) {
      db.payments.push({
        id: uid(), date: now(), direction: 'out', partyType: supplierId ? 'supplier' : 'other',
        partyId: supplierId || '', amount: x.amount, account: x.account, ref: no,
        embedded: true, note: 'پرداخت همراه خرید'
      });
      if (x.account === 'cash') {
        const cs = activeCashSession();
        if (cs) cashMove(cs.id, -x.amount, 'purchase', no, 'پرداخت نقدی خرید');
      }
    });
    const lines = [{ account: 'inventory', debit: netTotal, credit: 0 }];
    if (vat) lines.push({ account: 'vatReceivable', debit: vat, credit: 0 });
    if (cash) lines.push({ account: 'cash', debit: 0, credit: cash });
    if (card) lines.push({ account: 'card', debit: 0, credit: card });
    if (bank) lines.push({ account: 'bank', debit: 0, credit: bank });
    if (credit) lines.push({ account: 'payable', debit: 0, credit: credit, partyType: 'supplier', partyId: supplierId });
    postJournal(no, 'خرید', lines, { purchaseId: row.id, purchaseVat: vat, warehouseId: selectedWarehouseId });
    audit('ثبت خرید', no, '');
    saveDB(true);
    return { purchase: row, items: purchaseItems, number: no };
  }

  return { postJournal, stockMove, accountBalance, atomic, cashMove, activeCashSession, cashSessionExpected, openCashSession, closeCashSession, createSale, createPurchase, costingMethod, version: '1.4.0-engine' };
}
if (typeof module !== 'undefined' && module.exports) module.exports = { createEngine };
else window.UniqueEngine = { createEngine };
