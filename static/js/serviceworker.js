// Service Worker para Viba-Web
const CACHE_NAME = 'vibaweb-v1';
const urlsToCache = [
    '/static/css/vibaweb.css',
    '/static/img/pwa/icon-192x192.png',
];

self.addEventListener('install', event => {
    event.waitUntil(
        caches.open(CACHE_NAME).then(cache => cache.addAll(urlsToCache))
    );
});

self.addEventListener('fetch', event => {
    // NO cachear páginas HTML (navegación) para que el logout funcione
    if (event.request.mode === 'navigate') {
        event.respondWith(fetch(event.request));
        return;
    }
    
    // Para recursos estáticos, usar caché
    event.respondWith(
        caches.match(event.request).then(response => {
            return response || fetch(event.request);
        })
    );
});
