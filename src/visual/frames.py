"""Resampling every feed onto one animation timeline.

`build()` is a coordinator over four independent builders, in dependency order:

    _timeline()     bin /location onto a uniform frame grid
    lap_numbers()   leader's lap per frame  (tower rows and car frames both key off it)
    car_frames()    {driver: [x, y, heading]} per frame
    tower_rows()    the timing panel, one row list per frame

The outline is resolved before `car_frames()` on purpose: a stationary car has no
movement-derived heading, so it falls back to the direction of the nearest stretch of
track.

The outline itself comes from `circuit.py` (the official MultiViewer map) and is
**required**. Deriving it from one driver's /location lap used to be the fallback; it
silently truncated Monaco to 80% of the lap and was removed once the official map was
confirmed to cover every circuit OpenF1 exposes (48/48 crawled year+circuit_key pairs
as of 2026-08; see doc/refactor-plan.md, Task F).
"""

import math

import pandas as pd

from visual.race import tyre_at

FRAME_STEP = 0.25   # seconds per frame after resampling
KEEP_EVERY = 2      # thin frames to keep the payload small


# A full 57-lap race at 0.5 s/frame is ~12k frames (~22 MB of payload), so long
# windows get a coarser step. Positions are ~3.8 Hz, so 2 s/frame still tracks cars
# smoothly at circuit zoom — it's the tower ordering that loses granularity.
def step_for(duration_s: float) -> int:
    """KEEP_EVERY multiplier: 1 for short windows, up to 8 for a whole race."""
    if duration_s <= 400:      # a few laps
        return 1
    if duration_s <= 1200:     # ~10 min
        return 2
    if duration_s <= 3000:     # ~50 min
        return 4
    return 8                   # full race


def build(pos: pd.DataFrame, order_snaps: list, interval_snaps: list,
          ref_num: int, tyres: dict, pits: dict, lap0: int, out_cars: dict,
          thin: int = 1, lap_marks: list | None = None,
          official_outline: list | None = None, stints: dict | None = None
          ) -> tuple[list, list, list, dict, dict, list]:
    """Resample onto a shared timeline.

    Returns (frames, outline, tower_rows, colours, nums, lap_numbers). `pits` is
    {driver_number: [(start_s, end_s), …]} from race.pit_windows(). `stints` is
    race.tyre_stints() — per-driver stint lists, so the tyre shown changes at a stop.

    `official_outline` is required — see the module docstring.
    """
    if not official_outline:
        raise SystemExit(
            "No official circuit map for this session. The replay needs one: it is "
            "the only trustworthy outline (see visual/circuit.py). Check the "
            "circuit_key in sessions.csv and that data/raw/circuits/ has, or can "
            "fetch, <circuit_key>_<year>.json from api.multiviewer.app.")
    outline = official_outline

    grid, times, colours, nums = _timeline(pos, thin)
    num_to_code = {v: k for k, v in nums.items()}

    laps_per_frame = lap_numbers(times, lap_marks, lap0)
    frames = car_frames(grid, times, laps_per_frame, out_cars, num_to_code, lap0,
                        outline)
    rows_per_frame = tower_rows(times, laps_per_frame, order_snaps, interval_snaps,
                                num_to_code, tyres, stints, pits, out_cars)
    return frames, outline, rows_per_frame, colours, nums, laps_per_frame


def _timeline(pos: pd.DataFrame, thin: int) -> tuple[pd.DataFrame, list, dict, dict]:
    """Bin /location onto a uniform frame grid.

    Returns (grid, times, colours, nums) where `grid` has one row per (slot, driver)
    with the mean x/y in that slot, and `times` is every slot in range.
    """
    pos["date"] = pd.to_datetime(pos["date"], format="ISO8601")
    pos = pos.sort_values("date")
    t_start = pos.date.min()

    step = KEEP_EVERY * thin
    # Bin onto a UNIFORM grid of `step` slots, instead of taking every Nth *populated*
    # slot. /location is bursty — only 84.6% of Monaco's 0.25 s slots have any car in
    # them — so slicing the populated list produced frames whose real spacing averaged
    # 4.73 s (min 4.0, max 6.25) while the page renders and clocks them at exactly
    # dt=4.0 s. The replay therefore ran 15% fast and drifted monotonically: lap 78
    # was reached at frame time 5172 s against a true 6113 s, a 941 s error.
    pos["t"] = (((pos.date - t_start).dt.total_seconds() / FRAME_STEP)
                .round().astype(int) // step) * step
    grid = (pos.groupby(["t", "driver"])
               .agg(x=("x", "mean"), y=("y", "mean")).reset_index())

    # Every slot in range, so frame index i really is i * step * FRAME_STEP seconds.
    times = list(range(0, int(grid.t.max()) + step, step)) if len(grid) else []

    colours = pos.drop_duplicates("driver").set_index("driver")["colour"].to_dict()
    nums = pos.drop_duplicates("driver").set_index("driver")["num"].to_dict()
    return grid, times, colours, nums


def lap_numbers(times: list, lap_marks: list | None, lap0: int) -> list:
    """Leader's lap number per frame, from the lap start times in `lap_marks`.

    Computed BEFORE the frame and tower loops: per-frame tyre and retirement state
    both key off it.
    """
    laps_per_frame = []
    for tt in times:
        secs = tt * FRAME_STEP
        # 0 = pre-race: the grid is forming and lap 1 hasn't started.
        lap = 0 if (lap_marks and secs < lap_marks[0][1]) else lap0
        for ln, at in (lap_marks or []):
            if at <= secs:
                lap = ln
            else:
                break
        laps_per_frame.append(lap)
    return laps_per_frame


def car_frames(grid: pd.DataFrame, times: list, laps_per_frame: list, out_cars: dict,
               num_to_code: dict, lap0: int, outline: list) -> list:
    """[{driver_code: [x, y, heading]}, …] — one dict per frame.

    Retired cars are dropped (see below); `outline` is needed for the stationary-car
    heading fallback, which is why it has to exist before this runs.
    """
    # Cars out for the WHOLE window are dropped from the map; a car that retires
    # mid-window stays until the lap it actually stopped on and then disappears.
    gone_all = {num_to_code[n]: last for n, last in out_cars.items()
                if n in num_to_code and last < lap0}
    out_from = {num_to_code[n]: last for n, last in out_cars.items()
                if n in num_to_code and last >= lap0}
    lap_of = dict(zip(times, laps_per_frame))
    by_t = {t: {} for t in times}
    for r in grid.itertuples(index=False):
        if r.driver in gone_all:
            continue          # retired before this window — don't park it on track
        stop = out_from.get(r.driver)
        # Past its final lap: /location still emits the car's last coordinates, which
        # would park it motionless on the racing line for the rest of the replay.
        if stop is not None and lap_of.get(r.t, 0) > stop:
            continue
        by_t[r.t][r.driver] = [round(r.x), round(r.y)]
    frames = [by_t[t] for t in times]
    _add_headings(frames, outline)
    return frames


def _add_headings(frames: list, outline: list) -> None:
    """Append a heading (radians) to every [x, y] in place, from the step just taken.

    A car glyph needs an orientation and a dot doesn't carry one.
    """
    for fi, f in enumerate(frames):
        prev = frames[fi - 1] if fi else None
        nxt = frames[fi + 1] if fi + 1 < len(frames) else None
        for code, xy in f.items():
            if len(xy) > 2:
                continue
            if prev and code in prev:
                ref = prev[code]
                dx, dy = xy[0] - ref[0], xy[1] - ref[1]
            elif nxt and code in nxt:
                ref = nxt[code]
                dx, dy = ref[0] - xy[0], ref[1] - xy[1]
            else:
                dx = dy = 0
            # A stationary car (on the grid, or stopped in its box) gives dx=dy=0, so
            # atan2 returns 0 and every car would point right. Fall back to the
            # direction of the nearest stretch of track, which is where it's facing.
            xy.append(round(math.atan2(dy, dx), 3) if (dx or dy)
                      else _track_heading(xy, outline))


def tower_rows(times: list, laps_per_frame: list, order_snaps: list,
               interval_snaps: list, num_to_code: dict, tyres: dict,
               stints: dict | None, pits: dict, out_cars: dict) -> list:
    """Per-frame tower rows: position, code, leader time / interval, tyre, pit flag."""
    start_order = _start_order(order_snaps, num_to_code)

    rows_per_frame = []
    oi = ii = 0
    for t, lap in zip(times, laps_per_frame):
        secs = t * FRAME_STEP
        while oi + 1 < len(order_snaps) and order_snaps[oi + 1][0] <= secs:
            oi += 1
        while ii + 1 < len(interval_snaps) and interval_snaps[ii + 1][0] <= secs:
            ii += 1
        order = order_snaps[oi][1] if order_snaps else {}
        gaps = interval_snaps[ii][1] if interval_snaps else {}

        # /position can briefly report two cars in the same slot (29 of 46 Monaco
        # snapshots, 179 of 313 at Melbourne). Break ties on driver number so the
        # tower order is at least stable frame to frame instead of dict-order luck.
        ranked = sorted(((p, n) for n, p in order.items() if num_to_code.get(n)))
        out = []
        for _, dn in ranked:
            code = num_to_code[dn]
            gap, itv = gaps.get(dn, (None, None))
            # Tyre at THIS lap, so a stop changes the compound and the age climbs.
            if stints and dn in stints:
                comp, age = tyre_at(stints[dn], lap)
            else:
                comp, age = tyres.get(dn, ("", None))
            stop = out_cars.get(dn)
            is_out = stop is not None and lap > stop
            out.append({
                "d": code,
                "n": int(dn),
                # A retired car's last /intervals row is carried forward forever, so
                # it would keep showing a live gap (Monaco: #11 froze at "7.3" for all
                # 1327 frames while parked). Blank it once the car is out. The leader
                # has no gap to itself either — the feed reports 0.0, which the page
                # already special-cases, but the payload shouldn't claim a number.
                "g": None if (is_out or len(out) == 0) else _fmt_gap(gap),
                "i": None if (is_out or len(out) == 0) else _fmt_gap(itv),
                "c": (comp or "")[:1],      # S / M / H / I / W
                "a": age,
                # In the pit box right now, per the real stop window.
                "p": 0 if is_out else (
                    1 if any(a <= secs <= b for a, b in pits.get(dn, ())) else 0),
                "out": stop if is_out else None,   # last lap completed, if retired
                # Places gained (+) or lost (-) since the start. None = unchanged.
                "delta": (start_order.index(code) - len(out)
                          if code in start_order else None),
            })
        rows_per_frame.append(out)
    return rows_per_frame


def _start_order(order_snaps: list, num_to_code: dict) -> list:
    """Driver codes in grid order, for a persistent "places gained/lost" delta.

    A transient arrow shown only on the frame a pass happens is invisible: at
    4 s/frame just 1% of frames contain a change. Broadcasts show the running total
    against the grid instead, which is always meaningful.

    Sorted on the FULL (position, number) tuple — exactly the tie-break tower_rows()
    uses. This must match, or the delta is measured against a differently-ordered
    baseline. /position briefly reports two cars in one slot, and Monaco 2024's first
    snapshot is one such case: #31 OCO and #77 BOT both sat at P15, so sorting on
    position alone left the tie to dict insertion order. The two orderings disagreed,
    and OCO read +1 / BOT read -1 in all 1568 frames — including frame 0, where every
    delta is 0 by definition. Agreeing by construction, not by luck.
    """
    if not order_snaps:
        return []
    first = order_snaps[0][1]
    return [num_to_code[n] for _, n in
            sorted((p, n) for n, p in first.items() if num_to_code.get(n))]


def _track_heading(xy: list, outline: list) -> float:
    """Direction of travel of the nearest stretch of track, in radians.

    For cars that aren't moving — on the grid, or stopped in the pit box — where a
    movement-derived heading is undefined.
    """
    if not outline or len(outline) < 4:
        return 0.0
    bi, bd = 0, float("inf")
    for i, o in enumerate(outline):
        d = (o[0] - xy[0]) ** 2 + (o[1] - xy[1]) ** 2
        if d < bd:
            bd, bi = d, i
    cur = outline[bi]
    nxt = outline[(bi + 3) % len(outline)]
    return round(math.atan2(nxt[1] - cur[1], nxt[0] - cur[0]), 3)


def _fmt_gap(v):
    """Gaps arrive as floats, or strings like '1 LAP' when a car is lapped.

    Returns None for missing/NaN so the tower renders an empty cell rather than the
    literal text "nan".
    """
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        s = str(v).strip()
        return s or None
    if f != f:          # NaN
        return None
    return f"{f:.1f}"
