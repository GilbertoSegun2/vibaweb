// Service Worker blindado para Viba-Web
const CACHE_NAME = 'vibaweb-v2'; // ⭐ Subimos la versión para forzar la actualización

const urlsToCache = [
    '/static/css/vibaweb.css',
    '/static/img/pwa/icon-192x192.png',
];

// ⭐ BLINDAJE: Forzar la activación inmediata del nuevo SW
self.addEventListener('install', (event) => {
    self.skipWaiting();
    event.waitUntil(
        caches.open(CACHE_NAME).then(cache => cache.addAll(urlsToCache))
    );
});

// ⭐ BLINDAJE: Tomar el control de las pestañas abiertas y limpiar cachés viejas
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

// ⭐ BLINDAJE: Si el fetch falla, no bloquear la página
self.addEventListener('fetch', (event) => {
    // Solo interceptar peticiones GET
    if (event.request.method !== 'GET') return;

    // ⭐ IGNORAR peticiones de navegación (HTML) para no romper el login/logout ni el mapa
    if (event.request.mode === 'navigate') {
        return; // El navegador carga la página directamente de internet
    }

    // Para recursos estáticos, intentar caché con red de respaldo
    event.respondWith(
        caches.match(event.request).then((response) => {
            return response || fetch(event.request).catch(() => {
                return new Response('', { status: 408, statusText: 'Request Timeout' });
            });
        })
    );
});
