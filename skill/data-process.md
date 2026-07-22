# Data Process Guide

How to pull everything needed to build a DK lineup, and when.
All sources are free / no API key unless noted.

---

## Timeline for a race week

```
                 lineups lock at RACE START
                            │
 Fri practice   Sat quali   │  Sun race
 ────────────┬──────────────┼────────────┬──────────
             │              │            │
             │  ① refresh salaries       │  ④ post-race refresh
             │  ② pull quali results     │
             │  ③ check penalties/news   │
             │     (KEY WINDOW: Sat      │
             │      evening → Sun AM)    │
```

The whole edge lives in the window **after Saturday qualifying, before Sunday
race start**: that's when you know the grid, penalties, and weather but DK
salaries were set days earlier and don't react.

---

## ① Weekly refresh — automated scripts

Run these Saturday after qualifying (all cached, safe to re-run):

```bash
cd ~/Documents/projects/f1

python3 src/fetch_dk_contests.py --cheap   # find the $0.25 contest
python3 src/fetch_dk_salaries.py           # this week's salaries -> data/dk_salaries/
python3 src/fetch_jolpica.py               # latest results incl. yesterday's quali
python3 src/dk_points.py                   # recompute simulated DK points
python3 dashboard/build_data.py            # rebuild dashboard data.js
```

---

## ② Qualifying results (Jolpica)

- Endpoint: `https://api.jolpi.ca/ergast/f1/<year>/<round>/qualifying.json?limit=40`
- Updates within hours of the session (verified: available same day).
- **CAVEAT:** this is the *qualifying classification*, NOT the starting grid.
  Penalties are not applied here. The true penalized grid only appears after
  the race in the results endpoint's `grid` field. For pre-race grid you must
  apply penalties manually (see ③).

## ③ Penalties & late-breaking news (MANUAL — the highest-value step)

No good free API exists for pre-race penalties. Check these, in order:

| Source | URL | What you get |
|---|---|---|
| FIA decision documents | fia.com/documents (filter: current event) | Official grid penalties, the ground truth |
| F1.com latest news | formula1.com/en/latest/all | Penalty announcements in plain English |
| r/formula1 | reddit.com/r/formula1 | Fastest aggregation; check the race-weekend thread |
| RaceFans / The Race | racefans.net, the-race.com | Good penalty roundup articles |

What to look for, and why it matters for DK:

- **Grid penalties (engine/gearbox/battery components)** — THE big one.
  A fast car starting midfield/back = huge place-differential upside.
  Historically the single most profitable DK F1 angle.
  → e.g. 2026 Belgian GP: Norris P3→P13 (10-pl), Hadjar 30-pl, Alonso 20-pl.
- **Pit-lane starts** — driver takes new parts under parc fermé breach; starts
  from pit lane. Max differential upside, but usually means the team expects
  a hard race.
- **Driver substitutions** — affects "defeated teammate" bonus and constructor
  "both cars" bonuses (see scoring.yaml notes).
- **Sprint weekends** — sprint sets/changes grid dynamics; DK sometimes runs
  separate sprint contests. Check the contest's game set.

## ④ Other pre-lock signals worth checking

| Signal | Source | DK relevance |
|---|---|---|
| Weather forecast (rain %) | any weather site for the circuit; openf1 `weather` endpoint has live session data | Rain = chaos = DNFs + big differential swings. Favors consistent midfield drivers, hurts chalk lineups |
| Tyre allocation / strategy notes | F1.com, Pirelli preview | 1-stop vs 2-stop affects overtaking and variance. Record per-team plans in `config/race_notes.yaml` → `tyre_plans` (keyed by constructor id) — shown in the dashboard's "Tyre plans" box after `dashboard/build_data.py` |
| Track characteristics | our own data: `analyze.py` per-circuit | Spa/Monza = overtaking = differential points; Monaco = grid ≈ finish, qualifying is everything |
| FP2 long-run pace | The Race / F1 analysis articles | Better predictor of race pace than qualifying. Record per-driver practice summaries (pace, degradation, issues) in `config/race_notes.yaml` → `driver_performance` (keyed by driver code) — shown in the dashboard's "Driver Performance" box after `dashboard/build_data.py` |
| DK ownership/chalk | not available free pre-lock | In a $0.25 GPP, being contrarian on 1-2 picks helps; don't need data, just don't copy the obvious lineup |

## ⑤ Post-race (Sunday evening or Monday)

```bash
python3 src/fetch_jolpica.py     # pulls the completed race
python3 src/dk_points.py         # recompute
```

Then compare: what did my lineup actually score vs the simulator's range?
Log lessons in this file or the journal.

---

## Data inventory (what lives where)

| Path | Contents | Refreshed by |
|---|---|---|
| `data/raw/*.json` | Cached Jolpica API responses (results, quali, schedules 2023–2026) | `fetch_jolpica.py` (only fetches missing) |
| `data/processed/results.csv` | One row per driver per race: grid, finish, status, laps, fastest-lap rank | `fetch_jolpica.py` |
| `data/processed/qualifying.csv` | One row per driver per quali: position, Q1/Q2/Q3 times | `fetch_jolpica.py` |
| `data/processed/dk_driver_points.csv` | Simulated DK points per driver per race, itemized | `dk_points.py` |
| `data/processed/dk_constructor_points.csv` | Simulated DK constructor points per race | `dk_points.py` |
| `data/dk_salaries/<race>.csv` | DK salary snapshot per race week (KEEP ALL — builds salary history over time) | `fetch_dk_salaries.py` |
| `dashboard/data.js` | Bundled data for the dashboard | `dashboard/build_data.py` |

## API quick reference

| API | Base URL | Key? | Limits | Notes |
|---|---|---|---|---|
| Jolpica | `api.jolpi.ca/ergast/f1/` | no | bursty 429s; scripts retry | History to 1950. Results/quali/grid/status |
| OpenF1 | `api.openf1.org/v1/` | no | 3 req/s | 2023+. Weather, positions, stints, radio. Live data needs paid tier (not needed — lineups lock pre-race) |
| DK lobby | `draftkings.com/lobby/getcontests?sport=F1` | no | be gentle | All F1 contests, entry fees, draft group ids |
| DK draftables | `api.draftkings.com/draftgroups/v1/draftgroups/<id>/draftables` | no | be gentle | Salaries (CPT slot + D slot), FPPG |
| DK gametype rules | `api.draftkings.com/lineups/v1/gametypes/380/rules` | no | — | Roster structure, cap. Scoring itself is in `config/scoring.yaml` (hand-verified) |

## Known gaps / wishlist

- **Penalized starting grid pre-race**: manual only (③). Could scrape FIA docs
  PDF but format is inconsistent; revisit if manual checking gets old.
- **Laps led**: not in Jolpica results; approximated as 0 in dk_points.py
  backtest (small distortion, ~0.25/lap only for leaders). OpenF1 `position`
  data could reconstruct it — TODO if backtest accuracy matters more later.
- **Historical DK salaries**: DK doesn't serve past weeks. We snapshot every
  week into `data/dk_salaries/` — never delete these.
- **Ownership data**: not free pre-lock. Post-contest CSV export from DK shows
  field ownership — could save those too for learning.
