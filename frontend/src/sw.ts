/// <reference lib="webworker" />

import { clientsClaim } from "workbox-core";
import { ExpirationPlugin } from "workbox-expiration";
import { precacheAndRoute, cleanupOutdatedCaches, createHandlerBoundToURL } from "workbox-precaching";
import { registerRoute, NavigationRoute } from "workbox-routing";
import { CacheFirst, NetworkFirst, StaleWhileRevalidate } from "workbox-strategies";

declare let self: ServiceWorkerGlobalScope & {
  __WB_MANIFEST: Array<unknown>;
};

self.skipWaiting();
clientsClaim();

precacheAndRoute(self.__WB_MANIFEST);
cleanupOutdatedCaches();

const navigationHandler = createHandlerBoundToURL("/index.html");
registerRoute(new NavigationRoute(navigationHandler));

registerRoute(
  ({ request }) => request.destination === "style" || request.destination === "script",
  new StaleWhileRevalidate({
    cacheName: "assets-cache"
  })
);

registerRoute(
  ({ request }) => request.destination === "image" || request.destination === "font",
  new CacheFirst({
    cacheName: "media-cache",
    plugins: [new ExpirationPlugin({ maxEntries: 100, maxAgeSeconds: 60 * 60 * 24 * 30 })]
  })
);

registerRoute(
  ({ request, url }) => request.method === "GET" && url.pathname.startsWith("/api/"),
  new NetworkFirst({
    cacheName: "api-get-cache",
    networkTimeoutSeconds: 3
  })
);

interface PushDataPayload {
  title?: string;
  body?: string;
  tag?: string;
  data?: {
    url?: string;
    day_key?: string;
    slot?: string;
    type?: string;
    nag_count?: number;
  };
}

self.addEventListener("push", (event) => {
  if (!event.data) return;
  let payload: PushDataPayload = {};
  try {
    payload = event.data.json() as PushDataPayload;
  } catch {
    payload = { title: "Напоминание", body: event.data.text() };
  }

  const title = payload.title ?? "Напоминание о приеме";
  const body = payload.body ?? "Открой приложение и отметь прием.";
  const url = payload.data?.url ?? "/?screen=today";

  event.waitUntil(
    self.registration.showNotification(title, {
      body,
      tag: payload.tag ?? "anaprilin-reminder",
      data: { url }
    })
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = (event.notification.data?.url as string | undefined) ?? "/?screen=today";

  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((clientList) => {
      for (const client of clientList) {
        const windowClient = client as WindowClient;
        if ("focus" in windowClient) {
          windowClient.navigate(url);
          return windowClient.focus();
        }
      }
      return self.clients.openWindow(url);
    })
  );
});

