/**
 * Typed client for the ArchTutor API.
 *
 * Mirrors the backend Pydantic contracts in `backend/app/schemas/`. Dimensions
 * are millimetres everywhere, matching the UNIT PRINCIPLE: the frontend never
 * converts units either, so there is no second implementation of the scale
 * arithmetic to drift out of sync with the backend.
 *
 * One rule is worth stating explicitly, because it is the one this file exists
 * to protect: numbers are STRINGS on the wire. The backend measures in exact
 * `Decimal`, and `84.0` is not the same fact as `84`. A JavaScript number would
 * round that away the moment it crossed the network, and a validator that
 * disagrees with itself by a hundredth of a millimetre cannot be trusted to
 * mark a drawing. So every quantity here stays a string and is only ever
 * displayed, never computed on.
 *
 * Two base URLs, not one. The exercise pages are server components, so the
 * server needs to reach the API from inside the deployment, where the API is
 * usually an internal hostname that the browser has never heard of. The
 * browser needs a URL it can be told about, which means a `NEXT_PUBLIC_`
 * variable baked into the bundle. One constant for both is wrong in each
 * direction: it either leaks a server address to the client or makes a
 * server-rendered page call the public hostname it was served from.
 */

const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000";

export interface ApiBaseUrls {
  /** What the browser fetches from. May be relative, e.g. "/api". */
  browser: string;
  /** What a server component fetches from. Always absolute. */
  server: string;
}

/**
 * Work out both base URLs from the environment.
 *
 * Exported as a pure function of its arguments so the rule is testable without
 * a bundler: a module-level constant is fixed at import time, and a test that
 * cannot vary its input can only assert whatever the machine running it happens
 * to have configured. Trailing slashes are removed because the request paths
 * already begin with one, and `http://api:8000//health` is a 404 on some
 * proxies and a redirect on others.
 *
 * The browser URL may be *relative*, and the form to reach for is the proxy's own
 * mount point:
 *
 *   http://127.0.0.1:8000   the browser calls the API directly, so the API must
 *                           be reachable from the browser and allowed by CORS.
 *   /api                    the browser calls this site's own origin, and
 *                           `app/api/[...path]/route.ts` forwards to the API
 *                           server-side.
 *
 * The second is what makes the app publishable behind a single address: the API
 * is never exposed publicly, and no CORS origin has to be re-allowed when a
 * tunnel's hostname changes on every restart. Naming the mount point in
 * configuration rather than in the client is the point -- the alternative is a
 * relative base with no path, which asks for `/exercises` and gets a 404 from
 * the web app.
 *
 * The server URL must be absolute, since a server-side `fetch` of a relative path
 * has nothing to resolve it against. A relative browser URL therefore never
 * becomes the server URL, whatever else is configured.
 */
export function resolveApiBaseUrls(
  publicUrl: string | undefined,
  serverUrl: string | undefined,
  fallback: string = DEFAULT_API_BASE_URL,
): ApiBaseUrls {
  const trim = (url: string) => url.replace(/\/+$/, "");
  const browser = trim(publicUrl?.trim() || fallback);
  const absolute = (url: string) => /^https?:\/\//i.test(url);
  const fromServer = trim(serverUrl?.trim() || "");
  const server = absolute(fromServer)
    ? fromServer
    : absolute(browser)
      ? browser
      : trim(fallback);
  return { browser, server };
}

const baseUrls = resolveApiBaseUrls(
  process.env.NEXT_PUBLIC_API_BASE_URL,
  process.env.API_BASE_URL,
);

export const API_BASE_URL = baseUrls.browser;
export const serverApiBaseUrl = baseUrls.server;

/** The base URL for the environment the call is running in. */
export function apiBaseUrl(isServer: boolean): string {
  return isServer ? serverApiBaseUrl : API_BASE_URL;
}

export type Difficulty = "beginner" | "intermediate";

export type WallSide = "north" | "south" | "east" | "west";

export interface OpeningRequirement {
  kind: "door" | "window";
  width_mm: number;
  count: number;
  wall: WallSide | null;
  offset_mm: number | null;
  sill_height_mm: number | null;
  notes: string | null;
}

export interface DimensionRequirement {
  axis: "width" | "height";
  value_mm: number;
  on_wall: WallSide | null;
  label: string | null;
}

export interface Exercise {
  slug: string;
  title: string;
  description: string | null;
  room_width_mm: number;
  room_height_mm: number;
  wall_thickness_mm: number;
  scale_denominator: number;
  door_requirements: OpeningRequirement[];
  window_requirements: OpeningRequirement[];
  dimension_requirements: DimensionRequirement[];
  difficulty: Difficulty;
  id: string;
  created_at: string;
}

export interface ExerciseList {
  items: Exercise[];
  total: number;
}

export interface Health {
  status: string;
  database: string;
  version: string;
}

// --- The drawing ---------------------------------------------------------

/** A point on the sheet, in millimetres of paper. */
export interface Point {
  x: string;
  y: string;
}

export interface Wall {
  id: string;
  start: Point;
  end: Point;
  thickness_mm: string;
}

export interface Opening {
  id?: string;
  host_wall_id: string;
  offset_mm: string;
  width_mm: string;
  kind: "door" | "window";
}

export interface Dimension {
  start: Point;
  end: Point;
  actual_value_mm: string;
}

export interface StudentDrawing {
  scale_denominator: number;
  room: { boundary: Point[] };
  walls: Wall[];
  openings: Opening[];
  dimensions: Dimension[];
}

// --- Feedback ------------------------------------------------------------

/**
 * One mistake, in the form the student reads it.
 *
 * The seven facts a student needs are separate fields, never a pre-rendered
 * sentence. A card that composes its own prose in the backend cannot be quoted,
 * tested or reused in the tutor panel, and a11y tools cannot read it.
 */
export interface Issue {
  code: string;
  category: string;
  category_label: string;
  severity: "ERROR" | "WARNING";
  what_is_wrong: string;
  where: string;
  expected: string | number | null;
  actual: string | number | null;
  difference: string | number | null;
  unit: string;
  why_it_matters: string;
  how_to_fix: string[];
  geometry_reference: string | null;
  metadata: Record<string, unknown>;
}

/** How this attempt compares with the one before it. */
export interface Progress {
  attempt_number: number;
  passed: boolean;
  completed: boolean;
  is_first_attempt: boolean;
  improved: boolean;
  remaining_count: number;
  resolved_count: number;
  new_count: number;
  changed_count: number;
  remaining: Issue[];
  resolved: Issue[];
  new: Issue[];
  changed: Issue[];
}

export interface Learning {
  categories: Record<string, number>;
  category_count: number;
  primary_category: string | null;
}

export interface ValidationSummary {
  total: number;
  error_count: number;
  warning_count: number;
}

/** One finding exactly as the engine produced it: a fact and nothing else. */
export interface Finding {
  code: string;
  severity: "ERROR" | "WARNING";
  message: string;
  expected: string | number | null;
  actual: string | number | null;
  difference: string | number | null;
  unit: string;
  geometry_reference: string | null;
  metadata: Record<string, unknown>;
}

/**
 * What `/validate` returns.
 *
 * The engine's own shape, not the presented shape. A dry run is a measurement
 * and nothing more: it carries no WHY or HOW, because presenting it is the
 * learning layer's job and that layer reads stored attempts. The engine's
 * `message` is still a complete sentence, so a dry run is never a bare code.
 */
export interface EngineResult {
  exercise_id: string;
  passed: boolean;
  findings: Finding[];
  /** The same findings as the learning layer's issues, which is what a stored
   *  attempt returns. Present on a dry run so checking teaches as much as
   *  submitting does. */
  issues: Issue[];
  summary: ValidationSummary;
  scale_denominator: number;
  tolerance: Record<string, string>;
}

export interface Attempt {
  id: string;
  exercise_id: string;
  attempt_number: number;
  previous_attempt_id: string | null;
  student_geometry: StudentDrawing;
  /** The raw stored result, in the engine's shape. */
  validation_result: EngineResult;
  learning: Learning;
  progress: Progress;
  completed: boolean;
  submitted_at: string;
  completed_at: string | null;
}

export interface TutorExplanation {
  explanation: string;
  source: "llm" | "deterministic";
  blocked_numbers: string[];
  model: string | null;
  latency_ms: number | null;
}

export interface ExplainResponse {
  attempt_id: string;
  issue_index: number;
  issue: Issue;
  tutor: TutorExplanation;
}

export interface ExerciseSummary {
  exercise_id: string;
  attempt_count: number;
  completed: boolean;
  completion_attempt_number: number | null;
  category_totals: Record<string, number>;
  resolved_totals: Record<string, number>;
  first_attempt_error_count: number | null;
  final_error_count: number | null;
  /** What a pass demonstrated, taken from the brief. Every entry is a fact the
   *  validator confirmed, so the completion screen states it rather than
   *  inventing praise. */
  concepts: string[];
}

export class ApiError extends Error {
  readonly status: number;
  /** The server's correlation id, so a student can quote it in a report. */
  readonly requestId: string | null;

  constructor(status: number, message: string, requestId: string | null = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.requestId = requestId;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const base = apiBaseUrl(typeof window === "undefined");
  let response: Response;
  try {
    response = await fetch(`${base}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
      cache: "no-store",
    });
  } catch {
    throw new ApiError(
      0,
      /^https?:\/\//i.test(base)
        ? `Cannot reach the ArchTutor API at ${base}. Is the backend running?`
        : // A relative base is this site's own proxy, so naming the path would
          // tell the student nothing they can act on. Name the moving part.
          "Cannot reach the ArchTutor API through this site. Is the backend running?",
    );
  }

  if (!response.ok) {
    // The server returns `detail`, and on an unexpected failure a `request_id`.
    // Both are surfaced: a student pasting the id lets an operator find the
    // exact failing request in the logs.
    let message = `${response.status} ${response.statusText}`;
    let requestId: string | null = response.headers.get("x-request-id");
    try {
      const body = (await response.json()) as {
        detail?: string | { loc?: unknown[]; msg?: string }[];
        request_id?: string;
      };
      if (typeof body.detail === "string") {
        message = body.detail;
      } else if (Array.isArray(body.detail) && body.detail.length > 0) {
        // A schema violation arrives as a list of field errors. Rendered as an
        // object it would read "[object Object]", which tells a student nothing.
        message = body.detail
          .map((entry) => {
            const field = Array.isArray(entry.loc) ? entry.loc.join(".") : "";
            return field ? `${field}: ${entry.msg ?? "invalid"}` : (entry.msg ?? "invalid");
          })
          .join("; ");
      }
      if (body.request_id) {
        requestId = body.request_id;
      }
    } catch {
      // A non-JSON error body (a proxy, say) leaves the status line as the
      // message, which is still better than a JSON parse error.
    }
    throw new ApiError(response.status, message, requestId);
  }
  return (await response.json()) as T;
}

export const api = {
  health: () => request<Health>("/health"),
  listExercises: () => request<ExerciseList>("/exercises"),
  getExercise: (id: string) => request<Exercise>(`/exercises/${id}`),

  /** Validate without storing. Nothing is persisted, so this is safe to call
   *  as often as the student likes. */
  validate: (exerciseId: string, geometry: StudentDrawing) =>
    request<EngineResult>(`/exercises/${exerciseId}/validate`, {
      method: "POST",
      body: JSON.stringify({ geometry }),
    }),

  /** Check and store. This is what advances the retry loop. */
  submitAttempt: (exerciseId: string, geometry: StudentDrawing) =>
    request<Attempt>(`/exercises/${exerciseId}/attempts`, {
      method: "POST",
      body: JSON.stringify({ geometry }),
    }),

  listAttempts: (exerciseId: string) =>
    request<Attempt[]>(`/exercises/${exerciseId}/attempts`),

  /** Ask the tutor about one issue from a stored attempt. */
  explain: (exerciseId: string, attemptId: string, issueIndex: number) =>
    request<ExplainResponse>(`/exercises/${exerciseId}/attempts/${attemptId}/explain`, {
      method: "POST",
      body: JSON.stringify({ issue_index: issueIndex }),
    }),

  summary: (exerciseId: string) =>
    request<ExerciseSummary>(`/exercises/${exerciseId}/summary`),
};
