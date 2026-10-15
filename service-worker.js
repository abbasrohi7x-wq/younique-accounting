const CACHE='unique-46.3.0';
const CORE=['./','./index.html','./manifest.json','./icon-192.png','./icon-512.png'];
self.addEventListener('install',e=>e.waitUntil(caches.open(CACHE).then(c=>c.addAll(CORE)).then(()=>self.skipWaiting())));
self.addEventListener('activate',e=>e.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim())));
// Same-origin GET only. Pages: network-first (fixes reach users), cache fallback offline.
// Static assets: cache-first. Only successful (200) responses are cached; cache errors never break a response.
self.addEventListener('fetch',e=>{
  const req=e.request;
  if(req.method!=='GET')return;
  const url=new URL(req.url);
  if(url.origin!==self.location.origin)return;
  const store=res=>{if(res&&res.status===200&&res.type==='basic'){const copy=res.clone();caches.open(CACHE).then(c=>c.put(req,copy)).catch(()=>{})}return res};
  if(req.mode==='navigate'){
    e.respondWith(fetch(req).then(store).catch(()=>caches.match(req,{ignoreSearch:true}).then(r=>r||caches.match('./index.html'))));
    return;
  }
  e.respondWith(caches.match(req).then(cached=>cached||fetch(req).then(store).catch(()=>Response.error())));
});
