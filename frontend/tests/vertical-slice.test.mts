/**
 * The whole vertical slice, against a real running backend.
 *
 * This is the test that matters most, because it is the one that walks the path
 * a student walks: brief, a wrong drawing, an explanation, a correction, a
 * completion. It runs over HTTP against a real API and a real database, so
 * anything that only works in-process -- a response shape that the router
 * actually drops, a field the ORM never persists, a summary that reads the wrong
 * table -- fails here rather than in front of a student.
 *
 * It needs a seeded database and a running API:
 *
 *     cd backend && .venv/bin/uvicorn app.main:app --port 8000
 *     cd frontend && npm test
 *
 * If the API is not running, the test reports that and skips. Skipping is
 * deliberate: a unit suite that fails because someone is not running a server is
 * worse than a suite that tells the truth about what it could not check.
 *
 * Set `ARCHTUTOR_API_URL` to point somewhere other than the default.
 */

import test from "node:test";
import assert from "node:assert/strict";

const baseUrl = process.env.ARCHTUTOR_API_URL ?? process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

let reachable = false;
try {
  const response = await fetch(`${baseUrl}/health`);
  reachable = response.ok;
} catch {
  reachable = false;
}

const options = { skip: reachable ? false : `no API at ${baseUrl}` };

/** Every issue a student is shown must carry all seven teaching facts. */
const SEVEN_FIELDS = [
  "what_is_wrong",
  "where",
  "expected",
  "actual",
  "difference",
  "unit",
  "why_it_matters",
  "how_to_fix",
] as const;

test("a student can go from a brief to a completion", options, async (t) => {
  const { api } = await import("@/lib/api");
  const { drawingFromEditor, newEditorIds, prefilledEditor } = await import(
    "@/lib/editor"
  );

  const { items } = await api.listExercises();
  assert.ok(items.length > 0, "the database has no exercises seeded");
  const exercise = items[0];
  assert.equal(exercise.scale_denominator > 0, true);

  const before = await api.listAttempts(exercise.id);

  await t.test("a check reports the drawing without storing it", async () => {
    const wrong = drawingFromEditor(
      {
        ...prefilledEditor(exercise),
        // A deliberately wrong room: the right shape at the wrong size.
        roomWidthMm: String(Number(prefilledEditor(exercise).roomWidthMm) * 0.8),
        wallThicknessMm: "1",
      },
      newEditorIds(),
    );
    const result = await api.validate(exercise.id, wrong);
    const after = await api.listAttempts(exercise.id);

    assert.equal(result.passed, false);
    assert.ok(result.findings.length > 0);
    assert.equal(result.scale_denominator, exercise.scale_denominator);
    assert.equal(after.length, before.length, "a dry run must not store an attempt");
    assert.equal(
      result.summary.error_count + result.summary.warning_count,
      result.findings.length,
    );
  });

  let firstAttemptId = "";
  let firstAttemptErrorCount = 0;
  await t.test("a first attempt is stored, explained and not completed", async () => {
    const wrong = drawingFromEditor(
      {
        ...prefilledEditor(exercise),
        roomWidthMm: String(Number(prefilledEditor(exercise).roomWidthMm) * 0.8),
        wallThicknessMm: "1",
      },
      newEditorIds(),
    );
    const attempt = await api.submitAttempt(exercise.id, wrong);

    assert.equal(attempt.validation_result.passed, false);
    assert.equal(attempt.completed, false);
    assert.equal(attempt.completed_at, null);
    // Relative to whatever was already there. The suite is meant to be re-runnable
    // against a database that has history, and "first attempt" is a claim about
    // the attempt's position, not about the database being empty.
    assert.equal(attempt.progress.is_first_attempt, before.length === 0);
    assert.equal(attempt.attempt_number, before.length + 1);
    assert.equal(attempt.progress.remaining_count, attempt.validation_result.findings.length);
    assert.equal(attempt.previous_attempt_id, before[0]?.id ?? null);
    assert.equal(attempt.learning.category_count > 0, true);

    for (const issue of attempt.progress.remaining) {
      for (const field of SEVEN_FIELDS) {
        const value = issue[field];
        const present = Array.isArray(value) ? value.length > 0 : value !== null && value !== "";
        assert.equal(present, true, `${issue.code} is missing ${field}`);
      }
      assert.ok(issue.how_to_fix.length > 0, `${issue.code} has no fix steps`);
    }

    firstAttemptId = attempt.id;
    firstAttemptErrorCount = attempt.validation_result.summary.error_count;
  });

  await t.test("the tutor explains a stored issue by its index", async () => {
    const attempts = await api.listAttempts(exercise.id);
    const attempt = attempts.find((candidate) => candidate.id === firstAttemptId);
    assert.ok(attempt, "the first attempt is in the history");

    const response = await api.explain(exercise.id, attempt!.id, 0);
    assert.equal(response.issue_index, 0);
    assert.ok(response.tutor.explanation.length > 0);
    assert.ok(["deterministic", "llm"].includes(response.tutor.source));

    const first = attempt!.validation_result.findings[0];
    assert.equal(response.issue.code, first.code);
    assert.equal(response.issue.geometry_reference, first.geometry_reference);
  });

  await t.test("an out-of-range issue index is refused, not answered with another issue", async () => {
    const attempts = await api.listAttempts(exercise.id);
    const attempt = attempts.find((candidate) => candidate.id === firstAttemptId);
    assert.ok(attempt);

    await assert.rejects(
      () => api.explain(exercise.id, attempt!.id, 9999),
      (error: { status: number }) => error.status === 422,
    );
  });

  await t.test("fixing mistakes credits exactly what was fixed", async () => {
    const second = await api.submitAttempt(
      exercise.id,
      drawingFromEditor(prefilledEditor(exercise), newEditorIds()),
    );

    assert.equal(second.validation_result.passed, true, JSON.stringify(second.validation_result.findings));
    assert.equal(second.completed, true);
    assert.ok(second.completed_at);
    assert.equal(second.progress.is_first_attempt, false);
    assert.equal(second.previous_attempt_id, firstAttemptId);
    // Every mistake from the first attempt is credited as fixed, and fixing them
    // introduced none: a count that did not add up here would mean the progress
    // diff was flattering the student.
    assert.equal(second.progress.resolved_count, firstAttemptErrorCount);
    assert.equal(second.progress.remaining_count, 0);
    assert.equal(second.progress.new_count, 0);
    assert.equal(second.progress.changed_count, 0);
    assert.equal(second.progress.improved, true);
    assert.equal(second.attempt_number, before.length + 2);
  });

  await t.test("the summary reports what the student demonstrated", async () => {
    const summary = await api.summary(exercise.id);

    assert.equal(summary.completed, true);
    assert.equal(summary.final_error_count, 0);
    // Two attempts were submitted during this test, and nothing else.
    assert.equal(summary.attempt_count, before.length + 2);
    // The first attempt that ever passed, not the most recent one: a student who
    // finished on attempt 2 and then drew it wrong again has still finished.
    assert.ok(summary.completion_attempt_number !== null);
    assert.ok(summary.completion_attempt_number <= summary.attempt_count);
    assert.ok(summary.concepts.length > 0);
    assert.ok(summary.concepts.some((concept) => concept.includes(`1:${exercise.scale_denominator}`)));
    assert.ok(summary.concepts.some((concept) => concept.includes(`${exercise.wall_thickness_mm} mm walls`)));
    for (const concept of summary.concepts) {
      assert.ok(concept.trim().length > 0);
    }
  });

  await t.test("a check teaches what submitting would", async () => {
    const wrong = drawingFromEditor(
      {
        ...prefilledEditor(exercise),
        roomWidthMm: String(Number(prefilledEditor(exercise).roomWidthMm) * 0.8),
        wallThicknessMm: "1",
      },
      newEditorIds(),
    );
    const dryRun = await api.validate(exercise.id, wrong);
    const stored = await api.submitAttempt(exercise.id, wrong);

    assert.equal(dryRun.issues.length, dryRun.findings.length);
    for (const issue of dryRun.issues) {
      for (const field of SEVEN_FIELDS) {
        const value = issue[field];
        const present = Array.isArray(value) ? value.length > 0 : value !== null && value !== "";
        assert.equal(present, true, `${issue.code} is missing ${field} on a dry run`);
      }
    }

    // The same drawing, explained once. A student who checks and then submits
    // must not be told two different things about the same mistake.
    const compared = [
      "code",
      "category",
      "category_label",
      "severity",
      "what_is_wrong",
      "where",
      "expected",
      "actual",
      "difference",
      "unit",
      "why_it_matters",
      "how_to_fix",
      "geometry_reference",
    ] as const satisfies readonly (keyof import("@/lib/api").Issue)[];
    assert.deepEqual(
      dryRun.issues.map((issue) => compared.map((key) => issue[key])),
      stored.progress.remaining.map((issue) => compared.map((key) => issue[key])),
    );
  });
});
