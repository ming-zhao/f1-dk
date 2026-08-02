"""Fetch F1 race results + qualifying for a range of seasons, one folder per year.

Free, no API key (Jolpica / Ergast successor). Separate from fetch_jolpica.py
(which backfills 1950-present into flat data/raw + data/processed, feeding the
dashboard pipeline) — this script is for pulling a specific window of recent
seasons into their own self-contained folders, e.g. for standalone analysis.

Output per year:
    data/<year>/raw/r<round>_results.json
    data/<year>/raw/r<round>_qualifying.json
    data/<year>/results.csv      (one row per driver per race)
    data/<year>/qualifying.csv   (one row per driver per quali session)

Usage:
    python3 src/fetch_by_year.py                  # last 5 years + current year
    python3 src/fetch_by_year.py 2019 2020 2021    # explicit years
"""

import sys
import json
import time
from datetime import date
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

BASE = "https://api.jolpi.ca/ergast/f1"
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SLEEP = 0.8  # stay well under rate limits
MAX_RETRIES = 8
MAX_BACKOFF = 60


def get_json(url: str, cache_file: Path) -> Optional[dict]:
    """Fetch + cache a URL's JSON. Returns None (not an exception) if it
    keeps 429ing after MAX_RETRIES — callers must handle that as "couldn't
    get this one, move on" rather than a fatal error."""
    if cache_file.exists():
        return json.loads(cache_file.read_text())
    resp = None
    for attempt in range(MAX_RETRIES):
        resp = requests.get(url, timeout=30)
        if resp.status_code == 429:
            wait = min(10 * (attempt + 1), MAX_BACKOFF)
            print(f"  rate limited, waiting {wait}s...")
            time.sleep(wait)
            continue
        break
    if resp is None or resp.status_code == 429:
        print(f"  WARNING: giving up on {url} after {MAX_RETRIES} rate-limited retries, skipping")
        return None
    if not resp.ok:
        print(f"  WARNING: {resp.status_code} for {url}, skipping")
        return None
    data = resp.json()
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(data))
    time.sleep(SLEEP)
    return data


def season_rounds(year: int, raw_dir: Path) -> list[int]:
    data = get_json(f"{BASE}/{year}.json?limit=100", raw_dir / "schedule.json")
    if data is None:
        return []
    races = data["MRData"]["RaceTable"]["Races"]
    return [int(r["round"]) for r in races]


def fetch_round(year: int, rnd: int, raw_dir: Path) -> tuple[list[dict], list[dict], bool]:
    """Returns (results, qualifying, fetch_ok). fetch_ok=False means the
    results request itself failed (rate-limited out) — distinct from a
    legitimately empty response for a future race that hasn't run yet."""
    res_data = get_json(
        f"{BASE}/{year}/{rnd}/results.json?limit=40",
        raw_dir / f"r{rnd:02d}_results.json",
    )
    qual_data = get_json(
        f"{BASE}/{year}/{rnd}/qualifying.json?limit=40",
        raw_dir / f"r{rnd:02d}_qualifying.json",
    )

    results, qualifying = [], []
    if res_data is None:
        return results, qualifying, False

    races = res_data["MRData"]["RaceTable"]["Races"]
    if races:
        race = races[0]
        for r in race["Results"]:
            results.append({
                "year": year,
                "round": rnd,
                "race_name": race["raceName"],
                "circuit_id": race["Circuit"]["circuitId"],
                "date": race["date"],
                "driver_id": r["Driver"]["driverId"],
                "driver_code": r["Driver"].get("code", ""),
                "constructor_id": r["Constructor"]["constructorId"],
                "grid": int(r["grid"]),  # 0 = pit lane start
                "finish_position": int(r["position"]),
                "position_text": r["positionText"],  # "R" = retired etc.
                "status": r["status"],
                "laps": int(r["laps"]),
                "points_f1": float(r["points"]),
                "fastest_lap_rank": int(r.get("FastestLap", {}).get("rank", 0)),
            })

    if qual_data is not None:
        qraces = qual_data["MRData"]["RaceTable"]["Races"]
        if qraces:
            for q in qraces[0]["QualifyingResults"]:
                qualifying.append({
                    "year": year,
                    "round": rnd,
                    "driver_id": q["Driver"]["driverId"],
                    "constructor_id": q["Constructor"]["constructorId"],
                    "quali_position": int(q["position"]),
                    "q1": q.get("Q1", ""),
                    "q2": q.get("Q2", ""),
                    "q3": q.get("Q3", ""),
                })
    return results, qualifying, True


def fetch_year(year: int) -> None:
    year_dir = DATA / str(year)
    raw_dir = year_dir / "raw"
    print(f"\n=== {year} ===")
    rounds = season_rounds(year, raw_dir)
    if not rounds:
        print(f"{year}: no schedule data found, skipping")
        return
    print(f"{year}: {len(rounds)} rounds scheduled")

    year_results, year_qualifying, skipped = [], [], []
    current_year = date.today().year
    last_fetched = None
    for rnd in rounds:
        results, qualifying, fetch_ok = fetch_round(year, rnd, raw_dir)
        if not fetch_ok:
            print(f"  round {rnd}: fetch failed after retries, skipping (rerun to retry)")
            skipped.append(rnd)
            continue
        if not results:
            if year == current_year:
                print(f"  round {rnd}: no results yet (future race), stopping year")
                break
            print(f"  round {rnd}: no results in response, skipping")
            continue
        year_results.extend(results)
        year_qualifying.extend(qualifying)
        last_fetched = rnd
    if last_fetched is not None:
        print(f"  fetched through round {last_fetched}")

    year_dir.mkdir(parents=True, exist_ok=True)
    if year_results:
        pd.DataFrame(year_results).to_csv(year_dir / "results.csv", index=False)
        print(f"  wrote {len(year_results)} result rows -> {year_dir / 'results.csv'}")
    if year_qualifying:
        pd.DataFrame(year_qualifying).to_csv(year_dir / "qualifying.csv", index=False)
        print(f"  wrote {len(year_qualifying)} qualifying rows -> {year_dir / 'qualifying.csv'}")
    if skipped:
        print(f"  {len(skipped)} round(s) failed to fetch, rerun this script to retry: {skipped}")


def main():
    if len(sys.argv) > 1:
        years = [int(y) for y in sys.argv[1:]]
    else:
        current_year = date.today().year
        years = list(range(current_year - 5, current_year + 1))
    print(f"Fetching years: {years}")
    for year in years:
        fetch_year(year)


if __name__ == "__main__":
    main()
