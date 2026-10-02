"use client";

import dynamic from "next/dynamic";

import type { StudentDrawing } from "@/lib/api";

/**
 * Client-only wrapper around the Konva stage.
 *
 * Konva touches the DOM at import time, so it cannot be server-rendered.
 * `ssr: false` is only permitted inside a Client Component, which is why this
 * indirection exists rather than a `dynamic(..., { ssr: false })` call in the
 * page.
 */
const KonvaStage = dynamic(
  () => import("./konva-stage").then((module) => module.KonvaStage),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-[520px] items-center justify-center rounded border border-neutral-200 bg-white text-sm text-neutral-500">
        Loading drawing surface…
      </div>
    ),
  },
);

export interface DrawingSurfaceProps {
  drawing: StudentDrawing;
  highlight?: string | null;
  softHighlight?: string | null;
}

export function DrawingSurface(props: DrawingSurfaceProps) {
  return <KonvaStage {...props} />;
}
