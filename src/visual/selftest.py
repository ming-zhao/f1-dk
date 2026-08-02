#!/usr/bin/env python3
"""Regression checks for built race-replay payloads.

Validates the JSON that `track_replay.py` writes to `dashboard/replays/`. Every
past bug in this pipeline was a *silent* one — a truncated outline, a pit lane
drawn on the racing line, frames clocked at the wrong dt, a tower frozen on one
tyre compound. None of it raised; it just looked subtly wrong on screen. So this
asserts the properties a correct replay has, and prints the measured value next
to every verdict so a human can see how much headroom is left.

Usage:
    python3 src/visual/selftest.py dashboard/replays/replay_2024_Monaco.json
    python3 src/visual/selftest.py            # every replay in dashboard/replays/

Exits 1 if any check fails. NOTEs are advisory and never fail the run.

Units: coordinates are decimetres, ~9.8-9.9 per metre in OpenF1/MultiViewer
space. `M` below is the metre-to-unit factor; everything physical is expressed
in metres or m/s so the numbers are readable.
"""

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
REPLAY_DIR = ROOT / "dashboard" / "replays"

M = 10.0            # data units per metre
MAX_CAR_MS = 90.0   # an F1 car's top speed, ~325 km/h


# Official circuit lengths (km), keyed by the OpenF1 `location` field. Used to
# catch a truncated or doubled-back outline — the failure mode that silently cut
# Monaco to 80% of a lap. Unknown circuits are skipped with a NOTE rather than
# failed, so a new race doesn't break the run before anyone has added its length.
CIRCUIT_KM = {
    "Melbourne": 5.278,          # Albert Park
    "Monaco": 3.337,             # Monte Carlo
    "Monte Carlo": 3.337,
    "Sakhir": 5.412,
    "Jeddah": 6.174,
    "Shanghai": 5.451,
    "Suzuka": 5.807,
    "Miami": 5.412,
    "Imola": 4.909,
    "Barcelona": 4.657,
    "Catalunya": 4.657,
    "Montreal": 4.361,
    "Spielberg": 4.318,
    "Silverstone": 5.891,
    "Budapest": 4.381,
    "Spa-Francorchamps": 7.004,
    "Zandvoort": 4.259,
    "Monza": 5.793,
    "Baku": 6.003,
    "Singapore": 4.940,
    "Austin": 5.513,
    "Mexico City": 4.304,
    "Sao Paulo": 4.309,
    "Interlagos": 4.309,
    "Las Vegas": 6.201,
    "Lusail": 5.419,
    "Yas Marina Circuit": 5.281,
    "Abu Dhabi": 5.281,
}

# The pit lane merges tangentially into the racing line at its entry and exit, so
# the points at each END of the derived lane genuinely sit on top of the track.
# Only the lane's interior has to stand off from it. The strict all-points minimum
# is reported regardless, so an exemption can never hide a lane drawn on the
# racing line along its whole length.
PIT_END_EXEMPT = 3


# ---------------------------------------------------------------------------
# geometry helpers
# ---------------------------------------------------------------------------

def seg_dist(p, a, b) -> float:
    """Distance from point `p` to the SEGMENT a-b, in data units.

    Distance to the nearest outline *vertex* is not a usable proxy: outline
    points are 15-53 units apart at these circuits, so a point sitting exactly
    on the racing line can still read as ~26 m from the closest vertex. Every
    "how far from the track" question here therefore uses segment distance.
    """
    ax, ay = a
    bx, by = b
    px, py = p
    dx, dy = bx - ax, by - ay
    span = dx * dx + dy * dy
    if span == 0:
        return math.dist(p, a)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / span))
    return math.dist(p, (ax + t * dx, ay + t * dy))


class SegmentIndex:
    """Grid-bucketed segments, for "is this point near the track?" at scale.

    Check 8 asks that question once per car per frame — ~25k times against ~630
    segments, which is 16M distance evaluations if done naively. Bucketing each
    segment into the grid cells its bounding box covers turns the common case
    into a 9-cell lookup. The bounding box is a superset of the cells the segment
    actually crosses, so candidates are never missed.
    """

    def __init__(self, pts, cell: float = 500.0):
        self.segs = [(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
        self.cell = cell
        self.grid: dict = {}
        for i, (a, b) in enumerate(self.segs):
            x0, x1 = sorted((a[0], b[0]))
            y0, y1 = sorted((a[1], b[1]))
            for cx in range(int(x0 // cell), int(x1 // cell) + 1):
                for cy in range(int(y0 // cell), int(y1 // cell) + 1):
                    self.grid.setdefault((cx, cy), []).append(i)

    def within(self, p, radius: float) -> bool:
        """True if `p` is within `radius` of any segment."""
        reach = int(radius // self.cell) + 1
        cx, cy = int(p[0] // self.cell), int(p[1] // self.cell)
        seen = set()
        for i in range(cx - reach, cx + reach + 1):
            for j in range(cy - reach, cy + reach + 1):
                for si in self.grid.get((i, j), ()):
                    if si in seen:
                        continue
                    seen.add(si)
                    a, b = self.segs[si]
                    if seg_dist(p, a, b) <= radius:
                        return True
        return False

    def nearest(self, p) -> float:
        """Exact distance to the closest segment — full scan, for reporting."""
        if not self.segs:
            return float("inf")
        return min(seg_dist(p, a, b) for a, b in self.segs)


def polyline_len(pts) -> float:
    return sum(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))


# ---------------------------------------------------------------------------
# result reporting
# ---------------------------------------------------------------------------

class Report:
    """Collects verdicts, prints them grouped by section."""

    def __init__(self, label: str):
        self.label = label
        self.passed = 0
        self.failed = 0
        self.noted = 0
        self.skipped = 0
        self.failures: list = []
        self._section = None

    def section(self, name: str) -> None:
        self._section = name
        print(f"\n  {name}")

    def check(self, ok: bool, num: int, name: str, detail: str) -> None:
        if ok:
            self.passed += 1
            print(f"    PASS  {num:>2}. {name:<34} {detail}")
        else:
            self.failed += 1
            self.failures.append(f"{num}. {name} — {detail}")
            print(f"    FAIL  {num:>2}. {name:<34} {detail}")

    def note(self, num: int, name: str, detail: str) -> None:
        self.noted += 1
        print(f"    NOTE  {num:>2}. {name:<34} {detail}")

    def skip(self, num: int, name: str, detail: str) -> None:
        self.skipped += 1
        print(f"    SKIP  {num:>2}. {name:<34} {detail}")


# ---------------------------------------------------------------------------
# checks
# ---------------------------------------------------------------------------

def check_geometry(d: dict, r: Report) -> None:
    r.section("Geometry")
    outline = d.get("outline") or []

    # 1. A replay draws the outline as a closed loop. An open one leaves a
    #    visible gap at start/finish, or a chord cutting across the map.
    if len(outline) >= 2:
        gap = math.dist(outline[0], outline[-1])
        r.check(gap < 100, 1, "outline closes",
                f"first-last gap {gap / M:.1f} m (limit 10.0 m)")
    else:
        r.check(False, 1, "outline closes", f"only {len(outline)} points")

    # 2. Total length against the official circuit length. This is the check
    #    that would have caught Monaco being silently truncated to 2.68 km.
    loc = d.get("location")
    official = CIRCUIT_KM.get(loc)
    measured_km = polyline_len(outline) / (M * 1000) if len(outline) >= 2 else 0.0
    if official is None:
        r.skip(2, "outline length vs official",
               f"{measured_km:.3f} km measured; no official length known for "
               f"{loc!r} — add it to CIRCUIT_KM")
    else:
        err = abs(measured_km - official) / official
        r.check(err <= 0.05, 2, "outline length vs official",
                f"{measured_km:.3f} km vs {official:.3f} km official "
                f"({err * 100:.1f}% off, limit 5.0%)")

    # 3. Consecutive duplicates make the circuit appear to touch itself, which
    #    collapses the drawn road to the minimum-width floor.
    dups = [i for i in range(len(outline) - 1)
            if math.dist(outline[i], outline[i + 1]) < 5]
    worst = (f"closest pair {min(math.dist(outline[i], outline[i + 1]) for i in dups):.1f} u"
             if dups else "min step "
             f"{min((math.dist(outline[i], outline[i + 1]) for i in range(len(outline) - 1)), default=0):.1f} u")
    r.check(not dups, 3, "no duplicate outline points",
            f"{len(dups)} pair(s) closer than 5 u; {worst}")

    # 4. Too few points and the circuit renders as a polygon of straight lines.
    r.check(len(outline) >= 100, 4, "outline point count",
            f"{len(outline)} points (min 100)")

    # 5. The pit lane is derived from car positions during stops, so the two
    #    ways it goes wrong are landing on top of the racing line, or being
    #    flung far off it by a stray fix / bad path ordering.
    lane = d.get("pitlane") or []
    if len(lane) < 2 or len(outline) < 2:
        r.skip(5, "pit lane offset from track",
               f"{len(lane)} lane point(s) — nothing to check")
    else:
        idx = SegmentIndex(outline)
        dists = [idx.nearest(p) for p in lane]
        lo_m, hi_m = min(dists) / M, max(dists) / M
        # Interior only: the ends are the entry/exit merge (see PIT_END_EXEMPT).
        interior = dists[PIT_END_EXEMPT:len(dists) - PIT_END_EXEMPT] or dists
        bad_near = [x for x in interior if x < 3 * M]
        bad_far = [x for x in interior if x > 60 * M]
        ends_m = [f"{x / M:.1f}" for x in
                  dists[:PIT_END_EXEMPT] + dists[len(dists) - PIT_END_EXEMPT:]]
        r.check(not bad_near and not bad_far, 5, "pit lane offset from track",
                f"{len(lane)} pts, interior {min(interior) / M:.1f}-"
                f"{max(interior) / M:.1f} m from nearest segment (band 3-60 m); "
                f"all-points range {lo_m:.1f}-{hi_m:.1f} m")
        if min(dists) < 3 * M:
            r.note(5, "pit lane merge at ends",
                   f"end points at {', '.join(ends_m)} m — entry/exit merging "
                   f"into the racing line, exempt from the 3 m floor")


def check_frames(d: dict, r: Report) -> None:
    r.section("Frames")
    frames = d.get("frames") or []
    outline = d.get("outline") or []
    lane = d.get("pitlane") or []
    dt = float(d.get("dt") or 0)

    # 6. An empty frame is a blank map for one tick — a hole in the timeline.
    empty = [i for i, f in enumerate(frames) if len(f) < 1]
    counts = [len(f) for f in frames]
    r.check(not empty, 6, "every frame has a car",
            f"{len(empty)} empty of {len(frames)}; cars/frame "
            f"{min(counts, default=0)}-{max(counts, default=0)}")

    # 7. A position jump beyond the physical maximum means a bad fix or a
    #    mis-sized frame step. Bound it from dt: 90 m/s plus 50% headroom, which
    #    absorbs the ~0.4% of raw /location samples that are genuinely bogus.
    if dt <= 0 or len(frames) < 2:
        r.skip(7, "per-frame position jump", f"dt={dt}, {len(frames)} frames")
    else:
        limit = dt * MAX_CAR_MS * M * 1.5
        worst_d, worst_at = 0.0, None
        over = samples = 0
        for i in range(1, len(frames)):
            prev, cur = frames[i - 1], frames[i]
            for code, xy in cur.items():
                if code not in prev:
                    continue
                dist = math.dist(xy[:2], prev[code][:2])
                samples += 1
                if dist > worst_d:
                    worst_d, worst_at = dist, (code, i)
                if dist > limit:
                    over += 1
        pct = (100.0 * over / samples) if samples else 0.0
        who = f"{worst_at[0]} at frame {worst_at[1]}" if worst_at else "n/a"
        detail = (f"worst {worst_d / M:.0f} m = {worst_d / M / dt:.1f} m/s "
                  f"({who}); limit {limit / M:.0f} m; {over}/{samples} over "
                  f"({pct:.2f}%)")
        if over == 0:
            r.check(True, 7, "per-frame position jump", detail)
        elif pct <= 1.0:
            # Tolerated band: raw /location really does contain impossible
            # samples at about this rate. More than 1% is a pipeline problem.
            r.note(7, "per-frame position jump",
                   detail + " — within the ~0.4% bogus-sample rate of raw "
                            "/location, not failed")
        else:
            r.check(False, 7, "per-frame position jump", detail)

    # 8. A car far from both the track and the pit lane is a car drawn in a
    #    field. Segment distance again: vertex distance alone would flag cars
    #    sitting perfectly on the racing line.
    if len(outline) < 2:
        r.skip(8, "cars near track or pit lane", "no outline")
    else:
        allow = 30 * M
        track = SegmentIndex(outline)
        pit = SegmentIndex(lane) if len(lane) >= 2 else None
        bad = total = 0
        worst_d, worst_at = 0.0, None
        for i, f in enumerate(frames):
            for code, xy in f.items():
                total += 1
                p = xy[:2]
                if track.within(p, allow) or (pit and pit.within(p, allow)):
                    continue
                # Rare: pay for the exact distance only to report the offender.
                dist = track.nearest(p)
                if pit:
                    dist = min(dist, pit.nearest(p))
                bad += 1
                if dist > worst_d:
                    worst_d, worst_at = dist, (code, i)
        who = f"{worst_at[0]} at frame {worst_at[1]}, {worst_d / M:.0f} m" \
            if worst_at else "all within 30 m"
        r.check(bad == 0, 8, "cars near track or pit lane",
                f"{bad}/{total} beyond 30 m; worst {who}")


def check_timing(d: dict, r: Report) -> None:
    r.section("Timing / tower")
    frames = d.get("frames") or []
    rows = d.get("rows") or []
    lap_nums = d.get("lapNums") or []
    colours = d.get("colours") or {}
    total_laps = int(d.get("totalLaps") or 0)
    from_lap = int(d.get("fromLap") or 0)
    dt = float(d.get("dt") or 0)

    # 9. The lap counter drives the clock, the tyre state and retirements, so a
    #    non-monotonic or overrunning value corrupts all three. The phantom
    #    trailing lap in laps.csv used to make this read "lap 58 / 57".
    if not lap_nums:
        r.check(False, 9, "lap numbers sane", "lapNums is empty")
    else:
        drops = [i for i in range(len(lap_nums) - 1)
                 if lap_nums[i + 1] < lap_nums[i]]
        good_start = lap_nums[0] in (0, from_lap)
        top = max(lap_nums)
        ok = not drops and good_start and top <= total_laps
        problems = []
        if drops:
            problems.append(f"{len(drops)} backward step(s) (first at frame "
                            f"{drops[0]}: {lap_nums[drops[0]]}→"
                            f"{lap_nums[drops[0] + 1]})")
        if not good_start:
            problems.append(f"starts at {lap_nums[0]}, expected 0 or {from_lap}")
        if top > total_laps:
            problems.append(f"max {top} > totalLaps {total_laps}")
        r.check(ok, 9, "lap numbers sane",
                f"{lap_nums[0]}→{top} of {total_laps}"
                + (f"; {'; '.join(problems)}" if problems else ", monotonic"))

    # 10. A code in the tower with no colour renders as an unstyled row; a
    #     colour with no row is a car that vanished from the timing feed.
    in_rows = {row["d"] for f in rows for row in f}
    in_col = set(colours)
    missing = in_rows - in_col
    unused = in_col - in_rows
    r.check(not missing and not unused, 10, "rows/colours driver sets agree",
            f"{len(in_rows)} in rows, {len(in_col)} in colours"
            + (f"; missing colour: {sorted(missing)}" if missing else "")
            + (f"; unused colour: {sorted(unused)}" if unused else ""))

    # 11. The page indexes all three by the same frame counter, so unequal
    #     lengths mean the tower and the map drift apart, or a crash at the end.
    r.check(len(rows) == len(frames) == len(lap_nums), 11, "series lengths match",
            f"frames {len(frames)}, rows {len(rows)}, lapNums {len(lap_nums)}")

    # 12. Tyre state used to be a single snapshot for the whole replay, so every
    #     car showed one compound and one age all race. Over a full race most
    #     cars must pit, and age must climb.
    if not d.get("full"):
        r.skip(12, "tyre state varies", "short window (full=false)")
    elif not rows:
        r.check(False, 12, "tyre state varies", "no rows")
    else:
        states: dict = {}
        for f in rows:
            for row in f:
                states.setdefault(row["d"], set()).add((row["c"], row["a"]))
        changed = [k for k, v in states.items() if len(v) > 1]
        r.check(len(changed) * 2 >= len(states), 12, "tyre state varies",
                f"{len(changed)}/{len(states)} drivers change (c, a) "
                f"(need >= {math.ceil(len(states) / 2)})")

    # 13. `delta` is the persistent places-gained badge. It must agree with the
    #     orders it is derived from, or the tower shows a gain the positions
    #     contradict.
    if not rows:
        r.skip(13, "delta matches order", "no rows")
    else:
        start = [row["d"] for row in rows[0]]
        start_at = {code: i for i, code in enumerate(start)}
        bad = total = 0
        examples: list = []
        offenders: dict = {}
        for fi, f in enumerate(rows):
            for idx, row in enumerate(f):
                if row["d"] not in start_at:
                    continue
                total += 1
                want = start_at[row["d"]] - idx
                if row["delta"] != want:
                    bad += 1
                    offenders[row["d"]] = offenders.get(row["d"], 0) + 1
                    if len(examples) < 3:
                        examples.append(f"frame {fi} {row['d']} "
                                        f"delta={row['delta']} expected {want}")
        top = ", ".join(f"{k}x{v}" for k, v in
                        sorted(offenders.items(), key=lambda kv: -kv[1])[:4])
        r.check(bad == 0, 13, "delta matches order",
                f"{bad}/{total} mismatched"
                + (f"; drivers: {top}; e.g. {'; '.join(examples)}" if bad else ""))

    # 14. Once a car is out it stays out. /location keeps emitting a retired
    #     car's last coordinates, so a cleared `out` puts a ghost back on track.
    if not rows:
        r.skip(14, "retirements never clear", "no rows")
    else:
        retired_at: dict = {}
        revived: list = []
        for fi, f in enumerate(rows):
            still = {row["d"] for row in f if row["out"] is not None}
            for code in retired_at:
                if code in still:
                    continue
                if any(row["d"] == code for row in f):
                    revived.append(f"{code} at frame {fi} (retired at "
                                   f"{retired_at[code]})")
            for code in still:
                retired_at.setdefault(code, fi)
        r.check(not revived, 14, "retirements never clear",
                f"{len(retired_at)} driver(s) retire; {len(revived)} resurrection(s)"
                + (f": {'; '.join(revived[:3])}" if revived else ""))

    # 15. The PIT badge used to show for every car on the grid, from OpenF1's
    #     bogus lap-1 "stop" rows, and to stick on for a whole race. A real stop
    #     is well under two minutes.
    if not rows or dt <= 0:
        r.skip(15, "pit flags plausible", f"{len(rows)} rows, dt={dt}")
    else:
        pre_race = 0
        if lap_nums and len(lap_nums) == len(rows):
            pre_race = sum(1 for f, lap in zip(rows, lap_nums) if lap == 0
                           for row in f if row["p"])
        runs: list = []       # (driver, start_frame, end_frame)
        open_run: dict = {}
        for fi, f in enumerate(rows):
            flagged = {row["d"] for row in f if row["p"]}
            for code in [c for c in open_run if c not in flagged]:
                runs.append((code, open_run.pop(code), fi - 1))
            for code in flagged:
                open_run.setdefault(code, fi)
        for code, start in open_run.items():
            runs.append((code, start, len(rows) - 1))
        longest = max(((b - a + 1) * dt, c) for c, a, b in runs) \
            if runs else (0.0, None)
        too_long = [(c, (b - a + 1) * dt) for c, a, b in runs
                    if (b - a + 1) * dt > 120]
        ok = not too_long and pre_race == 0
        detail = (f"{len(runs)} stop(s), longest {longest[0]:.0f} s"
                  + (f" ({longest[1]})" if longest[1] else "")
                  + f", limit 120 s; {pre_race} flag(s) on the pre-race grid")
        if too_long:
            detail += "; over-long: " + ", ".join(
                f"{c} {s:.0f} s" for c, s in too_long[:3])
        r.check(ok, 15, "pit flags plausible", detail)


# ---------------------------------------------------------------------------
# driver
# ---------------------------------------------------------------------------

def run_file(path: Path) -> Report:
    d = json.loads(path.read_text())
    label = f"{d.get('year')} {d.get('location')}"
    window = "full race" if d.get("full") else f"from lap {d.get('fromLap')}"
    print(f"\n{'=' * 78}\n{path.name}  —  {label}  "
          f"(session {d.get('sessionKey')}, {window}, dt={d.get('dt')}s)"
          f"\n{'=' * 78}")
    r = Report(label)
    check_geometry(d, r)
    check_frames(d, r)
    check_timing(d, r)
    print(f"\n  {label}: {r.passed} passed, {r.failed} failed, "
          f"{r.noted} note(s), {r.skipped} skipped")
    return r


def main() -> int:
    if len(sys.argv) > 1:
        paths = [Path(a) for a in sys.argv[1:]]
    else:
        paths = sorted(REPLAY_DIR.glob("replay_*.json"))
        if not paths:
            print(f"No replays in {REPLAY_DIR}. Build one with:\n"
                  f"  python3 src/visual/track_replay.py 2024 8 --full")
            return 1

    reports = []
    for p in paths:
        if not p.exists():
            print(f"missing: {p}")
            return 1
        reports.append(run_file(p))

    total_f = sum(r.failed for r in reports)
    total_p = sum(r.passed for r in reports)
    total_n = sum(r.noted for r in reports)
    total_s = sum(r.skipped for r in reports)
    print(f"\n{'=' * 78}")
    if total_f:
        print("FAILURES")
        for r in reports:
            for f in r.failures:
                print(f"  {r.label}: {f}")
    print(f"SUMMARY  {len(reports)} replay(s) · {total_p} passed · "
          f"{total_f} failed · {total_n} note(s) · {total_s} skipped · "
          f"{'FAIL' if total_f else 'OK'}")
    return 1 if total_f else 0


if __name__ == "__main__":
    sys.exit(main())
