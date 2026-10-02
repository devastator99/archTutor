import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  turbopack: {
    // Pin the app root to the monorepo root explicitly. Without this, Turbopack
    // auto-detects the root by walking up looking for a lockfile, and picks up
    // an unrelated package-lock.json in the home directory.
    root: path.join(__dirname, ".."),
  },
};

export default nextConfig;
