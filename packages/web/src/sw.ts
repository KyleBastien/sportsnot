/// <reference lib="webworker" />

import { clientsClaim } from 'workbox-core';
import { precacheAndRoute, matchPrecache } from 'workbox-precaching';
import { registerRoute, setCatchHandler, Route } from 'workbox-routing';
import {
  CacheFirst,
  StaleWhileRevalidate,
  NetworkFirst,
} from 'workbox-strategies';
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
        new ExpirationPlugin({
          maxEntries: 100,
          maxAgeSeconds: 30 * 24 * 60 * 60,
        }),
      ],
    })
  )
);

// Stale-while-revalidate for API responses (rosters, standings)
registerRoute(
  new Route(
    ({ url }) =>
      url.pathname.includes('/rest/') || url.hostname.includes('supabase'),
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
      plugins: [new CacheableResponsePlugin({ statuses: [0, 200] })],
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

// Handle push notifications
self.addEventListener('push', (event) => {
  const defaultPayload = {
    title: 'SportsNot',
    body: 'You have a new notification',
    icon: '/favicon.ico',
    clickAction: '/',
  };

  let payload = defaultPayload;
  try {
    if (event.data) {
      payload = { ...defaultPayload, ...event.data.json() };
    }
  } catch {
    // Fall back to text if not JSON
    if (event.data) {
      payload = { ...defaultPayload, body: event.data.text() };
    }
  }

  event.waitUntil(
    self.registration.showNotification(payload.title, {
      body: payload.body,
      icon: payload.icon,
      data: { clickAction: payload.clickAction },
    })
  );
});

// Handle notification click - navigate to the action URL
self.addEventListener('notificationclick', (event) => {
  event.notification.close();

  const clickAction = event.notification.data?.clickAction || '/';

  event.waitUntil(
    self.clients
      .matchAll({ type: 'window', includeUncontrolled: true })
      .then((clientList) => {
        // Focus existing window if available
        for (const client of clientList) {
          if ('focus' in client) {
            (client as WindowClient).focus();
            (client as WindowClient).navigate(clickAction);
            return;
          }
        }
        // Open new window otherwise
        return self.clients.openWindow(clickAction);
      })
  );
});

// Listen for skip waiting message
self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
});
