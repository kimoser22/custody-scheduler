import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  skipTrailingSlashRedirect: true,
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
