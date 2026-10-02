/**
 * A same-origin proxy to the ArchTutor API.
 *
 * WHY THIS EXISTS
 * ---------------
 * The browser and the server reach the API differently. A server component
 * fetches from the server, where the API is an internal address. A client
 * component fetches from the browser, which can only reach what the browser can
 * see. That is why there are two base URLs in `lib/api.ts` and not one.
 *
 * With an absolute browser URL, publishing the app means publishing the API as a
 * second public address, in a second origin, with its own CORS configuration --
 * and a tunnel's hostname changes when it restarts, so the allowed origin has to
 * change with it. Forwarding through here removes all of that: the browser
 * calls the same origin it loaded the page from, Next forwards to the API
 * server-side, and exactly one address is ever public.
 *
 * WHAT IT DELIBERATELY IS NOT
 * ---------------------------
 * Not a gateway. The target is the configured API base URL, not anything in the
 * request, so this cannot be pointed at another host; there is no rewriting of
 * paths, no query filtering and no header injection. It forwards a request and
 * returns the answer, and nothing else is its business.
 */

import { serverApiBaseUrl } from "@/lib/api";

export const dynamic = "force-dynamic";

/** Headers that describe the browser's hop, not the request's meaning. */
const HOP_BY_HOP = new Set([
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
  // The browser's own origin and cookies must not be replayed to the API: it
  // would make the API believe a call came from this app's page.
  "cookie",
  "host",
  "origin",
  "referer",
  "content-length",
  "accept-encoding",
]);

/** Response headers worth passing back. */
const PASS_THROUGH_RESPONSE = new Set(["content-type", "x-request-id", "retry-after"]);

const METHODS_WITHOUT_BODY = new Set(["GET", "HEAD"]);

async function proxy(request: Request): Promise<Response> {
  // `/api/exercises?x=1` -> `/exercises?x=1` on the API.
  const incoming = new URL(request.url);
  const path = incoming.pathname.replace(/^\/api/, "") || "/";
  const target = `${serverApiBaseUrl}${path}${incoming.search}`;

  const headers = new Headers();
  for (const [name, value] of request.headers) {
    if (!HOP_BY_HOP.has(name.toLowerCase())) {
      headers.set(name, value);
    }
  }

  let response: Response;
  try {
    response = await fetch(target, {
      method: request.method,
      headers,
      body: METHODS_WITHOUT_BODY.has(request.method) ? undefined : await request.text(),
      cache: "no-store",
      redirect: "manual",
    });
  } catch (caught) {
    // Answered in the API's own error shape, so the client's error handling --
    // which reads `detail` -- produces the sentence a student sees, rather than
    // an opaque failed fetch.
    return Response.json(
      {
        detail:
          `The ArchTutor API at ${serverApiBaseUrl} could not be reached. ` +
          `Is the backend running? (${caught instanceof Error ? caught.message : String(caught)})`,
      },
      { status: 502 },
    );
  }

  const outHeaders = new Headers();
  for (const [name, value] of response.headers) {
    if (PASS_THROUGH_RESPONSE.has(name.toLowerCase())) {
      outHeaders.set(name, value);
    }
  }
  return new Response(await response.text(), {
    status: response.status,
    headers: outHeaders,
  });
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
export const HEAD = proxy;
export const OPTIONS = proxy;
