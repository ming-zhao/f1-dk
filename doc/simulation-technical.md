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

None yet — this is where we'll add alternative approaches as we design and build them
together. Each new method should get its own `## Method N: <name>` section here: what problem
it's trying to solve (usually one of the gaps listed above), how it actually works, and where
it's implemented (or a note if it's still a proposal, not yet in code).
