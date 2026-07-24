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
laps, race name, the raw `race_notes.yaml` contents (`raceNotes`), and `raceHistory` — real
per-race DK points for every past race in `dk_driver_points.csv`/`dk_constructor_points.csv`
(built by `build_race_history()`), used by the Testing AI tab. If `data.js` is missing or
stale, the driver/constructor tables render empty and the notes boxes show their
"add info and rebuild" placeholder.

**`config/race_notes.yaml` fields:** `tyre_plans` and `driver_performance` are the two fields
actually rendered in the dashboard (see below). `pit_strategy`, `penalties`, `weather`, and
`lineup_angles` also exist in the yaml and ship into `data.raceNotes` but currently have **no
UI** — they're captured for record-keeping / future use, not dead ends, but editing them won't
change anything visible today.

## Tabs

Five tabs, toggled via `switchTab('builder' | 'auto' | 'chances' | 'ai' | 'testing')` (generic
— loops the `TABS` array, toggling `#tab-<name>` display and `#tab-<name>-btn` active class):
**Lineup Builder** (default), **Auto Simulation**, **The Chances**, **AI Simulation**, and
**Testing AI**. Only one tab's container is visible at a time; state in all of them (current
lineup, last auto-sim results, last chances breakdown, AI simulation's running totals, last
backtest results) is preserved when switching — switching away from AI Simulation does **not**
stop it; it keeps running in the background via `setInterval` regardless of which tab is
active. Running auto simulation automatically switches to The Chances tab once it finishes
(see below).

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
  ranked one. If that candidate already has a `.chances` result attached (every AI Simulation
  candidate visible in the table has one, refreshed continuously by `updateAiChances()` — see
  the AI Simulation section below), it reuses that instantly instead of re-simulating;
  otherwise it runs a fresh 2000-sim analysis on the spot (fast enough — well under 100ms per
  lineup — to do synchronously on click). The intro text just says "this lineup," not "#1
  ranked," since it can now be any of them.

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

**Elimination is absolute; the 20-count is a best-effort target, not a guarantee.** A lineup
currently needing an almost-impossible (<5%) result from any pick is **never shown**, full
stop — even if that means the table shows fewer than 20 rows, or (rarely, right after Stop's
harsher precision pass) zero. This was a deliberate trade-off: an earlier version of this
feature always padded the display back up to exactly 20 by swapping in reserve candidates
regardless of whether they too failed the check, which technically let a fresh violator sit
displayed until its next chances re-check. Elimination now wins outright.

*Why the count fluctuates so much in practice:* a lineup's single best-of-N simulated outcome
is, by definition, an outlier — and outliers usually require at least one individually rare
break. So on any given sample, **most** candidates fail the <5% check on at least one pick, not
a rare few. In testing, a running pool often had only 5–7 of 20 passing at once, and Stop's
harsher 1000-sim precision pass (a more extreme "best of" than the live 300-sim one) not
infrequently finds that literally none of the currently-tracked candidates pass right at that
moment. That's expected, not a bug — the filter is working as strictly as asked.

State: `AI.shortlist` (up to 20 currently *tracked* candidates — mutable, entries get replaced
over time) and `AI.reserve` (backup candidates, pre-ranked by projection, not currently
tracked), with parallel arrays `AI.stats` (running avg/min/max per tracked slot), `AI.chances`
(last computed chances result per slot, or `null`), and `AI.visible` (boolean, whether that
slot currently clears the 5% bar). `aiCandidates`, the array actually rendered, is
`AI.shortlist` **filtered to only the currently-visible slots**, sorted by avg — length 0–20.

- **Start** (`startAiSimulation()`) — generates a pool of `AI_POOL_SIZE` = 200 candidates via
  the same `findTopCandidatesByProjection()` used by Auto Simulation (squad-deduped,
  captain/constructor capped, sorted by projection — in practice this often returns somewhat
  fewer than 200 distinct legal squads, which is fine). The top 20 become `AI.shortlist`
  (tracked), the rest become `AI.reserve` (held back, best-projection-first) — a much deeper
  reserve than an earlier version's 40, specifically to keep the visible count as close to 20
  as the underlying math allows for as long as possible. Zeroes `AI.stats`, marks every slot
  `visible` until the first chances pass says otherwise, runs one stats batch, and arms
  `setInterval(aiTick, 400)`. Each tick simulates `AI_TICK_BATCH` = 150 more races per tracked
  candidate (20 × 150 = 3000 sims/tick, ~50ms) and folds them into that slot's running
  avg/min/max.
- **Live quality control while running** (`MIN_PICK_CHANCE = 0.05`) — immediately after
  starting, `updateAiChances(300)` runs once synchronously and then again every 2 seconds via
  its own `setInterval` (`AI.chancesTimer`, separate from the stats tick): a lighter 300-sim
  `analyzeTopLineupChances()` pass per tracked candidate (20 × 300 = 6000 sims, ~300ms — fast
  enough for a 2s cadence, too much for every 400ms tick). Any slot whose best-case outcome
  needs an almost-impossible (<5%) result from some individual pick or the constructor is
  marked not-`visible` — and disappears from the rendered table on this same pass, unconditionally.
  Since every pass draws entirely fresh random simulations, a hidden candidate gets an
  independent fresh shot at passing on the *next* pass too — it isn't gone forever just because
  it failed once.
- **Swapping** (`performAiSwaps()`, called at the end of every `updateAiChances()` pass) — best
  effort to nudge the visible count back toward 20, not what makes elimination happen (the
  render-time filter does that unconditionally). Ranks the 20 tracked slots worst-first
  (not-visible ones always rank as worst, then by simulated avg ascending), and for each one,
  evicts and replaces it from `AI.reserve` (best-projection-first, via `.shift()`) if either:
  the slot is not-visible, or the next reserve candidate's *projection* beats that slot's
  *simulated avg*. A freshly swapped-in candidate is immediately seeded with one
  `AI_TICK_BATCH`-sized batch of sims and its own chances check. Stops once `AI.reserve` runs
  out (which it eventually will, even at 200-deep, given how often candidates fail the check —
  verified in testing: reserve hit 0 within ~10s of continuous swapping). Reports how many slots
  were swapped this pass (`AI.filteredOutCount`, reset to 0 whenever the reserve is empty or
  nothing needed swapping — an earlier version had a bug here: an early-return path on empty
  reserve skipped resetting this, so the status kept showing a stale nonzero swap count forever
  after the reserve ran dry; fixed).
- **Stop** (`stopAiSimulation()`) — clears both the stats timer and the chances timer, then
  runs one final, more precise `updateAiChances(1000)` pass (which also runs `performAiSwaps()`
  one more time) for a settled result instead of the noisier live 300-sim estimate. Being a more
  extreme "best of 1000" rather than "best of 300," this final pass is *more* likely to trip the
  5% filter, not less — don't be surprised if the count drops (even to zero) right at Stop.
  Status reads "computing final chances for each lineup…" while it runs, then "Stopped after N
  total simulations" plus a count/swap note.
- Clicking **Start** again always generates a fresh 200-candidate pool and resets everything
  (stats, chances, visibility, reserve, swap count) — it's a restart, not a resume.
- If the visible count is ever 0 (all currently-tracked candidates are failing at once), the
  table shows a message in place of rows rather than looking empty/broken — worded differently
  depending on whether it's still running ("keep waiting, every pass draws a fresh sample") or
  stopped ("Click Start to try a fresh pool").
- The table looks like Auto Simulation's (same columns plus a running **Sims** count and a
  **Chances** column, populated as soon as the first live pass completes — not just after Stop)
  with its own scrollable/sticky-header wrapper (`#ai-results-wrap`). The **Load** button
  (`loadAiCandidate()`) only appears once stopped (`renderAiTable()` checks `AI.running`) — the
  ranking and visible set keep shifting while running, so loading a row mid-run could load a
  lineup that's no longer where you clicked it, or that's about to fail the next check; Stop
  first, then Load. Same copy-into-`lineup`-then-jump-to-The-Chances behavior as Auto
  Simulation's Load (see below) — and since every visible candidate already has a `.chances`
  result from the live/final pass, Load is effectively instant (no on-the-spot re-simulation) —
  just against the `aiCandidates` array instead of `autoCandidates`.
  Rendering is split into `renderAiResults()` (filters `AI.shortlist` down to visible slots,
  sorts by avg into `aiCandidates`, then calls `renderAiTable()`) and `renderAiTable()` (just
  draws whatever's currently in `aiCandidates`, or the empty-state message) — kept separate so
  `updateAiChances()`/`performAiSwaps()` can trigger a redraw without duplicating the filter/sort
  logic.
- Because averages only get more precise the longer a given candidate stays tracked (standard
  error shrinks with more samples), leaving it running and checking back later gives a tighter
  estimate of each surviving candidate's true average than Auto Simulation's one-shot 1000-sim
  pass — on top of the list itself having been continuously upgraded via swaps.

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

## Testing AI tab (backtest against a chosen past season)

Answers "would the AI's picks have actually scored well in a specific real season?" using
genuine historical DK points — not a projection, not a simulation. Important data caveat,
shown directly in the tab's own UI: **there are no real historical DraftKings salaries or
contest payouts anywhere** (DK doesn't archive old pricing, and this project only started
saving weekly salary snapshots recently — one snapshot exists on disk, for the current race).
So this uses **today's** salary cap and driver salaries as a stand-in for pricing in every past
race tested — the scores shown are real, but "would this have made money" is a rough proxy,
not a real payout simulation. Never fabricate a dollar figure here; there's no real data to
base one on.

- **Season dropdown** (`populateTestingYearDropdown()`, run once at page load) — lists every
  year from `F1_FIRST_SEASON` = 1950 (F1's first World Championship season) through
  `TESTING_LAST_SEASON` = 2025, newest first. Years with no data actually fetched yet (checked
  against `D.raceHistory`) are labeled "(no data fetched yet)" right in the option text, so
  it's obvious before you even click Run — this project has only backfilled a handful of
  recent seasons so far (2023–2026 as of this data pull; 2026 doesn't appear in the dropdown
  since it's the in-progress season, not one of the 1950–2025 past seasons being backtested).
  Defaults to the most recent season that actually has data, falling back to 2025 if somehow
  none do.
- **Run backtest** (`runTestingAi()`):
  1. Reads the selected `<option>` value, filters `D.raceHistory` down to just that year's
     races (sorted by round). If none exist for that year, shows a direct "No race data
     fetched for {year} yet — run `python3 src/fetch_jolpica.py`..." message and stops there,
     no picking/scoring wasted.
  2. `pickTestingLineup()` — picks one lineup using today's rules: the same
     `findTopCandidatesByProjection(20)` + `evaluateCandidate(c, 500)` shortlist-then-simulate
     approach Auto Simulation uses, takes the highest-avg result. This is "the AI's" pick for
     the current race week, not something the user builds by hand, and is **the same pick
     regardless of which season is being tested** — the point is checking how one present-day
     recommendation would have fared against different real seasons, not re-optimizing per era.
  3. For each race in that season (`scoreLineupAtHistoricalRace()`) — sums the picked lineup's
     real point totals for that race (captain × 1.5, same as everywhere else) if and only if
     every pick (5 drivers + the constructor) actually appears in that race's data; if any pick
     wasn't racing that event (almost always the case for older seasons — a driver simply
     didn't exist in F1 yet), the row is marked "N/A — driver(s) not in that race's field"
     rather than silently scoring 0. Testing the 2025 season found full data for all 24 races;
     testing 2023 found 0 of 22, since that lineup included several 2025/2026-rookie picks who
     weren't racing in 2023 at all — an honest, expected result given how far back rookies'
     data doesn't reach, not a bug.
  4. `fieldAverageLineupScore()` — a cheap comparison baseline per race: the average real DK
     score across all drivers that race, applied as if an "average" driver filled all 5 driver
     slots (captain included, at 1.5×) plus the average constructor score — O(n), no
     combinatorial search needed. Deliberately *not* a true "best possible lineup that race"
     (which would need a full `fiveCombos()`-style search per race) — just a rough "did we beat
     a typical lineup" signal.
- Summary tiles: races that season, how many had full data, the average actual score across
  those, and how often the tested lineup beat the field-average baseline (count and %) — 83%
  across the 2025 season in testing.
- Full per-race table (round, race, our score, field-average baseline, delta) for the selected
  season only, in a scrollable container.
- Nothing here is persisted — re-running "Run backtest" (same season or a new one) re-picks a
  lineup from scratch (new random Monte Carlo sims in the evaluation step, so the exact pick
  can vary run to run) and rescoring is deterministic given that pick (real historical data, no
  randomness in the scoring itself).

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
