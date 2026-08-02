# Outstanding refactors — `src/vis/` and the simulator

Tasks A, B, C, E and F of the original plan are **done** (JS/CSS extracted from the Python
format string, the two page builders unified, long functions broken up, the dead
derived-outline path removed). Doubled braces went 288 → 0 and `replay.js` passes
`node --check`. Two items remain.

---

## D — split `assets/replay.js` (750 lines, one flat scope)

It works and it's now lintable, but it's a single scope with module-level mutable state
(`ROT`, `scale`, `laneScreen`, `TRACK_POS`, `lastOrder`, `marks`, `cursor`). Every
cache-invalidation bug so far came from that: `laneScreen` used before its `let`,
`TRACK_POS` not cleared on race switch. Four ES modules would make those structurally
impossible rather than merely fixed:

- `geometry.js` — projection, rotation, arc-length ↔ x/y (`toTrackCoords`,
  `fromTrackCoords`, `nearestTrack`). Pure functions, no DOM, unit-testable.
- `render.js` — canvas drawing (`drawTrack`, `drawCar`, `drawPitLane`, `drawStartMarker`).
- `tower.js` — the timing panel, owning its own DOM refs.
- `player.js` — playback clock, seek, speed, race switching. The only mutable state.

Each should take state as arguments rather than reaching for globals. Verify with
`src/vis/selftest.py` (30 checks) plus in-browser DOM measurements against a baseline; no
rendered output may change.

## G — extract the simulator and give it an entity model

**Where the simulator actually is:** not `src/sim/` (280 lines, which only scores past races
and prints value tables) but **1368 lines of JavaScript inside `dashboard/index.html`**
(60 functions: `simulateRace()`, `simulateCandidateScore()`, `runAutoSim()`,
`startAiSimulation()`). Any "give the car a class" work has to extract that first — there is
no Python object model to add a class to.

### A live bug to fix before restructuring

The two DK scoring implementations disagree. Verified by reading both:

| | JS `scoreDriver()` | Python `src/sim/dk_points.py` |
|---|---|---|
| **Laps led** | scored: `led × 0.25` | **absent — always 0** |
| Pit-lane start (`grid == 0`) | n/a (simulated grids are 1..22) | remapped to field size |
| Teammate bonus | strictly ahead of the other car | best finisher in team (needs ≥2 cars) |

The laps-led gap is the significant one: a **simulated** race leader scores 10–20 pts more
than the **same real race** scored by the backtest, so projections and backtests aren't on
the same scale and every backtest is biased against front-runners. Jolpica `/laps`
(doc/data.md §1.4) supplies the real lap-leader data. This is exactly the failure mode a
single shared scoring implementation prevents — which is the strongest argument for the
entity model, stronger than any tidiness case.

### The entity model

A driver is not a realisation of a car. A constructor fields two cars, each with one driver,
and the thing that scores is the pairing:

```
Constructor ──┬── Entry (car #1) ── Driver
              └── Entry (car #2) ── Driver
```

`Entry` — one car, one driver, one race — is the natural simulation unit: it takes the grid
slot, the DNF roll, the finish, the laps led. This matters concretely for DK: constructor
bonuses (`both_cars_classified`, `both_cars_in_points`, `both_cars_on_podium`) are only
computable from *both* entries, the teammate bonus is entry-vs-entry, and "max 2 picks per
team" is a constraint over pairings.

```
Driver        code, name, number                        identity only
Constructor   id, name, colour, entries[]               identity + its 2 cars
Entry         driver, constructor, salary, salaryCpt,   the simulation unit
              form: Form, grid, finish, dnf, lapsLed
Form          avgFinish stdFinish avgGrid stdGrid       measured distribution
              dnfRate avgDk races  + prior/clamp rules
RaceState     entries[], totalLaps, weather, fixedGrid  one simulated race
Scoring       loaded from config/scoring.yaml           rules, not data
```

**Do not** model `Car.pace` and `Driver.skill` separately. Every stat available
(`avgFinish`, `dnfRate`) is measured from finishing positions, which *conflate* driver skill
and car performance — they cannot be separated from results alone, and splitting them would
fabricate precision. Only OpenF1 telemetry (speed traps, sector times) could justify a
genuine car-performance term, because it would be measured.

`Form` deserves its own object: the 20-race window, the σ floor of 1.5, the `dnfRate` clamp
to [0.03, 0.35] and the new-driver priors are currently scattered between
`dashboard/build_data.py` and the JS.

### Order

1. Fix the laps-led divergence, so the refactor can be verified against known-correct numbers.
2. Extract the simulation JS out of `index.html` into an asset (same split as task B).
3. Introduce the entity model in one place; have the dashboard consume it.
4. Mirror it in `src/sim/model.py` so `dk_points.py` and the simulator share one scoring path.
5. Test: scoring a known race matches hand-computed DK points; a simulated field respects the
   cap and the max-2-per-team rule; σ floors and clamps hold. Seed the RNG so steps 2–4 can be
   shown not to change simulated distributions.

---

## Rules that earned their place today

1. **Never edit a multi-line block by slicing on `str.index()`.** It silently matched a
   docstring instead of code and ballooned a file to 486k lines — unrecoverable, because the
   file was untracked. Use exact-match assertions or the Edit tool.
2. **Verify "dead code" by call site, never by docstring.** `layout._order_path` was listed as
   dead; it's called unconditionally by `pit_lane()` and deleting it would have silently
   removed the pit lane from every replay. Its docstring lied.
3. **Read the JS console every time**, not just screenshots. Three errors rendered a blank or
   stale canvas with no visual clue why.
4. **Measure the quantity the user sees.** Checking car positions against raw frame
   coordinates gave 37% off-track; hooking the actual draw call gave 0.088%.
