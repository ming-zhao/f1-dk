"""OpenF1 — per-lap timing, tyres, pit stops, overtakes, weather, telemetry.

Free, no API key. Coverage starts 2023; 2022 has a single session and is unusable.

Two weight tiers:
    LIGHT (default, ~1-2 MB per race)
        drivers, session_result, laps, stints, pit, overtakes, weather, race_control
    HEAVY (opt-in via telemetry=True, ~73 MB per race)
        car_data  ~3.6 Hz speed/throttle/brake/gear/rpm/drs
        location  ~3.8 Hz x/y/z track position

Telemetry is what you need to derive straight-line vs cornering pace: join location
to car_data on timestamp, classify each track point as straight or corner, then
average speed per class.

Output:
    data/raw/openf1/<year>/api/<session_key>_<endpoint>.json   cached responses
    data/raw/openf1/<year>/sessions.csv                        one row per session
    data/raw/openf1/<year>/laps.csv                            one row per driver per lap
    data/raw/openf1/<year>/{stints,pit,overtakes,weather,...}.csv
    data/raw/openf1/<year>/telemetry/<session_key>_<driver>.csv  (opt-in)
"""

from datetime import date
from pathlib import Path
from typing import Optional

import pandas as pd

from ._http import DATA, get_json, merge_csv, write_csv

BASE = "https://api.openf1.org/v1"
FIRST_YEAR = 2023
SLEEP = 0.4

# Endpoints keyed only by session_key — light enough to pull for every session.
# NOTE: OpenF1 rejects a `limit` query param with HTTP 404 — never add one.
LIGHT_ENDPOINTS = [
    "drivers", "session_result", "laps", "stints",
    "pit", "overtakes", "weather", "race_control",
]

# What makes a row unique per endpoint, for merging single-round fetches into a
# season CSV without losing rows.
DEFAULT_MERGE_KEYS = ["session_key", "driver_number", "lap_number", "date"]
MERGE_KEYS = {
    "stints": ["session_key", "driver_number", "stint_number"],
    "drivers": ["session_key", "driver_number"],
    "session_result": ["session_key", "driver_number"],
    "laps": ["session_key", "driver_number", "lap_number"],
    "pit": ["session_key", "driver_number", "date"],
    "overtakes": ["session_key", "date", "overtaking_driver_number"],
    "weather": ["session_key", "date"],
    "race_control": ["session_key", "date", "category", "message"],
}


def fetch(year: int, only_round: Optional[int] = None,
          telemetry: bool = False, all_sessions: bool = False, **_) -> None:
    """Fetch a season, or a single round of it, into data/raw/openf1/<year>/.

    OpenF1 exposes no round number, so "round N" means the Nth race session of
    the season by start date.
    """
    if year < FIRST_YEAR:
        print(f"  {year}: OpenF1 starts at {FIRST_YEAR}, skipping")
        return

    year_dir = DATA / "raw" / "openf1" / str(year)
    api_dir = year_dir / "api"

    sessions = get_json(f"{BASE}/sessions?year={year}",
                        api_dir / "sessions.json", SLEEP)
    if not sessions:
        print(f"  {year}: no sessions")
        return

    if not all_sessions:
        sessions = [s for s in sessions if s.get("session_name") == "Race"]
    today = date.today().isoformat()
    sessions = [s for s in sessions if (s.get("date_start") or "")[:10] <= today]
    sessions.sort(key=lambda s: s.get("date_start") or "")
    if not sessions:
        print(f"  {year}: no sessions have run yet")
        return

    # Derive a round number from chronological order — the API has none.
    for i, s in enumerate(sessions, start=1):
        s["round"] = i

    all_of_them = list(sessions)
    if only_round is not None:
        sessions = [s for s in sessions if s["round"] == only_round]
        if not sessions:
            print(f"  {year}: round {only_round} not available "
                  f"(has 1-{len(all_of_them)}), skipping")
            return

    print(f"  {year}: {len(sessions)} session(s)")
    if only_round is None:
        write_csv(all_of_them, year_dir / "sessions.csv")
    else:
        merge_csv(all_of_them, year_dir / "sessions.csv", ["session_key"])

    collected: dict[str, list] = {e: [] for e in LIGHT_ENDPOINTS}
    for s in sessions:
        sk = s["session_key"]
        print(f"  {year} round {s['round']:>2} — {s.get('location')} "
              f"{s.get('session_name')} [session {sk}]")
        for endpoint in LIGHT_ENDPOINTS:
            rows = get_json(f"{BASE}/{endpoint}?session_key={sk}",
                            api_dir / f"{sk}_{endpoint}.json", SLEEP)
            if rows is None:
                continue
            # Stamp context so each CSV stands alone without joining sessions.csv.
            for r in rows:
                r.setdefault("year", year)
                r.setdefault("round", s["round"])
                r.setdefault("location", s.get("location"))
                r.setdefault("session_name", s.get("session_name"))
            collected[endpoint].extend(rows)
            print(f"      {endpoint:<15} {len(rows):>6} rows")

        if telemetry:
            numbers = sorted({d["driver_number"] for d in collected.get("drivers", [])
                              if d.get("session_key") == sk})
            _fetch_telemetry(sk, numbers, year_dir, api_dir)

    for endpoint, rows in collected.items():
        path = year_dir / f"{endpoint}.csv"
        if only_round is None:
            write_csv(rows, path)
        else:
            # Dedup key must include whatever makes a row unique for THIS endpoint —
            # stints have no lap_number/date, so without stint_number a merge would
            # collapse every stint of a driver into one row.
            merge_csv(rows, path, MERGE_KEYS.get(endpoint, DEFAULT_MERGE_KEYS))


def _fetch_telemetry(session_key: int, driver_numbers: list[int],
                     year_dir: Path, api_dir: Path) -> None:
    """Per-driver car_data + location, merged on nearest timestamp.

    ~38k rows per driver per endpoint per race, so each driver is written straight
    to its own CSV rather than accumulated in memory.
    """
    out_dir = year_dir / "telemetry"
    for dn in driver_numbers:
        out_file = out_dir / f"{session_key}_{dn}.csv"
        if out_file.exists():
            continue
        car = get_json(f"{BASE}/car_data?session_key={session_key}&driver_number={dn}",
                       api_dir / f"{session_key}_{dn}_car_data.json", SLEEP)
        if not car:
            continue
        loc = get_json(f"{BASE}/location?session_key={session_key}&driver_number={dn}",
                       api_dir / f"{session_key}_{dn}_location.json", SLEEP)

        df = pd.DataFrame(car)
        if loc:
            loc_df = pd.DataFrame(loc)[["date", "x", "y", "z"]]
            # Two independent ~3.7 Hz streams with unsynchronised timestamps —
            # nearest-match is the only way to line them up.
            df["date"] = pd.to_datetime(df["date"], format="ISO8601")
            loc_df["date"] = pd.to_datetime(loc_df["date"], format="ISO8601")
            df = pd.merge_asof(df.sort_values("date"), loc_df.sort_values("date"),
                               on="date", direction="nearest",
                               tolerance=pd.Timedelta("0.5s"))
        out_dir.mkdir(parents=True, exist_ok=True)
        df.to_csv(out_file, index=False)
        print(f"      telemetry driver {dn}: {len(df)} rows")
