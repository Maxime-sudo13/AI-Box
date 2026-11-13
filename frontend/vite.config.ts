import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import pkg from "./package.json";

export default defineConfig({
  plugins: [react()],
  // Affichée en bas du menu : permet de vérifier quelle version de l'interface est servie.
  define: { __APP_VERSION__: JSON.stringify(pkg.version) },
  server: {
    // En développement, l'API tourne à part ; en production, Caddy fait ce routage.
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
});
