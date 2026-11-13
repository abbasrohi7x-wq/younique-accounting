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
    pg.on('pageerror',lambda e:errs.append(str(e)[:200]));await pg.goto(URL);await pg.wait_for_timeout(1500);await pg.evaluate(HELP);pg.errs=errs;return pg,ctx
async def ev(pg,js):return await pg.evaluate('async()=>{'+js+'}')

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
      return{saved:!!sale,total:sale&&sale.total,paid:sale&&sale.paid,due:sale&&sale.due,p,
        stock:variantBy(S.v).stock,unb:T.unbalanced(),
        journalAccounts:journal?(journal.lines||[]).filter(x=>['cash','card','bank','receivable'].includes(x.account)).map(x=>[x.account,num(x.debit)]):[]}
    """)
    c.true(r['saved'],'manual split-payment sale saved')
    c.eq(r['total'],3000,'manual invoice total')
    c.eq(r['paid'],2400,'manual received total excludes credit')
    c.eq(r['due'],600,'manual credit balance')
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
async def manual_purchase_and_sale_require_open_cash_session(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,"""
      const S=await T.seed({});
      const before={p:db.purchases.length,s:db.sales.length,j:db.journal.length,
        pay:db.payments.length,stock:variantBy(S.v).stock};
      activeCashSession().status='closed';saveDB(true);
      const purchase=await T.buy(S,S.v,2,1000,{cash:2000});purchaseCart.splice(0);
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

asyncio.run(main())
