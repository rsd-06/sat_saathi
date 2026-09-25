import "server-only";

import { cache } from "react";

import { apiUrl } from "./session";

export type PublicConfig = {
  mode: string;
  review_threshold_pct: number;
  max_upload_mb: number;
  google_sign_in: boolean;
};

/** Used only if the API cannot be asked; matches the server's own defaults. */
const FALLBACK: PublicConfig = {
  mode: "online",
  review_threshold_pct: 75,
  max_upload_mb: 512,
  google_sign_in: false,
};

/** The server's settings, asked once per request. */
export const getPublicConfig = cache(async (): Promise<PublicConfig> => {
  try {
    const response = await fetch(apiUrl("/api/v1/config"), {
      cache: "no-store",
      signal: AbortSignal.timeout(5_000),
    });
    return response.ok ? ((await response.json()) as PublicConfig) : FALLBACK;
  } catch {
    return FALLBACK;
  }
});
