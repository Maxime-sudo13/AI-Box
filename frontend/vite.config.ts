import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    // En développement, l'API tourne à part ; en production, Caddy fait ce routage.
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
});
