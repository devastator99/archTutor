/**
 * The editor's conversions, tested without a browser.
 *
 * These are the only functions that turn what a student typed into geometry, and
 * the geometry they produce is what the validator judges. A mistake here is not
 * a cosmetic bug: a wall drawn at the wrong thickness, or an opening attached
 * to a wall id that does not exist, would produce a verdict about a drawing the
 * student never made. So the conversions are pinned here, where they are cheap
 * to pin, rather than discovered by looking at a screenshot.
 *
 * Run with the repository's own runner: `npm test`.
 */

import test from "node:test";
import assert from "node:assert/strict";

import {
  drawingFromEditor,
  emptyEditor,
  formatMm,
  missingFields,
  newEditorIds,
  parseMm,
  prefilledEditor,
  type EditorState,
} from "@/lib/editor";
import { briefLines, correctDrawingFor, newId, toPaperMm } from "@/lib/drawing";
import type { Exercise, StudentDrawing } from "@/lib/api";

function exercise(overrides: Partial<Exercise> = {}): Exercise {
  return {
    slug: "room-4200x3600-1-50",
    title: "Room 4200 x 3600 at 1:50",
    description: "Draw a 4200 x 3600 mm room at 1:50.",
    room_width_mm: 4200,
    room_height_mm: 3600,
    wall_thickness_mm: 230,
    scale_denominator: 50,
    door_requirements: [
      { kind: "door", width_mm: 900, count: 1, wall: "south", offset_mm: null, sill_height_mm: null, notes: null },
    ],
    window_requirements: [],
    dimension_requirements: [
      { axis: "width", value_mm: 4200, on_wall: "south", label: null },
    ],
    difficulty: "beginner",
    id: "11111111-1111-4111-8111-111111111111",
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function twoWindowExercise(): Exercise {
  return exercise({
    room_width_mm: 4800,
    dimension_requirements: [
      { axis: "width", value_mm: 4800, on_wall: "south", label: null },
    ],
    window_requirements: [
      { kind: "window", width_mm: 1200, count: 2, wall: "north", offset_mm: null, sill_height_mm: 900, notes: null },
    ],
  });
}

test("a typed number is read, and anything else is not", () => {
  assert.equal(parseMm("84"), 84);
  assert.equal(parseMm(" 84.0 "), 84);
  assert.equal(parseMm(""), null);
  assert.equal(parseMm("   "), null);
  assert.equal(parseMm("eighty"), null);
  assert.equal(parseMm("NaN"), null);
});

test("a field is tidied on blur without changing its value", () => {
  assert.equal(formatMm("84.0"), "84");
  assert.equal(formatMm("84.006"), "84.01");
  assert.equal(formatMm("nonsense"), "nonsense");
});

test("a real millimetre figure becomes paper at the brief's scale", () => {
  assert.equal(toPaperMm(4200, 50), 84);
  assert.equal(toPaperMm(2100, 20), 105);
  assert.equal(toPaperMm(7200, 200), 36);
});

test("an empty sheet says which figures are still missing", () => {
  const state = emptyEditor(exercise());
  assert.deepEqual(missingFields(state), ["room width", "room height", "wall thickness"]);

  const filled = { ...state, roomWidthMm: "84", roomHeightMm: "72", wallThicknessMm: "4.6" };
  assert.deepEqual(missingFields(filled), []);
});

test("a prefilled sheet carries the brief's figures in paper millimetres", () => {
  const state = prefilledEditor(exercise());
  const drawing = drawingFromEditor(state, newEditorIds());

  assert.equal(state.roomWidthMm, "84");
  assert.equal(state.roomHeightMm, "72");
  assert.equal(state.wallThicknessMm, "4.6");
  assert.deepEqual(
    drawing.room.boundary.map((point) => [point.x, point.y]),
    [
      ["0", "0"],
      ["84", "0"],
      ["84", "72"],
      ["0", "72"],
    ],
  );
  assert.equal(drawing.walls.length, 4);
  assert.ok(drawing.walls.every((wall) => wall.thickness_mm === "4.6"));
  assert.equal(drawing.openings[0].width_mm, "18");
  assert.equal(drawing.dimensions[0].actual_value_mm, "4200");
  assert.equal(drawing.scale_denominator, 50);
});

test("every opening is hosted by a wall that exists", () => {
  const drawing = drawingFromEditor(prefilledEditor(twoWindowExercise()), newEditorIds());
  const wallIds = new Set(drawing.walls.map((wall) => wall.id));

  assert.equal(drawing.openings.length, 2);
  for (const opening of drawing.openings) {
    assert.ok(wallIds.has(opening.host_wall_id), `unknown host ${opening.host_wall_id}`);
  }
  assert.equal(new Set(drawing.openings.map((o) => o.id)).size, 2);
});

test("an opening with no width is not drawn", () => {
  const state = prefilledEditor(exercise());
  const blank: EditorState = {
    ...state,
    openings: state.openings.map((opening) => ({ ...opening, widthMm: "" })),
  };
  const drawing = drawingFromEditor(blank, newEditorIds());

  assert.equal(drawing.openings.length, 0);
});

test("a dimension with no value written is not drawn", () => {
  const state = prefilledEditor(exercise());
  const drawing = drawingFromEditor(
    { ...state, dimensions: [{ axis: "width", valueMm: "" }] },
    newEditorIds(),
  );

  assert.equal(drawing.dimensions.length, 0);
});

test("a blank offset centres the opening on its wall", () => {
  const state = prefilledEditor(exercise());
  const drawing = drawingFromEditor(state, newEditorIds());
  // 900 mm at 1:50 is 18 mm on the sheet, centred on an 84 mm wall.
  assert.equal(drawing.openings[0].offset_mm, "33");
});

test("an explicit offset is the student's, not the editor's", () => {
  const state = prefilledEditor(exercise());
  const drawing = drawingFromEditor(
    {
      ...state,
      openings: state.openings.map((opening) => ({ ...opening, offsetMm: "5" })),
    },
    newEditorIds(),
  );

  assert.equal(drawing.openings[0].offset_mm, "5");
});

test("the scale sent is the one the student chose, not the brief's", () => {
  const state = { ...prefilledEditor(exercise()), scaleDenominator: 100 };
  const drawing = drawingFromEditor(state, newEditorIds());

  assert.equal(drawing.scale_denominator, 100);
  // The room figures are untouched, so drawing at 1:100 with a 1:50 size is
  // possible on purpose: that is the mistake the scale check exists to catch.
  assert.equal(drawing.room.boundary[1].x, "84");
});

test("wall ids survive a re-render, so opening references stay valid", () => {
  const ids = newEditorIds();
  const state = prefilledEditor(exercise());
  const first = drawingFromEditor(state, ids);
  const second = drawingFromEditor({ ...state, roomWidthMm: "80" }, ids);

  assert.deepEqual(
    first.walls.map((wall) => wall.id),
    second.walls.map((wall) => wall.id),
  );
  assert.equal(second.openings[0].host_wall_id, second.walls[0].id);
});

test("a wall is horizontal or vertical, never diagonal", () => {
  const drawing = drawingFromEditor(prefilledEditor(exercise()), newEditorIds());

  for (const wall of drawing.walls) {
    const sameRow = wall.start.y === wall.end.y;
    const sameColumn = wall.start.x === wall.end.x;
    assert.ok(sameRow !== sameColumn, `diagonal wall ${wall.start.x},${wall.start.y}`);
  }
});

test("the helper's correct drawing satisfies a two-window brief", () => {
  const drawing: StudentDrawing = correctDrawingFor(twoWindowExercise());
  const wallIds = new Set(drawing.walls.map((wall) => wall.id));

  // The brief still asks for its door, so there are three openings: one door
  // and the two windows, which is the whole point of checking the count.
  assert.equal(drawing.openings.length, 3);
  for (const opening of drawing.openings) {
    assert.ok(wallIds.has(opening.host_wall_id));
  }
  const windows = drawing.openings.filter((opening) => opening.kind === "window");
  assert.equal(windows.length, 2);
  // 1200 mm at 1:50 is 24 mm on a 96 mm wall: two windows, three equal gaps of
  // 16 mm, so the offsets are 16 and 56.
  assert.deepEqual(windows.map((opening) => opening.offset_mm), ["16", "56"]);
});

test("the brief reads as instructions, in the units it was given", () => {
  const lines = briefLines(twoWindowExercise());

  assert.ok(lines.includes("Room 4800 × 3600 mm"));
  assert.ok(lines.includes("Scale 1:50"));
  assert.ok(lines.includes("Walls 230 mm"));
  assert.ok(lines.includes("1 × 900 mm door on the south wall"));
  assert.ok(lines.includes("2 × 1200 mm windows on the north wall, 900 mm sill"));
  assert.ok(lines.includes("Dimension the width as 4800 mm on the south wall"));
});

test("generated ids are UUIDs the backend will accept", () => {
  const pattern = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

  assert.match(newId(), pattern);
  assert.match(newEditorIds().walls.south, pattern);
  assert.equal(new Set(Object.values(newEditorIds().walls)).size, 4);
});

test("ids are still valid UUIDs without crypto.randomUUID", () => {
  const original = Object.getOwnPropertyDescriptor(globalThis, "crypto");
  Object.defineProperty(globalThis, "crypto", {
    configurable: true,
    value: { getRandomValues: (bytes: Uint8Array) => bytes.fill(7) },
  });
  try {
    const id = newId();
    assert.match(id, /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
  } finally {
    if (original) {
      Object.defineProperty(globalThis, "crypto", original);
    }
  }
});
