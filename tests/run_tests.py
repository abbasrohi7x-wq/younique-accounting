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
async def invoice_ocr_review_does_not_write_before_confirmation(br,c):
    pg,ctx=await page(br);r=await ev(pg,'''const S=await T.seed({});
      const before={p:db.purchases.length,pi:db.purchaseItems.length,j:db.journal.length,stock:variantBy(S.v).stock};
      const parsed=parseLocalInvoiceText('فروشنده: فروشگاه نمونه\\nشماره فاکتور: INV-123\\nتاریخ: 1405/08/20\\nکفش نایک مشکی سایز 42 2 1000000 2000000\\nجمع کل: 2000000 ریال',[],.95);
      showInvoiceResult(parsed,null);await T.sleep(100);
      const after={p:db.purchases.length,pi:db.purchaseItems.length,j:db.journal.length,stock:variantBy(S.v).stock};
      return{before,after,review:!!document.querySelector('#invoiceConfirm'),total:parsed.total,items:parsed.items.length,number:parsed.invoiceNumber}''')
    c.eq(r['after'],r['before'],'OCR review must not write purchase, journal or stock')
    c.true(r['review'],'manual invoice confirmation is visible')
    c.eq(r['total'],2000000,'invoice total parsed')
    c.eq(r['items'],1,'invoice line parsed')
    c.eq(r['number'],'INV-123','invoice number parsed')
    await ctx.close()

@test
async def offline_voice_routes_to_assistant_and_sale_draft(br,c):
    pg,ctx=await page(br)
    r=await pg.evaluate("""() => ({
      voice:typeof window.yqVoiceDraft==='function' && typeof window.voiceRecord==='function',
      assistant:!!(window.UAI&&window.UAI.ui&&typeof window.UAI.ui.submit==='function')
    })""")
    c.true(r['voice'],'offline voice entry points exposed')
    c.true(r['assistant'],'assistant submit controller exposed to voice module')

    await pg.evaluate("""() => {
      window.page='ai';window.render();
      window.__voiceCapture=null;
      window.UAI.ui.submit=(text,source)=>{window.__voiceCapture={text,source};return Promise.resolve([])};
    }""")
    await pg.locator('#voiceBtn').click()
    await pg.locator('#yqVText').click()
    await pg.locator('#yqVManual').fill('گزارش فروش امروز')
    await pg.locator('#yqVManualApply').click()
    await pg.wait_for_timeout(80)
    a=await pg.evaluate("window.__voiceCapture")
    c.eq(a,{'text':'گزارش فروش امروز','source':'voice'},'assistant voice reaches local assistant API')

    await pg.evaluate("""() => {
      window.page='sale';window.render();
      window.__saleVoice=null;
      window.yqApplyVoiceDraft=(text)=>{window.__saleVoice=text;return {ok:true}};
    }""")
    await pg.locator('#voiceSale').click()
    await pg.locator('#yqVText').click()
    await pg.locator('#yqVManual').fill('دو جفت کتونی مشکی سایز ۴۲')
    await pg.locator('#yqVManualApply').click()
    await pg.wait_for_timeout(80)
    v=await pg.evaluate("window.__saleVoice")
    c.eq(v,'دو جفت کتونی مشکی سایز ۴۲','sale voice reaches sale draft parser')
    c.eq(pg.errs,[],'no browser runtime errors')
    await ctx.close()

@test
async def offline_voice_transcript_reaches_local_assistant(br,c):
    pg,ctx=await page(br);r=await ev(pg,'''window.yqVoiceDraft();await T.sleep(80);
      const box=document.querySelector('#yqVTranscript');const apply=document.querySelector('#yqVApply');
      if(!box||!apply)return{dialog:false,submitted:false};
      box.value='راهنما';apply.click();await T.sleep(300);
      return{dialog:true,submitted:!!(window.UAI&&window.UAI.ui&&window.UAI.ui.transcript.some(m=>m.role==='user'&&m.text==='راهنما'))}''')
    c.true(r['dialog'],'offline voice dialog opened')
    c.true(r['submitted'],'confirmed transcript reaches local assistant')
    await ctx.close()

@test
async def offline_voice_opens_real_microphone_pipeline(br,c):
    pg,ctx=await page(br)
    r=await pg.evaluate("""async() => {
      let handlers={},accepted=0,permissionRequested=false,recognizerSampleRate=0;
      const track={readyState:'live',stop(){}};
      const stream={getTracks:()=>[track],getAudioTracks:()=>[track]};
      Object.defineProperty(navigator,'mediaDevices',{configurable:true,value:{
        getUserMedia:async()=>{permissionRequested=true;return stream}
      }});
      Object.defineProperty(window,'caches',{configurable:true,value:{
        open:async()=>({match:async()=>({cached:true})})
      }});
      window.Vosk={createModel:async()=>({
        ready:true,
        KaldiRecognizer:function(rate){
          recognizerSampleRate=rate;
          this.on=(name,fn)=>{handlers[name]=fn};
          this.acceptWaveform=()=>{accepted++;if(handlers.partialresult)handlers.partialresult({result:{partial:'سلام'}})};
          this.remove=()=>{};
        },
        terminate(){}
      })};
      window.AudioContext=function(){
        this.state='running';this.sampleRate=48000;this.destination={};this.resume=async()=>{};
        this.createMediaStreamSource=()=>({connect(){}});
        this.createScriptProcessor=()=>{window.__fakeProcessor={connect(){},disconnect(){},onaudioprocess:null};return window.__fakeProcessor};
        this.createGain=()=>({gain:{value:1},connect(){},disconnect(){}});
        this.close=async()=>{};
      };
      window.yqVoiceDraft('assistant');
      await new Promise(r=>setTimeout(r,30));
      document.querySelector('#yqVStart').click();
      await new Promise(r=>setTimeout(r,80));
      if(window.__fakeProcessor&&window.__fakeProcessor.onaudioprocess){
        const samples=new Float32Array(4096).fill(.02);
        window.__fakeProcessor.onaudioprocess({inputBuffer:{getChannelData:()=>samples}});
      }
      await new Promise(r=>setTimeout(r,30));
      return {permissionRequested,accepted,recognizerSampleRate,status:document.querySelector('#yqVStatus')?.textContent||''};
    }""")
    c.true(r['permissionRequested'],'microphone permission requested on start button')
    c.eq(r['recognizerSampleRate'],48000,'Vosk recognizer receives actual AudioContext sample rate')
    c.true(r['accepted']>=1,'audio frames reached Vosk recognizer')
    c.true('سلام' in r['status'],'partial recognition updates visible status')
    c.eq(pg.errs,[],'no browser runtime errors')
    await ctx.close()


@test
async def offline_voice_button_uses_local_vosk_dialog_not_browser_speech(br,c):
    pg,ctx=await page(br)
    r=await pg.evaluate("""() => {
      window.page='ai';window.render();
      let nativeStarts=0;
      function NativeSpeech(){nativeStarts++;this.start=()=>nativeStarts++;}
      NativeSpeech.prototype.processLocally=true;
      Object.defineProperty(window,'SpeechRecognition',{configurable:true,value:NativeSpeech});
      Object.defineProperty(window,'webkitSpeechRecognition',{configurable:true,value:NativeSpeech});
      window.__voiceDialogContext=null;
      window.yqVoiceDraft=(context)=>{window.__voiceDialogContext=context||'assistant'};
      const button=document.querySelector('#voiceBtn');
      if(!button)return {button:false,nativeStarts,context:null};
      button.click();
      return {button:true,nativeStarts,context:window.__voiceDialogContext};
    }""")
    c.true(r['button'],'assistant microphone button exists')
    c.eq(r['context'],'assistant','microphone opens the local Vosk dialog')
    c.eq(r['nativeStarts'],0,'browser native speech UI is never launched even when processLocally is supported')
    c.eq(pg.errs,[],'no browser runtime errors')
    await ctx.close()


@test
async def offline_voice_resumes_audio_context_before_model_load(br,c):
    pg,ctx=await page(br)
    r=await pg.evaluate("""async() => {
      let requested=false,modelPending=false;
      const track={readyState:'live',stop(){}};
      const stream={getTracks:()=>[track],getAudioTracks:()=>[track]};
      Object.defineProperty(navigator,'mediaDevices',{configurable:true,value:{
        getUserMedia:()=>{requested=true;return Promise.resolve(stream)}
      }});
      Object.defineProperty(window,'caches',{configurable:true,value:{
        open:async()=>({match:async()=>({cached:true})})
      }});
      window.Vosk={createModel:()=>{modelPending=true;return new Promise(()=>{})}};
      window.AudioContext=function(){
        window.__audioContextCreated=true;
        this.state='suspended';this.destination={};
        this.resume=async()=>{this.state='running'};
        this.close=async()=>{};
      };
      window.yqVoiceDraft('assistant');
      document.querySelector('#yqVStart').click();
      await new Promise(resolve=>setTimeout(resolve,20));
      return {created:!!window.__audioContextCreated,requested,modelPending};
    }""")
    c.true(r['created'],'AudioContext is created synchronously from the microphone tap')
    c.true(r['requested'],'microphone permission request starts')
    c.true(r['modelPending'],'model loading can continue asynchronously after audio resume')
    c.eq(pg.errs,[],'no browser runtime errors')
    await ctx.close()


@test
async def indexeddb_roundtrip_and_backup_validation(br,c):
    pg,ctx=await page(br)
    r=await pg.evaluate("""async() => {
      await window.YStore.init();
      const mode=window.YStore.S.mode;
      db.settings.shopName='پایداری ذخیره‌سازی یونیک';
      db.settings.ai=db.settings.ai||{};db.settings.ai.apiKey='DO_NOT_EXPORT_SECRET';
      const saved=saveDB(true);await window.YStore.flush();
      const backup=JSON.parse(exportData());
      const secretExcluded=!JSON.stringify(backup).includes('DO_NOT_EXPORT_SECRET');
      const valid=validateBackupData(backup.data);
      const before=db.models.length;let rejected=false;
      try{replaceDB({models:[],variants:[]})}catch(e){rejected=true}
      const unchanged=db.models.length===before;
      db.settings.ai.apiKey='';
      return {mode,saved,secretExcluded,valid:valid.products===db.models.length,rejected,unchanged};
    }""")
    c.eq(r['mode'],'idb','IndexedDB is the primary storage mode')
    c.true(r['saved'],'saveDB reports successful persistence')
    c.true(r['secretExcluded'],'backup never exports a legacy API secret')
    c.true(r['valid'],'exported backup passes structural validation')
    c.true(r['rejected'] and r['unchanged'],'invalid restore is rejected before live data changes')
    await pg.reload()
    await pg.wait_for_timeout(1600)
    r2=await pg.evaluate("""async()=>{await window.YStore.init();return {shop:db.settings.shopName,mode:YStore.S.mode,ready:YStore.S.ready}}""")
    c.eq(r2['shop'],'پایداری ذخیره‌سازی یونیک','IndexedDB data survives a full page reload')
    c.eq(r2['mode'],'idb','IndexedDB remains primary after reload')
    c.true(r2['ready'],'IndexedDB initialization completes')
    await ctx.close()


@test
async def multi_method_purchase_and_sale_payments(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,'''const S=await T.seed({});
      const p=await T.buy(S,S.v,5,1000,{cash:1000,card:1000,bank:1000,credit:2000});
      const s=await T.sell(S,S.v,2,2000,{cash:500,card:1000,bank:1500,credit:1000});
      const b=T.bal();
      const purchasePay=db.payments.filter(x=>x.ref===p.number&&x.direction==='out');
      const salePay=db.payments.filter(x=>x.ref===s.number&&x.direction==='in');
      return {p:!!p,s:!!s,stock:variantBy(S.v).stock,cash:b.cash,card:b.card,bank:b.bank,receivable:b.receivable,payable:b.payable,inventory:b.inventory,
        pSum:purchasePay.reduce((a,x)=>a+num(x.amount),0),sSum:salePay.reduce((a,x)=>a+num(x.amount),0),
        pAccounts:[...new Set(purchasePay.map(x=>x.account))].sort(),sAccounts:[...new Set(salePay.map(x=>x.account))].sort(),unb:T.unbalanced()};
    ''')
    c.true(r['p'] and r['s'],'purchase and sale both saved')
    c.eq(r['stock'],3,'inventory follows purchase then sale quantities')
    c.eq(r['cash'],999500,'cash account reflects both cash legs')
    c.eq(r['card'],0,'card account reflects both card legs')
    c.eq(r['bank'],500,'bank account reflects both bank legs')
    c.eq(r['receivable'],1000,'unpaid sale balance is receivable')
    c.eq(r['payable'],-2000,'unpaid purchase balance is payable')
    c.eq(r['inventory'],3000,'inventory valuation follows remaining stock')
    c.eq(r['pSum'],3000,'purchase cash/card/bank payments are recorded; remaining amount is payable')
    c.eq(r['sSum'],3000,'sale cash/card/bank payments are recorded; remaining amount is receivable')
    c.eq(r['pAccounts'],['bank','card','cash'],'purchase records all three paid methods')
    c.eq(r['sAccounts'],['bank','card','cash'],'sale records all three paid methods')
    c.eq(r['unb'],0,'multi-method journals remain balanced')
    await ctx.close()


@test
async def product_color_size_matrix_and_unique_codes(br,c):
    pg,ctx=await page(br)
    r=await ev(pg,'''const before=db.variants.length;
      const made=ActionEngine.createProduct({name:'کفش ماتریس تست',brand:'برند تست',modelCode:'MATRIX-TEST',category:'کفش',
        colors:['مشکی','سفید'],sizes:['17','18','48'],buyPrice:1000,sellPrice:2000,minStock:2});
      const rows=db.variants.filter(v=>v.modelId===made.modelId);
      let duplicateBlocked=false;try{ActionEngine.createProduct({name:'بارکد تکراری',color:'مشکی',size:'42',barcode:rows[0].barcode})}catch(e){duplicateBlocked=true}
      return {count:made.variantCount,rows:rows.length,stock:rows.every(v=>v.stock===0),sizes:[...new Set(rows.map(v=>v.size))].sort(),
        colors:[...new Set(rows.map(v=>v.color))].sort(),barcodes:rows.every(v=>!!v.barcode)&&new Set(rows.map(v=>v.barcode)).size===rows.length,
        skus:rows.every(v=>!!v.sku)&&new Set(rows.map(v=>v.sku)).size===rows.length,duplicateBlocked,delta:db.variants.length-before};
    ''')
    c.eq(r['count'],6,'all color-size combinations created')
    c.eq(r['rows'],6,'six variants are persisted')
    c.true(r['stock'],'new product variants start with zero stock')
    c.eq(r['sizes'],['17','18','48'],'requested shoe sizes preserved')
    c.eq(r['colors'],['سفید','مشکی'],'requested colors preserved')
    c.true(r['barcodes'],'barcodes are generated and unique')
    c.true(r['skus'],'SKUs are generated and unique')
    c.true(r['duplicateBlocked'],'duplicate barcode is rejected')
    c.eq(r['delta'],6,'rejected duplicate does not create another variant')
    await ctx.close()


@test
async def offline_ocr_runtime_loads_from_local_assets(br,c):
    pg,ctx=await page(br)
    r=await pg.evaluate("""async()=> {
      const load=()=>new Promise((resolve,reject)=>{const s=document.createElement('script');s.src='./vendor/tesseract/tesseract.min.js';s.onload=resolve;s.onerror=()=>reject(Error('Tesseract script failed'));document.head.appendChild(s)});
      await load();
      const worker=await Tesseract.createWorker('eng',1,{workerPath:'./vendor/tesseract/worker.min.js',langPath:'./vendor/tesseract/lang/',corePath:'./vendor/tesseract/core/',gzip:true});
      try{
        const canvas=document.createElement('canvas');canvas.width=900;canvas.height=220;
        const ctx=canvas.getContext('2d');ctx.fillStyle='#fff';ctx.fillRect(0,0,900,220);
        ctx.fillStyle='#000';ctx.font='bold 86px Arial';ctx.fillText('TEST 12345',50,145);
        const result=await worker.recognize(canvas);
        return {loaded:true,text:String(result.data.text||'').trim(),confidence:Number(result.data.confidence||0)};
      }finally{await worker.terminate()}
    }""")
    c.true(r['loaded'],'Tesseract worker starts from bundled local files')
    c.true('TEST' in r['text'].upper(),'local OCR recognizes synthetic test text')
    c.true(r['confidence']>0,'Tesseract returns a confidence score')
    c.eq(pg.errs,[],'no browser runtime errors during local OCR')
    await ctx.close()


@test
async def offline_voice_stops_when_browser_emits_no_audio_frames(br,c):
    pg,ctx=await page(br)
    r=await pg.evaluate("""async()=> {
      let stopped=false;
      const track={readyState:'live',stop(){stopped=true;this.readyState='ended'}};
      const stream={getTracks:()=>[track],getAudioTracks:()=>[track]};
      Object.defineProperty(navigator,'mediaDevices',{configurable:true,value:{getUserMedia:async()=>stream}});
      Object.defineProperty(window,'caches',{configurable:true,value:{open:async()=>({match:async()=>({cached:true})})}});
      window.Vosk={createModel:async()=>({ready:true,KaldiRecognizer:function(){this.on=()=>{};this.acceptWaveform=()=>{};this.remove=()=>{}},terminate(){}})};
      window.AudioContext=function(){
        this.state='running';this.sampleRate=48000;this.destination={};this.resume=async()=>{};
        this.createMediaStreamSource=()=>({connect(){}});
        this.createScriptProcessor=()=>{window.__silentProcessor={connect(){},disconnect(){},onaudioprocess:null};return window.__silentProcessor};
        this.createGain=()=>({gain:{value:0},connect(){},disconnect(){}});
        this.close=async()=>{};
      };
      window.yqVoiceDraft('assistant');await new Promise(r=>setTimeout(r,20));
      document.querySelector('#yqVStart').click();
      await new Promise(r=>setTimeout(r,5300));
      return {stopped,status:document.querySelector('#yqVStatus')?.textContent||'',trackStopped:stopped};
    }""")
    c.true(r['trackStopped'],'microphone stream is released if no audio frames arrive')
    c.true('هیچ فریم صوتی' in r['status'],'user receives a specific no-audio diagnostic')
    c.eq(pg.errs,[],'no browser runtime errors')
    await ctx.close()


@test
async def local_file_transfer_strips_cloud_secrets_and_keeps_local_conflicts(br,c):
    pg,ctx=await page(br)
    r=await pg.evaluate("""async()=> {
      const S=await T.seed({});
      db.settings.supabase={url:'https://unused.example',anonKey:'CLOUD_SECRET_ANON',accessKey:'CLOUD_SECRET_ACCESS'};
      db.settings.ai=db.settings.ai||{};db.settings.ai.apiKey='AI_SECRET';
      const env=syncEnvelope(),backup=JSON.parse(exportData());
      const secretsStripped=!JSON.stringify(env).includes('CLOUD_SECRET')&&!JSON.stringify(env).includes('AI_SECRET')&&
        !JSON.stringify(backup).includes('CLOUD_SECRET')&&!JSON.stringify(backup).includes('AI_SECRET');
      const incoming=JSON.parse(JSON.stringify(env.data));
      db.customers.find(x=>x.id===S.cus).name='نام محلی';
      const remote=JSON.parse(JSON.stringify(incoming));
      remote.customers.find(x=>x.id===S.cus).name='نام دستگاه دیگر';
      remote.customers.push({id:'REMOTE-CUSTOMER-1',name:'مشتری دستگاه دوم',phone:'000',createdAt:'2026-11-14T00:00:00Z'});
      const merged=syncMerge(db,remote);
      proSync();
      const ui=document.querySelector('#content')?.innerText||'';
      const checksum=env.checksum===syncSig({app:env.app,schema:env.schema,version:env.version,deviceId:env.deviceId,createdAt:env.createdAt,data:env.data});
      return {secretsStripped,checksum,added:merged.added.some(x=>x.id==='REMOTE-CUSTOMER-1'),
        localKept:merged.data.customers.find(x=>x.id===S.cus)?.name==='نام محلی',
        conflict:merged.conflicts.some(x=>x.id===S.cus&&x.resolution==='local-kept'),
        localUI:ui.includes('انتقال فایل‌محور'),cloudUI:/Supabase|ابر رایگان/i.test(ui),
        hasExport:!!document.querySelector('#sx'),hasImport:!!document.querySelector('#si')};
    }""")
    c.true(r['secretsStripped'],'file backup and transfer never export cloud or AI credentials')
    c.true(r['checksum'],'transfer checksum is deterministic')
    c.true(r['added'],'new records from another device are detected')
    c.true(r['localKept'] and r['conflict'],'conflicting local record is preserved')
    c.true(r['localUI'] and not r['cloudUI'],'sync UI is local file transfer only')
    c.true(r['hasExport'] and r['hasImport'],'file export and import controls remain available')
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
asyncio.run(main())
