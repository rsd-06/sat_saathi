import { apiUrl, readToken } from "@/lib/session";

/**
 * The browser's only way to the API. The session token lives in an httpOnly
 * cookie on this origin, so every call — uploads, the event stream, downloads
 * — comes through here and leaves with it attached as a bearer header.
 */
async function forward(
  request: Request,
  { params }: { params: Promise<{ path: string[] }> },
) {
  const { path } = await params;
  const token = await readToken();
  const headers = new Headers(request.headers);
  headers.delete("host");
  headers.delete("cookie");
  if (token) headers.set("authorization", `Bearer ${token}`);

  const hasBody = request.method !== "GET" && request.method !== "HEAD";
  const upstream = await fetch(
    apiUrl(`/${path.join("/")}${new URL(request.url).search}`),
    {
      method: request.method,
      headers,
      body: hasBody ? request.body : undefined,
      // Required by Node's fetch to stream a request body (uploads).
      ...(hasBody ? { duplex: "half" } : {}),
      cache: "no-store",
    } as RequestInit,
  );

  const out = new Headers(upstream.headers);
  out.delete("content-encoding");
  out.delete("content-length");
  return new Response(upstream.body, { status: upstream.status, headers: out });
}

export const dynamic = "force-dynamic";
export {
  forward as GET,
  forward as POST,
  forward as PUT,
  forward as PATCH,
  forward as DELETE,
};
