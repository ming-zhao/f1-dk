"""Derive track characteristics empirically from race results.

No external track database needed — everything here is computed from our own
historical results, expressed in the terms DK scoring actually cares about:

  overtaking  — how much the finishing order differs from the grid.
                Drives PLACE DIFFERENTIAL points. High = a fast car with a
                grid penalty can climb (Spa, Monza); low = grid is destiny
                (Monaco), so penalised cars are traps and pole sitters are safe.
  chaos       — DNF rate. Drives variance: high-chaos tracks reward cheap
                reliable finishers and punish stacking expensive cars.
  outsider podiums — how often a non-top-3 starter reaches the podium; a
                cleaner read than raw movement on "can an outsider score big?"

Usage:
    python3 src/sim/track_profile.py                 # all circuits, recent era
    python3 src/sim/track_profile.py --since 2014    # custom era cutoff
    python3 src/sim/track_profile.py --circuit spa   # one circuit, with per-race detail
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from util.common import load_raw

# Default era: current turbo-hybrid regulations onward. Older races had wildly
# different reliability and overtaking, which would skew a DFS-oriented profile.
DEFAULT_SINCE = 2014
# Circuits with fewer races than this are shown but excluded from tiering —
# one-off events (Eifel 2020, Mugello 2020) are single noisy samples.
MIN_RACES = 3


def load_results(since: int) -> pd.DataFrame:
    df = load_raw("jolpica", "results")
    return df[df["year"] >= since].copy()


def annotate(df: pd.DataFrame) -> pd.DataFrame:
    """Add the per-driver derived columns the profile is built from."""
    df = df.copy()
    # Pit-lane starts (grid 0) count as starting last in that race
    field = df.groupby(["year", "round"])["finish_position"].transform("max")
    df["grid_adj"] = df["grid"].where(df["grid"] > 0, field)
    df["dnf"] = ~df["position_text"].astype(str).str.match(r"^\d+$")
    df["places_gained"] = df["grid_adj"] - df["finish_position"]
    df["abs_move"] = df["places_gained"].abs()
    df["outsider_podium"] = (df["grid_adj"] > 3) & (df["finish_position"] <= 3)
    df["big_mover"] = df["places_gained"] >= 5  # +5 places = meaningful haul
    return df


def profile(df: pd.DataFrame) -> pd.DataFrame:
    """One row per circuit with DFS-relevant, empirically derived traits.

    Grouped by circuit, NOT by race name — the same track gets renamed across
    years (Interlagos = Brazilian/Sao Paulo, Red Bull Ring = Austrian/Styrian),
    and splitting those would halve every sample.
    """
    # count distinct races as (year, round) pairs so a circuit used twice in one
    # season (2020's double-headers) counts both
    df = df.copy()
    df["race_key"] = df["year"].astype(str) + "-" + df["round"].astype(str)
    g = df.groupby("circuit_id")
    races = g["race_key"].nunique()
    # Overtaking must be measured on FINISHERS only. Including DNFs inflates it:
    # a retirement shows up as a huge position "loss", so crash-prone circuits
    # (Monaco) would look like overtaking festivals when the opposite is true.
    gf = df[~df["dnf"]].groupby("circuit_id")
    prof = pd.DataFrame({
        "race_name": g["race_name"].agg(lambda s: s.mode().iloc[0]),  # most common name
        "races": races,
        "laps": g["laps"].max(),
        "avg_move": gf["abs_move"].mean(),         # overtaking proxy, finishers only
        "dnf_rate": g["dnf"].mean(),
        "big_movers_per_race": df[~df["dnf"]].groupby("circuit_id")["big_mover"].sum() / races,
        "outsider_podiums_per_race": g["outsider_podium"].sum() / races,
    }).reset_index()

    # Tier only on circuits with enough races — one-off events (Eifel, Mugello)
    # would otherwise define the tier boundaries off a single noisy sample.
    solid = prof["races"] >= MIN_RACES
    prof["overtaking"] = "n/a"
    prof["chaos"] = "n/a"
    prof.loc[solid, "overtaking"] = tier(prof.loc[solid, "avg_move"])
    prof.loc[solid, "chaos"] = tier(prof.loc[solid, "dnf_rate"])
    return prof.sort_values("avg_move", ascending=False)


def tier(s: pd.Series) -> pd.Series:
    """Split a metric into LOW/MED/HIGH by terciles of the circuits present."""
    if s.nunique() < 3:
        return pd.Series(["MED"] * len(s), index=s.index)
    return pd.qcut(s, 3, labels=["LOW", "MED", "HIGH"]).astype(str)


def dfs_read(r: pd.Series) -> str:
    """Plain-language DFS takeaway for one circuit."""
    if r["overtaking"] == "HIGH":
        read = ("grid penalties are OPPORTUNITIES — fast cars starting back can climb, "
                "so target them for place differential")
    elif r["overtaking"] == "LOW":
        read = ("grid is close to destiny — penalised cars are traps; "
                "pay up for front-row starters instead")
    else:
        read = "moderate overtaking — differential is available but not automatic"

    if r["chaos"] == "HIGH":
        read += "; high DNF rate means real variance: cheap reliable finishers gain value"
    elif r["chaos"] == "LOW":
        read += "; attrition is low, so finishing-position points dominate"
    return read + "."


def show_circuit(prof: pd.DataFrame, df: pd.DataFrame, circuit: str) -> None:
    row = prof[prof["circuit_id"] == circuit]
    if row.empty:
        print(f"\nNo data for circuit '{circuit}'. Available: "
              f"{', '.join(sorted(prof.circuit_id))}")
        return
    r = row.iloc[0]
    print(f"\n=== {r['race_name']} ({circuit}) ===")
    print(f"races in era     : {r['races']}")
    print(f"race distance    : {r['laps']:.0f} laps")
    print(f"overtaking       : {r['overtaking']} (avg {r['avg_move']:.2f} places moved/driver)")
    print(f"chaos            : {r['chaos']} (DNF rate {r['dnf_rate'] * 100:.0f}%)")
    print(f"big movers (+5)  : {r['big_movers_per_race']:.1f} per race")
    print(f"outsider podiums : {r['outsider_podiums_per_race']:.2f} per race")
    print(f"\nDFS read: {dfs_read(r)}")

    sub = df[df["circuit_id"] == circuit]
    per_race = (
        sub.sort_values("finish_position")
        .groupby(["year", "round"])
        .agg(winner=("driver_code", "first"),
             won_from_grid=("grid", "first"),
             dnfs=("dnf", "sum"),
             best_gain=("places_gained", "max"))
        .reset_index()
        .sort_values("year")
    )
    print("\nPer-race history at this circuit:")
    print(per_race.to_string(index=False))


def main():
    args = sys.argv[1:]
    since = int(args[args.index("--since") + 1]) if "--since" in args else DEFAULT_SINCE
    circuit = args[args.index("--circuit") + 1] if "--circuit" in args else None

    df = load_results(since)
    if df.empty:
        print(f"No results at or after {since}. Run src/data/data_crawler.py --source jolpica first.")
        return
    df = annotate(df)
    print(f"Era: {since}–{df.year.max()} | {df.groupby(['year', 'round']).ngroups} races "
          f"| {df.circuit_id.nunique()} circuits")

    prof = profile(df)

    if circuit:
        show_circuit(prof, df, circuit)
        return

    print("\n" + "=" * 104)
    print("TRACK PROFILES (sorted by overtaking — top = best for place-differential plays)")
    print("=" * 104)
    show = prof[["race_name", "circuit_id", "races", "laps", "avg_move", "overtaking",
                 "dnf_rate", "chaos", "big_movers_per_race",
                 "outsider_podiums_per_race"]].copy()
    show["dnf_rate"] = (show["dnf_rate"] * 100).round(0)
    show = show.rename(columns={"dnf_rate": "dnf%", "avg_move": "places_moved",
                                "big_movers_per_race": "big_movers",
                                "outsider_podiums_per_race": "outsider_podiums"})
    print(show.to_string(index=False, float_format="%.2f"))

    thin = prof[prof["races"] < MIN_RACES]
    if len(thin):
        print(f"\nNote: {len(thin)} circuit(s) have <{MIN_RACES} races in this era "
              f"(shown but not tiered): {', '.join(thin.circuit_id)}")


if __name__ == "__main__":
    main()
