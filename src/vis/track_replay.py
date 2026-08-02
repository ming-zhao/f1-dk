"""Build a broadcast-style race replay: timing tower + animated circuit map.

Entry point. `main()` is a thin CLI over the named steps below, each independently
callable and testable:

    select_session   pick the race to replay
    resolve_window   find a lap-accurate time window and a frame step
    fetch_feeds      positions, running order, gaps, tyres, pits, retirements
    build_frames     resample everything onto one animation timeline
    derive_geometry  official circuit outline + a position-derived pit lane
    size_canvas      rotation, canvas size, track width, car scale
    write_outputs    standalone HTML + JSON payload + the player's index

The work itself lives in sibling modules:

    race.py       session selection, time windows, per-frame feeds
    circuit.py    official circuit map (MultiViewer), cached forever
    frames.py     resample feeds onto the animation timeline
    layout.py     pit lane, rotation, canvas sizing
    page.py       assembles a page from assets/ (replay.html/.css/.js) + one payload

Output is a self-contained HTML file — open it directly, no server needed.

Three things about this data that are easy to get wrong:

  * The race does NOT start at the session's `date_start`. Melbourne 2025 opens the
    session at 04:00 UTC but the first lap begins at 04:18, so windows are anchored
    to the first lap's `date_start`.
  * /position and /intervals are change-only feeds. A settled green-flag phase can
    pass with zero rows, which looks like a frozen tower but isn't — so the default
    window is the lap with the most position changes.
  * The circuit outline must come from the official map (circuit.py). Deriving it
    from one driver's /location lap silently truncated Monaco to 80% of the lap.

The map is rotated so the start/finish straight runs horizontally, which gives a
landscape footprint that fills a wide canvas and lets the car glyphs read clearly.

Usage:
    python3 src/vis/track_replay.py                       # latest crawled race
    python3 src/vis/track_replay.py 2025 1                # season 2025, round 1
    python3 src/vis/track_replay.py 2025 1 --from-lap 10 --laps 3
    python3 src/vis/track_replay.py 2025 1 --rotate 40    # override rotation
    python3 src/vis/track_replay.py --list                # what's available
"""

import argparse
import json
import os
import math
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

SRC = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SRC))

from vis import circuit, frames, layout, page, race  # noqa: E402
from vis.page import build_player  # noqa: E402

OUT_DIR = SRC.parent / "dashboard"
# Replay payloads are generated data, so they live under data/ rather than beside the
# dashboard's committed assets. One subdirectory per season.
REPLAY_DIR = SRC.parent / "data" / "replay"


@dataclass
class Window:
    """The slice of race being replayed, and how densely it's sampled."""
    t0: datetime
    t1: datetime
    ref: int          # reference car whose laps anchor the window
    from_lap: int
    n_laps: int
    thin: int         # frames.step_for() multiplier

    @property
    def span(self) -> float:
        return (self.t1 - self.t0).total_seconds()

    @property
    def dt(self) -> float:
        """Seconds of race time per rendered frame."""
        return frames.FRAME_STEP * frames.KEEP_EVERY * self.thin


@dataclass
class Feeds:
    """Everything fetched for one window. `pos` is mutated in place by build_frames."""
    pos: pd.DataFrame
    orders: list
    ivals: list
    tyres: dict
    stints: dict
    pits: dict
    out_cars: dict
    marks: list
    total_laps: int


@dataclass
class Built:
    """The resampled animation timeline."""
    frames: list
    outline: list
    rows: list
    colours: dict
    nums: dict
    lap_nums: list


@dataclass
class Canvas:
    """Where and how big to draw it."""
    w: int
    h: int
    track_w: float
    car_scale: float
    rotation: float   # radians, data space


def parse_args(argv: list | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="TV-style race replay: timing tower + circuit map.")
    ap.add_argument("args", nargs="*", type=int, metavar="YEAR|ROUND",
                    help="e.g. '2025 1' (default: latest crawled race)")
    ap.add_argument("--from-lap", type=int, default=None,
                    help="first lap to replay (default: the busiest lap)")
    ap.add_argument("--laps", type=int, default=2, help="how many laps (default: 2)")
    ap.add_argument("--full", action="store_true",
                    help="replay the ENTIRE race (frame step widens automatically; "
                         "~5 MB and ~20 location requests for a 57-lap race)")
    ap.add_argument("--size", default="1150x620", metavar="WxH",
                    help="max canvas size; the canvas is shrink-wrapped to the "
                         "circuit inside this budget (default 1150x620)")
    ap.add_argument("--rotate", type=float, default=None, metavar="DEG",
                    help="override rotation, clockwise degrees (default: lay the "
                         "start/finish straight horizontal)")
    ap.add_argument("--no-rotate", action="store_true",
                    help="keep the circuit's native orientation (north straight up)")
    ap.add_argument("--list", action="store_true", help="list crawled races and exit")
    ap.add_argument("--no-player", action="store_true",
                    help="skip regenerating dashboard/replay.html")
    return ap.parse_args(argv)


def list_races() -> None:
    """Print the crawled races available to replay."""
    df = race.available_races()
    if df.empty:
        print("No crawled OpenF1 races. Run:\n"
              "  python3 src/data/data_crawler.py 2025 --source openf1")
        return
    cols = [c for c in ("year", "round", "location", "session_key") if c in df.columns]
    print(df[cols].sort_values(cols[:2]).to_string(index=False))


def select_session(opts: argparse.Namespace) -> dict:
    """Resolve the positional YEAR [ROUND] arguments to one crawled session."""
    years = [n for n in opts.args if n >= 1950]
    rounds = [n for n in opts.args if 0 < n < 100]
    return race.pick_session(years[0] if years else None,
                             rounds[0] if rounds else None)


def resolve_window(session: dict, opts: argparse.Namespace) -> Window:
    """Pick the time window to replay, and how coarsely to sample it."""
    if opts.full:
        t0, t1, ref = race.lap_window(session, None, 0, full=True)
        from_lap = 1
    else:
        from_lap = opts.from_lap or race.busiest_lap(session)
        t0, t1, ref = race.lap_window(session, from_lap, opts.laps)
    win = Window(t0, t1, ref, from_lap, opts.laps, frames.step_for(
        (t1 - t0).total_seconds()))
    print(f"  window {win.t0.time()} → {win.t1.time()} UTC "
          f"({win.span/60:.0f} min, reference car #{win.ref}, {win.dt:g}s/frame)")
    return win


def fetch_feeds(session: dict, win: Window) -> Feeds:
    """Fetch every per-frame feed for `win`."""
    pos = race.fetch_positions(session, win.t0, win.t1)
    orders = race.fetch_order(session, win.t0, win.t1)
    ivals = race.fetch_intervals(session, win.t0, win.t1)
    tyres = race.tyre_state(session, win.t0,
                            range(win.from_lap, win.from_lap + win.n_laps))
    stints = race.tyre_stints(session)
    pits = race.pit_windows(session, win.t0)
    # EVERY retirement, not just pre-window ones: a car that stops mid-replay has to
    # be flagged from the lap it stopped on, or it sits motionless on the racing line.
    out_cars = race.retirements(session)
    if out_cars:
        print("  retired: %s" % ", ".join(
            f"#{n} (lap {l})" for n, l in sorted(out_cars.items(), key=lambda x: -x[1])))
    marks, total_laps = race.lap_marks(session, win.t0)
    return Feeds(pos, orders, ivals, tyres, stints, pits, out_cars, marks, total_laps)


def circuit_map(session: dict) -> tuple[list, float | None]:
    """Official circuit outline + rotation, in the same coordinate space as /location.

    Required, not optional — see the note in frames.build().
    """
    ck = int(session.get("circuit_key") or 0)
    outline, rot = circuit.outline(ck, int(session["year"])) if ck else ([], None)
    if outline:
        km = sum(math.dist(outline[i], outline[i + 1])
                 for i in range(len(outline) - 1)) / 10000
        print(f"  official circuit map: {len(outline)} pts, {km:.3f} km"
              + (f", rotation {rot:.0f}°" if rot is not None else ""))
    return outline, rot


def build_frames(feeds: Feeds, win: Window, off_outline: list) -> Built:
    """Resample every feed onto one animation timeline."""
    return Built(*frames.build(
        feeds.pos, feeds.orders, feeds.ivals, win.ref, feeds.tyres, feeds.pits,
        win.from_lap, feeds.out_cars, win.thin, feeds.marks,
        official_outline=off_outline, stints=feeds.stints))


def derive_geometry(session: dict, feeds: Feeds, win: Window,
                    outline: list) -> tuple[list, list]:
    """Pit lane path + box locations, derived from where cars actually went."""
    feeds.pos["date"] = pd.to_datetime(feeds.pos["date"], format="ISO8601")
    lane, boxes = layout.pit_lane(session, feeds.pits, feeds.pos, win.t0, outline)
    print(f"  pit lane: {len(lane)} path points, {len(boxes)} box locations"
          if lane else "  pit lane: no stops in this window — nothing to derive")
    return lane, boxes


def size_canvas(opts: argparse.Namespace, outline: list, off_rot: float | None,
                lane: list) -> Canvas:
    """Choose a rotation, then shrink-wrap the canvas around the circuit."""
    budget_w, budget_h = (int(v) for v in opts.size.lower().split("x"))
    if opts.no_rotate:
        rotation = 0.0
    elif opts.rotate is not None:
        # Screen-clockwise is negative in data space, since the canvas flips y.
        rotation = -opts.rotate * math.pi / 180
    elif off_rot is not None:
        # The official rotation orients the map the way broadcast graphics do.
        # +90 aligns it with a landscape canvas (the convention f1-dash uses).
        rotation = -(off_rot + 90) * math.pi / 180
    else:
        # The official map always carries a rotation, so this is defensive only.
        print("  no official rotation for this circuit — keeping native orientation")
        rotation = 0.0

    # Fit on circuit + pit lane, then grow until a full-width road fits without the
    # track overlapping itself (see layout.fit_for_track).
    w, h, track_w, car_scale = layout.fit_for_track(
        outline, rotation, budget_w, budget_h, extra=lane)
    gap_m = layout.min_self_gap(outline, rotation) / 10
    print(f"  canvas {w}x{h} · track {track_w:.0f}px · cars {car_scale:.2f}x "
          f"· tightest self-gap {gap_m:.0f}m")
    return Canvas(w, h, track_w, car_scale, rotation)


def render_html(label: str, opts: argparse.Namespace, win: Window, built: Built,
                feeds: Feeds, payload: dict) -> str:
    """Wrap the shared assets around this race's payload.

    The page gets exactly the same dict that goes to replays/*.json, inlined instead
    of fetched — so the standalone page and the picker cannot show different data.
    """
    n_out = len(feeds.out_cars)
    lap_range = ('–' + str(win.from_lap + win.n_laps - 1)
                 if win.n_laps > 1 and not opts.full else '')
    return page.standalone(
        title=f"{label} — race replay",
        subtitle=(f"{len(built.colours) - n_out} running"
                  f"{f' · {n_out} retired' if feeds.out_cars else ''}"
                  f" · lap {win.from_lap}{lap_range}"
                  f" · positions at ~3.8 Hz, timing from OpenF1 /position + /intervals"),
        race=payload,
    )


def replay_payload(session: dict, opts: argparse.Namespace, win: Window, built: Built,
                   feeds: Feeds, canvas: Canvas, lane: list, boxes: list) -> dict:
    """The same data as JSON, for the multi-race player (dashboard/replay.html)."""
    return {
        "year": int(session["year"]),
        "round": int(session.get("round") or 0),
        "location": session.get("location"),
        "sessionKey": int(session["session_key"]),
        "fromLap": win.from_lap, "laps": win.n_laps, "full": bool(opts.full),
        "running": len(built.colours) - len(feeds.out_cars),
        "retired": len(feeds.out_cars),
        "frames": built.frames, "outline": built.outline, "rows": built.rows,
        "lapNums": built.lap_nums, "totalLaps": feeds.total_laps,
        "colours": built.colours, "pitlane": lane, "pitbox": boxes,
        "w": canvas.w, "h": canvas.h, "trackw": round(canvas.track_w, 1),
        "carscale": round(canvas.car_scale, 3), "dt": win.dt,
        "rot": round(canvas.rotation, 5),
    }


def refresh_index(data_dir: Path) -> list:
    """Rebuild index.json from every payload on disk, across all years.

    Payloads live in per-year subdirectories, so `file` in the index is a relative
    path (`2024/replay_2024_Monaco.json`) that the picker can fetch directly.
    """
    index = []
    for f in sorted(data_dir.glob("*/replay_*.json")):
        r = json.loads(f.read_text())
        r["_file"] = f"{f.parent.name}/{f.name}"
        index.append(r)
    index.sort(key=lambda r: (r["year"], r["round"]))
    (data_dir / "index.json").write_text(json.dumps(
        [{k: r[k] for k in ("year", "round", "location", "fromLap", "laps",
                            "running", "retired")} | {"file": r["_file"]}
         for r in index], indent=1), encoding="utf-8")
    return index


def write_outputs(session: dict, opts: argparse.Namespace, html: str,
                  payload: dict) -> None:
    """Standalone HTML, JSON payload, refreshed index, and the player page."""
    stem = f"replay_{int(session['year'])}_{session.get('location','race')}"
    out = OUT_DIR / f"{stem}.html"
    out.write_text(html, encoding="utf-8")
    print(f"\nWrote {out} ({out.stat().st_size/1024:.0f} KB) — open in a browser.")

    year_dir = REPLAY_DIR / str(int(session["year"]))
    year_dir.mkdir(parents=True, exist_ok=True)
    jf = year_dir / f"{stem}.json"
    jf.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")

    index = refresh_index(REPLAY_DIR)
    if not opts.no_player:
        # URL path from dashboard/replay.html to the payload directory.
        build_player(os.path.relpath(REPLAY_DIR, OUT_DIR))
    print(f"Wrote {jf.relative_to(SRC.parent)} "
          f"({jf.stat().st_size/1024:.0f} KB) + refreshed "
          f"{(REPLAY_DIR / 'index.json').relative_to(SRC.parent)} "
          f"({len(index)} race(s)) — open dashboard/replay.html to switch races.")


def main(argv: list | None = None) -> None:
    opts = parse_args(argv)
    if opts.list:
        list_races()
        return

    session = select_session(opts)
    label = f"{int(session['year'])} {session.get('location')}"
    print(f"Building replay: {label} [session {int(session['session_key'])}]")

    win = resolve_window(session, opts)
    feeds = fetch_feeds(session, win)
    off_outline, off_rot = circuit_map(session)
    built = build_frames(feeds, win, off_outline)
    lane, boxes = derive_geometry(session, feeds, win, built.outline)
    canvas = size_canvas(opts, built.outline, off_rot, lane)

    print(f"  {len(built.frames)} frames · {len(built.colours)} cars · "
          f"{len(built.outline)} outline points")
    print(f"  timing: {'order OK' if any(built.rows) else 'NO order'}, "
          f"{len(feeds.ivals)} interval snapshots, {len(feeds.tyres)} tyre states, "
          f"rotation {-canvas.rotation * 180 / math.pi % 360:.0f}°")

    # One payload feeds both outputs: inlined into the standalone page, and written
    # to replays/*.json for the picker to fetch.
    payload = replay_payload(session, opts, win, built, feeds, canvas, lane, boxes)
    write_outputs(session, opts,
                  render_html(label, opts, win, built, feeds, payload), payload)


if __name__ == "__main__":
    main()
