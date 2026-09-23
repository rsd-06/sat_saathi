"use client";

import {
  createApiClient,
  toErrorBody,
  type AssetOut,
  type ErrorBody,
  type InputSetOut,
  type JobOut,
  type JobPage,
  type ReviewOut,
  type StepOut,
  type ToolOut,
} from "@satsaathi/api-client";

export type {
  AssetOut,
  ErrorBody,
  InputSetOut,
  JobOut,
  JobPage,
  ReviewOut,
  StepOut,
  ToolOut,
};

export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const client = createApiClient(API_BASE);

/** Thrown for any non-2xx response; carries the localisable message key. */
export class ApiError extends Error {
  constructor(
    readonly body: ErrorBody,
    readonly status: number,
  ) {
    super(body.key);
    this.name = "ApiError";
  }
}

function unwrap<T>(result: {
  data?: T;
  error?: unknown;
  response: Response;
}): T {
  if (result.error !== undefined || result.data === undefined) {
    throw new ApiError(toErrorBody(result.error), result.response.status);
  }
  return result.data;
}

export async function uploadAsset(file: File): Promise<AssetOut> {
  // openapi-fetch does not build multipart bodies, so this one is hand-rolled.
  const form = new FormData();
  form.append("file", file);
  const response = await fetch(`${API_BASE}/api/v1/assets`, {
    method: "POST",
    body: form,
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(toErrorBody(payload), response.status);
  return payload as AssetOut;
}

export async function setAssetBands(
  assetId: string,
  body: { preset?: string; band_map?: Record<string, number> },
): Promise<AssetOut> {
  return unwrap(
    await client.PATCH("/api/v1/assets/{asset_id}/bands", {
      params: { path: { asset_id: assetId } },
      body,
    }),
  );
}

export async function createInputSet(
  mode: "single" | "fusion" | "change",
  assets: Record<string, string>,
): Promise<InputSetOut> {
  return unwrap(
    await client.POST("/api/v1/input-sets", {
      // The role map is typed per mode on the server; the client passes it on.
      body: { mode, assets } as never,
    }),
  );
}

export async function createJob(body: {
  input_set_id: string;
  query_text: string;
  query_lang: string;
  ui_lang: string;
}): Promise<JobOut> {
  return unwrap(await client.POST("/api/v1/jobs", { body }));
}

export async function getJob(jobId: string): Promise<JobOut> {
  return unwrap(
    await client.GET("/api/v1/jobs/{job_id}", {
      params: { path: { job_id: jobId } },
    }),
  );
}

export async function listJobs(limit = 20): Promise<JobPage> {
  return unwrap(
    await client.GET("/api/v1/jobs", { params: { query: { limit } } }),
  );
}

export async function listTools(): Promise<ToolOut[]> {
  return unwrap(await client.GET("/api/v1/tools", {}));
}

export async function listReview(): Promise<ReviewOut[]> {
  return unwrap(await client.GET("/api/v1/review", {}));
}

export async function decideReview(
  jobId: string,
  body: {
    decision: "approve" | "edit" | "reject";
    note?: string | null;
    edited_answer?: Record<string, never> | null;
  },
): Promise<ReviewOut> {
  return unwrap(
    await client.POST("/api/v1/review/{job_id}", {
      params: { path: { job_id: jobId } },
      body,
    }),
  );
}

export async function getHealth() {
  return unwrap(await client.GET("/api/v1/health", {}));
}

export function traceUrl(jobId: string): string {
  return `${API_BASE}/api/v1/jobs/${jobId}/trace`;
}

export function geojsonUrl(jobId: string): string {
  return `${API_BASE}/api/v1/jobs/${jobId}/result.geojson`;
}

/**
 * Subscribe to a job's live trace.
 *
 * Each message is a whole job snapshot rather than a delta, so a dropped
 * connection costs nothing but the gap — the next message restores full state.
 * Returns an unsubscribe function.
 */
export function subscribeToJob(
  jobId: string,
  handlers: {
    onSnapshot: (job: JobOut) => void;
    onDone?: () => void;
    onError?: (error: ErrorBody) => void;
  },
): () => void {
  const source = new EventSource(`${API_BASE}/api/v1/jobs/${jobId}/events`);

  source.addEventListener("snapshot", (event) => {
    try {
      const raw = JSON.parse((event as MessageEvent).data) as Record<
        string,
        unknown
      >;
      // The server normalises every frame to the job shape; this guard only
      // covers an older stream that still keyed the identifier as job_id.
      const normalised = {
        ...raw,
        id: (raw.id ?? raw.job_id) as string,
      } as unknown as JobOut;
      handlers.onSnapshot(normalised);
    } catch {
      /* A malformed frame must not tear down a live run. */
    }
  });

  source.addEventListener("done", () => {
    handlers.onDone?.();
    source.close();
  });

  source.addEventListener("error", () => {
    // EventSource retries on its own; only report once it has given up.
    if (source.readyState === EventSource.CLOSED) {
      handlers.onError?.({
        key: "events.stream_failed",
        params: {} as Record<string, never>,
      });
    }
  });

  return () => source.close();
}
