import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  basePath: "/frontend/chat-app",
  output: "export",
  trailingSlash: true,
  turbopack: {
    root: process.cwd(),
  },
  experimental: {
    optimizePackageImports: ["lucide-react"],
  },
};

export default nextConfig;
