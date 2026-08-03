#!/usr/bin/env bash
# Populate data/replay/ so dashboard/replay.html has races to show.
#
# Open dashboard/replay.html directly afterwards — no server. It loads the payloads
# with <script> tags, which work from file:// (fetch() does not).
#
#   script/replay_data_builder.sh                 # a couple of sample races
#   script/replay_data_builder.sh 2025 1          # one specific race
#   script/replay_data_builder.sh 2025            # every crawled round of a season
#
# Each replay is ~3 MB and takes a few minutes: the crawl is cached, but ~20 telemetry
# requests per race are paced to stay inside OpenF1's rate limit. Re-running is cheap —
# cached responses are reused, so only new races cost anything.
set -euo pipefail

cd "$(dirname "$0")/.."
REPLAY=src/vis/track_replay.py

build() {   # build <year> <round>
  echo "── $1 round $2"
  python3 "$REPLAY" "$1" "$2" --full --no-player || {
    echo "   skipped $1 r$2 (not crawled? run: python3 src/data/data_crawler.py $1 --source openf1)"
    return 0
  }
}

case $# in
  0)
    # The whole 2025 season is listed below; only two are enabled by default because
    # each replay is ~3 MB and a few minutes of paced telemetry requests. Uncomment
    # any round you want — they're all crawled, so it just works.
    #
    # Melbourne and Monaco are the pair worth having: a fast permanent circuit with
    # real overtaking, and a tight street circuit where the grid is destiny. They
    # bracket the two extremes the DK place-differential scoring cares about.
    build 2025 1     # Melbourne
    build 2025 8     # Monaco
  # build 2025 2     # Shanghai
  # build 2025 3     # Suzuka
  # build 2025 4     # Sakhir
  # build 2025 5     # Jeddah
  # build 2025 6     # Miami Gardens
  # build 2025 7     # Imola
  # build 2025 9     # Barcelona
  # build 2025 10    # Montréal
  # build 2025 11    # Spielberg
  # build 2025 12    # Silverstone
  # build 2025 13    # Spa-Francorchamps
  # build 2025 14    # Budapest
  # build 2025 15    # Zandvoort
  # build 2025 16    # Monza
  # build 2025 17    # Baku
  # build 2025 18    # Marina Bay
  # build 2025 19    # Austin
  # build 2025 20    # Mexico City
  # build 2025 21    # São Paulo
  # build 2025 22    # Las Vegas
  # build 2025 23    # Lusail
  # build 2025 24    # Yas Island
    ;;
  1)
    year=$1
    rounds=$(python3 - "$year" <<'PY'
import sys, pandas as pd, pathlib
year = sys.argv[1]
f = pathlib.Path("data/raw/openf1") / year / "sessions.csv"
if not f.exists():
    sys.exit(f"No crawled sessions for {year}. Run:\n"
             f"  python3 src/data/data_crawler.py {year} --source openf1")
df = pd.read_csv(f)
df = df[df.get("session_name", "Race") == "Race"]
print(" ".join(str(int(r)) for r in sorted(df["round"].dropna().unique())))
PY
    ) || { echo "$rounds"; exit 1; }
    for r in $rounds; do build "$year" "$r"; done
    ;;
  2)
    build "$1" "$2"
    ;;
  *)
    echo "usage: $0 [YEAR [ROUND]]" >&2; exit 2 ;;
esac

# Regenerate the picker once at the end rather than per race.
python3 - <<'PY'
import sys, pathlib
sys.path.insert(0, "src")
from vis.page import build_player
from vis.track_replay import REPLAY_DIR, OUT_DIR, refresh_index
import os
index = refresh_index(REPLAY_DIR)
build_player(os.path.relpath(REPLAY_DIR, OUT_DIR).replace(os.sep, "/"))
print(f"\n{len(index)} replay(s) in data/replay/:")
for r in index:
    print(f"  {r['year']} r{r['round']:<2} {r['location']}")
print("\nOpen dashboard/replay.html — double-click it, no server needed.")
PY
