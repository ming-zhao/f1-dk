"""Jolpica (Ergast successor) — race + qualifying results, 1950-present.

Free, no API key. Rate-limits easily, so we sleep 0.8s between calls and back off
on 429.

Output:
    data/raw/jolpica/<year>/api/rNN_results.json      cached API responses
    data/raw/jolpica/<year>/api/rNN_qualifying.json
    data/raw/jolpica/<year>/results.csv               one row per driver per race
    data/raw/jolpica/<year>/qualifying.csv            one row per driver per quali
"""

from datetime import date
from typing import Optional

from ._http import DATA, get_json, merge_csv, write_csv

BASE = "https://api.jolpi.ca/ergast/f1"
FIRST_YEAR = 1950
SLEEP = 0.8


def fetch(year: int, only_round: Optional[int] = None, **_) -> None:
    """Fetch a season, or a single round of it, into data/raw/jolpica/<year>/."""
    if year < FIRST_YEAR:
        print(f"  {year}: before {FIRST_YEAR}, skipping")
        return

    year_dir = DATA / "raw" / "jolpica" / str(year)
    api_dir = year_dir / "api"

    schedule = get_json(f"{BASE}/{year}.json?limit=100",
                        api_dir / "schedule.json", SLEEP)
    if schedule is None:
        print(f"  {year}: no schedule, skipping")
        return
    races = schedule["MRData"]["RaceTable"]["Races"]
    if not races:
        print(f"  {year}: no rounds scheduled")
        return

    # round -> "Race Name (Locality, Country)", so the log names the actual race.
    where = {}
    for r in races:
        loc = r.get("Circuit", {}).get("Location", {})
        place = ", ".join(x for x in (loc.get("locality"), loc.get("country")) if x)
        where[int(r["round"])] = f"{r['raceName']} ({place})" if place else r["raceName"]

    rounds = sorted(where)
    if only_round is not None:
        if only_round not in where:
            print(f"  {year}: round {only_round} not in schedule "
                  f"(has 1-{max(rounds)}), skipping")
            return
        rounds = [only_round]

    results, qualifying, skipped = [], [], []
    current_year = date.today().year

    for rnd in rounds:
        label = f"  {year} round {rnd:>2} — {where[rnd]}"
        res = get_json(f"{BASE}/{year}/{rnd}/results.json?limit=40",
                       api_dir / f"r{rnd:02d}_results.json", SLEEP)
        if res is None:
            print(f"{label}: fetch failed")
            skipped.append(rnd)
            continue

        rows = res["MRData"]["RaceTable"]["Races"]
        if not rows:
            # Future race in the current season -> stop; a genuine gap otherwise.
            if year == current_year:
                print(f"{label}: not run yet, stopping season")
                break
            print(f"{label}: no results")
            continue

        race = rows[0]
        n_before = len(results)
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

        qual = get_json(f"{BASE}/{year}/{rnd}/qualifying.json?limit=40",
                        api_dir / f"r{rnd:02d}_qualifying.json", SLEEP)
        n_q = 0
        if qual is not None:
            qraces = qual["MRData"]["RaceTable"]["Races"]
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
                    n_q += 1
        print(f"{label}: {len(results) - n_before} results, {n_q} quali")

    # A single-round fetch must not clobber the rest of the season.
    keys = ["year", "round", "driver_id"]
    if only_round is None:
        write_csv(results, year_dir / "results.csv")
        write_csv(qualifying, year_dir / "qualifying.csv")
    else:
        merge_csv(results, year_dir / "results.csv", keys)
        merge_csv(qualifying, year_dir / "qualifying.csv", keys)
    if skipped:
        print(f"    {len(skipped)} round(s) failed, re-run to retry: {skipped}")
