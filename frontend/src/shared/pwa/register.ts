const SERVICE_WORKER_URL = "/sw.js";

export function registerAppServiceWorker(): void {
  if (!("serviceWorker" in navigator)) {
    return;
  }

  const hadController = Boolean(navigator.serviceWorker.controller);
  let reloadedForUpdate = false;

  navigator.serviceWorker.addEventListener("controllerchange", () => {
    if (!hadController || reloadedForUpdate) {
      return;
    }

    reloadedForUpdate = true;
    window.location.reload();
  });

  window.addEventListener("load", () => {
    navigator.serviceWorker
      .register(SERVICE_WORKER_URL, { scope: "/" })
      .then((registration) => registration.update())
      .catch((error) => {
        console.warn("Service worker registration failed:", error);
      });
  });
}
