/* Younique 46.0.2 — standalone PWA cache */
'use strict';
const CACHE_NAME = 'younique-v46.0.2';
const APP_SHELL = ['./index.html','./manifest.json','./icon-192.png','./icon-512.png'];
self.addEventListener('install', event => {
  event.waitUntil((async () => { const cache = await caches.open(CACHE_NAME); await cache.addAll(APP_SHELL); await self.skipWaiting(); })());
});
self.addEventListener('activate', event => {
  event.waitUntil((async () => { const keys = await caches.keys(); await Promise.all(keys.filter(key => key.startsWith('younique-') && key !== CACHE_NAME).map(key => caches.delete(key))); await self.clients.claim(); })());
});
self.addEventListener('fetch', event => {
  const request = event.request; if (request.method !== 'GET') return;
  const url = new URL(request.url); if (url.origin !== self.location.origin) return;
  if (request.mode === 'navigate') {
    event.respondWith((async () => { try { const response = await fetch(request); if (response && response.ok) { const cache = await caches.open(CACHE_NAME); await cache.put('./index.html', response.clone()); } return response; } catch (_) { return (await caches.match('./index.html')) || Response.error(); } })()); return;
  }
  event.respondWith((async () => { const cached = await caches.match(request); if (cached) return cached; try { const response = await fetch(request); if (response && response.ok && response.type === 'basic') { const cache = await caches.open(CACHE_NAME); await cache.put(request, response.clone()); } return response; } catch (_) { return Response.error(); } })());
});
