import path from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  base: "/static/",
  plugins: [react(), tailwindcss()],
  esbuild: {
    keepNames: true,
  },
  server: {
    proxy: {
      "/api": {
        target: process.env.DEFAULTSPACK_API_TARGET || "http://127.0.0.1:8766",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: path.resolve(__dirname, "../ui"),
    emptyOutDir: false,
    cssMinify: "esbuild",
    cssCodeSplit: false,
    assetsDir: ".",
    rollupOptions: {
      output: {
        entryFileNames: "shell-app.js",
        chunkFileNames: "shell-[name].js",
        manualChunks(id) {
          if (!id.includes("node_modules")) return undefined;
          if (id.includes("react-markdown") || id.includes("micromark") || id.includes("remark") || id.includes("mdast") || id.includes("hast")) {
            return "markdown";
          }
          if (id.includes("motion")) {
            return "motion";
          }
          if (id.includes("lucide-react")) {
            return "icons";
          }
          return "vendor";
        },
        assetFileNames: (assetInfo) => {
          if ((assetInfo.names ?? []).some((name) => name.endsWith(".css"))) {
            return "shell-app.css";
          }
          return "[name][extname]";
        },
      },
    },
  },
});
