"use client";

import { useMemo } from "react";
import {
  Arrow,
  Circle,
  Group,
  Label,
  Layer,
  Line,
  Rect,
  Stage,
  Tag,
  Text,
} from "react-konva";

import type { Point, StudentDrawing, WallSide } from "@/lib/api";

/**
 * The drawing preview.
 *
 * Konva is the drawing engine, per the constitution: this component renders what
 * the student has entered and nothing else. It performs no measurement and no
 * scale conversion of its own -- the millimetres it receives are already
 * millimetres of paper, and `app/measurement` on the server is the only place
 * that converts. The one thing computed here is the pixel-per-millimetre factor
 * that fits the sheet into the stage, which is presentation, not measurement.
 *
 * Every figure is drawn as entered, including figures the student knows are
 * wrong. Colour answers "where is the problem", never "is this right":
 * highlighting comes from the selected issue's `geometry_reference`, so the
 * preview points at what the validator complained about instead of second-
 * guessing it.
 */

const WIDTH = 760;
const HEIGHT = 520;
const PADDING = 28;
const GRID_MM = 10;
const MAJOR_GRID_MM = 50;

const INK = "#1c1917";
const PAPER = "#fafaf9";
const GRID = "#e7e5e4";
const GRID_MAJOR = "#d6d3d1";
const WALL = "#292524";
const STRONG = "#dc2626";
const SOFT = "#f59e0b";

/** How loudly an element is marked: the selected issue, a hovered one, or none. */
type Mark = "strong" | "soft" | "none";

const MARK_COLOUR: Record<Mark, string> = {
  strong: STRONG,
  soft: SOFT,
  none: INK,
};

function number(value: string | number): number {
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function distance(a: Point, b: Point): number {
  return Math.hypot(number(b.x) - number(a.x), number(b.y) - number(a.y));
}

/**
 * What a `geometry_reference` points at.
 *
 * The engine refers to geometry in several ways depending on the check: a wall
 * by its stored id for a thickness error, by its side for an alignment error, an
 * opening by id or by kind, a dimension line by axis or by its start point, a
 * corner by coordinates. All of them are handled here so the preview can point at
 * whichever one the student selected, and an unrecognised reference highlights
 * nothing rather than highlighting the wrong thing.
 */
function referenceMatcher(reference: string | null | undefined) {
  if (!reference) {
    return () => "none" as Mark;
  }
  const [kind, ...rest] = reference.split(":");
  const key = rest.join(":");

  return (candidate: {
    id?: string;
    side?: WallSide;
    kind?: string;
    axis?: string;
    point?: { x: number; y: number };
  }): Mark => {
    if ((kind === "room" || kind === "drawing") && key === "") {
      return "strong";
    }
    if (candidate.id !== undefined && key === candidate.id) {
      return "strong";
    }
    if (kind === "wall" && candidate.side !== undefined && key === candidate.side) {
      return "strong";
    }
    if (
      (kind === "door" || kind === "window") &&
      candidate.kind === kind &&
      key === ""
    ) {
      return "strong";
    }
    if (
      kind === "dimension" &&
      candidate.axis !== undefined &&
      key === candidate.axis
    ) {
      return "strong";
    }
    if (kind === "corner" && candidate.point) {
      const [x, y] = key.split(",").map(Number);
      if (x === candidate.point.x && y === candidate.point.y) {
        return "strong";
      }
    }
    return "none";
  };
}

export interface KonvaStageProps {
  drawing: StudentDrawing;
  /** A `geometry_reference` from the selected issue, pointed at in red. */
  highlight?: string | null;
  /** A `geometry_reference` from a hovered issue, pointed at in amber. */
  softHighlight?: string | null;
}

export function KonvaStage({ drawing, highlight, softHighlight }: KonvaStageProps) {
  const view = useMemo(() => {
    const xs = drawing.room.boundary.map((point) => number(point.x));
    const ys = drawing.room.boundary.map((point) => number(point.y));
    const thickness = Math.max(
      ...drawing.walls.map((wall) => number(wall.thickness_mm)),
      0,
    );
    // Dimension lines sit 10 mm off the sheet, so the margin has to clear them
    // as well as the walls, or a correct answer's label gets clipped.
    const margin = Math.max(20, thickness * 2);

    const minX = Math.min(...xs, 0) - margin;
    const minY = Math.min(...ys, 0) - margin;
    const maxX = Math.max(...xs, 0) + margin;
    const maxY = Math.max(...ys, 0) + margin;
    const spanX = Math.max(maxX - minX, 1);
    const spanY = Math.max(maxY - minY, 1);
    const pxPerMm = Math.min(
      (WIDTH - PADDING * 2) / spanX,
      (HEIGHT - PADDING * 2) / spanY,
    );

    return {
      spanX,
      spanY,
      minX,
      minY,
      pxPerMm,
      x: (value: string | number) => PADDING + (number(value) - minX) * pxPerMm,
      y: (value: string | number) => PADDING + (number(value) - minY) * pxPerMm,
    };
  }, [drawing]);

  const project = view;

  const strong = useMemo(() => referenceMatcher(highlight), [highlight]);
  const soft = useMemo(() => referenceMatcher(softHighlight), [softHighlight]);

  const gridLines = useMemo(() => {
    const lines: { points: number[]; major: boolean }[] = [];
    for (let mm = Math.floor(view.minX / MAJOR_GRID_MM) * MAJOR_GRID_MM; mm <= view.minX + view.spanX; mm += GRID_MM) {
      lines.push({
        points: [project.x(mm), project.y(view.minY), project.x(mm), project.y(view.minY + view.spanY)],
        major: mm % MAJOR_GRID_MM === 0,
      });
    }
    for (let mm = Math.floor(view.minY / MAJOR_GRID_MM) * MAJOR_GRID_MM; mm <= view.minY + view.spanY; mm += GRID_MM) {
      lines.push({
        points: [project.x(view.minX), project.y(mm), project.x(view.minX + view.spanX), project.y(mm)],
        major: mm % MAJOR_GRID_MM === 0,
      });
    }
    return lines;
  }, [project, view]);

  const boundary = drawing.room.boundary.map((point) => [
    project.x(point.x),
    project.y(point.y),
  ]);
  const boundaryPoints = boundary.flat();
  if (boundaryPoints.length >= 6) {
    boundaryPoints.push(boundaryPoints[0], boundaryPoints[1]);
  }
  const roomMark: Mark = strong({}) !== "none" ? "strong" : soft({}) !== "none" ? "soft" : "none";

  const wallsById = new Map(drawing.walls.map((wall) => [wall.id, wall]));

  return (
    <Stage
      width={WIDTH}
      height={HEIGHT}
      className="h-auto max-w-full rounded border border-neutral-200"
    >
      <Layer listening={false}>
        <Rect width={WIDTH} height={HEIGHT} fill={PAPER} />

        {gridLines.map((line, index) => (
          <Line
            key={index}
            points={line.points}
            stroke={line.major ? GRID_MAJOR : GRID}
            strokeWidth={1}
          />
        ))}

        {boundaryPoints.length >= 8 && (
          <Line
            points={boundaryPoints}
            closed
            fill="#f5f5f4"
            stroke={MARK_COLOUR[roomMark]}
            strokeWidth={roomMark === "none" ? 1.5 : 2.5}
            dash={roomMark === "none" ? undefined : [6, 4]}
          />
        )}

        {drawing.walls.map((wall) => {
          const side = sideOfWall(wall, drawing);
          const mark: Mark =
            strong({ id: wall.id, side }) !== "none"
              ? "strong"
              : soft({ id: wall.id, side }) !== "none"
                ? "soft"
                : "none";
          return (
            <Line
              key={wall.id}
              points={[
                project.x(wall.start.x),
                project.y(wall.start.y),
                project.x(wall.end.x),
                project.y(wall.end.y),
              ]}
              stroke={mark === "none" ? WALL : MARK_COLOUR[mark]}
              strokeWidth={Math.max(number(wall.thickness_mm) * project.pxPerMm, 2)}
              lineCap="butt"
            />
          );
        })}

        {drawing.openings.map((opening, index) => {
          const wall = wallsById.get(opening.host_wall_id);
          if (!wall) {
            return null;
          }
          const length = distance(wall.start, wall.end);
          if (length === 0) {
            return null;
          }
          const unitX = (number(wall.end.x) - number(wall.start.x)) / length;
          const unitY = (number(wall.end.y) - number(wall.start.y)) / length;
          const offset = number(opening.offset_mm);
          const openingWidth = number(opening.width_mm);
          const near = {
            x: number(wall.start.x) + unitX * offset,
            y: number(wall.start.y) + unitY * offset,
          };
          const far = {
            x: number(wall.start.x) + unitX * (offset + openingWidth),
            y: number(wall.start.y) + unitY * (offset + openingWidth),
          };

          const candidate = { id: opening.id, kind: opening.kind };
          const mark: Mark =
            strong(candidate) !== "none"
              ? "strong"
              : soft(candidate) !== "none"
                ? "soft"
                : "none";
          const x1 = project.x(near.x);
          const y1 = project.y(near.y);
          const x2 = project.x(far.x);
          const y2 = project.y(far.y);
          const colour = MARK_COLOUR[mark];
          const gapWidth = Math.max(number(wall.thickness_mm) * project.pxPerMm, 2) + 4;

          return (
            <Group key={opening.id ?? `opening-${index}`}>
              {/* Erased through the wall: an opening is a gap, not a mark. */}
              <Line points={[x1, y1, x2, y2]} stroke={PAPER} strokeWidth={gapWidth} lineCap="butt" />
              <Line points={[x1, y1, x2, y2]} stroke={colour} strokeWidth={2} lineCap="butt" />
              {opening.kind === "window" && (
                <Line
                  points={[
                    x1 + unitY * gapWidth * 0.4,
                    y1 - unitX * gapWidth * 0.4,
                    x2 + unitY * gapWidth * 0.4,
                    y2 - unitX * gapWidth * 0.4,
                  ]}
                  stroke={colour}
                  strokeWidth={1}
                  dash={[4, 3]}
                />
              )}
              <Circle x={x1} y={y1} radius={3} fill={colour} />
              <Circle x={x2} y={y2} radius={3} fill={colour} />
              <Label x={(x1 + x2) / 2 - 45} y={(y1 + y2) / 2 - 24}>
                <Tag
                  fill={mark === "strong" ? "#fee2e2" : mark === "soft" ? "#fef3c7" : "#ffffff"}
                  stroke={mark === "none" ? GRID_MAJOR : colour}
                />
                <Text
                  text={`${opening.kind} ${openingWidth} mm`}
                  fontSize={11}
                  fill={colour}
                  padding={3}
                  width={90}
                  align="center"
                />
              </Label>
            </Group>
          );
        })}

        {drawing.dimensions.map((dimension, index) => {
          const horizontal = dimension.start.y === dimension.end.y;
          const axis = horizontal ? "width" : "height";
          const candidate = {
            axis,
            point: {
              x: Number(dimension.start.x),
              y: Number(dimension.start.y),
            },
          };
          const mark: Mark =
            strong(candidate) !== "none"
              ? "strong"
              : soft(candidate) !== "none"
                ? "soft"
                : "none";
          const x1 = project.x(dimension.start.x);
          const y1 = project.y(dimension.start.y);
          const x2 = project.x(dimension.end.x);
          const y2 = project.y(dimension.end.y);
          const colour = mark === "none" ? "#2563eb" : MARK_COLOUR[mark];
          const angle = (Math.atan2(y2 - y1, x2 - x1) * 180) / Math.PI;
          const tick = 6;

          return (
            <Group key={`dimension-${index}`}>
              <Line points={[x1, y1, x2, y2]} stroke={colour} strokeWidth={1.5} />
              <Line points={[x1, y1 - tick, x1, y1 + tick]} stroke={colour} strokeWidth={1.5} />
              <Line points={[x2, y2 - tick, x2, y2 + tick]} stroke={colour} strokeWidth={1.5} />
              <Arrow
                points={[x1, y1, x2, y2]}
                pointerLength={7}
                pointerWidth={7}
                fill={colour}
                stroke={colour}
                strokeWidth={1}
              />
              <Label
                x={(x1 + x2) / 2 - 45}
                y={(y1 + y2) / 2 - 24}
                rotation={angle}
                offsetX={45}
                offsetY={12}
              >
                <Tag
                  fill={mark === "strong" ? "#fee2e2" : mark === "soft" ? "#fef3c7" : "#eff6ff"}
                  stroke={mark === "none" ? "#bfdbfe" : colour}
                />
                <Text
                  text={`${dimension.actual_value_mm} mm`}
                  fontSize={11}
                  fill={colour}
                  padding={3}
                  width={90}
                  align="center"
                />
              </Label>
            </Group>
          );
        })}

        {drawing.room.boundary.map((point, index) => {
          const mark: Mark =
            strong({ point: { x: Number(point.x), y: Number(point.y) } }) !== "none"
              ? "strong"
              : soft({ point: { x: Number(point.x), y: Number(point.y) } }) !== "none"
                ? "soft"
                : "none";
          if (mark === "none") {
            return null;
          }
          return (
            <Circle
              key={`corner-${index}`}
              x={project.x(point.x)}
              y={project.y(point.y)}
              radius={7}
              stroke={MARK_COLOUR[mark]}
              strokeWidth={2}
            />
          );
        })}

        <Text
          x={PADDING}
          y={HEIGHT - 20}
          text={`Sheet: mm at 1:${drawing.scale_denominator} · grid ${GRID_MM} mm`}
          fontSize={11}
          fill="#78716c"
        />
      </Layer>
    </Stage>
  );
}

/**
 * Which side of the room a wall sits on, for a highlight that names a side.
 *
 * The same convention the backend uses: north is maximum y, south is minimum y,
 * east is maximum x, west is minimum x. A side is only reported when the wall
 * is axis-aligned and on that boundary, so a wall that is nowhere near a side is
 * named as nothing rather than guessed at.
 */
function sideOfWall(
  wall: { start: Point; end: Point },
  drawing: StudentDrawing,
): WallSide | undefined {
  const xs = drawing.room.boundary.map((point) => number(point.x));
  const ys = drawing.room.boundary.map((point) => number(point.y));
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const { start, end } = wall;
  const startX = number(start.x);
  const startY = number(start.y);
  const endY = number(end.y);
  const horizontal = startY === endY;

  if (horizontal && startY === minY) return "south";
  if (horizontal && startY === maxY) return "north";
  if (!horizontal && startX === minX) return "west";
  if (!horizontal && startX === maxX) return "east";
  return undefined;
}
