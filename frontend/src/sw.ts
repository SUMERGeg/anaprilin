/// <reference lib="webworker" />

import { clientsClaim, setCacheNameDetails } from "workbox-core";
import { ExpirationPlugin } from "workbox-expiration";
import { addRoute, cleanupOutdatedCaches, createHandlerBoundToURL, precache } from "workbox-precaching";
import { registerRoute, NavigationRoute } from "workbox-routing";
import { CacheFirst, NetworkOnly } from "workbox-strategies";

declare let self: ServiceWorkerGlobalScope & {
  __WB_MANIFEST: Array<unknown>;
};

const CURRENT_CACHE_PREFIX = "anaprilin-pwa-v3";
const MEDIA_CACHE = `${CURRENT_CACHE_PREFIX}-media`;
const LEGACY_RUNTIME_CACHES = new Set(["assets-cache", "api-get-cache", "media-cache", "html-cache"]);
const LEGACY_CACHE_PREFIXES = ["workbox-", "anaprilin-pwa-v1", "anaprilin-pwa-v2"];

setCacheNameDetails({ prefix: CURRENT_CACHE_PREFIX });

self.skipWaiting();
clientsClaim();

precache(self.__WB_MANIFEST);
cleanupOutdatedCaches();

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      const cacheNames = await caches.keys();
      await Promise.all(
        cacheNames.map((cacheName) => {
          const isCurrentCache = cacheName.startsWith(`${CURRENT_CACHE_PREFIX}-`);
          const isLegacyCache =
            LEGACY_RUNTIME_CACHES.has(cacheName) || LEGACY_CACHE_PREFIXES.some((prefix) => cacheName.startsWith(prefix));

          return !isCurrentCache && isLegacyCache ? caches.delete(cacheName) : Promise.resolve(false);
        })
      );
    })()
  );
});

const appShellFallback = createHandlerBoundToURL("/index.html");
const navigationHandler = async (options: Parameters<typeof appShellFallback>[0]): Promise<Response> => {
  try {
    const networkResponse = await fetch(new Request(options.request, { cache: "no-store" }));
    if (networkResponse.ok) {
      return networkResponse;
    }
  } catch {
    // Fall through to the precached app shell for offline starts.
  }

  return appShellFallback(options);
};

registerRoute(new NavigationRoute(navigationHandler, { denylist: [/^\/api\//, /\/[^/?]+\.[^/]+$/] }));

addRoute();

registerRoute(
  ({ request }) => request.destination === "image" || request.destination === "font",
  new CacheFirst({
    cacheName: MEDIA_CACHE,
    plugins: [new ExpirationPlugin({ maxEntries: 100, maxAgeSeconds: 60 * 60 * 24 * 30 })]
  })
);

for (const method of ["GET", "POST", "PUT", "PATCH", "DELETE"] as const) {
  registerRoute(({ url }) => url.pathname.startsWith("/api/"), new NetworkOnly(), method);
}

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
