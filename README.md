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
│   └── data-process.md     # THE data-pull guide: weekly refresh, penalties, pre-lock signals
├── config/
│   └── scoring.yaml        # DK scoring rules (hand-verified — source of truth)
├── data/
│   ├── raw/                # fetched API data (json), cached
│   ├── processed/          # tidy csv tables (results, qualifying, dk points)
│   └── dk_salaries/        # weekly DK salary snapshots (keep all — irreplaceable)
├── src/
│   ├── fetch_jolpica.py    # backfill race + qualifying results
│   ├── fetch_dk_salaries.py# current DK salaries via DK API
│   ├── fetch_dk_contests.py# list F1 contests (find the $0.25 game)
│   ├── dk_points.py        # DK points simulator (what would each driver have scored?)
│   └── analyze.py          # value analysis: pts/$1K, captain value, place differential
└── dashboard/
    ├── index.html          # lineup builder + race simulator (open directly in browser)
    ├── build_data.py       # regenerates data.js from processed data + salaries
    ├── data.js             # generated — do not edit
    └── logos/              # team logos (from DK CDN)
```

## Workflow (race week)

1. Saturday after qualifying: export DK salary CSV → drop into `data/dk_salaries/`
2. Run analysis / optimizer → pick lineup
3. Submit on DK before race start ($0.25 contest)
4. After race: refresh data, compare predicted vs actual, learn

## Setup / run

```bash
python3 src/fetch_jolpica.py     # backfill 2023–2025 (cached in data/raw/)
python3 src/dk_points.py         # compute simulated DK points per driver per race
python3 src/analyze.py           # value patterns report
```
