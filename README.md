# F1 DFS (DraftKings Fantasy) Project

Goal: analyze and optimize DraftKings F1 classic contest lineups ($0.25 contests, for fun + learning).

## How it works

DraftKings F1 classic: draft **6 drivers + 1 constructor** under a **$50,000 salary cap**.
Points come from finishing position, place differential (grid vs finish), fastest lap,
laps completed/led, and defensive/overtake bonuses. Lineups lock at race start, so the
key window is **after Saturday qualifying → before Sunday race start**.

## Data sources (all free, no API key)

| Source | URL | Coverage | Used for |
|---|---|---|---|
| Jolpica (Ergast successor) | `api.jolpi.ca/ergast/f1/` | 1950–present | Race results, qualifying, grid, status |
| OpenF1 | `api.openf1.org/v1/` | 2023–present | Positions, stints, weather (later, finer features) |
| DraftKings salaries | manual CSV export from DK lineup page | weekly | Salary + roster for optimizer |

## Project layout

```
f1/
├── README.md
├── CLAUDE.md               # project guide for Claude sessions (points to skill/)
├── skill/
│   ├── data-process.md     # THE data-pull guide: weekly refresh, penalties, pre-lock signals
│   └── dashboard.md        # how to build/rebuild/troubleshoot the dashboard
├── doc/
│   ├── data.md             # every source, table, column, grain — what the data IS
│   ├── dashboard.md        # what the dashboard does
│   └── simulation*.md      # how a lineup's race outcome gets simulated
├── config/
│   ├── scoring.yaml        # DK scoring rules (hand-verified — source of truth)
│   └── race_notes.yaml     # race-week intel: penalties, weather, tyre plans
├── data/
│   ├── raw/<source>/<year>/  # everything the crawler fetches (jolpica, openf1, draftkings)
│   └── processed/            # derived DK points tables
├── src/
│   ├── data/               # one module per source + data_crawler.py (THE entry point)
│   ├── util/               # shared name/id mappings, paths, DK API access
│   └── simulation/         # dk_points.py (DK scoring), analyze.py (value analysis)
└── dashboard/              # index.html + data.js (plain files, no server)
```

## Workflow (race week)

1. Saturday after qualifying: `python3 src/data/data_crawler.py --source draftkings`
2. Run analysis / optimizer → pick lineup
3. Submit on DK before race start ($0.25 contest)
4. After race: refresh data, compare predicted vs actual, learn

## Setup / run

```bash
python3 src/data/data_crawler.py     # crawl every source (cached, safe to re-run)
python3 src/sim/dk_points.py  # compute simulated DK points per driver per race
python3 src/sim/analyze.py    # value patterns report
```
