import { registerSW } from "virtual:pwa-register";

export function registerServiceWorker(): void {
  registerSW({
    immediate: true,
    onOfflineReady() {
      console.info("PWA ready for offline usage.");
    },
    onRegisterError(error) {
      console.error("SW register failed:", error);
    }
  });
}

