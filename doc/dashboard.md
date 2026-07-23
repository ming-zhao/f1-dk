# Dashboard

`dashboard/index.html` — a single static HTML file (no server, no build step) that lets you
build a DraftKings F1 classic lineup and simulate a race outcome against it. Open it directly
in a browser (or serve it over HTTP — see [skill/dashboard.md](../skill/dashboard.md) for why
that matters when testing).

## Data dependency

The page loads `dashboard/data.js` via `<script src="data.js">`. That file is **generated**,
not hand-edited — regenerate it after refreshing race/salary data or editing race notes:

```bash
python3 dashboard/build_data.py
```

`build_data.py` reads:

- `data/processed/results.csv`, `dk_driver_points.csv`, `dk_constructor_points.csv`
  (from `src/fetch_jolpica.py` + `src/dk_points.py`)
- the latest file in `data/dk_salaries/` (from `src/fetch_dk_salaries.py`)
- `config/scoring.yaml` (DK scoring rules)
- `config/race_notes.yaml` (optional, hand-curated race notes — see below)

and writes a single `const F1DATA = {...}` payload: driver stats (avg finish/grid, std dev,
DNF rate, avg DK points, both roster-slot salaries), constructor stats, scoring rules, total
laps, race name, and the raw `race_notes.yaml` contents (`raceNotes`). If `data.js` is missing
or stale, the driver/constructor tables render empty and the notes boxes show their
"add info and rebuild" placeholder.

**`config/race_notes.yaml` fields:** `tyre_plans` and `driver_performance` are the two fields
actually rendered in the dashboard (see below). `pit_strategy`, `penalties`, `weather`, and
`lineup_angles` also exist in the yaml and ship into `data.raceNotes` but currently have **no
UI** — they're captured for record-keeping / future use, not dead ends, but editing them won't
change anything visible today.

## Tabs

Four tabs, toggled via `switchTab('builder' | 'auto' | 'chances' | 'ai')` (generic — loops the
`TABS` array, toggling `#tab-<name>` display and `#tab-<name>-btn` active class): **Lineup
Builder** (default), **Auto Simulation**, **The Chances**, and **AI Simulation**. Only one
tab's container is visible at a time; state in all of them (current lineup, last auto-sim
results, last chances breakdown, AI simulation's running totals) is preserved when switching —
switching away from AI Simulation does **not** stop it; it keeps running in the background via
`setInterval` regardless of which tab is active. Running auto simulation automatically switches
to The Chances tab once it finishes (see below).

## Layout — Lineup Builder tab

- **Driver pool** (left) — one row per driver, teammates grouped and separated by a divider
  line. Columns: team logo, name, CPT salary, D salary, actions. Column headers are clickable
  to sort (`th.sortable`); sorting re-groups teams by their best driver on the active column —
  the underlying sort keys (`avgDk`, `avgFinish`, `dnfRate`) still work even though those stat
  columns aren't shown in the table. Clicking a driver's **name** opens a stats popup (CPT/D
  salary, avg DK pts, races, avg finish ± std dev, avg grid ± std dev, DNF rate); close it via
  the ✕, clicking outside the card, or Escape.
- **Constructors** (left, below drivers) — salary, avg DK pts, max DK pts, "both top-10 %".
  Also sortable.
- **Your lineup** (right) — salary used / remaining / projected avg points tiles, a salary
  meter bar, and the 6 roster slots (1 CPT + 4 D + 1 CNSTR). A **Remove all** button next to
  the heading clears the whole lineup in one click; it's disabled whenever the lineup is
  already empty.
- **Tyre plans** (right, below Your lineup) — each fielded team's tyre/stint strategy for the
  race, read from `data.raceNotes.tyre_plans` (sourced from `config/race_notes.yaml` →
  `tyre_plans`, keyed by constructor id). Teams with no notes yet show "No plan yet"; if
  nothing at all has been filled in, the box shows a placeholder pointing at the yaml file
  instead. Purely informational — fill in the yaml and rebuild `data.js` to update it.
- **Driver Performance** (right, below Tyre plans) — same pattern, per driver instead of per
  team: a free-text summary of each driver's practice (FP1/FP2/FP3) pace and issues, read from
  `data.raceNotes.driver_performance` (sourced from `config/race_notes.yaml` →
  `driver_performance`, keyed by driver code). Same empty/partial-fill behavior as Tyre plans.
- **Simulate race** button — enabled only once the lineup is legal and complete.
- **Results panel** (hidden until first simulation) — total score, a per-pick score
  breakdown table, and the full simulated race classification.

## Lineup rules (enforced client-side)

- Roster = 1 Captain + 4 Drivers + 1 Constructor.
- Captain scores at 1.5× and costs 1.5× the driver's base salary (both salaries come straight
  from the DK CSV, not computed from a fixed ratio).
- $50,000 salary cap (`data.salaryCap`); going over disables the Simulate button and shows a
  warning.
- DK rule: can't roster 2 drivers **and** the constructor from the same team — also enforced
  as a warning.
- A driver/team's row and buttons grey out once you can no longer afford it (CPT or D slot)
  given remaining salary.

## Race simulation (`simulateRace()`)

Randomized per click — re-simulate to see outcome variance, not a single deterministic
prediction:

1. **Qualifying** — if a real grid has been applied via the Driver's Qualifying box (see
   below), every driver's grid position comes straight from `fixedGrid` instead, identical on
   every call. Otherwise (the default) each driver's grid position is sampled from
   `avgGrid ± stdGrid` (Gaussian), then ranked into grid 1..N.
2. **Race** — each driver independently rolls a DNF against their historical `dnfRate`.
   Finishers get a pace score blended from grid position (45%) and historical finish
   form (55%, `avgFinish ± stdFinish`), then are ranked; DNFs are appended ordered by laps
   completed.
3. **Laps led** — the race winner leads 45–80% of laps; the next few finishers split most of
   the remainder.
4. **Fastest lap** — picked at random from the top 10 classified finishers.

## DK scoring (`scoreDriver` / `scoreConstructor`)

Applies `config/scoring.yaml` rules to the simulated outcome:

- **Driver**: finishing-position points + place-differential (grid − finish) + bonuses
  (fastest lap, laps led, classified finish, beat teammate).
- **Constructor**: sum of both cars' finishing-position points + bonuses (fastest lap, laps
  led, both classified, both in points, both on podium).
- Captain's total is multiplied by 1.5× when summed into the final score.

Results panel shows the full breakdown per pick plus the entire simulated field
(your picks starred and bolded), so you can see how the lineup would have scored under that
random outcome.

## Auto Simulation tab (lineup optimizer)

"Run auto simulation" (`runAutoSim()`) searches for the best lineup automatically, in two
passes so it stays fast in-browser:

1. **Exhaustive projection search** (`findTopCandidatesByProjection`) — enumerates every
   legal combination of 1 Captain + 4 Drivers + 1 Constructor (5-driver combos via
   `fiveCombos()`, a plain nested-loop generator — C(22,5) ≈ 26k combos × 5 captain choices ×
   11 constructors ≈ 1.4M candidates), filtering out anything over the $50,000 cap or that
   breaks the DK same-team rule, and scores each by **projected** points (`cptAvgDk × 1.5 +
   sum of other 4 avgDk` — the same fast heuristic as the "Proj. avg pts" tile, no simulation).
   Candidates are deduped by **driver squad** (the 5 people picked, regardless of who's
   captain or which constructor) — only the best-projected variant of each unique squad is
   kept, so the shortlist doesn't fill up with near-duplicates that just swap the captain or
   constructor. Individual drivers can and will reappear across different squads (that overlap
   is expected — only the exact same 5-person group is deduped).

   On top of squad dedup, the final 50 are chosen **greedily by projection while capping how
   many times any one captain or constructor can appear** (`maxPerCpt`/`maxPerCons`, default 5
   each) — without this, the single highest-avgDk driver tends to be the optimal captain for
   almost every squad (same for the best-value constructor), so the list would otherwise read
   as "same captain/constructor, different drivers" rather than genuinely varied picks. If the
   caps are too tight to fill 50 slots (not enough distinct legal squads under those limits),
   they're relaxed by 1 for both at a time until there's enough — so counts can end up slightly
   above 5 (e.g. 6) rather than being dropped entirely; they're never released all at once, so
   one captain/constructor can't dominate the list by backfilling unchecked. Runs in well under
   a second.
2. **Monte Carlo evaluation** (`evaluateCandidate`) — for each of the 50 shortlisted lineups,
   runs 1000 full `simulateRace()` calls and scores each with the same `scoreDriver` /
   `scoreConstructor` functions the main Simulate button uses, then reports avg / min / max
   simulated score. Shortlisted first (rather than simulating all ~1.4M combos) because full
   Monte Carlo on every legal combo would be far too slow client-side. The full 50×1000 = 50k
   simulations run in about a second in testing.

Results render as a ranked table (captain, 4 drivers, constructor, salary, avg score, min–max
range) inside a scrollable container (`#auto-results-wrap`, max-height 640px, sticky header)
since 50 rows would otherwise make the page very long. Each row has a **Load** button
(`loadCandidate()`) that copies that lineup into `lineup`, re-renders the builder so it's ready
whenever you switch back to it, then jumps straight to **The Chances tab** for that specific
lineup (see below) — the loaded lineup is always cap-legal and rule-legal by construction, so
Simulate is immediately enabled if you do go back to the builder.

Runs synchronously but wrapped in `setTimeout(...,10)` between the two passes so the "Searching
…" / "Simulating …" status text actually paints before the heavy loop blocks the main thread.

## The Chances tab

Shows what has to happen for a specific lineup's single best-case simulated outcome, and how
likely it is. Gets populated two ways:

- **Automatically** — after ranking finishes, `runAutoSim()` calls `analyzeTopLineupChances()`
  on the **#1 ranked lineup** (2000 dedicated `simulateRace()` runs) and switches to The Chances
  tab on its own, without waiting for a click.
- **Any Load button** — clicking **Load** on *any* row in Auto Simulation or AI Simulation
  (`loadCandidate()` / `loadAiCandidate()`, via a shared `showChancesForCandidate()` helper)
  loads that lineup into the builder, then shows its chances the same way — not just the #1
  ranked one. If that candidate already has a `.chances` result attached (AI Simulation
  candidates get this from `computeAiChances()` after Stop), it reuses that instantly instead of
  re-simulating; otherwise it runs a fresh 2000-sim analysis on the spot (fast enough — well
  under 100ms per lineup — to do synchronously on click). The intro text just says "this
  lineup," not "#1 ranked," since it can now be any of them.

What the analysis does, using that batch of ~2000 sims (1000 if reusing an AI Simulation
candidate's cached result):

- Tracks every run's total score and keeps the **single highest-scoring run** found — that
  becomes "the outcome": each pick's finish position (and grid), DNF status, and which bonuses
  fired (fastest lap, laps led, classified, beat teammate, both-in-points, etc.), read straight
  off `scoreDriver` / `scoreConstructor`'s existing `bonusDetail` output.
- For each pick, **"Chance (solo)"** = how often, across those same 2000 runs, that pick's own
  scored total — finish points *and* every bonus combined (fastest lap, laps led, classified,
  beat teammate, etc.) — was at least as good as it was in the best run. It's driven off the
  pick's full point total, not just their finish position in isolation, so it lines up with the
  finish-plus-bonuses actually shown for that pick (constructor's solo chance works the same way
  off its own point total, since it doesn't have a finish position).
- **"Chance of this outcome or better"** = how often, across the same 2000 runs, the *whole
  lineup's total score* was ≥ the best run's score — i.e. the actual empirical probability of
  the full combined outcome, not a product of the per-pick chances (which aren't independent —
  grid and race pace are correlated across the field, explained in the box's own footer text).
  For a genuine single-run maximum this is often ~1/2000 (0.05%), which is expected and
  correctly conveys how much variance/luck is baked into hitting a ceiling outcome.
- Nothing here is persisted or configurable yet — every "Run auto simulation" click re-runs
  the whole thing (new random sims, so the exact best-case shown can shift slightly run to
  run) against whichever lineup ranks #1 that time.

Below that, a second card ("Why this percent?", `buildChancesExplanation()`) explains the
combined percentage in plain language, computed from the same `best` result — no extra
simulation:

- **Bottleneck / easiest pick** — the picks are re-sorted by solo probability; the lowest one
  is called out as "the toughest single requirement" (the main reason the outcome is rare), and
  the highest as the easiest part.
- **Naive-vs-actual comparison** — multiplies every pick's solo probability together (what the
  combined chance *would* be if picks were independent) and compares it to the real simulated
  `combinedProb`. Since race outcomes are correlated (grid/pace/DNFs are all drawn relative to
  the same field each run, not independently per driver), the two numbers are usually quite
  different — the text calls out whether the actual chance ran notably higher or lower than the
  naive estimate, and explains why.
- **Per-pick breakdown** — a line for every pick (drivers + constructor) spelling out exactly
  why their solo percentage is what it is: what they scored in the best run (finish + bonuses),
  their real historical numbers pulled from `data.js` (avg finish ± std dev, avg grid, DNF
  rate), and a qualifier (`qualify()`) — "a fairly ordinary result," "a solidly good day," or
  "a real stretch" — based on how high the solo probability actually is. This directly answers
  "why does pick X show Y%": the number always comes from `byCode[code]`'s actual season stats,
  not a canned explanation.

## AI Simulation tab (continuous background loop)

Same underlying math-based engine as Auto Simulation — no external AI/LLM call, no network
request, nothing server-side. "AI" here means "runs on its own without you clicking Simulate,"
not an LLM reasoning about picks.

- **Start** (`startAiSimulation()`) — shortlists 20 candidates via the same
  `findTopCandidatesByProjection()` used by Auto Simulation (squad-deduped, captain/constructor
  capped), zeroes out a per-candidate accumulator (`{n, sum, min, max}`), then immediately runs
  one batch and arms a `setInterval` (`aiTick()`, every 400ms) to keep running batches
  indefinitely. Each tick simulates 150 more races per candidate (20 × 150 = 3000 sims/tick,
  ~50ms of work — cheap enough to keep the tab responsive) and folds them into the running
  avg/min/max, then `renderAiResults()` re-sorts and redraws the table live.
- **Stop** (`stopAiSimulation()`) — clears the interval, then runs `computeAiChances()`: a
  dedicated `analyzeTopLineupChances()` pass (the same engine The Chances tab uses for the #1
  Auto Simulation lineup) for **every** currently-ranked AI candidate, 1000 sims each (20 × 1000
  = 20k sims, ~1.1s in testing). Each row's new **Chances** column then shows that candidate's
  own best-case score and "chance of this or better" (`combinedProb`), computed the same way as
  The Chances tab — this only happens once, on Stop, not continuously while running (too
  expensive to redo every 400ms tick). Status reads "computing chances for each lineup…" while
  it runs, then reverts to "Stopped after N total simulations."
- **Filtering out unrealistic best cases** (`MIN_PICK_CHANCE = 0.05`, applied inside
  `computeAiChances()` right after computing chances) — any candidate whose best-case outcome
  needs *any* individual pick (or the constructor) to hit a result with less than a 5% solo
  chance gets dropped from `aiCandidates` entirely; it's not shown, not loadable. This can be
  aggressive — a lineup's single best-of-1000 run often involves at least one rare event (a
  fastest lap, an outsized points day), so it's common for most of the 20 shortlisted candidates
  to get filtered out in one Stop (e.g. 19 of 20 hidden, 1 survivor, in testing). If **every**
  candidate gets filtered, the table shows a message ("Every shortlisted lineup needed an
  almost-impossible… result — Click Start to try a fresh shortlist") in place of rows rather
  than an empty-looking table; the status line also reports how many were hidden. Clicking
  **Start** resets `AI.filteredOutCount` to 0 and re-shows all candidates unfiltered until the
  next Stop recomputes and re-filters.
- Clicking **Start** again always starts a fresh shortlist and resets all counters (and any
  computed chances) to zero — it's a restart, not a resume.
- The table looks like Auto Simulation's (same columns plus a running **Sims** count and, once
  stopped, a **Chances** column per candidate) with its own scrollable/sticky-header wrapper
  (`#ai-results-wrap`). The **Load** button (`loadAiCandidate()`) only appears once stopped
  (`renderAiTable()` checks `AI.running` and renders an empty cell instead while it's still
  live) — the ranking keeps shifting every tick while running, so loading a row mid-run could
  load a lineup that's no longer where you clicked it; Stop first, then Load. Same
  copy-into-`lineup`-then-jump-to-The-Chances behavior as Auto Simulation's Load (see below) —
  and since Stop already ran `computeAiChances()`, every AI Simulation candidate has a
  `.chances` result cached, so its Load is effectively instant (no on-the-spot re-simulation) —
  just against the `aiCandidates` array instead of `autoCandidates`.
  Rendering is split into `renderAiResults()` (recomputes avg/min/max from `AI.stats` while
  ticking, then calls `renderAiTable()`) and `renderAiTable()` (just redraws whatever's
  currently in `aiCandidates`, including any `.chances` attached by `computeAiChances()` —
  kept separate so attaching chances data doesn't get clobbered by a stray re-sort).
- Because averages only get more precise the longer it runs (standard error shrinks with more
  samples), leaving it running and checking back later gives a tighter estimate of each
  candidate's true average than Auto Simulation's one-shot 1000-sim pass.

The AI Simulation tab uses a `.layout` two-column grid (same pattern as the Lineup Builder tab)
so the AI Simulation card sits next to a second card, **Driver's Qualifying** — see below.

## Driver's Qualifying (real grid entry)

Every simulation in the dashboard (`simulateRace()`) normally samples each driver's grid
position randomly from their historical `avgGrid`/`stdGrid`. Once real qualifying happens,
that guesswork becomes unnecessary — this box lets you enter the actual grid and have every
simulation (Simulate race, Auto Simulation, AI Simulation, The Chances) use it instead.

- **State**: `qualiOrder` (array of driver codes, defaults to predicted order sorted by
  `avgGrid`), `qualiPenalties` (`{code: places}`, all zero until set), and `fixedGrid`
  (`null` by default — simulated qualifying; once populated, `simulateRace()` reads grid
  positions straight from it instead of sampling).
- **Reordering** (`moveQualiRow`) — ▲/▼ per row swap that driver with its neighbor, for
  dragging the list from the predicted order into the real qualifying classification.
- **Penalties** (`setQualiPenalty`) — a number input per row (places to drop). The **Grid**
  column previews the result live via `computeGrid()`, which mimics real F1 penalty
  application: a penalized driver's sort key is `qualifying position + penalty places`;
  everyone else sorts by their plain qualifying position; ties (a penalized driver landing on
  the same target rank as someone else) are broken by original qualifying order, relying on
  `Array.sort`'s stability. This is an approximation of the FIA's actual (more intricate)
  penalty-application process, but matches typical single/double-penalty scenarios described in
  `config/race_notes.yaml`'s `penalties` notes.
- **Apply grid** (`applyQualiGrid`) — sets `fixedGrid = computeGrid(qualiOrder, qualiPenalties)`.
  From that point on, `simulateRace()`'s qualifying step is deterministic (same grid every
  single simulated race) instead of randomized — the race itself (DNFs, pace, laps led, fastest
  lap) is still random, only the starting grid becomes fixed.
- **Use simulated grid** (`resetQualiGrid`) — sets `fixedGrid = null`, reverting to the default
  randomized qualifying. The status line under the buttons always says which mode is active.
- **Auto-apply from `config/race_notes.yaml`** (`initQualifying()`, called once at page load,
  after `renderTyrePlans()`/`renderDriverPerformance()`): if `config/race_notes.yaml` →
  `qualifying.order` has been filled in (a list of driver codes, best to worst) and
  `dashboard/data.js` rebuilt, the dashboard loads that as `qualiOrder`, merges in
  `qualifying.penalties`, and calls `applyQualiGrid()` automatically — no manual reordering or
  clicking needed, the real grid is just already active when the page opens. Any driver code
  missing from `order` (e.g. a data mismatch) is appended in predicted order rather than
  dropped, so the table always has all 22 rows. If `order` is empty (the default, until
  qualifying actually happens), it falls back to `resetQualiGrid()` — today's behavior,
  unchanged. Manually reordering/entering penalties in the UI afterward still works exactly the
  same way regardless of how the initial state was populated; nothing about the box is
  read-only once loaded, this only affects the *starting* state on page load.

## Refreshing for a new race week

1. `python3 src/fetch_jolpica.py` — backfill/update race + qualifying results.
2. `python3 src/dk_points.py` — recompute DK points from results.
3. `python3 src/fetch_dk_salaries.py` — pull the current week's DK salaries (auto-detects the
   active F1 draft group).
4. Edit `config/race_notes.yaml` as intel comes in during the week — `tyre_plans`,
   `driver_performance`, penalties, weather, etc., and `qualifying.order`/`qualifying.penalties`
   once real qualifying happens (see [skill/data-process.md](../skill/data-process.md) for
   sources/timing).
5. `python3 dashboard/build_data.py` — regenerate `dashboard/data.js` (rerun any time the yaml
   changes, not just on a full data refresh).
6. Reload `dashboard/index.html`.
