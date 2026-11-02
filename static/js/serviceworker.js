// Service Worker ultra-seguro para Viba-Web
const CACHE_NAME = 'vibaweb-v3';

self.addEventListener('install', (event) => {
    self.skipWaiting();
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((cacheNames) => {
            return Promise.all(
                cacheNames.map((cacheName) => {
                    if (cacheName !== CACHE_NAME) {
                        return caches.delete(cacheName);
                    }
                })
            );
        }).then(() => self.clients.claim())
    );
});

self.addEventListener('fetch', (event) => {
    // Solo cachear imágenes (que no cambian)
    if (event.request.destination === 'image') {
        event.respondWith(
            caches.match(event.request).then((response) => {
                return response || fetch(event.request);
            })
        );
        return;
    }
    
    // Para todo lo demás (HTML, JS, CSS, API), NO interceptar.
    // El navegador los carga directamente de internet.
});
