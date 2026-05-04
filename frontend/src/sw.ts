/// <reference lib="webworker" />

import { clientsClaim, setCacheNameDetails } from "workbox-core";
import { ExpirationPlugin } from "workbox-expiration";
import { cleanupOutdatedCaches, createHandlerBoundToURL, precacheAndRoute } from "workbox-precaching";
import { registerRoute, NavigationRoute } from "workbox-routing";
import { CacheFirst, NetworkOnly } from "workbox-strategies";

declare let self: ServiceWorkerGlobalScope & {
  __WB_MANIFEST: Array<unknown>;
};

const CURRENT_CACHE_PREFIX = "anaprilin-pwa-v4";
const MEDIA_CACHE = `${CURRENT_CACHE_PREFIX}-media`;
const LEGACY_RUNTIME_CACHES = new Set(["assets-cache", "api-get-cache", "media-cache", "html-cache"]);
const LEGACY_CACHE_PREFIXES = ["workbox-", "anaprilin-pwa-v1", "anaprilin-pwa-v2", "anaprilin-pwa-v3"];

setCacheNameDetails({ prefix: CURRENT_CACHE_PREFIX });

self.skipWaiting();
clientsClaim();

precacheAndRoute(self.__WB_MANIFEST, {
  ignoreURLParametersMatching: [/^utm_/, /^fbclid$/, /^source$/, /^screen$/, /^day$/, /^slot$/, /^after_reset$/, /^v$/]
});
cleanupOutdatedCaches();

async function deleteLegacyCaches(): Promise<void> {
  const cacheNames = await caches.keys();
  await Promise.all(
    cacheNames.map((cacheName) => {
      const isCurrentCache = cacheName.startsWith(`${CURRENT_CACHE_PREFIX}-`);
      const isLegacyCache =
        LEGACY_RUNTIME_CACHES.has(cacheName) || LEGACY_CACHE_PREFIXES.some((prefix) => cacheName.startsWith(prefix));

      return !isCurrentCache && isLegacyCache ? caches.delete(cacheName) : Promise.resolve(false);
    })
  );
}

self.addEventListener("activate", (event) => {
  event.waitUntil(deleteLegacyCaches());
});

self.addEventListener("message", (event) => {
  if (event.data?.type === "SKIP_WAITING") {
    self.skipWaiting();
  }

  if (event.data?.type === "CLEAR_LEGACY_CACHES") {
    event.waitUntil(deleteLegacyCaches());
  }
});

const appShellFallback = createHandlerBoundToURL("/index.html");

const navigationHandler = async (options: Parameters<typeof appShellFallback>[0]): Promise<Response> => {
  try {
    const networkResponse = await fetch(options.request, {
      cache: "no-store",
      credentials: "same-origin",
      redirect: "follow",
      headers: {
        "Cache-Control": "no-cache",
        Pragma: "no-cache"
      }
    });

    const contentType = networkResponse.headers.get("content-type") ?? "";
    if (networkResponse.ok && contentType.includes("text/html")) {
      return networkResponse;
    }
  } catch {
    // Offline start: fall back to the precached app shell.
  }

  return appShellFallback(options);
};

registerRoute(
  new NavigationRoute(navigationHandler, {
    denylist: [/^\/api(?:\/|$)/, /^\/sw\.js$/, /^\/manifest\.webmanifest$/, /\/[^/?]+\.[^/]+$/]
  })
);

registerRoute(
  ({ url }) => url.origin === self.location.origin && url.pathname.startsWith("/api/"),
  new NetworkOnly(),
  "GET"
);

for (const method of ["POST", "PUT", "PATCH", "DELETE"] as const) {
  registerRoute(
    ({ url }) => url.origin === self.location.origin && url.pathname.startsWith("/api/"),
    new NetworkOnly(),
    method
  );
}

registerRoute(
  ({ request, url }) =>
    request.method === "GET" &&
    url.origin === self.location.origin &&
    (request.destination === "image" || request.destination === "font"),
  new CacheFirst({
    cacheName: MEDIA_CACHE,
    plugins: [new ExpirationPlugin({ maxEntries: 100, maxAgeSeconds: 60 * 60 * 24 * 30 })]
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
