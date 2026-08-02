"""List available DraftKings F1 contests (entry fee, prize pool, entries).

Usage:
    python3 src/fetch_dk_contests.py              # all F1 contests
    python3 src/fetch_dk_contests.py --cheap      # only contests <= $1.00 entry
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sys

import pandas as pd

from util.common import fetch_dk_lobby


def fetch_contests() -> pd.DataFrame:
    rows = []
    for c in fetch_dk_lobby().get("Contests", []):
        rows.append({
            "contest_id": c.get("id"),
            "name": c.get("n", ""),
            "entry_fee": c.get("a", 0),
            "prize_pool": c.get("po", 0),
            "max_entries": c.get("m", 0),
            "current_entries": c.get("ec", 0),
            "entries_per_user": c.get("mec", 1),
            "game_type": c.get("gameType", ""),
            "starts": c.get("sd", ""),
            "draft_group_id": c.get("dg", ""),
        })
    return pd.DataFrame(rows)


def main():
    df = fetch_contests()
    if "--cheap" in sys.argv:
        df = df[df["entry_fee"] <= 1.0]
    df = df.sort_values("entry_fee")

    print(f"Found {len(df)} F1 contests")
    print()
    print(df[[
        "name", "entry_fee", "prize_pool", "current_entries",
        "max_entries", "entries_per_user", "game_type"
    ]].to_string(index=False))


if __name__ == "__main__":
    main()
