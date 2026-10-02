# ArchTutor

Drafting practice and feedback for B.Arch students. The MVP covers architectural
scale, room geometry, wall thickness, doors, windows and dimensions — and, above
all, tells a student **exactly why their drawing is wrong**.

This repository contains the whole MVP: the exercise engine, the drawing model,
the validation engine, the learning layer that turns findings into teaching, the
guarded tutor that explains them, and the web app a student uses. The tutor is
server-side and optional; with no model configured it falls back to deterministic
explanations, so the product works fully without one.

The measurement engine, geometry model and validator are all pure: no LLM, no
network, no clock, no randomness. The same submission always produces the same
findings, in the same order, which is what makes a finding something a student
can be shown and a bug can be distinguished from a mistake.

## Two rules that shape the code

1. **Deterministic code is the source of truth.** The backend calculates every
   dimension, scale conversion, coordinate, tolerance and validation result. The
   LLM receives verified results and explains them. It never computes them.
2. **Everything is millimetres.** Real-world and paper dimensions are both
   millimetres; scale is a divisor. `4200 mm at 1:50 = 84 mm`. Exercises store
   integer millimetres, and anything fractional is an exact `Decimal` -- never a
   binary float, because `0.1` is not representable and a wall thickness of
   `4.6 mm` must not become `4.5999999999999996` in transit.
3. **The student's drawing is the evidence.** It defines what exists. The exercise
   defines what was required. Neither overrides the other, and the validator never
   rewrites a submission.

## Repository layout

```
.
├── backend/                  FastAPI + Pydantic + SQLAlchemy + Alembic
│   ├── app/
│   │   ├── main.py           application factory, CORS, router registration
│   │   ├── api/              HTTP routes only — no domain logic
│   │   ├── core/             settings
│   │   ├── db/               engine, session, declarative base
│   │   ├── models/           Exercise, ExerciseAttempt
│   │   ├── schemas/          Pydantic request/response contracts
│   │   ├── measurement/      units and scale — the only place conversion happens
│   │   ├── geometry/         drawing model: points, walls, openings, rooms
│   │   ├── validation/       the deterministic validator
│   │   ├── exercises/        exercise domain logic and persistence
│   │   ├── attempts/         attempt persistence
│   │   ├── learning/         feedback, explanations, progress, taxonomy
│   │   └── tutor/            guarded explanations over verified findings
│   ├── alembic/              migrations
│   ├── scripts/              dev seed
│   └── tests/                pytest suite
├── frontend/                 Next.js (App Router) + TypeScript + Tailwind
│   ├── app/                  routes: /exercise (briefs), /drawing (workspace)
│   ├── components/           the editor, the Konva preview, issue cards
│   ├── lib/                  typed API client, editor model, drawing helpers
│   └── tests/                node:test suites, including the live vertical slice
└── README.md
```

## Prerequisites

- Python 3.12+ (developed on 3.14)
- Node.js 20+ (developed on 24)
- PostgreSQL 14+ running locally

## Setup

### 1. PostgreSQL

Create a role and two databases — one for development, one for tests:

```bash
createuser --createdb archtutor          # password: archtutor
createdb -O archtutor archtutor
createdb -O archtutor archtutor_test
```

On Homebrew macOS, if the service is not running: `brew services start postgresql@14`.

### 2. Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env

alembic upgrade head
python -m scripts.seed_dev_exercises      # 20 beginner briefs, idempotent
```

Run the API:

```bash
uvicorn app.main:app --reload --port 8000
```

- API: <http://127.0.0.1:8000>
- Docs: <http://127.0.0.1:8000/docs>

### 3. Frontend

In a second terminal:

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

- App: <http://localhost:3000>

The home page calls the backend's `GET /health` from the browser, so it is also
the connectivity check: if it reports `api: ok`, CORS and the API are both
working.

## Environment variables

`backend/.env` (see `backend/.env.example`):

| Variable | Default | Purpose |
| --- | --- | --- |
| `POSTGRES_USER` | `archtutor` | Database user |
| `POSTGRES_PASSWORD` | `archtutor` | Database password |
| `POSTGRES_HOST` | `127.0.0.1` | Database host |
| `POSTGRES_PORT` | `5432` | Database port |
| `POSTGRES_DB` | `archtutor` | Database name |
| `HOST` | `127.0.0.1` | Bind address |
| `PORT` | `8000` | Bind port |
| `CORS_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` | Allowed frontend origins |
| `TUTOR_BASE_URL` | empty | OpenAI-compatible API root, without `/chat/completions`; blank disables the tutor |
| `TUTOR_API_KEY` | empty | The provider's key. A secret: it belongs in `.env`, which git ignores, and nowhere else |
| `TUTOR_MODEL` | empty | Model id, e.g. `openai/gpt-oss-20b` on Groq |
| `TUTOR_REASONING_EFFORT` | empty | Optional `low`/`medium`/`high` for reasoning models; sent only when set, because a provider that does not know the parameter answers `400` |

`frontend/.env.local` (see `frontend/.env.example`):

| Variable | Default | Purpose |
| --- | --- | --- |
| `API_BASE_URL` | `http://127.0.0.1:8000` | Server-only base URL. The exercise pages are server components, and `app/api/[...path]/route.ts` forwards to it; it is never shipped to the browser. Must be absolute |
| `NEXT_PUBLIC_API_BASE_URL` | `http://127.0.0.1:8000` | Browser-visible base URL, baked into the bundle. Either an absolute API address, or `/api` for same-origin requests through the proxy |

Two variables rather than one, because the two sides are reached differently. A
server component needs an address the deployment can resolve — usually an
internal hostname the browser has never heard of — and a browser needs an address
it was told about. Either constant serving both is wrong in one direction or the
other. Verified by starting the app with the public URL pointed at a dead port:
the server-rendered HTML still listed the briefs, fetched over the server URL,
while the client bundle carried the public one.

A relative `NEXT_PUBLIC_API_BASE_URL` is the one value that is not a URL. Set it
to `/api` and the browser sends same-origin requests that
`app/api/[...path]/route.ts` forwards to `API_BASE_URL`, which is what makes the
app publishable behind a single address: the API is never exposed publicly, and
no CORS origin has to be re-allowed when a tunnel's hostname changes. The
alternative — an absolute browser URL — means the tunnel must also carry the
API, and the two have to be started, stopped, and shared together. The mount
point is named in configuration rather than hard-coded in the client, because a
relative base with no path asks for `/exercises`, which the web app 404s.

No `.env` file is committed. The database password is never written into
`alembic.ini`; migrations read it from application settings so the app and the
migrations cannot disagree about the target database.

## Sharing the app

Both services bind to loopback, so nothing is reachable off the machine until
something publishes it. The backend has no authentication, which is fine on
loopback and a problem on a public address: any visitor can ask the tutor
questions, and each question costs a provider call. Anything shared is therefore
temporary, and worth stopping when the demo ends.

Build before sharing. `next dev` recompiles on demand, and a tunnel will happily
forward a request to a server that is still compiling.

```bash
cd frontend
NEXT_PUBLIC_API_BASE_URL=/api npm run build   # bake the same-origin base in
npm start                                      # production server on :3000
ngrok http 3000                                # print the https://…-ngrok-free.dev URL
```

With `NEXT_PUBLIC_API_BASE_URL=/api` the tunnel carries only this app. A visitor
needs no second hostname and no CORS change, which matters because the free
ngrok hostname is a new random one on every restart — an absolute browser URL
would need a matching `CORS_ORIGINS` entry for a name that does not exist yet.
ngrok also serves a one-time "you are about to visit" warning page to a new
browser; after one click the cookie lets the session through.

## Database

Two tables, both created by Alembic:

- **`exercises`** — title, description, room width/height, scale denominator,
  wall thickness, door/window/dimension requirements (`JSONB`), difficulty. Enough
  to describe the north-star exercise: *draw a 4200 × 3600 mm room at 1:50, 230 mm
  walls, one 900 mm door, dimensioned.*
- **`exercise_attempts`** — the student's submitted geometry (`JSONB`), the
  validation result (`JSONB`), and `submitted_at`.

`scale_denominator` is constrained to `> 1`. At 1:1 the paper millimetres equal
the building millimetres, so a submission declaring 1 would satisfy any brief
whatever the geometry, and the scale check would be trivially defeated.

Geometry and validation payloads are `JSONB` on purpose. The shapes are still
moving; normalising them now would encode guesses about a domain that is not
finished. PostGIS is not used — an exercise is a handful of wall segments.

New migration after changing a model:

```bash
cd backend
alembic revision --autogenerate -m "describe the change"
alembic upgrade head
```

## API

| Method | Path | Status |
| --- | --- | --- |
| `GET` | `/health` | `200` when the API and database are both up, `503` otherwise |
| `GET` | `/exercises` | `200` — `{ items, total }` |
| `GET` | `/exercises/{id}` | `200`, `404` if unknown |
| `POST` | `/exercises/{id}/validate` | `200` — grade without storing, with the same `issues` an attempt returns |
| `POST` | `/exercises/{id}/attempts` | `201` — grade and store |
| `GET` | `/exercises/{id}/attempts` | `200` — newest first |
| `POST` | `/exercises/{id}/attempts/{attempt_id}/explain` | `200` — explain one issue from a stored attempt |
| `GET` | `/exercises/{id}/summary` | `200` — attempts, categories, completion, concepts |

Every path returns `404` if the exercise does not exist. `explain` returns `404`
if the attempt is not one of that exercise's, or the issue index is out of range,
and `422` if the index is not a plausible one at all.

### Submitting a drawing

`geometry` is the drawing itself, in **paper millimetres** at the student's
declared scale. Walls carry an explicit `id` because an opening references its
host wall by id. Opening ids are optional and derived from content when omitted,
so a submission without them still reproduces exactly.

```bash
curl -s -X POST http://127.0.0.1:8000/exercises/$ID/validate \
  -H 'Content-Type: application/json' \
  -d '{"geometry": {
        "scale_denominator": 50,
        "room": {"boundary": [
          {"x": "0", "y": "0"}, {"x": "84", "y": "0"},
          {"x": "84", "y": "72"}, {"x": "0", "y": "72"}]},
        "walls": [
          {"id": "…01", "start": {"x": "0", "y": "0"},
           "end": {"x": "84", "y": "0"}, "thickness_mm": "4.6"},
          {"id": "…02", "start": {"x": "0", "y": "72"},
           "end": {"x": "84", "y": "72"}, "thickness_mm": "4.6"},
          {"id": "…03", "start": {"x": "0", "y": "0"},
           "end": {"x": "0", "y": "72"}, "thickness_mm": "4.6"},
          {"id": "…04", "start": {"x": "84", "y": "0"},
           "end": {"x": "84", "y": "72"}, "thickness_mm": "4.6"}],
        "openings": [
          {"host_wall_id": "…01", "offset_mm": "30",
           "width_mm": "18", "kind": "door"}],
        "dimensions": [
          {"start": {"x": "0", "y": "-10"}, "end": {"x": "84", "y": "-10"},
           "actual_value_mm": "4200"},
          {"start": {"x": "-10", "y": "0"}, "end": {"x": "-10", "y": "72"},
           "actual_value_mm": "3600"}]}}'
```

That is a correct 4200 × 3600 room at 1:50 with 230 mm walls, one 900 mm door
and both dimensions, and the bedroom brief answers it with
`{"passed": true, "findings": []}`. Against the same geometry labelled 1:100
it returns `SCALE_ERROR` plus the room, wall, opening and dimension errors that
follow from drawing a 1:50 sheet and calling it 1:100.

`north` is the maximum y, `south` the minimum y, `east` the maximum x, `west` the
minimum x. A wall on the north or south boundary runs east-west and is therefore
horizontal; east and west walls are vertical.

An optional `tolerance` object loosens individual checks and is always echoed
back, so a forgiving verdict can never be mistaken for a strict one. The default
is exact — `0` on every quantity:

```json
{"geometry": {…}, "tolerance": {"wall_thickness_mm": 1}}
```

A drawing the parser cannot read is `422`, never a verdict. Reporting
`passed: true` for geometry the server rejected would tell a student their work
is correct when the server never understood it.

### Findings

Every finding is a fact, not an explanation: `code`, `severity`, `expected`,
`actual`, `difference`, `unit`, `geometry_reference`, `metadata`. `expected` and
`actual` are **paper** millimetres, because that is the number on the sheet the
student can act on; the equivalent building millimetres are in `metadata`.
Decimals serialise as strings so they survive JSON unchanged.

Codes: `SCALE_ERROR`, `ROOM_DIMENSION_ERROR`, `WALL_THICKNESS_ERROR`,
`DOOR_WIDTH_ERROR`, `DOOR_PLACEMENT_ERROR`, `WINDOW_WIDTH_ERROR`,
`OPENING_PLACEMENT_ERROR`, `DIMENSION_ERROR`, `ALIGNMENT_ERROR`,
`MISSING_ELEMENT`, `UNEXPECTED_ELEMENT`. These are part of the API contract.

Every check runs, regardless of what earlier ones found, so a drawing at the
wrong scale reports `SCALE_ERROR` *and* the room, wall, opening and dimension
errors that follow from it. A student needs every cause, not the first one
found.

A **stored attempt** returns those same findings in the learning layer's shape:
`what_is_wrong`, `where`, `expected`, `actual`, `difference`, `unit`,
`why_it_matters`, `how_to_fix` and the category it belongs to, alongside the raw
`validation_result` it was built from. The two coexist deliberately — the raw
result is the evidence, the issue is the lesson, and neither is a rewrite of the
other.

### The tutor cannot change a number

`explain` reads the stored attempt, not the live geometry, so the explanation
always matches the verdict on screen. The model is given the verified figures and
is told to compute nothing; whatever it returns is then checked against the
figures the validator produced. A single unverified number discards the whole
answer and the deterministic explanation is served instead, with
`blocked_numbers` saying which figures were rejected. The endpoint is
synchronous with an 8-second timeout for the same reason: an explanation is part
of the loop, not a background job.

This project is developed against [Groq](https://console.groq.com), which serves
an OpenAI-compatible API, so no SDK is involved:

```bash
TUTOR_BASE_URL=https://api.groq.com/openai/v1
TUTOR_API_KEY=gsk_...
TUTOR_MODEL=openai/gpt-oss-20b
TUTOR_REASONING_EFFORT=low
```

`openai/gpt-oss-120b` and `qwen/qwen3.8-27b` were also measured on the same
account and work unchanged; the model is one line of configuration. Measured
latency for one explanation, synchronously, with `reasoning_effort: low`, was
0.6-0.8s — comfortably inside the 8-second budget, which is the point of asking
a small model to describe a finding the validator has already computed.

`reasoning_effort` is worth setting on a reasoning model. Measured on
`gpt-oss-20b`, one explanation cost 352 completion tokens and about a second
with the default effort, and 141 tokens and 0.7s at `low` — and a response that
spends its whole budget thinking returns no prose at all. Both cases still
resolve to the deterministic explanation rather than to an error: a model that
answers with nothing, or with a number the validator never produced, is a
provider problem the student should never see.

### Scale is measured, not trusted

A declared scale is a label. The validator derives the scale the sheet was
actually drawn at and compares it to the label, because "the geometry is right
but the title block says 1:100" and "the whole sheet is drawn at 1:100" are
different mistakes and only one of them is a drawing error:

| Drawn at | Labelled | Finding |
| --- | --- | --- |
| 1:50 | 1:50 | passes |
| 1:100 | 1:50 | `drawn at 1:100` — the sheet is half size |
| 1:50 | 1:100 | `not the 1:100 it is labelled` — correct work, wrong title block |
| 1:100 | 1:100 | `the brief requires 1:50` — honest, and still wrong |
| 1:60 | 1:50 | `drawn at 1:60` — an unusual scale is reported, never rejected |
| 1:60 wide, 1:50 tall | 1:50 | no scale finding — the sheet has no single scale |
| no scale fits | 1:50 | no scale finding — the room check reports the real problem |

The last two rows matter. A scale is a property of the whole sheet, so it is
only named when the width *and* the height imply the same denominator. A sheet
70 mm wide and 72 mm tall is 1:60 one way and 1:50 the other; it is not at
1:60, and sending a student to "draw at 1:60" would not make the 72 mm height
correct. When the axes disagree, or when no denominator reproduces the sheet at
all, the check stays silent instead of inventing a cause, and
`ROOM_DIMENSION_ERROR` says exactly what is wrong.

Interactive docs: <http://127.0.0.1:8000/docs>

## The vertical slice

One loop, in this order, and nothing in the product runs out of order:

1. **Brief.** `/exercise` lists the seeded briefs with their room, scale and
   walls. Choosing one opens `/drawing?exercise=<id>`.
2. **Draw.** The editor is parametric: room size on the sheet, wall thickness,
   each opening's kind, wall, width and offset, and the value written on each
   dimension line. The Konva preview draws what has been entered, and the scale
   can be set to something wrong on purpose — that is a mistake the exercise
   exists to catch.
3. **Check.** "Check" grades the drawing and stores nothing. It returns the
   engine's findings — a code, a sentence, and expected/actual/difference in
   millimetres — *and* the same seven-field issues a stored attempt returns, so
   checking teaches exactly as much as submitting. The two are compared field by
   field in the tests, because a student who is told one thing while checking
   and something vaguer after submitting has been misled. While the sheet is
   still missing a room, both actions stay disabled rather than sending a
   drawing the engine cannot measure.
4. **Explain.** "Submit attempt" stores the same verdict and returns the
   learning layer's version of it — seven facts per issue (what, where,
   expected, actual, difference, why, how) plus what changed since the previous
   attempt. Each issue has **Explain this**, which reads the *stored* result, so
   the explanation always matches the attempt on screen.
5. **Correct and re-check.** Fix the numbers and submit again. Progress reports
   resolved, changed and new mistakes separately: a mistake that moved is not
   credited as fixed.
6. **Complete.** A passing attempt records completion, and the summary lists what
   the brief's requirements mean the student has now demonstrated.

Every number the student is judged on is calculated by the backend. The
frontend's arithmetic is limited to converting a brief figure into the size to
draw (`actual / denominator`), always shown next to the brief so it can be
checked, and to formatting.

## Testing

```bash
cd backend
source .venv/bin/activate
POSTGRES_DB=archtutor_test pytest
```

Tests run against a real PostgreSQL database, not SQLite — the models use `JSONB`
and Postgres-native enums, and a SQLite shim would compile to something the
application never runs against. The suite drops and recreates the schema in
`archtutor_test` for each test, so point `POSTGRES_DB` somewhere disposable.

If PostgreSQL is unreachable the suite skips with an explicit reason rather than
passing vacuously.

Two invariants are worth calling out, because they are the ones a refactor would
break first:

- **Reproducibility.** The same exercise, drawing and tolerance must serialise to
  identical bytes every time. That is why omitted opening ids are derived from
  content rather than generated.
- **Every brief is satisfiable.** Each seeded brief is checked against a drawing
  that satisfies it, which must pass with zero findings, and against the same
  drawing relabelled at the wrong scale, which must fail. A brief no drawing could
  satisfy is indistinguishable from a stuck student.

Frontend:

```bash
cd frontend
npm test             # node:test, no framework dependency
npm run test:browser # opt-in: a real Chrome, driven over CDP
npm run lint
npm run typecheck
npm run build
```

`npm test` runs four suites. `tests/editor.test.mts` covers the conversions that
turn typed input into geometry — the scale arithmetic, blank fields, opening
counts, wall references, and UUIDs the backend will accept. `tests/api.test.mts`
covers the client's own contract with the network: which base URL each side uses,
and what a student is told when the API is unreachable, when a request fails, or
when the server rejects a payload. `tests/vertical-slice.test.mts`
walks the whole loop over HTTP against a running API and a real database: brief,
a wrong drawing, a check that teaches, an explanation, a correction, a
completion. It skips, loudly, when no API is reachable, so a unit run is never a
false pass.

To run it against the API:

```bash
cd backend && .venv/bin/uvicorn app.main:app --port 8000
cd frontend && npm test            # ARCHTUTOR_API_URL overrides the default
```

`tests/browser-e2e.test.mts` is the one suite that clicks. It drives Chrome over
the DevTools Protocol using Node's own WebSocket — no automation dependency, and
no browser download for anyone who does not want one — and it does the parts
nothing else can: types into a controlled input, checks the Konva stage actually
painted, and asserts a check teaches, an attempt stores, an explanation arrives,
and a fix completes. It is opt-in so that `npm test` stays runnable without a
browser; when it is asked for explicitly, a missing server fails the run rather
than skipping it.

```bash
cd backend && .venv/bin/uvicorn app.main:app --port 8000
cd frontend && npm run dev
cd frontend && npm run test:browser  # CHROME_PATH overrides the browser
```

It writes real attempts to whatever exercise it picks, exactly as a student
would, and skips only when no browser is installed.

## Not in this version

Deliberately absent, and not to be added without a decision: 3D, BIM, IFC,
climate/wind/solar analysis, sciography, OCR, computer vision, automatic
floor-plan recognition, construction-system analysis, a standards database,
collaboration, payments, social features, gamification, authentication,
microservices, Kubernetes, Redis, background workers, and generic chat.

The drawing model is **structured and parametric**, not freehand: a student
defines wall segments and openings, and the backend reads the model. Freehand
strokes cannot yield a wall thickness deterministically without computer vision,
which is out of scope. The editor therefore follows the backend's model, not the
other way round.

## Built so far

- `app/measurement` — units and scale. The only place conversion happens.
- `app/geometry` — the drawing model: points, walls, openings hosted on a wall,
  rectangular rooms, dimensions.
- `app/validation` — scale, room, walls, openings, dimensions and alignment, with
  structured findings under stable codes and a configurable tolerance.
- `app/learning` — findings turned into teaching: the seven-field issue, a
  stable identity per mistake, a resolved/changed/new diff between attempts, and
  the concepts a completed exercise demonstrates.
- `app/exercises`, `app/attempts` — persistence for briefs, submissions and
  progress, with attempt numbering serialised per exercise.
- `app/tutor` — explanations over verified findings, guarded so a model that
  states an unverified figure has its whole answer discarded in favour of the
  deterministic one.
- `app/api` — list/get exercises, grade a drawing, record an attempt, explain an
  issue, summarise an exercise.
- `frontend` — the parametric editor, the Konva preview, issue cards, the retry
  diff and the completion panel.

## Next

1. **Students.** Nothing else is planned until the loop has been used by someone
   learning to draft, and the notes on what they reach for first are in.
2. A browser-level end-to-end test. The slice is covered at the API boundary and
   the geometry conversions are unit-tested; the click-through itself is checked
   by hand.
3. Authentication, only if a student needs their history to follow them across
   devices. Until then there is nothing to authenticate.
