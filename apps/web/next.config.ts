import { existsSync } from "node:fs";
import path from "node:path";

import createNextIntlPlugin from "next-intl/plugin";
import type { NextConfig } from "next";

// The repository keeps one secrets file, .env.local at its root, read by the
// API and by this app alike. Next on its own only looks in apps/web, which
// would mean two copies of every secret, drifting apart.
//
// Node's own loader rather than @next/env: Next has already called
// loadEnvConfig for apps/web by the time this file runs, and @next/env caches
// that first result, so a second call for another directory silently returns
// the cached, empty answer. process.loadEnvFile has no cache, and like Next it
// never overrides a variable that is already set — so CI and the compose
// stack, which set real environment variables, are unaffected.
const rootEnv = path.resolve(process.cwd(), "../../.env.local");
if (existsSync(rootEnv)) process.loadEnvFile(rootEnv);

const withNextIntl = createNextIntlPlugin("./i18n/request.ts");

const nextConfig: NextConfig = {
  // Workspace packages ship TypeScript source, not a build step.
  transpilePackages: ["@satsaathi/api-client"],
  // This repo keeps its own agent guidance; don't scaffold a competing copy.
  agentRules: false,
};

export default withNextIntl(nextConfig);
