import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In development, /api calls are forwarded to the FastAPI service (backend/expose_backend.py).
// Set VIGIL_API_URL to point at a different API host.
export default defineConfig({
    plugins: [react()],
    server: {
        port: 5174,
        proxy: {
            "/api": process.env.VIGIL_API_URL || "http://localhost:8001",
        },
    },
});
