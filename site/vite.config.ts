import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Static marketing site for NEXUS. It has no backend of its own; the Status page
// talks to a running NEXUS backend directly from the browser.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { host: "127.0.0.1", port: 5180 },
  preview: { host: "127.0.0.1", port: 4180 },
  build: {
    target: "es2022",
    sourcemap: false,
  },
});
