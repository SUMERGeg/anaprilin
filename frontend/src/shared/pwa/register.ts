const SERVICE_WORKER_VERSION = "2026-05-04-standalone-v4";
const SERVICE_WORKER_URL = `/sw.js?v=${SERVICE_WORKER_VERSION}`;

function activateWaitingServiceWorker(registration: ServiceWorkerRegistration): void {
  if (registration.waiting) {
    registration.waiting.postMessage({ type: "SKIP_WAITING" });
  }
}

export function registerAppServiceWorker(): void {
  if (!("serviceWorker" in navigator)) {
    return;
  }

  let reloadedForUpdate = false;

  navigator.serviceWorker.addEventListener("controllerchange", () => {
    if (reloadedForUpdate) {
      return;
    }

    reloadedForUpdate = true;
    window.location.reload();
  });

  window.addEventListener("load", () => {
    navigator.serviceWorker
      .register(SERVICE_WORKER_URL, { scope: "/" })
      .then((registration) => {
        activateWaitingServiceWorker(registration);
        registration.active?.postMessage({ type: "CLEAR_LEGACY_CACHES" });

        registration.addEventListener("updatefound", () => {
          const installingWorker = registration.installing;
          if (!installingWorker) {
            return;
          }

          installingWorker.addEventListener("statechange", () => {
            if (installingWorker.state === "installed" && navigator.serviceWorker.controller) {
              activateWaitingServiceWorker(registration);
            }
          });
        });

        void registration.update();
      })
      .catch((error) => {
        console.warn("Service worker registration failed:", error);
      });
  });
}
