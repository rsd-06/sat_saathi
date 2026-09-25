import { SESSION_COOKIE, apiUrl } from "@/lib/session";

/**
 * The browser's only way to the API.
 *
 * The session token lives in an httpOnly cookie on this origin, which the API
 * on another origin never sees. Every call from the page therefore comes
 * here, and leaves with the token attached as a bearer credential — so the
 * API knows whose work is whose without the page ever holding the token.
 *
 * Bodies stream both ways: uploads go up without being buffered here, and the
 * live trace (server-sent events) comes back as it is written.
 */
async function forward(request: Request, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params;
  const url = new URL(request.url);
  const target = apiUrl(`/api/v1/${path.map(encodeURIComponent).join("/")}${url.search}`);

  const headers = new Headers();
  for (const name of ["content-type", "accept", "last-event-id"]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  const token = request.headers
    .get("cookie")
    ?.split(";")
    .map((part) => part.trim())
    .find((part) => part.startsWith(`${SESSION_COOKIE}=`))
    ?.slice(SESSION_COOKIE.length + 1);
  if (token) headers.set("authorization", `Bearer ${token}`);

  const hasBody = !["GET", "HEAD"].includes(request.method);
  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method: request.method,
      headers,
      body: hasBody ? request.body : undefined,
      // Required by Node's fetch to stream a request body.
      ...(hasBody ? { duplex: "half" } : {}),
      cache: "no-store",
      redirect: "manual",
    } as RequestInit);
  } catch {
    return Response.json(
      { error: { key: "error.apiUnreachable.title", params: {} } },
      { status: 503 },
    );
  }

  const out = new Headers();
  for (const name of ["content-type", "content-disposition", "cache-control"]) {
    const value = upstream.headers.get(name);
    if (value) out.set(name, value);
  }
  // Nginx and friends buffer event streams unless told otherwise.
  if (out.get("content-type")?.startsWith("text/event-stream")) out.set("x-accel-buffering", "no");
  return new Response(upstream.body, { status: upstream.status, headers: out });
}

export const GET = forward;
export const POST = forward;
export const PATCH = forward;
export const PUT = forward;
export const DELETE = forward;
export const dynamic = "force-dynamic";
