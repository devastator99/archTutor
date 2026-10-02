/**
 * The same-origin proxy, tested as a function.
 *
 * This is the piece that carries every browser request once the app is published
 * behind one address, so the things it must get right are narrow and exact: the
 * path it forwards to, the method and body it forwards, the status and error
 * body it returns, and the browser headers it must not replay to the API.
 *
 * The handlers are called directly with a `Request` rather than through a live
 * server, because what is under test is the shaping of one request, not Next's
 * routing of it. `tests/vertical-slice.test.mts` covers the app working over real
 * HTTP.
 */

import test from "node:test";
import assert from "node:assert/strict";

/** The handler under test, with the API base URL it reads. */
async function handlers() {
  return import("@/app/api/[...path]/route");
}

/** Record what the proxy sent upstream, and reply with `reply`. */
function captureUpstream(reply: (request: Request) => Response | Promise<Response>) {
  const original = globalThis.fetch;
  const seen: { url?: string; init?: RequestInit } = {};
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    seen.url = String(input);
    seen.init = init;
    return reply(new Request(String(input), init));
  }) as typeof fetch;
  return {
    seen,
    restore: () => {
      globalThis.fetch = original;
    },
  };
}

test("the proxy forwards to the API and returns its answer", async (t) => {
  const { GET, POST } = await handlers();

  await t.test("the /api prefix is stripped and the query string kept", async () => {
    const upstream = captureUpstream(
      () => new Response(JSON.stringify({ ok: true }), { status: 200 }),
    );
    try {
      const response = await GET(new Request("http://site.test/api/exercises?difficulty=beginner"));

      assert.equal(upstream.seen.url, "http://127.0.0.1:8000/exercises?difficulty=beginner");
      assert.equal(response.status, 200);
      assert.deepEqual(await response.json(), { ok: true });
    } finally {
      upstream.restore();
    }
  });

  await t.test("a nested path reaches the matching API route", async () => {
    const upstream = captureUpstream(() => new Response("{}", { status: 200 }));
    try {
      await GET(new Request("http://site.test/api/health"));

      assert.equal(upstream.seen.url, "http://127.0.0.1:8000/health");
    } finally {
      upstream.restore();
    }
  });

  await t.test("the method and body are passed through", async () => {
    const upstream = captureUpstream(() => new Response("{}", { status: 201 }));
    try {
      const response = await POST(
        new Request("http://site.test/api/exercises/x/attempts", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ geometry: { walls: [] } }),
        }),
      );

      assert.equal(upstream.seen.init?.method, "POST");
      assert.equal(upstream.seen.init?.body, JSON.stringify({ geometry: { walls: [] } }));
      assert.equal(response.status, 201);
    } finally {
      upstream.restore();
    }
  });

  await t.test("a GET carries no body, so the API never sees one", async () => {
    const upstream = captureUpstream(() => new Response("{}", { status: 200 }));
    try {
      await GET(new Request("http://site.test/api/exercises"));

      assert.equal(upstream.seen.init?.body, undefined);
    } finally {
      upstream.restore();
    }
  });

  await t.test("an error status and its body are passed through unchanged", async () => {
    /** The client's error formatting depends on this body surviving. */
    const detail = [
      { loc: ["body", "geometry", "walls", 0], msg: "field required" },
    ];
    const upstream = captureUpstream(
      () =>
        new Response(JSON.stringify({ detail }), {
          status: 422,
          headers: { "content-type": "application/json" },
        }),
    );
    try {
      const response = await POST(
        new Request("http://site.test/api/exercises/x/validate", { method: "POST" }),
      );

      assert.equal(response.status, 422);
      assert.deepEqual(await response.json(), { detail });
    } finally {
      upstream.restore();
    }
  });

  await t.test("the request id survives, so a student can quote it", async () => {
    const upstream = captureUpstream(
      () =>
        new Response(JSON.stringify({ detail: "boom" }), {
          status: 500,
          headers: { "content-type": "application/json", "x-request-id": "req-42" },
        }),
    );
    try {
      const response = await GET(new Request("http://site.test/api/exercises"));

      assert.equal(response.headers.get("x-request-id"), "req-42");
    } finally {
      upstream.restore();
    }
  });

  await t.test("the browser's own headers are not replayed to the API", async () => {
    /** Replaying cookies or an Origin would make the API believe a call came
     *  from this page, which is a forged provenance the app never intended. */
    const upstream = captureUpstream(() => new Response("{}", { status: 200 }));
    try {
      await GET(
        new Request("http://site.test/api/exercises", {
          headers: {
            cookie: "session=secret",
            origin: "http://site.test",
            referer: "http://site.test/drawing",
            "x-requested-with": "kept",
          },
        }),
      );

      const sent = new Headers(upstream.seen.init?.headers);
      assert.equal(sent.get("cookie"), null);
      assert.equal(sent.get("origin"), null);
      assert.equal(sent.get("referer"), null);
      assert.equal(sent.get("x-requested-with"), "kept", "unrelated headers still pass");
    } finally {
      upstream.restore();
    }
  });

  await t.test("an unreachable API becomes a readable 502, not a hung request", async () => {
    const original = globalThis.fetch;
    globalThis.fetch = (() => Promise.reject(new TypeError("fetch failed"))) as typeof fetch;
    try {
      const response = await GET(new Request("http://site.test/api/exercises"));
      const body = (await response.json()) as { detail: string };

      assert.equal(response.status, 502);
      // In the API's own error shape, which is what the client knows how to read.
      assert.match(body.detail, /could not be reached/);
      assert.match(body.detail, /fetch failed/);
    } finally {
      globalThis.fetch = original;
    }
  });

  await t.test("the target host comes from configuration, never from the request", async () => {
    /** The reason this is not an open forwarder.

    The path is deliberately not rewritten or filtered: the API is the authority
    on which routes exist, and a proxy that second-guessed it would be a second
    place for routing to live. What must never vary is *where* the request goes,
    so that is what this asserts -- including for a request that tries to name a
    different destination itself.
    */
    const upstream = captureUpstream(() => new Response("{}", { status: 200 }));
    try {
      await GET(new Request("http://site.test/api/http://evil.test/steal"));
      assert.equal(new URL(String(upstream.seen.url)).host, "127.0.0.1:8000");
      assert.equal(new URL(String(upstream.seen.url)).pathname, "/http://evil.test/steal");

      await GET(new Request("http://site.test/api/../../admin"));
      assert.equal(new URL(String(upstream.seen.url)).host, "127.0.0.1:8000");
      assert.equal(new URL(String(upstream.seen.url)).protocol, "http:");
    } finally {
      upstream.restore();
    }
  });
});
