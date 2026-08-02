"""DraftKings — salaries for the upcoming race.

Free, but needs a browser User-Agent (see src/util/common.py DK_HEADERS).

Deliberately NOT split by year: DK only ever serves the upcoming race and publishes
no salary history, so a race week not snapshotted is lost permanently. Files are
keyed by race name instead.

Output:
    data/raw/draftkings/<race_name>.csv   one row per (driver, roster slot)
"""

from typing import Optional

import requests

from ._http import DATA, write_csv


def fetch(year: Optional[int] = None, only_round: Optional[int] = None, **_) -> None:
    """Fetch the upcoming race's salaries. `year`/`only_round` are ignored — DK
    serves only the current draft group, so there's nothing to select."""
    # Imported here so the other sources work even if util.common is unhappy.
    from util.common import DK_DRAFTABLES_URL, DK_HEADERS, fetch_dk_lobby

    try:
        groups = fetch_dk_lobby().get("DraftGroups", [])
    except requests.RequestException as exc:
        print(f"  DK lobby unreachable ({type(exc).__name__}) — skipping")
        return
    if not groups:
        print("  no F1 draft groups in the DK lobby (no upcoming race?)")
        return

    dg_id = groups[0]["DraftGroupId"]
    try:
        resp = requests.get(DK_DRAFTABLES_URL.format(dg_id),
                            headers=DK_HEADERS, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"  draftables fetch failed ({type(exc).__name__}) — skipping")
        return

    # Drivers appear twice — once per roster slot (CPT and D) — so keep both rows
    # but drop exact duplicates.
    rows, seen = [], set()
    for d in resp.json().get("draftables", []):
        key = (d["displayName"], d["rosterSlotId"])
        if key in seen:
            continue
        seen.add(key)
        rows.append({
            "name": d["displayName"],
            "position": d["position"],            # D or CNSTR
            "roster_slot_id": d["rosterSlotId"],  # distinguishes CPT vs D slot
            "salary": d["salary"],
            "team": d.get("teamAbbreviation") or "",
            "fppg": d.get("fppg"),
            "competition": (d.get("competition") or {}).get("name", ""),
            "draftable_id": d["draftableId"],
        })
    if not rows:
        print("  draft group returned no draftables")
        return

    race = rows[0]["competition"] or f"dg_{dg_id}"
    print(f"  upcoming race — {race} [draft group {dg_id}]")
    fname = race.replace(" ", "_").replace("/", "_") + ".csv"
    write_csv(rows, DATA / "raw" / "draftkings" / fname)
