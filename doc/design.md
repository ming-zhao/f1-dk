# Design — how the code is organised

Companion to [`data.md`](data.md). That file documents **what the data is**; this one
documents **what the code is**: the modules, what each owns, how they depend on each other,
and the decisions that would otherwise get re-litigated.

For work still outstanding see [`refactor-plan.md`](refactor-plan.md).

---

## 1. Shape of the project

```
src/
├── data/     crawl external sources → data/raw/<source>/<year>/
├── util/     shared name/id mappings, paths, DK API access
├── sim/      DK scoring of real races + value analysis
└── vis/      race replay: fetch feeds → build frames → render a page
dashboard/    the lineup dashboard (index.html) + generated replay pages
config/       hand-maintained scoring rules and race-week notes
doc/          this file, data.md, dashboard.md, simulation*.md
skill/        operational checklists (how to fetch, how to rebuild)
```

About 3,200 lines of Python plus 755 lines of JavaScript in `src/`, and a further 1,368
lines of JavaScript inside `dashboard/index.html`.

## 2. Dependency direction

Dependencies point **inwards to `util`, never sideways**:

```
data/ ──┐
sim/  ──┼──> util/          data/_http is the one shared exception (vis/race uses it)
vis/  ──┘
```

| Module | Imports |
|---|---|
| `data/data_crawler` | `data.*`, `data._http` |
| `data/draftkings` | `util.common` |
| `sim/dk_points`, `sim/analyze` | `util.common` |
| `vis/race` | `data._http` (for the cached-fetch helper) |
| `vis/frames` | `vis.race` |
| `vis/track_replay` | `vis.*`, `vis.page` |
| `dashboard/build_data` | `util.common` |

There are **no cycles**, and nothing in `data/` or `util/` imports from `vis/` or `sim/`. That
matters: the crawler must stay usable without the visualiser, and vice versa.

## 3. What each module owns

### `src/data/` — crawling

One module per source, each exposing a single `fetch(year, only_round=None, **opts)`.
`data_crawler.py` is the only entry point; it holds the CLI and the inventory view.

| File | Owns |
|---|---|
| `data_crawler.py` | CLI, year/round argument parsing, `--list` inventory, dispatch |
| `_http.py` | cached `get_json`, `write_csv`, `merge_csv`. **Every** network call goes through it |
| `jolpica.py` | race + qualifying results, 1950-present |
| `openf1.py` | per-lap timing, tyres, pit, overtakes, weather, opt-in telemetry |
| `draftkings.py` | salaries for the upcoming race |

Adding a source means adding one module with a `fetch()` and one line in `data/__init__.py`.
Nothing else changes.

### `src/util/` — shared

`common.py` holds the three name-mapping tables (`NAME_TO_CODE`, `TEAMS`,
`DK_ABBREV_TO_ID`), the path constants, DK API access, and `load_raw()` for reading
per-year CSVs as one frame. `dk_contests.py` lists DK contests.

**Why the mappings live here:** DK identifies drivers by display name, Jolpica by slug,
OpenF1 by car number. Three sources, three vocabularies, one translation layer — see
`data.md` §6.

### `src/sim/` — scoring and analysis

`dk_points.py` scores real past races against `config/scoring.yaml`. `analyze.py` prints
value tables (pts/$1K, captain value, place differential).

**Note the name overstates it.** Nothing here simulates. The Monte Carlo simulator is 1,368
lines of JavaScript inside `dashboard/index.html`, and there is a **live divergence** between
the two scoring paths — see §7.

### `src/vis/` — the race replay

A pipeline, and the module order is the data flow:

```
race.py      pick a session, resolve a lap window, fetch every per-frame feed
circuit.py   official circuit outline + rotation (cached, static per circuit)
frames.py    resample feeds onto one animation timeline
layout.py    pit lane, self-gap measurement, canvas sizing
page.py      assemble an HTML page from assets + a data payload
assets/      replay.js, replay.css, replay.html — the browser side
track_replay.py  the CLI that runs the above in order
selftest.py  30 regression checks over a built payload
```

`track_replay.main()` is a thin CLI over named steps — `select_session`,
`resolve_window`, `fetch_feeds`, `circuit_map`, `build_frames`, `derive_geometry`,
`size_canvas`, `render_html`, `write_outputs` — each independently callable. Four dataclasses
(`Window`, `Feeds`, `Built`, `Canvas`) carry state between them instead of a dozen loose
locals.

## 4. Entry points

Every runnable command, and what it needs:

| Command | Needs | Produces |
|---|---|---|
| `python3 src/data/data_crawler.py` | network | `data/raw/<source>/<year>/` |
| `python3 src/data/data_crawler.py --list` | — | inventory of what's on disk |
| `python3 src/vis/track_replay.py <year> [round]` | crawled OpenF1 data | `data/replay/<year>/<location>.json` + refreshed `replay.html` |
| `… --standalone` | same | also a self-contained `dashboard/replay_<year>_<loc>.html` (~3 MB) |
| `python3 src/vis/track_replay.py --list` | — | crawled races available to replay |
| `python3 src/vis/selftest.py [payload]` | a built payload | 30 PASS/FAIL checks, non-zero exit on failure |
| `python3 src/vis/circuit.py` | — | circuit-map coverage report |
| `python3 src/vis/page.py` | built payloads | `dashboard/replay.html` (the picker) |
| `python3 src/sim/dk_points.py` | Jolpica results | `data/processed/dk_*_points.csv` |
| `python3 src/sim/analyze.py` | DK points + a salary file | value tables on stdout |
| `python3 dashboard/build_data.py` | DK points + a salary file | `dashboard/data.js` |

Two of these currently fail because `data/raw/draftkings/` is empty and DK only serves the
upcoming race — see `data.md` §7.

## 5. The browser side

`assets/replay.js` (755 lines, 26 functions) does everything the replay page does: geometry
and projection, canvas rendering, the timing tower, and playback.

**Assets are real files, not Python strings.** They used to live inside a Python format
string, which meant 288 doubled braces (`{{`/`}}`) to protect 17 placeholders and no way to
lint the JS — three runtime errors reached the browser that way. Now `replay.js` passes
`node --check`, and data arrives as a single JSON blob (`<script id="replay-data">`).

**`dashboard/replay.html` is the entry point.** At ~40 KB it fetches payloads on demand
and covers every race in `data/replay/`, so it's the only page you normally need.

**One asset, two pages.** `page.py` builds both that picker and an optional self-contained
per-race page from the same `replay.js`. They differ by one field in the config blob:

```
{"mode": "inline", "race": {...}}                  standalone: data baked in
{"mode": "picker", "dataDir": "../data/replay"}    picker: fetches on demand
```

`dataDir` is passed in rather than hardcoded, so payloads can move without touching the JS.

The standalone page inlines its whole payload, so it is ~3 MB against the picker's ~40 KB and
covers one race instead of all of them. It is therefore **opt-in** (`--standalone`) and only
worth building to hand someone a single race as one file. Both are git-ignored.

## 6. Testing

`src/vis/selftest.py` — 30 checks over a built payload, grouped into geometry, frames, and
timing/tower. It validates outline closure and length against official circuit lengths, that
no car leaves a drivable path, monotonic lap numbers, tyre state actually varying, retirement
consistency, and plausible pit windows.

It is **mutation-tested**: every check was verified to fire against a deliberately corrupted
payload, so none passes vacuously. It reproduces and catches the historical Monaco 80%
truncation bug.

Run it after any change to `vis/`. It has already caught a real bug that visual inspection
did not — two orderings breaking a position tie differently, giving two drivers a wrong
badge in all 1,568 frames of a replay.

## 7. Decisions worth not re-litigating

**Circuit geometry comes from an official map, not from car positions.** Deriving the outline
from one driver's lap silently truncated Monaco to 80% of the track. MultiViewer publishes a
centreline keyed by the same `circuit_key` OpenF1 returns, in the same coordinate space.
Coverage verified 48/48. See `data.md` §5b.

**Interpolate along the track, not between raw samples.** Cars are sampled every ~4 s on a
full race, about 103 m of travel. A straight line between samples cuts across corners and can
even point backwards on a hairpin. Positions are therefore converted to (arc length, lateral
offset) and interpolated in that space.

**Scale is deliberately not 1:1.** A real F1 car is ~17% of track width, invisible at circuit
zoom. Track and cars are drawn exaggerated, and the canvas grows for tight circuits rather
than the road thinning — see `data.md`.

**The pit lane is derived and has no width.** No source publishes F1 pit geometry. It's drawn
as a 1-D dashed path, offset a constant distance, because inventing a road width would be
fabricating data.

**Do not split driver skill from car performance.** Every available stat is measured from
finishing positions, which conflate the two. They cannot be separated from results alone.

**Known divergence — the two scoring paths disagree.** The JS simulator scores laps-led
(`led × 0.25`); `sim/dk_points.py` omits it entirely. A simulated race leader therefore scores
10-20 pts more than the same real race scored by the backtest, biasing every backtest against
front-runners. Jolpica `/laps` (`data.md` §1.4) has the data needed to fix it. This is the
strongest argument for the shared entity model in `refactor-plan.md` §G.

## 8. Conventions

- **`data/` is entirely generated and git-ignored.** Anything there must be reproducible by
  the crawler, with one exception: DK salary snapshots cannot be re-fetched, so they are
  irreplaceable.
- **Cache every network response.** Re-runs fetch only what's missing, which is what makes
  iteration bearable.
- **A single-round fetch merges into the season CSV** rather than replacing it. Convenient,
  but it means `data_crawler.py 2025 3` leaves a CSV containing only round 3.
- **Config is hand-maintained and authoritative.** `config/scoring.yaml` is verified against
  DK's published rules; treat it as the source of truth, not something to infer.
- **Read the browser console, not just screenshots.** Three JS errors this project rendered a
  blank or stale canvas with no visual clue why.
- **Verify "dead code" by call site, never by docstring.** `layout._order_path` was
  documented as an unused fallback; it is called unconditionally and deleting it would have
  removed the pit lane from every replay.
