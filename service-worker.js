const CACHE='unique-pro-1.0';
const CORE=['./','./index.html','./manifest.json','./icon-192.png','./icon-512.png','./logo.svg'];
self.addEventListener('install',e=>e.waitUntil(caches.open(CACHE).then(c=>c.addAll(CORE)).then(()=>self.skipWaiting())));
self.addEventListener('activate',e=>e.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim())));
// Same-origin GET only (AI calls, /api/* and other origins are never touched).
// Pages: network first with a 3 s timeout (fixes reach users; weak networks fall back to the cached app quickly).
// Static assets: cache first. Only successful (200) basic responses are cached; cache errors never break a response.
self.addEventListener('fetch',e=>{
  const req=e.request;
  if(req.method!=='GET')return;
  const url=new URL(req.url);
  if(url.origin!==self.location.origin)return;
  if(url.pathname.startsWith('/api/'))return; // server functions (AI proxy, health) are never cached
  const put=(key,res)=>{caches.open(CACHE).then(c=>c.put(key,res)).catch(()=>{})};
  const store=res=>{if(res&&res.status===200&&res.type==='basic')put(req,res.clone());return res};
  if(req.mode==='navigate'){
    e.respondWith((async()=>{
      try{
        const res=await Promise.race([fetch(req),new Promise((_,rej)=>setTimeout(()=>rej(new Error('timeout')),3000))]);
        if(res&&res.status===200&&res.type==='basic'){put(req,res.clone());put('./index.html',res.clone())}
        return res;
      }catch(_){
        return (await caches.match(req,{ignoreSearch:true}))||(await caches.match('./index.html'))||Response.error();
      }
    })());
    return;
  }
  e.respondWith(caches.match(req).then(cached=>cached||fetch(req).then(store).catch(()=>Response.error())));
});
