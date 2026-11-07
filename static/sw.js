// Service Worker - Presensi Ekskul MTs Muhammadiyah Tajurhalang
const CACHE_NAME = 'presensi-ekskul-v2';
const STATIC_ASSETS = [
  '/',
  '/static/style.css',
  '/static/app.js',
  '/static/logo-mtsm.png',
  '/static/icon-192.png',
  '/static/icon-512.png',
  '/static/manifest.json'
];

// Install Event: Pre-cache static assets
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      console.log('[SW] Pre-caching static assets');
      return cache.addAll(STATIC_ASSETS).catch((err) => {
        console.warn('[SW] Non-fatal pre-cache skip:', err);
      });
    })
  );
  self.skipWaiting();
});

// Activate Event: Cleanup older caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.map((key) => {
          if (key !== CACHE_NAME) {
            console.log('[SW] Removing old cache:', key);
            return caches.delete(key);
          }
        })
      );
    })
  );
  self.clients.claim();
});

// Fetch Event: Network-first for dynamic navigation, Cache-first for static assets
self.addEventListener('fetch', (event) => {
  const request = event.request;
  const url = new URL(request.url);

  // Jangan tangani selain GET atau request ke luar domain
  if (request.method !== 'GET' || url.origin !== location.origin) {
    return;
  }

  // Static assets: Cache First, fallback to Network
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.match(request).then((cachedResponse) => {
        if (cachedResponse) {
          return cachedResponse;
        }
        return fetch(request).then((networkResponse) => {
          if (networkResponse && networkResponse.status === 200) {
            const responseClone = networkResponse.clone();
            caches.open(CACHE_NAME).then((cache) => {
              cache.put(request, responseClone);
            });
          }
          return networkResponse;
        });
      })
    );
    return;
  }

  // Dynamic pages (HTML / API): Network First, fallback to Cache
  event.respondWith(
    fetch(request)
      .then((networkResponse) => {
        // Cache copy of valid successful responses
        if (networkResponse && networkResponse.status === 200) {
          const responseClone = networkResponse.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(request, responseClone);
          });
        }
        return networkResponse;
      })
      .catch(() => {
        // Jika offline, ambil dari cache
        return caches.match(request).then((cachedResponse) => {
          if (cachedResponse) {
            return cachedResponse;
          }
          // Fallback offline message jika halaman belum ada di cache
          return new Response(
            '<!DOCTYPE html><html lang="id"><head><meta charset="UTF-8"><title>Offline — Presensi Ekskul</title>' +
            '<meta name="viewport" content="width=device-width, initial-scale=1.0">' +
            '<style>body{font-family:sans-serif;text-align:center;padding:40px 20px;background:#0f172a;color:#fff;}' +
            'h1{color:#f59e0b;}p{color:#cbd5e1;line-height:1.6;}</style></head>' +
            '<body><h1>📡 Anda Sedang Offline</h1>' +
            '<p>Koneksi internet tidak tersedia.<br>Silakan periksa jaringan Wi-Fi atau paket data di HP Anda lalu muat ulang halaman.</p>' +
            '<button onclick="location.reload()" style="background:#2563eb;color:#fff;border:none;padding:10px 20px;border-radius:8px;font-weight:bold;cursor:pointer;margin-top:15px;">🔄 Coba Lagi</button>' +
            '</body></html>',
            { headers: { 'Content-Type': 'text/html; charset=utf-8' } }
          );
        });
      })
  );
});
