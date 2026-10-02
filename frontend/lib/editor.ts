/**
 * The editor's state, and the one conversion out of it.
 *
 * The student edits numbers, not geometry: room size on the sheet, wall
 * thickness, each opening's width and position, and the value each dimension
 * line claims. `drawingFromEditor` turns that into the `StudentDrawing` the API
 * expects, and it is the only place that builds one.
 *
 * Why the state is flat numbers rather than points: every geometric fact the
 * validator needs (a closed rectangle, walls on the boundary, openings hosted by
 * a wall) is implied by these numbers. A student who cannot move a wall off the
 * boundary cannot draw a shape that is not a room, so the editor never offers an
 * illegal move. What the student can get wrong is exactly what the exercise is
 * about: sizes, scale, wall thickness, opening widths and the numbers written on
 * the dimension lines.
 *
 * Nothing here judges. Every value is passed through as the student typed it,
 * including values that are wrong on purpose -- turning a correct answer into a
 * wrong one is how the student practices finding the mistake.
 */

import type { Exercise, StudentDrawing, WallSide } from "@/lib/api";
import { newId, toPaperMm } from "@/lib/drawing";

/** The sides a wall can sit on, matching the backend's own naming. */
export const SIDES: WallSide[] = ["south", "north", "west", "east"];

/** Scales a student may draw at. The brief's scale is listed first and is the
 *  default; the others exist so a student can practise the mistake of drawing
 *  at the wrong scale and see what the validator says about it. */
export const SCALE_CHOICES = [20, 25, 50, 100, 200];

export interface EditorOpening {
  id: string;
  kind: "door" | "window";
  wall: WallSide;
  /** Width of the opening on the sheet, in millimetres of paper. */
  widthMm: string;
  /** Distance from the start of its wall to the near edge, on the sheet. */
  offsetMm: string;
}

export interface EditorState {
  scaleDenominator: number;
  /** Room size on the sheet, in millimetres of paper. */
  roomWidthMm: string;
  roomHeightMm: string;
  wallThicknessMm: string;
  openings: EditorOpening[];
  /** The value the student writes on each dimension line, in real millimetres. */
  dimensions: { axis: "width" | "height"; valueMm: string }[];
}

/** Parse a user-typed number, or `null` if it is not one. */
export function parseMm(value: string): number | null {
  const trimmed = value.trim();
  if (trimmed === "") {
    return null;
  }
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) ? parsed : null;
}

/** `84` for `84`, `84.00` for `84.0`, and the input back if it was not a number. */
export function formatMm(value: string): string {
  const parsed = parseMm(value);
  if (parsed === null) {
    return value;
  }
  return String(Number(parsed.toFixed(2)));
}

/** Wall ids are minted once per editing session and kept in state, because every
 *  opening refers to its host wall by id. Minting them during render would
 *  change the ids on each keystroke and break those references. */
export interface EditorIds {
  walls: Record<WallSide, string>;
}

export function newEditorIds(): EditorIds {
  return { walls: { south: newId(), north: newId(), west: newId(), east: newId() } };
}

/**
 * An empty sheet at the brief's scale.
 *
 * Deliberately wrong: the room is 100 mm square with 10 mm walls and no
 * openings. A student who submits this without drawing anything gets a full set
 * of honest findings, which is a better first experience than an empty sheet
 * that cannot be measured at all.
 */
export function emptyEditor(exercise: Exercise): EditorState {
  return {
    scaleDenominator: exercise.scale_denominator,
    roomWidthMm: "",
    roomHeightMm: "",
    wallThicknessMm: "",
    openings: [],
    dimensions: exercise.dimension_requirements.map((requirement) => ({
      axis: requirement.axis,
      valueMm: "",
    })),
  };
}

/** Fill every field with the brief's correct figures, computed on the sheet. */
export function prefilledEditor(exercise: Exercise): EditorState {
  const scale = exercise.scale_denominator;
  return {
    scaleDenominator: scale,
    roomWidthMm: formatMm(String(toPaperMm(exercise.room_width_mm, scale))),
    roomHeightMm: formatMm(String(toPaperMm(exercise.room_height_mm, scale))),
    wallThicknessMm: formatMm(String(toPaperMm(exercise.wall_thickness_mm, scale))),
    openings: [...exercise.door_requirements, ...exercise.window_requirements].map(
      (requirement) => ({
        id: newId(),
        kind: requirement.kind,
        wall: requirement.wall ?? "south",
        widthMm: formatMm(String(toPaperMm(requirement.width_mm, scale))),
        offsetMm: "",
      }),
    ),
    dimensions: exercise.dimension_requirements.map((requirement) => ({
      axis: requirement.axis,
      valueMm: String(requirement.value_mm),
    })),
  };
}

/** Where an opening sits when the student has not chosen: centred on its wall. */
function defaultOffset(state: EditorState, wall: WallSide, widthMm: number): number {
  const wallLength = wall === "north" || wall === "south" ? state.roomWidthMm : state.roomHeightMm;
  const length = parseMm(wallLength) ?? 0;
  const offset = (length - widthMm) / 2;
  return Number.isFinite(offset) && offset >= 0 ? Number(offset.toFixed(2)) : 0;
}

/**
 * Build the drawing to send.
 *
 * A field the student left blank is simply not drawn. That is the honest
 * reading: a blank room size means there is no room on the sheet, and the
 * validator reports what it cannot find. A blank claimed value means the student
 * has not written that dimension, so no dimension line is sent.
 */
export function drawingFromEditor(
  state: EditorState,
  ids: EditorIds,
): StudentDrawing {
  const width = parseMm(state.roomWidthMm) ?? 0;
  const height = parseMm(state.roomHeightMm) ?? 0;
  const thickness = parseMm(state.wallThicknessMm) ?? 0;
  const num = (value: number) => String(Number(value.toFixed(2)));

  // South is the top edge of the sheet and north the bottom, which is the
  // backend's own convention (`north` is maximum y, `south` is minimum y).
  const corners = {
    southWest: { x: "0", y: "0" },
    southEast: { x: num(width), y: "0" },
    northWest: { x: "0", y: num(height) },
    northEast: { x: num(width), y: num(height) },
  };

  const walls = [
    { id: ids.walls.south, start: corners.southWest, end: corners.southEast },
    { id: ids.walls.north, start: corners.northWest, end: corners.northEast },
    { id: ids.walls.west, start: corners.southWest, end: corners.northWest },
    { id: ids.walls.east, start: corners.southEast, end: corners.northEast },
  ].map((wall) => ({ ...wall, thickness_mm: num(thickness) }));

  const openings = state.openings.flatMap((opening) => {
    const widthMm = parseMm(opening.widthMm);
    if (widthMm === null || widthMm <= 0) {
      return [];
    }
    const offset = parseMm(opening.offsetMm);
    return [
      {
        id: opening.id,
        host_wall_id: ids.walls[opening.wall],
        offset_mm: num(offset ?? defaultOffset(state, opening.wall, widthMm)),
        width_mm: num(widthMm),
        kind: opening.kind,
      },
    ];
  });

  const dimensions = state.dimensions.flatMap((dimension) => {
    const claimed = parseMm(dimension.valueMm);
    if (claimed === null) {
      return [];
    }
    return [
      dimension.axis === "width"
        ? {
            start: { x: "0", y: num(-10) },
            end: { x: num(width), y: num(-10) },
            actual_value_mm: String(claimed),
          }
        : {
            start: { x: num(-10), y: "0" },
            end: { x: num(-10), y: num(height) },
            actual_value_mm: String(claimed),
          },
    ];
  });

  return {
    scale_denominator: state.scaleDenominator,
    room: {
      boundary: [corners.southWest, corners.southEast, corners.northEast, corners.northWest],
    },
    walls,
    openings,
    dimensions,
  };
}

/** Every field of a drawing that is empty, for an honest "not drawable yet". */
export function missingFields(state: EditorState): string[] {
  const missing: string[] = [];
  if (parseMm(state.roomWidthMm) === null) missing.push("room width");
  if (parseMm(state.roomHeightMm) === null) missing.push("room height");
  if (parseMm(state.wallThicknessMm) === null) missing.push("wall thickness");
  return missing;
}
