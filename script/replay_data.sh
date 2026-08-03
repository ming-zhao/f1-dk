#!/usr/bin/env bash
# Build race replays into data/replay/, then open dashboard/replay.html — no server.
#
#   script/replay_data.sh                # the two sample races (Melbourne, Monaco)
#   script/replay_data.sh 2025 1         # one race
#   script/replay_data.sh 2025           # every crawled round of that season
#   script/replay_data.sh --list         # what would be built
#   script/replay_data.sh 2025 --jobs 1  # force serial
#
# All the logic lives in src/vis/build_replays.py — this is just a shorthand so you
# don't have to remember the module path.
set -euo pipefail
cd "$(dirname "$0")/.."
exec python3 src/vis/build_replays.py "$@"
