/* Feasibility probe: can the existing engine run WITHOUT a browser (server-side)?  node tests/headless_probe.js */
const fs=require('fs'),vm=require('vm'),path=require('path');
const html=fs.readFileSync(path.join(__dirname,'..','index.html'),'utf8');
const scripts=[...html.matchAll(/<script([^>]*)>([\s\S]*?)<\/script>/g)].filter(m=>!/\bsrc=/.test(m[1])&&!/json/.test(m[1])).map(m=>m[2]);
function P(){const f=function(){return P()};return new Proxy(f,{get:(t,k)=>k===Symbol.toPrimitive?()=>'':k==='length'?0:k==='then'?undefined:P(),set:()=>true,apply:()=>P(),construct:()=>P(),has:()=>true})}
const store={};const ls={getItem:k=>k in store?store[k]:null,setItem:(k,v)=>{store[k]=String(v)},removeItem:k=>{delete store[k]},key:i=>Object.keys(store)[i]||null,get length(){return Object.keys(store).length}};
const win={};const ctx=vm.createContext(Object.assign(win,{document:P(),localStorage:ls,sessionStorage:{...ls},navigator:{userAgent:'node',serviceWorker:undefined,language:'fa'},location:{href:'http://x/',search:'',hash:'',pathname:'/'},history:P(),indexedDB:undefined,crypto:require('crypto').webcrypto,TextEncoder,TextDecoder,URL,Blob,console:{log(){},warn(){},error(){}},setTimeout:(f)=>0,clearTimeout(){},setInterval:()=>0,clearInterval(){},requestAnimationFrame:()=>0,matchMedia:()=>({matches:false,addEventListener(){}}),addEventListener(){},removeEventListener(){},getComputedStyle:()=>P(),MutationObserver:class{observe(){}},Image:class{},FileReader:class{},fetch:()=>Promise.reject(new Error('offline')),performance,Intl}));
ctx.window=ctx;ctx.self=ctx;ctx.globalThis=ctx;
let ok=0,fail=[];scripts.forEach((src,i)=>{try{vm.runInContext(src,ctx,{timeout:5000});ok++}catch(e){fail.push(i+': '+String(e.message).slice(0,80))}});
console.log('scripts loaded headless:',ok+'/'+scripts.length);if(fail.length)console.log('script errors:\n  '+fail.join('\n  '));
const run=c=>vm.runInContext(c,ctx);
const has=n=>run('typeof '+n);
console.log('engine symbols:',['db','Fin','postJournal','accountBalance','stockMoveV21','atomic','cashMove','openCashSession','costingMethod','validateBackupData'].map(n=>n+':'+has(n)).join(' '));
if(has('db')!=='object'||has('postJournal')!=='function'){console.log('RESULT: engine did NOT become available headless');process.exit(2)}
const out=run(`(()=>{const r={};
  const n0=db.journal.length;
  try{postJournal('T-UNBAL','unbalanced',[{account:'cash',debit:100,credit:0},{account:'sales',debit:0,credit:90}]);r.unbalancedAccepted=true}catch(e){r.unbalancedRejected=String(e.message).slice(0,60)}
  r.journalAfterReject=db.journal.length-n0;
  postJournal('T-OK','balanced',[{account:'cash',debit:100,credit:0},{account:'sales',debit:0,credit:100}]);
  r.cash=accountBalance('cash');r.sales=accountBalance('sales');
  const n1=db.journal.length;try{atomic('rollback-test',()=>{postJournal('T-RB','x',[{account:'cash',debit:5,credit:0},{account:'sales',debit:0,credit:5}]);throw new Error('boom')})}catch(e){r.rollbackThrew=true}
  r.journalAfterRollback=db.journal.length-n1;
  r.costing=costingMethod();return JSON.stringify(r)})()`);
console.log('headless engine scenario:',out);
