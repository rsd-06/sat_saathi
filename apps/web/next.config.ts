import createNextIntlPlugin from "next-intl/plugin";
import type { NextConfig } from "next";

const withNextIntl = createNextIntlPlugin("./i18n/request.ts");

const nextConfig: NextConfig = {
  // This repo keeps its own agent guidance; don't scaffold a competing copy.
  agentRules: false,
};

export default withNextIntl(nextConfig);
