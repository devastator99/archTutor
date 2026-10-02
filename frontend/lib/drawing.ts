/**
 * Turning a brief into a drawing.
 *
 * This is the only place in the frontend that does arithmetic on dimensions,
 * and it is deliberately a *display* concern: converting a real-world
 * millimetre figure to the millimetres of paper it should occupy at 1:N, so the
 * editor can show the student the size they are aiming for.
 *
 * Two rules keep this from becoming a second validator:
 *
 * 1. Nothing here decides whether a drawing is correct. The student may enter
 *    any number at all, including a wrong one on purpose, and that is the point
 *    of the exercise. These helpers only ever *prefill* a field.
 * 2. Every conversion goes through `app/measurement` on the server when it
 *    matters. What is computed here is a starting value for a text input, and it
 *    is always shown next to the brief so the student can check it.
 *
 * The arithmetic is `actual / denominator`, kept in this one function so there
 * is a single line to audit rather than a formula repeated across components.
 */

import type { Exercise, Point, StudentDrawing, Wall } from "@/lib/api";

/** Real-world millimetres to millimetres of paper at 1:N. */
export function toPaperMm(actualMm: number, scaleDenominator: number): number {
  return actualMm / scaleDenominator;
}

/** The brief as a list of lines a student can read without decoding JSON. */
export function briefLines(exercise: Exercise): string[] {
  const lines: string[] = [
    `Room ${exercise.room_width_mm} × ${exercise.room_height_mm} mm`,
    `Scale 1:${exercise.scale_denominator}`,
    `Walls ${exercise.wall_thickness_mm} mm`,
  ];

  for (const door of exercise.door_requirements) {
    lines.push(
      `${door.count} × ${door.width_mm} mm ${plural(door.count, "door")}${door.wall ? ` on the ${door.wall} wall` : ""}`,
    );
  }
  for (const window of exercise.window_requirements) {
    const sill = window.sill_height_mm ? `, ${window.sill_height_mm} mm sill` : "";
    lines.push(
      `${window.count} × ${window.width_mm} mm ${plural(window.count, "window")}${window.wall ? ` on the ${window.wall} wall` : ""}${sill}`,
    );
  }
  for (const dimension of exercise.dimension_requirements) {
    lines.push(
      `Dimension the ${dimension.axis} as ${dimension.value_mm} mm${dimension.on_wall ? ` on the ${dimension.on_wall} wall` : ""}`,
    );
  }
  return lines;
}

/** `1 door` and `2 doors`: a brief that says "2 × 900 mm door" is a typo waiting
 *  to be read as a mistake in the brief rather than in the drawing. */
function plural(count: number, noun: string): string {
  return count === 1 ? noun : `${noun}s`;
}

/** A UUID-shaped id, so a wall is referencable before the server assigns one.
 *
 *  The backend rejects anything that is not a UUID (`walls[0].id must be a
 *  UUID`), so the fallback below is deliberately shaped like a v4 rather than a
 *  short string. Ids are generated on the client only to let an opening refer to
 *  its host wall within one drawing; the server never trusts or reuses them.
 */
export function newId(): string {
  const cryptoRef = globalThis.crypto;
  if (cryptoRef && typeof cryptoRef.randomUUID === "function") {
    return cryptoRef.randomUUID();
  }
  const hex = (): string => {
    const bytes = new Uint8Array(16);
    if (cryptoRef && typeof cryptoRef.getRandomValues === "function") {
      cryptoRef.getRandomValues(bytes);
    } else {
      for (let i = 0; i < bytes.length; i += 1) {
        bytes[i] = Math.floor(Math.random() * 256);
      }
    }
    return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
  };
  const raw = hex();
  return [
    raw.slice(0, 8),
    raw.slice(8, 12),
    `4${raw.slice(13, 16)}`,
    `${"89ab"[Number.parseInt(raw[16], 16) % 4]}${raw.slice(17, 20)}`,
    raw.slice(20, 32),
  ].join("-");
}

/** Round to hundredths: no drawing is measured finer than 0.01 mm. */
function paper(value: number): string {
  return String(Number(value.toFixed(2)));
}

/**
 * A starting drawing for this brief, with every figure correct.
 *
 * This is the editor's "correct answer" button, not a cheat: it exists so a
 * student can see what a right drawing looks like before making their own, and
 * so the preview is not an empty box. It is labelled as such in the UI.
 */
export function correctDrawingFor(exercise: Exercise): StudentDrawing {
  const scale = exercise.scale_denominator;
  const width = toPaperMm(exercise.room_width_mm, scale);
  const height = toPaperMm(exercise.room_height_mm, scale);
  const thickness = toPaperMm(exercise.wall_thickness_mm, scale);

  const origin: Point = { x: "0", y: "0" };
  const topRight: Point = { x: paper(width), y: "0" };
  const bottomRight: Point = { x: paper(width), y: paper(height) };
  const bottomLeft: Point = { x: "0", y: paper(height) };

  // Walls are named by the side they sit on, south at the top of the sheet,
  // because that is the convention the brief uses when it says "the south wall".
  const walls: Wall[] = [
    {
      id: newId(),
      start: origin,
      end: topRight,
      thickness_mm: paper(thickness),
    },
    {
      id: newId(),
      start: bottomLeft,
      end: bottomRight,
      thickness_mm: paper(thickness),
    },
    {
      id: newId(),
      start: origin,
      end: bottomLeft,
      thickness_mm: paper(thickness),
    },
    {
      id: newId(),
      start: topRight,
      end: bottomRight,
      thickness_mm: paper(thickness),
    },
  ];

  const bySide: Record<string, Wall> = {
    south: walls[0],
    north: walls[1],
    west: walls[2],
    east: walls[3],
  };

  const openings = [...exercise.door_requirements, ...exercise.window_requirements]
    .filter((requirement) => requirement.wall && bySide[requirement.wall])
    .flatMap((requirement) => {
      const wall = bySide[requirement.wall!];
      const drawnWidth = toPaperMm(requirement.width_mm, scale);
      const wallLength = Math.hypot(
        Number(wall.end.x) - Number(wall.start.x),
        Number(wall.end.y) - Number(wall.start.y),
      );
      // The brief fixes how many and how wide, never where. Spreading them
      // evenly with equal end gaps is one arbitrary-but-neat choice; `count`
      // is respected because the brief's count is part of the brief.
      const count = Math.max(1, requirement.count);
      const gap = (wallLength - drawnWidth * count) / (count + 1);
      return Array.from({ length: count }, (_, index) => ({
        host_wall_id: wall.id,
        offset_mm: paper(gap * (index + 1) + drawnWidth * index),
        width_mm: paper(drawnWidth),
        kind: requirement.kind,
      }));
    });

  // A dimension is a line plus the value the student claims it measures. The
  // engine works out which axis it spans by measuring the line, so `axis` is
  // not sent: sending it would let the client assert something the server
  // derives.
  const dimensions = exercise.dimension_requirements.map((requirement) =>
    requirement.axis === "width"
      ? {
          start: { x: "0", y: paper(-10) },
          end: { x: paper(width), y: paper(-10) },
          actual_value_mm: String(requirement.value_mm),
        }
      : {
          start: { x: paper(-10), y: "0" },
          end: { x: paper(-10), y: paper(height) },
          actual_value_mm: String(requirement.value_mm),
        },
  );

  return {
    scale_denominator: scale,
    room: { boundary: [origin, topRight, bottomRight, bottomLeft] },
    walls,
    openings,
    dimensions,
  };
}

/** The bounding box of the sheet content, for fitting the preview. */
export function drawingExtent(drawing: StudentDrawing): {
  width: number;
  height: number;
} {
  const xs = drawing.room.boundary.map((point) => Number(point.x));
  const ys = drawing.room.boundary.map((point) => Number(point.y));
  return {
    width: Math.max(...xs, 0),
    height: Math.max(...ys, 0),
  };
}
