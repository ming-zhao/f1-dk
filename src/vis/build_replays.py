"""Build several replays at once, and refresh the picker afterwards.

`track_replay.py` builds ONE race. This drives it over a list of races, decides what
can run concurrently, and regenerates `dashboard/replay.html` once at the end instead
of per race. `script/replay_data.sh` is a thin wrapper over this — the logic lives here
so it is testable and doesn't turn into Python heredocs inside a shell script.

Concurrency is deliberately conditional. Rebuilding a race whose telemetry is already
cached is CPU-bound and parallelises well (measured 1.88x on two races). Building a NEW
race is almost entirely `time.sleep()` waiting on OpenF1's rate limit, so running those
concurrently just makes them contend for the same budget and get throttled. So:

    already built  ->  run in parallel
    new            ->  run one at a time

Usage:
    python3 src/vis/build_replays.py                  # the default sample races
    python3 src/vis/build_replays.py 2025 1           # one race
    python3 src/vis/build_replays.py 2025             # every crawled round of a season
    python3 src/vis/build_replays.py --list           # what would be built
    python3 src/vis/build_replays.py 2025 --jobs 1    # force serial
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

SRC = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SRC))

from vis.page import build_player  # noqa: E402
from vis.track_replay import OUT_DIR, REPLAY_DIR, refresh_index  # noqa: E402

ROOT = SRC.parent
TRACK_REPLAY = SRC / "vis" / "track_replay.py"

# Two contrasting races, enough to exercise the page without downloading a season:
# a fast permanent circuit with real overtaking, and a street circuit where the grid is
# destiny. They bracket what DK's place-differential scoring cares about.
DEFAULT_RACES = [(2025, 1), (2025, 8)]   # Melbourne, Monaco


def crawled_rounds(year: int) -> list[int]:
    """Race rounds with crawled OpenF1 sessions, in order."""
    f = ROOT / "data" / "raw" / "openf1" / str(year) / "sessions.csv"
    if not f.exists():
        raise SystemExit(
            f"No crawled sessions for {year}. Run:\n"
            f"  python3 src/data/data_crawler.py {year} --source openf1")
    df = pd.read_csv(f)
    df = df[df.get("session_name", "Race") == "Race"]
    return sorted(int(r) for r in df["round"].dropna().unique())


def location_of(year: int, rnd: int) -> str | None:
    """The circuit location for a round, which is what payloads are named after."""
    f = ROOT / "data" / "raw" / "openf1" / str(year) / "sessions.csv"
    if not f.exists():
        return None
    df = pd.read_csv(f)
    df = df[(df.get("session_name", "Race") == "Race") & (df["round"] == rnd)]
    return None if df.empty else str(df.location.iloc[0])


def payload_path(year: int, rnd: int) -> Path | None:
    """Where a round's payload lives, or None if the round isn't crawled."""
    loc = location_of(year, rnd)
    return None if loc is None else REPLAY_DIR / str(year) / f"{loc}.js"


def build_one(year: int, rnd: int, quiet: bool = False) -> bool:
    cmd = [sys.executable, str(TRACK_REPLAY), str(year), str(rnd),
           "--full", "--no-player"]
    r = subprocess.run(cmd, cwd=ROOT,
                       capture_output=quiet, text=True)
    if r.returncode != 0:
        print(f"  ! {year} r{rnd} failed"
              + (f": {(r.stderr or '').strip().splitlines()[-1]}" if quiet and r.stderr
                 else ""))
        return False
    return True


def build(races: list[tuple[int, int]], jobs: int) -> None:
    existing = [(y, r) for y, r in races
                if (p := payload_path(y, r)) is not None and p.exists()]
    fresh = [(y, r) for y, r in races if (y, r) not in set(existing)]

    if existing:
        n = min(jobs, len(existing))
        print(f"── rebuilding {len(existing)} cached race(s) "
              f"with {n} parallel job(s)")
        with ThreadPoolExecutor(max_workers=n) as pool:
            list(pool.map(lambda yr: build_one(*yr, quiet=True), existing))

    for year, rnd in fresh:
        loc = location_of(year, rnd)
        print(f"── {year} round {rnd}"
              + (f" ({loc})" if loc else " — not crawled, skipping"))
        if loc is None:
            continue
        build_one(year, rnd)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("args", nargs="*", type=int, metavar="YEAR [ROUND]")
    ap.add_argument("--jobs", type=int, default=os.cpu_count() or 4,
                    help="parallel jobs for already-built races (default: cores)")
    ap.add_argument("--list", action="store_true",
                    help="show what would be built, and exit")
    opts = ap.parse_args(argv)

    if len(opts.args) >= 2:
        races = [(opts.args[0], opts.args[1])]
    elif len(opts.args) == 1:
        year = opts.args[0]
        races = [(year, r) for r in crawled_rounds(year)]
    else:
        races = DEFAULT_RACES

    if opts.list:
        for y, r in races:
            p = payload_path(y, r)
            state = "built" if p and p.exists() else "new"
            print(f"  {y} r{r:<2} {location_of(y, r) or '?':<20} {state}")
        return 0

    build(races, max(1, opts.jobs))

    index = refresh_index(REPLAY_DIR)
    build_player(os.path.relpath(REPLAY_DIR, OUT_DIR).replace(os.sep, "/"))
    print(f"\n{len(index)} replay(s) in data/replay/:")
    for r in index:
        print(f"  {r['year']} r{r['round']:<2} {r['location']}")
    print("\nOpen dashboard/replay.html — double-click it, no server needed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
