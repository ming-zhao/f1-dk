#!/usr/bin/env bash
# Build race replays into data/replay/, then open dashboard/replay.html — no server.
#
# PICK RACES BY EDITING THE LIST BELOW: uncomment a line to include that race, comment
# it out to skip it. That list is the only thing in this file meant to be edited; the
# work itself lives in src/vis/build_replays.py.
#
#   script/replay_data.sh                # build whatever is uncommented below
#   script/replay_data.sh --list         # show what that would build, build nothing
#   script/replay_data.sh 2025 1         # ignore the list, build one race
#   script/replay_data.sh 2025           # ignore the list, build a whole season
#   script/replay_data.sh --jobs 1       # force serial
#
# Each replay is ~3 MB. Rebuilding one already built takes ~3 s and they run in
# parallel; a NEW race takes ~1-2 min and they run one at a time, because that time is
# almost all sleep waiting on OpenF1's rate limit (concurrent fetches just get
# throttled).
set -euo pipefail
cd "$(dirname "$0")/.."

# ── Races to build ─────────────────────────────────────────────────────────────
# Melbourne and Monaco are on by default: two races is enough to exercise the page, and
# they bracket what DK's place-differential scoring cares about — a fast permanent
# circuit with real overtaking, and a street circuit where the grid is destiny.
RACES=(
    "2025:1"     # Melbourne
  # "2025:2"     # Shanghai
  # "2025:3"     # Suzuka
  # "2025:4"     # Sakhir
  # "2025:5"     # Jeddah
  # "2025:6"     # Miami Gardens
  # "2025:7"     # Imola
    "2025:8"     # Monaco
  # "2025:9"     # Barcelona
  # "2025:10"    # Montréal
  # "2025:11"    # Spielberg
  # "2025:12"    # Silverstone
  # "2025:13"    # Spa-Francorchamps
  # "2025:14"    # Budapest
  # "2025:15"    # Zandvoort
  # "2025:16"    # Monza
  # "2025:17"    # Baku
  # "2025:18"    # Marina Bay
  # "2025:19"    # Austin
  # "2025:20"    # Mexico City
  # "2025:21"    # São Paulo
  # "2025:22"    # Las Vegas
  # "2025:23"    # Lusail
  # "2025:24"    # Yas Island
)
# ───────────────────────────────────────────────────────────────────────────────

# A four-digit YEAR as the first argument overrides the list above (so `2025 1` and
# `2025` still work); otherwise the list is what gets built. Flags such as --list and
# --jobs work either way.
if [[ "${1:-}" =~ ^[0-9]{4}$ ]]; then
  exec python3 src/vis/build_replays.py "$@"
fi

joined=$(IFS=,; echo "${RACES[*]:-}")
exec python3 src/vis/build_replays.py --races "$joined" "$@"
