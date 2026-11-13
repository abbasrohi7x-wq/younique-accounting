/**
 * UNIQUE Fin module v0.3 — Returns & Voids with improved VAT
 */
'use strict';
function createFin(db, h, core) {
  const {
    uid, now, num,
    roundMoney = (x) => Math.round(num(x) * 100) / 100,
    audit = () => {}, saveDB = () => true,
    variantBy, variantName = (v) => v?.name || v?.id || '?',
    paymentAccount = (m) => m === 'card' ? 'card' : m === 'bank' ? 'bank' : 'cash',
    saleByNo, purchaseByNo,
  } = h;
  const { atomic, postJournal, stockMove, cashMove, activeCashSession } = core;
  const R = roundMoney;

  function returnedQty(type, itemKey, itemId) {
    let q = 0;
    for (const r of (db.returns || []).filter(r => r.type === type))
      for (const it of (r.items || [])) if (it[itemKey] === itemId) q += num(it.qty);
    return q;
  }
  function findSale(ref) {
    if (typeof saleByNo === 'function') return saleByNo(ref);
    return (db.sales || []).find(s => s.number === ref || s.id === ref) || null;
  }
  function findPurchase(ref) {
    if (typeof purchaseByNo === 'function') return purchaseByNo(ref);
    return (db.purchases || []).find(p => p.number === ref || p.id === ref) || null;
  }


  function reverseJournal(j, desc, meta) {
    const lines = (j.lines || []).map(l => ({
      account: l.account,
      debit: num(l.credit),
      credit: num(l.debit),
      partyType: l.partyType,
      partyId: l.partyId
    }));
    return postJournal(j.ref + '-VOID', desc, lines, { reversalOf: j.id, ...(meta || {}) });
  }

  function saleReturn({ ref, qtys = {}, method = 'credit', note = '' }) {
    return atomic('برگشت از فروش ' + ref, () => {
      const s = findSale(ref);
      if (!s) throw new Error('فاکتور فروش پیدا نشد');
      if (s.status !== 'confirmed') throw new Error('فاکتور باطل‌شده یا نامعتبر قابل برگشت نیست');
      if (method === 'credit' && !s.customerId) throw new Error('برای تسویه در حساب، فاکتور باید مشتری داشته باشد');
      if (method === 'cash' && !activeCashSession()) throw new Error('برای برگشت نقدی ابتدا صندوق را باز کنید');

      const items = (s.items || []).map(id => (db.saleItems || []).find(x => x.id === id)).filter(Boolean);
      const sumNet = items.reduce((a, i) => a + num(i.total), 0);
      let total = 0, costTotal = 0;
      const out = [];

      for (const i of items) {
        const q = num(qtys[i.id]);
        if (!q) continue;
        if (!Number.isInteger(q) || q < 0) throw new Error('تعداد برگشت باید عدد صحیح مثبت باشد');
        const already = returnedQty('sale', 'saleItemId', i.id);
        if (q + already > num(i.qty) + 1e-9) throw new Error('تعداد برگشت بیشتر از مقدار قابل برگشت است');

        // Proportional net after invoice-level discount allocation
        const net = R(num(i.total) - (sumNet ? num(s.discount) * num(i.total) / sumNet : 0));
        const doneNet = 0; // simplified cumulative for first extraction
        const rev = R(net * (q / num(i.qty)));
        const costAll = num(i.costTotal) || R(num(i.cost) * num(i.qty));
        const cst = R(costAll * (q / num(i.qty)));

        stockMove(i.variantId, q, 'sale_return', ref, cst / q, i.warehouseId || s.warehouseId || 'MAIN');
        total += rev; costTotal += cst;
        out.push({ variantId: i.variantId, qty: q, saleItemId: i.id, unitPrice: i.unitPrice, net: rev, cost: cst / q, costTotal: cst });
      }
      if (!out.length) throw new Error('حداقل یک قلم برای برگشت انتخاب کنید');
      total = R(total); costTotal = R(costTotal);
      if (total <= 0) throw new Error('مبلغ برگشت معتبر نیست');

      // VAT handling closer to original
      const prevR = (db.returns || []).filter(r => r.type === 'sale' && r.ref === ref);
      const doneBase = prevR.reduce((a, r) => a + num(r.total), 0);
      const doneVat = prevR.reduce((a, r) => a + num(r.vat), 0);
      const sv = num(s.vat), incl = s.vatMode === 'inclusive';
      const base = incl ? num(s.total) : num(s.total) - sv;
      let vatRet = 0;
      if (sv > 0 && base > 0) {
        vatRet = (doneBase + total >= base - 0.01)
          ? R(Math.max(0, sv - doneVat))
          : R(Math.min(sv - doneVat, sv * total / base));
      }
      const refund = incl ? total : R(total + vatRet);

      const row = {
        id: uid(), date: now(), type: 'sale', ref, total, vat: vatRet, refund,
        note: note || '', method, customerId: s.customerId || '', supplierId: '', costTotal, items: out
      };
      db.returns = db.returns || []; db.returns.push(row);

      const lines = [{ account: 'salesReturn', debit: incl ? R(total - vatRet) : total, credit: 0 }];
      if (vatRet) lines.push({ account: 'vatPayable', debit: vatRet, credit: 0 });
      if (method === 'credit') lines.push({ account: 'receivable', debit: 0, credit: refund, partyType: 'customer', partyId: s.customerId });
      else lines.push({ account: paymentAccount(method), debit: 0, credit: refund });
      if (costTotal) {
        lines.push({ account: 'inventory', debit: costTotal, credit: 0 });
        lines.push({ account: 'cogs', debit: 0, credit: costTotal });
      }
      const jr = ref + '-R' + row.id.slice(-4);
      postJournal(jr, 'برگشت از فروش', lines, { returnId: row.id, costTotal });

      if (method !== 'credit') {
        db.payments = db.payments || [];
        db.payments.push({ id: uid(), date: now(), direction: 'out', partyType: s.customerId ? 'customer' : 'other', partyId: s.customerId || '', amount: refund, account: paymentAccount(method), ref: jr, embedded: true, note: 'پرداخت برگشت فروش' });
        if (method === 'cash') { const cs = activeCashSession(); if (cs) cashMove(cs.id, -refund, 'sale_return', ref, 'پرداخت برگشت فروش'); }
      }
      audit('ثبت برگشت', ref, 'sale · ' + total); saveDB(true); return row;
    });
  }

  function purchaseReturn({ ref, qtys = {}, method = 'credit', note = '' }) {
    return atomic('برگشت از خرید ' + ref, () => {
      const p = findPurchase(ref);
      if (!p) throw new Error('فاکتور خرید پیدا نشد');
      if (p.status !== 'confirmed') throw new Error('فاکتور باطل‌شده قابل برگشت نیست');
      if (method === 'credit' && !p.supplierId) throw new Error('برای ثبت در حساب، فاکتور باید تأمین‌کننده داشته باشد');
      if (method === 'cash' && !activeCashSession()) throw new Error('برای دریافت نقدی ابتدا صندوق را باز کنید');
      const items = (p.items || []).map(id => (db.purchaseItems || []).find(x => x.id === id)).filter(Boolean);
      let total = 0; const out = [];
      for (const i of items) {
        const q = num(qtys[i.id]); if (!q) continue;
        if (!Number.isInteger(q) || q < 0) throw new Error('تعداد برگشت باید عدد صحیح مثبت باشد');
        const already = returnedQty('purchase', 'purchaseItemId', i.id);
        if (q + already > num(i.qty) + 1e-9) throw new Error('تعداد برگشت بیشتر از مقدار قابل برگشت است');
        const v = variantBy(i.variantId); if (!v) throw new Error('تنوع کالا پیدا نشد');
        if (num(v.stock) < q) throw new Error('موجودی برای برگشت کافی نیست');
        const lineTotal = R(num(i.unitPrice) * q);
        stockMove(i.variantId, -q, 'purchase_return', ref, num(i.unitPrice), i.warehouseId || p.warehouseId || 'MAIN');
        total += lineTotal;
        out.push({ variantId: i.variantId, qty: q, purchaseItemId: i.id, unitPrice: i.unitPrice, total: lineTotal });
      }
      if (!out.length) throw new Error('حداقل یک قلم برای برگشت انتخاب کنید');
      total = R(total);
      const row = { id: uid(), date: now(), type: 'purchase', ref, total, note: note || '', method, supplierId: p.supplierId || '', customerId: '', items: out };
      db.returns = db.returns || []; db.returns.push(row);
      const lines = [];
      if (method === 'credit') lines.push({ account: 'payable', debit: total, credit: 0, partyType: 'supplier', partyId: p.supplierId });
      else lines.push({ account: paymentAccount(method), debit: total, credit: 0 });
      lines.push({ account: 'inventory', debit: 0, credit: total });
      const jr = ref + '-PR' + row.id.slice(-4);
      postJournal(jr, 'برگشت از خرید', lines, { returnId: row.id });
      if (method !== 'credit') {
        db.payments = db.payments || [];
        db.payments.push({ id: uid(), date: now(), direction: 'in', partyType: 'supplier', partyId: p.supplierId || '', amount: total, account: paymentAccount(method), ref: jr, embedded: true, note: 'دریافت برگشت خرید' });
      }
      if (method === 'cash') { const cs = activeCashSession(); if (cs) cashMove(cs.id, total, 'purchase_return', ref, 'دریافت برگشت خرید'); }
      audit('ثبت برگشت خرید', ref, String(total)); saveDB(true); return row;
    });
  }

  function voidSale(refOrOpts, reasonArg) {
    const no = typeof refOrOpts === 'string' ? refOrOpts : (refOrOpts && refOrOpts.ref);
    const reason = typeof refOrOpts === 'string' ? (reasonArg || '') : ((refOrOpts && refOrOpts.reason) || '');
    return atomic('ابطال فروش ' + no, () => {
      if (!String(reason || '').trim()) throw new Error('دلیل ابطال الزامی است');
      const s = findSale(no);
      if (!s) throw new Error('فاکتور پیدا نشد');
      if (s.status === 'voided') throw new Error('این فاکتور قبلاً باطل شده است');
      if ((db.returns || []).some(r => r.type === 'sale' && r.ref === no)) {
        throw new Error('برای این فاکتور برگشت ثبت شده است؛ ابطال ممکن نیست');
      }
      const j = (db.journal || []).find(x => x.saleId === s.id && !x.reversalOf);
      if (!j) throw new Error('سند حسابداری فاکتور پیدا نشد');
      if ((db.journal || []).some(x => x.reversalOf === j.id)) {
        throw new Error('سند معکوس قبلاً ثبت شده است');
      }
      // restore stock
      for (const id of (s.items || [])) {
        const i = (db.saleItems || []).find(x => x.id === id);
        if (!i) continue;
        const warehouseId = i.warehouseId || s.warehouseId || 'MAIN';
        stockMove(i.variantId, num(i.qty), 'void_sale', no, num(i.cost), warehouseId);
      }
      // reverse embedded payments
      for (const pm of (db.payments || []).filter(x => x.ref === no && x.embedded && x.direction === 'in')) {
        db.payments.push({
          id: uid(), date: now(), direction: 'out',
          partyType: pm.partyType, partyId: pm.partyId,
          amount: pm.amount, account: pm.account,
          ref: no + '-VOID', embedded: true, note: 'معکوس پرداخت فاکتور باطل‌شده'
        });
        if (pm.account === 'cash') {
          const cs = activeCashSession();
          if (!cs) throw new Error('برای ابطال فاکتور دارای دریافت نقدی ابتدا صندوق را باز کنید');
          cashMove(cs.id, -num(pm.amount), 'sale_void', no, 'ابطال فاکتور');
        }
      }
      const rj = reverseJournal(j, 'ابطال فروش', { saleId: s.id, voidReason: reason });
      s.status = 'voided';
      s.voidedAt = now();
      s.voidReason = reason;
      s.voidJournalId = rj.id;
      audit('ابطال فروش', no, reason);
      saveDB(true);
      return s;
    });
  }

  function voidPurchase(refOrOpts, reasonArg) {
    const no = typeof refOrOpts === 'string' ? refOrOpts : (refOrOpts && refOrOpts.ref);
    const reason = typeof refOrOpts === 'string' ? (reasonArg || '') : ((refOrOpts && refOrOpts.reason) || '');
    return atomic('ابطال خرید ' + no, () => {
      if (!String(reason || '').trim()) throw new Error('دلیل ابطال الزامی است');
      const pur = findPurchase(no);
      if (!pur) throw new Error('فاکتور پیدا نشد');
      if (pur.status === 'voided') throw new Error('این فاکتور قبلاً باطل شده است');
      if ((db.returns || []).some(r => r.type === 'purchase' && r.ref === no)) {
        throw new Error('برای این فاکتور برگشت ثبت شده است؛ ابطال ممکن نیست');
      }
      // block if stock already sold (insufficient to reverse)
      for (const id of (pur.items || [])) {
        const i = (db.purchaseItems || []).find(x => x.id === id);
        if (!i) continue;
        const v = variantBy(i.variantId);
        if (!v || num(v.stock) < num(i.qty)) {
          throw new Error('موجودی کافی برای ابطال خرید نیست (احتمالاً فروخته شده)');
        }
      }
      const j = (db.journal || []).find(x => (x.purchaseId === pur.id || x.ref === no) && !x.reversalOf);
      if (!j) throw new Error('سند حسابداری فاکتور پیدا نشد');
      if ((db.journal || []).some(x => x.reversalOf === j.id)) {
        throw new Error('سند معکوس قبلاً ثبت شده است');
      }
      for (const id of (pur.items || [])) {
        const i = (db.purchaseItems || []).find(x => x.id === id);
        if (!i) continue;
        stockMove(i.variantId, -num(i.qty), 'void_purchase', no, num(i.unitPrice), i.warehouseId || pur.warehouseId || 'MAIN');
      }
      for (const pm of (db.payments || []).filter(x => x.ref === no && x.embedded && x.direction === 'out')) {
        db.payments.push({
          id: uid(), date: now(), direction: 'in',
          partyType: pm.partyType, partyId: pm.partyId,
          amount: pm.amount, account: pm.account,
          ref: no + '-VOID', embedded: true, note: 'معکوس پرداخت خرید باطل‌شده'
        });
        if (pm.account === 'cash') {
          const cs = activeCashSession();
          if (!cs) throw new Error('برای ابطال خرید دارای پرداخت نقدی ابتدا صندوق را باز کنید');
          cashMove(cs.id, num(pm.amount), 'purchase_void', no, 'ابطال خرید');
        }
      }
      const rj = reverseJournal(j, 'ابطال خرید', { purchaseId: pur.id, voidReason: reason });
      pur.status = 'voided';
      pur.voidedAt = now();
      pur.voidReason = reason;
      pur.voidJournalId = rj.id;
      audit('ابطال خرید', no, reason);
      saveDB(true);
      return pur;
    });
  }

  return { saleReturn, purchaseReturn, voidSale, voidPurchase, version: '0.3.0-fin' };
}
if (typeof module !== 'undefined' && module.exports) module.exports = { createFin };
else window.UniqueFin = { createFin };
