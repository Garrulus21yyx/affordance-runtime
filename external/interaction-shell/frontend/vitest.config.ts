import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
  },
  resolve: {
    alias: [
      { find: "@copilotkit/react-core/v2", replacement: new URL("./src/test/copilotkit-v2-stub.tsx", import.meta.url).pathname },
      { find: "@", replacement: new URL("./src", import.meta.url).pathname },
    ],
  },
});
