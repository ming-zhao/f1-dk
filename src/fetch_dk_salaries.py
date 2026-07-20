"""Fetch current DraftKings F1 salaries from the DK draftables API.

Keeps both roster-slot salaries per driver (CPT slot is ~1.5x the D slot,
but we record the real numbers rather than assume the ratio).
Writes to data/dk_salaries/<race_name>.csv.

Usage:
    python3 src/fetch_dk_salaries.py                  # auto-detect current F1 draftgroup
    python3 src/fetch_dk_salaries.py <draftgroup_id>  # manually specify
"""

import sys

import pandas as pd
import requests

from common import DK_DRAFTABLES_URL, DK_HEADERS, DK_SALARIES_DIR, fetch_dk_lobby


def get_current_draftgroup() -> int:
    groups = fetch_dk_lobby().get("DraftGroups", [])
    if not groups:
        raise RuntimeError("No F1 draft groups found in DK lobby")
    return groups[0]["DraftGroupId"]


def fetch_salaries(draftgroup_id: int) -> pd.DataFrame:
    resp = requests.get(DK_DRAFTABLES_URL.format(draftgroup_id),
                        headers=DK_HEADERS, timeout=30)
    resp.raise_for_status()

    # One row per (name, roster slot): drivers appear twice (CPT + D slots).
    rows, seen = [], set()
    for d in resp.json().get("draftables", []):
        key = (d["displayName"], d["rosterSlotId"])
        if key in seen:
            continue
        seen.add(key)
        rows.append({
            "name": d["displayName"],
            "position": d["position"],  # D or CNSTR
            "roster_slot_id": d["rosterSlotId"],
            "salary": d["salary"],
            "team": d.get("teamAbbreviation") or "",
            "fppg": d.get("fppg"),
            "competition": (d.get("competition") or {}).get("name", ""),
            "draftable_id": d["draftableId"],
        })
    return pd.DataFrame(rows)


def main():
    dg_id = int(sys.argv[1]) if len(sys.argv) > 1 else get_current_draftgroup()
    print(f"Draft group: {dg_id}")

    df = fetch_salaries(dg_id)
    race_name = df["competition"].iloc[0] if len(df) > 0 else f"dg_{dg_id}"
    out_file = DK_SALARIES_DIR / (race_name.replace(" ", "_").replace("/", "_") + ".csv")
    DK_SALARIES_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_file, index=False)
    print(f"Wrote {len(df)} rows -> {out_file}")
    print(df[["name", "position", "roster_slot_id", "salary"]].to_string(index=False))


if __name__ == "__main__":
    main()
