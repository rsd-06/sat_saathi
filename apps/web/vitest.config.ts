import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    // e2e/ holds Playwright specs, which have their own runner and config.
    exclude: ["**/node_modules/**", "**/.next/**", "e2e/**"],
  },
});
