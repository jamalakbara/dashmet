import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  images: {
    // Allow Meta CDN image domains for ad creatives
    remotePatterns: [
      {
        protocol: "https",
        hostname: "**.facebook.com",
      },
      {
        protocol: "https",
        hostname: "**.fbcdn.net",
      },
    ],
  },
};

export default nextConfig;
