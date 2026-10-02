/**
 * The client's own contract with the API and the network.
 *
 * The base URL rule is here because it is invisible until it is wrong: a server
 * component calling the browser's hostname still renders a page, so the failure
 * appears in a deployment rather than in a test. Asserting it costs nothing.
 */

import test from "node:test";
import assert from "node:assert/strict";

import { ApiError, resolveApiBaseUrls } from "@/lib/api";

test("the base URL rule", async (t) => {
  await t.test("with nothing configured, both sides use the local default", () => {
    const urls = resolveApiBaseUrls(undefined, undefined);

    assert.equal(urls.browser, "http://127.0.0.1:8000");
    assert.equal(urls.server, "http://127.0.0.1:8000");
  });

  await t.test("one public URL serves both, which is the local setup", () => {
    const urls = resolveApiBaseUrls("http://api.test:8000", undefined);

    assert.equal(urls.browser, "http://api.test:8000");
    assert.equal(urls.server, "http://api.test:8000");
  });

  await t.test("a server-only URL is used by the server alone", () => {
    const urls = resolveApiBaseUrls(undefined, "http://api.internal:8000");

    // The browser has never heard of an internal hostname, and shipping one in
    // the bundle would be a leak rather than a convenience.
    assert.equal(urls.browser, "http://127.0.0.1:8000");
    assert.equal(urls.server, "http://api.internal:8000");
  });

  await t.test("when both are set, each side gets its own", () => {
    const urls = resolveApiBaseUrls("https://archtutor.example", "http://api.internal:8000");

    assert.equal(urls.browser, "https://archtutor.example");
    assert.equal(urls.server, "http://api.internal:8000");
  });

  await t.test("a trailing slash is removed, since paths carry their own", () => {
    const urls = resolveApiBaseUrls("https://archtutor.example/", "http://api.internal:8000///");

    assert.equal(urls.browser, "https://archtutor.example");
    assert.equal(urls.server, "http://api.internal:8000");
  });

  await t.test("a blank value is treated as unset rather than as a URL", () => {
    const urls = resolveApiBaseUrls("   ", "  ");

    assert.equal(urls.browser, "http://127.0.0.1:8000");
    assert.equal(urls.server, "http://127.0.0.1:8000");
  });

  await t.test("a relative public URL sends the browser to this site's own proxy", () => {
    /** What makes the app publishable behind a single address. */
    const urls = resolveApiBaseUrls("/api", "http://127.0.0.1:8000");

    assert.equal(urls.browser, "/api", "so a request becomes /api/exercises");
    assert.equal(urls.server, "http://127.0.0.1:8000");
  });

  await t.test("a relative public URL never becomes the server URL", () => {
    /** A server-side fetch of a relative path has nothing to resolve it against,
     *  so this has to fail safe rather than at the first server render. */
    const urls = resolveApiBaseUrls("/api", undefined);

    assert.equal(urls.server, "http://127.0.0.1:8000");
  });

  await t.test("a relative server URL is ignored rather than used", () => {
    const urls = resolveApiBaseUrls("http://127.0.0.1:8000", "/api");

    assert.equal(urls.server, "http://127.0.0.1:8000");
  });

  await t.test("a relative public URL still lets the server name the API", () => {
    const urls = resolveApiBaseUrls("/api", "http://api.internal:8000");

    assert.equal(urls.browser, "/api");
    assert.equal(urls.server, "http://api.internal:8000");
  });
});

test("an unreachable API is reported as one, not as a crash", async () => {
  const original = globalThis.fetch;
  globalThis.fetch = (() => Promise.reject(new TypeError("fetch failed"))) as typeof fetch;
  try {
    const { api } = await import("@/lib/api");
    await assert.rejects(() => api.health(), (error: unknown) => {
      assert.ok(error instanceof ApiError);
      // A student sees this sentence, so it has to name the thing to check.
      assert.match(error.message, /Cannot reach the ArchTutor API/);
      assert.equal(error.status, 0);
      return true;
    });
  } finally {
    globalThis.fetch = original;
  }
});

test("a failed request carries the server's reason and its request id", async () => {
  const original = globalThis.fetch;
  globalThis.fetch = (async () =>
    new Response(
      JSON.stringify({ detail: "attempt not found", request_id: "req-123" }),
      { status: 404, headers: { "x-request-id": "req-123" } },
    )) as typeof fetch;
  try {
    const { api } = await import("@/lib/api");
    await assert.rejects(
      () => api.getExercise("00000000-0000-0000-0000-000000000000"),
      (error: unknown) => {
        assert.ok(error instanceof ApiError);
        assert.equal(error.status, 404);
        assert.equal(error.message, "attempt not found");
        assert.equal(error.requestId, "req-123");
        return true;
      },
    );
  } finally {
    globalThis.fetch = original;
  }
});

test("a schema violation lists the fields that failed", async () => {
  const original = globalThis.fetch;
  globalThis.fetch = (async () =>
    new Response(
      JSON.stringify({
        detail: [
          { loc: ["body", "geometry", "walls", 0], msg: "field required" },
          { loc: ["body", "scale_denominator"], msg: "not a plausible scale" },
        ],
      }),
      { status: 422 },
    )) as typeof fetch;
  try {
    const { api } = await import("@/lib/api");
    await assert.rejects(
      () => api.validate("00000000-0000-0000-0000-000000000000", {} as never),
      (error: unknown) => {
        assert.ok(error instanceof ApiError);
        // "[object Object]" is what this would be without the formatting, and a
        // student cannot act on it.
        assert.equal(
          error.message,
          "body.geometry.walls.0: field required; body.scale_denominator: not a plausible scale",
        );
        return true;
      },
    );
  } finally {
    globalThis.fetch = original;
  }
});
