#!/usr/bin/env bash
# Serve the dashboards and open one in a browser.
#
# Why this exists: dashboard/replay.html FETCHES its ~3 MB payload at runtime, and
# browsers block fetch() from a file:// origin — so double-clicking it gives a blank
# page. It has to be served over HTTP. (dashboard/index.html works either way, because
# it loads data through a <script> tag, which CORS exempts.)
#
#   ./run.sh            # serve + open the replay
#   ./run.sh dashboard  # serve + open the lineup dashboard
#   ./run.sh none       # just serve, don't open anything
set -euo pipefail

PORT="${PORT:-8000}"
WHAT="${1:-replay}"
cd "$(dirname "$0")"

case "$WHAT" in
  replay)    PAGE="dashboard/replay.html" ;;
  dashboard) PAGE="dashboard/index.html" ;;
  none)      PAGE="" ;;
  *) echo "usage: $0 [replay|dashboard|none]" >&2; exit 2 ;;
esac

if [ "$WHAT" = replay ] && [ ! -f data/replay/index.json ]; then
  echo "No replays built yet. Build one first, e.g.:"
  echo "  python3 src/vis/track_replay.py 2025 1 --full"
  exit 1
fi

# Reuse an existing server on this port instead of failing on 'address in use'.
if curl -sfo /dev/null "http://localhost:$PORT/" 2>/dev/null; then
  echo "Server already running on port $PORT"
else
  python3 -m http.server "$PORT" --bind 127.0.0.1 >/tmp/f1-server.log 2>&1 &
  echo "Serving $(pwd) on port $PORT (log: /tmp/f1-server.log, pid $!)"
  for _ in $(seq 20); do
    curl -sfo /dev/null "http://localhost:$PORT/" 2>/dev/null && break
    sleep 0.2
  done
fi

if [ -n "$PAGE" ]; then
  URL="http://localhost:$PORT/$PAGE"
  echo "Opening $URL"
  command -v open >/dev/null && open "$URL" || echo "Open it manually: $URL"
fi
