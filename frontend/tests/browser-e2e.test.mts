/**
 * The one test that uses a real browser.
 *
 * It walks the path the product is for: read a brief, type a wrong dimension,
 * check the drawing, submit it, ask why, fix the mistake, and finish. Every step
 * is a click or a keystroke in Chrome, not a call into the app's own modules, so
 * a click handler that was never wired up, a canvas that never paints, or a
 * controlled input that ignores typing all fail here.
 *
 * Opt in with ``npm run test:browser``. The default ``npm test`` skips it, so a
 * machine without a browser, or without the two dev servers running, still gets
 * a green suite instead of a red one for the wrong reason.
 */

import test from "node:test";
import assert from "node:assert/strict";

import { findChrome, openPage } from "./cdp.mts";

const optedIn = process.env.ARCHTUTOR_E2E === "1";
const webUrl = process.env.ARCHTUTOR_WEB_URL ?? "http://localhost:3000";
const apiBase = process.env.ARCHTUTOR_API_URL ?? "http://127.0.0.1:8000";

const skip = !optedIn
  ? "browser test is opt-in: run npm run test:browser"
  : !findChrome()
    ? `no Chrome or Chromium found${process.env.CHROME_PATH ? ` at ${process.env.CHROME_PATH}` : ""}`
    : false;

/**
 * Set a controlled input the way a browser would.
 *
 * React installs its own value setter on the element, so assigning `input.value`
 * directly updates the DOM without React noticing. Going through the prototype's
 * setter and then dispatching the event is what makes the framework see the
 * change, which is exactly the gap a unit test cannot cover.
 */
function setField(labelText: string, value: string) {
  const label = Array.from(document.querySelectorAll("label")).find((candidate) =>
    (candidate.textContent ?? "").includes(labelText),
  );
  const field = label?.querySelector("input, select");
  if (!field) {
    return "missing";
  }
  const prototype =
    field instanceof HTMLSelectElement
      ? HTMLSelectElement.prototype
      : HTMLInputElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(prototype, "value")?.set;
  if (!setter) {
    return "no setter";
  }
  setter.call(field, value);
  field.dispatchEvent(new Event("input", { bubbles: true }));
  field.dispatchEvent(new Event("change", { bubbles: true }));
  field.dispatchEvent(new Event("blur", { bubbles: true }));
  return (field as HTMLInputElement).value;
}

/**
 * How much of the stage is not the page background: a canvas that mounted but
 * never painted returns 0, and a missing stage returns -1.
 *
 * The selector is Konva's own container, not any canvas on the page. The Next dev
 * overlay draws to a canvas too, and a canvas that already holds a WebGL
 * context refuses a 2D one, which would look like a missing stage.
 */
function paintedFraction() {
  const canvas = document.querySelector<HTMLCanvasElement>(".konvajs-content canvas");
  if (!canvas) {
    return -1;
  }
  const context = canvas.getContext("2d");
  if (!context) {
    return -1;
  }
  const { data } = context.getImageData(0, 0, canvas.width, canvas.height);
  const pixels = data.length / 4;
  let painted = 0;
  for (let index = 0; index < data.length; index += 4) {
    const visible =
      data[index + 3] > 0 &&
      (data[index] < 250 || data[index + 1] < 250 || data[index + 2] < 250);
    if (visible) {
      painted += 1;
    }
  }
  return painted / pixels;
}

/**
 * The tutor panel's source label, read from the element rather than the text.
 *
 * The label carries the model with it ("llm · openai/gpt-oss-20b"), so this takes
 * the leading word rather than the whole string. Serialised into the page, so it
 * has to be self-contained.
 */
function SOURCE_LABEL() {
  for (const span of Array.from(document.querySelectorAll("span"))) {
    const match = /^(llm|deterministic)\b/.exec((span.textContent ?? "").trim());
    if (match) {
      return match[1];
    }
  }
  return null;
}

test("a student can check, submit, explain and finish in a real browser", { skip }, async () => {
  const { api } = await import("@/lib/api");
  const { drawingFromEditor, newEditorIds, prefilledEditor } = await import(
    "@/lib/editor"
  );

  // The dev servers have to be up: a deliberate request to run this should say
  // so plainly rather than skip.
  const health = await fetch(`${apiBase}/health`).catch(() => null);
  assert.ok(health?.ok, `the API must be running at ${apiBase}`);
  const home = await fetch(webUrl, { redirect: "follow" }).catch(() => null);
  assert.ok(home?.ok, `the web app must be running at ${webUrl}`);

  // Pick a brief the prefill can actually satisfy, so this measures the app and
  // not the seed data. The prefill is what "Fill from the brief" produces, so a
  // student following the app can finish the exercise they were given.
  let chosenId = "";
  let briefWidth = "";
  for (const exercise of (await api.listExercises()).items) {
    const editor = prefilledEditor(exercise);
    const result = await api.validate(
      exercise.id,
      drawingFromEditor(editor, newEditorIds()),
    );
    if (result.passed) {
      chosenId = exercise.id;
      briefWidth = editor.roomWidthMm;
      break;
    }
  }
  assert.ok(chosenId, "no seeded brief is satisfied by the prefill it offers");
  const chosenScale = (await api.getExercise(chosenId)).scale_denominator;

  // Attempt numbers are a per-exercise sequence, so the count of what is
  // already stored says which numbers this run will use.
  const before = (await api.listAttempts(chosenId)).length;
  const page = await openPage();
  try {
    await page.goto(`${webUrl}/drawing?exercise=${chosenId}`);
    await page.waitFor(
      () =>
        document.querySelector(".konvajs-content canvas") !== null &&
        Array.from(document.querySelectorAll("button")).some((button) =>
          button.textContent?.includes("Check"),
        ),
      "the drawing workspace and its stage to load",
      { timeoutMs: 60_000 },
    );

    // A canvas that exists but never painted would pass every other check here.
    const painted = await page.evaluate(paintedFraction);
    assert.ok(painted > 0.005, `the drawing stage should be painted, saw ${painted}`);

    // A sheet with nothing in it cannot be graded, so the actions wait rather
    // than spending a request to be told the drawing is malformed.
    assert.equal(await page.clickText("Check (stores nothing)"), "disabled");
    assert.match(await page.text(), /Still to fill in/);

    // Filling from the brief is how a student starts, and it makes the sheet
    // gradable.
    assert.equal(await page.clickText("Fill from the brief"), "clicked");
    await page.waitFor(
      (value: string) =>
        Array.from(document.querySelectorAll("label"))
          .find((label) => (label.textContent ?? "").includes("Room width"))
          ?.querySelector("input")?.value === value,
      "the brief's room width to be filled in",
      { args: [briefWidth] },
    );
    assert.match(await page.text(), new RegExp(`Scale\\s*1:${chosenScale}`));

    // Typing is the interaction a unit test cannot see: a controlled input can
    // look right in the DOM and still never reach the app's state.
    const wrongWidth = String(Math.round(Number(briefWidth) * 0.8));
    assert.equal(
      await page.evaluate(setField, "Room width", wrongWidth),
      wrongWidth,
      "the room width field should hold what was typed",
    );

    assert.equal(await page.clickText("Check (stores nothing)"), "clicked");
    await page.waitFor(
      () => document.body.textContent?.includes("ROOM_DIMENSION_ERROR"),
      "the wrong room width to be reported",
    );
    const checked = await page.text();
    assert.match(checked, /Why/, "a check should teach, not only report");
    assert.match(checked, /the room outline/, "and should say where the mistake is");
    assert.match(checked, /How/, "and how to fix it");

    // An explanation is about a stored attempt, so the button must refuse
    // rather than answer with some other attempt's issue.
    assert.equal(await page.clickText("Explain this"), "disabled");
    assert.equal(
      (await api.listAttempts(chosenId)).length,
      before,
      "checking must not store an attempt",
    );

    assert.equal(await page.clickText("Submit attempt"), "clicked");
    await page.waitFor(
      (label: string) => document.body.textContent?.includes(label) ?? false,
      "the first stored attempt to be shown",
      { args: [`Attempt ${before + 1}`] },
    );
    assert.equal(
      (await api.listAttempts(chosenId)).length,
      before + 1,
      "submitting stores exactly one attempt",
    );
    assert.doesNotMatch(await page.text(), /Exercise complete\./);

    // Now that the attempt is stored, the same card can be explained. The wait
    // is on the source label element itself rather than on a word in the page's
    // text: the panel's heading and its source sit in adjacent elements, so
    // `textContent` runs them together as "Tutorllm" and a word-boundary pattern
    // never matches. That mistake hid here for a while, because the fallback
    // note also contains a standalone "deterministic", so the wait succeeded
    // only when the tutor was *not* being used.
    assert.equal(await page.clickText("Explain this"), "clicked");
    await page.waitFor(SOURCE_LABEL, "the tutor's explanation to appear");
    // The panel names where the explanation came from, so a reader can tell a
    // model's answer from the deterministic one. Which one it is depends on
    // whether a tutor is configured, and the product is complete either way.
    const source = await page.evaluate(SOURCE_LABEL);
    assert.ok(source === "llm" || source === "deterministic", `unexpected source: ${source}`);
    const explained = await page.text();
    assert.ok(explained.length > 0);

    // Correcting the mistake the way a student would: back to the brief.
    assert.equal(await page.clickText("Fill from the brief"), "clicked");
    await page.waitFor(
      (value: string) =>
        Array.from(document.querySelectorAll("label"))
          .find((label) => (label.textContent ?? "").includes("Room width"))
          ?.querySelector("input")?.value === value,
      "the room width to return to the brief",
      { args: [briefWidth] },
    );

    assert.equal(await page.clickText("Submit attempt"), "clicked");
    await page.waitFor(
      () => document.body.textContent?.includes("Exercise complete."),
      "the exercise to be complete",
    );
    const finished = await page.text();
    assert.match(finished, /Demonstrated/, "completion names what was demonstrated");
    assert.ok(
      finished.includes(`Attempt ${before + 2}, 0 findings`),
      `the completing attempt should report no findings, saw: ${finished.slice(-400)}`,
    );
    assert.equal(
      (await api.listAttempts(chosenId)).length,
      before + 2,
      "two attempts, and only two, should be stored",
    );

    assert.deepEqual(page.errors, [], "the page should raise no uncaught errors");
  } finally {
    await page.close();
  }
});
