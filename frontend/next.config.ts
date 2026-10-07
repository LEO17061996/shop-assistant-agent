import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  images: {
    // Product photos come straight from the public Amazon Berkeley Objects bucket
    remotePatterns: [
      { protocol: "https", hostname: "amazon-berkeley-objects.s3.amazonaws.com", pathname: "/images/small/**" },
    ],
  },
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
