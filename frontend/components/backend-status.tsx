"use client";

import { useEffect, useState } from "react";
import { api, ApiError, API_BASE_URL, type Health } from "@/lib/api";

type State =
  | { status: "loading" }
  | { status: "ready"; health: Health }
  | { status: "error"; message: string };

/**
 * Calls the backend's GET /health from the browser.
 *
 * This is the connectivity check: it exercises CORS, so it proves the
 * frontend can actually reach the API rather than merely that the API works.
 */
export function BackendStatus() {
  const [state, setState] = useState<State>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;

    api
      .health()
      .then((health) => {
        if (!cancelled) setState({ status: "ready", health });
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        setState({
          status: "error",
          message:
            error instanceof ApiError
              ? error.message
              : "Unexpected error contacting the API.",
        });
      });

    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="rounded border border-neutral-200 bg-white p-4 text-sm">
      <p className="font-medium">Backend connection</p>
      <p className="mt-1 font-mono text-xs text-neutral-500">{API_BASE_URL}</p>

      {state.status === "loading" && (
        <p className="mt-2 text-neutral-500">Checking /health…</p>
      )}

      {state.status === "ready" && (
        <dl className="mt-2 grid grid-cols-3 gap-2 font-mono text-xs">
          <div>
            <dt className="text-neutral-500">api</dt>
            <dd className="text-emerald-700">{state.health.status}</dd>
          </div>
          <div>
            <dt className="text-neutral-500">database</dt>
            <dd className="text-emerald-700">{state.health.database}</dd>
          </div>
          <div>
            <dt className="text-neutral-500">version</dt>
            <dd>{state.health.version}</dd>
          </div>
        </dl>
      )}

      {state.status === "error" && (
        <p className="mt-2 text-red-700">{state.message}</p>
      )}
    </div>
  );
}
