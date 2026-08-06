import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
  reactCompiler: true,
  // Use Vercel's default server build. `output: "standalone"` is intended
  // for custom Docker deployments and can cause .nft.json artifacts to be
  // required during the build. Removing it avoids the missing file error on
  // Vercel's managed build pipeline.
};

export default nextConfig;
