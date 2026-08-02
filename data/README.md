# `data/` — how to (re)generate it

This whole folder is **git-ignored** (see the repo `.gitignore`), so a fresh clone has an
empty `data/` — only this README comes along. Everything else here is regenerated locally by
the scripts in `../src/`. That's deliberate: race data is free to re-fetch, so we don't commit
it. This file is the instructions for rebuilding it so **your data matches mine**.

Run every command below from the **repo root** (`f1-dk/`), not from inside `data/`.

---

## 0. Prerequisites (one time)

- **Python 3.9+** (I'm on 3.9.6).
- Two packages: `pandas` and `requests`.

```bash
python3 -m pip install --user pandas requests
```

The APIs are all **free and need no key or login**, so there's nothing to configure.

---

## 1. Fastest path — the per-year data you see in this folder

The `data/2021/ … data/2026/` folders are produced by **one script**:

```bash
python3 src/fetch_by_year.py
```

With no arguments it fetches the **last 5 seasons + the current one** — in 2026 that's exactly
`2021`–`2026`, which is why those six folders exist. To pull specific seasons instead:

```bash
python3 src/fetch_by_year.py 2019 2020 2021
```

It's polite to the API (0.8s between calls, automatic back-off on rate limits) so a full run
takes a few minutes. It **caches every response** under `data/<year>/raw/`, so re-running is
cheap and only fetches what's missing — safe to re-run any time (e.g. to pick up new races, or
to retry rounds that got rate-limited the first time — it prints which ones to retry).

### What it writes (one self-contained folder per year)

```
data/<year>/
├── raw/
│   ├── schedule.json
│   ├── r01_results.json        # cached raw API responses, one per round
│   ├── r01_qualifying.json
│   └── …
├── results.csv                 # one row per driver per race
└── qualifying.csv              # one row per driver per qualifying session
```

`results.csv` columns:
`year, round, race_name, circuit_id, date, driver_id, driver_code, constructor_id, grid,
finish_position, position_text, status, laps, points_f1, fastest_lap_rank`

`qualifying.csv` columns:
`year, round, driver_id, constructor_id, quali_position, q1, q2, q3`

Source: **Jolpica** (`api.jolpi.ca`, the Ergast successor).

---

## 2. The dashboard's data (only if you want to rebuild `dashboard/data.js`)

The interactive dashboard does **not** read the per-year folders above. `dashboard/data.js` is
committed to the repo, so the dashboard already works from a clone with **no data at all**.
You only need this section if you want to regenerate that file yourself.

It's fed by a separate *flat* pipeline that lands in `data/raw/` and `data/processed/`:

```bash
python3 src/fetch_jolpica.py       # backfill race + quali results  -> data/raw/, data/processed/results.csv + qualifying.csv
python3 src/dk_points.py           # simulate DK points per driver   -> data/processed/dk_driver_points.csv + dk_constructor_points.csv
python3 dashboard/build_data.py    # regenerate dashboard/data.js from processed/ + latest salaries
```

`build_data.py` also needs a DraftKings salary file (see next section). It reads the **newest**
CSV in `data/dk_salaries/`.

> Heads-up: `fetch_jolpica.py` defaults to backfilling **1950→current**, which is a long first
> run (thousands of cached JSON files). It's incremental and cached like the per-year script, so
> subsequent runs are fast.

---

## 3. DraftKings salaries — the one thing you *can't* reproduce exactly

```bash
python3 src/fetch_dk_salaries.py   # current week's DK salaries -> data/dk_salaries/<snapshot>.csv
```

This only ever returns the **salaries for the upcoming race**. DraftKings publishes no history,
so **past weeks' salary snapshots cannot be re-fetched** — that's why the repo guide calls the
files in `data/dk_salaries/` "irreplaceable, never delete."

**So for identical results:** race and qualifying CSVs will match mine byte-for-byte (historical
API data is fixed), but if you want the *exact* salary snapshots I used for past races, copy my
`data/dk_salaries/*.csv` files over directly — you can't regenerate them. For the current race
week, running the command above gives us the same file.

---

## 4. What's reproducible, and what isn't

| Data | Same as mine? | Why |
|---|---|---|
| Past race & qualifying CSVs | ✅ Byte-identical | Historical results never change |
| Current season (2026) | ⚠️ Depends on when you run | It grows as races happen — re-run after each GP |
| `data/dk_salaries/` past weeks | ❌ Not regenerable | DK publishes no salary history — copy the files directly |
| `data/dk_salaries/` current week | ✅ Same | Fetched live from DK for the upcoming race |

---

## 5. Troubleshooting

- **`ModuleNotFoundError: pandas` / `requests`** — run the install in step 0.
- **"rate limited, waiting Ns…"** — normal; the scripts back off and retry automatically. If a
  round is skipped after retries, just re-run the same command — caching means it only re-fetches
  the misses.
- **"No race data fetched for {year}"** in the dashboard's Testing tab — you haven't run
  `fetch_jolpica.py` yet (that tab reads the flat pipeline's history).
- **Wrong working directory** — all paths are relative to the repo root; the scripts resolve
  `data/` from their own location, so run them as `python3 src/…` from `f1-dk/`.
