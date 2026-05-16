import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Minimal Docker-friendly build at .next/standalone
  output: "standalone",
  // Proxy /api/* and /ws/* to backend in dev so frontend can be same-origin
  async rewrites() {
    const backend = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    return [
      { source: "/api/:path*", destination: `${backend}/api/:path*` },
      { source: "/ws/:path*", destination: `${backend}/ws/:path*` },
    ];
  },
};

export default nextConfig;
