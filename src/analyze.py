"""Value analysis: find over/under-priced drivers for this week's DK contest.

Combines historical DK points with current salaries to compute:
- Points per $1000 salary (value metric)
- Place differential patterns (who gains places consistently)
- Consistency vs ceiling analysis (std, max pts)
- Captain candidates (high ceiling * 1.5x)

Usage:
    python3 src/analyze.py                          # uses latest salary file
    python3 src/analyze.py data/dk_salaries/X.csv   # use specific salary file
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from common import CONSTR_NAME_MAP, NAME_TO_CODE, PROCESSED_DIR, ROOT, latest_salary_file

SCORING = yaml.safe_load((ROOT / "config" / "scoring.yaml").read_text())
CAPTAIN_MULT = SCORING["captain_multiplier"]


def main():
    sal_file = Path(sys.argv[1]) if len(sys.argv) > 1 else latest_salary_file()

    salaries = pd.read_csv(sal_file)
    driver_pts = pd.read_csv(PROCESSED_DIR / "dk_driver_points.csv")
    constructor_pts = pd.read_csv(PROCESSED_DIR / "dk_constructor_points.csv")

    print(f"Salary file: {sal_file.name}")
    print(f"Points data: {driver_pts.year.min()}–{driver_pts.year.max()}, "
          f"{driver_pts.year.nunique()} seasons")
    print()

    # --- Driver stats: recent races weighted heavier (last 10 = 2x) ---
    recent = driver_pts.sort_values(["year", "round"], ascending=False).copy()
    recent["rank"] = recent.groupby("driver_code").cumcount()
    recent["weight"] = np.where(recent["rank"] < 10, 2.0, 1.0)
    recent["wpts"] = recent["dk_points_total"] * recent["weight"]

    g = recent.groupby("driver_code")
    driver_stats = pd.DataFrame({
        "avg_pts": g["wpts"].sum() / g["weight"].sum(),
        "recent_avg": recent[recent["rank"] < 10].groupby("driver_code")["dk_points_total"].mean(),
        "std_pts": g["dk_points_total"].std(),
        "max_pts": g["dk_points_total"].max(),
        "avg_place_diff": g["pts_place_diff"].mean(),
        "races": g.size(),
    }).reset_index()

    # --- Merge with salaries (driver slot rows only, not the CPT duplicates) ---
    driver_sal = salaries[salaries["position"] == "D"].copy()
    if "roster_slot_id" in driver_sal.columns:
        # keep the higher (CPT) salary row per driver for captain math,
        # lower (D) for the value metric
        cpt_sal = driver_sal.groupby("name")["salary"].max()
        d_sal = driver_sal.groupby("name")["salary"].min()
        driver_sal = driver_sal.drop_duplicates("name")[["name", "team"]]
        driver_sal["salary"] = driver_sal["name"].map(d_sal)
        driver_sal["salary_cpt"] = driver_sal["name"].map(cpt_sal)
    else:
        driver_sal["salary_cpt"] = driver_sal["salary"]

    driver_sal["driver_code"] = driver_sal["name"].map(NAME_TO_CODE)
    merged = driver_sal.merge(driver_stats, on="driver_code", how="left")
    merged["pts_per_1k"] = merged["avg_pts"] / (merged["salary"] / 1000)
    merged["captain_value"] = (merged["avg_pts"] * CAPTAIN_MULT) / (merged["salary_cpt"] / 1000)
    merged = merged.sort_values("pts_per_1k", ascending=False)

    print("=" * 80)
    print("DRIVER VALUE RANKINGS (sorted by pts/$1K, driver-slot salary)")
    print("=" * 80)
    cols = ["name", "salary", "avg_pts", "recent_avg", "std_pts", "max_pts",
            "avg_place_diff", "pts_per_1k", "captain_value"]
    print(merged[cols].to_string(index=False, float_format="%.1f"))

    print()
    print("=" * 80)
    print("CAPTAIN CANDIDATES (avg_pts * 1.5 / CPT salary)")
    print("=" * 80)
    captain_df = merged.sort_values("captain_value", ascending=False).head(8)
    print(captain_df[["name", "salary_cpt", "avg_pts", "max_pts", "captain_value"]]
          .to_string(index=False, float_format="%.1f"))

    print()
    print("=" * 80)
    print("HIGH PLACE-DIFFERENTIAL DRIVERS (gain places from grid)")
    print("=" * 80)
    diff_df = merged.sort_values("avg_place_diff", ascending=False).head(8)
    print(diff_df[["name", "salary", "avg_pts", "avg_place_diff", "pts_per_1k"]]
          .to_string(index=False, float_format="%.1f"))

    # --- Constructors ---
    print()
    print("=" * 80)
    print("CONSTRUCTOR VALUE RANKINGS")
    print("=" * 80)
    constr_sal = salaries[salaries["position"] == "CNSTR"].copy()
    constr_stats = (
        constructor_pts.sort_values(["year", "round"], ascending=False)
        .groupby("constructor_id")
        .head(15)
        .groupby("constructor_id")["dk_points_total"]
        .agg(avg_pts="mean", std_pts="std", max_pts="max")
        .reset_index()
    )
    constr_sal["constructor_id"] = constr_sal["name"].map(CONSTR_NAME_MAP)
    constr_merged = constr_sal.merge(constr_stats, on="constructor_id", how="left")
    constr_merged["pts_per_1k"] = constr_merged["avg_pts"] / (constr_merged["salary"] / 1000)
    constr_merged = constr_merged.sort_values("pts_per_1k", ascending=False)
    print(constr_merged[["name", "salary", "avg_pts", "std_pts", "max_pts", "pts_per_1k"]]
          .to_string(index=False, float_format="%.1f"))


if __name__ == "__main__":
    main()
