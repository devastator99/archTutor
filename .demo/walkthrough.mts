/**
 * A walkthrough of the built product, in a real browser, saving a screenshot at
 * every step. Not a test: nothing here asserts, it just drives the app the way a
 * student would and leaves pictures behind.
 *
 *   node --import ./tests/register.mjs ../.demo/walkthrough.mts
 */

import { writeFile } from "node:fs/promises";

import { openPage } from "../frontend/tests/cdp.mts";

const webUrl = process.env.ARCHTUTOR_WEB_URL ?? "http://localhost:3000";
const apiBase = process.env.ARCHTUTOR_API_URL ?? "http://127.0.0.1:8000";
const outDir = new URL("./screens/", import.meta.url).pathname;

const { api } = await import("../frontend/lib/api.ts");
const { drawingFromEditor, newEditorIds, prefilledEditor } = await import(
  "../frontend/lib/editor.ts"
);

function setField(labelText: string, value: string) {
  const label = Array.from(document.querySelectorAll("label")).find((candidate) =>
    (candidate.textContent ?? "").includes(labelText),
  );
  const field = label?.querySelector("input, select");
  if (!field) {
    return "missing";
  }
  const prototype =
    field instanceof HTMLSelectElement ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(prototype, "value")?.set;
  setter?.call(field, value);
  field.dispatchEvent(new Event("input", { bubbles: true }));
  field.dispatchEvent(new Event("change", { bubbles: true }));
  return (field as HTMLInputElement).value;
}

/**
 * Screenshot plus the page's own words, because a picture shows the layout and
 * the text shows what the app actually says. Reading the two together is the
 * only way to tell "looks right" from "says the right thing".
 */
const step = async (page: any, name: string, note: string) => {
  await page.screenshot(`${outDir}${name}.png`);
  const text = (await page.text()).replace(/\n{3,}/g, "\n\n").trim();
  await writeFile(`${outDir}${name}.txt`, text);
  console.log(`  ${name}  ${note}`);
};

const health = await fetch(`${apiBase}/health`);
console.log(`API ${apiBase} -> ${health.status}`);
await fetch(`${webUrl}/exercise`);

let chosenId = "";
let briefWidth = "";
for (const exercise of (await api.listExercises()).items) {
  const editor = prefilledEditor(exercise);
  const result = await api.validate(exercise.id, drawingFromEditor(editor, newEditorIds()));
  if (result.passed) {
    chosenId = exercise.id;
    briefWidth = editor.roomWidthMm;
    console.log(
      `brief: ${exercise.title} — ${exercise.room_width_mm} x ${exercise.room_height_mm} mm` +
        ` real, 1:${exercise.scale_denominator}, so ${briefWidth} mm on the sheet`,
    );
    break;
  }
}

const page = await openPage();
try {
  await page.goto(`${webUrl}/exercise`);
  await page.waitFor(() => document.body.textContent?.includes("at 1:") ?? false, "briefs");
  await step(page, "1-briefs", "the list of briefs, all 20 seeded");

  await page.goto(`${webUrl}/drawing?exercise=${chosenId}`);
  await page.waitFor(
    () =>
      document.querySelector(".konvajs-content canvas") !== null &&
      Array.from(document.querySelectorAll("button")).some((b) => b.textContent?.includes("Check")),
    "the workspace",
    { timeoutMs: 60_000 },
  );
  await step(page, "2-blank", "an empty sheet: nothing can be graded yet");

  await page.clickText("Fill from the brief");
  await page.waitFor(
    (value: string) =>
      Array.from(document.querySelectorAll("label"))
        .find((l) => (l.textContent ?? "").includes("Room width"))
        ?.querySelector("input")?.value === value,
    "the brief filled in",
    { args: [briefWidth] },
  );
  await new Promise((resolve) => setTimeout(resolve, 400));
  await step(page, "3-filled", "filled from the brief: fields in sheet mm, drawn to scale");

  const wrongWidth = String(Math.round(Number(briefWidth) * 0.8));
  await page.evaluate(setField, "Room width", wrongWidth);
  await new Promise((resolve) => setTimeout(resolve, 400));
  await step(page, "4-wrong", `room width mistyped: ${wrongWidth} sheet mm instead of ${briefWidth}`);

  await page.clickText("Check (stores nothing)");
  await page.waitFor(
    () => document.body.textContent?.includes("ROOM_DIMENSION_ERROR") ?? false,
    "the check",
  );
  await new Promise((resolve) => setTimeout(resolve, 300));
  await step(page, "5-check", "Check teaches: what, where, why, how — and stores nothing");

  await page.clickText("Submit attempt");
  await page.waitFor(
    () => /Attempt \d+/.test(document.body.textContent ?? ""),
    "the stored attempt",
  );
  await new Promise((resolve) => setTimeout(resolve, 300));
  await step(page, "6-attempt", "submitted: stored, graded, progress computed");

  // Wait for the button to be live before clicking: a click that lands before
  // React has attached its handler is a no-op, and the wait afterwards then
  // times out for a reason that has nothing to do with the app.
  await page.waitFor(
    () =>
      Array.from(document.querySelectorAll("button")).some(
        (b) => b.textContent?.includes("Explain this") && !b.disabled,
      ),
    "the explain button to become available",
  );
  console.log(`  explain click -> ${await page.clickText("Explain this")}`);
  await page.waitFor(
    () =>
      Array.from(document.querySelectorAll("span")).some((s) =>
        /^(llm|deterministic)\b/.test((s.textContent ?? "").trim()),
      ),
    "the explanation",
    { timeoutMs: 60_000 },
  );
  await new Promise((resolve) => setTimeout(resolve, 300));
  await step(page, "7-tutor", "the tutor explains it, and names where the answer came from");

  await page.clickText("Fill from the brief");
  await page.waitFor(
    (value: string) =>
      Array.from(document.querySelectorAll("label"))
        .find((l) => (l.textContent ?? "").includes("Room width"))
        ?.querySelector("input")?.value === value,
    "the correction",
    { args: [briefWidth] },
  );
  await page.clickText("Submit attempt");
  await page.waitFor(
    () => document.body.textContent?.includes("Exercise complete.") ?? false,
    "completion",
  );
  await new Promise((resolve) => setTimeout(resolve, 300));
  await step(page, "8-complete", "corrected and finished: what was demonstrated");

  const summaries = (await api.listExercises()).items.length;
  console.log(`\n${summaries} briefs available; screenshots in ${outDir}`);
  if (page.errors.length > 0) {
    console.log(`page errors: ${page.errors.join(" | ")}`);
  }
} finally {
  await page.close();
}
