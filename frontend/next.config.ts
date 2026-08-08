import type { NextConfig } from "next";

import { buildSecurityHeaders } from "./src/lib/securityHeaders";

const nextConfig: NextConfig = {
  skipTrailingSlashRedirect: true,
  async headers() {
    // NEXT_PUBLIC_API_URL is the cross-origin API in production; unset in local
    // dev, where rewrites proxy /api to same-origin (so connect-src 'self').
    return [
      {
        source: "/:path*",
        headers: buildSecurityHeaders(process.env.NEXT_PUBLIC_API_URL),
      },
    ];
  },
  async rewrites() {
    const apiTarget = process.env.API_PROXY_TARGET ?? "http://127.0.0.1:8000";
    return [
      {
        source: "/api/v1/schedule",
        destination: `${apiTarget}/api/v1/schedule/`,
      },
      {
        source: "/api/v1/schedule/",
        destination: `${apiTarget}/api/v1/schedule/`,
      },
      {
        source: "/api/:path*",
        destination: `${apiTarget}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
