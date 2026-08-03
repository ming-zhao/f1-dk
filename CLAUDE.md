# F1 DFS Project

DraftKings F1 fantasy analysis. Goal: build good $0.25-contest lineups, learn DFS strategy.

## Skills — check first

Before working on this project, read the relevant skill in `skill/`:

- `skill/data-process.md` — how and when to pull all data (weekly refresh commands,
  qualifying, penalties/news checking, pre-lock signals, API reference, data inventory).
  Follow it step by step for any race-week data work.
- `skill/dashboard.md` — how to build/rebuild/troubleshoot `dashboard/index.html` and
  `dashboard/data.js` (rebuild workflow, verification, known pitfalls). See also
  `doc/dashboard.md` for what the dashboard actually does, and `doc/sim.md` for how a
  lineup's race outcome actually gets simulated (a living doc — add new methods there as we
  build them, don't just change the code silently).

Add new skills here as recurring workflows emerge (e.g. lineup-optimization.md,
post-race-review.md).

## Key facts

- Scoring rules: `config/scoring.yaml` — hand-verified against DK; treat as source of truth.
- Roster: 1 CPT (1.5x pts, 1.5x salary) + 4 D + 1 CNSTR, $50K cap.
  DK rule: max 2 picks (drivers+constructor combined) from one team.
- Lineups lock at race start; the edge window is Sat quali → Sun race start.
- Jolpica quali endpoint shows qualifying classification, NOT the penalized grid —
  check penalties manually (see skill/data-process.md § ③).
- DK salary snapshots in `data/raw/draftkings/` are irreplaceable — never delete.
- Dashboard: `dashboard/index.html` (plain file, no server). It is GENERATED —
  edit `dashboard/assets/*.js` + `dashboard.css`, then `python3 dashboard/build_page.py`.
  Rebuild the data with `python3 dashboard/build_data.py` after refreshing data.
  The modules are concatenated (not ES `import`) because `file://` blocks module
  loading for the same CORS reason it blocks `fetch()`.
- Code layout: `src/data/` (crawlers, entry point `data_crawler.py`), `src/util/`
  (shared mappings/paths), `src/sim/` (DK points + analysis).
- All crawled data lands in `data/raw/<source>/<year>/`. See `doc/data.md` for every
  table and column; `skill/data-process.md` for how to fetch it.
- `doc/design.md` is the code counterpart to `doc/data.md`: module layout, dependency
  direction, entry points, and the design decisions not to re-litigate. Read it before
  restructuring anything.
