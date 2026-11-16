#!/usr/bin/env python3
"""UNIQUE — portable regression tests.
Runs the real app in headless Chromium (Playwright) and asserts accounting/inventory/security invariants.
Setup:  pip install playwright && python -m playwright install chromium      Run:  python3 tests/run_tests.py [name-filter]
Every test uses a fresh browser context (clean storage) and only synthetic data."""
import asyncio,sys,json,pathlib,time
from playwright.async_api import async_playwright
HERE=pathlib.Path(__file__).resolve().parent;ROOT=HERE.parent;URL='http://127.0.0.1:8765/index.html';HELP=(HERE/'helpers.js').read_text(encoding='utf8')
TESTS=[];RES=[]
def test(f):TESTS.append(f);return f
class Check:
    def __init__(s,name):s.name=name;s.fails=[];s.n=0
    def eq(s,got,exp,what):
        s.n+=1
        if got!=exp:s.fails.append(f'{what}: expected {exp!r}, got {got!r}')
    def true(s,cond,what):
        s.n+=1
        if not cond:s.fails.append(what)
async def page(br):
    ctx=await br.new_context(viewport={'width':1280,'height':800});pg=await ctx.new_page();errs=[]
    pg.on('pageerror',lambda e:errs.append(str(getattr(e,'stack',e))[:900]));await pg.goto(URL);await pg.wait_for_timeout(1500);await pg.evaluate(HELP);pg.errs=errs;return pg,ctx
async def ev(pg,js):return await pg.evaluate('async()=>{'+js+'}')

@test
async def runtime_boot_diagnostics(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,"""
      return{cash:typeof window.openCashSession,stockMove:typeof window.stockMoveV21,
        db:!!window.db,version:window.YOUNIQUE_VERSION,title:document.title,
        body:document.body.innerText.slice(0,500)};
    """)
    c.eq(r['cash'],'function','cash-session service is exposed after boot: '+str(r))
    c.eq(r['stockMove'],'function','warehouse movement service is exposed after boot: '+str(r))
    c.true(r['db'],'database is initialized after boot: '+str(r))
    c.eq(pg.errs,[],'boot has no uncaught browser exceptions')
    await ctx.close()


@test
async def vat_exclusive_sale_and_ledger(br,c):
    pg,ctx=await page(br);r=await ev(pg,'''const S=await T.seed({vat:10});await T.buy(S,S.v,10,1000,{cash:4000,credit:7000});
      const s=await T.sell(S,S.v,3,1500,{cash:2000,credit:2950});const b=T.bal();const v=variantBy(S.v);
      return{sale:s&&{total:s.total,vat:s.vat,profit:s.profit},b,stock:v.stock,unb:T.unbalanced(),health:runYouniqueHealthCheck().ok}''')
    c.eq(r['sale'],{'total':4950,'vat':450,'profit':1500},'sale totals');c.eq(r['stock'],7,'stock')
    for k,x in {'inventory':7000,'vatReceivable':1000,'vatPayable':-450,'receivable':2950,'sales':-4500,'cogs':3000,'payable':-7000}.items():c.eq(r['b'].get(k),x,'account '+k)
    c.eq(r['unb'],0,'unbalanced journals');c.true(r['health'],'health check');c.eq(pg.errs,[],'page errors');await ctx.close()

@test
async def vat_inclusive_with_discount(br,c):
    pg,ctx=await page(br);r=await ev(pg,'''const S=await T.seed({vat:9,mode:'inclusive'});await T.buy(S,S.v,7,333,{cash:2331});
      const s=await T.sell(S,S.v,3,999,{cash:2897},100);return{s:s&&{t:s.total,vat:s.vat,d:s.discount,p:s.profit},b:T.bal(),unb:T.unbalanced()}''')
    c.eq(r['s'],{'t':2897,'vat':239,'d':100,'p':1741},'inclusive sale');c.eq(r['b'].get('cogs'),917,'cogs');c.eq(r['b'].get('inventory'),1222,'inventory');c.eq(r['unb'],0,'balanced');await ctx.close()

@test
async def returns_partial_full_and_over_return_blocked(br,c):
    pg,ctx=await page(br);r=await ev(pg,'''const S=await T.seed({vat:10});await T.buy(S,S.v,10,1000,{cash:11000});const s=await T.sell(S,S.v,3,1500,{cash:4950});
      const it=s.items[0];const r1=Fin.saleReturn({ref:s.number,qtys:{[it]:1},method:'cash',note:'t'});const r2=Fin.saleReturn({ref:s.number,qtys:{[it]:2},method:'cash',note:'t'});
      let over=null;try{Fin.saleReturn({ref:s.number,qtys:{[it]:1},method:'cash'})}catch(e){over=e.message}
      return{r1:[r1.total,r1.vat,r1.refund],r2:[r2.total,r2.vat,r2.refund],over:!!over,stock:variantBy(S.v).stock,unb:T.unbalanced(),inv:T.bal().inventory}''')
    c.eq(r['r1'],[1500,150,1650],'partial return');c.eq(r['r2'],[3000,300,3300],'final return');c.true(r['over'],'over-return must be blocked')
    c.eq(r['stock'],10,'stock restored');c.eq(r['inv'],10000,'inventory account');c.eq(r['unb'],0,'balanced');await ctx.close()

@test
async def void_flows_restore_everything(br,c):
    pg,ctx=await page(br);r=await ev(pg,'''const S=await T.seed({vat:10});const p=await T.buy(S,S.v,10,1000,{cash:11000});const s=await T.sell(S,S.v,3,1500,{cash:4950});
      let blocked=null;try{Fin.voidPurchase(p.number,'t')}catch(e){blocked=e.message}
      Fin.voidSale(s.number,'t');Fin.voidPurchase(p.number,'t');let dbl=null;try{Fin.voidSale(s.number,'t')}catch(e){dbl=e.message}
      const b=T.bal();const z=Object.entries(b).filter(([k,v])=>k!=='cash'&&k!=='equity'&&Math.abs(v)>0.01);
      return{blocked:!!blocked,dbl:!!dbl,nonZero:z,stock:variantBy(S.v).stock,cash:b.cash,unb:T.unbalanced()}''')
    c.true(r['blocked'],'void purchase must be blocked after stock sold');c.true(r['dbl'],'double void blocked');c.eq(r['nonZero'],[],'all accounts back to zero');c.eq(r['stock'],0,'stock');c.eq(r['cash'],1000000,'cash restored');c.eq(r['unb'],0,'balanced');await ctx.close()


@test
async def invoice_void_reverses_mixed_tender_and_all_ledgers(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,"""
      const S=await T.seed({cash:1000000});
      const purchase=await T.buy(S,S.v,4,1000,{cash:2000,card:1000,bank:1000});
      const sale=await T.sell(S,S.v,1,1500,{cash:500,card:500,bank:500});
      const purchaseJournal=db.journal.find(j=>j.purchaseId===purchase.id&&!j.reversalOf);
      const saleJournal=db.journal.find(j=>j.saleId===sale.id&&!j.reversalOf);
      const before={stock:variantBy(S.v).stock,warehouse:db.warehouseStocks.MAIN[S.v],
        cash:accountBalance('cash'),card:accountBalance('card'),bank:accountBalance('bank'),
        payments:db.payments.length,journal:db.journal.length,cashMoves:db.cashMovements.length};
      const voidSale=Fin.voidSale(sale.number,'mixed tender sale reversal');
      const saleReverse=db.journal.find(j=>j.reversalOf===saleJournal.id);
      const salePaymentReversals=db.payments.filter(p=>p.ref===sale.number+'-VOID'&&p.direction==='out');
      const afterSale={stock:variantBy(S.v).stock,cash:accountBalance('cash'),
        card:accountBalance('card'),bank:accountBalance('bank'),
        reversals:salePaymentReversals.length,cashMoves:db.cashMovements.length};
      const voidPurchase=Fin.voidPurchase(purchase.number,'mixed tender purchase reversal');
      const purchaseReverse=db.journal.find(j=>j.reversalOf===purchaseJournal.id);
      const purchasePaymentReversals=db.payments.filter(p=>p.ref===purchase.number+'-VOID'&&p.direction==='in');
      return{before,voidSale:!!voidSale,voidPurchase:!!voidPurchase,
        saleStatus:sale.status,purchaseStatus:purchase.status,
        afterSale,saleReverse:!!saleReverse,saleReversalPayments:salePaymentReversals.map(p=>[p.account,p.amount]),
        purchaseReverse:!!purchaseReverse,purchaseReversalPayments:purchasePaymentReversals.map(p=>[p.account,p.amount]),
        final:{stock:variantBy(S.v).stock,warehouse:db.warehouseStocks.MAIN[S.v],
          cash:accountBalance('cash'),card:accountBalance('card'),bank:accountBalance('bank'),
          inventory:accountBalance('inventory'),cashMoves:db.cashMovements.length,
          unbalanced:T.unbalanced(),health:runYouniqueHealthCheck().ok}};
    """)
    c.eq(r['before']['stock'],3,'sale consumes one unit before void')
    c.eq(r['before']['warehouse'],3,'warehouse stock follows sale')
    c.true(r['voidSale'],'mixed tender sale void succeeds')
    c.eq(r['afterSale']['stock'],4,'sale void restores variant stock')
    c.eq(r['afterSale']['cash'],998000,'sale void reverses cash receipt')
    c.eq(r['afterSale']['card'],-1000,'sale void reverses card receipt')
    c.eq(r['afterSale']['bank'],-1000,'sale void reverses bank receipt')
    c.eq(r['afterSale']['reversals'],3,'sale void reverses all three tender rows')
    c.true(r['saleReverse'],'sale void creates a reversing journal')
    c.eq(r['saleReversalPayments'],[['cash',500],['card',500],['bank',500]],'sale reversal preserves tender accounts and amounts')
    c.true(r['voidPurchase'],'mixed tender purchase void succeeds after sale reversal')
    c.eq(r['saleStatus'],'voided','sale status is voided')
    c.eq(r['purchaseStatus'],'voided','purchase status is voided')
    c.true(r['purchaseReverse'],'purchase void creates a reversing journal')
    c.eq(r['purchaseReversalPayments'],[['cash',2000],['card',1000],['bank',1000]],'purchase reversal preserves tender accounts and amounts')
    c.eq(r['final'],{'stock':0,'warehouse':0,'cash':1000000,'card':0,'bank':0,
      'inventory':0,'cashMoves':4,'unbalanced':0,'health':True},
      'both voids restore all stock, tender balances, cash movements and accounting integrity')
    c.eq(pg.errs,[],'mixed tender invoice voids produce no browser errors')
    await ctx.close()


@test
async def credit_only_invoice_void_restores_party_balances_without_cash_movements(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,"""
      const S=await T.seed({cash:750000});
      const purchase=await T.buy(S,S.v,4,1000,{credit:4000});
      const sale=await T.sell(S,S.v,1,1500,{credit:1500});
      const before={stock:variantBy(S.v).stock,cash:accountBalance('cash'),
        receivable:accountBalance('receivable'),payable:accountBalance('payable'),
        payments:db.payments.filter(x=>x.embedded).length,
        cashMoves:db.cashMovements.length};
      const voidSale=Fin.voidSale(sale.number,'credit-only sale reversal');
      const afterSale={stock:variantBy(S.v).stock,receivable:accountBalance('receivable'),
        payable:accountBalance('payable'),cash:accountBalance('cash'),
        cashMoves:db.cashMovements.length};
      const voidPurchase=Fin.voidPurchase(purchase.number,'credit-only purchase reversal');
      return{before,voidSale:!!voidSale,voidPurchase:!!voidPurchase,
        saleStatus:sale.status,purchaseStatus:purchase.status,afterSale,
        final:{stock:variantBy(S.v).stock,cash:accountBalance('cash'),
          receivable:accountBalance('receivable'),payable:accountBalance('payable'),
          payments:db.payments.filter(x=>x.embedded).length,
          cashMoves:db.cashMovements.length,unbalanced:T.unbalanced(),
          health:runYouniqueHealthCheck().ok}};
    """)
    c.eq(r['before'],{'stock':3,'cash':750000,'receivable':1500,'payable':-4000,
      'payments':0,'cashMoves':0},'credit-only invoice starting balances')
    c.true(r['voidSale'],'credit-only sale void succeeds')
    c.eq(r['afterSale'],{'stock':4,'receivable':0,'payable':-4000,
      'cash':750000,'cashMoves':0},'sale void restores customer balance without cash movement')
    c.true(r['voidPurchase'],'credit-only purchase void succeeds')
    c.eq(r['saleStatus'],'voided','credit-only sale status')
    c.eq(r['purchaseStatus'],'voided','credit-only purchase status')
    c.eq(r['final'],{'stock':0,'cash':750000,'receivable':0,'payable':0,
      'payments':0,'cashMoves':0,'unbalanced':0,'health':True},
      'credit-only voids restore inventory and party ledgers without synthetic payments')
    c.eq(pg.errs,[],'credit-only voids produce no browser errors')
    await ctx.close()

@test
async def costing_fifo_vs_average(br,c):
    for method,cogs,inv in (('fifo',12400,9600),('weighted_average',13200,8800)):
        pg,ctx=await page(br);r=await ev(pg,f'''const S=await T.seed({{costing:'{method}'}});await T.buy(S,S.v,10,1000,{{cash:10000}});await T.buy(S,S.v,10,1200,{{cash:12000}});
          await T.sell(S,S.v,12,2000,{{cash:24000}});const b=T.bal();return{{m:costingMethod(),cogs:b.cogs,inv:b.inventory,unb:T.unbalanced()}}''')
        c.eq(r['m'],method,method+' active');c.eq(r['cogs'],cogs,method+' cogs');c.eq(r['inv'],inv,method+' inventory');c.eq(r['unb'],0,'balanced');await ctx.close()

@test
async def cash_session_variance_and_reopen(br,c):
    pg,ctx=await page(br);r=await ev(pg,'''const S=await T.seed({});await T.buy(S,S.v,10,1000,{cash:10000});await T.sell(S,S.v,3,2000,{cash:6000});
      const exp=cashSessionExpected(activeCashSession());closeCashSession(exp-500,'short');let b=T.bal();const short=b.cashShortage,cashAfterClose=b.cash;
      const o=openCashSession(1000000,'again','t');b=T.bal();return{exp,short,cashAfterClose,cashAfterReopen:b.cash,expected2:cashSessionExpected(o),unb:T.unbalanced()}''')
    c.eq(r['exp'],996000,'expected cash');c.eq(r['short'],500,'shortage booked');c.eq(r['cashAfterClose'],995500,'ledger cash after close')
    c.eq(r['cashAfterReopen'],r['expected2'],'ledger cash equals session expected after reopen');c.eq(r['unb'],0,'balanced');await ctx.close()

@test
async def loan_with_insufficient_cash_leaves_no_orphan_journal(br,c):
    pg,ctx=await page(br);r=await ev(pg,'''const S=await T.seed({cash:100});page='loans';render();await T.sleep(100);window.proLoans();await T.sleep(100);document.querySelector('#newLoan').click();await T.sleep(100);
      const set=(id,v)=>{document.querySelector('#'+id).value=v};set('loanType','borrowed');set('loanParty','بانک');set('loanAmount','5000');set('loanAccount','bank');set('loanParts','1');
      document.querySelector('#loanForm').dispatchEvent(new Event('submit',{cancelable:true}));await T.sleep(150);const x=db.loans[0];
      document.querySelector('[data-loan-pay="'+x.id+'"]').click();await T.sleep(100);set('loanPayAmount','3000');set('loanPayAccount','cash');const j0=db.journal.length;
      document.querySelector('#loanPayForm').dispatchEvent(new Event('submit',{cancelable:true}));await T.sleep(150);
      return{newJournals:db.journal.length-j0,remaining:db.loans[0].remaining,cash:T.bal().cash,unb:T.unbalanced()}''')
    c.eq(r['newJournals'],0,'no journal for failed payment');c.eq(r['remaining'],5000,'loan unchanged');c.eq(r['cash'],100,'cash unchanged');c.eq(r['unb'],0,'balanced');await ctx.close()

@test
async def cheque_lifecycle(br,c):
    pg,ctx=await page(br);r=await ev(pg,'''await T.seed({});page='checks';render();await T.sleep(100);window.proChecks();await T.sleep(100);const set=(id,v)=>{document.querySelector('#'+id).value=v};
      async function mk(t,n,a){document.querySelector('#newCheck').click();await T.sleep(80);set('newCheckType',t);set('newCheckNumber',n);set('newCheckParty','x');set('newCheckBank','b');set('newCheckAmount',String(a));set('newCheckDue','2026-12-01');document.querySelector('#newCheckForm').dispatchEvent(new Event('submit',{cancelable:true}));await T.sleep(120)}
      await mk('received','R1',2000);await mk('paid','P1',1500);
      async function st(n,v){const c=db.checks.find(x=>x.number===n);const s=document.querySelector('[data-check-status="'+c.id+'"]');s.value=v;s.onchange();await T.sleep(120)}
      await st('R1','cashed');await st('P1','paid');const b=T.bal();const c1=db.checks.find(x=>x.number==='R1');const s=document.querySelector('[data-check-status="'+c1.id+'"]');
      if(s){s.value='returned';s.onchange();await T.sleep(80)}
      return{bank:b.bank,cr:b.checksReceivable,cp:b.checksPayable,final:db.checks.find(x=>x.number==='R1').status,unb:T.unbalanced()}''')
    c.eq(r['bank'],500,'bank');c.eq(r['cr'],0,'checks receivable cleared');c.eq(r['cp'],0,'checks payable cleared');c.eq(r['final'],'cashed','final status locked');c.eq(r['unb'],0,'balanced');await ctx.close()

@test
async def warehouse_transfer_and_stocktake(br,c):
    pg,ctx=await page(br);r=await ev(pg,'''const S=await T.seed({});db.warehouses.push({id:'W2',name:'W2',active:true});saveDB(true);await T.buy(S,S.v,10,1000,{cash:10000});
      page='warehouse';render();await T.sleep(150);document.querySelector('#transfer').click();await T.sleep(100);
      document.querySelector('#tv').value=S.v;document.querySelector('#tfrom').value='MAIN';document.querySelector('#tto').value='W2';document.querySelector('#tq').value='4';document.querySelector('#tf').dispatchEvent(new Event('submit',{cancelable:true}));await T.sleep(150);
      const after=[variantBy(S.v).stock,whStock('MAIN',S.v),whStock('W2',S.v)];
      yqStocktake(S.v,'W2',3);return{after,final:[variantBy(S.v).stock,whStock('MAIN',S.v),whStock('W2',S.v)],inv:T.bal().inventory,unb:T.unbalanced(),h:runYouniqueHealthCheck().ok}''')
    c.eq(r['after'],[10,6,4],'after transfer');c.eq(r['final'],[9,6,3],'after stocktake');c.eq(r['inv'],9000,'inventory account follows stocktake');c.eq(r['unb'],0,'balanced');c.true(r['h'],'health');await ctx.close()


@test
async def stocktake_records_have_unique_traceable_references(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,'''const S=await T.seed({});
      await T.buy(S,S.v,5,1000,{cash:5000});
      yqStocktake(S.v,'MAIN',4);
      yqStocktake(S.v,'MAIN',3);
      const rows=db.stocktakes.slice(-2),refs=rows.map(x=>x.ref);
      const moveRefs=db.stockMoves.filter(x=>x.type==='stocktake'&&refs.includes(x.ref)).map(x=>x.ref);
      return{refs,moveRefs,diffs:rows.map(x=>x.diff),stock:variantBy(S.v).stock,
        unb:T.unbalanced(),health:runYouniqueHealthCheck().ok};
    ''')
    c.eq(r['refs'].length,2,'two stocktake records created')
    c.true(r['refs'].every(Boolean),'each stocktake has a reference')
    c.true(r['refs'][0]!=r['refs'][1],'same-day stocktakes receive distinct references')
    c.eq(sorted(r['moveRefs']),sorted(r['refs']),'stock movements point back to their exact stocktake records')
    c.eq(r['diffs'],[-1,-1],'each stocktake records its own counted difference')
    c.eq(r['stock'],3,'both stocktakes update global stock')
    c.eq(r['unb'],0,'stocktake journals remain balanced')
    c.true(r['health'],'stocktake records preserve inventory reconciliation')
    c.eq(pg.errs,[],'stocktake traceability produces no browser errors')
    await ctx.close()


@test
async def bulk_barcode_assignment_rolls_back_on_storage_failure(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,'''const S=await T.seed({});
      const v=variantBy(S.v);v.barcode='';v.sku='';
      page='products';render();
      const row=document.querySelector('.pv');row.checked=true;
      const before={barcode:v.barcode,sku:v.sku,seq:{...db.seq}};
      const original=window.saveDB;window.saveDB=()=>false;
      document.querySelector('#bulkBar').click();
      window.saveDB=original;
      return{before,after:{barcode:v.barcode,sku:v.sku,seq:{...db.seq}},
        health:runYouniqueHealthCheck().ok,errors:[]};
    ''')
    c.eq(r['after'],r['before'],'failed bulk barcode persistence restores codes and counters')
    c.true(r['health'],'bulk barcode rollback preserves catalog integrity')
    c.eq(r['errors'],[],'bulk barcode storage failure is handled')
    await ctx.close()


@test
async def bulk_variant_price_edit_is_atomic_on_storage_failure(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,'''const S=await T.seed({});
      const v=variantBy(S.v),before={purchasePrice:v.purchasePrice,sellPrice:v.sellPrice,minStock:v.minStock};
      page='products';render();document.querySelector('.pv').checked=true;
      document.querySelector('#bulkPrices').click();
      document.querySelector('#bpBuy').value='2222';
      document.querySelector('#bpSell').value='3333';
      document.querySelector('#bpMin').value='7';
      const originalConfirm=window.confirm,originalSave=window.saveDB;
      window.confirm=()=>true;window.saveDB=()=>false;
      document.querySelector('#bulkPriceForm').dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));
      window.confirm=originalConfirm;window.saveDB=originalSave;
      return{before,after:{purchasePrice:v.purchasePrice,sellPrice:v.sellPrice,minStock:v.minStock},
        health:runYouniqueHealthCheck().ok,errors:[]};
    ''')
    c.eq(r['after'],r['before'],'failed bulk price persistence restores all selected variant fields')
    c.true(r['health'],'bulk price rollback preserves catalog integrity')
    c.eq(r['errors'],[],'bulk price storage failure is handled')
    await ctx.close()


@test
async def invalid_inputs_are_rejected(br,c):
    pg,ctx=await page(br);r=await ev(pg,'''const S=await T.seed({});await T.buy(S,S.v,10,1000,{cash:10000});const n0=db.sales.length;
      await T.sell(S,S.v,-2,1500,{cash:100});await T.sell(S,S.v,0.5,1500,{cash:100});await T.sell(S,S.v,1,1500,{cash:0},999999);await T.sell(S,S.v,99,1500,{cash:100});
      return{newSales:db.sales.length-n0,stock:variantBy(S.v).stock,errs:T.msgs.filter(m=>m.startsWith('ERR:')).length,num:[num('1e3'),num('0x10'),num('۱٬۲۳۴'),num('12.5')]}''')
    c.eq(r['newSales'],0,'no invalid sale saved');c.eq(r['stock'],10,'stock untouched');c.true(r['errs']>=4,'each invalid input produced an error');c.eq(r['num'],[0,0,1234,12.5],'num() parsing');await ctx.close()

@test
async def role_page_guard(br,c):
    pg,ctx=await page(br);r=await ev(pg,'''const pages=[...document.querySelectorAll('.nav [data-page]')].map(e=>e.getAttribute('data-page'));const o={};
      for(const role of ['owner','accountant','cashier']){db.users[0].role=role;const bl=[];for(const p of pages){window.page=p;render();await T.sleep(30);if(window.page!==p)bl.push(p)}o[role]=bl}return o''')
    c.eq(r['owner'],[],'owner sees everything');c.eq(sorted(r['accountant']),['automation','backup','settings','users'],'accountant blocked set')
    for p in ('users','settings','backup','accounting','finance','purchase'):c.true(p in r['cashier'],'cashier blocked from '+p)
    await ctx.close()

@test
async def pin_lock_and_lockout(br,c):
    pg,ctx=await page(br);r=await ev(pg,'''db.users[0].pin=window.yqPinInput('4321','');db.security={loginEnabled:true,failed:0,lockedUntil:null};saveDB(true);sessionStorage.removeItem('younique_local_unlock_v1');render();await T.sleep(150);
      const try_=async v=>{document.querySelector('#yUnlockPin').value=v;document.querySelector('#yUnlockForm').dispatchEvent(new Event('submit',{cancelable:true}));await T.sleep(120)};
      const hashed=String(db.users[0].pin).startsWith('h2:');for(let i=0;i<5;i++)await try_('0000');const locked=db.security.lockedUntil>Date.now();
      document.querySelector('#yUnlockPin').disabled=false;document.querySelector('#yUnlockPin').value='4321';document.querySelector('#yUnlockForm').dispatchEvent(new Event('submit',{cancelable:true}));await T.sleep(120);
      const duringLock=sessionStorage.getItem('younique_local_unlock_v1')==='1';db.security.lockedUntil=null;db.security.failed=0;saveDB(true);render();await T.sleep(150);await try_('4321');
      return{hashed,locked,duringLock,after:sessionStorage.getItem('younique_local_unlock_v1')==='1',raw:JSON.stringify(db).includes('"4321"')}''')
    c.true(r['hashed'],'PIN stored hashed');c.true(r['locked'],'5 failures lock');c.true(not r['duringLock'],'correct PIN rejected during lockout');c.true(r['after'],'correct PIN unlocks after lockout');c.true(not r['raw'],'raw PIN not in data');await ctx.close()

@test
async def receipt_qr_and_no_photo(br,c):
    pg,ctx=await page(br);r=await ev(pg,'''const S=await T.seed({});db.settings.shopName='فروشگاه تست';await T.buy(S,S.v,5,1000,{cash:5000});const s=await T.sell(S,S.v,1,2500,{cash:2500});
      const h=yqReceiptHtml(s.id,'a5');const m=yqQr('YQ|'+'x'.repeat(100));return{hasSvg:/<svg/.test(h),hasImg:/<img/i.test(h),shop:h.includes('فروشگاه تست'),num:h.includes(s.number),qrSize:m&&m.length}''')
    c.true(r['hasSvg'],'QR present');c.true(not r['hasImg'],'no photo on receipt');c.true(r['shop'] and r['num'],'shop name and number printed');c.true(r['qrSize'] and r['qrSize']>=29,'QR version >= 2')
    try:
        import cv2,numpy as np
        svg=await pg.evaluate("yqQrSvg('YQ|فروشگاه|U-1|5000|2026-01-01',480)");await pg.evaluate("h=>{const o=document.createElement('div');o.id='q';o.style.cssText='position:fixed;left:0;top:0;z-index:99999;background:#fff';o.innerHTML=h;document.body.appendChild(o)}",svg)
        png=await pg.screenshot(clip={'x':0,'y':0,'width':480,'height':480});img=cv2.imdecode(np.frombuffer(png,np.uint8),cv2.IMREAD_GRAYSCALE);val,_,_=cv2.QRCodeDetector().detectAndDecode(img);c.eq(val,'YQ|فروشگاه|U-1|5000|2026-01-01','QR decodes with independent decoder (OpenCV)')
    except ImportError:print('   (cv2 not installed — independent QR decode check skipped)')
    await ctx.close()


@test
async def indexeddb_roundtrip_survives_reload(br,c):
    pg,ctx=await page(br)
    await ev(pg,"const S=await T.seed({});db.settings.shopName='ذخیره پایدار آزمون';db.customers.push({id:'persist-customer',name:'مشتری پایدار'});saveDB(true);await YStore.flush();")
    await pg.reload();await pg.wait_for_timeout(1500);await pg.evaluate(HELP)
    r=await ev(pg,"return{mode:YStore.S.mode,ready:YStore.S.ready,shop:db.settings.shopName,customer:db.customers.some(x=>x.id==='persist-customer'),error:window.__YOUNIQUE_LOAD_ERROR||''}")
    c.eq(r['mode'],'idb','IndexedDB mode after reload');c.true(r['ready'],'store ready after reload')
    c.eq(r['shop'],'ذخیره پایدار آزمون','settings survive reload');c.true(r['customer'],'customer survives reload')
    c.eq(r['error'],'','no load error');await ctx.close()


@test
async def indexeddb_missing_record_blocks_overwrite(br,c):
    pg,ctx=await page(br)
    await ev(pg,"const S=await T.seed({});db.settings.shopName='رکوردی که نباید حذف شود';saveDB(true);await YStore.flush();")
    await pg.evaluate("""async()=>{const d=await new Promise((res,rej)=>{const q=indexedDB.open('younique_store');q.onsuccess=()=>res(q.result);q.onerror=()=>rej(q.error)});await new Promise((res,rej)=>{const t=d.transaction('kv','readwrite');t.objectStore('kv').delete('k:settings');t.oncomplete=res;t.onerror=()=>rej(t.error);t.onabort=()=>rej(t.error)});d.close()}""")
    await pg.reload();await pg.wait_for_timeout(1500);await pg.evaluate(HELP)
    r=await ev(pg,"return{mode:YStore.S.mode,integrity:!!YStore.S.integrityError,save:saveDB(true),flushPending:Object.keys(YStore.S.pending).length}")
    c.eq(r['mode'],'idb','store remains in IndexedDB mode');c.true(r['integrity'],'missing record detected')
    c.eq(r['save'],False,'writes blocked on incomplete data');c.eq(r['flushPending'],0,'no automatic overwrite queued')
    await ctx.close()



@test
async def validated_backup_recovers_integrity_locked_store(br,c):
    pg,ctx=await page(br)
    await ev(pg,"const S=await T.seed({});db.settings.shopName='نسخه سالم پشتیبان';saveDB(true);await YStore.flush();sessionStorage.setItem('unique-test-backup',exportData());")
    await pg.evaluate("""async()=>{const d=await new Promise((res,rej)=>{const q=indexedDB.open('younique_store');q.onsuccess=()=>res(q.result);q.onerror=()=>rej(q.error)});await new Promise((res,rej)=>{const t=d.transaction('kv','readwrite');t.objectStore('kv').delete('k:settings');t.oncomplete=res;t.onerror=()=>rej(t.error);t.onabort=()=>rej(t.error)});d.close()}""")
    await pg.reload();await pg.wait_for_timeout(1500);await pg.evaluate(HELP)
    r=await ev(pg,"const backup=JSON.parse(sessionStorage.getItem('unique-test-backup'));await replaceDB(backup.data);await YStore.flush();return{integrity:!!YStore.S.integrityError,failed:!!YStore.S.failed,shop:db.settings.shopName,ready:YStore.S.ready}")
    c.true(not r['integrity'],'validated backup clears integrity lock after successful restore')
    c.true(not r['failed'],'restore transaction completed without failure')
    c.eq(r['shop'],'نسخه سالم پشتیبان','backup settings restored')
    c.true(r['ready'],'store remains ready')
    await ctx.close()


@test
async def indexeddb_encryption_rekey_and_disable_roundtrip(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,"""
      const S=await T.seed({});db.settings.shopName='رمزنگاری پایدار';saveDB(true);await YStore.flush();
      await YStore.enableEncryption('test-pass-123');
      const read=async()=>{const d=await new Promise((res,rej)=>{const q=indexedDB.open('younique_store');q.onsuccess=()=>res(q.result);q.onerror=()=>rej(q.error)});const x=await new Promise((res,rej)=>{const t=d.transaction('kv','readonly');const q=t.objectStore('kv').get('k:settings');q.onsuccess=()=>res(q.result);q.onerror=()=>rej(q.error)});d.close();return x};
      const enc1=await read(),meta1=await new Promise((res,rej)=>{const q=indexedDB.open('younique_store');q.onsuccess=()=>{const d=q.result;const t=d.transaction('kv','readonly'),g=t.objectStore('kv').get('meta');g.onsuccess=()=>{d.close();res(g.result)};g.onerror=()=>rej(g.error)};q.onerror=()=>rej(q.error)});
      await YStore.changePassphrase('test-pass-123','new-pass-456');
      const meta2=await new Promise((res,rej)=>{const q=indexedDB.open('younique_store');q.onsuccess=()=>{const d=q.result;const t=d.transaction('kv','readonly'),g=t.objectStore('kv').get('meta');g.onsuccess=()=>{d.close();res(g.result)};g.onerror=()=>rej(g.error)};q.onerror=()=>rej(q.error)});
      await YStore.disableEncryption();
      const meta3=await new Promise((res,rej)=>{const q=indexedDB.open('younique_store');q.onsuccess=()=>{const d=q.result;const t=d.transaction('kv','readonly'),g=t.objectStore('kv').get('meta');g.onsuccess=()=>{d.close();res(g.result)};g.onerror=()=>rej(g.error)};q.onerror=()=>rej(q.error)});
      const plain=await read();
      return{enc:!!meta1.enc,encryptedRecord:!!(enc1&&enc1.iv&&enc1.ct),rekeyed:!!meta2.enc&&String(meta1.enc.salt)!==String(meta2.enc.salt),disabled:!meta3.enc&&!YStore.S.enc,plainRecord:typeof plain==='string'&&JSON.parse(plain).shopName==='رمزنگاری پایدار',failed:!!YStore.S.failed,shop:db.settings.shopName}
    """)
    c.true(r['enc'],'encryption metadata stored')
    c.true(r['encryptedRecord'],'settings record encrypted at rest')
    c.true(r['rekeyed'],'passphrase change generated a new salt')
    c.true(r['disabled'],'encryption can be disabled')
    c.true(r['plainRecord'],'plaintext restored after disabling encryption')
    c.eq(r['failed'],False,'no storage failure during encryption transitions')
    c.eq(r['shop'],'رمزنگاری پایدار','live data preserved')
    await ctx.close()


@test
async def encrypted_store_accepts_validated_backup_restore(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,"""
      const S=await T.seed({});db.settings.shopName='نسخه پشتیبان رمزنگاری';saveDB(true);await YStore.flush();
      const backup=JSON.parse(exportData());await YStore.enableEncryption('test-pass-123');
      db.settings.shopName='داده تغییریافته';saveDB(true);await YStore.flush();
      await replaceDB(backup.data);await YStore.flush();
      const d=await new Promise((res,rej)=>{const q=indexedDB.open('younique_store');q.onsuccess=()=>res(q.result);q.onerror=()=>rej(q.error)});
      const state=await new Promise((res,rej)=>{const t=d.transaction('kv','readonly'),st=t.objectStore('kv'),m=st.get('meta'),v=st.get('k:settings');t.oncomplete=()=>res({meta:m.result,record:v.result});t.onerror=()=>rej(t.error)});d.close();
      return{shop:db.settings.shopName,encrypted:!!state.meta.enc,recordEncrypted:!!(state.record&&state.record.iv&&state.record.ct),failed:!!YStore.S.failed,integrity:!!YStore.S.integrityError}
    """)
    c.eq(r['shop'],'نسخه پشتیبان رمزنگاری','backup data restored')
    c.true(r['encrypted'],'encryption remains enabled after restore')
    c.true(r['recordEncrypted'],'restored data remains encrypted at rest')
    c.eq(r['failed'],False,'no storage failure during encrypted restore')
    c.eq(r['integrity'],False,'no integrity lock after restore')
    await ctx.close()


@test
async def invalid_backup_never_mutates_live_data(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,"""
      const S=await T.seed({});db.settings.shopName='اطلاعات زنده';await YStore.flush();
      const before=cloneDB();let missing=false,row=false;
      const badMissing={...cloneDB(),customers:'خراب'};
      try{await replaceDB(badMissing)}catch(_){missing=true}
      const badRow=cloneDB();badRow.models=[null];
      try{await replaceDB(badRow)}catch(_){row=true}
      return{missing,row,shop:db.settings.shopName,customers:db.customers.length,models:db.models.length,
        pending:Object.keys(YStore.S.pending).length,failed:!!YStore.S.failed,integrity:!!YStore.S.integrityError}
    """)
    c.true(r['missing'],'missing required section rejected')
    c.true(r['row'],'malformed record rejected')
    c.eq(r['shop'],'اطلاعات زنده','live settings unchanged')
    c.eq(r['customers'],1,'live customers unchanged')
    c.eq(r['models'],1,'live models unchanged')
    c.eq(r['pending'],0,'invalid imports do not queue writes')
    c.eq(r['failed'],False,'invalid imports do not fail storage')
    c.eq(r['integrity'],False,'invalid imports do not alter integrity state')
    await ctx.close()



@test
async def backup_rejects_malformed_settings_and_storage_metadata(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,"""
      const S=await T.seed({});
      db.settings.shopName='داده زنده';await YStore.flush();
      const before=JSON.stringify({shop:db.settings.shopName,models:db.models,
        variants:db.variants,sales:db.sales,journal:db.journal});
      const cases=[];
      const badSettings=cloneDB();badSettings.settings=[];
      const badSeq=cloneDB();badSeq.seq='not-an-object';
      const badWarehouse=cloneDB();badWarehouse.warehouseStocks=[];
      for(const data of [badSettings,badSeq,badWarehouse]){
        let rejected=false;try{await replaceDB(data)}catch(_){rejected=true}
        cases.push(rejected);
      }
      const after=JSON.stringify({shop:db.settings.shopName,models:db.models,
        variants:db.variants,sales:db.sales,journal:db.journal});
      return{cases,before,after,pending:Object.keys(YStore.S.pending).length,
        failed:!!YStore.S.failed,integrity:!!YStore.S.integrityError,errors:[]};
    """)
    c.eq(r['cases'],[True,True,True],'malformed settings, sequence and warehouse metadata are rejected')
    c.eq(r['after'],r['before'],'invalid backup metadata never replaces live business data')
    c.eq(r['pending'],0,'invalid backup metadata queues no storage writes')
    c.eq(r['failed'],False,'invalid backup metadata does not poison storage')
    c.eq(r['integrity'],False,'invalid backup metadata does not alter integrity lock')
    c.eq(pg.errs,[],'backup validation produces no browser errors')
    await ctx.close()


@test
async def encrypted_backup_rejects_malformed_envelope(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,"""
      const valid=JSON.parse(await yqEncryptBackup(JSON.stringify({app:'younique',data:{}}),'test-pass-123'));
      const variants=[
        {...valid,kdf:'PBKDF2-SHA1'},
        {...valid,iter:999999999},
        {...valid,salt:'AA=='},
        {...valid,iv:'AA=='},
        {...valid,data:'AA=='},
        {...valid,app:'other'}
      ];
      const rejected=[];
      for(const item of variants){try{await yqDecryptBackup(item,'test-pass-123');rejected.push(false)}catch(_){rejected.push(true)}}
      return{rejected,validTag:valid.enc,validIter:valid.iter}
    """)
    c.eq(r['rejected'],[True,True,True,True,True,True],'malformed encrypted envelopes rejected')
    c.eq(r['validIter'],310000,'valid backup retains supported KDF work factor')
    await ctx.close()


@test
async def localstorage_migrates_to_indexeddb(br,c):
    ctx=await br.new_context(viewport={'width':1280,'height':800})
    await ctx.add_init_script("""localStorage.setItem('younique_v16_db',JSON.stringify({
      schema:13,settings:{shopName:'مهاجرت نسخه قدیمی'},models:[],variants:[],
      sales:[],purchases:[],customers:[],suppliers:[]
    }))""")
    pg=await ctx.new_page();await pg.goto(URL);await pg.wait_for_timeout(1500);await pg.evaluate(HELP)
    r=await ev(pg,"return{mode:YStore.S.mode,migrated:YStore.S.migrated,shop:db.settings.shopName,ready:YStore.S.ready}")
    c.eq(r['mode'],'idb','migrated store uses IndexedDB');c.true(r['migrated'],'legacy migration flagged')
    c.eq(r['shop'],'مهاجرت نسخه قدیمی','legacy settings preserved');c.true(r['ready'],'store ready after migration')
    await ctx.close()


@test
async def backup_export_excludes_ai_secret(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,"""
      await T.seed({});
      db.settings.ai=db.settings.ai||{};
      db.settings.ai.apiKey='UNIQUE_TEST_SECRET_DO_NOT_EXPORT';
      const raw=exportData(),parsed=JSON.parse(raw);
      return{secretInBackup:raw.includes('UNIQUE_TEST_SECRET_DO_NOT_EXPORT'),
        backupKey:parsed.data.settings.ai.apiKey,
        liveKey:db.settings.ai.apiKey}
    """)
    c.eq(r['secretInBackup'],False,'AI secret never appears in exported backup')
    c.eq(r['backupKey'],'','backup contains an empty AI key')
    c.eq(r['liveKey'],'UNIQUE_TEST_SECRET_DO_NOT_EXPORT','export preserves the active in-memory key')
    await ctx.close()


@test
async def ai_sale_requires_explicit_confirmation(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,"""
      const S=await T.seed({});await T.buy(S,S.v,5,1000,{cash:5000});
      UAI.ctx.reset();const before={sales:db.sales.length,stock:variantBy(S.v).stock,journal:db.journal.length};
      const info={intent:'create_sale',entities:{}};
      const asked=await UAI._runSteps([{tool:'create_sale',params:{items:[{variantId:S.v,qty:1,price:1500}],method:'cash'}}],0,info,'text','فروش یک عدد کتونی');
      const waiting=!!UAI.ctx.pending;
      const unchanged={sales:db.sales.length===before.sales,stock:variantBy(S.v).stock===before.stock,journal:db.journal.length===before.journal};
      const answer=await UAI.chat.handle('بله',{source:'text'});
      return{kind:asked[0]&&asked[0].kind,waiting,unchanged,committed:db.sales.length===before.sales+1,
        stock:variantBy(S.v).stock,answerKind:answer[0]&&answer[0].kind,answerText:answer.map(x=>x.text).join(' | '),stage:window.__YQ_AI_SALE_STAGE,pending:!!UAI.ctx.pending,toasts:T.msgs.slice(-8),unb:T.unbalanced()}
    """)
    c.eq(r['kind'],'confirm','AI write produces confirmation prompt')
    c.true(r['waiting'],'pending confirmation is stored')
    c.eq(r['unchanged'],{'sales':True,'stock':True,'journal':True},'no business data changes before confirmation')
    c.true(r['committed'],'sale commits after explicit yes '+r['answerText']+' stage='+str(r['stage'])+' '+str(r['toasts']))
    c.eq(r['stock'],4,'confirmed sale decrements stock')
    c.eq(r['pending'],False,'pending confirmation cleared')
    c.eq(r['unb'],0,'confirmed sale journals balanced')
    await ctx.close()


@test
async def manual_sale_split_payment_is_persisted(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,"""
      const S=await T.seed({});await T.buy(S,S.v,5,1000,{cash:5000});
      const sale=await T.sell(S,S.v,2,1500,{cash:600,card:1500,bank:300,credit:600});
      const p=Object.fromEntries((sale&&sale.payments||[]).map(x=>[x.account,num(x.amount)]));
      const journal=db.journal.find(j=>j.ref===sale.number||j.number===sale.number);
      return{saved:!!sale,total:sale&&sale.total,paid:sale&&sale.paid,due:sale&&sale.due,payment:sale&&sale.payment,p,
        stock:variantBy(S.v).stock,unb:T.unbalanced(),
        journalAccounts:journal?(journal.lines||[]).filter(x=>['cash','card','bank','receivable'].includes(x.account)).map(x=>[x.account,num(x.debit)]):[]}
    """)
    c.true(r['saved'],'manual split-payment sale saved')
    c.eq(r['total'],3000,'manual invoice total')
    c.eq(r['paid'],2400,'manual received total excludes credit')
    c.eq(r['due'],600,'manual credit balance')
    c.eq(r['payment'],'mixed','manual multi-method sale is classified as mixed')
    c.eq(r['p'],{'cash':600,'card':1500,'bank':300,'credit':600},'manual payment allocations persist exactly')
    c.eq(r['stock'],3,'manual sale decrements stock by two')
    c.eq(r['unb'],0,'manual split-payment journal balanced')
    c.eq(dict(r['journalAccounts']),{'cash':600,'card':1500,'bank':300,'receivable':600},'manual journal posts each payment account')
    await ctx.close()


@test
async def ai_sale_split_payment_requires_confirmation_and_persists(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,"""
      const S=await T.seed({});await T.buy(S,S.v,5,1000,{cash:5000});
      UAI.ctx.reset();
      const before={sales:db.sales.length,stock:variantBy(S.v).stock,journal:db.journal.length,payments:db.payments.length};
      const info={intent:'create_sale',entities:{}};
      const asked=await UAI._runSteps([{tool:'create_sale',params:{
        customerId:S.cus,items:[{variantId:S.v,qty:2,price:1500}],
        payments:{cash:600,card:1500,bank:300,credit:600},unit:'rial'
      }}],0,info,'text','فروش دو عدد با پرداخت ترکیبی');
      const waiting=!!UAI.ctx.pending;
      const unchanged={sales:db.sales.length===before.sales,stock:variantBy(S.v).stock===before.stock,
        journal:db.journal.length===before.journal,payments:db.payments.length===before.payments};
      const answer=await UAI.chat.handle('بله',{source:'text'});
      const sale=db.sales.at(-1);
      const p=Object.fromEntries((sale&&sale.payments||[]).map(x=>[x.account,num(x.amount)]));
      const journal=db.journal.find(j=>j.ref===sale.number||j.number===sale.number);
      return{kind:asked[0]&&asked[0].kind,waiting,unchanged,committed:db.sales.length===before.sales+1,
        total:sale&&sale.total,paid:sale&&sale.paid,due:sale&&sale.due,p,stock:variantBy(S.v).stock,
        paymentRecords:db.payments.filter(x=>x.ref===sale.number&&x.embedded).map(x=>[x.account,num(x.amount)]),
        journalAccounts:journal?(journal.lines||[]).filter(x=>['cash','card','bank','receivable'].includes(x.account)).map(x=>[x.account,num(x.debit)]):[],
        answer:answer.map(x=>x.text).join(' '),unb:T.unbalanced(),pending:!!UAI.ctx.pending}
    """)
    c.eq(r['kind'],'confirm','AI split-payment write asks for confirmation')
    c.true(r['waiting'],'AI split-payment confirmation is pending')
    c.eq(r['unchanged'],{'sales':True,'stock':True,'journal':True,'payments':True},'AI split-payment does not mutate data before confirmation')
    c.true(r['committed'],'AI split-payment commits after explicit confirmation')
    c.eq(r['total'],3000,'AI split-payment invoice total')
    c.eq(r['paid'],2400,'AI split-payment received total')
    c.eq(r['due'],600,'AI split-payment credit balance')
    c.eq(r['p'],{'cash':600,'card':1500,'bank':300,'credit':600},'AI payment allocations persist exactly')
    c.eq(r['stock'],3,'AI sale decrements stock by two')
    c.eq(dict(r['paymentRecords']),{'cash':600,'card':1500,'bank':300},'AI payment records use correct accounts and amounts')
    c.eq(dict(r['journalAccounts']),{'cash':600,'card':1500,'bank':300,'receivable':600},'AI journal debits match split payments')
    c.eq(r['unb'],0,'AI split-payment journal balanced')
    c.eq(r['pending'],False,'AI confirmation is cleared after commit')
    await ctx.close()


@test
async def ai_sale_decline_and_permission_recheck(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,"""
      const S=await T.seed({});await T.buy(S,S.v,5,1000,{cash:5000});
      const info={intent:'create_sale',entities:{}};
      const start=db.sales.length;
      await UAI._runSteps([{tool:'create_sale',params:{items:[{variantId:S.v,qty:1,price:1500}],method:'cash'}}],0,info,'text','فروش یک عدد');
      const declined=await UAI.chat.handle('خیر',{source:'text'});
      const declineSafe=db.sales.length===start&&variantBy(S.v).stock===5&&!UAI.ctx.pending;
      await UAI._runSteps([{tool:'create_sale',params:{items:[{variantId:S.v,qty:1,price:1500}],method:'cash'}}],0,info,'text','فروش یک عدد');
      db.users[0].role='accountant';
      const blocked=await UAI.chat.handle('بله',{source:'text'});
      return{declineSafe,blockedNoSale:db.sales.length===start,stock:variantBy(S.v).stock,
        pending:!!UAI.ctx.pending,blockedText:blocked.map(x=>x.text).join(' '),unb:T.unbalanced()}
    """)
    c.true(r['declineSafe'],'declined operation leaves sales and stock unchanged')
    c.true(r['blockedNoSale'],'permission revoked before confirmation blocks the write')
    c.eq(r['stock'],5,'stock unchanged after decline and permission denial')
    c.eq(r['pending'],False,'pending confirmation cleared')
    c.true('اجازه' in r['blockedText'],'permission denial is surfaced')
    c.eq(r['unb'],0,'ledger remains balanced')
    await ctx.close()


@test
async def cash_void_requires_open_session_without_partial_mutation(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,"""
      const S=await T.seed({cash:1000000});
      const purchase=await T.buy(S,S.v,2,1000,{cash:2000});
      const cashAfterPurchase=accountBalance('cash');
      const sale=await T.sell(S,S.v,1,1500,{cash:1500});
      const session=activeCashSession();
      closeCashSession(cashSessionExpected(session),'close before void','test');
      const snapshot=()=>JSON.stringify({
        status:sale.status,stock:variantBy(S.v).stock,
        payments:db.payments,journal:db.journal,
        cashMoves:db.cashMovements,stockMoves:db.stockMoves,
        warehouseMoves:db.warehouseMoves,cash:accountBalance('cash')
      });
      const before=snapshot();let blocked='';
      try{Fin.voidSale(sale.number,'void after shift close')}catch(e){blocked=e.message}
      const after=snapshot();
      openCashSession(1000000,'new shift','test');
      const voided=Fin.voidSale(sale.number,'void after reopening shift');
      return{blocked:!!blocked,before,after,voided:!!voided,cashAfterPurchase,
        status:sale.status,stock:variantBy(S.v).stock,
        cash:accountBalance('cash'),unbalanced:T.unbalanced(),
        health:runYouniqueHealthCheck().ok};
    """)
    c.true(r['blocked'],'cash sale void is blocked when no cash session is open')
    c.eq(r['after'],r['before'],'blocked cash sale void leaves every ledger unchanged')
    c.true(r['voided'],'cash sale void succeeds after opening a new cash session')
    c.eq(r['status'],'voided','sale status is voided after retry')
    c.eq(r['stock'],2,'successful retry restores stock exactly once')
    c.eq(r['cash'],r['cashAfterPurchase'],'cash account returns to the pre-sale balance while the purchase remains posted')
    c.eq(r['unbalanced'],0,'cash session guard preserves balanced journals')
    c.true(r['health'],'cash session guard preserves database health')
    c.eq(pg.errs,[],'cash session guard produces no browser errors')
    await ctx.close()



@test
async def duplicate_variant_lines_cannot_oversell_combined_stock(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,"""
      const S=await T.seed({});
      await T.buy(S,S.v,3,1000,{cash:3000});
      page='sale';render();await T.sleep(80);
      saleCart=[{id:S.v,qty:2,price:1500,discount:0},
                {id:S.v,qty:2,price:1500,discount:0}];
      document.querySelector('#saleCustomer').value=S.cus;
      document.querySelector('#saleDiscount').value='0';
      window.__salePayments={cash:6000,card:0,bank:0,credit:0};
      const before={sales:db.sales.length,journal:db.journal.length,
        payments:db.payments.length,stock:variantBy(S.v).stock,
        warehouse:warehouseAvailable('MAIN',S.v)};
      const result=window.saveSaleV18();
      return{result:result||null,before,
        after:{sales:db.sales.length,journal:db.journal.length,
          payments:db.payments.length,stock:variantBy(S.v).stock,
          warehouse:warehouseAvailable('MAIN',S.v)},
        message:T.msgs[T.msgs.length-1],unbalanced:T.unbalanced()};
    """)
    c.eq(r['result'],None,'oversell rejected')
    c.eq(r['after'],r['before'],'rejected duplicate lines leave all ledgers and stock unchanged')
    c.true('کافی نیست' in r['message'],'clear combined-stock error is shown')
    c.eq(r['unbalanced'],0,'ledger remains balanced')
    c.eq(pg.errs,[],'no browser errors')
    await ctx.close()



@test
async def stale_party_and_warehouse_selections_are_rejected_without_writes(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,"""
      const S=await T.seed({});
      const snapshot=()=>({sales:db.sales.length,purchases:db.purchases.length,
        payments:db.payments.length,journal:db.journal.length,
        stock:variantBy(S.v).stock,stockMoves:db.stockMoves.length});
      page='purchase';render();await T.sleep(80);
      const pur=document.querySelector('#purSup');
      pur.add(new Option('شناسه نامعتبر','missing-supplier'));
      pur.value='missing-supplier';
      purchaseCart=[{id:S.v,qty:1,price:1000}];
      const beforePurchase=snapshot(),purchaseResult=window.savePurchaseV18();
      const afterPurchase=snapshot(),purchaseMessage=T.msgs[T.msgs.length-1];
      pur.value=S.sup;
      const wh=document.querySelector('#purWarehouse');
      wh.add(new Option('انبار نامعتبر','missing-warehouse'));
      wh.value='missing-warehouse';
      purchaseCart=[{id:S.v,qty:1,price:1000}];
      const beforeWarehouse=snapshot(),warehouseResult=window.savePurchaseV18();
      const afterWarehouse=snapshot(),warehouseMessage=T.msgs[T.msgs.length-1];
      page='sale';render();await T.sleep(80);
      const cus=document.querySelector('#saleCustomer');
      cus.add(new Option('شناسه نامعتبر','missing-customer'));
      cus.value='missing-customer';
      saleCart=[{id:S.v,qty:1,price:1500,discount:0}];
      window.__salePayments={cash:1500,card:0,bank:0,credit:0};
      const beforeSale=snapshot(),saleResult=window.saveSaleV18();
      const afterSale=snapshot(),saleMessage=T.msgs[T.msgs.length-1];
      return{purchaseResult:purchaseResult||null,beforePurchase,afterPurchase,purchaseMessage,
        warehouseResult:warehouseResult||null,beforeWarehouse,afterWarehouse,warehouseMessage,
        saleResult:saleResult||null,beforeSale,afterSale,saleMessage,
        unbalanced:T.unbalanced()};
    """)
    c.eq(r['purchaseResult'],None,'invalid supplier purchase rejected')
    c.eq(r['afterPurchase'],r['beforePurchase'],'invalid supplier causes no purchase writes')
    c.true('تأمین‌کننده' in r['purchaseMessage'],'invalid supplier error is clear')
    c.eq(r['warehouseResult'],None,'invalid warehouse purchase rejected')
    c.eq(r['afterWarehouse'],r['beforeWarehouse'],'invalid warehouse causes no purchase writes')
    c.true('انبار' in r['warehouseMessage'],'invalid warehouse error is clear')
    c.eq(r['saleResult'],None,'invalid customer sale rejected')
    c.eq(r['afterSale'],r['beforeSale'],'invalid customer causes no sale writes')
    c.true('مشتری' in r['saleMessage'],'invalid customer error is clear')
    c.eq(r['unbalanced'],0,'ledger remains balanced')
    c.eq(pg.errs,[],'no browser errors')
    await ctx.close()


async def main():
    flt=sys.argv[1] if len(sys.argv)>1 else '';t0=time.time()
    async with async_playwright() as p:
        br=await p.chromium.launch()
        for f in TESTS:
            if flt and flt not in f.__name__:continue
            c=Check(f.__name__)
            try:await f(br,c)
            except Exception as e:c.fails.append('EXCEPTION '+type(e).__name__+': '+str(e)[:300])
            RES.append(c);print(('PASS ' if not c.fails else 'FAIL ')+c.name+f'  ({c.n} assertions)')
            for x in c.fails:print('     -',x)
        await br.close()
    bad=[c for c in RES if c.fails];print(f'\n{len(RES)-len(bad)}/{len(RES)} tests passed, {sum(c.n for c in RES)} assertions, {time.time()-t0:.0f}s');sys.exit(1 if bad else 0)


@test
async def product_variant_edit_rejects_duplicate_combinations_and_codes(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,"""
      const S=await T.seed({});
      const v=variantBy(S.v),original={color:v.color,size:String(v.size),barcode:v.barcode,sku:v.sku,buyPrice:v.buyPrice};
      const sibling={...v,id:'variant-sibling',size:String(Number(v.size)+1),barcode:'9988776655443',sku:'SKU-SIBLING'};
      db.variants.push(sibling);
      function submit(){document.querySelector('#vf').dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}))}
      variantEdit(S.v);document.querySelector('#vs').value=sibling.size;submit();
      const duplicateCombinationRejected=String(v.size)===original.size;
      variantEdit(S.v);document.querySelector('#sku').value=sibling.sku;submit();
      const duplicateSkuRejected=v.sku===original.sku;
      variantEdit(S.v);document.querySelector('#vb').value=sibling.barcode;submit();
      const duplicateBarcodeRejected=v.barcode===original.barcode;
      variantEdit(S.v);document.querySelector('#vbuy').value='-10';submit();
      const negativePriceRejected=Number(v.buyPrice)===Number(original.buyPrice);
      return{duplicateCombinationRejected,duplicateSkuRejected,duplicateBarcodeRejected,negativePriceRejected};
    """)
    c.true(r['duplicateCombinationRejected'],'same model cannot contain duplicate color/size combinations')
    c.true(r['duplicateSkuRejected'],'SKU must remain unique across variants')
    c.true(r['duplicateBarcodeRejected'],'barcode must remain unique across variants')
    c.true(r['negativePriceRejected'],'negative purchase price is rejected')
    await ctx.close()


@test
async def cancelled_product_wizard_does_not_mutate_catalog(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,"""
      const S=await T.seed({});
      const count=db.models.length,original=modelBy(S.m).name;
      productModal();
      document.querySelector('#mn').value='کالای آزمایشی لغوشده';
      document.querySelector('#mb').value='برند تست';
      document.querySelector('#mc').value='CANCEL-01';
      document.querySelector('#mf').dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));
      const newModelCountWhileChoosingVariants=db.models.length;
      closeModal();
      const newModelCountAfterCancel=db.models.length;
      productModal(S.m);
      document.querySelector('#mn').value='نام تأییدشده';
      document.querySelector('#mf').dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));
      const existingNameWhileChoosingVariants=modelBy(S.m).name;
      document.querySelector('#customColor').value='آبی آزمایشی';
      document.querySelector('.vs').checked=true;
      document.querySelector('#makeVariants').click();
      await T.sleep(80);
      return{count,newModelCountWhileChoosingVariants,newModelCountAfterCancel,original,existingNameWhileChoosingVariants,finalName:modelBy(S.m).name};
    """)
    c.eq(r['newModelCountWhileChoosingVariants'],r['count'],'new model is not persisted before variant confirmation')
    c.eq(r['newModelCountAfterCancel'],r['count'],'cancelled new model leaves no orphan catalog record')
    c.eq(r['existingNameWhileChoosingVariants'],r['original'],'editing a model is staged until variant confirmation')
    c.eq(r['finalName'],'نام تأییدشده','confirmed model edit is applied together with the variant')
    await ctx.close()


@test
async def inventory_purchase_precedes_sale_and_split_payment(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,"""
      const S=await T.seed({});
      const before={sales:db.sales.length,journal:db.journal.length,payments:db.payments.length};
      page='sale';render();await T.sleep(80);addSale(S.v);
      const noStock={blocked:saleCart.length===0,stock:variantBy(S.v).stock,
        sales:db.sales.length===before.sales,journal:db.journal.length===before.journal,
        payments:db.payments.length===before.payments,msg:T.msgs.at(-1)};
      saleCart.splice(0);
      const purchase=await T.buy(S,S.v,5,1000,{cash:3000,card:2000});
      const afterPurchase=variantBy(S.v).stock;
      const sale=await T.sell(S,S.v,2,1500,{cash:600,card:1500,bank:300,credit:600});
      const allocations=Object.fromEntries((sale&&sale.payments||[]).map(x=>[x.account,num(x.amount)]));
      return{noStock,purchase:!!purchase,purchasePayment:purchase&&purchase.payment,afterPurchase,sale:!!sale,allocations,
        stock:variantBy(S.v).stock,unb:T.unbalanced(),health:runYouniqueHealthCheck().ok}
    """)
    c.true(r['noStock']['blocked'],'sale with zero inventory is rejected')
    c.eq(r['noStock']['stock'],0,'rejected sale leaves zero stock')
    c.true(r['noStock']['sales'] and r['noStock']['journal'] and r['noStock']['payments'],'rejected sale creates no financial records')
    c.eq(r['afterPurchase'],5,'confirmed purchase creates available inventory')
    c.true(r['purchase'],'purchase invoice saved before sale')
    c.eq(r['purchasePayment'],'mixed','purchase with cash and card is classified as mixed')
    c.true(r['sale'],'sale succeeds after stock is received')
    c.eq(r['allocations'],{'cash':600,'card':1500,'bank':300,'credit':600},'sale payment methods are preserved')
    c.eq(r['stock'],3,'sale decrements received inventory')
    c.eq(r['unb'],0,'purchase and sale ledgers remain balanced')
    c.true(r['health'],'business health check remains valid')
    await ctx.close()


@test
async def manual_purchase_and_sale_require_open_cash_session(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,"""
      const S=await T.seed({});
      const before={p:db.purchases.length,s:db.sales.length,j:db.journal.length,
        pay:db.payments.length,stock:variantBy(S.v).stock};
      activeCashSession().status='closed';saveDB(true);
      const purchase=await T.buy(S,S.v,2,1000,{card:2000});purchaseCart.splice(0);
      const afterPurchase={p:db.purchases.length,j:db.journal.length,pay:db.payments.length,
        stock:variantBy(S.v).stock,msg:T.msgs.at(-1)};
      openCashSession(100000,'test reopen','test');
      await T.buy(S,S.v,5,1000,{cash:5000});
      activeCashSession().status='closed';saveDB(true);
      const sale=await T.sell(S,S.v,1,1500,{cash:1500});
      return{purchaseBlocked:!purchase&&afterPurchase.p===before.p&&afterPurchase.j===before.j&&
          afterPurchase.pay===before.pay&&afterPurchase.stock===before.stock,
        purchaseMessage:afterPurchase.msg,saleBlocked:!sale&&db.sales.length===before.s,
        finalStock:variantBy(S.v).stock,saleMessage:T.msgs.at(-1),unb:T.unbalanced()}
    """)
    c.true(r['purchaseBlocked'],'manual purchase blocked with closed cash session and no mutation')
    c.true('صندوق' in r['purchaseMessage'],'manual purchase explains cash session requirement')
    c.true(r['saleBlocked'],'manual sale blocked with closed cash session and no mutation')
    c.eq(r['finalStock'],5,'blocked manual sale leaves inventory unchanged')
    c.true('صندوق' in r['saleMessage'],'manual sale explains cash session requirement')
    c.eq(r['unb'],0,'ledger remains balanced after blocked invoices')
    await ctx.close()


@test
async def ai_purchase_and_sale_require_open_cash_session(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,"""
      const S=await T.seed({});
      activeCashSession().status='closed';saveDB(true);
      const info={intent:'create_purchase',entities:{}},p0=db.purchases.length,
        stock0=variantBy(S.v).stock,j0=db.journal.length;
      const purchase=await UAI._runSteps([{tool:'create_purchase',params:{
        supplierId:S.sup,items:[{variantId:S.v,qty:2,price:1000}],method:'card'
      }}],0,info,'text','خرید دو عدد با کارت');
      const purchaseSafe=db.purchases.length===p0&&variantBy(S.v).stock===stock0&&db.journal.length===j0&&!UAI.ctx.pending;
      openCashSession(100000,'test reopen','test');
      await T.buy(S,S.v,5,1000,{cash:5000});
      activeCashSession().status='closed';saveDB(true);
      UAI.ctx.reset();
      const s0=db.sales.length,st0=variantBy(S.v).stock,j1=db.journal.length;
      const sale=await UAI._runSteps([{tool:'create_sale',params:{
        items:[{variantId:S.v,qty:1,price:1500}],method:'card'
      }}],0,{intent:'create_sale',entities:{}},'text','فروش یک عدد با کارت');
      const saleSafe=db.sales.length===s0&&variantBy(S.v).stock===st0&&db.journal.length===j1&&!UAI.ctx.pending;
      return{purchaseSafe,purchaseText:purchase.map(x=>x.text).join(' '),saleSafe,
        saleText:sale.map(x=>x.text).join(' '),stock:variantBy(S.v).stock,unb:T.unbalanced()}
    """)
    c.true(r['purchaseSafe'],'AI purchase rejected before confirmation when cash session is closed')
    c.true('صندوق' in r['purchaseText'],'AI purchase explains cash session requirement')
    c.true(r['saleSafe'],'AI sale rejected before confirmation when cash session is closed')
    c.true('صندوق' in r['saleText'],'AI sale explains cash session requirement')
    c.eq(r['stock'],5,'AI blocked invoices leave inventory unchanged')
    c.eq(r['unb'],0,'ledger remains balanced after AI blocks')
    await ctx.close()


@test
async def manual_and_ai_invoices_share_authoritative_writers(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,"""
      const S=await T.seed({});
      const saleWriter=window.__YQ_ENGINE.createSale;
      const purchaseWriter=window.__YQ_ENGINE.createPurchase;
      let engineSaleCalls=0,enginePurchaseCalls=0;
      window.__YQ_ENGINE.createSale=()=>{engineSaleCalls++;throw new Error('engine_sale_must_not_be_used_yet')};
      window.__YQ_ENGINE.createPurchase=()=>{enginePurchaseCalls++;throw new Error('engine_purchase_must_not_be_used_yet')};
      const before={sales:db.sales.length,purchases:db.purchases.length,stock:variantBy(S.v).stock};
      const firstPurchase=await T.buy(S,S.v,5,1000,{cash:5000});
      const sale=await T.sell(S,S.v,1,1500,{cash:1500});
      const purchase=await T.buy(S,S.v,2,900,{cash:1800});
      window.__YQ_ENGINE.createSale=saleWriter;
      window.__YQ_ENGINE.createPurchase=purchaseWriter;
      return{before,firstPurchase:!!firstPurchase,sale:!!sale,purchase:!!purchase,
        sales:db.sales.length,purchases:db.purchases.length,stock:variantBy(S.v).stock,
        engineSaleCalls,enginePurchaseCalls,unb:T.unbalanced(),health:runYouniqueHealthCheck().ok}
    """)
    c.true(r['firstPurchase'],'purchase uses the validated tax-aware writer')
    c.true(r['sale'],'sale uses the validated writer')
    c.true(r['purchase'],'subsequent purchase uses the same validated writer')
    c.eq(r['sales'],1,'one sale is committed')
    c.eq(r['purchases'],2,'two purchases are committed')
    c.eq(r['stock'],6,'stock reflects 5 received, 1 sold, then 2 received')
    c.eq(r['engineSaleCalls'],0,'sale UI does not bypass to the incomplete extracted engine')
    c.eq(r['enginePurchaseCalls'],0,'purchase UI does not bypass to the incomplete extracted engine')
    c.true(r['engineSaleCalls']==0 and r['enginePurchaseCalls']==0,'manual invoice paths do not bypass the verified writers')
    c.eq(r['unb'],0,'all journals remain balanced')
    c.true(r['health'],'business health check remains valid')
    await ctx.close()


@test
async def negative_split_payments_are_rejected_without_partial_commits(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,"""const S=await T.seed({});
      const p0=db.purchases.length,j0=db.journal.length,m0=db.payments.length;
      await T.buy(S,S.v,2,1000,{cash:2500,card:-500});
      const badPurchase={p:db.purchases.length-p0,j:db.journal.length-j0,m:db.payments.length-m0,stock:variantBy(S.v).stock};
      const p=await T.buy(S,S.v,2,1000,{cash:2000});
      const s0=db.sales.length,j1=db.journal.length,m1=db.payments.length;
      await T.sell(S,S.v,1,1500,{cash:2000,card:-500});
      return{badPurchase,p:!!p,badSale:{s:db.sales.length-s0,j:db.journal.length-j1,m:db.payments.length-m1,stock:variantBy(S.v).stock},
        errors:T.msgs.filter(x=>x.startsWith('ERR:')).length,unb:T.unbalanced(),health:runYouniqueHealthCheck().ok}""")
    c.eq(r['badPurchase'],{'p':0,'j':0,'m':0,'stock':0},'negative purchase payment cannot partially commit')
    c.true(r['p'],'valid purchase commits before sale validation')
    c.eq(r['badSale'],{'s':0,'j':0,'m':0,'stock':2},'negative sale payment cannot partially commit or change stock')
    c.true(r['errors']>=2,'both negative split payment attempts are rejected')
    c.eq(r['unb'],0,'all journals remain balanced')
    c.true(r['health'],'business health check remains valid')
    await ctx.close()


@test
async def invalid_purchase_lines_are_rejected_without_partial_commits(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,"""const S=await T.seed({});
      const before=()=>({p:db.purchases.length,j:db.journal.length,m:db.payments.length,
        stock:variantBy(S.v).stock,moves:db.stockMoves.length,items:db.purchaseItems.length});
      const start=before();
      await T.buy(S,S.v,-1,1000,{cash:10000});
      const negativeQty=before();
      await T.buy(S,S.v,1.5,1000,{cash:10000});
      const fractionalQty=before();
      await T.buy(S,S.v,1,-1000,{cash:10000});
      const negativePrice=before();
      return{start,negativeQty,fractionalQty,negativePrice,
        errors:T.msgs.filter(x=>x.startsWith('ERR:')).length,
        messages:T.msgs.filter(x=>x.startsWith('ERR:')).slice(-3),
        unb:T.unbalanced(),health:runYouniqueHealthCheck().ok}""")
    unchanged={'p':0,'j':0,'m':0,'stock':0,'moves':0,'items':0}
    for key in ('negativeQty','fractionalQty','negativePrice'):
        c.eq(r[key],r['start'],key+' leaves all purchase, stock and ledger records unchanged')
    c.true(r['errors']>=3,'each invalid purchase line is rejected with an error')
    c.eq(r['unb'],0,'rejected purchase lines leave journals balanced')
    c.true(r['health'],'business health check remains valid')
    await ctx.close()


@test
async def vat_purchase_return_preserves_original_warehouse(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,"""const S=await T.seed({vat:10});
      db.warehouses.push({id:'W2',name:'انبار دوم',active:true});
      db.warehouseStocks.W2={};saveDB(true);
      page='purchase';render();await T.sleep(100);addPurchase(S.v);
      purchaseCart[0].qty=4;purchaseCart[0].price=1000;renderPurchaseCart();
      document.querySelector('#purSup').value=S.sup;
      document.querySelector('#purWarehouse').value='W2';
      document.querySelector('#purCash').value='4400';renderPurchasePaymentSummary();
      document.querySelector('#savePurchase').click();await T.sleep(200);
      const p=db.purchases.at(-1),item=db.purchaseItems.find(x=>x.id===p.items[0]);
      const ret=Fin.purchaseReturn({ref:p.number,qtys:{[item.id]:1},method:'card'});
      const move=db.warehouseMoves.at(-1),b=T.bal();
      return{purchaseWarehouse:p.warehouseId,itemWarehouse:item.warehouseId,returnWarehouse:move.warehouseId,
        stock:variantBy(S.v).stock,main:whStock('MAIN',S.v),w2:whStock('W2',S.v),
        returnVat:ret.vat,inventory:b.inventory,value:costValue(),unb:T.unbalanced(),
        health:runYouniqueHealthCheck().ok}""")
    c.eq(r['purchaseWarehouse'],'W2','purchase header records selected warehouse')
    c.eq(r['itemWarehouse'],'W2','purchase line records selected warehouse')
    c.eq(r['returnWarehouse'],'W2','VAT purchase return movement uses original warehouse')
    c.eq(r['stock'],3,'one returned unit is removed from total stock')
    c.eq(r['main'],0,'main warehouse remains unchanged')
    c.eq(r['w2'],3,'return is deducted from original warehouse')
    c.eq(r['returnVat'],100,'VAT return is prorated from the original purchase')
    c.eq(r['inventory'],3000,'inventory ledger reflects returned net cost')
    c.eq(r['value'],3000,'cost-layer valuation matches inventory ledger')
    c.eq(r['unb'],0,'return journal remains balanced')
    c.true(r['health'],'business health check remains valid')
    await ctx.close()


@test
async def purchase_return_records_all_noncredit_payment_methods(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,'''const S=await T.seed({});
      const p=await T.buy(S,S.v,4,1000,{cash:4000});
      const before=db.payments.length;
      const item=(db.purchaseItems||[]).find(x=>x.variantId===S.v&&x.qty===4);
      const ret=Fin.purchaseReturn({ref:p.number,qtys:{[item.id]:2},method:'card',note:'تست برگشت خرید'});
      const pm=db.payments.slice(before).find(x=>x.ref&&x.ref.includes('-R'));
      return{ret:!!ret,stock:variantBy(S.v).stock,supplierId:S.sup,payment:pm&&{direction:pm.direction,partyType:pm.partyType,partyId:pm.partyId,amount:pm.amount,account:pm.account},unb:T.unbalanced(),health:runYouniqueHealthCheck().ok}''')
    c.true(r['ret'],'purchase return saved')
    c.eq(r['stock'],2,'returned quantity removed from stock')
    c.eq(r['payment'],{'direction':'in','partyType':'supplier','partyId':r['supplierId'],'amount':2000,'account':'card'},'card receipt recorded as supplier refund')
    c.eq(r['unb'],0,'purchase return journals remain balanced')
    c.true(r['health'],'business health check remains valid')
    await ctx.close()


@test
async def purchase_return_reconciles_inventory_cost_and_supplier_refund(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,"""const S=await T.seed({costing:'weighted_average'});
      const p1=await T.buy(S,S.v,2,1000,{cash:2000});
      const p2=await T.buy(S,S.v,2,2000,{card:4000});
      const item=db.purchaseItems.find(x=>x.variantId===S.v&&x.qty===2&&x.unitPrice===1000);
      const ret=Fin.purchaseReturn({ref:p1.number,qtys:{[item.id]:1},method:'card',note:'valuation regression'});
      const jr=db.journal.find(x=>x.returnId===ret.id);
      const refund=db.payments.find(x=>x.ref&&x.ref.includes('-R')&&x.partyType==='supplier'&&x.direction==='in');
      return{p1:!!p1,p2:!!p2,ret:!!ret,stock:variantBy(S.v).stock,
        costValue:costValue(),inventoryLedger:accountBalance('inventory'),
        returnedCost:ret.costTotal,variance:jr&&jr.lines.find(x=>x.account==='purchaseReturnVariance'),
        refund:refund&&{direction:refund.direction,partyId:refund.partyId,amount:refund.amount,account:refund.account},
        unb:T.unbalanced(),health:runYouniqueHealthCheck().ok,supplierId:S.sup}""")
    c.true(r['p1'] and r['p2'] and r['ret'],'weighted-average purchases and partial purchase return succeed')
    c.eq(r['stock'],3,'partial purchase return removes one unit')
    c.true(abs(r['costValue']-r['inventoryLedger'])<0.01,'inventory valuation matches inventory control account after return')
    c.true(abs(r['returnedCost']-1500)<0.01,'returned inventory uses current weighted-average cost')
    c.true(r['variance'] is not None,'purchase return price/cost difference is posted to variance account')
    c.eq(r['refund'],{'direction':'in','partyId':r['supplierId'],'amount':1000,'account':'card'},'supplier refund is recorded to the selected card account')
    c.eq(r['unb'],0,'purchase return journal remains balanced')
    c.true(r['health'],'business health check remains valid')
    await ctx.close()


@test
async def committed_invoice_drafts_cannot_be_submitted_twice(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,"""
      const S=await T.seed({});
      page='purchase';render();await T.sleep(80);addPurchase(S.v);
      purchaseCart[0].qty=2;purchaseCart[0].price=1000;renderPurchaseCart();
      document.querySelector('#purSup').value=S.sup;
      document.querySelector('#purCash').value='2000';renderPurchasePaymentSummary();
      const p0=db.purchases.length,j0=db.journal.length;
      window.savePurchase();
      const purchaseAfterFirst={count:db.purchases.length,cart:purchaseCart.length,stock:variantBy(S.v).stock};
      window.savePurchase();
      const purchaseAfterRetry={count:db.purchases.length,journals:db.journal.length};
      page='sale';render();await T.sleep(80);addSale(S.v);
      saleCart[0].qty=1;window.__salePayments={cash:1500,card:0,bank:0,credit:0};
      const s0=db.sales.length,sj0=db.journal.length;
      window.saveSale();
      const saleAfterFirst={count:db.sales.length,cart:saleCart.length,stock:variantBy(S.v).stock};
      window.saveSale();
      return{purchaseAfterFirst,purchaseAfterRetry,p0,j0,
        saleAfterFirst,salesAfterRetry:db.sales.length,journalsAfterRetry:db.journal.length,
        s0,sj0,unb:T.unbalanced(),health:runYouniqueHealthCheck().ok}
    """)
    c.eq(r['purchaseAfterFirst'],{'count':r['p0']+1,'cart':0,'stock':2},'purchase draft is cleared after successful commit')
    c.eq(r['purchaseAfterRetry'],{'count':r['p0']+1,'journals':r['j0']+1},'repeated purchase submit cannot duplicate records')
    c.eq(r['saleAfterFirst'],{'count':r['s0']+1,'cart':0,'stock':1},'sale draft is cleared after successful commit')
    c.eq(r['salesAfterRetry'],r['s0']+1,'repeated sale submit cannot duplicate invoices')
    c.eq(r['journalsAfterRetry'],r['sj0']+1,'repeated sale submit cannot duplicate journal entries')
    c.eq(r['unb'],0,'journals remain balanced')
    c.true(r['health'],'business health check remains valid')
    await ctx.close()


@test
async def voice_recognition_never_falls_back_to_remote_service(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,"""
      let starts=0;
      class RemoteOnlyRecognition{start(){starts++}stop(){}}
      Object.defineProperty(window,'SpeechRecognition',{value:RemoteOnlyRecognition,configurable:true,writable:true});
      Object.defineProperty(window,'webkitSpeechRecognition',{value:undefined,configurable:true,writable:true});
      window.__speech=null;
      await voiceRecord();
      const title=document.querySelector('#modal h2')?.textContent||'';
      const manual=document.querySelector('#yqVText')?.textContent||'';
      const transcript=!!document.querySelector('#yqVTranscript');
      return{starts,title,manual,transcript}
    """)
    c.eq(r['starts'],0,'remote-only speech recognition is never started')
    c.eq(r['title'],'دستیار گفتاری آفلاین فارسی','voice entry opens the on-device Vosk dialog')
    c.eq(r['manual'],'ورود متن','manual text entry remains available when speech is unavailable')
    c.true(r['transcript'],'a reviewable transcript field is available before applying text')
    await ctx.close()


@test
async def ocr_invoice_requires_review_and_only_creates_purchase_draft(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,"""
      const S=await T.seed({});
      const before={p:db.purchases.length,j:db.journal.length,pay:db.payments.length,stock:variantBy(S.v).stock};
      const name=variantName(variantBy(S.v));
      showInvoiceResult({documentType:'purchase_invoice',confidence:.95,total:1000,subtotal:1000,
        discount:0,tax:0,shipping:0,items:[{name,qty:2,unitPrice:1000,lineTotal:1000,confidence:.95}]},null);
      document.querySelector('#invoiceConfirm').click();await T.sleep(40);
      const mismatchBlocked=!!document.querySelector('#invoiceConfirm')&&db.purchases.length===before.p;
      closeModal();
      showInvoiceResult({documentType:'purchase_invoice',confidence:.95,total:1000,subtotal:1000,
        discount:0,tax:0,shipping:0,items:[{name,qty:1,unitPrice:1000,lineTotal:1000,confidence:.95}]},null);
      const review=document.querySelector('.modalbox h2')?.textContent||'';
      const rows=document.querySelectorAll('#invoiceRows tr').length;
      document.querySelector('#invoiceConfirm').click();await T.sleep(80);
      const draft=document.querySelector('.modalbox h2')?.textContent||'';
      const afterReview={p:db.purchases.length,j:db.journal.length,pay:db.payments.length,stock:variantBy(S.v).stock};
      document.querySelector('#aiExec').click();await T.sleep(100);
      return{review,rows,draft,before,afterReview,mismatchBlocked,
        afterDraft:{p:db.purchases.length,j:db.journal.length,pay:db.payments.length,stock:variantBy(S.v).stock},
        cart:purchaseCart.length,form:!!document.querySelector('#purWarehouse')}
    """)
    c.true(r['mismatchBlocked'],'OCR approval blocks a line amount that differs from quantity times unit price')
    c.eq(r['review'],'بررسی و تأیید فاکتور','OCR opens an editable invoice review before any purchase')
    c.eq(r['rows'],1,'OCR review shows the extracted invoice line')
    c.eq(r['draft'],'پیش‌نویس خرید','confirming OCR opens a purchase draft preview')
    c.eq(r['afterReview'],r['before'],'review confirmation does not commit financial records')
    c.eq(r['afterDraft'],r['before'],'creating the purchase draft still does not post stock or ledger entries')
    c.eq(r['cart'],1,'the approved OCR item is carried into the manual purchase cart')
    c.true(r['form'],'user lands on the normal purchase form for final payment and commit')
    c.eq(r['afterDraft']['p'],0,'no purchase invoice is committed before final manual save')
    await ctx.close()


@test
async def ocr_rejects_invalid_and_oversized_files_before_processing(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,"""
      const S=await T.seed({});
      const before={p:db.purchases.length,j:db.journal.length,pay:db.payments.length,
        stock:variantBy(S.v).stock,history:db.aiHistory.length};
      let empty=false,type=false,size=false;
      try{await analyzeInvoiceImage(new File([], 'empty.jpg', {type:'image/jpeg'}))}catch(e){empty=/خالی|نامعتبر/.test(e.message)}
      try{await analyzeInvoiceImage(new File(['x'], 'note.txt', {type:'text/plain'}))}catch(e){type=/تصویری/.test(e.message)}
      try{await analyzeInvoiceImage({size:26*1024*1024,type:'image/jpeg'})}catch(e){size=/۲۵ مگابایت/.test(e.message)}
      return{before,empty,type,size,progress:OCRProgress.visible(),
        after:{p:db.purchases.length,j:db.journal.length,pay:db.payments.length,
          stock:variantBy(S.v).stock,history:db.aiHistory.length}}
    """)
    c.true(r['empty'],'empty image is rejected')
    c.true(r['type'],'non-image file is rejected')
    c.true(r['size'],'oversized image is rejected before decoding')
    c.eq(r['progress'],False,'invalid files never start OCR processing')
    c.eq(r['after'],r['before'],'invalid files do not mutate business data or OCR history')
    await ctx.close()


@test
async def offline_ocr_loader_retries_after_script_download_failure(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,"""
      const original=HTMLHeadElement.prototype.appendChild;
      const previous=window.Tesseract;
      let attempts=0,firstFailed=false,secondLoaded=false;
      HTMLHeadElement.prototype.appendChild=function(node){
        if(node.tagName==='SCRIPT'&&node.src.includes('/vendor/tesseract/tesseract.min.js')){
          attempts++;
          setTimeout(()=>{
            if(attempts===1)node.onerror(new Event('error'));
            else{window.Tesseract={createWorker:function(){}};node.onload(new Event('load'))}
          },0);
          return node;
        }
        return original.call(this,node);
      };
      try{
        try{await ensureLocalOCR()}catch(e){firstFailed=true}
        const T=await ensureLocalOCR();
        secondLoaded=!!(T&&T.createWorker);
        return{attempts,firstFailed,secondLoaded};
      }finally{
        HTMLHeadElement.prototype.appendChild=original;
        if(previous===undefined)delete window.Tesseract;else window.Tesseract=previous;
      }
    """)
    c.eq(r['attempts'],2,'failed OCR script is removed and a fresh download is attempted')
    c.true(r['firstFailed'],'first failed download is surfaced')
    c.true(r['secondLoaded'],'OCR engine can initialize on a later attempt')
    await ctx.close()


@test
async def local_tesseract_worker_loads_and_recognizes_invoice_text(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,"""
      await new Promise((resolve,reject)=>{
        const s=document.createElement('script');s.src='./vendor/tesseract/tesseract.min.js';
        s.onload=resolve;s.onerror=()=>reject(new Error('local tesseract.min.js failed to load'));
        document.head.appendChild(s);
      });
      const worker=await Promise.race([Tesseract.createWorker('eng',1,{
        workerPath:'./vendor/tesseract/worker.min.js',
        langPath:'./vendor/tesseract/lang/',
        corePath:'./vendor/tesseract/core/',
        gzip:true
      }),new Promise((_,reject)=>setTimeout(()=>reject(new Error('Tesseract worker initialization timed out')),40000))]);
      try{
        const canvas=document.createElement('canvas');canvas.width=1400;canvas.height=300;
        const cx=canvas.getContext('2d');cx.fillStyle='#fff';cx.fillRect(0,0,1400,300);
        cx.fillStyle='#000';cx.font='bold 140px Arial';cx.fillText('INVOICE 12345',40,190);
        const result=await Promise.race([worker.recognize(canvas),new Promise((_,reject)=>setTimeout(()=>reject(new Error('Tesseract OCR recognition timed out')),40000))]);
        return{loaded:true,text:String(result.data.text||''),confidence:Number(result.data.confidence)||0};
      }finally{await worker.terminate()}
    """)
    c.true(r['loaded'],'local Tesseract worker and core initialize successfully')
    c.true('12345' in r['text'].replace(' ','').replace('\\n',''),'local OCR recognizes the invoice number')
    c.true(r['confidence']>0,'OCR returns a confidence score')
    c.eq(pg.errs,[],'OCR smoke test produces no uncaught page errors')
    await ctx.close()


@test
async def local_persian_tesseract_model_loads_and_processes_mixed_invoice_text(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,"""
      await new Promise((resolve,reject)=>{
        const script=document.createElement('script');script.src='./vendor/tesseract/tesseract.min.js';
        script.onload=resolve;script.onerror=()=>reject(new Error('local Tesseract.js failed to load for Persian OCR'));
        document.head.appendChild(script);
      });
      const workers=await Promise.race([Promise.all([getLocalOCRWorker(),getLocalOCRWorker()]),
        new Promise((_,reject)=>setTimeout(()=>reject(new Error('Persian Tesseract initialization timed out')),60000))]);
      const worker=workers[0];
      const sameWorker=workers[0]===workers[1];
      try{
        /* Use the app's bundled Persian font: CI runners do not guarantee Tahoma. */
        const font=new FontFace('UniqueOCRTest','url(./vendor/fonts/vazirmatn-arabic.woff2)');
        await font.load();document.fonts.add(font);await document.fonts.ready;
        const canvas=document.createElement('canvas');canvas.width=1600;canvas.height=360;
        const cx=canvas.getContext('2d');cx.fillStyle='#fff';cx.fillRect(0,0,1600,360);
        cx.fillStyle='#000';cx.textAlign='right';cx.direction='rtl';
        cx.font='bold 150px UniqueOCRTest';cx.fillText('فاکتور',1500,230);
        /* Keep the Latin invoice number in a separate LTR run to avoid bidi ambiguity. */
        cx.textAlign='left';cx.direction='ltr';cx.font='bold 140px Arial';
        cx.fillText('12345',80,230);
        const result=await Promise.race([worker.recognize(canvas),new Promise((_,reject)=>setTimeout(()=>reject(new Error('Persian OCR recognition timed out')),60000))]);
        return{loaded:true,sameWorker,text:String(result.data.text||''),confidence:Number(result.data.confidence)||0};
      }finally{await worker.terminate()}
    """)
    constText = r['text'].replace(' ','').replace('\\n','')
    c.true(r['sameWorker'],'concurrent OCR requests share one initialized worker')
    c.true(r['loaded'],'Persian and English traineddata load in the local worker')
    c.true(any(chr(0x0600) <= ch <= chr(0x06FF) for ch in constText),'Persian OCR recognizes Persian glyphs; extracted: '+r['text'])
    c.true('12345' in constText,'Persian OCR preserves the invoice number; extracted: '+r['text'])
    c.eq(pg.errs,[],'Persian OCR produces no uncaught page errors')
    await ctx.close()


@test
async def offline_ocr_pack_is_cached_and_served_without_network(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,"""
      await navigator.serviceWorker.ready;
      for(let i=0;i<40&&!navigator.serviceWorker.controller;i++)await new Promise(resolve=>setTimeout(resolve,250));
      if(!navigator.serviceWorker.controller)throw new Error('service worker did not take control');
      const sw=navigator.serviceWorker.controller;
      const ready=new Promise((resolve,reject)=>{
        const timer=setTimeout(()=>reject(new Error('OCR precache timed out')),120000);
        const handler=e=>{
          if(e.data?.type==='OCR_READY'){clearTimeout(timer);navigator.serviceWorker.removeEventListener('message',handler);resolve(e.data)}
          if(e.data?.type==='OCR_ERROR'){clearTimeout(timer);navigator.serviceWorker.removeEventListener('message',handler);reject(new Error(e.data.message||'OCR precache failed'))}
        };
        navigator.serviceWorker.addEventListener('message',handler);
      });
      sw.postMessage({type:'PRECACHE_OCR'});
      const downloaded=await ready;
      const files=[
        './vendor/tesseract/tesseract.min.js','./vendor/tesseract/worker.min.js',
        './vendor/tesseract/core/tesseract-core-simd-lstm.wasm.js',
        './vendor/tesseract/core/tesseract-core-lstm.wasm.js',
        './vendor/tesseract/lang/fas.traineddata.gz','./vendor/tesseract/lang/eng.traineddata.gz'
      ];
      const status=await new Promise((resolve,reject)=>{
        const timer=setTimeout(()=>reject(new Error('OCR_STATUS timed out')),10000);
        const handler=e=>{if(e.data?.type==='OCR_STATUS'){clearTimeout(timer);navigator.serviceWorker.removeEventListener('message',handler);resolve(e.data)}};
        navigator.serviceWorker.addEventListener('message',handler);sw.postMessage({type:'OCR_STATUS'});
      });
      return{downloaded,status,files};
    """)
    c.eq(r['status']['cached'],6,'all six OCR assets are cached')
    c.eq(r['status']['ready'],True,'OCR pack reports ready after download')
    await ctx.set_offline(True)
    offline=await pg.evaluate("""async files=>{
      const results=[];
      for(const path of files){const response=await fetch(path);results.push({path,ok:response.ok,status:response.status})}
      return results;
    }""",r['files'])
    c.true(all(x['ok'] for x in offline),'all OCR assets are served from cache with network disabled')
    await ctx.set_offline(False)
    c.eq(pg.errs,[],'offline OCR cache test produces no uncaught page errors')
    await ctx.close()


@test
async def file_transfer_restores_complete_encrypted_snapshot(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,"""
      const S=await T.seed({});
      db.customers.push({id:'local-only-customer',name:'مشتری مقصد'});
      const destinationDevice=window.UniqueTransfer.deviceId();
      const env=window.UniqueTransfer.createEnvelope();
      env.deviceId='DEV-SOURCE-DEVICE';
      env.data.pro.sync.deviceId=env.deviceId;
      env.data.customers=env.data.customers.filter(x=>x.id!=='local-only-customer');
      env.data.customers.push({id:'incoming-transfer-customer',name:'مشتری مبدأ'});
      env.checksum=window.UniqueTransfer.checksum({app:env.app,schema:env.schema,version:env.version,deviceId:env.deviceId,createdAt:env.createdAt,data:env.data});
      const raw=await window.yqEncryptBackup(JSON.stringify(env),'TransferPass123');
      window.prompt=()=> 'TransferPass123';window.confirm=()=>true;
      const dt=new DataTransfer();dt.items.add(new File([raw],'transfer.enc.json',{type:'application/json'}));
      const before=db.customers.length;
      page='sync';render();await T.sleep(80);
      const input=document.querySelector('#sif');if(!input)throw new Error('sync UI missing: '+JSON.stringify({page,proSync:typeof window.proSync,transferUI:typeof window.UniqueTransferUI,content:!!document.querySelector('#content'),text:document.querySelector('#content')?.innerText?.slice(0,240),error:document.querySelector('.error-inline pre')?.innerText}));Object.defineProperty(input,'files',{configurable:true,value:dt.files});
      input.dispatchEvent(new Event('change',{bubbles:true}));await T.sleep(250);
      const preview=!!document.querySelector('#sapply');
      const previewText=document.querySelector('#syncResult')?.innerText||'';
      if(preview)document.querySelector('#sapply').click();
      await T.sleep(350);
      return{preview,previewText,before,after:db.customers.length,
        local:db.customers.some(x=>x.id==='local-only-customer'),
        incoming:db.customers.some(x=>x.id==='incoming-transfer-customer'),
        encrypted:JSON.parse(raw).enc==='younique-enc-v1',
        destinationDevice,deviceAfter:db.pro.sync.deviceId,
        sourceDevice:env.deviceId,health:runYouniqueHealthCheck().ok}
    """)
    c.true(r['preview'],'valid encrypted transfer produces an explicit restore preview')
    c.true('پیش‌نمایش نسخهٔ انتقال' in r['previewText'],'preview shows the full restore scope')
    c.true(r['after']>0,'restored dataset remains populated')
    c.eq(r['local'],False,'full restore replaces destination-only records')
    c.true(r['incoming'],'source customer is restored')
    c.true(r['encrypted'],'transfer package uses AES-GCM encrypted envelope')
    c.eq(r['deviceAfter'],r['destinationDevice'],'destination device identity is preserved')
    c.true(r['deviceAfter']!=r['sourceDevice'],'source device identity is not copied to destination')
    c.true(r['health'],'restored data passes business integrity check')
    await ctx.close()


@test
async def file_transfer_rejects_tampered_checksum_without_mutation(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,"""
      const S=await T.seed({});
      const env=window.UniqueTransfer.createEnvelope();
      env.data.customers.push({id:'tampered-transfer-customer',name:'نباید وارد شود'});
      env.checksum='00000000';
      const raw=await window.yqEncryptBackup(JSON.stringify(env),'TransferPass123');
      window.prompt=()=> 'TransferPass123';
      const before=db.customers.length;
      const dt=new DataTransfer();dt.items.add(new File([raw],'tampered.enc.json',{type:'application/json'}));
      page='sync';render();await T.sleep(80);
      const input=document.querySelector('#sif');if(!input)throw new Error('sync UI missing: '+JSON.stringify({page,proSync:typeof window.proSync,transferUI:typeof window.UniqueTransferUI,content:!!document.querySelector('#content'),text:document.querySelector('#content')?.innerText?.slice(0,240),error:document.querySelector('.error-inline pre')?.innerText}));Object.defineProperty(input,'files',{configurable:true,value:dt.files});
      input.dispatchEvent(new Event('change',{bubbles:true}));await T.sleep(250);
      return{before,after:db.customers.length,preview:!!document.querySelector('#sapply'),
        message:document.querySelector('#syncResult')?.innerText||''}
    """)
    c.eq(r['after'],r['before'],'tampered package never mutates local data')
    c.eq(r['preview'],False,'tampered package never presents a replace action')
    c.true('صحت بسته' in r['message'],'checksum failure is explained')
    await ctx.close()



@test
async def returns_and_purchase_void_preserve_original_warehouse(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,'''const S=await T.seed({});
      db.warehouses.push({id:'W2',name:'انبار دوم',active:true});db.warehouseStocks.W2={};saveDB(true);
      const p=await T.buy(S,S.v,4,1000,{cash:4000});
      stockMove(S.v,-4,'test_transfer','T1',1000,undefined,'MAIN');stockMove(S.v,4,'test_transfer','T1',1000,4000,'W2');
      p.warehouseId='W2';for(const id of p.items)db.purchaseItems.find(x=>x.id===id).warehouseId='W2';
      const pi=db.purchaseItems.find(x=>x.variantId===S.v);
      const pr=Fin.purchaseReturn({ref:p.number,qtys:{[pi.id]:1},method:'card',note:'تست انبار دوم'});
      const afterPurchaseReturn={total:variantBy(S.v).stock,main:whStock('MAIN',S.v),w2:whStock('W2',S.v)};
      const p2=await T.buy(S,S.v,2,1000,{cash:2000});
      stockMove(S.v,-2,'test_transfer','T2',1000,undefined,'MAIN');stockMove(S.v,2,'test_transfer','T2',1000,2000,'W2');
      p2.warehouseId='W2';for(const id of p2.items)db.purchaseItems.find(x=>x.id===id).warehouseId='W2';
      Fin.voidPurchase(p2.number,'ابطال تست انبار دوم');
      const afterVoid={total:variantBy(S.v).stock,main:whStock('MAIN',S.v),w2:whStock('W2',S.v)};
      const old=window.saleWarehouseId;window.saleWarehouseId=()=> 'W2';
      const sale=await T.sell(S,S.v,1,1500,{cash:1500});window.saleWarehouseId=old;
      const si=db.saleItems.find(x=>x.variantId===S.v);const sr=Fin.saleReturn({ref:sale.number,qtys:{[si.id]:1},method:'card',note:'تست برگشت فروش انبار دوم'});
      return{pr:!!pr,sr:!!sr,afterPurchaseReturn,afterVoid,afterSaleReturn:{total:variantBy(S.v).stock,main:whStock('MAIN',S.v),w2:whStock('W2',S.v)},unb:T.unbalanced(),health:runYouniqueHealthCheck().ok}''')
    c.true(r['pr'],'purchase return from secondary warehouse succeeds')
    c.eq(r['afterPurchaseReturn'],{'total':3,'main':0,'w2':3},'purchase return decrements the source warehouse')
    c.eq(r['afterVoid'],{'total':3,'main':0,'w2':3},'purchase void removes stock from the original warehouse only')
    c.true(r['sr'],'sale return to secondary warehouse succeeds')
    c.eq(r['afterSaleReturn'],{'total':3,'main':0,'w2':3},'sale return restores stock to the original warehouse')
    c.eq(r['unb'],0,'warehouse return and void journals remain balanced')
    c.true(r['health'],'health check remains valid')
    await ctx.close()


@test
async def all_navigation_pages_render_without_runtime_errors(br,c):
    pg,ctx=await page(br)
    pages=['dashboard','sale','sales','returns','purchase','purchases','products','inventory',
      'barcode','automation','customers','suppliers','finance','reports','ai','documents',
      'backup','settings','accounting','warehouse','crm','insights','security','tax','sync',
      'checks','loans','engine']
    results=[]
    for name in pages:
      await pg.evaluate("(name)=>{window.page=name;window.render()}",name)
      await pg.wait_for_timeout(60)
      state=await pg.evaluate("""()=>({
        content:!!document.querySelector('#content'),
        error:!!document.querySelector('#content .error-inline, .error-screen'),
        text:(document.querySelector('#content')?.innerText||'').trim().slice(0,80)
      })""")
      results.append((name,state))
      c.true(state['content'] and not state['error'] and bool(state['text']),
        'page '+name+' renders useful content without an error screen')
    c.eq(pg.errs,[],'navigation smoke test has no uncaught browser errors')
    await ctx.close()


@test
async def local_persian_nlu_normalizes_colloquial_commands(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,'''const S=await T.seed({});
      UAI.ctx.reset();
      const pairs=[
        ['صندوق چنده','موجودی صندوق چقدره'],
        ['سود','سود این ماه'],
        ['امروز چقدر فروختیم','فروش امروز چقدره']
      ];
      const parsed=pairs.map(([a,b])=>{
        const x=UAI.NLU.understand(a,UAI.ctx),y=UAI.NLU.understand(b,UAI.ctx);
        return {aUnknown:!!x.unknown,bUnknown:!!y.unknown,aIntent:x.intent,bIntent:y.intent};
      });
      const digits=UAI.normalize('۱۲۳٤ كفش ي'),initialStock=variantBy(S.v).stock;
      return {parsed,digits,sales:db.sales.length,initialStock,stock:variantBy(S.v).stock}''')
    for row in r['parsed']:
      c.true(not row['aUnknown'] and not row['bUnknown'],'colloquial command is understood: '+row['aIntent'])
      c.eq(row['aIntent'],row['bIntent'],'colloquial and canonical phrase resolve to the same intent')
    c.eq(r['digits'],'1234 کفش ی','Persian/Arabic digits and Arabic letter forms normalize consistently')
    c.eq(r['sales'],0,'intent parsing does not create invoices')
    c.eq(r['stock'],r['initialStock'],'intent parsing does not mutate inventory')
    await ctx.close()


@test
async def critical_pages_fit_mobile_viewport_without_horizontal_page_overflow(br,c):
    pg,ctx=await page(br)
    await pg.set_viewport_size({"width":360,"height":780})
    r=await ev(pg,'''const pages=['dashboard','sale','purchase','products','inventory','reports','ai','backup','settings'];
      const results=[];
      for(const name of pages){
        window.page=name;window.render();await new Promise(resolve=>setTimeout(resolve,35));
        results.push({name,content:!!document.querySelector('#content'),
          overflow:document.documentElement.scrollWidth>window.innerWidth+1,
          width:document.documentElement.scrollWidth,viewport:window.innerWidth,
          error:!!document.querySelector('#content .error-inline,.error-screen')});
      }
      return results''')
    for row in r:
      c.true(row['content'] and not row['error'],'mobile page renders: '+row['name'])
      c.true(not row['overflow'],'mobile page has no document-level horizontal overflow: '+row['name']+' ('+str(row['width'])+'/'+str(row['viewport'])+')')
    c.eq(pg.errs,[],'mobile navigation has no uncaught browser errors')
    await ctx.close()


@test
async def health_check_detects_catalog_and_journal_integrity_drift(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,'''const S=await T.seed({});
      const clean=runYouniqueHealthCheck();
      const v=variantBy(S.v);v.sku='HEALTH-CHECK-SKU';
      const duplicate={...v,id:'health-duplicate',sku:v.sku,barcode:v.barcode};
      db.variants.push(duplicate);
      const catalog=runYouniqueHealthCheck();
      db.variants.pop();
      const badJournal={id:'health-journal',ref:'HEALTH-JOURNAL',debit:100,credit:100,
        lines:[{account:'cash',debit:40,credit:0},{account:'sales',debit:0,credit:40}]};
      db.journal.push(badJournal);
      const ledger=runYouniqueHealthCheck();
      db.journal.pop();
      return {clean:clean.ok,catalog:catalog.issues,ledger:ledger.issues,
        restored:runYouniqueHealthCheck().ok}''')
    c.true(r['clean'],'a valid seeded store passes the expanded integrity check')
    c.true(any('SKU تکراری' in x for x in r['catalog']),'duplicate SKU is detected')
    c.true(any('بارکد تکراری' in x for x in r['catalog']),'duplicate barcode is detected')
    c.true(any('ترکیب رنگ و سایز تکراری' in x for x in r['catalog']),'duplicate variant combination is detected')
    c.true(any('جمع ردیف‌های سند' in x for x in r['ledger']),'journal line/header mismatch is detected')
    c.true(r['restored'],'removing test corruption restores a healthy status')
    await ctx.close()


@test
async def exclusive_sale_returns_reconcile_dashboard_and_management_reports(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,'''const S=await T.seed({vat:10});
      await T.buy(S,S.v,10,1000,{cash:11000});
      const sale=await T.sell(S,S.v,3,1500,{cash:4950});
      const ret=Fin.saleReturn({ref:sale.number,qtys:{[sale.items[0]]:1},method:'cash',note:'report test'});
      const t=totals();page='reports';render();
      const body=document.querySelector('#content').innerText;
      return {return:{total:ret.total,vat:ret.vat,refund:ret.refund},revenue:t.revenue,profit:t.profit,
        reportRevenue:body.includes(money(3300)),reportProfit:body.includes(money(1000)),
        returnRow:body.includes('برگشت فروش'),body:body.slice(0,1600),reportError:!!document.querySelector('#content .error-inline'),unb:T.unbalanced()}''')
    c.eq(r['return'],{'total':1500,'vat':150,'refund':1650},'exclusive VAT return totals')
    c.eq(r['revenue'],3300,'dashboard revenue subtracts the full refund including VAT')
    c.eq(r['profit'],1000,'dashboard profit subtracts returned net revenue less returned cost')
    c.true(r['reportRevenue'],'management report shows net revenue: '+r['body'])
    c.true(r['reportProfit'],'management report shows net gross profit: '+r['body'])
    c.true(r['returnRow'],'management report lists the sale return: '+r['body'])
    c.eq(r['unb'],0,'return journal remains balanced')
    await ctx.close()


@test
async def inclusive_sale_returns_remove_vat_from_profit_reversal(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,'''const S=await T.seed({vat:9,mode:'inclusive'});
      await T.buy(S,S.v,7,333,{cash:2331});
      const sale=await T.sell(S,S.v,3,999,{cash:2997});
      const ret=Fin.saleReturn({ref:sale.number,qtys:{[sale.items[0]]:1},method:'cash',note:'inclusive report test'});
      const t=totals();page='reports';render();
      const body=document.querySelector('#content').innerText;
      return {saleProfit:sale.profit,return:{total:ret.total,vat:ret.vat,cost:ret.costTotal},
        revenue:t.revenue,profit:t.profit,reportRevenue:body.includes(money(1998)),
        reportProfit:body.includes(money(1222)),body:body.slice(0,1600),unb:T.unbalanced()}''')
    c.eq(r['return'],{'total':999,'vat':82,'cost':306},'inclusive return retains its VAT and actual FIFO cost components')
    c.eq(r['revenue'],1998,'inclusive net revenue subtracts the refunded gross amount')
    c.eq(r['profit'],1222,'inclusive profit reversal excludes VAT from returned profit')
    c.true(r['reportRevenue'],'management report shows inclusive net revenue: '+r['body'])
    c.true(r['reportProfit'],'management report shows VAT-adjusted net profit: '+r['body'])
    c.eq(r['unb'],0,'inclusive return journal remains balanced')
    await ctx.close()


@test
async def final_store_acceptance_purchase_sale_return_reports_and_backup(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,'''const S=await T.seed({vat:10});
      const purchase=await T.buy(S,S.v,10,1000,{cash:3000,card:2000,bank:1000,credit:5000});
      const sale=await T.sell(S,S.v,3,1500,{cash:1500,card:1000,bank:500,credit:1950});
      const ret=Fin.saleReturn({ref:sale.number,qtys:{[sale.items[0]]:1},method:'cash',note:'final acceptance'});
      const totalsNow=totals();window.reports();
      const reportText=document.querySelector('#content').innerText;
      const backup=JSON.parse(exportData()),summary=validateBackupData(backup.data);
      return {
        purchase:{total:purchase.total,paid:purchase.paid,due:purchase.due,split:purchase.payments.reduce((a,x)=>a+num(x.amount),0)},
        sale:{total:sale.total,paid:sale.paid,due:sale.due,split:sale.payments.reduce((a,x)=>a+num(x.amount),0)},
        returned:{refund:ret.refund,qty:ret.items.reduce((a,x)=>a+num(x.qty),0)},
        stock:variantBy(S.v).stock,revenue:totalsNow.revenue,profit:totalsNow.profit,
        reportNet:reportText.includes(money(3300)),reportReturn:reportText.includes('برگشت فروش'),
        backup:summary,health:runYouniqueHealthCheck().ok,unbalanced:T.unbalanced()
      }''')
    c.eq(r['purchase'],{'total':11000,'paid':6000,'due':5000,'split':11000},'purchase payment split and supplier balance reconcile')
    c.eq(r['sale'],{'total':4950,'paid':3000,'due':1950,'split':4950},'sale payment split and customer balance reconcile')
    c.eq(r['returned'],{'refund':1650,'qty':1},'sale return is posted with correct VAT-inclusive refund')
    c.eq(r['stock'],8,'final stock equals purchases minus net sales')
    c.eq(r['revenue'],3300,'dashboard net revenue matches the end-to-end workflow')
    c.eq(r['profit'],1000,'dashboard net profit matches the end-to-end workflow')
    c.true(r['reportNet'] and r['reportReturn'],'management report includes net sales and return rows')
    c.eq(r['backup'],{'products':1,'variants':1,'sales':1,'purchases':1,'customers':1,'suppliers':1},'full backup validates after the workflow')
    c.true(r['health'],'final data integrity check passes')
    c.eq(r['unbalanced'],0,'all purchase, sale and return journal entries remain balanced')
    await ctx.close()


@test
async def offline_voice_dialog_uses_local_assistant_and_manual_fallback(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,'''const has=typeof window.yqVoiceDraft==='function'&&typeof window.UAI?.ui?.submit==='function';
      window.yqVoiceDraft('assistant');
      const dialog=document.querySelector('#modal');
      const visible=!!dialog&&dialog.classList.contains('show');
      const title=dialog&&dialog.innerText.includes('دستیار گفتاری آفلاین فارسی');
      document.querySelector('#yqVText').click();
      await new Promise(r=>setTimeout(r,50));
      const manual=document.querySelector('#yqVManual');
      if(manual){manual.value='سلام، گزارش فروش امروز را نشان بده';document.querySelector('#yqVManualApply').click();await new Promise(r=>setTimeout(r,350));}
      return{has,visible,title,manual:!!manual,submitted:window.UAI.ui.transcript.some(x=>x.role==='user'&&x.text.includes('گزارش فروش امروز'))}''')
    c.true(r['has'],'offline voice module connects to the existing local assistant')
    c.true(r['visible'] and r['title'],'voice dialog opens inside the existing modal')
    c.true(r['manual'],'manual text fallback remains available')
    c.true(r['submitted'],'manual fallback submits text to the local assistant')
    c.eq(pg.errs,[],'no browser page errors')
    await ctx.close()



@test
async def cash_session_open_and_close_roll_back_on_persistence_failure(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,'''const originalPersist=window._persist;
      db.cashSessions=[];db.cashMovements=[];db.journal=[];db.audit=[];saveDB(true);
      const j0=db.journal.length;
      window._persist=()=>false;let openError='';
      try{openCashSession(500,'failed open','test')}catch(e){openError=e.message}
      window._persist=originalPersist;saveDB(true);
      const openState={error:!!openError,sessions:db.cashSessions.length,journals:db.journal.length-j0,
        openingAudits:db.audit.filter(x=>x.action==='باز کردن صندوق').length};
      const session=openCashSession(1000,'close test','test');
      const expected=cashSessionExpected(session),beforeJ=db.journal.length;
      window._persist=()=>false;let closeError='';
      try{closeCashSession(expected-100,'variance test','test')}catch(e){closeError=e.message}
      window._persist=originalPersist;saveDB(true);
      const active=activeCashSession();
      return{openState,close:{error:!!closeError,status:active?.status,journalDelta:db.journal.length-beforeJ,
        varianceRef:active?.varianceJournalRef||null,expected:cashSessionExpected(active),opening:active?.openingCash},
        health:runYouniqueHealthCheck().ok}''')
    c.eq(r['openState'],{'error':True,'sessions':0,'journals':0,'openingAudits':0},
      'failed cash opening rolls back session, opening journal and opening audit')
    c.eq(r['close'],{'error':True,'status':'open','journalDelta':0,'varianceRef':None,'expected':1000,'opening':1000},
      'failed cash closing rolls back variance journal and keeps the session open')
    c.true(r['health'],'cash persistence rollback preserves a healthy database')
    c.eq(pg.errs,[],'cash rollback produces no uncaught browser errors')
    await ctx.close()


@test
async def failed_purchase_persistence_preserves_draft_and_rolls_back(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,'''const S=await T.seed({});
      page='purchase';render();await T.sleep(100);
      addPurchase(S.v);purchaseCart[0].qty=2;purchaseCart[0].price=1000;renderPurchaseCart();
      document.querySelector('#purSup').value=S.sup;
      document.querySelector('#purCash').value='2000';
      document.querySelector('#purCard').value='0';
      document.querySelector('#purBank').value='0';
      document.querySelector('#purCredit').value='0';
      renderPurchasePaymentSummary();
      const before={j:db.journal.length,p:db.payments.length,stock:variantBy(S.v).stock};
      const originalPersist=window._persist;window._persist=()=>false;
      savePurchase();
      window._persist=originalPersist;saveDB(true);
      return{purchases:db.purchases.length,items:db.purchaseItems.length,
        stock:variantBy(S.v).stock,journalDelta:db.journal.length-before.j,
        paymentDelta:db.payments.length-before.p,cart:purchaseCart.map(x=>[x.qty,x.price]),
        page,health:runYouniqueHealthCheck().ok,messages:T.msgs.slice()}''')
    c.eq(r['purchases'],0,'failed persistence creates no purchase')
    c.eq(r['items'],0,'failed persistence creates no purchase lines')
    c.eq(r['stock'],0,'failed persistence leaves inventory unchanged')
    c.eq(r['journalDelta'],0,'failed persistence leaves no journal entries')
    c.eq(r['paymentDelta'],0,'failed persistence leaves no payment records')
    c.eq(r['cart'],[[2,1000]],'failed persistence preserves the purchase draft')
    c.eq(r['page'],'purchase','failed persistence keeps the purchase page open')
    c.true(not any('با موفقیت ثبت شد' in x for x in r['messages']),'failed persistence never shows a purchase success message')
    c.true(r['health'],'failed purchase rollback preserves database integrity')
    c.eq(pg.errs,[],'purchase persistence failure produces no uncaught browser errors')
    await ctx.close()



@test
async def cash_opening_variance_is_atomic_with_session_creation(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,'''const originalPersist=window._persist;
      db.cashSessions=[];db.cashMovements=[];db.journal=[];db.audit=[];saveDB(true);
      openCashSession(1000,'first shift','test');
      closeCashSession(1000,'close first shift','test');
      const before={sessions:db.cashSessions.length,journal:db.journal.length,openingAudits:db.audit.filter(x=>String(x.action).startsWith('باز کردن صندوق')).length,cash:accountBalance('cash')};
      window._persist=()=>false;let error='';
      try{openCashSession(900,'second shift','test')}catch(e){error=e.message}
      window._persist=originalPersist;saveDB(true);
      const failed={sessions:db.cashSessions.length,journal:db.journal.length,openingAudits:db.audit.filter(x=>String(x.action).startsWith('باز کردن صندوق')).length,
        variance:db.journal.filter(j=>j.entryType==='cash_open_variance').length,active:!!activeCashSession()};
      const second=openCashSession(900,'second shift retry','test');
      const variance=db.journal.find(j=>j.ref===second.number+'-OPEN-VARIANCE');
      return{before,failed,error:!!error,success:{sessions:db.cashSessions.length,variance:variance&&variance.variance,
        entryType:variance&&variance.entryType,balanced:variance&&Math.abs(variance.debit-variance.credit)<0.01,
        cash:accountBalance('cash'),health:runYouniqueHealthCheck().ok}}
    ''')
    c.eq(r['before']['cash'],1000,'first shift establishes the ledger cash balance')
    c.true(r['error'],'failed persistence is surfaced to the caller')
    c.eq(r['failed'],{'sessions':1,'journal':r['before']['journal'],'openingAudits':r['before']['openingAudits'],'variance':0,'active':False},
      'failed second opening rolls back the session and opening variance together')
    c.eq(r['success']['sessions'],2,'retry opens the next cash session')
    c.eq(r['success']['variance'],-100,'opening shortage equals counted cash minus ledger cash')
    c.eq(r['success']['entryType'],'cash_open_variance','opening variance has a dedicated journal type')
    c.true(r['success']['balanced'],'opening variance journal is balanced')
    c.eq(r['success']['cash'],900,'cash ledger reconciles to the counted opening amount')
    c.true(r['success']['health'],'database integrity remains valid after reconciliation')
    c.eq(pg.errs,[],'opening variance rollback produces no uncaught browser errors')
    await ctx.close()


@test
async def customer_payment_failure_rolls_back_all_ledgers(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,'''const S=await T.seed({});await T.buy(S,S.v,2,1000,{cash:2000});
      await T.sell(S,S.v,1,1500,{credit:1500});
      const before={balance:customerBalance(S.cus),payments:db.payments.length,journal:db.journal.length,
        cashMoves:db.cashMovements.length,cash:accountBalance('cash'),receivable:accountBalance('receivable','customer',S.cus)};
      personPayment('customer',S.cus);await T.sleep(80);
      document.querySelector('#pa').value='400';document.querySelector('#pac').value='صندوق';
      document.querySelector('#pnote').value='تست دریافت';
      const originalPersist=window._persist;window._persist=()=>false;
      document.querySelector('#payf').dispatchEvent(new Event('submit',{cancelable:true,bubbles:true}));
      window._persist=originalPersist;saveDB(true);await T.sleep(80);
      return{before,after:{balance:customerBalance(S.cus),payments:db.payments.length,journal:db.journal.length,
        cashMoves:db.cashMovements.length,cash:accountBalance('cash'),receivable:accountBalance('receivable','customer',S.cus)},
        modal:!!document.querySelector('#payf'),health:runYouniqueHealthCheck().ok}
    ''')
    c.eq(r['before']['balance'],1500,'customer has an outstanding receivable before payment')
    c.eq(r['after']['balance'],r['before']['balance'],'failed payment leaves customer balance unchanged')
    c.eq(r['after']['payments'],r['before']['payments'],'failed payment creates no payment row')
    c.eq(r['after']['journal'],r['before']['journal'],'failed payment creates no journal entry')
    c.eq(r['after']['cashMoves'],r['before']['cashMoves'],'failed payment creates no cash movement')
    c.eq(r['after']['cash'],r['before']['cash'],'failed payment leaves cash balance unchanged')
    c.eq(r['after']['receivable'],r['before']['receivable'],'failed payment leaves receivable ledger unchanged')
    c.true(r['modal'],'failed payment keeps the form available for retry')
    c.true(r['health'],'failed payment rollback preserves database integrity')
    c.eq(pg.errs,[],'failed payment produces no uncaught browser errors')
    await ctx.close()


@test
async def sale_persistence_failure_rolls_back_invoice_and_preserves_draft(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,'''const S=await T.seed({});await T.buy(S,S.v,2,1000,{cash:2000});
      page='sale';render();await T.sleep(100);addSale(S.v);saleCart[0].qty=1;saleCart[0].price=1500;renderSaleCart();
      window.__salePayments={cash:700,card:800,bank:0,credit:0};
      const before={sales:db.sales.length,items:db.saleItems.length,journal:db.journal.length,payments:db.payments.length,
        moves:db.cashMovements.length,stock:variantBy(S.v).stock,cash:accountBalance('cash'),card:accountBalance('card')};
      const originalSaveDB=window.saveDB;window.saveDB=()=>false;saveSale();window.saveDB=originalSaveDB;saveDB(true);
      return{before,after:{sales:db.sales.length,items:db.saleItems.length,journal:db.journal.length,payments:db.payments.length,
        moves:db.cashMovements.length,stock:variantBy(S.v).stock,cash:accountBalance('cash'),card:accountBalance('card')},
        cart:saleCart.map(x=>[x.qty,x.price]),page,health:runYouniqueHealthCheck().ok}
    ''')
    c.eq(r['after'],r['before'],'failed sale persistence rolls back every ledger and stock mutation')
    c.eq(r['cart'],[[1,1500]],'failed sale preserves the editable sale draft')
    c.eq(r['page'],'sale','failed sale keeps the POS page open')
    c.true(r['health'],'failed sale rollback preserves database integrity')
    c.eq(pg.errs,[],'sale persistence failure produces no uncaught browser errors')
    await ctx.close()




@test
async def return_persistence_failure_rolls_back_stock_and_ledgers(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,"""
      const S=await T.seed({});const purchase=await T.buy(S,S.v,5,1000,{cash:5000});
      const sale=await T.sell(S,S.v,1,1500,{cash:1500});
      const saleItem=db.saleItems.find(x=>x.id===sale.items[0]);
      const purchaseItem=db.purchaseItems.find(x=>x.id===purchase.items[0]);
      const snap=()=>({returns:db.returns.length,stock:variantBy(S.v).stock,
        stockMoves:db.stockMoves.length,warehouseMoves:db.warehouseMoves.length,
        payments:db.payments.length,journal:db.journal.length,
        inventory:accountBalance('inventory'),cash:accountBalance('cash'),card:accountBalance('card')});
      const beforeSale=snap(),originalSaveDB=window.saveDB;
      window.saveDB=()=>false;let saleError='';
      try{Fin.saleReturn({ref:sale.number,qtys:{[saleItem.id]:1},method:'card'})}catch(e){saleError=e.message}
      window.saveDB=originalSaveDB;saveDB(true);const afterSale=snap();
      const beforePurchase=snap();window.saveDB=()=>false;let purchaseError='';
      try{Fin.purchaseReturn({ref:purchase.number,qtys:{[purchaseItem.id]:1},method:'card'})}catch(e){purchaseError=e.message}
      window.saveDB=originalSaveDB;saveDB(true);const afterPurchase=snap();
      return{saleError:!!saleError,beforeSale,afterSale,purchaseError:!!purchaseError,
        beforePurchase,afterPurchase,health:runYouniqueHealthCheck().ok,unb:T.unbalanced()}
    """)
    c.true(r['saleError'],'sale return persistence failure is surfaced')
    c.eq(r['afterSale'],r['beforeSale'],'failed sale return restores stock, payments, journals and movement ledgers')
    c.true(r['purchaseError'],'purchase return persistence failure is surfaced')
    c.eq(r['afterPurchase'],r['beforePurchase'],'failed purchase return restores stock, payments, journals and movement ledgers')
    c.true(r['health'],'return rollback preserves business data integrity')
    c.eq(r['unb'],0,'return rollback leaves balanced journals')
    c.eq(pg.errs,[],'return persistence rollback produces no uncaught browser errors')
    await ctx.close()




@test
async def invoice_void_persistence_failure_rolls_back_all_ledgers(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,"""
      const snap=(S,doc,type)=>JSON.stringify({
        status:doc.status,stock:variantBy(S.v).stock,
        warehouse:db.warehouseStocks.MAIN[S.v],
        stockMoves:db.stockMoves,warehouseMoves:db.warehouseMoves,
        payments:db.payments,journal:db.journal,
        cashMoves:db.cashMovements,inventory:accountBalance('inventory'),
        cash:accountBalance('cash'),card:accountBalance('card'),
        costLayers:db.costLayers[S.v]
      });
      const S1=await T.seed({});const salePurchase=await T.buy(S1,S1.v,4,1000,{cash:4000});
      const sale=await T.sell(S1,S1.v,1,1500,{cash:1500});
      const beforeSale=snap(S1,sale,'sale'),originalSaveDB=window.saveDB;
      window.saveDB=()=>false;let saleError='';
      try{Fin.voidSale(sale.number,'test persistence failure')}catch(e){saleError=e.message}
      window.saveDB=originalSaveDB;saveDB(true);
      const afterSale=snap(S1,sale,'sale');
      const active=activeCashSession();if(active)closeCashSession(cashSessionExpected(active),'close sale void test shift','test');
      const S2=await T.seed({});const purchase=await T.buy(S2,S2.v,4,1000,{cash:4000});
      const beforePurchase=snap(S2,purchase,'purchase');
      window.saveDB=()=>false;let purchaseError='';
      try{Fin.voidPurchase(purchase.number,'test persistence failure')}catch(e){purchaseError=e.message}
      window.saveDB=originalSaveDB;saveDB(true);
      const afterPurchase=snap(S2,purchase,'purchase');
      return{saleError:!!saleError,beforeSale,afterSale,purchaseError:!!purchaseError,
        beforePurchase,afterPurchase,health:runYouniqueHealthCheck().ok,unb:T.unbalanced()};
    """)
    c.true(r['saleError'],'sale void persistence failure is surfaced')
    c.eq(r['afterSale'],r['beforeSale'],'failed sale void restores status, stock, payments, journals and movement ledgers')
    c.true(r['purchaseError'],'purchase void persistence failure is surfaced')
    c.eq(r['afterPurchase'],r['beforePurchase'],'failed purchase void restores status, stock, cost layers and ledgers')
    c.true(r['health'],'void rollback preserves database integrity')
    c.eq(r['unb'],0,'void rollback leaves balanced journals')
    c.eq(pg.errs,[],'void persistence rollback produces no uncaught browser errors')
    await ctx.close()


@test
async def warehouse_stock_reconciliation_is_reported(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,"""
      const S=await T.seed({});
      await T.buy(S,S.v,4,1000,{cash:4000});
      const healthy=runYouniqueHealthCheck();
      const before=variantBy(S.v).stock;
      db.warehouseStocks.MAIN[S.v]=num(db.warehouseStocks.MAIN[S.v])+1;
      const broken=runYouniqueHealthCheck();
      db.warehouseStocks.MAIN[S.v]=before;
      const repaired=runYouniqueHealthCheck();
      return{healthy:healthy.ok,broken:broken.issues.some(x=>x.includes('عدم تطابق مجموع موجودی انبارها')),
        repaired:repaired.ok,stock:variantBy(S.v).stock,warehouse:db.warehouseStocks.MAIN[S.v]};
    """)
    c.true(r['healthy'],'balanced warehouse stock passes integrity check')
    c.true(r['broken'],'warehouse/variant stock mismatch is detected')
    c.true(r['repaired'],'restoring warehouse quantity clears the integrity warning')
    c.eq(r['stock'],r['warehouse'],'warehouse total equals variant stock')
    c.eq(pg.errs,[],'stock reconciliation check produces no browser errors')
    await ctx.close()


@test
async def returns_cannot_exceed_original_quantity_or_be_voided(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,"""
      const S=await T.seed({});
      const purchase=await T.buy(S,S.v,3,1000,{cash:3000});
      const sale=await T.sell(S,S.v,2,1500,{cash:3000});
      const si=db.saleItems.find(x=>x.id===sale.items[0]);
      const pi=db.purchaseItems.find(x=>x.id===purchase.items[0]);
      const saleFirst=Fin.saleReturn({ref:sale.number,qtys:{[si.id]:1},method:'card'});
      const saleBefore={returns:db.returns.length,stock:variantBy(S.v).stock,journal:db.journal.length};
      let saleOver='',saleVoid='';
      try{Fin.saleReturn({ref:sale.number,qtys:{[si.id]:2},method:'card'})}catch(e){saleOver=e.message}
      try{Fin.voidSale(sale.number,'تست پس از برگشت')}catch(e){saleVoid=e.message}
      const saleAfter={returns:db.returns.length,stock:variantBy(S.v).stock,journal:db.journal.length};
      const purchaseFirst=Fin.purchaseReturn({ref:purchase.number,qtys:{[pi.id]:1},method:'card'});
      const purchaseBefore={returns:db.returns.length,stock:variantBy(S.v).stock,journal:db.journal.length};
      let purchaseOver='',purchaseVoid='';
      try{Fin.purchaseReturn({ref:purchase.number,qtys:{[pi.id]:3},method:'card'})}catch(e){purchaseOver=e.message}
      try{Fin.voidPurchase(purchase.number,'تست پس از برگشت')}catch(e){purchaseVoid=e.message}
      const purchaseAfter={returns:db.returns.length,stock:variantBy(S.v).stock,journal:db.journal.length};
      return{saleFirst:!!saleFirst,saleOver:!!saleOver,saleVoid:!!saleVoid,saleBefore,saleAfter,
        purchaseFirst:!!purchaseFirst,purchaseOver:!!purchaseOver,purchaseVoid:!!purchaseVoid,
        purchaseBefore,purchaseAfter,health:runYouniqueHealthCheck().ok,unb:T.unbalanced()};
    """)
    c.true(r['saleFirst'],'partial sale return is accepted')
    c.true(r['saleOver'],'sale return quantity cannot exceed remaining invoice quantity')
    c.true(r['saleVoid'],'sale with a registered return cannot be voided')
    c.eq(r['saleAfter'],r['saleBefore'],'rejected sale over-return and void attempts leave all ledgers unchanged')
    c.true(r['purchaseFirst'],'partial purchase return is accepted')
    c.true(r['purchaseOver'],'purchase return quantity cannot exceed remaining invoice quantity')
    c.true(r['purchaseVoid'],'purchase with a registered return cannot be voided')
    c.eq(r['purchaseAfter'],r['purchaseBefore'],'rejected purchase over-return and void attempts leave all ledgers unchanged')
    c.true(r['health'],'return guardrails preserve database integrity')
    c.eq(r['unb'],0,'return guardrails preserve balanced journals')
    c.eq(pg.errs,[],'return guardrails produce no uncaught browser errors')
    await ctx.close()

@test
async def invoice_payment_split_reconciliation_is_reported(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,"""
      const S=await T.seed({});
      const purchase=await T.buy(S,S.v,3,1000,{cash:3000});
      const sale=await T.sell(S,S.v,1,1500,{cash:1500});
      const healthy=runYouniqueHealthCheck();
      sale.payments[0].amount+=1;
      const brokenSale=runYouniqueHealthCheck();
      sale.payments[0].amount-=1;
      purchase.due=1;
      const brokenPurchase=runYouniqueHealthCheck();
      purchase.due=0;
      const repaired=runYouniqueHealthCheck();
      return{healthy:healthy.ok,sale:brokenSale.issues.some(x=>x.includes('مغایرت تفکیک پرداخت فاکتور فروش')),
        purchase:brokenPurchase.issues.some(x=>x.includes('مغایرت تفکیک پرداخت فاکتور خرید')),
        repaired:repaired.ok,unb:T.unbalanced()};
    """)
    c.true(r['healthy'],'valid sale and purchase payment splits pass health check')
    c.true(r['sale'],'sale payment amount mismatch is detected')
    c.true(r['purchase'],'purchase paid/due mismatch is detected')
    c.true(r['repaired'],'restoring invoice payment values clears integrity warnings')
    c.eq(r['unb'],0,'payment split validation does not unbalance accounting journals')
    c.eq(pg.errs,[],'invoice payment reconciliation produces no browser errors')
    await ctx.close()


@test
async def stock_moves_reject_invalid_warehouses_and_stocktake_overdraw(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,""" 
      const S=await T.seed({});
      await T.buy(S,S.v,3,1000,{cash:3000});
      db.warehouses.push({id:'OFF',name:'انبار غیرفعال',active:false});
      db.warehouses.push({id:'EMPTY',name:'انبار خالی',active:true});
      db.warehouseStocks.EMPTY={};
      const snap=()=>JSON.stringify({
        stock:variantBy(S.v).stock,
        warehouses:db.warehouseStocks,
        moves:db.stockMoves,
        layers:db.costLayers[S.v]
      });
      const before=snap();let missing='',inactive='',overdraw='';
      try{stockMoveV21(S.v,-1,'adjustment','BAD-WH',1000,undefined,'MISSING')}catch(e){missing=e.message}
      try{stockMoveV21(S.v,-1,'adjustment','BAD-WH',1000,undefined,'OFF')}catch(e){inactive=e.message}
      try{stockMoveV21(S.v,-1,'stocktake','BAD-ST',1000,undefined,'EMPTY')}catch(e){overdraw=e.message}
      const afterRejected=snap();
      const valid=stockMoveV21(S.v,-1,'stocktake','GOOD-ST',1000,undefined,'MAIN');
      return{missing:!!missing,inactive:!!inactive,overdraw:!!overdraw,before,afterRejected,
        stock:variantBy(S.v).stock,main:db.warehouseStocks.MAIN[S.v],valid:valid.cost,
        health:runYouniqueHealthCheck().ok,unb:T.unbalanced(),errors:[]};
    """)
    c.true(r['missing'],'movement rejects an unknown warehouse instead of silently using the default')
    c.true(r['inactive'],'movement rejects an inactive warehouse')
    c.true(r['overdraw'],'stocktake cannot consume more than the selected warehouse balance')
    c.eq(r['afterRejected'],r['before'],'rejected warehouse movements leave stock, cost layers and movement records unchanged')
    c.eq(r['stock'],2,'valid stocktake movement updates global stock')
    c.eq(r['main'],2,'valid stocktake movement updates selected warehouse stock')
    c.true(r['health'],'valid stocktake keeps warehouse and global balances reconciled')
    c.eq(r['unb'],0,'stocktake movement keeps accounting journals balanced')
    c.eq(pg.errs,[],'warehouse movement guardrails produce no browser errors')
    await ctx.close()


@test
async def purchase_order_receipt_rolls_back_partial_multi_line_failure(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,"""
      const S=await T.seed({});
      await T.buy(S,S.v,3,1000,{cash:3000});
      const po={id:'PO-ATOMIC',number:'PO-ATOMIC',status:'draft',supplierId:'',
        lines:[{variantId:S.v,qty:2,received:0,unitCost:1000},{variantId:S.v,qty:2,received:0,unitCost:1000}],total:4000};
      (db.purchaseOrders=db.purchaseOrders||[]).push(po);
      const snap=()=>JSON.stringify({stock:variantBy(S.v).stock,warehouse:db.warehouseStocks.MAIN[S.v],
        moves:db.stockMoves,journal:db.journal,costLayers:db.costLayers[S.v],
        status:db.purchaseOrders.find(x=>x.id===po.id).status,
        received:db.purchaseOrders.find(x=>x.id===po.id).lines.map(x=>x.received)});
      const before=snap();window.receivePO(po.id);
      const form=document.querySelector('#rof41');
      const fields=[...form.querySelectorAll('[data-rq41]')];fields.forEach(x=>x.value='2');
      form.onsubmit({preventDefault(){}});
      const after=snap();
      return{before,after,health:runYouniqueHealthCheck().ok,unb:T.unbalanced(),errors:[]};
    """)
    c.eq(r['after'],r['before'],'failed later receipt line rolls back earlier stock, cost and document mutations')
    c.true(r['health'],'purchase receipt rollback preserves data integrity')
    c.eq(r['unb'],0,'purchase receipt rollback leaves balanced journals')
    c.eq(pg.errs,[],'purchase receipt rollback produces no browser errors')
    await ctx.close()


@test
async def payments_reject_unknown_counterparties_and_zero_after_rounding(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,"""
      await T.seed({});
      const snap=()=>JSON.stringify({payments:db.payments,journal:db.journal,cash:accountBalance('cash'),
        bank:accountBalance('bank'),card:accountBalance('card')});
      const before=snap();let customer='',supplier='',rounded='';
      try{recordPayment({direction:'in',amount:1000,account:'bank',partyType:'customer',partyId:'MISSING-C'})}catch(e){customer=e.message}
      try{recordPayment({direction:'out',amount:1000,account:'bank',partyType:'supplier',partyId:'MISSING-S'})}catch(e){supplier=e.message}
      try{recordPayment({direction:'in',amount:0.001,account:'bank',partyType:'other'})}catch(e){rounded=e.message}
      const after=snap();
      return{customer:!!customer,supplier:!!supplier,rounded:!!rounded,before,after,unb:T.unbalanced(),
        health:runYouniqueHealthCheck().ok,errors:[]};
    """)
    c.true(r['customer'],'payment rejects an unknown customer')
    c.true(r['supplier'],'payment rejects an unknown supplier')
    c.true(r['rounded'],'payment rejects an amount that rounds to zero')
    c.eq(r['after'],r['before'],'rejected payments do not mutate payment rows, journal or account balances')
    c.eq(r['unb'],0,'rejected payments leave balanced journals')
    c.true(r['health'],'payment validation preserves database health')
    c.eq(pg.errs,[],'payment validation produces no browser errors')
    await ctx.close()


@test
async def purchase_order_receipt_uses_order_destination_warehouse(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,"""
      const S=await T.seed({});
      await T.buy(S,S.v,2,1000,{cash:2000});
      db.warehouses.push({id:'ALT-PO',name:'انبار دوم',active:true});
      db.warehouseStocks['ALT-PO']={};
      const po={id:'PO-ALT',number:'PO-ALT',status:'draft',supplierId:'',warehouseId:'ALT-PO',
        lines:[{variantId:S.v,qty:2,received:0,unitCost:1000}],total:2000};
      (db.purchaseOrders=db.purchaseOrders||[]).push(po);
      window.receivePO(po.id);
      const form=document.querySelector('#rof41');
      form.querySelector('[data-rq41="0"]').value='1';
      form.onsubmit({preventDefault(){}});
      return{global:variantBy(S.v).stock,main:db.warehouseStocks.MAIN[S.v]||0,
        alternate:db.warehouseStocks['ALT-PO'][S.v],received:po.lines[0].received,
        destination:po.warehouseId,health:runYouniqueHealthCheck().ok,unb:T.unbalanced(),errors:[]};
    """)
    c.eq(r['global'],3,'partial purchase receipt increases global stock')
    c.eq(r['main'],2,'purchase receipt does not incorrectly route stock to MAIN')
    c.eq(r['alternate'],1,'purchase receipt increases the order destination warehouse')
    c.eq(r['received'],1,'purchase order records the received quantity')
    c.eq(r['destination'],'ALT-PO','purchase order retains its destination warehouse')
    c.true(r['health'],'multi-warehouse purchase receipt preserves stock integrity')
    c.eq(r['unb'],0,'multi-warehouse purchase receipt keeps journals balanced')
    c.eq(pg.errs,[],'multi-warehouse receipt produces no browser errors')
    await ctx.close()


@test
async def purchase_receipt_rejects_fractional_quantity_without_mutation(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,"""
      const S=await T.seed({});
      await T.buy(S,S.v,3,1000,{cash:3000});
      const po={id:'PO-FRACTION',number:'PO-FRACTION',status:'draft',supplierId:'',
        warehouseId:'MAIN',lines:[{variantId:S.v,qty:2,received:0,unitCost:1000}],total:2000};
      (db.purchaseOrders=db.purchaseOrders||[]).push(po);
      const snap=()=>JSON.stringify({stock:variantBy(S.v).stock,warehouse:db.warehouseStocks.MAIN[S.v],
        moves:db.stockMoves.length,journal:db.journal.length,received:po.lines[0].received,status:po.status});
      const before=snap();window.receivePO(po.id);
      const form=document.querySelector('#rof41');
      form.querySelector('[data-rq41="0"]').value='1.5';
      form.onsubmit({preventDefault(){}});
      return{before,after:snap(),errors:[]};
    """)
    c.eq(r['after'],r['before'],'fractional receipt is rejected before any inventory or accounting mutation')
    c.eq(pg.errs,[],'invalid fractional receipt produces no browser errors')
    await ctx.close()


@test
async def colloquial_cash_register_commands_resolve_to_cash_session_tools(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,"""
      const U=window.UAI;
      const phrases=['صندوق رو باز کن','صندوق را باز کن','صندوقو باز کن','شروع شیفت'];
      const open=phrases.map(x=>U.NLU.understand(x,U.ctx));
      const close=['صندوق رو ببند','صندوق را ببند','صندوقو ببند','پایان شیفت'].map(x=>U.NLU.understand(x,U.ctx));
      const tool=info=>info&&info.plan&&info.plan.steps&&info.plan.steps[0]&&info.plan.steps[0].tool;
      return{open:open.map(tool),close:close.map(tool),unknown:open.concat(close).some(x=>!x||x.unknown)};
    """)
    c.eq(r['open'],['open_cash_session']*4,'colloquial open-register phrases resolve to the cash opening action')
    c.eq(r['close'],['close_cash_session']*4,'colloquial close-register phrases resolve to the cash closing action')
    c.eq(r['unknown'],False,'cash register phrases are understood locally')
    c.eq(pg.errs,[],'cash register NLU produces no browser errors')
    await ctx.close()


@test
async def finance_transfers_recheck_balance_inside_atomic_transaction(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,"""
      const S=await T.seed({});
      postJournal('TEST-BANK-SEED','seed bank',[{account:'bank',debit:1000,credit:0},{account:'equity',debit:0,credit:1000}]);
      const before=JSON.stringify({transfers:db.fundTransfers||[],journal:db.journal,
        bank:accountBalance('bank'),card:accountBalance('card')});
      const original=window.atomic;
      window.atomic=(label,fn)=>original(label,()=>{
        postJournal('TEST-BANK-RACE','concurrent bank outflow',
          [{account:'expense',debit:800,credit:0},{account:'bank',debit:0,credit:800}]);
        return fn();
      });
      let rejected=false;
      try{transferFunds('bank','card',500,'race test','test')}catch(e){rejected=/موجودی حساب مبدأ/.test(e.message)}
      window.atomic=original;
      const after=JSON.stringify({transfers:db.fundTransfers||[],journal:db.journal,
        bank:accountBalance('bank'),card:accountBalance('card')});
      return{rejected,before,after,health:runYouniqueHealthCheck().ok,errors:[]};
    """)
    c.true(r['rejected'],'transfer rejects when source balance falls below amount inside the transaction')
    c.eq(r['after'],r['before'],'failed transfer rolls back the transaction and intervening ledger mutation')
    c.true(r['health'],'rejected transfer leaves the database healthy')
    c.eq(pg.errs,[],'transfer race validation produces no browser errors')
    await ctx.close()


@test
async def cash_income_revalidates_open_session_inside_atomic_transaction(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,"""
      const S=await T.seed({});
      const before=JSON.stringify({incomes:db.incomes,journal:db.journal,
        movements:db.cashMovements,sessions:db.cashSessions});
      const original=window.atomic;
      window.atomic=(label,fn)=>original(label,()=>{
        activeCashSession().status='closed';
        return fn();
      });
      let rejected=false;
      try{recordIncome(2500,'income race','cash','test')}catch(e){rejected=/صندوق/.test(e.message)}
      window.atomic=original;
      const after=JSON.stringify({incomes:db.incomes,journal:db.journal,
        movements:db.cashMovements,sessions:db.cashSessions});
      return{rejected,before,after,active:!!activeCashSession(),
        health:runYouniqueHealthCheck().ok,errors:[]};
    """)
    c.true(r['rejected'],'cash income rejects when its session is no longer open at commit time')
    c.eq(r['after'],r['before'],'rejected cash income rolls back all financial and session changes')
    c.true(r['active'],'rollback restores the active cash session')
    c.true(r['health'],'rejected cash income leaves the database healthy')
    c.eq(pg.errs,[],'cash income session validation produces no browser errors')
    await ctx.close()


@test
async def colloquial_cash_open_command_asks_amount_then_requires_confirmation(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,"""
      const U=window.UAI;
      const before={sessions:db.cashSessions.length,journal:db.journal.length};
      const first=await U.chat.handle('صندوق رو باز کن',{source:'text'});
      const askedAmount=!!U.ctx.clarify&&!U.ctx.pending;
      const unchangedBeforeAmount={sessions:db.cashSessions.length,journal:db.journal.length};
      const second=await U.chat.handle('۰ ریال',{source:'text'});
      const waiting=!!U.ctx.pending;
      const unchangedBeforeConfirm={sessions:db.cashSessions.length,journal:db.journal.length};
      const third=await U.chat.handle('بله',{source:'text'});
      return{firstKind:first[0]&&first[0].kind,askedAmount,unchangedBeforeAmount,
        secondKind:second[0]&&second[0].kind,waiting,unchangedBeforeConfirm,
        opened:!!activeCashSession(),opening:activeCashSession()&&activeCashSession().openingCash,
        sessions:db.cashSessions.length,answer:third.map(x=>x.text).join(' '),
        unbalanced:T.unbalanced(),health:runYouniqueHealthCheck().ok,errors:[],before};
    """)
    c.eq(r['firstKind'],'ask','colloquial open-register command asks for the opening amount')
    c.true(r['askedAmount'],'amount clarification is pending before confirmation')
    c.eq(r['unchangedBeforeAmount'],r['before'],'asking for opening amount does not mutate data')
    c.eq(r['secondKind'],'confirm','supplying the amount creates an explicit confirmation prompt')
    c.true(r['waiting'],'opening the cash register awaits explicit confirmation')
    c.eq(r['unchangedBeforeConfirm'],r['before'],'cash register remains unchanged before confirmation')
    c.true(r['opened'],'cash register opens after explicit confirmation')
    c.eq(r['opening'],0,'zero opening balance is preserved')
    c.eq(r['sessions'],1,'exactly one cash session is created')
    c.eq(r['unbalanced'],0,'opening cash journal remains balanced')
    c.true(r['health'],'confirmed cash opening preserves database integrity')
    c.eq(pg.errs,[],'cash assistant flow produces no browser errors')
    await ctx.close()


@test
async def voids_reject_missing_source_invoice_lines_without_mutation(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,"""
      const S=await T.seed({});
      const purchase=await T.buy(S,S.v,4,1000,{cash:4000});
      const sale=await T.sell(S,S.v,2,1500,{cash:3000});
      const si=db.saleItems.find(x=>x.id===sale.items[0]);
      const pi=db.purchaseItems.find(x=>x.id===purchase.items[0]);
      db.saleItems=db.saleItems.filter(x=>x.id!==si.id);
      db.purchaseItems=db.purchaseItems.filter(x=>x.id!==pi.id);
      const snap=()=>JSON.stringify({
        saleStatus:sale.status,purchaseStatus:purchase.status,
        stock:variantBy(S.v).stock,journal:db.journal.length,payments:db.payments.length,
        stockMoves:db.stockMoves.length,warehouseMoves:db.warehouseMoves.length,
        returns:db.returns.length
      });
      const before=snap();let saleError='',purchaseError='';
      try{Fin.voidSale(sale.number,'missing source line')}catch(e){saleError=e.message}
      try{Fin.voidPurchase(purchase.number,'missing source line')}catch(e){purchaseError=e.message}
      return{saleError,purchaseError,before,after:snap(),saleStatus:sale.status,
        purchaseStatus:purchase.status,unb:T.unbalanced(),errors:[]};
    """)
    c.true(r['saleError'],'sale void rejects a missing original sale item')
    c.true(r['purchaseError'],'purchase void rejects a missing original purchase item')
    c.eq(r['after'],r['before'],'invalid voids leave stock, journals, payments and movements unchanged')
    c.eq(r['saleStatus'],'confirmed','sale remains confirmed after rejected void')
    c.eq(r['purchaseStatus'],'confirmed','purchase remains confirmed after rejected void')
    c.eq(r['unb'],0,'rejected voids preserve balanced journals')
    c.eq(pg.errs,[],'missing source-line guards produce no uncaught browser errors')
    await ctx.close()


@test
async def returns_reject_invalid_settlement_and_missing_source_items_atomically(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,"""
      const S=await T.seed({});
      const purchase=await T.buy(S,S.v,4,1000,{cash:4000});
      const sale=await T.sell(S,S.v,2,1500,{cash:3000});
      const saleItem=db.saleItems.find(x=>x.id===sale.items[0]);
      const purchaseItem=db.purchaseItems.find(x=>x.id===purchase.items[0]);
      const snapshot=()=>JSON.stringify({returns:db.returns,journal:db.journal,payments:db.payments,
        stock:variantBy(S.v).stock,moves:db.stockMoves,warehouseMoves:db.warehouseMoves});
      const before=snapshot();
      let saleMethod=false,purchaseMethod=false,missingSale=false,missingPurchase=false;
      try{Fin.saleReturn({ref:sale.number,qtys:{[saleItem.id]:1},method:'crypto'})}catch(e){saleMethod=/روش تسویه/.test(e.message)}
      try{Fin.purchaseReturn({ref:purchase.number,qtys:{[purchaseItem.id]:1},method:'cheque'})}catch(e){purchaseMethod=/روش تسویه/.test(e.message)}
      const afterMethods=snapshot();
      const saleIds=sale.items.slice();sale.items=['missing-sale-item'];
      try{Fin.saleReturn({ref:sale.number,qtys:{'missing-sale-item':1},method:'card'})}catch(e){missingSale=/اقلام فاکتور/.test(e.message)}
      sale.items=saleIds;
      const purchaseIds=purchase.items.slice();purchase.items=['missing-purchase-item'];
      try{Fin.purchaseReturn({ref:purchase.number,qtys:{'missing-purchase-item':1},method:'card'})}catch(e){missingPurchase=/اقلام فاکتور/.test(e.message)}
      purchase.items=purchaseIds;
      return{saleMethod,purchaseMethod,missingSale,missingPurchase,before,afterMethods,
        returns:db.returns.length,health:runYouniqueHealthCheck().ok,unb:T.unbalanced(),errors:[]};
    """)
    c.true(r['saleMethod'],'sale return rejects an unsupported settlement method')
    c.true(r['purchaseMethod'],'purchase return rejects an unsupported settlement method')
    c.eq(r['afterMethods'],r['before'],'unsupported settlement methods leave all records unchanged')
    c.true(r['missingSale'],'sale return rejects a missing source invoice item')
    c.true(r['missingPurchase'],'purchase return rejects a missing source invoice item')
    c.eq(r['returns'],0,'invalid returns never create return records')
    c.true(r['health'],'rejected returns preserve business data integrity')
    c.eq(r['unb'],0,'rejected returns preserve balanced journals')
    c.eq(pg.errs,[],'return validation produces no browser errors')
    await ctx.close()

@test
async def bulk_barcode_generation_is_atomic_and_preserves_existing_codes(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,"""
      const S=await T.seed({});
      const first=variantBy(S.v),existing=first.barcode;
      const second={...first,id:'barcode-bulk-second',size:String(Number(first.size)+1),barcode:'',sku:''};
      const third={...first,id:'barcode-bulk-third',size:String(Number(first.size)+2),barcode:'',sku:''};
      db.variants.push(second,third);saveDB(true);
      page='barcode';render();
      selected.clear();selected.add(second.id);selected.add(third.id);
      document.querySelector('#genSelected').click();
      const selectedCodes=[second.barcode,third.barcode];
      const uniqueSelected=new Set(selectedCodes).size===2&&selectedCodes.every(Boolean);
      const preserved=first.barcode===existing;
      const beforeAll=db.variants.filter(v=>v.active!==false).map(v=>v.barcode);
      document.querySelector('#genAll').click();
      const after=db.variants.filter(v=>v.active!==false);
      const codes=after.map(v=>v.barcode).filter(Boolean);
      const skus=after.map(v=>v.sku).filter(Boolean);
      return{uniqueSelected,preserved,allHaveCodes:after.every(v=>!!v.barcode),
        uniqueAll:new Set(codes).size===codes.length,allHaveSkus:after.every(v=>!!v.sku),
        uniqueSkus:new Set(skus.map(x=>x.toLowerCase())).size===skus.length,
        health:runYouniqueHealthCheck().ok,errors:[]};
    """)
    c.true(r['uniqueSelected'],'selected variants receive distinct generated barcodes')
    c.true(r['preserved'],'bulk generation never changes an existing barcode')
    c.true(r['allHaveCodes'],'complete action fills all active missing barcodes')
    c.true(r['uniqueAll'],'all generated barcodes remain unique')
    c.true(r['allHaveSkus'],'complete action fills missing SKUs')
    c.true(r['uniqueSkus'],'all generated SKUs remain unique')
    c.true(r['health'],'bulk barcode operations preserve catalog integrity')
    c.eq(pg.errs,[],'bulk barcode actions produce no browser errors')
    await ctx.close()

@test
async def invalid_variant_wizard_input_never_mutates_catalog(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,"""
      const S=await T.seed({});
      const count=db.models.length,original=modelBy(S.m).name;
      productModal();
      document.querySelector('#mn').value='کالای نامعتبر';
      document.querySelector('#mf').dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));
      document.querySelector('#customColor').value='سبز';
      document.querySelector('.vs').checked=true;
      document.querySelector('#buy').value='-1';
      document.querySelector('#makeVariants').click();
      const createUnchanged=db.models.length===count&&!db.models.some(x=>x.name==='کالای نامعتبر');
      closeModal();
      productModal(S.m);
      document.querySelector('#mn').value='نامی که نباید ذخیره شود';
      document.querySelector('#mf').dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));
      document.querySelector('#customColor').value='آبی';
      document.querySelector('.vs').checked=true;
      document.querySelector('#sell').value='-5';
      document.querySelector('#makeVariants').click();
      const editUnchanged=modelBy(S.m).name===original;
      return{createUnchanged,editUnchanged,health:runYouniqueHealthCheck().ok,errors:[]};
    """)
    c.true(r['createUnchanged'],'invalid new product prices do not insert a partial model')
    c.true(r['editUnchanged'],'invalid edit prices do not mutate the existing model')
    c.true(r['health'],'rejected variant wizard input preserves catalog integrity')
    c.eq(pg.errs,[],'invalid wizard validation produces no browser errors')
    await ctx.close()

@test
async def sale_void_restores_recorded_fifo_unit_cost(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,"""
      const S=await T.seed({});
      await T.buy(S,S.v,2,1000,{cash:2000});
      await T.buy(S,S.v,2,2000,{cash:4000});
      const sale=await T.sell(S,S.v,3,3000,{cash:9000});
      const item=db.saleItems.find(x=>x.id===sale.items[0]);
      const expected=Number((num(item.costTotal)/num(item.qty)).toFixed(2));
      const before=db.stockMoves.length;
      Fin.voidSale(sale.number,'FIFO cost reversal regression');
      const movement=db.stockMoves.slice(before).find(x=>x.type==='void_sale');
      return{expected,actual:movement&&movement.cost,stock:variantBy(S.v).stock,
        health:runYouniqueHealthCheck().ok,unbalanced:T.unbalanced(),errors:[]};
    """)
    c.eq(r['actual'],r['expected'],'sale void restores stock at the exact recorded FIFO unit cost')
    c.eq(r['stock'],4,'void restores all sold units')
    c.true(r['health'],'FIFO void reversal preserves data integrity')
    c.eq(r['unbalanced'],0,'FIFO void reversal keeps journals balanced')
    c.eq(pg.errs,[],'FIFO void reversal produces no browser errors')


@test
async def extracted_fin_partial_sale_returns_reconcile_exact_cents(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,"""
      const S=await T.seed({vat:0});
      await T.buy(S,S.v,3,700,{cash:2100});
      const sale=await T.sell(S,S.v,3,1001,{cash:3003});
      const item=db.saleItems.find(x=>x.id===sale.items[0]);
      sale.discount=1;
      const beforeCost=Number(item.costTotal||item.cost*item.qty);
      const parity=window.__YQ_FIN_PARITY_ONLY;
      if(!parity)throw Error('extracted finance parity module unavailable');
      const rows=[];
      for(let n=0;n<3;n++)rows.push(parity.saleReturn({ref:sale.number,qtys:{[item.id]:1},method:'cash'}));
      return{net:rows.reduce((a,x)=>a+x.total,0),cost:rows.reduce((a,x)=>a+x.costTotal,0),
        expectedNet:Number(item.total)-1,expectedCost:beforeCost,
        qty:rows.reduce((a,x)=>a+x.items[0].qty,0),
        stock:variantBy(S.v).stock,unbalanced:T.unbalanced(),errors:[]};
    """)
    c.eq(r['net'],r['expectedNet'],'split returns reconcile to the exact discounted line net')
    c.eq(r['cost'],r['expectedCost'],'split returns reconcile to the original recorded cost')
    c.eq(r['qty'],3,'all original units are returned across partial returns')
    c.eq(r['stock'],3,'all returned units restore stock')
    c.eq(r['unbalanced'],0,'split return journals remain balanced')
    c.eq(pg.errs,[],'split returns produce no browser errors')
    await ctx.close()


@test
async def active_returns_reject_incomplete_or_foreign_invoice_lines_atomically(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,"""
      const S=await T.seed({});
      const purchase=await T.buy(S,S.v,5,1000,{cash:5000});
      const sale=await T.sell(S,S.v,2,1500,{cash:3000});
      const saleItem=sale.items[0],purchaseItem=purchase.items[0];
      const snap=()=>({returns:db.returns.length,stock:variantBy(S.v).stock,
        stockMoves:db.stockMoves.length,warehouseMoves:db.warehouseMoves.length,
        payments:db.payments.length,journal:db.journal.length});
      const before=snap(),saleIds=[...sale.items],purchaseIds=[...purchase.items];
      sale.items=[...saleIds,'missing-sale-source-line'];
      purchase.items=[...purchaseIds,'missing-purchase-source-line'];
      let saleMissing='',purchaseMissing='';
      try{Fin.saleReturn({ref:sale.number,qtys:{[saleItem]:1},method:'cash'})}catch(e){saleMissing=e.message}
      try{Fin.purchaseReturn({ref:purchase.number,qtys:{[purchaseItem]:1},method:'card'})}catch(e){purchaseMissing=e.message}
      sale.items=saleIds;purchase.items=purchaseIds;
      let saleForeign='',purchaseForeign='';
      try{Fin.saleReturn({ref:sale.number,qtys:{'foreign-sale-line':1},method:'cash'})}catch(e){saleForeign=e.message}
      try{Fin.purchaseReturn({ref:purchase.number,qtys:{'foreign-purchase-line':1},method:'card'})}catch(e){purchaseForeign=e.message}
      return{before,after:snap(),saleMissing:!!saleMissing,purchaseMissing:!!purchaseMissing,
        saleForeign:!!saleForeign,purchaseForeign:!!purchaseForeign,
        health:runYouniqueHealthCheck().ok,unbalanced:T.unbalanced(),errors:[]};
    """)
    c.true(r['saleMissing'],'sale return rejects a missing source invoice line')
    c.true(r['purchaseMissing'],'purchase return rejects a missing source invoice line')
    c.true(r['saleForeign'],'sale return rejects a line ID from another invoice')
    c.true(r['purchaseForeign'],'purchase return rejects a line ID from another invoice')
    c.eq(r['after'],r['before'],'all rejected returns leave stock, journals, payments and movement ledgers unchanged')
    c.true(r['health'],'restored source invoices preserve business health')
    c.eq(r['unbalanced'],0,'rejected returns preserve balanced journals')
    c.eq(pg.errs,[],'return source validation produces no browser errors')
    await ctx.close()


@test
async def purchase_order_partial_receipts_get_unique_traceable_refs_and_legacy_warehouse(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,"""
      const S=await T.seed({});
      const po={id:'PO-PARTIAL-TRACE',number:'PO-PARTIAL-TRACE',status:'draft',supplierId:'',
        lines:[{variantId:S.v,qty:3,received:0,unitCost:1200}],total:3600};
      (db.purchaseOrders=db.purchaseOrders||[]).push(po);
      const receive=qty=>{
        window.receivePO(po.id);
        const f=document.querySelector('#rof41');
        f.querySelector('[data-rq41="0"]').value=String(qty);
        f.onsubmit({preventDefault(){}});
      };
      receive(1);const afterFirst={status:po.status,received:po.lines[0].received};
      receive(2);
      const journals=db.journal.filter(j=>j.purchaseOrderId===po.id);
      const moves=db.stockMoves.filter(m=>m.type==='purchase_receipt'&&String(m.ref).startsWith(po.number));
      const refs=journals.map(j=>j.ref);
      const legacy={id:'PO-LEGACY-WH',number:'PO-LEGACY-WH',status:'draft',supplierId:'',
        lines:[{variantId:S.v,qty:1,received:0,unitCost:500}],total:500};
      db.warehouses.find(w=>w.id==='MAIN').active=false;
      db.warehouses.push({id:'LEGACY-ALT',name:'انبار جایگزین',active:true});
      db.warehouseStocks['LEGACY-ALT']={};
      (db.purchaseOrders=db.purchaseOrders||[]).push(legacy);
      window.receivePO(legacy.id);
      const lf=document.querySelector('#rof41');
      lf.querySelector('[data-rq41="0"]').value='1';
      lf.onsubmit({preventDefault(){}});
      return{afterFirst,finalStatus:po.status,received:po.lines[0].received,
        journalCount:journals.length,uniqueRefs:new Set(refs).size===refs.length,
        moveRefs:moves.map(m=>m.ref),journalRefs:refs,receiptCount:po.receipts?.length||0,
        totalReceived:po.receipts?.reduce((a,x)=>a+x.total,0)||0,
        legacyWarehouse:legacy.warehouseId,legacyReceived:legacy.lines[0].received,
        legacyStock:db.warehouseStocks['LEGACY-ALT'][S.v],health:runYouniqueHealthCheck().ok,
        unbalanced:T.unbalanced(),errors:[]};
    """)
    c.eq(r['afterFirst'],{'status':'partial','received':1},'first partial receipt updates only its received quantity')
    c.eq(r['finalStatus'],'received','second receipt completes the order')
    c.eq(r['received'],3,'partial receipts accumulate to the ordered quantity')
    c.eq(r['journalCount'],2,'each partial receipt creates its own accounting entry')
    c.true(r['uniqueRefs'],'each receipt journal has a unique reference')
    c.eq(r['moveRefs'],r['journalRefs'],'inventory movements and journal entries share receipt references')
    c.eq(r['receiptCount'],2,'each receipt is retained in the purchase order history')
    c.eq(r['totalReceived'],3600,'receipt history reconciles to received cost')
    c.eq(r['legacyWarehouse'],'LEGACY-ALT','legacy order without warehouse uses an active warehouse when MAIN is unavailable')
    c.eq(r['legacyReceived'],1,'legacy order receipt is recorded')
    c.eq(r['legacyStock'],1,'legacy receipt enters the resolved destination warehouse')
    c.true(r['health'],'purchase order receipt history preserves data integrity')
    c.eq(r['unbalanced'],0,'partial receipt journals remain balanced')
    c.eq(pg.errs,[],'partial receipt flow produces no browser errors')
    await ctx.close()


@test
async def variant_edit_rejects_case_insensitive_barcode_and_rolls_back_failed_save(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,"""
      const S=await T.seed({});
      const v=variantBy(S.v);
      const sibling={...v,id:'variant-case-barcode',size:String(Number(v.size)+1),barcode:'Case-Barcode-42',sku:'SKU-CASE-42'};
      db.variants.push(sibling);
      variantEdit(S.v);document.querySelector('#vb').value='case-barcode-42';
      document.querySelector('#vf').dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));
      const duplicateRejected=variantBy(S.v).barcode!== 'case-barcode-42';
      const before=variantBy(S.v),snapshot={color:before.color,size:before.size,barcode:before.barcode,
        sku:before.sku,purchasePrice:before.purchasePrice,sellPrice:before.sellPrice,minStock:before.minStock};
      variantEdit(S.v);document.querySelector('#vc').value='تغییر نباید ذخیره شود';
      const originalSave=window.saveDB;window.saveDB=()=>false;
      document.querySelector('#vf').dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));
      window.saveDB=originalSave;
      const after=variantBy(S.v);
      const unchanged=JSON.stringify({color:after.color,size:after.size,barcode:after.barcode,sku:after.sku,
        purchasePrice:after.purchasePrice,sellPrice:after.sellPrice,minStock:after.minStock})===JSON.stringify(snapshot);
      return{duplicateRejected,unchanged,health:runYouniqueHealthCheck().ok,errors:[]};
    """)
    c.true(r['duplicateRejected'],'barcode uniqueness is case-insensitive')
    c.true(r['unchanged'],'failed persistence restores the original variant values')
    c.true(r['health'],'variant edit rollback preserves catalog integrity')
    c.eq(pg.errs,[],'variant edit persistence failure is handled without browser errors')
    await ctx.close()


@test
async def product_creation_rolls_back_model_variants_and_codes_on_save_failure(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,"""
      await T.seed({});
      const before={models:db.models.length,variants:db.variants.length,
        barcodeSeq:db.seq.barcode,skuSeq:db.seq.sku};
      productModal();
      document.querySelector('#mn').value='کفش تست تراکنشی';
      document.querySelector('#mb').value='برند تست';
      document.querySelector('#mf').dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));
      document.querySelector('.vc').checked=true;
      document.querySelector('.vs').checked=true;
      const originalSave=window.saveDB;window.saveDB=()=>false;
      document.querySelector('#makeVariants').click();
      window.saveDB=originalSave;
      const after={models:db.models.length,variants:db.variants.length,
        barcodeSeq:db.seq.barcode,skuSeq:db.seq.sku};
      return{before,after,partialModel:db.models.some(m=>m.name==='کفش تست تراکنشی'),
        partialVariant:db.variants.some(v=>v.modelId&&modelBy(v.modelId)?.name==='کفش تست تراکنشی'),
        health:runYouniqueHealthCheck().ok,errors:[]};
    """)
    c.eq(r['after'],r['before'],'failed product save restores model, variants and generated code counters')
    c.true(not r['partialModel'],'failed product save leaves no partial model')
    c.true(not r['partialVariant'],'failed product save leaves no partial variants')
    c.true(r['health'],'product creation rollback preserves catalog integrity')
    c.eq(pg.errs,[],'product creation persistence failure is handled without browser errors')
    await ctx.close()


@test
async def backup_validation_rejects_broken_references_duplicate_barcodes_and_unbalanced_ledger(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,"""
      const S=await T.seed({});
      await T.buy(S,S.v,2,1000,{cash:2000});
      await T.sell(S,S.v,1,1500,{cash:1500});
      const base=JSON.parse(exportData()).data;
      const clone=()=>JSON.parse(JSON.stringify(base));
      const duplicate=clone();duplicate.variants[0].barcode='BACKUP-DUP-1';
      const extra={...duplicate.variants[0],id:'backup-duplicate-barcode',size:String(Number(duplicate.variants[0].size)+1)};
      duplicate.variants.push(extra);
      const dangling=clone();dangling.sales[0].items[0]='missing-backup-sale-line';
      const unbalanced=clone();unbalanced.journal[0].lines[0].debit=Number(unbalanced.journal[0].lines[0].debit||0)+1;
      const rejected={duplicate:false,dangling:false,unbalanced:false,restore:false};
      for(const [key,data] of Object.entries({duplicate,dangling,unbalanced})){
        try{validateBackupData(data)}catch(e){rejected[key]=true}
      }
      const before={models:db.models.length,variants:db.variants.length,sales:db.sales.length,
        purchases:db.purchases.length,journal:db.journal.length,stock:variantBy(S.v).stock};
      try{await replaceDB(dangling)}catch(e){rejected.restore=true}
      const after={models:db.models.length,variants:db.variants.length,sales:db.sales.length,
        purchases:db.purchases.length,journal:db.journal.length,stock:variantBy(S.v).stock};
      return{rejected,before,after,health:runYouniqueHealthCheck().ok,errors:[]};
    """)
    for key in ['duplicate','dangling','unbalanced','restore']:
        c.true(r['rejected'][key],f'backup validator rejects {key} corruption')
    c.eq(r['after'],r['before'],'failed restore leaves the live database unchanged')
    c.true(r['health'],'backup rejection preserves current database integrity')
    c.eq(pg.errs,[],'backup integrity checks produce no browser errors')
    await ctx.close()


asyncio.run(main())
