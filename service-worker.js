/* ==========================================================================
   Unique Pro — Service Worker  (cache v1.11.0)
   Goals: fully offline, predictable updates, no network traffic to other origins.

   Caches
     unique-shell-<VERSION>  app shell (replaced on every release)
     unique-ocr-v1           OCR engine + language data (large, survives releases)

   Strategies
     navigation         network-first (3 s) → cached index.html when offline
     /vendor/tesseract  cache-first (HEAD answered from cache → offline OCR check works)
     other same-origin  stale-while-revalidate
     cross-origin       never intercepted
   ========================================================================== */
'use strict';

const VERSION = '1.11.0';
const SHELL_CACHE = 'unique-shell-' + VERSION;
const OCR_CACHE = 'unique-ocr-v1';

const SHELL_FILES = [
  './', './index.html', './manifest.json', './logo.svg', './icon-192.png', './icon-512.png',
  './src/engine/core.js', './src/engine/fin.js', './src/ui/upgrade.js', './src/ui/local-nlu.js', './vendor/fonts/vazirmatn-arabic.woff2', './vendor/fonts/vazirmatn-latin.woff2'
];
/* Everything OCR needs. core/tesseract-core-lstm is the no-SIMD fallback. */
const OCR_FILES = [
  './vendor/tesseract/tesseract.min.js',
  './vendor/tesseract/worker.min.js',
  './vendor/tesseract/core/tesseract-core-simd-lstm.wasm.js',
  './vendor/tesseract/core/tesseract-core-lstm.wasm.js',
  './vendor/tesseract/lang/fas.traineddata.gz',
  './vendor/tesseract/lang/eng.traineddata.gz'
];
const NAV_TIMEOUT_MS = 3000;

/* ---------- install: precache the shell; activation waits for the page's consent ---------- */
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(SHELL_CACHE).then((cache) =>
      cache.addAll(SHELL_FILES.map((u) => new Request(u, { cache: 'reload' })))
    )
  );
});

/* ---------- activate: drop old shell caches (never the OCR cache), enable preload ---------- */
self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const keep = new Set([SHELL_CACHE, OCR_CACHE]);
    for (const key of await caches.keys()) {
      if ((key.startsWith('unique-') || key.startsWith('younique-')) && !keep.has(key)) await caches.delete(key);
    }
    if (self.registration.navigationPreload) {
      try { await self.registration.navigationPreload.enable(); } catch (_) { /* optional */ }
    }
    await self.clients.claim();
  })());
});

/* ---------- messages from the page ---------- */
self.addEventListener('message', (event) => {
  const data = event.data || {};
  const client = event.source;
  if (data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  } else if (data.type === 'GET_VERSION') {
    if (client) client.postMessage({ type: 'VERSION', version: VERSION });
  } else if (data.type === 'PRECACHE_OCR') {
    event.waitUntil(precacheOcr(client));
  } else if (data.type === 'OCR_STATUS') {
    event.waitUntil(ocrStatus().then((s) => client && client.postMessage({ type: 'OCR_STATUS', ...s })));
  }
});

async function ocrStatus() {
  const cache = await caches.open(OCR_CACHE);
  const have = [];
  for (const f of OCR_FILES) if (await cache.match(f)) have.push(f);
  return { total: OCR_FILES.length, cached: have.length, ready: have.length === OCR_FILES.length };
}

async function precacheOcr(client) {
  const cache = await caches.open(OCR_CACHE);
  let done = 0;
  for (const file of OCR_FILES) {
    try {
      if (!(await cache.match(file))) {
        const res = await fetch(file, { cache: 'reload' });
        if (!res.ok) throw new Error(file + ' → ' + res.status);
        await cache.put(file, res);
      }
      done++;
      if (client) client.postMessage({ type: 'OCR_PROGRESS', done, total: OCR_FILES.length, file });
    } catch (err) {
      if (client) client.postMessage({ type: 'OCR_ERROR', message: String(err && err.message || err), file });
      return;
    }
  }
  if (client) client.postMessage({ type: 'OCR_READY', total: OCR_FILES.length });
}

/* ---------- fetch ---------- */
self.addEventListener('fetch', (event) => {
  const req = event.request;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;          // never touch other origins
  const isOcr = url.pathname.includes('/vendor/tesseract/');

  if (req.method === 'HEAD' && isOcr) { event.respondWith(headFromCache(req)); return; }
  if (req.method !== 'GET') return;

  if (req.mode === 'navigate') { event.respondWith(handleNavigation(event)); return; }
  if (isOcr) { event.respondWith(cacheFirst(req, OCR_CACHE)); return; }
  event.respondWith(staleWhileRevalidate(event, SHELL_CACHE));
});

/* The app verifies OCR files with HEAD; answer from cache so that works offline. */
async function headFromCache(req) {
  const hit = await caches.match(req.url, { ignoreSearch: true });
  if (hit) {
    return new Response(null, {
      status: 200,
      headers: {
        'content-type': hit.headers.get('content-type') || 'application/octet-stream',
        'content-length': hit.headers.get('content-length') || ''
      }
    });
  }
  try { return await fetch(req); } catch (_) { return new Response(null, { status: 504, statusText: 'offline and not cached' }); }
}

async function cacheFirst(req, cacheName) {
  const cache = await caches.open(cacheName);
  const hit = await cache.match(req, { ignoreSearch: true });
  if (hit) return hit;
  const res = await fetch(req);
  if (res.ok && res.status === 200) cache.put(req, res.clone()).catch(() => {});
  return res;
}

async function staleWhileRevalidate(event, cacheName) {
  const cache = await caches.open(cacheName);
  const hit = await cache.match(event.request, { ignoreSearch: true });
  const network = fetch(event.request).then((res) => {
    if (res.ok && res.status === 200) cache.put(event.request, res.clone()).catch(() => {});
    return res;
  });
  if (hit) { event.waitUntil(network.catch(() => {})); return hit; }
  try { return await network; } catch (err) { return new Response('', { status: 504, statusText: 'offline' }); }
}

async function handleNavigation(event) {
  const cache = await caches.open(SHELL_CACHE);
  try {
    const preload = event.preloadResponse ? await event.preloadResponse : null;
    const fresh = preload || await Promise.race([
      fetch(event.request),
      new Promise((_, reject) => setTimeout(() => reject(new Error('timeout')), NAV_TIMEOUT_MS))
    ]);
    if (fresh && fresh.ok && fresh.status === 200) cache.put('./index.html', fresh.clone()).catch(() => {});
    return fresh;
  } catch (_) {
    const fallback = await cache.match('./index.html') || await cache.match('./');
    return fallback || new Response('آفلاین هستید و برنامه هنوز روی این دستگاه ذخیره نشده است.', {
      status: 503, headers: { 'content-type': 'text/plain; charset=utf-8' }
    });
  }
}
