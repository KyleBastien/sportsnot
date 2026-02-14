/* eslint-disable no-undef */
/// <reference lib="webworker" />

import { clientsClaim } from 'workbox-core';
import { precacheAndRoute, matchPrecache } from 'workbox-precaching';
import { registerRoute, setCatchHandler, Route } from 'workbox-routing';
import { CacheFirst, StaleWhileRevalidate, NetworkFirst } from 'workbox-strategies';
import { ExpirationPlugin } from 'workbox-expiration';
import { CacheableResponsePlugin } from 'workbox-cacheable-response';

declare const self: ServiceWorkerGlobalScope;

clientsClaim();

// Precache static assets injected by Workbox at build time
// This includes offline.html
precacheAndRoute(self.__WB_MANIFEST);

// Cache-first for static assets (JS, CSS, images, fonts)
registerRoute(
  new Route(
    ({ request }) =>
      request.destination === 'script' ||
      request.destination === 'style' ||
      request.destination === 'image' ||
      request.destination === 'font',
    new CacheFirst({
      cacheName: 'static-assets',
      plugins: [
        new CacheableResponsePlugin({ statuses: [0, 200] }),
        new ExpirationPlugin({ maxEntries: 100, maxAgeSeconds: 30 * 24 * 60 * 60 }),
      ],
    })
  )
);

// Stale-while-revalidate for API responses (rosters, standings)
registerRoute(
  new Route(
    ({ url }) =>
      url.pathname.includes('/rest/') ||
      url.hostname.includes('supabase'),
    new StaleWhileRevalidate({
      cacheName: 'api-responses',
      plugins: [
        new CacheableResponsePlugin({ statuses: [0, 200] }),
        new ExpirationPlugin({ maxEntries: 50, maxAgeSeconds: 24 * 60 * 60 }),
      ],
    })
  )
);

// Network-first for HTML navigation requests
registerRoute(
  new Route(
    ({ request }) => request.mode === 'navigate',
    new NetworkFirst({
      cacheName: 'pages',
      plugins: [
        new CacheableResponsePlugin({ statuses: [0, 200] }),
      ],
    })
  )
);

// Offline fallback when all strategies fail
setCatchHandler(async ({ request }: { request: Request }) => {
  if (request.destination === 'document') {
    const fallback = await matchPrecache('/offline.html');
    return fallback || Response.error();
  }
  return Response.error();
});

// Listen for skip waiting message
self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
});
