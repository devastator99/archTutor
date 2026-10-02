"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { DrawingSurface } from "@/components/drawing/drawing-surface";
import { IssueCard, factsFromFinding, factsFromIssue } from "@/components/issue-card";
import {
  ApiError,
  api,
  type Attempt,
  type EngineResult,
  type Exercise,
  type ExerciseSummary,
  type Finding,
  type Issue,
  type StudentDrawing,
  type TutorExplanation,
  type WallSide,
} from "@/lib/api";
import { briefLines, newId, toPaperMm } from "@/lib/drawing";
import {
  SCALE_CHOICES,
  SIDES,
  drawingFromEditor,
  emptyEditor,
  formatMm,
  missingFields,
  newEditorIds,
  prefilledEditor,
  type EditorState,
} from "@/lib/editor";

/**
 * The vertical slice, in one component: brief, drawing, check, explanation,
 * correction, re-check, completion.
 *
 * The state machine is deliberately small. `dryRun` is what a check found and is
 * thrown away; `attempt` is what was stored and is what the student is judged
 * against. They are separate variables on purpose, because conflating them is
 * how a UI ends up showing a verdict for a drawing that was never submitted.
 *
 * Every number shown as a verdict comes from the server. The inputs are the only
 * place the student types, and `lib/editor.ts` is the only place those inputs
 * become geometry.
 */

/** Which result the student is currently looking at. */
type Mode = "check" | "attempt";

export interface DrawingWorkspaceProps {
  exercise: Exercise;
}

export function DrawingWorkspace({ exercise }: DrawingWorkspaceProps) {
  const [editor, setEditor] = useState<EditorState>(() => emptyEditor(exercise));
  const [ids] = useState(() => newEditorIds());
  const [dryRun, setDryRun] = useState<EngineResult | null>(null);
  const [attempt, setAttempt] = useState<Attempt | null>(null);
  const [summary, setSummary] = useState<ExerciseSummary | null>(null);
  const [mode, setMode] = useState<Mode>("check");
  const [selected, setSelected] = useState<number | null>(null);
  const [explanations, setExplanations] = useState<Record<number, TutorExplanation>>({});
  const [busy, setBusy] = useState<"check" | "submit" | "explain" | "summary" | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Which attempt is on screen right now, readable from an async continuation
  // without re-running an effect. Explaining is the one action that can be
  // overtaken by a submission, so it is the one that needs to check.
  const latestAttempt = useRef<string | null>(null);
  useEffect(() => {
    // Synced after commit, not assigned during render: render runs speculatively
    // and can be thrown away, so a ref written there can describe a render that
    // never happened.
    latestAttempt.current = attempt?.id ?? null;
  }, [attempt]);

  const drawing: StudentDrawing = useMemo(
    () => drawingFromEditor(editor, ids),
    [editor, ids],
  );

  const incomplete = missingFields(editor);
  // A room with no height has coincident corners, which the engine cannot
  // measure. The app knows that before the click, so the buttons say so instead
  // of spending a round trip to be told the drawing is malformed.
  const ungradable = incomplete.length > 0;
  const ungradableReason = `Fill in ${incomplete.join(", ")} first`;
  const drawingsDiffer = useMemo(
    () => JSON.stringify(drawing) !== JSON.stringify(attempt?.student_geometry ?? null),
    [drawing, attempt],
  );

  function update(patch: Partial<EditorState>) {
    setEditor((current) => ({ ...current, ...patch }));
  }

  function updateOpening(id: string, patch: Partial<EditorState["openings"][number]>) {
    setEditor((current) => ({
      ...current,
      openings: current.openings.map((opening) =>
        opening.id === id ? { ...opening, ...patch } : opening,
      ),
    }));
  }

  function addOpening() {
    setEditor((current) => ({
      ...current,
      openings: [
        ...current.openings,
        {
          id: newId(),
          kind: "window",
          wall: "east" as WallSide,
          widthMm: "",
          offsetMm: "",
        },
      ],
    }));
  }

  function removeOpening(id: string) {
    setEditor((current) => ({
      ...current,
      openings: current.openings.filter((opening) => opening.id !== id),
    }));
  }

  function reportFailure(caught: unknown) {
    if (caught instanceof ApiError) {
      setError(
        caught.requestId
          ? `${caught.message} (request ${caught.requestId})`
          : caught.message,
      );
      return;
    }
    setError(caught instanceof Error ? caught.message : String(caught));
  }

  async function check() {
    if (ungradable) {
      return;
    }
    setBusy("check");
    setError(null);
    try {
      const result = await api.validate(exercise.id, drawing);
      setDryRun(result);
      setMode("check");
      setSelected(null);
    } catch (caught) {
      reportFailure(caught);
    } finally {
      setBusy(null);
    }
  }

  async function submit() {
    if (ungradable) {
      return;
    }
    setBusy("submit");
    setError(null);
    try {
      const stored = await api.submitAttempt(exercise.id, drawing);
      setAttempt(stored);
      setDryRun(null);
      setMode("attempt");
      setSelected(null);
      setExplanations({});
      if (stored.completed) {
        await loadSummary();
      }
    } catch (caught) {
      reportFailure(caught);
    } finally {
      setBusy(null);
    }
  }

  async function loadSummary() {
    setBusy("summary");
    try {
      setSummary(await api.summary(exercise.id));
    } catch (caught) {
      // The exercise is already recorded as complete; a failed summary read is
      // a missing flourish, not a failed submission, so it is not escalated.
      reportFailure(caught);
    } finally {
      setBusy(null);
    }
  }

  async function explain(index: number) {
    if (!attempt) {
      return;
    }
    // The attempt this explanation is about. An answer that arrives after the
    // student has already submitted a new one is about a drawing that is no
    // longer on screen, and showing it there would put one attempt's words under
    // another's findings.
    const askedAbout = attempt.id;
    setBusy("explain");
    setError(null);
    try {
      const response = await api.explain(exercise.id, askedAbout, index);
      if (latestAttempt.current !== askedAbout) {
        return;
      }
      setExplanations((current) => ({ ...current, [index]: response.tutor }));
    } catch (caught) {
      if (latestAttempt.current === askedAbout) {
        reportFailure(caught);
      }
    } finally {
      setBusy(null);
    }
  }

  // A stored attempt's issues, in the engine's order, because that order is the
  // index the explain endpoint expects. The presented copy of each issue is
  // looked up by code plus geometry reference, which is how the learning layer
  // carries a finding's identity across attempts.
  const presentedByKey = useMemo(() => {
    const map = new Map<string, Issue>();
    for (const issue of attempt?.progress.remaining ?? []) {
      map.set(`${issue.code}|${issue.geometry_reference}`, issue);
    }
    return map;
  }, [attempt]);

  const cards: {
    index: number;
    code: string;
    severity: "ERROR" | "WARNING";
    what: string;
    where: string;
    facts: { label: string; value: string }[];
    why?: string;
    how?: string[];
    categoryLabel?: string;
    highlight: string | null;
  }[] = [];

  if (mode === "check" && dryRun) {
    // The dry run carries presented issues, so a check teaches exactly what
    // submitting would. The engine's own findings are the fallback for a
    // response that predates that, and their order is the same either way.
    const presented = dryRun.issues ?? [];
    dryRun.findings.forEach((finding: Finding, index: number) => {
      const issue = presented[index];
      cards.push({
        index,
        code: finding.code,
        severity: issue?.severity ?? finding.severity,
        what: issue?.what_is_wrong ?? finding.message,
        where: issue?.where ?? finding.geometry_reference ?? "not on a specific element",
        facts: issue ? factsFromIssue(issue) : factsFromFinding(finding),
        why: issue?.why_it_matters,
        how: issue?.how_to_fix,
        categoryLabel: issue?.category_label,
        highlight: issue?.geometry_reference ?? finding.geometry_reference,
      });
    });
  } else if (mode === "attempt" && attempt) {
    attempt.validation_result.findings.forEach((finding, index) => {
      const presented = presentedByKey.get(
        `${finding.code}|${finding.geometry_reference}`,
      );
      cards.push({
        index,
        code: finding.code,
        severity: presented?.severity ?? finding.severity,
        what: presented?.what_is_wrong ?? finding.message,
        where: presented?.where ?? finding.geometry_reference ?? "not on a specific element",
        facts: presented ? factsFromIssue(presented) : factsFromFinding(finding),
        why: presented?.why_it_matters,
        how: presented?.how_to_fix,
        categoryLabel: presented?.category_label,
        highlight: presented?.geometry_reference ?? finding.geometry_reference,
      });
    });
  }

  const selectedCard = selected === null ? undefined : cards.find((card) => card.index === selected);
  const passed = mode === "attempt" ? attempt?.validation_result.passed : dryRun?.passed;

  return (
    <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      <div className="space-y-4">
        <section className="rounded border border-neutral-200 bg-white p-4">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-neutral-500">
            Brief
          </h2>
          <p className="mt-2 text-sm text-neutral-700">{exercise.description}</p>
          <ul className="mt-3 space-y-1 font-mono text-xs text-neutral-600">
            {briefLines(exercise).map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
          <p className="mt-3 text-xs text-neutral-500">
            The room should occupy{" "}
            <span className="font-mono">
              {toPaperMm(exercise.room_width_mm, exercise.scale_denominator)}
            </span>{" "}
            ×{" "}
            <span className="font-mono">
              {toPaperMm(exercise.room_height_mm, exercise.scale_denominator)}
            </span>{" "}
            mm of paper at 1:{exercise.scale_denominator}, with{" "}
            <span className="font-mono">
              {toPaperMm(exercise.wall_thickness_mm, exercise.scale_denominator)}
            </span>{" "}
            mm walls.
          </p>
        </section>

        <section className="rounded border border-neutral-200 bg-white p-4">
          <div className="flex items-baseline justify-between gap-2">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-neutral-500">
              Drawing
            </h2>
            <span className="font-mono text-xs text-neutral-400">mm on the sheet</span>
          </div>

          <div className="mt-3 grid grid-cols-2 gap-3">
            <label className="block text-xs text-neutral-600">
              Scale
              <select
                value={editor.scaleDenominator}
                onChange={(event) =>
                  update({ scaleDenominator: Number(event.target.value) })
                }
                className="mt-1 w-full rounded border border-neutral-300 bg-white px-2 py-1 font-mono text-sm"
              >
                {SCALE_CHOICES.map((choice) => (
                  <option key={choice} value={choice}>
                    1:{choice}
                  </option>
                ))}
              </select>
            </label>
            <label className="block text-xs text-neutral-600">
              Wall thickness
              <input
                value={editor.wallThicknessMm}
                onChange={(event) => update({ wallThicknessMm: event.target.value })}
                onBlur={(event) => update({ wallThicknessMm: formatMm(event.target.value) })}
                inputMode="decimal"
                className="mt-1 w-full rounded border border-neutral-300 px-2 py-1 font-mono text-sm"
              />
            </label>
            <label className="block text-xs text-neutral-600">
              Room width
              <input
                value={editor.roomWidthMm}
                onChange={(event) => update({ roomWidthMm: event.target.value })}
                onBlur={(event) => update({ roomWidthMm: formatMm(event.target.value) })}
                inputMode="decimal"
                className="mt-1 w-full rounded border border-neutral-300 px-2 py-1 font-mono text-sm"
              />
            </label>
            <label className="block text-xs text-neutral-600">
              Room height
              <input
                value={editor.roomHeightMm}
                onChange={(event) => update({ roomHeightMm: event.target.value })}
                onBlur={(event) => update({ roomHeightMm: formatMm(event.target.value) })}
                inputMode="decimal"
                className="mt-1 w-full rounded border border-neutral-300 px-2 py-1 font-mono text-sm"
              />
            </label>
          </div>

          <div className="mt-4">
            <div className="flex items-baseline justify-between gap-2">
              <h3 className="text-xs uppercase tracking-wide text-neutral-400">
                Openings
              </h3>
              <button
                type="button"
                onClick={addOpening}
                className="text-xs font-medium text-neutral-700 hover:underline"
              >
                Add
              </button>
            </div>
            {editor.openings.length === 0 && (
              <p className="mt-2 text-xs text-neutral-500">
                None yet. The brief asks for{" "}
                {exercise.door_requirements.reduce((total, item) => total + item.count, 0) +
                  exercise.window_requirements.reduce((total, item) => total + item.count, 0)}
                .
              </p>
            )}
            <ul className="mt-2 space-y-2">
              {editor.openings.map((opening) => (
                <li
                  key={opening.id}
                  className="grid grid-cols-[1fr_1fr_1fr_auto] items-end gap-2 rounded border border-neutral-200 p-2"
                >
                  <label className="block text-[11px] text-neutral-500">
                    Kind
                    <select
                      value={opening.kind}
                      onChange={(event) =>
                        updateOpening(opening.id, {
                          kind: event.target.value as "door" | "window",
                        })
                      }
                      className="mt-0.5 w-full rounded border border-neutral-300 px-1 py-1 text-xs"
                    >
                      <option value="door">door</option>
                      <option value="window">window</option>
                    </select>
                  </label>
                  <label className="block text-[11px] text-neutral-500">
                    Wall
                    <select
                      value={opening.wall}
                      onChange={(event) =>
                        updateOpening(opening.id, { wall: event.target.value as WallSide })
                      }
                      className="mt-0.5 w-full rounded border border-neutral-300 px-1 py-1 text-xs"
                    >
                      {SIDES.map((side) => (
                        <option key={side} value={side}>
                          {side}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="block text-[11px] text-neutral-500">
                    Width
                    <input
                      value={opening.widthMm}
                      onChange={(event) =>
                        updateOpening(opening.id, { widthMm: event.target.value })
                      }
                      onBlur={(event) =>
                        updateOpening(opening.id, { widthMm: formatMm(event.target.value) })
                      }
                      inputMode="decimal"
                      className="mt-0.5 w-full rounded border border-neutral-300 px-1 py-1 font-mono text-xs"
                    />
                  </label>
                  <label className="block text-[11px] text-neutral-500">
                    Offset
                    <input
                      value={opening.offsetMm}
                      placeholder="centre"
                      onChange={(event) =>
                        updateOpening(opening.id, { offsetMm: event.target.value })
                      }
                      onBlur={(event) =>
                        updateOpening(opening.id, { offsetMm: formatMm(event.target.value) })
                      }
                      inputMode="decimal"
                      className="mt-0.5 w-full rounded border border-neutral-300 px-1 py-1 font-mono text-xs"
                    />
                  </label>
                  <button
                    type="button"
                    onClick={() => removeOpening(opening.id)}
                    className="rounded px-1 py-1 text-xs text-neutral-500 hover:text-red-700"
                    aria-label="Remove opening"
                  >
                    ✕
                  </button>
                </li>
              ))}
            </ul>
          </div>

          <div className="mt-4">
            <h3 className="text-xs uppercase tracking-wide text-neutral-400">
              Dimension lines
            </h3>
            <ul className="mt-2 space-y-2">
              {editor.dimensions.map((dimension, index) => (
                <li key={`${dimension.axis}-${index}`} className="flex items-end gap-2">
                  <span className="w-16 shrink-0 pb-1 font-mono text-xs text-neutral-500">
                    {dimension.axis}
                  </span>
                  <label className="block flex-1 text-[11px] text-neutral-500">
                    Value written on the line (real mm)
                    <input
                      value={dimension.valueMm}
                      onChange={(event) => {
                        const next = [...editor.dimensions];
                        next[index] = { ...dimension, valueMm: event.target.value };
                        update({ dimensions: next });
                      }}
                      inputMode="numeric"
                      className="mt-0.5 w-full rounded border border-neutral-300 px-2 py-1 font-mono text-xs"
                    />
                  </label>
                </li>
              ))}
              {editor.dimensions.length === 0 && (
                <li className="text-xs text-neutral-500">
                  This brief does not ask for dimension lines.
                </li>
              )}
            </ul>
          </div>

          <div className="mt-4 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={check}
              disabled={busy !== null || ungradable}
              title={ungradable ? ungradableReason : undefined}
              className="rounded border border-neutral-300 px-3 py-1.5 text-sm font-medium text-neutral-800 hover:bg-neutral-100 disabled:opacity-40"
            >
              {busy === "check" ? "Checking…" : "Check (stores nothing)"}
            </button>
            <button
              type="button"
              onClick={submit}
              disabled={busy !== null || ungradable}
              title={ungradable ? ungradableReason : undefined}
              className="rounded bg-neutral-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-neutral-700 disabled:opacity-40"
            >
              {busy === "submit" ? "Submitting…" : "Submit attempt"}
            </button>
            <button
              type="button"
              onClick={() => setEditor(prefilledEditor(exercise))}
              disabled={busy !== null}
              className="rounded border border-neutral-300 px-3 py-1.5 text-sm text-neutral-700 hover:bg-neutral-100 disabled:opacity-40"
            >
              Fill from the brief
            </button>
            <button
              type="button"
              onClick={() => setEditor(emptyEditor(exercise))}
              disabled={busy !== null}
              className="rounded border border-neutral-300 px-3 py-1.5 text-sm text-neutral-700 hover:bg-neutral-100 disabled:opacity-40"
            >
              Clear
            </button>
          </div>

          {incomplete.length > 0 && (
            <p className="mt-2 text-xs text-neutral-500">
              Still to fill in: {incomplete.join(", ")}. There is nothing to
              check until the drawing has a room, so the two actions above wait
              for the rest.
            </p>
          )}
        </section>
      </div>

      <div className="space-y-4">
        <DrawingSurface
          drawing={drawing}
          highlight={selectedCard?.highlight ?? null}
        />

        {error && (
          <p className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-800">
            {error}
          </p>
        )}

        {mode === "attempt" && attempt && (
          <ProgressPanel attempt={attempt} stale={drawingsDiffer} />
        )}

        {passed && mode === "check" && (
          <section className="rounded border border-green-200 bg-green-50 p-4">
            <h2 className="text-sm font-semibold text-green-900">
              No mistakes found.
            </h2>
            <p className="mt-1 text-sm text-green-800">
              That was a dry run, so nothing was recorded. Submit the attempt to
              finish the exercise.
            </p>
          </section>
        )}

        {cards.length > 0 && (
          <section>
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h2 className="text-sm font-semibold uppercase tracking-wide text-neutral-500">
                {mode === "check" ? "Check" : "Attempt " + attempt?.attempt_number}
              </h2>
              <span className="font-mono text-xs text-neutral-500">
                {cards.length} finding{cards.length === 1 ? "" : "s"}
              </span>
            </div>
            <ul className="mt-3 space-y-3">
              {cards.map((card) => (
                <IssueCard
                  key={`${card.index}-${card.code}`}
                  index={card.index}
                  code={card.code}
                  severity={card.severity}
                  categoryLabel={card.categoryLabel}
                  what={card.what}
                  where={card.where}
                  facts={card.facts}
                  why={card.why}
                  how={card.how}
                  selected={selected === card.index}
                  onSelect={() =>
                    setSelected((current) => (current === card.index ? null : card.index))
                  }
                  explanation={explanations[card.index]}
                  onExplain={() => explain(card.index)}
                  explainDisabled={mode !== "attempt" || !attempt || busy !== null}
                  explainHint={
                    mode === "attempt" && attempt
                      ? busy === null
                        ? undefined
                        : "Wait for the current request to finish first."
                      : "An explanation comes from a stored attempt, so submit this drawing first."
                  }
                  explainPending={busy === "explain"}
                />
              ))}
            </ul>
            {cards.length === 0 && (
              <p className="mt-3 text-sm text-neutral-600">
                Nothing to report.
              </p>
            )}
          </section>
        )}

        {mode === "attempt" && attempt?.completed && (
          <CompletionPanel summary={summary} attempt={attempt} />
        )}

        {mode === "check" && !dryRun && (
          <p className="text-sm text-neutral-500">
            {ungradable
              ? `Nothing to check yet: ${ungradableReason.toLowerCase()}.`
              : "Check the drawing, or submit an attempt to record it."}
          </p>
        )}
      </div>
    </div>
  );
}

function ProgressPanel({ attempt, stale }: { attempt: Attempt; stale: boolean }) {
  const progress = attempt.progress;
  return (
    <section className="rounded border border-neutral-200 bg-white p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-neutral-500">
          Progress
        </h2>
        <span className="font-mono text-xs text-neutral-500">
          attempt {progress.attempt_number} · {progress.remaining_count} left
        </span>
      </div>

      <div className="mt-2 flex flex-wrap gap-2 text-xs">
        <Count label="resolved" value={progress.resolved_count} tone="green" />
        <Count label="changed" value={progress.changed_count} tone="amber" />
        <Count label="new" value={progress.new_count} tone="red" />
        <Count label="remaining" value={progress.remaining_count} tone="neutral" />
      </div>

      {progress.is_first_attempt ? (
        <p className="mt-2 text-xs text-neutral-500">
          First attempt, so there is nothing to compare against yet.
        </p>
      ) : (
        <p className="mt-2 text-xs text-neutral-500">
          {progress.improved
            ? "Fewer mistakes than the attempt before."
            : "No fewer mistakes than the attempt before."}
        </p>
      )}

      {progress.resolved.length > 0 && (
        <p className="mt-2 text-xs text-green-800">
          Fixed since last time:{" "}
          {progress.resolved.map((issue) => issue.code).join(", ")}
        </p>
      )}
      {progress.changed.length > 0 && (
        <p className="mt-1 text-xs text-amber-800">
          Still wrong, but different:{" "}
          {progress.changed.map((issue) => issue.code).join(", ")}
        </p>
      )}
      {progress.new.length > 0 && (
        <p className="mt-1 text-xs text-red-800">
          New mistakes: {progress.new.map((issue) => issue.code).join(", ")}
        </p>
      )}

      {stale && (
        <p className="mt-3 text-xs text-amber-700">
          The drawing has been changed since this attempt. What is shown below is
          the stored result for the drawing as it was submitted.
        </p>
      )}
    </section>
  );
}

function Count({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone: "green" | "amber" | "red" | "neutral";
}) {
  const tones = {
    green: "bg-green-100 text-green-800",
    amber: "bg-amber-100 text-amber-800",
    red: "bg-red-100 text-red-800",
    neutral: "bg-neutral-100 text-neutral-700",
  };
  return (
    <span className={`rounded px-2 py-1 font-mono ${tones[tone]}`}>
      {value} {label}
    </span>
  );
}

function CompletionPanel({
  summary,
  attempt,
}: {
  summary: ExerciseSummary | null;
  attempt: Attempt;
}) {
  const concepts = summary?.concepts ?? [];
  return (
    <section className="rounded border border-green-300 bg-green-50 p-4">
      <h2 className="text-base font-semibold text-green-900">Exercise complete.</h2>
      <p className="mt-1 text-sm text-green-800">
        Attempt {attempt.attempt_number}, {attempt.validation_result.summary.total}{" "}
        finding{attempt.validation_result.summary.total === 1 ? "" : "s"}.
      </p>
      {concepts.length > 0 ? (
        <>
          <h3 className="mt-3 text-xs uppercase tracking-wide text-green-700">
            Demonstrated
          </h3>
          <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-green-900">
            {concepts.map((concept) => (
              <li key={concept}>{concept}</li>
            ))}
          </ul>
        </>
      ) : (
        <p className="mt-2 text-sm text-green-800">Loading what you demonstrated…</p>
      )}
    </section>
  );
}
