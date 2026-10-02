import type { Metadata } from "next";
import Link from "next/link";

import { DrawingWorkspace } from "@/components/drawing-workspace";
import { api, type Exercise } from "@/lib/api";

export const metadata: Metadata = { title: "Drawing" };

/** The exercise set is authored and seeded out of band; read it per request. */
export const dynamic = "force-dynamic";

/**
 * The drawing workspace.
 *
 * One route rather than a route per exercise: the exercise is chosen with a
 * query parameter, so `/drawing?exercise=<id>` is shareable and the page stays
 * a single thing to keep correct. A student with the brief open in one tab and
 * the workspace in another is a normal way to work.
 */
async function loadExercises(): Promise<Exercise[]> {
  try {
    return (await api.listExercises()).items;
  } catch {
    return [];
  }
}

function optionFor(exercise: Exercise): string {
  return `${exercise.title} · ${exercise.room_width_mm} × ${exercise.room_height_mm} mm · 1:${exercise.scale_denominator}`;
}

export default async function DrawingPage({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  const requested = (await searchParams).exercise;
  const wanted = typeof requested === "string" ? requested : undefined;
  const exercises = await loadExercises();
  const exercise =
    exercises.find((candidate) => candidate.id === wanted) ?? exercises[0] ?? null;

  return (
    <div className="mx-auto max-w-7xl px-6 py-8">
      <Link href="/exercise" className="text-sm text-neutral-500 hover:underline">
        ← Exercise
      </Link>

      <div className="mt-3 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-lg font-semibold tracking-tight">
            {exercise ? exercise.title : "Drawing"}
          </h1>
          {exercise && (
            <p className="mt-1 font-mono text-xs text-neutral-500">
              {exercise.room_width_mm} × {exercise.room_height_mm} mm · 1:
              {exercise.scale_denominator} · {exercise.wall_thickness_mm} mm walls
            </p>
          )}
        </div>

        {exercises.length > 1 && (
          <nav className="flex flex-wrap gap-1" aria-label="Choose an exercise">
            {exercises.map((candidate) => {
              const active = candidate.id === exercise?.id;
              return (
                <Link
                  key={candidate.id}
                  href={`/drawing?exercise=${candidate.id}`}
                  aria-current={active ? "page" : undefined}
                  className={`rounded px-2 py-1 text-xs ${
                    active
                      ? "bg-neutral-900 text-white"
                      : "bg-white text-neutral-600 ring-1 ring-neutral-200 hover:bg-neutral-100"
                  }`}
                  title={optionFor(candidate)}
                >
                  {candidate.title}
                </Link>
              );
            })}
          </nav>
        )}
      </div>

      {exercise ? (
        <DrawingWorkspace exercise={exercise} />
      ) : (
        <p className="mt-6 rounded border border-dashed border-neutral-300 bg-white p-6 text-sm text-neutral-600">
          No exercise loaded. Seed the database to see a brief here:
          <code className="mx-1 font-mono text-xs">
            python -m scripts.seed_dev_exercises
          </code>
          in <code className="font-mono text-xs">backend/</code>.
        </p>
      )}
    </div>
  );
}
