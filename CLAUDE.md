# F1 DFS Project

DraftKings F1 fantasy analysis. Goal: build good $0.25-contest lineups, learn DFS strategy.

## Skills — check first

Before working on this project, read the relevant skill in `skill/`:

- `skill/data-process.md` — how and when to pull all data (weekly refresh commands,
  qualifying, penalties/news checking, pre-lock signals, API reference, data inventory).
  Follow it step by step for any race-week data work.

Add new skills here as recurring workflows emerge (e.g. lineup-optimization.md,
post-race-review.md).

## Key facts

- Scoring rules: `config/scoring.yaml` — hand-verified against DK; treat as source of truth.
- Roster: 1 CPT (1.5x pts, 1.5x salary) + 4 D + 1 CNSTR, $50K cap.
  DK rule: max 2 picks (drivers+constructor combined) from one team.
- Lineups lock at race start; the edge window is Sat quali → Sun race start.
- Jolpica quali endpoint shows qualifying classification, NOT the penalized grid —
  check penalties manually (see skill/data-process.md § ③).
- DK salary snapshots in `data/dk_salaries/` are irreplaceable — never delete.
- Dashboard: `dashboard/index.html` (plain file, no server). Rebuild data with
  `python3 dashboard/build_data.py` after refreshing data.
