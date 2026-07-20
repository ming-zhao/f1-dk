"""Backfill F1 race results + qualifying from the Jolpica API (Ergast successor).

Free, no API key. Rate limits are modest, so responses are cached in data/raw/
and we sleep between requests. Re-running only fetches what's missing.

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
YEARS = range(2023, date.today().year + 1)
SLEEP = 0.6  # stay well under rate limits


def get_json(url: str, cache_file: Path) -> dict:
    if cache_file.exists():
        return json.loads(cache_file.read_text())
    for attempt in range(6):
        resp = requests.get(url, timeout=30)
        if resp.status_code == 429:
            wait = 10 * (attempt + 1)
            print(f"  rate limited, waiting {wait}s...")
            time.sleep(wait)
            continue
        break
    resp.raise_for_status()
    data = resp.json()
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(data))
    time.sleep(SLEEP)
    return data


def season_rounds(year: int) -> list[int]:
    data = get_json(f"{BASE}/{year}.json?limit=100", RAW / f"{year}_schedule.json")
    races = data["MRData"]["RaceTable"]["Races"]
    return [int(r["round"]) for r in races]


def fetch_round(year: int, rnd: int) -> tuple[list[dict], list[dict]]:
    res_data = get_json(
        f"{BASE}/{year}/{rnd}/results.json?limit=40",
        RAW / f"{year}_r{rnd:02d}_results.json",
    )
    qual_data = get_json(
        f"{BASE}/{year}/{rnd}/qualifying.json?limit=40",
        RAW / f"{year}_r{rnd:02d}_qualifying.json",
    )

    results, qualifying = [], []
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
    return results, qualifying


def main():
    all_results, all_qualifying = [], []
    for year in YEARS:
        rounds = season_rounds(year)
        print(f"{year}: {len(rounds)} rounds scheduled")
        for rnd in rounds:
            results, qualifying = fetch_round(year, rnd)
            if not results:
                print(f"  {year} round {rnd}: no results yet (future race), stopping year")
                break
            all_results.extend(results)
            all_qualifying.extend(qualifying)
        print(f"  fetched through round {rnd}")

    PROCESSED.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(all_results).to_csv(PROCESSED / "results.csv", index=False)
    pd.DataFrame(all_qualifying).to_csv(PROCESSED / "qualifying.csv", index=False)
    print(f"\nWrote {len(all_results)} result rows -> {PROCESSED / 'results.csv'}")
    print(f"Wrote {len(all_qualifying)} qualifying rows -> {PROCESSED / 'qualifying.csv'}")


if __name__ == "__main__":
    main()
