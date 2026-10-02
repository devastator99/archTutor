"use client";

import type { Finding, Issue, TutorExplanation } from "@/lib/api";

/**
 * One mistake, as a student reads it.
 *
 * The seven facts are separate rows rather than a paragraph: WHAT, WHERE,
 * EXPECTED, ACTUAL, DIFFERENCE, WHY and HOW. A student needs to be able to point
 * at a row and say "that number is the problem", which a sentence does not allow.
 *
 * Both response shapes render through this one card. A stored attempt arrives as
 * a presented `Issue` with the teaching fields filled in; a dry run arrives as an
 * engine `Finding`, which is a fact and a message but no teaching, because the
 * learning layer reads stored attempts. The card says which it is showing rather
 * than filling the gap with prose the validator never produced.
 */

export interface IssueCardProps {
  index: number;
  code: string;
  categoryLabel?: string;
  severity: "ERROR" | "WARNING";
  what: string;
  where: string;
  facts: { label: string; value: string }[];
  why?: string;
  how?: string[];
  selected: boolean;
  onSelect: () => void;
  explanation?: TutorExplanation;
  onExplain: () => void;
  explainDisabled: boolean;
  explainPending: boolean;
  /** Why the button is unavailable, when it is. */
  explainHint?: string;
}

const SEVERITY_STYLE: Record<IssueCardProps["severity"], string> = {
  ERROR: "border-red-200 bg-red-50/40",
  WARNING: "border-amber-200 bg-amber-50/40",
};

export function IssueCard(props: IssueCardProps) {
  const {
    index,
    code,
    categoryLabel,
    severity,
    what,
    where,
    facts,
    why,
    how,
    selected,
    onSelect,
    explanation,
    onExplain,
    explainDisabled,
    explainPending,
    explainHint,
  } = props;
  const shown = facts.filter((fact) => fact.value !== "" && fact.value !== "null");

  return (
    <li
      className={`rounded border p-4 ${selected ? "border-red-400 ring-1 ring-red-200" : SEVERITY_STYLE[severity]}`}
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="font-mono text-xs text-neutral-500">
          {index + 1}. {code}
        </span>
        <span className="font-mono text-xs text-neutral-400">
          {categoryLabel ?? severity.toLowerCase()}
        </span>
      </div>

      <button
        type="button"
        onClick={onSelect}
        className="mt-2 block w-full text-left"
        aria-pressed={selected}
      >
        <span className="block text-xs uppercase tracking-wide text-neutral-400">
          What
        </span>
        <span className="mt-0.5 block text-sm text-neutral-800">{what}</span>
        <span className="mt-2 block text-xs uppercase tracking-wide text-neutral-400">
          Where
        </span>
        <span className="mt-0.5 block font-mono text-xs text-neutral-700">{where}</span>
      </button>

      {shown.length > 0 && (
        <dl className="mt-3 grid grid-cols-3 gap-2 font-mono text-xs">
          {shown.map((fact) => (
            <div key={fact.label} className="rounded bg-white/70 px-2 py-1">
              <dt className="text-neutral-400">{fact.label}</dt>
              <dd className="mt-0.5 text-neutral-800">{fact.value}</dd>
            </div>
          ))}
        </dl>
      )}

      {why && (
        <p className="mt-3 text-sm text-neutral-600">
          <span className="text-xs uppercase tracking-wide text-neutral-400">
            Why{" "}
          </span>
          {why}
        </p>
      )}

      {how && how.length > 0 && (
        <div className="mt-2">
          <span className="text-xs uppercase tracking-wide text-neutral-400">
            How
          </span>
          <ol className="mt-1 list-decimal space-y-1 pl-5 text-sm text-neutral-700">
            {how.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ol>
        </div>
      )}

      {!why && !how && (
        <p className="mt-3 text-xs text-neutral-500">
          The engine measured this and found a discrepancy, but the API returned
          no teaching copy with it. Submit the attempt to see it explained.
        </p>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={onExplain}
          disabled={explainDisabled || explainPending}
          title={explainDisabled ? explainHint : undefined}
          className="rounded border border-neutral-300 px-2 py-1 text-xs font-medium text-neutral-700 hover:bg-neutral-100 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {explainPending ? "Explaining…" : "Explain this"}
        </button>
        {selected && (
          <span className="text-xs text-neutral-500">
            Shown in red on the drawing.
          </span>
        )}
      </div>

      {explanation && (
        <div className="mt-3 rounded border border-neutral-200 bg-white p-3">
          <div className="flex items-baseline justify-between gap-2">
            <span className="text-xs uppercase tracking-wide text-neutral-400">
              Tutor
            </span>
            <span className="font-mono text-[11px] text-neutral-400">
              {explanation.source}
              {explanation.model ? ` · ${explanation.model}` : ""}
            </span>
          </div>
          <p className="mt-1 whitespace-pre-line text-sm text-neutral-700">
            {explanation.explanation}
          </p>
          {explanation.blocked_numbers.length > 0 && (
            <p className="mt-2 rounded bg-amber-50 px-2 py-1 text-xs text-amber-800">
              A drafted explanation used figures the validator has not confirmed
              ({explanation.blocked_numbers.join(", ")}), so it was discarded and
              the explanation below is the deterministic one.
            </p>
          )}
        </div>
      )}
    </li>
  );
}

/** Facts from a presented issue, in the seven-field order. */
export function factsFromIssue(issue: Issue): { label: string; value: string }[] {
  return [
    { label: "expected", value: text(issue.expected) },
    { label: "actual", value: text(issue.actual) },
    { label: "difference", value: text(issue.difference) },
  ];
}

/** Facts from an engine finding: the same three numbers, and the unit that
 *  makes them mean something. */
export function factsFromFinding(finding: Finding): { label: string; value: string }[] {
  const withUnit = (value: string | number | null) =>
    value === null || value === "" ? "" : `${value} ${finding.unit}`;
  return [
    { label: "expected", value: withUnit(finding.expected) },
    { label: "actual", value: withUnit(finding.actual) },
    { label: "difference", value: withUnit(finding.difference) },
  ];
}

function text(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") {
    return "";
  }
  return String(value);
}
