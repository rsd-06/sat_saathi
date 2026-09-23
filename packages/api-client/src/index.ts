import createClient from "openapi-fetch";

import type { components, paths } from "./schema";

export type Schema = components["schemas"];
export type AssetOut = Schema["AssetOut"];
export type InputSetOut = Schema["InputSetOut"];
export type JobOut = Schema["JobOut"];
export type JobPage = Schema["JobPage"];
export type StepOut = Schema["StepOut"];
export type CheckOut = Schema["CheckOut"];
export type ToolOut = Schema["ToolOut"];
export type ReviewOut = Schema["ReviewOut"];
export type ErrorBody = Schema["ErrorBody"];

export const DEFAULT_BASE_URL = "http://localhost:8000";

export function createApiClient(baseUrl: string = DEFAULT_BASE_URL) {
  return createClient<paths>({ baseUrl });
}

export type ApiClient = ReturnType<typeof createApiClient>;

/**
 * Errors arrive as {"error": {"key", "params"}} so the interface can localise
 * them. This narrows an unknown failure body to that shape, falling back to a
 * generic key rather than surfacing an untranslated sentence.
 */
export function toErrorBody(value: unknown): ErrorBody {
  if (
    typeof value === "object" &&
    value !== null &&
    "error" in value &&
    typeof (value as { error: unknown }).error === "object"
  ) {
    const body = (value as { error: { key?: unknown; params?: unknown } }).error;
    if (typeof body.key === "string") {
      return {
        key: body.key,
        params: (body.params ?? {}) as Record<string, never>,
      };
    }
  }
  return { key: "http.error", params: {} as Record<string, never> };
}

export type { paths, components };
