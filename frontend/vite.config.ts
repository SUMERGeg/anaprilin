import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      strategies: "injectManifest",
      srcDir: "src",
      filename: "sw.ts",
      injectRegister: false,
      manifest: false,
      injectManifest: {
        globPatterns: ["**/*.{html,js,css,png,svg,ico,webmanifest}"],
        maximumFileSizeToCacheInBytes: 5 * 1024 * 1024
      }
    })
  ]
});
