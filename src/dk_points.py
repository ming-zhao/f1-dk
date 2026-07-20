"""DraftKings F1 fantasy points simulator.

Reads the verified scoring rules from config/scoring.yaml and the backfilled
race/qualifying data to compute what each driver/constructor WOULD have scored
in every past race.

Note: laps-led points are not computed (lap-by-lap leader data isn't in
Jolpica results) — a small underestimate for race leaders only.

Output:
    data/processed/dk_driver_points.csv   — per-driver per-race DK points breakdown
    data/processed/dk_constructor_points.csv
"""

import pandas as pd
import yaml

from common import PROCESSED_DIR, ROOT

SCORING = yaml.safe_load((ROOT / "config" / "scoring.yaml").read_text())


def compute_driver_points(results: pd.DataFrame) -> pd.DataFrame:
    """Compute DK fantasy points for each driver in each race."""
    cfg = SCORING["driver"]
    pos_pts = cfg["finishing_position"]

    rows = []
    for (year, rnd), race_df in results.groupby(["year", "round"]):
        total_laps = race_df["laps"].max()
        # Pit-lane starts (grid 0) count as starting last
        pit_lane_grid = len(race_df)
        # Best finish per team, for the defeated-teammate bonus
        team_best = race_df.groupby("constructor_id")["finish_position"].min()
        team_size = race_df.groupby("constructor_id").size()

        for _, row in race_df.iterrows():
            grid = row["grid"] or pit_lane_grid
            team = row["constructor_id"]
            beat_teammate = (
                team_size[team] > 1 and row["finish_position"] == team_best[team]
            )
            classified = total_laps > 0 and row["laps"] >= total_laps * 0.9

            pts_finish = pos_pts.get(row["finish_position"], 0)
            pts_diff = (grid - row["finish_position"]) * cfg["place_differential_per_position"]
            pts_fastest = cfg["fastest_lap"] if row["fastest_lap_rank"] == 1 else 0
            pts_classified = cfg["classified_finish"] if classified else 0
            pts_teammate = cfg["defeated_teammate"] if beat_teammate else 0

            rows.append({
                "year": year,
                "round": rnd,
                "race_name": row["race_name"],
                "driver_id": row["driver_id"],
                "driver_code": row["driver_code"],
                "constructor_id": team,
                "grid": row["grid"],
                "finish_position": row["finish_position"],
                "pts_finish": pts_finish,
                "pts_place_diff": pts_diff,
                "pts_fastest_lap": pts_fastest,
                "pts_classified": pts_classified,
                "pts_defeated_teammate": pts_teammate,
                "dk_points_total": pts_finish + pts_diff + pts_fastest
                                   + pts_classified + pts_teammate,
            })

    return pd.DataFrame(rows)


def compute_constructor_points(results: pd.DataFrame) -> pd.DataFrame:
    """Compute DK fantasy points for each constructor in each race."""
    cfg = SCORING["constructor"]
    pos_pts = cfg["finishing_position"]

    rows = []
    for (year, rnd), race_df in results.groupby(["year", "round"]):
        total_laps = race_df["laps"].max()

        for cid, team_df in race_df.groupby("constructor_id"):
            finish = team_df["finish_position"]
            two_cars = len(team_df) == 2

            pts_finish = sum(pos_pts.get(p, 0) for p in finish)
            pts_fastest = cfg["fastest_lap"] if (team_df["fastest_lap_rank"] == 1).any() else 0
            pts_both_classified = (
                cfg["both_cars_classified"]
                if two_cars and total_laps > 0 and (team_df["laps"] >= total_laps * 0.9).all()
                else 0
            )
            pts_both_points = cfg["both_cars_in_points"] if two_cars and (finish <= 10).all() else 0
            pts_both_podium = cfg["both_cars_on_podium"] if two_cars and (finish <= 3).all() else 0

            rows.append({
                "year": year,
                "round": rnd,
                "race_name": team_df.iloc[0]["race_name"],
                "constructor_id": cid,
                "pts_finish": pts_finish,
                "pts_fastest_lap": pts_fastest,
                "pts_both_classified": pts_both_classified,
                "pts_both_in_points": pts_both_points,
                "pts_both_podium": pts_both_podium,
                "dk_points_total": pts_finish + pts_fastest + pts_both_classified
                                   + pts_both_points + pts_both_podium,
            })

    return pd.DataFrame(rows)


def main():
    results = pd.read_csv(PROCESSED_DIR / "results.csv")
    print(f"Loaded {len(results)} result rows ({results.year.nunique()} seasons)")

    driver_pts = compute_driver_points(results)
    constructor_pts = compute_constructor_points(results)

    driver_pts.to_csv(PROCESSED_DIR / "dk_driver_points.csv", index=False)
    constructor_pts.to_csv(PROCESSED_DIR / "dk_constructor_points.csv", index=False)

    print(f"\nDriver DK points: {len(driver_pts)} rows -> dk_driver_points.csv")
    print(f"Constructor DK points: {len(constructor_pts)} rows -> dk_constructor_points.csv")

    print("\n=== Top 10 Drivers by avg DK points/race (2025+) ===")
    recent = driver_pts[driver_pts["year"] >= 2025]
    top = (
        recent.groupby(["driver_code", "constructor_id"])["dk_points_total"]
        .agg(avg_pts="mean", std_pts="std", races="count")
        .sort_values("avg_pts", ascending=False)
        .head(10)
    )
    print(top.round(1).to_string())

    print("\n=== Top Constructors by avg DK points/race (2025+) ===")
    recent_c = constructor_pts[constructor_pts["year"] >= 2025]
    top_c = (
        recent_c.groupby("constructor_id")["dk_points_total"]
        .agg(avg_pts="mean", std_pts="std", races="count")
        .sort_values("avg_pts", ascending=False)
        .head(10)
    )
    print(top_c.round(1).to_string())


if __name__ == "__main__":
    main()
