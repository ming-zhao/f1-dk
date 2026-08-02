# Refactor plan — `src/vis/`

Written while three agents hold `template.py`, `player.py`, `frames.py`, `race.py` and
`layout.py`, so nothing here is applied yet. This is the plan to execute once they land.

## The two structural problems

Both of today's recurring bug classes trace to these two design mistakes, not to
individual coding slips.

### 1. A 555-line JS program lives inside a Python format string

`template.py` is 719 lines: 555 JS, 85 CSS, 79 HTML — with **264 doubled braces**
(`{{`/`}}`) existing purely to protect 17 real placeholders from `str.format()`.

Consequences, all of which bit today:
- No editor, linter, or formatter can check the JS. Two `ReferenceError`s
  (`drawStartMarker`, `laneScreen`) and a `TypeError` (null `innerHTML`) reached the
  browser and were caught only by reading the console.
- Miss one brace and you get a silent `KeyError` at build time, or a literal
  `{trackw}` in the output — which happened ("trackw is not defined").
- 18 JS functions share one flat scope with module-level mutable state (`ROT`, `scale`,
  `laneScreen`, `TRACK_POS`, `lastOrder`, `marks`, `cursor`). Cache-invalidation bugs
  stay invisible until something renders wrong.

**Fix:** move the JS and CSS into real files under `src/vis/assets/`. Python's only
job becomes serialising data and inlining assets:

```
src/vis/assets/replay.js     # real JS — lintable, formattable, no brace escaping
src/vis/assets/replay.css
src/vis/assets/replay.html   # skeleton with {DATA} and {ASSETS} slots
```

Data reaches the page as one JSON blob (`<script id="data" type="application/json">`)
parsed by `replay.js`, instead of 17 interpolated globals. Placeholders drop 17 → 2,
doubled braces 264 → 0.

### 2. `player.py` re-derives the page from `template.py` by string surgery

18 `replace`/`re.sub`/`index` operations reconstruct the multi-race page from the
standalone one. Its anchors broke **four separate times today** — the file now carries
three `raise SystemExit("couldn't find …")` guards as scar tissue, and the tower-row
markup is duplicated in both files and must be hand-synced (it desynced once already).

**Fix:** delete the surgery. With assets extracted, both pages share one `replay.js`
and differ only in how data arrives:

- standalone → data inlined in the page
- player → `fetch('replays/<file>.json')`, driven by the dropdowns

That's one `if` in the JS bootstrap, not 18 regex transforms. `player.py` shrinks to
writing a small HTML skeleton.

## Target module layout

| File | Responsibility | ~lines |
|---|---|---|
| `track_replay.py` | CLI + orchestration only | 150 |
| `race.py` | session selection, window, feed fetching | 350 |
| `layout.py` | outline, pit lane, rotation, canvas sizing | 250 |
| `frames.py` | resample feeds onto the animation timeline | 220 |
| `circuit.py` | official circuit map (cached) | 100 |
| `page.py` | assemble HTML from assets + data (replaces `player.py`) | 60 |
| `selftest.py` | regression checks on a built replay | — |
| `assets/replay.js` | all rendering + playback | 560 |
| `assets/replay.css` | all styling | 85 |
| `assets/replay.html` | skeleton | 80 |

Python drops from ~2000 lines to ~1130, and the 560 lines of JS become real, checkable
JS.

## Splitting `replay.js`

Not one flat scope — four ES modules with explicit boundaries:

- `geometry.js` — projection, rotation, arc-length ↔ x/y (`toTrackCoords`,
  `fromTrackCoords`, `nearestTrack`). Pure functions, no DOM, unit-testable.
- `render.js` — canvas drawing (`drawTrack`, `drawCar`, `drawPitLane`,
  `drawStartMarker`, `shade`).
- `tower.js` — the timing panel (`updateTower`, `setText`), owning its own DOM refs.
- `player.js` — playback clock, seek, speed, race switching. The only mutable state.

Each takes state as arguments rather than reaching for globals, which is what makes the
cache-invalidation bugs (`laneScreen`, `TRACK_POS`) impossible rather than merely fixed.

## Order of work

1. Land the three agents' fixes first — don't refactor around moving code.
2. Run `selftest.py`; capture a baseline screenshot + DOM measurements.
3. Extract CSS (zero risk, no logic).
4. Extract JS verbatim into `assets/replay.js`; switch to a JSON data blob.
5. Rewrite `player.py` → `page.py`, sharing the same asset.
6. Split `replay.js` into the four modules.
7. Re-run `selftest.py`; diff screenshots and DOM measurements against the baseline.

Steps 3–6 must each be individually verifiable — build, load in a browser, read the
console, compare to the baseline. No step should change rendered output at all.

## Rules that would have prevented today's bugs

1. **Never edit a multi-line block with `str.index()` slicing.** It silently matched a
   docstring instead of code and ballooned `shape.py` to 486k lines; the file was
   untracked, so there was no recovery. Use exact-match assertions or the Edit tool.
2. **Commit before refactoring.** `src/vis/` is still entirely untracked.
3. **Read the JS console every time**, not just screenshots. Three errors today
   rendered a blank or stale canvas with no visual clue why.
4. **One source of truth per artefact.** Duplicated tower markup desynced within hours.

---

## Measured evidence

Gathered read-only while the fix agents held the files.

| Smell | Measurement |
|---|---|
| JS embedded in a Python format string | 555 JS + 85 CSS lines; **264 doubled braces** guarding 17 placeholders |
| `player.py` rebuilds the page by string surgery | **18** `replace`/`re.sub`/`index` ops; **3** `SystemExit` guards added today after anchors broke **4** times |
| Duplicated JS between the two builders | `setSpeed` and `tick` defined in both; `player.py` carries a **100-line** LOADER block; tower-row markup duplicated (desynced once) |
| Over-long functions | `track_replay.main()` **174** lines · `frames.build()` **132** · `race.lap_window()` **52** |
| Dead helpers from the retired derived-outline path | `_one_lap`, `_dedupe`, `best_rotation` — only reachable via a fallback that no longer fires for any crawled circuit. (`_order_path` was listed here too but is live — see Task F.) |
| Untracked source | **10** Python files under `src/` outside git; `shape.py` was already lost this way |

No genuinely unreferenced top-level functions — the problem is structure and
duplication, not orphaned code.

## Fan-out plan (one agent per task)

Sequential where marked; the rest are independent. Every task must build, load in a
browser, read the JS console, and diff against the baseline captured in step 0.

**Step 0 — baseline (do first, alone).** Build both replays, run `selftest.py`, capture
screenshots and a DOM/geometry measurement dump to `doc/baseline/`. Everything after
this is judged against it. No behaviour may change in steps 1–5.

**Task A — extract CSS.** `template.py` → `assets/replay.css`, inlined at build. Zero
logic, purely mechanical. Unblocks B by shrinking the file.

**Task B — extract JS (depends on A).** Move the 555 JS lines verbatim into
`assets/replay.js`. Replace the 17 interpolated globals with a single JSON blob
(`<script id="data" type="application/json">`) parsed on load. Expected: doubled braces
264 → 0.

**Task C — unify the two page builders (depends on B).** Delete `player.py`'s string
surgery; add `page.py` that writes a skeleton around the shared asset. Standalone
inlines its data, the picker fetches it — one `if` in the JS bootstrap. Removes all 18
transforms, both `SystemExit` guards, and the duplicated markup.

**Task D — split `replay.js` (depends on C).** Four ES modules: `geometry.js` (pure,
unit-testable), `render.js`, `tower.js`, `player.js`. State passed as arguments, not
read from globals — this is what makes the `laneScreen`/`TRACK_POS` cache bugs
structurally impossible.

**Task E — break up the long Python functions (independent of A–D).** `main()` 174 → a
thin CLI over named steps; `build()` 132 → separate frame/tower/lap builders.

**Task E — DONE.** Longest function is now 44 lines (`frames.tower_rows`); nothing
exceeds 50.

| Function | Before | After |
|---|---|---|
| `track_replay.main()` | 174 | **26** — parses args, then calls the named steps below |
| `frames.build()` | 132 | **28** — coordinator over `_timeline` / `lap_numbers` / `car_frames` / `tower_rows` |
| `race.lap_window()` | 52 | **20** — `_timed_laps` + `reference_car` + `_span` + `full_race_window` |

`main()`'s steps are `select_session` → `resolve_window` → `fetch_feeds` →
`circuit_map` → `build_frames` → `derive_geometry` → `size_canvas` →
`render_html`/`replay_payload` → `write_outputs`, each independently callable. Four small
dataclasses (`Window`, `Feeds`, `Built`, `Canvas`) carry state between them instead of a
dozen loose locals; `Window.dt` replaces the `FRAME_STEP * KEEP_EVERY * thin` expression
that was spelled out in four places.

Ordering dependency preserved and documented: the outline is resolved before
`car_frames()`, because a stationary car's heading falls back to the nearest track
direction.

Verified byte-identical: both `--full` payloads and the standalone HTML for 2024 R8 and
2025 R1 have unchanged MD5s, and stdout `diff`s clean. `race.py` was left as one module —
the target layout above keeps session selection and feed fetching together, and splitting
them would have churned the file for no reader benefit.

**Task F — delete the dead derived-outline path (independent).** Remove `_one_lap`,
`_dedupe`, `_order_path` and the `best_rotation` fallback *only after* confirming the
official map covers every circuit that can be crawled; otherwise keep it and add a test
that exercises it, so it can't rot unnoticed.

**Task F — DONE. Coverage is complete, so the fallback was removed.** All **48**
`(year, circuit_key)` pairs in `data/raw/openf1/*/sessions.csv` (2024 and 2025, the same
24 circuits each) resolve to a MultiViewer map — 0 missing. Every response is now cached
in `data/raw/circuits/` (48 files, 1.0 MB), so the check is offline and repeatable:

```
python3 src/vis/circuit.py     # prints per-circuit pts/km/rotation, exits 1 on a gap
```

Removed: `frames._one_lap`, `frames._dedupe`, `layout.best_rotation`. `frames.build()`
now raises `SystemExit` with a diagnostic if no official outline is passed, rather than
drawing a wrong shape. If a gap ever appears the fix is to add geometry for that
circuit, not to reinstate the derived outline.

One correction to the table above: **`layout._order_path` was never dead.** It is called
unconditionally by `layout.pit_lane()` and is what turns the per-driver, per-stop pit
samples into one traversable polyline (39 path points at Monaco, 36 at Melbourne in the
current builds). Its docstring said "fallback for when no outline is available", which is
what made it look dead. Kept, with the docstring corrected.

**Prerequisite before any of this:** commit `src/vis/` (10 untracked files). Needs
mgzhao's go-ahead — a tarball backup exists in the meantime.

---

## Entity model for the simulator

### First, a correction on where the simulator actually is

`src/sim/` is only 280 lines and does **not** simulate anything — `dk_points.py`
scores past races and `analyze.py` prints value tables. The real Monte Carlo simulator is
**1368 lines of JavaScript inside `dashboard/index.html`** (60 functions):
`simulateRace()`, `simulateCandidateScore()`, `runAutoSim()`, `startAiSimulation()`.

So "give the car a class" has to mean *extract the simulator from `index.html` first*.
There is no Python object model to add a class to.

### The hierarchy needs inverting

A driver is not a realisation of a car. In F1 a **constructor fields two cars**, and each
car has **one driver**. The thing that actually scores is the pairing:

```
Constructor ──┬── Entry(car #1) ── Driver
              └── Entry(car #2) ── Driver
```

`Entry` — one car, one driver, one race — is the natural simulation unit. It's what gets
a grid slot, a DNF roll, a finishing position and laps led. This matters for DK because:

- **Both** drivers and constructors score, separately (`config/scoring.yaml` has distinct
  `driver:` and `constructor:` blocks), so both are first-class, not one nested in the other.
- Constructor bonuses (`both_cars_classified`, `both_cars_in_points`, `both_cars_on_podium`)
  are only computable from **both** its entries — the constructor needs to reach its two
  cars.
- The "defeated teammate" bonus is entry-vs-entry within a constructor.
- The roster rule "max 2 picks from one team" is a constraint over the pairing, not over
  drivers alone.

### What the entities can and cannot know

A real caveat: every stat we have (`avgFinish`, `stdFinish`, `avgGrid`, `dnfRate`) is
measured from **finishing positions**, which conflate driver skill and car performance.
They cannot be separated from results alone. So:

- Do **not** model `Car.pace` and `Driver.skill` as separate parameters — we cannot
  estimate them independently, and inventing a split would be fabricating precision.
- `Entry` holds the measured distribution. `Driver` holds identity. `Constructor` holds
  identity plus its own DK stats and its two entries.
- If OpenF1 telemetry (`st_speed`, sector times) is ever wired in, *that* is what could
  justify a genuine car-performance term — measured, not assumed.

### Proposed model

```
Driver        code, name, number                        identity only
Constructor   id, name, colour, entries[]               identity + its 2 cars
Entry         driver, constructor, salary, salaryCpt,   the simulation unit
              form: Form, grid, finish, dnf, lapsLed
Form          avgFinish stdFinish avgGrid stdGrid       measured distribution
              dnfRate avgDk races  + prior/clamp rules  (+ where it came from)
RaceState     entries[], totalLaps, weather, fixedGrid  one simulated race
Scoring       loaded from config/scoring.yaml           rules, not data
```

`Form` as its own object is worth it: the 20-race window, the σ floor of 1.5, the
`dnfRate` clamp to [0.03, 0.35] and the priors for new drivers are all currently scattered
between `build_data.py` and the JS. Putting them in one place makes them testable and
stops them drifting apart.

`Lineup` (1 CPT + 4 D + 1 CNSTR, $50k cap, max 2 per team) then becomes a small class that
validates itself, instead of the constraint being re-checked inline in several JS functions.

### Why this is worth doing

Not aesthetics — three concrete wins:

1. **The simulator becomes testable.** Today it can only be exercised by clicking the
   dashboard. As Python (or an importable JS module) it can be asserted against known
   distributions and against `dk_points.py`'s scoring of real races.
2. **One scoring implementation instead of two.** `dk_points.py` scores real results in
   Python; `scoreDriver()`/`scoreConstructor()` score simulated ones in JS. Two
   implementations of the same `scoring.yaml` that must agree — and nothing checks that
   they do. This is exactly the class of bug that has cost the most time today.
3. **Laps-led can finally be scored.** `dk_points.py` skips it (understating leaders by
   10–20 pts); the JS simulator models it. Sharing one `Entry`/`Scoring` pair closes that
   gap, and Jolpica `/laps` (§1.4) supplies the real data.

### Task G — extract and model the simulator (independent of A–F)

1. ~~Verify the two scoring paths agree~~ — **already checked, and they don't.** Three
   divergences found by reading both implementations:

   | | JS `scoreDriver()` | Python `dk_points.py` |
   |---|---|---|
   | **Laps led** | scored: `led × 0.25` | **absent — always 0** |
   | Pit-lane start (`grid == 0`) | n/a (simulated grids are 1..22) | remapped to field size |
   | Teammate bonus | strictly ahead of the other car | best finisher in team (needs ≥2 cars) |

   The laps-led gap is the significant one: a **simulated** race leader scores 10–20 pts
   more than the **same real race** scored by the backtest. Projections and backtests are
   therefore not on the same scale, which silently biases every backtest against
   front-runners. This is a live bug and should be fixed before any restructuring — and it
   is precisely the failure mode a single shared `Scoring` implementation prevents.

   The teammate rule differs only for one-car teams or mid-season driver changes; the
   pit-lane rule exists in the Python path alone.
2. Extract the simulation JS out of `index.html` into `assets/simulate.js` (same asset
   split as Task B; `index.html` is 1860 lines with 1368 of them JS).
3. Introduce the entity model above in one place, and have both the replay and the
   dashboard consume it.
4. Add a Python `sim/model.py` mirroring it, so `dk_points.py` and the simulator
   share one definition of an entry and one scoring implementation.
5. Cover it with tests: scoring a known race matches hand-computed DK points; a
   simulated field respects the cap and the max-2-per-team rule; σ floors and clamps hold.

Sequence: step 1 is a bug hunt and should run before the rest. Steps 2–4 must not change
simulated output distributions — check by seeding the RNG and comparing before/after.
