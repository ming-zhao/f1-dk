"""Picking a race and fetching everything a replay needs.

Two halves:
  * choosing a session and a lap-accurate time window
  * fetching the per-frame feeds (positions, order, gaps, tyres, pits, retirements)

/position and /intervals are **change-only** feeds — a row appears when something
changes, not on a fixed clock — so values are carried forward from before the window.
Note the race does NOT start at the session's `date_start`: Melbourne 2025 opens the
session at 04:00 UTC but the first lap begins at 04:18.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd

from data._http import DATA, get_json

OPENF1 = "https://api.openf1.org/v1"
SLEEP = 0.4
GRID_LEAD_IN = 45   # seconds before lights-out, to show the grid forming


def available_races() -> pd.DataFrame:
    rows = []
    root = DATA / "raw" / "openf1"
    if root.exists():
        for year_dir in sorted(root.iterdir()):
            f = year_dir / "sessions.csv"
            if year_dir.is_dir() and f.exists():
                rows.append(pd.read_csv(f))
    if not rows:
        return pd.DataFrame()
    df = pd.concat(rows, ignore_index=True)
    return df[df.get("session_name", "Race") == "Race"]

def pick_session(year: Optional[int], rnd: Optional[int]) -> dict:
    df = available_races()
    if df.empty:
        raise SystemExit("No crawled OpenF1 sessions. Run:\n"
                         "  python3 src/data/data_crawler.py 2025 --source openf1")
    if year:
        df = df[df.year == year]
        if df.empty:
            raise SystemExit(f"No crawled races for {year}.")
    if rnd:
        if "round" not in df.columns:
            raise SystemExit("sessions.csv has no `round` column — re-crawl that season.")
        df = df[df["round"] == rnd]
        if df.empty:
            raise SystemExit(f"Round {rnd} not crawled for {year}.")
    return df.sort_values("date_start").iloc[-1].to_dict()

def _timed_laps(session: dict) -> pd.DataFrame:
    """Rows of laps.csv for this session that have a `date_start`.

    Raises SystemExit with a runnable crawl command if the season file is missing or
    the round simply hasn't been crawled.
    """
    year = int(session["year"])
    sk = int(session["session_key"])
    laps_file = DATA / "raw" / "openf1" / str(year) / "laps.csv"
    if not laps_file.exists():
        raise SystemExit(f"{laps_file} missing — crawl this season first.")

    laps = pd.read_csv(laps_file)
    laps = laps[(laps.session_key == sk) & laps.date_start.notna()]
    if laps.empty:
        # sessions.csv covers the whole season, but lap data is only present for
        # rounds actually crawled — so an indexed race can still have no laps.
        raise SystemExit(
            f"No lap data for session {sk} ({session.get('location')}). "
            f"The season index lists it, but this round hasn't been crawled. Run:\n"
            f"  python3 src/data/data_crawler.py {year} "
            f"{int(session.get('round') or 0)} --source openf1")
    return laps


def reference_car(laps: pd.DataFrame) -> tuple[int, pd.DataFrame]:
    """(driver_number, that car's laps) for the car with the most complete laps.

    Its lap boundaries anchor the replay window, so the position trace closes into a
    loop rather than starting mid-circuit.
    """
    ref = laps.driver_number.value_counts().idxmax()
    return int(ref), laps[laps.driver_number == ref].sort_values("lap_number")


def _span(sel: pd.DataFrame, lead_in: float = 0.0) -> tuple[datetime, datetime]:
    """(t0, t1) covering the selected laps. Missing durations assume a 95 s lap."""
    t0 = datetime.fromisoformat(sel.date_start.iloc[0]) - timedelta(seconds=lead_in)
    total = float(sel.lap_duration.fillna(95).sum()) + lead_in
    return t0, t0 + timedelta(seconds=total)


def full_race_window(session: dict) -> tuple[datetime, datetime, int]:
    """The whole race, lap 1 included — a standing start is worth seeing."""
    ref, ref_laps = reference_car(_timed_laps(session))
    # Lap 1's `date_start` IS lights-out, so starting there means the cars are
    # already moving and the grid is never shown. Back up to catch the formation.
    t0, t1 = _span(ref_laps, lead_in=GRID_LEAD_IN)
    return t0, t1, ref


def lap_window(session: dict, from_lap: Optional[int], n_laps: int,
               full: bool = False) -> tuple[datetime, datetime, int]:
    """Time window covering `n_laps` whole laps, from the crawled laps.csv.

    Anchored to real lap boundaries so the position trace closes into a loop.
    """
    if full:
        return full_race_window(session)

    ref, ref_laps = reference_car(_timed_laps(session))
    # Skip lap 1 by default: a standing start means the grid is stationary and the
    # trace starts mid-circuit. Mid-race laps are clean flying laps.
    start_lap = from_lap if from_lap else max(2, int(ref_laps.lap_number.min()) + 1)
    sel = ref_laps[ref_laps.lap_number.between(start_lap, start_lap + n_laps - 1)]
    if sel.empty:
        raise SystemExit(f"Laps {start_lap}-{start_lap + n_laps - 1} not available "
                         f"(car #{ref} has {int(ref_laps.lap_number.max())} laps).")
    t0, t1 = _span(sel)
    return t0, t1, ref


def lap_marks(session: dict, t0: datetime,
              leader: Optional[int] = None) -> tuple[list, int]:
    """([(lap_number, seconds_from_t0)], total_laps).

    Lap count follows the **race leader** — that's what "lap X of Y" means on a
    broadcast. Backmarkers can be a lap or more down, so keying off an arbitrary
    reference car would understate the race's progress.
    """
    year = int(session["year"])
    sk = int(session["session_key"])
    f = DATA / "raw" / "openf1" / str(year) / "laps.csv"
    if not f.exists():
        return [], 0
    laps = pd.read_csv(f)
    laps = laps[(laps.session_key == sk) & laps.date_start.notna()]
    if laps.empty:
        return [], 0
    # Leader = whoever finished P1, else the car that completed the most laps.
    ref = leader
    if ref is None or ref not in set(laps.driver_number):
        res_f = DATA / "raw" / "openf1" / str(year) / "session_result.csv"
        if res_f.exists():
            res = pd.read_csv(res_f)
            res = res[(res.session_key == sk) & (res.position == 1)]
            if not res.empty:
                ref = int(res.driver_number.iloc[0])
    if ref is None or ref not in set(laps.driver_number):
        ref = laps.groupby("driver_number").lap_number.max().idxmax()

    rl = laps[laps.driver_number == ref].sort_values("lap_number")

    # laps.csv carries a PHANTOM trailing lap: the row created when the leader
    # crosses the line for the last time, with lap_duration NaN because that lap is
    # never completed. Melbourne 2025 therefore reports 58 laps for a 57-lap race
    # (#4 is the only car with a lap-58 row, and it has no duration), and the last 20
    # frames read "lap 58 / 58". session_result.number_of_laps is authoritative, so
    # trim to it; fall back to dropping a duration-less final lap.
    official = None
    res_f = DATA / "raw" / "openf1" / str(year) / "session_result.csv"
    if res_f.exists():
        res = pd.read_csv(res_f)
        res = res[(res.session_key == sk) & (res.driver_number == ref)]
        if not res.empty and pd.notna(res.number_of_laps.iloc[0]):
            official = int(res.number_of_laps.iloc[0])
    if official is None and len(rl) > 1 and pd.isna(rl.lap_duration.iloc[-1]):
        official = int(rl.lap_number.iloc[-1]) - 1
    if official is not None:
        rl = rl[rl.lap_number <= official]
    if rl.empty:
        return [], 0

    marks = []
    for r in rl.itertuples(index=False):
        secs = (datetime.fromisoformat(r.date_start) - t0).total_seconds()
        marks.append((int(r.lap_number), secs))
    return marks, int(rl.lap_number.max())

def busiest_lap(session: dict) -> int:
    """Lap with the most position changes — where the racing actually happens.

    /position is a change-only feed, so a settled phase yields a frozen tower. This
    finds a window worth watching.
    """
    sk = int(session["session_key"])
    year = int(session["year"])
    cache = DATA / "raw" / "openf1" / str(year) / "api"
    pos = get_json(f"{OPENF1}/position?session_key={sk}",
                   cache / f"{sk}_position.json", SLEEP) or []
    laps_file = DATA / "raw" / "openf1" / str(year) / "laps.csv"
    if not pos or not laps_file.exists():
        return 2

    pdf = pd.DataFrame(pos)
    pdf["date"] = pd.to_datetime(pdf["date"], format="ISO8601")
    laps = pd.read_csv(laps_file)
    laps = laps[(laps.session_key == sk) & laps.date_start.notna()]
    if laps.empty:
        return 2                      # not crawled yet; lap_window() reports it properly
    _, rl = reference_car(laps)
    rl = rl.dropna(subset=["lap_duration"]).copy()
    rl["date_start"] = pd.to_datetime(rl.date_start, format="ISO8601")

    best, best_n = 2, -1
    for r in rl.itertuples(index=False):
        t0 = r.date_start
        t1 = t0 + timedelta(seconds=float(r.lap_duration))
        n = len(pdf[(pdf.date >= t0) & (pdf.date < t1)])
        # Skip lap 1: a standing start scrambles everything and isn't representative.
        if int(r.lap_number) > 1 and n > best_n:
            best, best_n = int(r.lap_number), n
    print(f"  busiest lap: {best} ({best_n} position changes)")
    return best


def fetch_positions(session: dict, t0: datetime, t1: datetime) -> pd.DataFrame:
    sk = int(session["session_key"])
    cache = DATA / "raw" / "openf1" / str(int(session["year"])) / "api"
    drivers = get_json(f"{OPENF1}/drivers?session_key={sk}",
                       cache / f"{sk}_drivers.json", SLEEP) or []
    if not drivers:
        raise SystemExit(f"No driver list for session {sk}.")

    tag = t0.strftime("%H%M%S")

    # One /location request per driver, ~0.6 s each: 20 cars is ~12 s serial (plus
    # the politeness sleep). It's pure I/O wait, so threads are enough — the GIL is
    # released during the request, and multiprocessing would only add overhead.
    def fetch_one(d):
        dn = d["driver_number"]
        url = (f"{OPENF1}/location?session_key={sk}&driver_number={dn}"
               f"&date>{t0.isoformat()}&date<{t1.isoformat()}")
        return d, get_json(url, cache / f"{sk}_{dn}_loc_{tag}.json", SLEEP)

    # Modest pool: OpenF1 429s under load, and get_json() backs off per request.
    with ThreadPoolExecutor(max_workers=5) as pool:
        fetched = list(pool.map(fetch_one, drivers))

    frames = []
    for d, rows in fetched:
        dn = d["driver_number"]
        if not rows:
            continue
        df = pd.DataFrame(rows)
        df = df[df.x.notna() & df.y.notna()]
        # (0,0) is OpenF1's "no fix" sentinel, not the start line.
        df = df[~((df.x == 0) & (df.y == 0))]
        if df.empty:
            continue
        df["driver"] = d.get("name_acronym") or str(dn)
        df["num"] = dn
        df["colour"] = "#" + (d.get("team_colour") or "888888")
        frames.append(df[["date", "x", "y", "driver", "num", "colour"]])
        print(f"    #{dn:<3} {d.get('name_acronym','?'):<4} {len(df):>5} points")

    if not frames:
        raise SystemExit("No position data returned.")
    return pd.concat(frames, ignore_index=True)

def fetch_order(session: dict, t0: datetime, t1: datetime) -> list:
    """Running order over time from /position, as [{t, order:[driver,…]}]."""
    sk = int(session["session_key"])
    cache = DATA / "raw" / "openf1" / str(int(session["year"])) / "api"
    rows = get_json(f"{OPENF1}/position?session_key={sk}",
                    cache / f"{sk}_position.json", SLEEP) or []
    if not rows:
        return []

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"], format="ISO8601")
    # Carry forward the last known position for each driver into the window.
    df = df[df.date <= t1].sort_values("date")
    if df.empty:
        return []

    latest = {}
    snapshots = []
    for r in df.itertuples(index=False):
        latest[r.driver_number] = r.position
        if r.date >= t0:
            secs = (r.date - t0).total_seconds()
            snapshots.append((secs, dict(latest)))
    if not snapshots:
        snapshots = [(0.0, dict(latest))]
    return snapshots

def fetch_intervals(session: dict, t0: datetime, t1: datetime) -> list:
    """Gap-to-leader + interval over time, as [(secs, {driver_number: (gap, int)})].

    Change-only feed, so values are carried forward from before the window.
    """
    sk = int(session["session_key"])
    cache = DATA / "raw" / "openf1" / str(int(session["year"])) / "api"
    rows = get_json(f"{OPENF1}/intervals?session_key={sk}",
                    cache / f"{sk}_intervals.json", SLEEP) or []
    if not rows:
        return []
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"], format="ISO8601")
    df = df[df.date <= t1].sort_values("date")
    latest, snaps = {}, []
    for r in df.itertuples(index=False):
        latest[r.driver_number] = (r.gap_to_leader, r.interval)
        if r.date >= t0:
            snaps.append(((r.date - t0).total_seconds(), dict(latest)))
    return snaps or [(0.0, dict(latest))]

def tyre_stints(session: dict) -> dict:
    """{driver_number: [(lap_start, compound, tyre_age_at_start), …]} — every stint.

    The whole stint list, so callers can resolve a car's tyre at ANY lap. Returning a
    single snapshot for the window's first lap (what this used to do) froze the tyre
    for a whole race: Monaco 2024 has 6 of 16 drivers pitting at least once — #18
    ran MEDIUM→HARD→SOFT — and Melbourne 2025 averages 5.9 stints per car, yet every
    frame showed one compound and one age per driver.
    """
    year = int(session["year"])
    sk = int(session["session_key"])
    f = DATA / "raw" / "openf1" / str(year) / "stints.csv"
    if not f.exists():
        return {}
    st = pd.read_csv(f)
    st = st[(st.session_key == sk) & st.lap_start.notna()]
    out: dict[int, list] = {}
    for dn, grp in st.groupby("driver_number"):
        grp = grp.sort_values(["lap_start", "stint_number"])
        stints = []
        for r in grp.itertuples(index=False):
            ls = int(r.lap_start)
            age = int(r.tyre_age_at_start) if pd.notna(r.tyre_age_at_start) else 0
            comp = str(r.compound) if pd.notna(r.compound) else ""
            # OpenF1 emits a degenerate lap_start==lap_end==1 placeholder for the
            # tyre a car started the weekend on; the real opening stint is the next
            # row, also at lap_start 1. Keeping the later one at each lap is right.
            if stints and stints[-1][0] == ls:
                stints[-1] = (ls, comp, age)
            else:
                stints.append((ls, comp, age))
        if stints:
            out[int(dn)] = stints
    return out


def tyre_at(stints: list, lap: int) -> tuple:
    """(compound, age) for a driver on `lap`, from tyre_stints()'s stint list."""
    cur = None
    for ls, comp, age0 in stints:
        if ls <= max(lap, 1):
            cur = (ls, comp, age0)
        else:
            break
    if cur is None:
        return ("", None)
    ls, comp, age0 = cur
    return (comp, age0 + max(0, max(lap, 1) - ls))


def tyre_state(session: dict, t0: datetime, laps_span: range) -> dict:
    """{driver_number: (compound, age_at_window)} — tyre at the window's first lap.

    Kept for callers that only need one snapshot. Per-frame replays should use
    tyre_stints() + tyre_at() instead, so a pit stop actually changes the tyre shown.
    """
    lap0 = laps_span.start
    return {dn: tyre_at(st, lap0) for dn, st in tyre_stints(session).items()}

def pit_windows(session: dict, t0: datetime) -> dict:
    """{driver_number: [(start_s, end_s), …]} — actual stop intervals, in seconds
    relative to the replay start.

    Flagging the whole lap is wrong: a lap is ~92 s but a stop lasts ~19 s, so the
    PIT badge would show while the car is visibly out on track. `date` in pit.csv is
    the *end* of the stop, so the window is [date - pit_duration, date].
    """
    year = int(session["year"])
    sk = int(session["session_key"])
    f = DATA / "raw" / "openf1" / str(year) / "pit.csv"
    if not f.exists():
        return {}
    pit = pd.read_csv(f)
    pit = pit[(pit.session_key == sk) & pit.date.notna()]
    # OpenF1 records a bogus lap-1 "stop" for most cars, timed from session start
    # rather than an actual pit visit: Monaco 2024 shows 16 such rows with
    # pit_duration ~2380 s, against 24-28 s for real stops. Left in, every car shows
    # a PIT badge on the grid. A real F1 stop is well under two minutes.
    pit = pit[pit.pit_duration.notna() & (pit.pit_duration < 120)]
    if pit.empty:
        return {}
    pit["date"] = pd.to_datetime(pit["date"], format="ISO8601")

    out: dict[int, list] = {}
    for r in pit.itertuples(index=False):
        dur = float(r.pit_duration) if pd.notna(r.pit_duration) else 20.0
        end = (r.date - t0).total_seconds()
        out.setdefault(int(r.driver_number), []).append((end - dur, end))
    return out

def retirements(session: dict) -> dict:
    """{driver_number: last_lap} for EVERY car that failed to finish.

    Not filtered by window. A car retiring on lap 46 of 57 is retired for the last
    fifth of a full-race replay, and the old window filter (`last_lap < lap0`) marked
    nobody at all on a --full replay starting at lap 1 — Monaco 2024 has 4 DNFs and
    Melbourne 2025 has 6, and none were flagged. /location keeps emitting a retired
    car's final coordinates, so an unflagged DNF is a car parked on track: all four
    Monaco DNFs sat at a fixed point for all 1327 frames with zero total movement.
    """
    year = int(session["year"])
    sk = int(session["session_key"])
    res_f = DATA / "raw" / "openf1" / str(year) / "session_result.csv"
    laps_f = DATA / "raw" / "openf1" / str(year) / "laps.csv"
    if not res_f.exists() or not laps_f.exists():
        return {}
    res = pd.read_csv(res_f)
    res = res[(res.session_key == sk) & (res.get("dnf", False) | res.get("dns", False))]
    if res.empty:
        return {}
    laps = pd.read_csv(laps_f)
    laps = laps[laps.session_key == sk]
    last = laps.groupby("driver_number").lap_number.max().to_dict()
    return {int(dn): int(last.get(dn, 0)) for dn in res.driver_number}


def retired(session: dict, lap0: int) -> dict:
    """{driver_number: last_lap} for cars already out before `lap0`.

    Subset of retirements() — the cars that never appear in this window at all, so
    they can be dropped from the map entirely rather than flagged mid-replay.
    """
    return {dn: last for dn, last in retirements(session).items() if last < lap0}
