"""Build dashboard/data.js from processed data + current DK salaries.

Packages driver stats (finish distributions, DNF rate, grid tendency),
constructor info, race notes (pit strategy etc.), and the scoring rules into
a single JS file so the dashboard works as a plain local file (no server).

Driver-team assignments and both roster-slot salaries come from the salary
CSV (DK is the source of truth) — nothing per-driver is hardcoded here.

Run after refreshing data:
    python3 dashboard/build_data.py
"""

import json
import sys
from pathlib import Path

import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from common import (  # noqa: E402
    DK_ABBREV_TO_ID, NAME_TO_CODE, PROCESSED_DIR, ROOT, TEAMS, latest_salary_file,
)

OUT = ROOT / "dashboard" / "data.js"
RACE_NOTES = ROOT / "config" / "race_notes.yaml"

SCORING = yaml.safe_load((ROOT / "config" / "scoring.yaml").read_text())

# Priors for entries with little/no history (new drivers/teams)
DRIVER_PRIOR = {
    "avgFinish": 12.0, "stdFinish": 4.0, "avgGrid": 12.0, "stdGrid": 3.0,
    "dnfRate": 0.12, "avgDk": 15.0,
}
CONSTRUCTOR_PRIOR = {"avgDk": 20.0, "maxDk": 35.0, "bothPtsRate": 0.05}


def build_race_history(dk_pts: pd.DataFrame, dk_cpts: pd.DataFrame) -> list:
    """One entry per past race actually run: real DK points scored by every
    driver/constructor that race, for the Testing AI tab's backtest — picks
    a lineup with today's rules/salaries, then checks what it would have
    actually scored using real historical results (not projections).
    """
    races = {}
    for _, row in dk_pts.iterrows():
        key = (int(row["year"]), int(row["round"]))
        races.setdefault(key, {"year": int(row["year"]), "round": int(row["round"]),
                                "raceName": row["race_name"], "drivers": {}, "constructors": {}})
        races[key]["drivers"][row["driver_code"]] = float(row["dk_points_total"])
    for _, row in dk_cpts.iterrows():
        key = (int(row["year"]), int(row["round"]))
        races.setdefault(key, {"year": int(row["year"]), "round": int(row["round"]),
                                "raceName": row["race_name"], "drivers": {}, "constructors": {}})
        races[key]["constructors"][row["constructor_id"]] = float(row["dk_points_total"])
    return sorted(races.values(), key=lambda r: (r["year"], r["round"]))


def race_total_laps(results: pd.DataFrame, race_name: str) -> int:
    """Look up the circuit's race distance from past results at this event.

    Matches the DK competition name (e.g. 'Belgian Grand Prix 2026') against
    Jolpica race names ('Belgian Grand Prix').
    """
    base = race_name.rsplit(" ", 1)[0]  # strip trailing year
    past = results[results["race_name"] == base]
    if len(past):
        return int(past["laps"].max())
    return 55  # median F1 race distance as fallback


def main():
    results = pd.read_csv(PROCESSED_DIR / "results.csv")
    dk_pts = pd.read_csv(PROCESSED_DIR / "dk_driver_points.csv")
    dk_cpts = pd.read_csv(PROCESSED_DIR / "dk_constructor_points.csv")
    salaries = pd.read_csv(latest_salary_file())
    race_name = salaries["competition"].iloc[0]

    results = results.sort_values(["year", "round"], ascending=False)
    dk_pts = dk_pts.sort_values(["year", "round"], ascending=False)
    dk_cpts = dk_cpts.sort_values(["year", "round"], ascending=False)

    # --- Drivers: one entry per driver, both slot salaries from the CSV ---
    driver_rows = salaries[salaries["position"] == "D"]
    drivers = []
    for name, grp in driver_rows.groupby("name", sort=False):
        code = NAME_TO_CODE.get(name)
        team = DK_ABBREV_TO_ID.get(grp["team"].iloc[0])
        if code is None or team is None:
            print(f"  WARNING: unmapped driver/team skipped: {name} ({grp['team'].iloc[0]})")
            continue
        salary_cpt = int(grp["salary"].max())
        salary_d = int(grp["salary"].min())

        hist = results[results["driver_code"] == code].head(20)
        pts_hist = dk_pts[dk_pts["driver_code"] == code].head(20)

        stats = dict(DRIVER_PRIOR)
        if len(hist) > 0:
            finished = hist[hist["position_text"].str.match(r"\d+")]
            stats["dnfRate"] = 1 - len(finished) / len(hist)
            if len(finished):
                stats["avgFinish"] = float(finished["finish_position"].mean())
            if len(finished) > 1:
                stats["stdFinish"] = float(finished["finish_position"].std())
            started = hist[hist["grid"] > 0]
            if len(started):
                stats["avgGrid"] = float(started["grid"].mean())
            if len(started) > 1:
                stats["stdGrid"] = float(started["grid"].std())
            if len(pts_hist):
                stats["avgDk"] = float(pts_hist["dk_points_total"].mean())

        drivers.append({
            "name": name,
            "code": code,
            "team": team,
            "salaryCpt": salary_cpt,
            "salary": salary_d,
            "avgFinish": round(stats["avgFinish"], 2),
            "stdFinish": round(max(stats["stdFinish"], 1.5), 2),
            "avgGrid": round(stats["avgGrid"], 2),
            "stdGrid": round(max(stats["stdGrid"], 1.5), 2),
            "dnfRate": round(min(max(stats["dnfRate"], 0.03), 0.35), 3),
            "avgDk": round(stats["avgDk"], 1),
            "races": int(len(hist)),
        })

    # --- Constructors ---
    constructors = []
    for _, srow in salaries[salaries["position"] == "CNSTR"].iterrows():
        team = TEAMS.get(srow["name"])
        if team is None:
            print(f"  WARNING: unmapped constructor skipped: {srow['name']}")
            continue
        cid = team["id"]
        hist = dk_cpts[dk_cpts["constructor_id"] == cid].head(20)
        stats = dict(CONSTRUCTOR_PRIOR)
        if len(hist) > 0:
            stats["avgDk"] = float(hist["dk_points_total"].mean())
            stats["maxDk"] = float(hist["dk_points_total"].max())
            stats["bothPtsRate"] = float((hist["pts_both_in_points"] > 0).mean())
        constructors.append({
            "name": srow["name"],
            "shortName": team["short"],
            "id": cid,
            "salary": int(srow["salary"]),
            "avgDk": round(stats["avgDk"], 1),
            "maxDk": round(stats["maxDk"], 1),
            "bothPtsRate": round(stats["bothPtsRate"], 3),
            "races": int(len(hist)),
        })

    # --- Race notes (pit strategy, penalties, weather) — hand/agent-curated ---
    race_notes = {}
    if RACE_NOTES.exists():
        race_notes = yaml.safe_load(RACE_NOTES.read_text()) or {}
        if race_notes.get("race") != race_name:
            print(f"  NOTE: race_notes.yaml is for '{race_notes.get('race')}', "
                  f"current race is '{race_name}' — shipping it anyway, please update")

    payload = {
        "raceName": race_name,
        "totalLaps": race_total_laps(results, race_name),
        "salaryCap": SCORING["salary_cap"],
        "captainMultiplier": SCORING["captain_multiplier"],
        "scoring": SCORING,
        "drivers": sorted(drivers, key=lambda d: -d["salaryCpt"]),
        "constructors": sorted(constructors, key=lambda c: -c["salary"]),
        "raceNotes": race_notes,
        "raceHistory": build_race_history(dk_pts, dk_cpts),
    }

    OUT.write_text("// Generated by dashboard/build_data.py — do not edit by hand\n"
                   "const F1DATA = " + json.dumps(payload, indent=1) + ";\n",
                   encoding="utf-8")
    print(f"Wrote {OUT} — {len(drivers)} drivers, {len(constructors)} constructors, "
          f"{len(payload['raceHistory'])} historical races, "
          f"race: {race_name}, laps: {payload['totalLaps']}")


if __name__ == "__main__":
    main()
