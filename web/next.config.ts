import type { NextConfig } from "next";

const config: NextConfig = {
  async headers() {
    return [{ source: "/:path*", headers: [{ key: "X-Frame-Options", value: "DENY" }] }];
  },
};

export default config;
