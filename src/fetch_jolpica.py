"""Backfill F1 race results + qualifying from the Jolpica API (Ergast successor).

Free, no API key. Rate limits are modest, so responses are cached in data/raw/
and we sleep between requests. Re-running only fetches what's missing.

Resilient to persistent rate-limiting: a URL that keeps 429ing after all
retries is logged and skipped (returns None) rather than crashing the whole
run, and whatever's been fetched so far is always written to the processed
CSVs on exit (success, error, or Ctrl-C) via the try/finally in main() — a
failure partway through a decades-long backfill no longer loses everything
accumulated before it.

Output:
    data/raw/<year>_r<round>_results.json
    data/raw/<year>_r<round>_qualifying.json
    data/processed/results.csv      (one row per driver per race)
    data/processed/qualifying.csv   (one row per driver per quali session)
"""

import json
import time
from datetime import date
from pathlib import Path

import pandas as pd
import requests

BASE = "https://api.jolpi.ca/ergast/f1"
ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
YEARS = range(1950, date.today().year + 1)
SLEEP = 0.8  # stay well under rate limits
MAX_RETRIES = 8
MAX_BACKOFF = 60  # cap per-retry wait so one stuck URL can't stall for hours


def get_json(url: str, cache_file: Path) -> dict | None:
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


def season_rounds(year: int) -> list[int]:
    data = get_json(f"{BASE}/{year}.json?limit=100", RAW / f"{year}_schedule.json")
    if data is None:
        return []
    races = data["MRData"]["RaceTable"]["Races"]
    return [int(r["round"]) for r in races]


def fetch_round(year: int, rnd: int) -> tuple[list[dict], list[dict], bool]:
    """Returns (results, qualifying, fetch_ok). fetch_ok=False means the
    results request itself failed (rate-limited out) — distinct from a
    legitimately empty response for a future race that hasn't run yet."""
    res_data = get_json(
        f"{BASE}/{year}/{rnd}/results.json?limit=40",
        RAW / f"{year}_r{rnd:02d}_results.json",
    )
    qual_data = get_json(
        f"{BASE}/{year}/{rnd}/qualifying.json?limit=40",
        RAW / f"{year}_r{rnd:02d}_qualifying.json",
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


def main():
    all_results, all_qualifying = [], []
    skipped = []  # (year, round) pairs that failed to fetch, for a rerun to retry
    current_year = date.today().year
    try:
        for year in YEARS:
            rounds = season_rounds(year)
            if not rounds:
                print(f"{year}: no schedule data (skipped or truly no season)")
                continue
            print(f"{year}: {len(rounds)} rounds scheduled")
            last_fetched = None
            for rnd in rounds:
                results, qualifying, fetch_ok = fetch_round(year, rnd)
                if not fetch_ok:
                    print(f"  {year} round {rnd}: fetch failed after retries, skipping (will retry on rerun)")
                    skipped.append((year, rnd))
                    continue
                if not results:
                    if year == current_year:
                        print(f"  {year} round {rnd}: no results yet (future race), stopping year")
                        break
                    print(f"  {year} round {rnd}: no results in response, skipping")
                    continue
                all_results.extend(results)
                all_qualifying.extend(qualifying)
                last_fetched = rnd
            if last_fetched is not None:
                print(f"  fetched through round {last_fetched}")
    finally:
        # Always persist whatever we got, even on a crash or interrupt partway
        # through — the raw JSON cache is safe either way, but without this
        # the aggregated CSVs would silently lose everything on failure.
        PROCESSED.mkdir(parents=True, exist_ok=True)
        if all_results:
            pd.DataFrame(all_results).to_csv(PROCESSED / "results.csv", index=False)
            print(f"\nWrote {len(all_results)} result rows -> {PROCESSED / 'results.csv'}")
        if all_qualifying:
            pd.DataFrame(all_qualifying).to_csv(PROCESSED / "qualifying.csv", index=False)
            print(f"Wrote {len(all_qualifying)} qualifying rows -> {PROCESSED / 'qualifying.csv'}")
        if skipped:
            print(f"\n{len(skipped)} round(s) failed to fetch after retries (rerun this script to "
                  f"retry just these — everything else is cached): {skipped}")


if __name__ == "__main__":
    main()
