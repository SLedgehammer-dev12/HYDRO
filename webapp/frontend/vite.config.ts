import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8080",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: process.env.HYDRO_SOURCEMAP === "true" ? "hidden" : false,
    chunkSizeWarningLimit: 500,
    rolldownOptions: {
      output: {
        codeSplitting: {
          groups: [
            {
              name: "vendor-react",
              test: /node_modules[\\/](react|react-dom|scheduler)[\\/]/,
              priority: 40,
            },
            {
              name: "vendor-state",
              test: /node_modules[\\/](@tanstack[\\/]react-query|zustand|use-sync-external-store|clsx|tailwind-merge)[\\/]/,
              priority: 35,
            },
            {
              name: "vendor-three",
              test: /node_modules[\\/]three[\\/]/,
              priority: 30,
            },
            {
              name: "vendor-r3f",
              test: /node_modules[\\/]@react-three[\\/]/,
              priority: 25,
            },
            {
              name: "vendor-charts",
              test: /node_modules[\\/](recharts|victory-vendor|@reduxjs[\\/]toolkit|immer|reselect|es-toolkit|decimal\.js-light|react-redux|eventemitter3)[\\/]/,
              includeDependenciesRecursively: false,
              priority: 25,
            },
          ],
        },
      },
    },
  },
});
