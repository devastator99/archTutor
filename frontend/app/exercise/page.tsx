import type { Metadata } from "next";
import Link from "next/link";
import { api, type Exercise } from "@/lib/api";

export const metadata: Metadata = { title: "Exercise" };

/** Read fresh on every request: the exercise set changes as content is authored. */
export const dynamic = "force-dynamic";

async function loadExercises(): Promise<Exercise[]> {
  try {
    return (await api.listExercises()).items;
  } catch {
    // A backend that is down should not 500 the page. The list is navigation,
    // and the empty state below tells the student what to do about it.
    return [];
  }
}

export default async function ExercisePage() {
  const exercises = await loadExercises();

  return (
    <div className="mx-auto max-w-5xl px-6 py-10">
      <h1 className="text-xl font-semibold tracking-tight">Exercise</h1>
      <p className="mt-1 text-sm text-neutral-600">
        Pick a brief, draw it to scale, and get measured.
      </p>

      {exercises.length === 0 ? (
        <p className="mt-6 rounded border border-dashed border-neutral-300 bg-white p-6 text-sm text-neutral-600">
          No exercises yet. Seed the development database with{" "}
          <code className="font-mono">python -m scripts.seed_dev_exercises</code>{" "}
          in <code className="font-mono">backend/</code>.
        </p>
      ) : (
        <ul className="mt-6 space-y-3">
          {exercises.map((exercise) => (
            <li
              key={exercise.id}
              className="rounded border border-neutral-200 bg-white p-4"
            >
              <div className="flex flex-wrap items-baseline justify-between gap-3">
                <span className="font-medium">{exercise.title}</span>
                <span className="font-mono text-xs text-neutral-500">
                  {exercise.difficulty}
                </span>
              </div>

              {exercise.description && (
                <p className="mt-1 text-sm text-neutral-600">
                  {exercise.description}
                </p>
              )}

              <dl className="mt-3 grid gap-x-6 gap-y-1 font-mono text-xs text-neutral-600 sm:grid-cols-3">
                <div className="flex gap-2">
                  <dt className="text-neutral-400">room</dt>
                  <dd>
                    {exercise.room_width_mm} × {exercise.room_height_mm} mm
                  </dd>
                </div>
                <div className="flex gap-2">
                  <dt className="text-neutral-400">scale</dt>
                  <dd>1:{exercise.scale_denominator}</dd>
                </div>
                <div className="flex gap-2">
                  <dt className="text-neutral-400">walls</dt>
                  <dd>{exercise.wall_thickness_mm} mm</dd>
                </div>
              </dl>

              <Link
                href={`/drawing?exercise=${exercise.id}`}
                className="mt-4 inline-block rounded bg-neutral-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-neutral-700"
              >
                Draw it
              </Link>
            </li>
          ))}
        </ul>
      )}

      <p className="mt-8 max-w-2xl text-xs text-neutral-500">
        Dimensions above are real-world millimetres. The expected size of the
        drawing is calculated by the backend, never in the browser.
      </p>
    </div>
  );
}
