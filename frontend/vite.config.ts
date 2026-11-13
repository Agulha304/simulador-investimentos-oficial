import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// A porta do backend é configurável (BACKEND_PORT) para não colidir com outros projetos na 8000.
const backend = `http://localhost:${process.env.BACKEND_PORT ?? "8000"}`;

export default defineConfig({
  plugins: [react()],
  server: {
    port: Number(process.env.FRONTEND_PORT ?? 5173),
    proxy: { "/api": backend },
  },
});
