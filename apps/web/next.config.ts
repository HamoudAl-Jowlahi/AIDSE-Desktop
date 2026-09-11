import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "export",
  trailingSlash: true,
  images: {
    unoptimized: true,
  },
  // Both were true, so `next build` shipped regardless of type or lint errors.
  // tsc --noEmit is clean and eslint reports warnings only, so turning the
  // checks on costs nothing today and catches regressions from here on.
  eslint: {
    ignoreDuringBuilds: false,
  },
  typescript: {
    ignoreBuildErrors: false,
  },
};

export default nextConfig;
