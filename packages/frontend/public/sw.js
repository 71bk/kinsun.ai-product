// Minimal offline-shell service worker for the elder-care PWA.
// Voice interaction itself requires network connectivity (WebSocket to the
// backend); this cache only keeps the app shell available so navigation
// doesn't fail outright when connectivity briefly drops.
const CACHE_NAME = 'elderly-care-shell-v1';
const APP_SHELL = ['/', '/manifest.json'];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL)).then(() => self.skipWaiting()),
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') return;
  event.respondWith(
    caches.match(event.request).then((cached) => cached ?? fetch(event.request).catch(() => caches.match('/'))),
  );
});
