import type { NextConfig } from "next";

const backend = process.env.SHELL_BACKEND_URL ?? "http://127.0.0.1:8100";
const config: NextConfig = {
  allowedDevOrigins: ["127.0.0.1", "localhost"],
  async rewrites() {
    return [
      { source: "/shell-api/:path*", destination: `${backend}/:path*` },
      { source: "/viewer/:path*", destination: `${backend}/viewer/:path*` },
    ];
  },
};

export default config;
