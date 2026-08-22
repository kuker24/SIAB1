/**
 * Service Worker for Exam System PWA
 * Provides offline caching for critical assets
 *
 * Version: 1.0 (Phase 2 Offline Resilience)
 */

const CACHE_NAME = 'exam-system-v20260430-perf1';
const OFFLINE_URL = '/student/';

// Critical assets to cache for resilient APK WebView startup.
// Keep versions aligned with the student runtime templates.
const CACHE_ASSETS = [
    '/student/',
    '/student/dashboard.html',
    '/static/css/student.css',
    '/static/css/exam.css?v=20260418-richtext1',
    '/static/js/auth.js?v=20260226-hotfix1',
    '/static/js/api.js?v=20260306-phase4',
    '/static/js/exam-system.js?v=20260418-richtext1'
];

// Install event - cache critical assets
self.addEventListener('install', (event) => {

    event.waitUntil(
        caches.open(CACHE_NAME)
            .then((cache) => {
                return cache.addAll(CACHE_ASSETS);
            })
            .then(() => {
                self.skipWaiting();
            })
    );
});

// Activate event - clean old caches
self.addEventListener('activate', (event) => {

    event.waitUntil(
        caches.keys().then((cacheNames) => {
            return Promise.all(
                cacheNames
                    .filter((name) => name !== CACHE_NAME)
                    .map((name) => caches.delete(name))
            );
        }).then(() => {
            self.clients.claim();
        })
    );
});

// Fetch event - serve from cache, fallback to network
self.addEventListener('fetch', (event) => {
    // Only handle GET requests
    if (event.request.method !== 'GET') return;

    // Skip API requests (they should always go to network)
    if (event.request.url.includes('/api/')) return;

    event.respondWith(
        fetch(event.request)
            .then((response) => {
                // Clone the response for caching
                const responseClone = response.clone();

                // Cache successful responses
                if (response.status === 200) {
                    caches.open(CACHE_NAME).then((cache) => {
                        cache.put(event.request, responseClone);
                    });
                }

                return response;
            })
            .catch(() => {
                // Network failed, try cache
                return caches.match(event.request)
                    .then((cachedResponse) => {
                        if (cachedResponse) {
                            return cachedResponse;
                        }

                        // For navigation requests, show offline page
                        if (event.request.mode === 'navigate') {
                            return caches.match(OFFLINE_URL);
                        }

                        return new Response('Offline', {
                            status: 503,
                            statusText: 'Service Unavailable'
                        });
                    });
            })
    );
});

// Background sync for pending answers (when supported)
self.addEventListener('sync', (event) => {
    if (event.tag === 'sync-answers') {
        event.waitUntil(syncAnswers());
    }
});

async function syncAnswers() {
    // This will be handled by the AnswerSyncWorker in the main thread
    // Service Worker just triggers the sync event
    const clients = await self.clients.matchAll();
    clients.forEach(client => {
        client.postMessage({ type: 'SYNC_ANSWERS' });
    });
}
