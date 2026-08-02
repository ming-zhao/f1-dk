"""Single entry point for crawling every data source.

Each source is a module in src/data/ exposing `fetch(year, only_round, **opts)`.
Everything lands under data/raw/<source>/<year>/, and every response is cached, so
re-running only fetches what's missing — cheap and safe to re-run any time.

    data/raw/jolpica/2025/results.csv        one row per driver per race
    data/raw/jolpica/2025/qualifying.csv     quali classification + Q1/Q2/Q3
    data/raw/openf1/2025/laps.csv            per-lap sectors + speed traps
    data/raw/openf1/2025/…                   stints, pit, overtakes, weather, …
    data/raw/openf1/2025/telemetry/          ~3.6 Hz car data (opt-in, large)
    data/raw/draftkings/<race>.csv           salaries (not by year — upcoming race only)

Usage:
    python3 src/data/data_crawler.py                     # all sources, last 6 seasons
    python3 src/data/data_crawler.py 2025                 # one season
    python3 src/data/data_crawler.py 2025 2026            # several seasons
    python3 src/data/data_crawler.py 2025 3               # 2025 round 3 only
    python3 src/data/data_crawler.py 2025 --source openf1 --telemetry
    python3 src/data/data_crawler.py --list               # show what's on disk

Year vs round is inferred from magnitude: >= 1950 is a year, < 100 is a round.
So "2025 3" means season 2025, round 3.
"""

import argparse
import sys
from datetime import date
from pathlib import Path
from typing import Optional

SRC = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SRC))  # so `util.common` imports cleanly from the fetchers

from data import SOURCES  # noqa: E402
from data._http import DATA  # noqa: E402

FIRST_YEAR = 1950
DEFAULT_SEASONS = 6


def split_years_and_round(nums: list[int]) -> tuple[list[int], Optional[int]]:
    """Interpret positional args: >= 1950 is a year, < 100 is a round."""
    years = [n for n in nums if n >= FIRST_YEAR]
    rounds = [n for n in nums if 0 < n < 100]
    unknown = [n for n in nums if n not in years and n not in rounds]
    if unknown:
        raise SystemExit(f"error: can't tell if {unknown} are years or rounds "
                         f"(years >= {FIRST_YEAR}, rounds 1-99)")
    if len(rounds) > 1:
        raise SystemExit(f"error: one round at a time, got {rounds}")
    if rounds and len(years) != 1:
        raise SystemExit("error: a round needs exactly one year, e.g. '2025 3' "
                         f"(got years {years})")
    return years, (rounds[0] if rounds else None)


def show_inventory() -> None:
    """Print what's on disk, fetch nothing."""
    raw = DATA / "raw"
    print("data/raw/ inventory\n")
    if not raw.exists():
        print("  (nothing crawled yet)")
        return

    for source in sorted(p for p in raw.iterdir() if p.is_dir()):
        print(f"  {source.name}/")
        years = sorted(p for p in source.iterdir() if p.is_dir() and p.name.isdigit())
        if years:
            for y in years:
                bits = []
                for c in sorted(y.glob("*.csv")):
                    try:
                        n = sum(1 for _ in c.open()) - 1
                    except OSError:
                        n = "?"
                    bits.append(f"{c.stem}={n}")
                tele = y / "telemetry"
                extra = (f", telemetry={len(list(tele.glob('*.csv')))} files"
                         if tele.exists() else "")
                print(f"    {y.name}: {', '.join(bits) if bits else '(no csv)'}{extra}")
        else:
            # Not every source is year-partitioned or CSV: draftkings/ is keyed by
            # race name, and circuits/ holds cached JSON circuit maps.
            loose = sorted(list(source.glob("*.csv")) + list(source.glob("*.json")))
            for c in loose[:10]:
                print(f"    {c.name}")
            if len(loose) > 10:
                print(f"    … {len(loose) - 10} more")
            if not loose:
                print("    (empty)")
    print()


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Crawl every F1 data source into data/raw/<source>/<year>/.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="examples:\n"
               "  python3 src/data/data_crawler.py                 # all sources, last 6 seasons\n"
               "  python3 src/data/data_crawler.py 2025            # one season\n"
               "  python3 src/data/data_crawler.py 2025 3          # 2025 round 3 only\n"
               "  python3 src/data/data_crawler.py 2025 --source openf1 --telemetry\n"
               "  python3 src/data/data_crawler.py --list          # what's on disk\n",
    )
    ap.add_argument("args", nargs="*", type=int, metavar="YEAR|ROUND",
                    help=f"seasons to crawl (default: last {DEFAULT_SEASONS}); "
                         "add a round to fetch a single race, e.g. '2025 3'")
    ap.add_argument("--source", choices=[*SOURCES, "all"], default="all",
                    help="crawl only one source (default: all)")
    ap.add_argument("--telemetry", action="store_true",
                    help="OpenF1: also pull car_data + location (~73 MB per race)")
    ap.add_argument("--all-sessions", action="store_true",
                    help="OpenF1: include practice/quali/sprint, not just races")
    ap.add_argument("--list", action="store_true",
                    help="show what's already on disk and exit")
    opts = ap.parse_args()

    if opts.list:
        show_inventory()
        return

    years, only_round = split_years_and_round(opts.args)
    if not years:
        current = date.today().year
        years = list(range(current - DEFAULT_SEASONS + 1, current + 1))

    want = list(SOURCES) if opts.source == "all" else [opts.source]
    scope = f"years {years}" + (f", round {only_round}" if only_round else "")
    print(f"Crawling {', '.join(want)} — {scope}"
          f"{' + telemetry' if opts.telemetry else ''}\n")

    for name in want:
        module = SOURCES[name]
        first = getattr(module, "FIRST_YEAR", None)
        print(f"=== {name}" + (f" ({first}-present)" if first else "") + " ===")
        if name == "draftkings":
            # No year dimension — DK serves only the upcoming race.
            module.fetch()
        else:
            for y in years:
                module.fetch(y, only_round,
                             telemetry=opts.telemetry,
                             all_sessions=opts.all_sessions)
        print()

    print("Done. Responses are cached — re-runs only fetch what's missing.")
    print("Run with --list to see what's on disk.")


if __name__ == "__main__":
    main()
