# Simulation — Technical Version

> **Audience label: TECHNICAL.** This is the precise, implementation-level writeup. For a
> plain-language version of the same content, see [simulation-simple.md](simulation-simple.md).

How we simulate a lineup's race outcome — the actual modeling choices, not just what the
buttons do (see [dashboard.md](dashboard.md) for that). This file is meant to grow over time:
right now there's one method (what `simulateRace()` in `dashboard/index.html` actually does
today), and we'll add alternative/experimental methods here as we build them.

## What "simulating a lineup" means here

Given a lineup (1 Captain + 4 Drivers + 1 Constructor), generate one plausible race outcome —
grid, finishing order, DNFs, laps led, fastest lap — then score it with the real DK rules
(`config/scoring.yaml`). Run it many times (a click, or thousands of times in Auto/AI
Simulation) to see the distribution of outcomes, not just one guess. This is different from
the Testing AI tab, which doesn't simulate anything — it replays a lineup against *real*
historical results. Simulation is for races that haven't happened yet (or haven't been
qualified for yet); Testing AI is a backtest against real ones.

## Method 1 (current default): historical-distribution Monte Carlo

Implemented in `simulateRace()`. Every driver/constructor has a handful of season-to-date
stats baked into `dashboard/data.js` by `build_data.py`: `avgFinish`/`stdFinish`,
`avgGrid`/`stdGrid`, `dnfRate`, `avgDk`. The simulation samples from those per-entity
distributions independently each run:

1. **Qualifying (grid).** Each driver's grid position is sampled as
   `avgGrid + gauss() × stdGrid` (Gaussian via Box-Muller), then the field is ranked by that
   score into grid 1..N. This is a proxy for "how well they tend to qualify," not a real
   qualifying simulation (no Q1/Q2/Q3 knockout, no track-specific effects).
   - **Override:** if a real grid has been entered in the Driver's Qualifying box and applied
     (`fixedGrid` is set), this step is skipped entirely — every driver's grid comes straight
     from the real, known grid instead. Everything downstream (steps 2–4) is unchanged and
     still random.
2. **DNF.** Independent Bernoulli trial per driver against their `dnfRate`. No correlation
   between drivers (a first-lap pileup that takes out three cars isn't modeled — each DNF is
   its own coin flip).
3. **Race pace / finishing order.** Finishers get a pace score:
   `0.45 × grid + 0.55 × (avgFinish + gauss() × stdFinish)` — blends where they started with
   their historical finishing tendency, weighted slightly toward the historical side. Lower
   score = better finish. DNFs are appended after all finishers, ordered by how many laps they
   completed (`Math.random() × totalLaps × 0.88`, so a DNF can happen at any point up to ~88%
   race distance).
4. **Laps led.** Whoever finishes first leads 45–80% of race laps
   (`totalLaps × (0.45 + Math.random() × 0.35)`); the next three finishers split most of the
   remaining laps at random. Nobody outside the top 4 finishers leads any laps.
5. **Fastest lap.** Picked uniformly at random from the top 10 classified (non-DNF) finishers —
   no pace-based weighting, a slow-but-classified P10 has the same shot as the leader.

**What this method is good at:** cheap enough to run tens of thousands of times per second
(needed for Auto/AI Simulation's combinatorial search), captures each entity's *own* historical
variance reasonably well, and responds correctly to a real entered grid when you have one.

**What it doesn't capture** (candidates for a future method, once we design one):
- No correlation between drivers — a rain race or a first-lap incident should make multiple
  DNFs/bad finishes more likely together, not independently.
- No track-specific modeling (Monaco's grid ≈ finish; Spa/Monza reward overtaking) — see
  `analyze.py`'s per-circuit output, which isn't wired into the simulator at all yet.
- No qualifying-session structure (Q1/Q2/Q3 knockout, red flags) — grid is a single Gaussian
  draw, not a simulated session.
- No weather modeling, even though `config/race_notes.yaml` → `weather` notes exist and are
  read into `data.js` (`data.raceNotes.weather`) — nothing currently consumes them for
  simulation purposes.
- No tyre-strategy modeling, despite `race_notes.yaml` → `tyre_plans` existing and being shown
  in its own dashboard box — also not wired into `simulateRace()`.
- Fastest lap and laps-led are essentially uniform-random among likely candidates, not modeled
  off any actual pace signal.

## Other simulation methods

As we design alternatives they go here, each as its own `## Method N: <name>` section: what
problem it targets (usually a gap listed above), how it works, and where it's implemented (or a
note if it's still a proposal). Method 2 below is now implemented.

## Method 2 (implemented): street-circuit adjustments

**Framing — "street circuit" is not one racing profile, it's two things bolted together, and
the simulator should treat them as separate knobs:**

1. **Overtaking difficulty is per-circuit, NOT a blanket "street" trait.** Monaco and Singapore
   (Marina Bay) are the hardest places to pass on the whole calendar — Monaco averages only
   ~10–12 on-track overtakes per race (lowest for ~25 years; the last on-track pass *for the
   lead* was 1996), so **grid position ≈ finish position**. But Baku, Jeddah and Las Vegas are
   *also* street circuits and produce lots of passing — Las Vegas had ~82 overtakes in 2023 and
   ~60 in 2024 (the most of any race that year) thanks to long straights + DRS. So the
   overtaking lever is keyed to the specific circuit, never to "is it a street track."
2. **What actually unifies street circuits is walls with no run-off → more crashes → far higher
   safety-car and DNF rates.** Public stats: in *dry* races the safety-car probability is ~65%
   at street circuits vs ~30% at permanent tracks (wet: ~75% vs ~59%). Baku has historically
   sat ~50% SC; Singapore had at least one safety car in *every* race from 2008 until the streak
   finally broke in 2024 (~24 SC deployments over 16 races, ~1.5/race), and runs high attrition
   (~12 DNFs across 2022–2024, ~4/race). All numbers are approximate/historical — they're
   parameter seeds, not exact constants.

These map to two independent knobs added to `simulateRace()`:

**Knob 1 — grid→finish coupling (overtaking), affects steps 1 & 3.** Replace the fixed
`0.45 × grid + 0.55 × (avgFinish + gauss × stdFinish)` weighting with a per-circuit `wGrid`:
`pace = wGrid × grid + (1 − wGrid) × (avgFinish + gauss × stdFinish)`.
- Monaco: `wGrid ≈ 0.80` (grid is destiny; also shrink `stdFinish`, positions are sticky).
- Singapore: `wGrid ≈ 0.65–0.70`.
- Baku / Jeddah / Las Vegas: `wGrid ≈ 0.40–0.45` (default, or even lower — pace beats grid).
- Every other circuit keeps today's `0.45`.
At the sticky tracks, also raise the leader's laps-led share (step 4) — e.g. pole leads ~60–90%
at Monaco — since track position barely changes.

**Knob 2 — correlated safety-car / attrition, affects step 2.** This is where street circuits
break Method 1's "every DNF is an independent coin flip" assumption. Add a per-race draw:
- `safetyCar = random() < pSC`, with `pSC` per circuit (Monaco/Singapore ~0.90+, Baku ~0.55,
  permanent tracks ~0.30; add ~0.10–0.15 if `data.raceNotes.weather` says wet).
- Baseline: multiply every driver's `dnfRate` by a street factor (~×1.4–1.8) for the run.
- If `safetyCar` fired: **(a)** trigger a first-lap/restart *incident* that can collect 1–3 cars
  at once (sample a small correlated cluster of extra DNFs — the multi-car pileup Method 1
  explicitly can't model), and **(b)** bunch the field — add extra Gaussian noise to the
  finishing pace of cars that would still have to pit, modelling the undercut/overcut lottery a
  cheap SC pit stop creates. That noise is what makes street races high-variance and rewards
  contrarian DFS picks.

**Wiring (as built):** lives entirely in `dashboard/index.html`. A `STREET_CIRCUITS` map holds
the per-circuit `{ wGrid, pSC, dnfFactor }` (Monaco `0.80/0.90/1.5`, Singapore `0.68/0.95/1.7`,
Baku `0.42/0.55/1.5`, Las Vegas `0.42/0.55/1.4`, Jeddah `0.45/0.65/1.6`), and `STREET_CFG` is
resolved once at load by matching `D.raceName` against that map (year suffix ignored). When it's
non-null, `simulateRace()` applies both knobs; when null, every term collapses to the old
constants (`wGrid=0.45`, `dnfMult=1`, `safetyCar=false`), so non-street races are byte-identical
to Method 1. Because Auto/AI Simulation and The Chances all call `simulateRace()`, the model
propagates to every tab automatically. A "Street circuit" banner is injected into each tab when
`IS_STREET`. Detection is by race name; add a race to `STREET_CIRCUITS` to extend it. Still TODO:
have `build_data.py` emit these per-circuit (keyed by circuit, not name) and wire the
already-present `data.raceNotes.weather` into the wet SC bump (`pSC + ~0.10–0.15`).

*Data sources for the numbers above:*
[RacingNews365 — Monaco overtakes](https://racingnews365.com/how-often-are-overtakes-at-the-monaco-grand-prix),
[F1StatsGuru 2024 overtakes-per-race](https://www.threads.com/@f1statsguru/post/DENKaKHSOGC),
[Marina Bay Street Circuit — safety cars/DNFs (Wikipedia)](https://en.wikipedia.org/wiki/Marina_Bay_Street_Circuit),
[Odds2Win — safety-car probability by circuit type](https://odds2win.bet/motorsports-betting/safety-car-betting/).
