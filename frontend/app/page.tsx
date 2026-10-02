import Link from "next/link";
import { BackendStatus } from "@/components/backend-status";

const LOOP = [
  "Exercise",
  "Student draws",
  "System measures",
  "System validates",
  "System identifies mistake",
  "Tutor explains",
  "Student corrects",
  "Retry",
] as const;

export default function Page() {
  return (
    <div className="mx-auto max-w-6xl px-6 py-10">
      <h1 className="text-2xl font-semibold tracking-tight">ArchTutor</h1>
      <p className="mt-2 max-w-2xl text-neutral-600">
        Drafting practice and feedback for B.Arch students. Draw a room, and find
        out exactly why your drawing is wrong &mdash; measured, not guessed.
      </p>

      <section className="mt-8">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-neutral-500">
          The core loop
        </h2>
        <ol className="mt-3 flex flex-wrap gap-2">
          {LOOP.map((step, index) => (
            <li
              key={step}
              className="flex items-center gap-2 rounded border border-neutral-200 bg-white px-3 py-1.5 text-sm"
            >
              <span className="font-mono text-xs text-neutral-400">
                {String(index + 1).padStart(2, "0")}
              </span>
              {step}
            </li>
          ))}
        </ol>
      </section>

      <section className="mt-8 max-w-md">
        <BackendStatus />
      </section>

      <section className="mt-8">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-neutral-500">
          Get started
        </h2>
        <p className="mt-2 text-neutral-600">
          <Link
            href="/exercise"
            className="font-medium text-neutral-900 underline underline-offset-4"
          >
            Browse exercises
          </Link>
        </p>
      </section>
    </div>
  );
}
