/* Injected into the page by run_tests.py. Drives the REAL app (UI + engine) with isolated test data. */
window.T=(function(){
  const sleep=t=>new Promise(r=>setTimeout(r,t));
  const msgs=[];const _t=window.toast;window.toast=(m,e)=>{msgs.push((e?'ERR:':'')+String(m));return _t&&_t(m,e)};window.confirm=()=>true;
  const bal=()=>{const b={};for(const j of db.journal)for(const l of j.lines)b[l.account]=(b[l.account]||0)+num(l.debit)-num(l.credit);return b};
  const unbalanced=()=>db.journal.filter(j=>Math.abs(num(j.debit)-num(j.credit))>0.01).length;
  async function seed(o){o=o||{};
    db.taxProfile={enabled:!!o.vat,vatRate:o.vat||0,vatMode:o.mode||'exclusive'};
    db.costing=db.costing||{};if(o.costing)db.costing.method=o.costing;
    const m={id:uid(),name:'کتونی تست',brand:'',modelCode:'T'+uid().slice(0,4),category:'a',active:true};db.models.push(m);
    const v={id:uid(),modelId:m.id,color:'مشکی',size:'42',barcode:'B'+uid().slice(0,6),sku:'SKU-'+uid().slice(0,5),buyPrice:0,sellPrice:o.sell||1500,minStock:1,stock:0,active:true};db.variants.push(v);
    const sup={id:uid(),name:'تأمین‌کننده',phone:'0912'};db.suppliers.push(sup);const cus={id:uid(),name:'مشتری',phone:'0913'};db.customers.push(cus);
    saveDB(true);openCashSession(o.cash==null?1000000:o.cash,'test','test');return{v:v.id,sup:sup.id,cus:cus.id,m:m.id}}
  async function buy(S,vid,q,p,pay){page='purchase';render();await sleep(80);addPurchase(vid);purchaseCart[0].qty=q;purchaseCart[0].price=p;renderPurchaseCart();
    document.querySelector('#purSup').value=S.sup;pay=pay||{cash:q*p};
    for(const [id,k] of [['purCash','cash'],['purCard','card'],['purBank','bank'],['purCredit','credit']])document.querySelector('#'+id).value=String(pay[k]||0);
    renderPurchasePaymentSummary();const n0=db.purchases.length;document.querySelector('#savePurchase').click();await sleep(150);return db.purchases.length>n0?db.purchases[db.purchases.length-1]:null}
  async function sell(S,vid,q,p,pay,disc){page='sale';render();await sleep(80);addSale(vid);saleCart[0].qty=q;saleCart[0].price=p;renderSaleCart&&renderSaleCart();
    document.querySelector('#saleCustomer').value=S.cus;document.querySelector('#saleDiscount').value=String(disc||0);
    window.__salePayments=Object.assign({cash:0,card:0,bank:0,credit:0},pay||{});for(const e of document.querySelectorAll('[data-pay]')){const k=e.dataset.pay;if(Object.prototype.hasOwnProperty.call(window.__salePayments,k)){e.value=String(window.__salePayments[k]||0);e.dispatchEvent(new Event('input',{bubbles:true}))}}const n0=db.sales.length;document.querySelector('#saveSale').click();await sleep(200);return db.sales.length>n0?db.sales[db.sales.length-1]:null}
  return{sleep,msgs,bal,unbalanced,seed,buy,sell}})();
