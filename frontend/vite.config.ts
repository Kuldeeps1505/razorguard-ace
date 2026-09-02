import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/agent": "http://127.0.0.1:8000",
      "/intents": "http://127.0.0.1:8000",
      "/policy": "http://127.0.0.1:8000",
      "/consents": "http://127.0.0.1:8000",
      "/merchants": "http://127.0.0.1:8000",
      "/audit/events": "http://127.0.0.1:8000",
      "/security/dashboard": "http://127.0.0.1:8000",
      "/payments": "http://127.0.0.1:8000",
      "/protocols": "http://127.0.0.1:8000",
      "/health": "http://127.0.0.1:8000",
    },
  },
});
