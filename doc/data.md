# Data — sources, tables, schemas

Complete reference for every piece of data in this project, **organised by source**. Each
top-level section is one source; each dataset it provides gets its own subsection with the full
column list, meanings, and refresh frequency.

**This file is the *what the data is* reference** — every table, column, and grain.
For *how to fetch or rebuild* it, see [`skill/data-process.md`](../skill/data-process.md):
the race-week checklist, refresh commands, penalty sources, and API quick reference. For
*how the code is organised*, see [`design.md`](design.md).

---

## Contents

### Sources

| § | Source | Auth | Coverage | What it gives you |
|---|---|---|---|---|
| [1](#1-jolpica) | **Jolpica** (Ergast successor) | none | results 1950+, laps 1996+, pit stops 2012+ | Race + qualifying results; also lap-by-lap positions, pit stops, championship standings (§1.4–1.8, not yet crawled) |
| [2](#2-openf1) | **OpenF1** | none | 2023–present<br>*on disk: 2025 only* | Sector times, speed traps, tyre stints, pit stops, overtakes, weather, raw telemetry |
| [3](#3-draftkings) | **DraftKings** | none | upcoming race only | Salaries (CPT + D slot), contest list |
| [4](#4-hand-maintained-config) | **Hand-maintained config** | — | current race week | Scoring rules, grid penalties, weather + tyre notes |
| [5](#5-derived-datasets) | **Derived** (computed here) | — | 2023–2026 | DK fantasy points, dashboard bundle |
| [6](#6-cross-source-joins) | — | — | — | How to join across sources |
| [7](#7-known-gaps) | — | — | — | Known gaps |

**Both API sources are free and need no key or login.** Verified live.

### How `data/` is laid out

Everything the crawler fetches lands under `data/raw/<source>/<year>/`, so what you have on
disk is obvious at a glance. Derived tables go in `data/processed/`, and built replay
payloads in `data/replay/<year>/`.

```
data/
├── raw/                        ← everything the crawler fetches
│   ├── jolpica/<year>/
│   │   ├── api/                cached API responses, one file per round
│   │   ├── results.csv         one row per driver per race           §1.2
│   │   └── qualifying.csv      one row per driver per quali          §1.3
│   ├── openf1/<year>/
│   │   ├── api/                cached API responses, one per session
│   │   ├── sessions.csv        one row per session                   §2.1
│   │   ├── laps.csv            one row per driver per lap            §2.2
│   │   ├── drivers.csv  session_result.csv  stints.csv               §2.3–2.9
│   │   ├── pit.csv  overtakes.csv  weather.csv  race_control.csv
│   │   └── telemetry/          ~3.6 Hz car data, opt-in              §2.10
│   ├── circuits/               ← NOT by year: official circuit maps, static
│   │   └── <circuit_key>_<year>.json    outline + rotation + corners §5b
│   └── draftkings/             ← NOT by year: DK serves only the upcoming race
│       └── Belgian_Grand_Prix_2026.csv                               §3.1
│
├── processed/                  ← derived, computed from raw/          §5
│   ├── dk_driver_points.csv
│   └── dk_constructor_points.csv
│
└── replay/                     ← built replay payloads               §5b
    ├── index.json              the race list dashboard/replay.html reads
    └── <year>/<location>.json  e.g. 2024/Monaco.json (~3 MB each)
```

All of `data/` is git-ignored. Re-crawl with `python3 src/data/data_crawler.py`, and
`--list` shows what's currently on disk.

**What's actually there now** (verified, so you can tell a gap from a bug):

| Path | Contents |
|---|---|
| `raw/jolpica/` | **55 year directories.** Only **2021–2026** have `results.csv`/`qualifying.csv` (2,520 result rows). The **1950–1998** directories hold *only* cached API responses — an interrupted backfill, no CSVs. |
| `raw/openf1/` | **2024 and 2025** only, 455 cached responses. No `telemetry/` anywhere — it needs `--telemetry` and is ~73 MB per race. |
| `raw/circuits/` | **48 maps** (24 circuits × 2 seasons), 1.0 MB. Complete for everything crawlable — verify with `python3 src/vis/circuit.py`. |
| `raw/draftkings/` | **Empty**, so `dashboard/build_data.py` and `src/sim/analyze.py` both fail. Needs `data_crawler.py --source draftkings`, and only works when DK has an open draft group. |
| `raw/*.json` (loose) | **1,118 stray files** from the retired flat pipeline. Superseded by `raw/jolpica/<year>/api/`; safe to delete. |
| `processed/` | DK points tables, plus `results.csv`/`qualifying.csv` left over from the old flat pipeline. |
| `replay/` | 2 payloads (~3 MB each) + `index.json`. |

Two traps worth knowing. A **single-round fetch merges into the season CSV** rather than
replacing it, so `data_crawler.py 2025 3` leaves a CSV containing only round 3 — which is how
2025 spent part of today holding 40 rows instead of 479. Re-run without a round number to
rebuild the full season; it's free, since every response is cached. And **an `api/` directory
is not the same as a usable CSV** — the 1950–1998 Jolpica directories prove the point.

### Grain, dataset by dataset

**Grain is a property of each table, not of its source** — Jolpica spans whole-race outcomes to
per-lap positions, and OpenF1 goes from one-row-per-session down to one-row-per-0.27-seconds.
This is the quickest way to see whether a dataset can answer a given question.

| Dataset | § | Source | One row = | Time resolution | Rows per race |
|---|---|---|---|---|---|
| `results.csv` | [1.2](#12-resultscsv) | Jolpica | driver × race | whole race | 20 |
| `qualifying.csv` | [1.3](#13-qualifyingcsv) | Jolpica | driver × quali session | whole session | 20 |
| `laps` *(not crawled)* | [1.4](#14-laps-lap-by-lap-positions-available-not-yet-crawled) | Jolpica | **driver × lap** (position + time) | per lap | ~1100 |
| `pitstops` *(not crawled)* | [1.5](#15-pitstops-pit-stop-timings-available-not-yet-crawled) | Jolpica | pit stop | timestamped event | ~43 |
| `driverstandings` *(not crawled)* | [1.6](#16-driverstandings-constructorstandings-available-not-yet-crawled) | Jolpica | driver × round, cumulative | after each round | 20 |
| `status` *(not crawled)* | [1.7](#17-status-retirement-reason-counts-available-not-yet-crawled) | Jolpica | status code × race (a count) | whole race | ~5 |
| `sessions.csv` | [2.1](#21-sessionscsv) | OpenF1 | session | whole session | 1 |
| `laps.csv` | [2.2](#22-lapscsv-the-sector-speed-trap-table) | OpenF1 | **driver × lap** | **per lap + 3 sectors** | ~1099 |
| `session_result.csv` | [2.3](#23-session_resultcsv) | OpenF1 | driver × session | whole session | 20 |
| `stints.csv` | [2.4](#24-stintscsv-tyre-strategy) | OpenF1 | **driver × tyre stint** | lap range | ~50 |
| `pit.csv` | [2.5](#25-pitcsv) | OpenF1 | **pit stop** | timestamped event | ~28 |
| `overtakes.csv` | [2.6](#26-overtakescsv) | OpenF1 | **single overtake** | timestamped event | ~228 |
| `race_control.csv` | [2.8](#28-race_controlcsv) | OpenF1 | **marshal message** | timestamped event | ~87 |
| `weather.csv` | [2.7](#27-weathercsv) | OpenF1 | **session × ~30 s** — *no driver dimension* | ~30 s | ~154 |
| `drivers.csv` | [2.9](#29-driverscsv) | OpenF1 | driver × session | whole session | 20 |
| `telemetry/*.csv` | [2.10](#210-telemetry-car_data-location-opt-in) | OpenF1 | **driver × sample** | **~0.27 s (3.6 Hz)** | ~38,400 *per driver* |
| `draftkings/*.csv` | [3.1](#31-datarawdraftkingscsv) | DK | **driver × roster slot** (each driver twice) | one race week | ~46 |
| `scoring.yaml` | [4.1](#41-configscoringyaml) | config | scoring rule | static | — |
| `race_notes.yaml` | [4.2](#42-configrace_notesyaml) | config | note, keyed by driver/team | one race week | — |
| `dk_driver_points.csv` | [5.1](#51-dataprocesseddk_driver_pointscsv) | derived | driver × race | whole race | 20 |
| `dk_constructor_points.csv` | [5.2](#52-dataprocesseddk_constructor_pointscsv) | derived | constructor × race | whole race | ~10 |
| `dashboard/data.js` | [5.3](#53-dashboarddatajs) | derived | one bundle (whole file) | season aggregate | — |

Row counts are 2025 medians where measured; §1.4–1.7 are from single-race probes.

**Reading the grain.** Anything at *driver × race* grain can only answer whole-race questions.
Per-lap detail needs §1.4 (positions, 1996+) or §2.2 (sector times + speed traps, 2023+);
sub-second detail needs telemetry (§2.10). `weather.csv` is the one dataset with **no driver
dimension** — join it on time, not on driver.

---

## 1. Jolpica

Ergast's successor: the canonical source for F1 results going back to 1950.

- **Base URL:** `https://api.jolpi.ca/ergast/f1`
- **Auth:** none, free
- **Rate limits:** HTTP 429 under load; fetchers sleep 0.8 s and back off to 60 s
- **Fetched by:** `src/data/jolpica.py`, via `python3 src/data/data_crawler.py --source jolpica`
  — currently crawls **results + qualifying only**; §1.4–1.8 are available but unwired
- **Granularity:** one row per driver per session — outcomes only, no timing detail

### 1.1 Raw JSON cache

- **Location:** `data/raw/jolpica/<year>/api/rNN_results.json`, `rNN_qualifying.json`,
  `schedule.json`
- **Grain:** one file per round per endpoint (verbatim API response)

Cached so re-runs are cheap. Envelope is `MRData.RaceTable.Races[0]` with `season`, `round`,
`raceName`, `date`, `time`, `Circuit`, `Results[]`.

**`Circuit`** — `circuitId`, `circuitName`, `url`, `Location{lat, long, locality, country}`.
That is the *entire* extent of track data here: no layout, no corner count, no straight lengths.

**`Results[]`** per driver — `number`, `position`, `positionText`, `points`, `grid`, `laps`,
`status`, `Time{millis, time}` (finishers only), `FastestLap{rank, lap, Time{time}}`, plus
nested `Driver{driverId, permanentNumber, code, givenName, familyName, dateOfBirth,
nationality, url}` and `Constructor{constructorId, name, nationality, url}`.

Qualifying files use `QualifyingResults[]` with `position`, `Q1`, `Q2`, `Q3`. Those are
**whole-lap time strings** (`"1:15.096"`) — no sector splits.

The CSV builders keep only the subset below. `Time.millis`, `FastestLap.lap`, the fastest lap
*time*, driver names, dates of birth, and nationality are all **dropped**.

### 1.2 `results.csv`

- **Location:** `data/raw/jolpica/<year>/results.csv`
- **Grain:** one row per driver per race

| Column | Type | Meaning |
|---|---|---|
| `year` | int | Season |
| `round` | int | Round number within season (1-based) |
| `race_name` | str | e.g. `Australian Grand Prix` (no year suffix) |
| `circuit_id` | str | Jolpica circuit slug, e.g. `albert_park` |
| `date` | date | Race date, `YYYY-MM-DD` |
| `driver_id` | str | Jolpica slug, e.g. `norris` — **join key** |
| `driver_code` | str | 3-letter code, e.g. `NOR`; `""` for some historical drivers |
| `constructor_id` | str | Jolpica slug, e.g. `mclaren` — **join key** |
| `grid` | int | Starting position. **`0` = pit-lane start**, not pole |
| `finish_position` | int | Classified finishing position (from `position`) |
| `position_text` | str | `"1"`, or `R` retired / `D` disqualified / `W` withdrawn / `E` excluded / `F` failed to qualify / `N` not classified |
| `status` | str | Free text: `Finished`, `+1 Lap`, `Accident`, `Engine`, … |
| `laps` | int | Laps completed |
| `points_f1` | float | **Official F1 championship points — NOT DK fantasy points** |
| `fastest_lap_rank` | int | `1` = set race fastest lap; `0` = unavailable |

**Gotchas.** DNF detection is `position_text` failing to match `^\d+` (a DNF still gets a
`finish_position`). `grid == 0` must be remapped to last place before computing place
differential — `dk_points.py` substitutes field size.

### 1.3 `qualifying.csv`

- **Location:** `data/raw/jolpica/<year>/qualifying.csv`
- **Grain:** one row per driver per qualifying session

| Column | Type | Meaning |
|---|---|---|
| `year`, `round` | int | Session identity |
| `driver_id`, `constructor_id` | str | Join keys |
| `quali_position` | int | **Qualifying classification, NOT the penalized grid** |
| `q1`, `q2`, `q3` | str | Best lap per segment, `"M:SS.sss"`; `""` if knocked out earlier |

**Critical gotcha:** `quali_position` is the result *before* grid penalties. The real starting
grid is published ~2 h before the formation lap and must be tracked by hand — see
`skill/data-process.md` §③ and `config/race_notes.yaml` → `qualifying.penalties`. Getting this
wrong corrupts place-differential, a major DK scoring component. OpenF1 doesn't fix this either
— §2 has no grid field.

### 1.4 `laps` — lap-by-lap positions (**available, not yet crawled**)

- **Location:** not on disk — endpoint is `/{year}/{round}/laps.json`
- **Grain:** one row per driver per lap (position + lap time)

Verified live: a 2024 race returns **1129 lap records**. Each lap carries a `Timings[]`
array of `{driverId, position, time}`.

| Field | Meaning |
|---|---|
| `number` | Lap number |
| `Timings[].driverId` | Jolpica driver slug |
| `Timings[].position` | Position **at the end of that lap** |
| `Timings[].time` | Lap time, `"M:SS.sss"` |

**Why this matters:** it's the missing input for **laps-led** DK points (0.25/lap), which
`dk_points.py` currently scores as zero — see §7. Counting laps where a driver holds
`position == 1` reconstructs it exactly.

**Coverage: 1996-present.** 1996 returns 812 records; 1995 and earlier return **0**. So this
is deeper history than OpenF1 (2023+) but shallower than results (1950+).

### 1.5 `pitstops` — pit stop timings (**available, not yet crawled**)

- **Location:** not on disk — endpoint is `/{year}/{round}/pitstops.json`
- **Grain:** one row per pit stop

Verified live: 43 stops for a 2024 race.

| Field | Meaning |
|---|---|
| `driverId` | Jolpica driver slug |
| `lap` | Lap the stop happened on |
| `stop` | Stop number for that driver (1, 2, …) |
| `time` | Local clock time, `"HH:MM:SS"` |
| `duration` | Stationary time, seconds (e.g. `"36.604"` — includes the pit lane) |

Overlaps OpenF1's `pit` (§2.5) but reaches back to **2012** rather than 2023.

### 1.6 `driverstandings` / `constructorstandings` (**available, not yet crawled**)

- **Location:** not on disk — `/{year}/{round}/driverstandings.json`,
  `/{year}/{round}/constructorstandings.json`
- **Grain:** one row per driver (or constructor) per round — **cumulative championship
  state after that round**

| Field | Meaning |
|---|---|
| `position`, `positionText` | Championship position |
| `points` | Season points total **after this round** |
| `wins` | Wins so far this season |
| `Driver{…}` / `Constructor{…}` | Nested identity blocks |

Useful as a form/motivation signal — a driver fighting for a title behaves differently from
one already out of contention.

### 1.7 `status` — retirement reason counts (**available, not yet crawled**)

- **Location:** not on disk — endpoint is `/{year}/{round}/status.json`
- **Grain:** one row per status code per race (a **count**, not per driver)

Fields: `statusId`, `status` (e.g. `Finished`, `Lapped`, `Engine`), `count`. Per-driver status
is already in `results.csv`; this is the aggregate view. Query without a round for
season/all-time reliability rates by cause.

### 1.8 Other Jolpica endpoints

`sprint` (sprint race results — returns 0 for non-sprint rounds), plus the reference tables
`circuits`, `drivers`, `constructors`, `seasons`. All keyed the same way.

> **Throttling warning.** Jolpica rate-limits hard — I hit repeated HTTP 429s during probing
> and needed **20–45 s between calls** to get clean responses. A lap-by-lap backfill across
> many seasons will be slow. The crawler's backoff handles it, but budget real time.

---

## 2. OpenF1

The fine-grained source: per-lap timing, tyres, pit stops, overtakes, weather, and raw
telemetry. **Now wired up** — `src/data/openf1.py`.

- **Base URL:** `https://api.openf1.org/v1`
- **Auth:** none, free (verified live)
- **Rate limits:** no `RateLimit` headers published; HTTP 429 does occur under sustained
  fetching. The fetcher sleeps 0.4 s and backs off 5→60 s on 429/5xx.
- **Coverage available from the API:** 2023 = 23 races, 2024 = 24, 2025 = 24, 2026 = 13 run
  of 25 scheduled. **2022 has only 1 session — unusable.** So OpenF1 features span a *shorter*
  history than Jolpica results.
- **Coverage on disk:** run `python3 src/data/data_crawler.py --list` to check. Figures in
  §2.1–2.9 were measured on 2025 (all 24 races); fill in other seasons with
  `python3 src/data/data_crawler.py 2023 2024 2026 --source openf1`.
- **Fetched by:** `src/data/openf1.py` → `data/raw/openf1/<year>/`
- **⚠️ Never pass a `limit` query param** — OpenF1 returns **HTTP 404** for it.

**Two weight tiers.** Light endpoints (~1–2 MB/race) are fetched for every session by default.
Heavy telemetry (~73 MB/race raw) is opt-in via `--telemetry`.

```bash
# the crawler drives every source; --source openf1 limits it to this one
python3 src/data/data_crawler.py 2025 --source openf1
python3 src/data/data_crawler.py 2025 3 --source openf1     # round 3 only
python3 src/data/data_crawler.py 2025 --source openf1 --all-sessions
python3 src/data/data_crawler.py 2025 --source openf1 --telemetry
```

Every light CSV is stamped with `year`, `location`, and `session_name` so it's usable without a
join back to `sessions.csv`.

> **Row counts quoted in §2 come from the 2025 season** (24 race sessions, races only — no
> practice, qualifying, or sprint). Per-race volume varies a lot: `race_control` runs 25→198
> rows depending on how eventful the race was, so treat the figures in the grain table above as
> medians, not guarantees. Run `python3 src/data/data_crawler.py --list` to see what's actually
> on disk.

### 2.1 `sessions.csv`

- **Location:** `data/raw/openf1/<year>/sessions.csv`
- **Grain:** one row per session — the index for everything else; `session_key` is the join key

| Column | Type | Meaning |
|---|---|---|
| `session_key` | int | **Primary key** for all other OpenF1 datasets |
| `session_type` | str | `Race`, `Qualifying`, `Practice` |
| `session_name` | str | `Race`, `Sprint`, `Qualifying`, `Practice 1`… |
| `date_start`, `date_end` | ISO ts | UTC session bounds |
| `meeting_key` | int | Groups all sessions of one Grand Prix weekend |
| `circuit_key` | int | OpenF1 circuit id (**not** Jolpica's `circuit_id`) |
| `circuit_short_name` | str | e.g. `Melbourne` |
| `country_key`, `country_code`, `country_name` | | e.g. `5`, `AUS`, `Australia` |
| `location` | str | e.g. `Melbourne` |
| `gmt_offset` | str | Local UTC offset, `"11:00:00"` |
| `year` | int | Season |
| `is_cancelled` | bool | True for cancelled sessions |

### 2.2 `laps.csv` — **the sector + speed-trap table**

- **Location:** `data/raw/openf1/<year>/laps.csv`
- **Grain:** one row per driver per lap — the most valuable OpenF1 dataset for pace analysis

| Column | Type | Non-null | Meaning |
|---|---|---|---|
| `session_key`, `meeting_key` | int | 100% | Join keys |
| `driver_number` | int | 100% | Car number — **join via `drivers.csv`**, not a driver id |
| `lap_number` | int | 100% | 1-based |
| `date_start` | ISO ts | 100% | When the lap began (UTC) |
| `lap_duration` | float | 100% | Lap time, seconds |
| `duration_sector_1/2/3` | float | 100% | Sector times, seconds |
| `i1_speed` | float | **84%** | Speed trap at intermediate 1, km/h |
| `i2_speed` | float | **96%** | Speed trap at intermediate 2, km/h |
| `st_speed` | float | **92%** | Speed trap on the **main straight**, km/h |
| `segments_sector_1/2/3` | list[int] | 100% | Mini-sector status codes (`2049` = green, `2051` = purple, …) — stored as a string in CSV |
| `is_pit_out_lap` | bool | 100% | True on out-laps — **exclude these from pace stats** |

**Speed-trap density.** Measured over full sessions: `st_speed` is 92% populated in 2025 and
75% in 2026 Budapest. A single lap can look much worse (one sampled Budapest lap had only
12/21) — so judge coverage per season, not per lap, and always guard for nulls.

`st_speed` is the closest thing to a **straight-line speed** proxy available without telemetry.
Cornering pace has to come from `duration_sector_*` (pick a slow-corner sector) or from §2.10.

### 2.3 `session_result.csv`

- **Location:** `data/raw/openf1/<year>/session_result.csv`
- **Grain:** one row per driver per session — the finishing classification

| Column | Type | Non-null | Meaning |
|---|---|---|---|
| `session_key`, `meeting_key`, `driver_number` | int | 100% | Join keys |
| `position` | float | **89%** | Final classified position; null when unclassified |
| `number_of_laps` | float | 99% | Laps completed |
| `points` | float | 100% | **Official F1 points**, not DK |
| `dnf`, `dns`, `dsq` | bool | 100% | Explicit flags — **cleaner than Jolpica's `position_text`** |
| `duration` | float | **69%** | Total race time, seconds; null for non-finishers |
| `gap_to_leader` | str | 87% | Seconds as a string, or lap-count text — **parse carefully** |

The `dnf`/`dns`/`dsq` booleans are the reason to prefer this over regex-matching
`position_text`.

### 2.4 `stints.csv` — tyre strategy

- **Location:** `data/raw/openf1/<year>/stints.csv`
- **Grain:** one row per driver per tyre stint

| Column | Type | Meaning |
|---|---|---|
| `session_key`, `meeting_key`, `driver_number` | int | Join keys |
| `stint_number` | int | 1-based within the session |
| `lap_start`, `lap_end` | float | Inclusive lap range of the stint |
| `compound` | str | `SOFT`, `MEDIUM`, `HARD`, `INTERMEDIATE`, `WET` |
| `tyre_age_at_start` | int | Laps already on the set (`0` = new) |

This is **actual** tyre usage, unlike the hand-written plans in `config/race_notes.yaml` →
`tyre_plans`. Useful for validating those notes after the fact.

### 2.5 `pit.csv`

- **Location:** `data/raw/openf1/<year>/pit.csv`
- **Grain:** one row per pit stop

| Column | Type | Non-null | Meaning |
|---|---|---|---|
| `session_key`, `meeting_key`, `driver_number` | int | 100% | Join keys |
| `date` | ISO ts | 100% | Stop timestamp |
| `lap_number` | int | 100% | Lap the stop happened on |
| `pit_duration` | float | 100% | Total time lost, seconds |
| `lane_duration` | float | 100% | Time in the pit lane, seconds |
| `stop_duration` | float | **86%** | Stationary time only, seconds |

### 2.6 `overtakes.csv`

- **Location:** `data/raw/openf1/<year>/overtakes.csv`
- **Grain:** one row per on-track pass

| Column | Type | Meaning |
|---|---|---|
| `session_key`, `meeting_key` | int | Join keys |
| `overtaking_driver_number` | int | Car that made the pass |
| `overtaken_driver_number` | int | Car that lost the place |
| `date` | ISO ts | When it happened |
| `position` | int | Position being contested |

Directly relevant to DFS: DK pays **place differential**, and this is empirical evidence of
which drivers and which circuits actually generate passes.

### 2.7 `weather.csv`

- **Location:** `data/raw/openf1/<year>/weather.csv`
- **Grain:** one row per ~30 s of session — **no driver dimension**, join on time

| Column | Type | Meaning |
|---|---|---|
| `session_key`, `meeting_key` | int | Join keys |
| `date` | ISO ts | Sample time |
| `air_temperature`, `track_temperature` | float | °C |
| `humidity` | float | % |
| `pressure` | float | mbar |
| `rainfall` | int | `0`/`1` flag — **not** an mm amount |
| `wind_speed` | float | m/s |
| `wind_direction` | int | Degrees, 0–359 |

Real measured weather, unlike the hand-written forecast notes in `race_notes.yaml` → `weather`.

### 2.8 `race_control.csv`

- **Location:** `data/raw/openf1/<year>/race_control.csv`
- **Grain:** one row per marshal / stewarding message

| Column | Type | Non-null | Meaning |
|---|---|---|---|
| `session_key`, `meeting_key` | int | 100% | Join keys |
| `date` | ISO ts | 100% | Message time |
| `lap_number` | int | 100% | Lap it applies to |
| `category` | str | 100% | `Flag`, `SafetyCar`, `Drs`, `Other`… |
| `message` | str | 100% | Raw text, e.g. `LOW GRIP CONDITIONS` |
| `flag` | str | **49%** | `GREEN`, `YELLOW`, `RED`, `CLEAR`, `CHEQUERED` |
| `scope` | str | **49%** | `Track`, `Sector`, `Driver` |
| `driver_number` | float | **23%** | Set only for driver-specific messages |
| `sector` | float | **21%** | Set only when `scope == Sector` |
| `qualifying_phase` | float | **0%** | Always null in race sessions |

Safety-car and red-flag timing lives here — the main lever for modelling correlated DNFs, which
the simulator currently treats as independent coin flips.

### 2.9 `drivers.csv`

- **Location:** `data/raw/openf1/<year>/drivers.csv`
- **Grain:** one row per driver per session — **the join bridge** from `driver_number` to a code

| Column | Type | Non-null | Meaning |
|---|---|---|---|
| `session_key`, `meeting_key`, `driver_number` | int | 100% | Join keys |
| `driver_number` | int | 100% | **Permanent car number** (VER=1, NOR=4, PIA=81, HAM=44) — the join key every other OpenF1 endpoint uses. **Not stable across seasons**, so join per session |
| `name_acronym` | str | 100% | 3-letter code, e.g. `VER` — **matches Jolpica `driver_code`** |
| `full_name`, `first_name`, `last_name` | str | 100% | e.g. `Max VERSTAPPEN` |
| `broadcast_name` | str | 100% | e.g. `M VERSTAPPEN` |
| `team_name` | str | 100% | e.g. `Red Bull Racing` — DK-style name, not a Jolpica id |
| `team_colour` | str | 100% | Hex, no `#` |
| `headshot_url` | str | 96% | Portrait image |
| `country_code` | — | **0%** | Always null — do not rely on it |

### 2.10 Telemetry — `car_data` + `location` (opt-in)

- **Location:** `data/raw/openf1/<year>/telemetry/<session_key>_<driver_number>.csv`
- **Grain:** one row per driver per ~0.27 s sample (~3.6 Hz)

Written only when you pass `--telemetry`. **Per driver per race: ~38,400 rows** → ~768k rows and
**~73 MB raw JSON** for a full 20-car race. That's why it isn't fetched by default. (Measured on
one driver at Melbourne 2025 and extrapolated to 20 cars — no telemetry has been downloaded yet.)

`car_data` fields (~3.6 Hz per driver):

| Column | Type | Meaning |
|---|---|---|
| `date` | ISO ts | Sample time |
| `speed` | int | km/h |
| `rpm` | int | Engine RPM |
| `n_gear` | int | Gear, 0–8 |
| `throttle` | int | % applied |
| `brake` | int | `0` or `100` — effectively a boolean |
| `drs` | int | DRS state code (values >9 mean open) |

`location` fields (~3.8 Hz per driver) are merged in by the fetcher: `x`, `y`, `z` track
position. The two streams have **unsynchronised timestamps**, so `openf1.py` joins them
with `pd.merge_asof(direction="nearest", tolerance=0.5s)` — expect nulls where a match fell
outside tolerance.

**Deriving straight-line vs cornering speed.** This is the reason to pull telemetry: no endpoint
exposes it directly. With `x`/`y` joined to `speed`, classify each track point as straight or
corner (curvature of the position trace, or a fixed corner map), then average speed per class
per driver. The `fastf1` library (3.8.3, pip-installable, **not currently a dependency**) wraps
the same feed and ships **built-in circuit geometry with corners already marked**, which would
skip the corner-detection step entirely.

### 2.11 Endpoints deliberately not fetched

Verified to exist but unused: `position` (~335 rows/race, running order over time),
`intervals` (**~18,965 rows/race** — gap-to-leader at high frequency), `team_radio` (audio clip
URLs). Those per-race figures come from probing a single 2025 session (Melbourne), not a full
season pull. `meetings` and `starting_grid` return **HTTP 404** — the latter is worth re-checking
later, since a real grid endpoint would remove the manual penalty tracking in §1.3.

---

## 3. DraftKings

The only source for salaries — and the only one you **cannot backfill**.

- **Auth:** none, but a browser `User-Agent` header is required (see `common.DK_HEADERS`)
- **Coverage:** the **upcoming race only**. DK publishes no history.
- **Fetched by:** `src/data/draftkings.py` (via the crawler); `src/util/dk_contests.py` lists contests

### 3.1 `data/raw/draftkings/*.csv`

- **Location:** `data/raw/draftkings/<race_name>.csv` (e.g. `Belgian_Grand_Prix_2026.csv`)
- **Grain:** one row per (driver, roster slot) — each driver appears twice, CPT and D

Endpoint: `api.draftkings.com/draftgroups/v1/draftgroups/{id}/draftables`.
**Refresh: weekly, before each race — irreplaceable.**

| Column | Type | Meaning |
|---|---|---|
| `name` | str | DK display name, e.g. `Lando Norris` — map via `common.NAME_TO_CODE` |
| `position` | str | `D` (driver) or `CNSTR` (constructor) |
| `roster_slot_id` | int | Distinguishes CPT vs D slot for the same driver |
| `salary` | int | Slot salary in dollars; CPT ≈ 1.5× the D slot |
| `team` | str | DK abbreviation (`MCL`, `VCARB`…) — map via `common.DK_ABBREV_TO_ID` |
| `fppg` | float | DK's own fantasy-points-per-game average; may be null |
| `competition` | str | e.g. `Belgian Grand Prix 2026` (**includes** the year) |
| `draftable_id` | int | DK's internal id |

Each driver appears on **two rows** (CPT + D slot); `build_data.py` collapses them via
`max(salary)` → CPT and `min(salary)` → D.

> ⚠️ **No salary snapshot is on disk yet.** `build_data.py`
> calls `latest_salary_file()`, which raises `FileNotFoundError` when no CSV is present, so
> **`python3 dashboard/build_data.py` fails today** — verified by running it. The committed
> `dashboard/data.js` still works (built for Hungarian GP 2026) but cannot be regenerated until
> you run `python3 src/data/data_crawler.py --source draftkings`. Any past week not
> snapshotted is **gone permanently**.

### 3.2 Contest list (not persisted)

- **Location:** none — printed to stdout, **never written to disk**
- **Grain:** one row per open F1 contest

`src/util/dk_contests.py` hits `draftkings.com/lobby/getcontests?sport=F1` to find the $0.25
contest and its `DraftGroupId`. `DraftGroups[0]` is also how `src/data/draftkings.py`
auto-detects the current draft group.

---

## 4. Hand-maintained config

Not fetched from anywhere — curated by hand or agent, and treated as source of truth.

### 4.1 `config/scoring.yaml`

- **Location:** `config/scoring.yaml`
- **Grain:** one entry per scoring rule (static — not per race or per driver)

DK Classic rules, hand-verified against draftkings.com/help/rules/27 (last verified 2026-07-18).
**Refresh:** only when DK changes rules. Read by `sim/dk_points.py` and
`dashboard/build_data.py`.

Keys: `salary_cap` (50000), `roster{captain:1, drivers:4, constructors:1}`,
`captain_multiplier` (1.5), `driver{finishing_position{1..22},
place_differential_per_position, fastest_lap, laps_led_per_lap, defeated_teammate,
classified_finish}`, `constructor{finishing_position, fastest_lap, laps_led_per_lap,
both_cars_classified, both_cars_in_points, both_cars_on_podium}`. Trailing comments carry the
edge cases (post-race DQs don't change scoring; withdrawal/replacement effects on bonuses).

One roster constraint isn't expressible in the YAML: **max 2 selections from any one team**,
drivers and constructor combined.

### 4.2 `config/race_notes.yaml`

- **Location:** `config/race_notes.yaml`
- **Grain:** one note list per topic, keyed by driver code or constructor id — covers **one race week at a time** (overwritten each week, no history)

Race-week intel, refreshed weekly. Read wholesale into `data.js` → `data.raceNotes`.

| Key | Shape | Consumed by |
|---|---|---|
| `race` | str, e.g. `Belgian Grand Prix 2026` | Checked against the salary file's `competition`; mismatch only **warns** |
| `pit_strategy`, `penalties`, `weather`, `lineup_angles` | list[str] | Dashboard info box |
| `tyre_plans` | map constructor_id → list[str] | Displayed only |
| `qualifying.order` | list of driver codes, best→worst | **Applied automatically** as real grid when non-empty |
| `qualifying.penalties` | map driver code → places dropped | Applied with `order` |
| `driver_performance` | map driver code → list[str] (FP1–3 notes) | Displayed only |

`weather`, `tyre_plans`, and `driver_performance` are **displayed but never used by the
simulator** — see `doc/simulation-technical.md`. Now that §2.4 and §2.7 provide *measured* tyre
and weather data, these notes are best treated as pre-race forecasts only. This file currently
says Belgian GP while `data.js` was built for Hungarian GP — a week stale.

---

## 5. Derived datasets

Computed here from the sources above. Not raw data.

### 5.1 `data/processed/dk_driver_points.csv`

- **Location:** `data/processed/dk_driver_points.csv`
- **Grain:** one row per driver per race

Producer: `src/sim/dk_points.py`, from `data/raw/jolpica/<year>/results.csv` +
`config/scoring.yaml`. What each driver **would have scored** under current DK rules.

| Column | Type | Meaning |
|---|---|---|
| `year`, `round`, `race_name` | | Race identity |
| `driver_id`, `driver_code`, `constructor_id` | str | Join keys |
| `grid`, `finish_position` | int | Copied from results (raw `grid`, so `0` = pit lane) |
| `pts_finish` | float | Position points, 40 (P1) → 0 (P22) |
| `pts_place_diff` | float | `(grid − finish) × 1`; negative if places lost |
| `pts_fastest_lap` | float | `3` if `fastest_lap_rank == 1` |
| `pts_classified` | float | `1` if `laps ≥ 90%` of the winner's laps |
| `pts_defeated_teammate` | float | `5` if best finisher on the team (needs ≥2 cars) |
| `dk_points_total` | float | Sum of the five components |

**Known undercount:** laps-led (`0.25`/lap) is **never computed** — Jolpica has no lap-by-lap
leader data, so race leaders are understated by roughly 10–20 points. OpenF1's `position`
endpoint (§2.11) could fix this. The captain's 1.5× multiplier is also not applied here; that
happens at lineup construction.

### 5.2 `data/processed/dk_constructor_points.csv`

- **Location:** `data/processed/dk_constructor_points.csv`
- **Grain:** one row per constructor per race

Same producer as §5.1.

| Column | Type | Meaning |
|---|---|---|
| `year`, `round`, `race_name`, `constructor_id` | | Identity + join key |
| `pts_finish` | float | **Sum over both cars** (P1+P3 = 40+35 = 75) |
| `pts_fastest_lap` | float | `3` if either car set fastest lap |
| `pts_both_classified` | float | `2` if both cars classified (≥90% laps) |
| `pts_both_in_points` | float | `5` if both finished P10 or better |
| `pts_both_podium` | float | `3` if both finished top 3 |
| `dk_points_total` | float | Sum of the five |

All `both_*` bonuses require exactly 2 cars entered; a one-car team scores `0` for all three.
Laps-led likewise not computed.

### 5.3 `dashboard/data.js`

- **Location:** `dashboard/data.js`
- **Grain:** one bundle for the whole file — driver/constructor stats are **season aggregates** (last 20 races), not per-race rows

Producer: `dashboard/build_data.py`. A single `const F1DATA = {…}` object so `index.html` runs as
a plain local file with no server. **Committed to git** (unlike `data/`), so a fresh clone has a
working dashboard. **Refresh:** after every data refresh.

Top-level keys: `raceName`, `totalLaps`, `salaryCap`, `captainMultiplier`, `scoring` (verbatim
`scoring.yaml`), `drivers`, `constructors`, `raceNotes` (verbatim `race_notes.yaml`),
`raceHistory`. `totalLaps` is looked up from past results at the same-named race, falling back
to **55**.

**`drivers[]`** — 22 entries, sorted by descending CPT salary. Stats from that driver's **last
20 races only**:

| Field | Meaning |
|---|---|
| `name`, `code`, `team` | Identity; `team` is a Jolpica constructor id |
| `salaryCpt`, `salary` | CPT-slot and D-slot salary |
| `avgFinish`, `stdFinish` | Mean/σ finishing position, **finishers only** (σ floored at 1.5) |
| `avgGrid`, `stdGrid` | Mean/σ grid, **excluding pit-lane starts** (σ floored at 1.5) |
| `dnfRate` | Fraction not classified, **clamped to [0.03, 0.35]** |
| `avgDk` | Mean `dk_points_total` |
| `races` | Sample size (≤20) |

**`constructors[]`** — 11 entries: `name`, `shortName`, `id`, `salary`, `avgDk`, `maxDk`,
`bothPtsRate`, `races`.

Entries with no history fall back to priors in `build_data.py`: drivers `avgFinish 12.0,
stdFinish 4.0, avgGrid 12.0, stdGrid 3.0, dnfRate 0.12, avgDk 15.0`; constructors `avgDk 20.0,
maxDk 35.0, bothPtsRate 0.05`. A `races: 0` entry is pure prior — treat with suspicion.

**`raceHistory[]`** — 80 past races, each `{year, round, raceName, drivers{CODE: pts},
constructors{id: pts}}`. Real historical DK points for the Testing AI tab's backtest.

Unmapped drivers or teams are **skipped with a warning**, silently shrinking the pool — add new
names to `common.NAME_TO_CODE` / `TEAMS` / `DK_ABBREV_TO_ID` when the grid changes.

---

## 5b. Visualisation — `src/vis/track_replay.py`

Builds a self-contained broadcast-style replay HTML (timing tower left, circuit right)
from OpenF1 data. Split across `src/vis/`: `track_replay.py` (CLI), `race.py` (pick a race + window,
fetch all feeds), `circuit.py` (official circuit map), `frames.py` (animation timeline),
`layout.py` (pit lane, rotation, canvas sizing), and `page.py`, which assembles both
output pages from the real front-end files in `src/vis/assets/` (`replay.html`,
`replay.css`, `replay.js`). Both pages load the same `replay.js`; the only difference
is how data arrives — the standalone page inlines one JSON blob, while
`dashboard/replay.html` (a multi-race picker) fetches `dashboard/replays/*.json`.
`--full` replays a whole race, widening the frame step automatically (a 57-lap race is
~1300 frames / 2.3 MB rather than 12k frames / 22 MB). The tower shows **lap X / Y**
from the race leader's lap count — not an arbitrary reference car, since backmarkers
run laps down.

`/location` is fetched with a 5-thread pool: it's ~0.6 s per driver, so 20 cars is
~12 s serially. It's pure I/O wait, so threads suffice — the GIL is released during
the request and multiprocessing would only add overhead. Rendering is **not** a
bottleneck: measured at 0.49 ms/frame (~2000 fps) against a 500 ms frame interval, so
a GPU would change nothing. No separate track-geometry source is needed: **one driver's `/location`
trace across a whole lap *is* the circuit outline.**

```bash
python3 src/vis/track_replay.py 2025 1          # busiest lap, auto-picked
python3 src/vis/track_replay.py 2025 1 --from-lap 10 --laps 3
python3 src/vis/track_replay.py --list          # crawled races
```

Inputs: `/location` (dots), `/position` (order), `/intervals` (gaps) fetched on demand and
cached; `stints.csv` (tyre), `pit.csv` (pit flag), `session_result.csv` + `laps.csv`
(retirements) read from disk. Output goes to `dashboard/replay_<year>_<location>.html`.

Four things that are non-obvious and cost real debugging time:

1. **The race doesn't start at the session's `date_start`.** Melbourne 2025 opens the
   session at 04:00 UTC but the first lap begins at **04:18**. Window from the first lap's
   `date_start`, or you get 18 minutes of a stationary grid.
2. **`/position` and `/intervals` are change-only feeds.** They emit a row when something
   changes, not on a clock. Laps 10–11 at Melbourne had **zero** position changes, so the
   tower looked frozen — it was correct. `--from-lap` defaults to the **busiest lap** (most
   position changes) for this reason; Melbourne's is lap 44 with 65 changes.
3. **A time-sliced outline doesn't close.** Slicing an arbitrary window leaves a visible
   gap where the car hadn't driven yet. Slice on real lap boundaries
   (`date_start` + `lap_duration`) so the trace is a full lap, then `closePath()`.
4. **`/location` keeps emitting a retired car's last coordinates.** Without filtering, DNFs
   sit motionless on the track looking like live cars. Melbourne 2025 had 4 (SAI, DOO lap 1;
   ALO lap 33) — they're excluded from the map and shown as `OUT` in the tower.

**What the map shows.** Cars are drawn as oriented F1 glyphs (heading derived from the step
just taken, with a gradient body and driver code label so they read at a glance). A **red halo**
marks cars within ~1 car length of each other — real wheel-to-wheel battles or contact, never
staged, since these are recorded positions.

The **pit lane is derived**, not sourced: no source publishes F1 pit geometry — not OpenF1,
not FastF1, not the MultiViewer map (which carries only scalar `pitLoss` times). So the route
cars take during a stop *is* the lane, and the near-stationary points are the boxes. The
derived data is a **1-D path with no width**, so it's drawn as a dashed line with entry/exit
and box markers rather than as wide asphalt — drawing a road would be inventing information.
It's offset a constant 2.6 track widths from the circuit: real pit lanes are parallel by
construction (RMS deviation ~0.4 m at Melbourne), and the offset has to clear the **forming
grid**, which sits on the start straight the lane runs alongside. Order lane points along the
**lane itself**, never by nearest racing-line index — indexing against the circuit wraps at
start/finish, which split Melbourne's lane in half and drew a 293 m spike across the map
(mean turn angle 41-86° that way, ~1° ordering along the lane). Use exactly the
stop window (`date − pit_duration` → `date`) — widening it by even a few seconds pulls in the
car's position on the main straight, which made the derived "lane" land on top of the racing
line. The `PIT` badge is time-windowed the same way; flagging the whole lap showed PIT while the
car was visibly on track, because a lap is ~92 s but a stop is ~19 s.

**The circuit outline comes from an official map, not from car positions.** Deriving it
from one driver's lap was the wrong foundation: it caused a long run of bugs (lap-seam
self-intersection, duplicate points from stationary cars, size-dependent thresholds) and
was **silently truncating Monaco to 80% of the lap** — 2.68 km of 3.337 km, discarding
the whole tunnel / Nouvelle Chicane stretch. Every width and rotation tweak was fighting
a broken shape.

MultiViewer publishes a hand-authored closed centreline per circuit, keyed by the **same
`circuit_key` OpenF1 already returns** in `/sessions`, and — critically — in the **same
coordinate space**, so car positions overlay with no transform:

```
https://api.multiviewer.app/api/v1/circuits/{circuit_key}/{year}
```

Free, no auth. Also supplies an official **`rotation`** (broadcast orientation; add 90°
for a landscape canvas) and corner markers with arc-length distances. Verified against
official lengths: Monaco 3.270 km vs 3.337, Melbourne 5.243 vs 5.278 — within 1–2%, and
Monaco now draws a full-width 26 px road with cars at 0.98× instead of being clamped.
Implemented in `src/vis/circuit.py`, cached permanently under
`data/raw/circuits/` since the geometry is static. The position-derived path remains as
a fallback for circuits the map doesn't cover.

Note FastF1 fetches this **same endpoint** but parses only corners/rotation and discards
the `x`/`y` outline — so calling it directly avoids the dependency. FastF1's own track-map
example derives the outline from a fastest lap, inheriting the same fragility. Neither
source provides **pit-lane geometry**; that still has to be derived from position data.

**Sizing is derived per circuit, not fixed.** A single hardcoded road width fails:
Monaco's closest non-adjacent sections are only ~15–25 m apart, so at 26 px the track
overlaps itself into a blob, while clamping the width instead shrinks cars to 0.39×.
The fix is to grow the **canvas** until the circuit's real tightest self-gap can hold a
full-width road (`shape.fit_for_track`), then scale it down with CSS to fit the
viewport — more px/metre, same screen space. Monaco lands at 710×968 with a 22 px road;
Melbourne needs no growth at 1150×606. Cars are sized off the road width so they stay
proportionate everywhere.

Three traps in measuring that self-gap, each of which collapsed the track to the 7 px
floor:
1. **The lap seam.** A trimmed lap slightly overlaps itself at start/finish, so points
   92% and 96% round the lap read as 4 m apart. Skip ~10% of the lap either side.
2. **Multi-lap outlines.** `--full` traces the whole race, so the "circuit" was 16–24k
   points of the same lap repeated. Trim to one lap — and use thresholds **relative to
   the circuit's size**, since a fixed 200 m arming distance never triggers at Monaco,
   which only reaches ~1 km from the start line.
3. **Stationary cars.** A car on the grid or in its pit box emits identical
   coordinates repeatedly, giving a self-gap of exactly 0. Dedupe consecutive samples.

**Scale is deliberately not 1:1.** A real F1 car is ~2 m wide on a ~12 m track (~17%), which at
this zoom renders as a speck. Track and cars are drawn ~10× exaggerated so the racing is legible.
That breaks adjacent geometry: Albert Park's pit lane is only ~10–15 m from the main straight
(~3 px here), so at 26 px road widths the two collide. The fix is to scale the lane's **real
perpendicular offset** by the same exaggeration factor — proportional, so the lane sits beside
the track exactly as in reality, just enlarged. Filtering "overlapping" points instead is wrong:
the overlap is genuine geometry, and a 7 m cutoff deleted all but 2 of 88 lane points.

**Playback must interpolate.** Positions are sampled every `dt` seconds — 4 s on a full
race after frame-thinning — so drawing one frame per `dt` is 0.25 fps: visible
stop-motion, not animation. The page advances a **continuous cursor** with
`requestAnimationFrame` and blends the two nearest frames (headings interpolated the
short way round the circle), giving smooth motion from the same data. Measured: 30/30
sampled cursor values fractional, wall-clock advance matching `elapsed/dt`.

**Position deltas must be persistent, not transient.** Flagging a change only on the
frame it happens is invisible — at 4 s/frame barely **1% of frames** contain one. The
tower instead shows places gained/lost **since the start**, in its own column, always
populated (`0` when unchanged, `–` when unknown). That's the broadcast convention and
it's always meaningful: SAI reads `▲13` at Monaco 2024 having started P16.

**Layout.** The map is rotated so the **start/finish straight runs horizontally** — a landscape
footprint fills a wide canvas and lets the glyphs read clearly. Two earlier objectives were
worse: bounding-box area barely separates candidates (Albert Park scores within 2% at 0° and
105°), and principal-axis alignment fought the canvas aspect, leaving the circuit at ~44% of the
width. The canvas is then shrink-wrapped to the rotated circuit inside a size budget. The timing
tower updates **in place** rather than re-rendering `innerHTML` each frame — rebuilding every row
16×/second made it strobe — and movement arrows persist ~1.2 s so they're readable. The tower
uses `table-layout:fixed` with an explicit `<colgroup>` and a fixed-width arrow slot: otherwise
inserting a ▲/▼ reflows every column. Verified across all 342 frames (66 showing arrows) that
exactly one column layout occurs.

Also: `(0,0)` in `/location` is a no-fix sentinel, not the start line — filter it. The map
carries a compass, since track coords are y-up in an arbitrary local frame and the rotation
makes north arbitrary on screen (`--rotate DEG` overrides, `--no-rotate` keeps native).

---

## 6. Cross-source joins

Each source uses a different identifier. `src/util/common.py` holds the translation tables.

| From | To | Via |
|---|---|---|
| Jolpica `driver_id` (`norris`) | code (`NOR`) | `results.csv.driver_code` |
| OpenF1 `driver_number` (`4`) | code (`NOR`) | `openf1/drivers.csv.name_acronym` |
| DK `name` (`Lando Norris`) | code (`NOR`) | `common.NAME_TO_CODE` |
| DK `team` (`MCL`) | Jolpica `constructor_id` (`mclaren`) | `common.DK_ABBREV_TO_ID` |
| DK constructor name (`McLaren`) | `constructor_id` | `common.TEAMS` |
| OpenF1 `session_key` | Jolpica `(year, round)` | **no direct key** — match on `year` + circuit/location |

**Gotchas.**
- The **3-letter code is the only identifier common to all three sources.** Route joins through it.
- OpenF1 `circuit_key` (int) ≠ Jolpica `circuit_id` (slug). No mapping table exists yet; match on `location` / `circuit_short_name` against `race_name`.
- OpenF1 has **no `round` number** — derive it by ordering sessions by `date_start` within a year.
- DK `competition` includes the year (`Belgian Grand Prix 2026`); Jolpica `race_name` doesn't. `build_data.py` strips the trailing token.
- `race_notes.yaml` keys on **driver code**, not `driver_id`.
- OpenF1 `driver_number` is **not stable across seasons** — always join per session.

### Refresh cadence

| Cadence | Do this |
|---|---|
| **Weekly, before race** | `python3 src/data/data_crawler.py --source draftkings` — irreplaceable |
| **After qualifying** | Fill `race_notes.yaml` → `qualifying.order` + `penalties` (manual) |
| **Race week** | Refresh `pit_strategy`, `weather`, `driver_performance`, `lineup_angles` |
| **After each race** | `python3 src/data/data_crawler.py <year> <round>` → `sim/dk_points.py` → `dashboard/build_data.py` |
| **On rule change** | Re-verify `config/scoring.yaml`, re-run `sim/dk_points.py` |
| **Rarely / on demand** | `data_crawler.py <year> --telemetry` (~73 MB per race) |
| **Never** | Delete anything in `data/raw/draftkings/` |

The crawler caches every response and is safe to re-run — it only fetches what's missing.

---

## 7. Known gaps

1. **No DK salary snapshot on disk** → `dashboard/build_data.py` fails until you run
   `python3 src/data/data_crawler.py --source draftkings`. Salaries can't be backfilled.
2. **Only 2025 OpenF1 data has been crawled** (24 races) — so every row count in §2 is a 2025
   figure. Fetch the rest with
   `python3 src/data/data_crawler.py 2023 2024 2026 --source openf1`.
3. **No telemetry has been pulled at all** (§2.10) — needs `--telemetry`, ~73 MB per race.
   Note `src/vis/track_replay.py` fetches `/location` on demand, so the replay works
   without a telemetry crawl.
4. **Jolpica `/laps`, `/pitstops`, `/driverstandings`, `/status` are unwired** (§1.4–1.8) —
   verified available, but `src/data/jolpica.py` only pulls results + qualifying.
5. **Straight-line vs cornering speed still isn't computed** — §2.10 explains how; nothing
   implements it. `st_speed` (§2.2) is the cheap proxy available today.
6. **OpenF1 data isn't consumed by anything yet** — the crawler writes
   `data/raw/openf1/<year>/*.csv`, but neither `sim/dk_points.py` nor
   `dashboard/build_data.py` reads it. The simulator still runs purely on season-aggregate
   finish distributions.
7. **Laps-led points never computed** — understates race leaders ~10–20 pts. **Two ways to
   fix it:** Jolpica `/laps` (§1.4, back to 1996) or OpenF1 `/position` (§2.11, 2023+).
   Jolpica is the better option — deeper history, and already a wired-up source.
8. **Grid penalties are manual** — `quali_position` isn't the starting grid, and OpenF1's
   `starting_grid` endpoint 404s. See §1.3.
9. **No OpenF1 ↔ Jolpica circuit mapping table** — joins rely on name matching (§6).
10. **`race_notes.yaml` may drift from the built `data.js`** — `build_data.py` only warns on a
   race-name mismatch, it doesn't fail.
11. **20-race window + clamps** in `build_data.py` mean driver stats span seasons and
    regulation changes, and `dnfRate` can never leave [0.03, 0.35].
