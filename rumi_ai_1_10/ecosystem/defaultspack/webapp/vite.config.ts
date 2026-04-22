import path from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    outDir: path.resolve(__dirname, "../ui"),
    emptyOutDir: false,
    cssCodeSplit: false,
    assetsDir: ".",
    rollupOptions: {
      output: {
        entryFileNames: "shell-app.js",
        chunkFileNames: "shell-app.js",
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
