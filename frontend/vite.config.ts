import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      strategies: "injectManifest",
      srcDir: "src",
      filename: "sw.ts",
      injectRegister: "auto",
      manifest: {
        name: "Anaprilin Reminder",
        short_name: "Anaprilin",
        start_url: "/",
        display: "standalone",
        background_color: "#ffffff",
        theme_color: "#0b6bcb",
        lang: "ru",
        icons: []
      }
    })
  ]
});

