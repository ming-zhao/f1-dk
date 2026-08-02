"""Circuit geometry: pit lane, self-clearance, rotation and how big to draw it all.

The road is drawn at the width computed here, unscaled, so these numbers ARE the
pixels on screen — the renderer used to shrink them to 0.62x, which made a road
narrower than two cars abreast and left no room for a starting grid.

The circuit outline itself comes from `circuit.py` (the official MultiViewer map) —
deriving it from a car's /location lap was tried and abandoned, because it silently
truncated Monaco to 80% of the lap. The **pit lane** is still derived from position
data, and legitimately so: no source publishes pit-lane geometry, and the route cars
take during a stop *is* the lane.

Sizing is derived per circuit — a tight track like Monaco needs more pixels rather
than a thinner road.
"""

import math

from datetime import datetime

import pandas as pd

# The border stroke the renderer draws under the road, in px. Must match the
# `TRACK_W + 4` outer stroke in replay.js drawTrack().
BORDER_PX = 4.0


def pit_lane(session: dict, pits: dict, pos: pd.DataFrame,
             t0: datetime, outline: list | None = None) -> tuple[list, list]:
    """Derive the pit lane path and box locations from position data.

    OpenF1 publishes no pit-lane geometry, but a car in the pits is still emitting
    /location — so the route cars take during a stop *is* the pit lane. Take each
    stop window, keep that driver's positions, and the resulting path is the lane.

    Returns (lane_path, boxes): a smoothed [x, y] polyline, and the near-stationary
    points where cars actually sit.
    """
    if not pits or pos.empty:
        return [], []

    pos = pos.copy()
    pos["secs"] = (pos["date"] - t0).dt.total_seconds()

    lane_pts, boxes = [], []
    for dn, windows in pits.items():
        rows = pos[pos["num"] == dn]
        if rows.empty:
            continue
        for a, b in windows:
            # EXACTLY the stop window: pit_duration is lane time, so [a, b] is the
            # lane traversal itself. Widening it (an earlier attempt used ±6 s) drags
            # in the car's position on the main straight, which made the derived
            # "pit lane" sit on top of the racing line.
            seg = rows[(rows.secs >= a) & (rows.secs <= b)].sort_values("secs")
            if len(seg) < 4:
                continue
            xy = list(seg[["x", "y"]].itertuples(index=False, name=None))
            lane_pts.extend(xy)
            # The stationary stretch is the box: consecutive samples barely moving.
            for i in range(1, len(xy)):
                if math.dist(xy[i - 1], xy[i]) < 40:
                    boxes.append(xy[i])

    if not lane_pts:
        return [], []
    # Keep the lane as recorded — the drawing code scales its real offset from the
    # circuit, so points close to the racing line are fine and filtering them out
    # (an earlier attempt cut at 7 m) deleted most of the lane.

    # Thin the cloud onto a grid so many stops don't produce a hairball.
    grid, keep = set(), []
    for x, y in lane_pts:
        k = (round(x / 120), round(y / 120))
        if k not in grid:
            grid.add(k)
            keep.append([round(x), round(y)])

    # Order along the LANE itself, not by nearest racing-line index. Indexing against
    # the circuit wraps at start/finish — Melbourne's lane straddles the line, so
    # points landed at both index ~0 and ~321, splitting the lane and drawing a 293 m
    # spike across the map. It also collides: at Monaco 39 lane points mapped to only
    # 20 distinct indices, tie-broken arbitrarily. Mean turn angle per vertex was
    # 41-86° that way, versus ~1° ordering along the lane.
    path = _smooth(_order_path(keep))

    bgrid, bkeep = set(), []
    for x, y in boxes:
        k = (round(x / 250), round(y / 250))
        if k not in bgrid:
            bgrid.add(k)
            bkeep.append([round(x), round(y)])

    return path, bkeep


def _smooth(pts: list, window: int = 3) -> list:
    """Moving average, so scattered per-driver samples read as one road.

    Clamps at the ends (edge replication) rather than shrinking the window — and
    definitely not zero-padding, which drags endpoint coordinates toward the origin.
    """
    if len(pts) < window * 2:
        return pts
    half = window // 2
    out = []
    for i in range(len(pts)):
        seg = [pts[min(max(k, 0), len(pts) - 1)] for k in range(i - half, i + half + 1)]
        out.append([round(sum(q[0] for q in seg) / len(seg)),
                    round(sum(q[1] for q in seg) / len(seg))])
    return out


def _order_path(pts: list) -> list:
    """Greedy nearest-neighbour ordering of an unordered point cloud.

    How the pit-lane samples — which arrive per driver, per stop, in no useful order —
    become one traversable polyline. See the note in pit_lane() for why ordering
    against the circuit outline instead does not work.
    """
    if len(pts) < 3:
        return pts
    remaining = pts[:]
    start = max(remaining, key=lambda p: (p[0] ** 2 + p[1] ** 2))
    remaining.remove(start)
    path = [start]
    while remaining:
        last = path[-1]
        nxt = min(remaining, key=lambda p: math.dist(last, p))
        # A big jump means the cloud is disjoint; stop rather than draw a stray line.
        if math.dist(last, nxt) > 900:
            break
        remaining.remove(nxt)
        path.append(nxt)
    return path


def min_self_gap(outline: list, rot: float) -> float:
    """Closest approach between two NON-ADJACENT parts of the circuit, in data units.

    This is the hard constraint on how wide the track can be drawn. Monaco's hairpin
    complex brings sections within ~15-25 m of each other; drawing a 26 px road at
    Monaco's zoom makes those sections merge into a blob.
    """
    ca, sa = math.cos(rot), math.sin(rot)
    pts = [(x * ca - y * sa, x * sa + y * ca) for x, y in outline]
    n = len(pts)
    if n < 40:
        return float("inf")
    # Skip ~10% of the lap either side. A smaller window (4%) let the lap seam count
    # as a "self-approach": the trimmed lap overlaps itself slightly at start/finish,
    # and points 92% and 96% round the lap read as 4 m apart, collapsing the drawn
    # track to the 7 px floor.
    skip = max(24, n // 10)
    best = float("inf")
    for i in range(n):
        for j in range(i + skip, min(n, i + n - skip + 1)):
            d = math.dist(pts[i], pts[j])
            if d < best:
                best = d
    return best


def track_width_px(outline: list, rot: float, w: int, h: int,
                   pad: int = 34, desired: float = 26.0) -> tuple[float, float]:
    """(track_width_px, car_scale) that fit without the circuit overlapping itself."""
    ca, sa = math.cos(rot), math.sin(rot)
    xs = [x * ca - y * sa for x, y in outline]
    ys = [x * sa + y * ca for x, y in outline]
    bw, bh = max(xs) - min(xs), max(ys) - min(ys)
    if bw <= 0 or bh <= 0:
        return desired, 1.0
    scale = min((w - 2 * pad) / bw, (h - 2 * pad) / bh)   # px per data unit

    gap_px = min_self_gap(outline, rot) * scale
    if gap_px == float("inf"):
        return desired, 1.0
    # Two roads at their closest approach each occupy HALF a width plus half the
    # border stroke, so the centre-to-centre gap must cover a full width + border,
    # not just a width. The browser draws a `TRACK_W + BORDER` outer stroke under the
    # road (see drawTrack), and omitting it here left Monaco with 0.46 px of daylight
    # between the drawn roads once the road stopped being scaled down at render time.
    allowed = max(7.0, gap_px * 0.85 - BORDER_PX)
    width = min(desired, allowed)
    return width, width / desired


def fit_canvas(outline: list, rot: float, budget_w: int, budget_h: int,
               pad: int = 34, extra: list | None = None) -> tuple[int, int]:
    """Canvas size matching the rotated circuit's aspect, inside a w×h budget."""
    # Include the pit lane: it sits outside the circuit (2000+ units beyond it at
    # Monaco), so fitting on the outline alone clipped it off-canvas.
    pts = list(outline) + list(extra or [])
    ca, sa = math.cos(rot), math.sin(rot)
    xs = [x * ca - y * sa for x, y in pts]
    ys = [x * sa + y * ca for x, y in pts]
    bw, bh = max(xs) - min(xs), max(ys) - min(ys)
    if bw <= 0 or bh <= 0:
        return budget_w, budget_h
    s = min((budget_w - 2 * pad) / bw, (budget_h - 2 * pad) / bh)
    return max(320, round(bw * s) + 2 * pad), max(320, round(bh * s) + 2 * pad)


def fit_for_track(outline: list, rot: float, budget_w: int, budget_h: int,
                  pad: int = 34, desired: float = 26.0,
                  max_w: int = 2600, max_h: int = 1500,
                  extra: list | None = None) -> tuple[int, int, float, float]:
    """(canvas_w, canvas_h, track_width_px, car_scale).

    Tight circuits need MORE pixels, not thinner roads. Monaco's closest
    self-approach is ~15-25 m: at 1150x620 that's ~12 px, so a 26 px road overlaps
    itself, and clamping the width instead shrinks the cars to 0.39x. Growing the
    canvas raises px/metre until the real gap can hold a full-width road — the page
    scales it down with CSS, which is far better than an illegible blob.
    """
    w, h = fit_canvas(outline, rot, budget_w, budget_h, pad, extra)
    width, car = track_width_px(outline, rot, w, h, pad, desired)

    while car < 0.8 and w < max_w and h < max_h:
        grow = min(1.25, max_w / w, max_h / h)
        if grow <= 1.001:
            break
        w, h = int(w * grow), int(h * grow)
        width, car = track_width_px(outline, rot, w, h, pad, desired)
    return w, h, width, car
