"""Official circuit outlines, instead of deriving them from car positions.

Deriving the outline from a single driver's lap was the wrong foundation. It cost a
long series of bugs — lap-seam self-intersection, duplicate points from stationary
cars, absolute thresholds that failed on short circuits — and worst of all it was
**silently truncating Monaco to 80% of the lap** (2.68 km of 3.337 km), discarding the
whole Nouvelle Chicane / tunnel-exit stretch. Every width and rotation tweak was
fighting a broken shape.

MultiViewer publishes a hand-authored closed centreline per circuit, keyed by the SAME
`circuit_key` OpenF1 already gives us in /sessions — and crucially in the **same
coordinate space**, so car positions overlay with no transform. It also carries an
official `rotation` for orienting the map the way broadcasts do, plus corner markers.

    https://api.multiviewer.app/api/v1/circuits/{circuit_key}/{year}

Verified against official track lengths (units are ~decimetres, ~9.8-9.9 per metre):
Monaco 3.270 km vs 3.337 official; Melbourne within 0.5%.

This is a community service and the geometry is static per circuit, so responses are
cached to disk permanently and never re-fetched.

Coverage is COMPLETE, which is why the derived-outline fallback could be deleted:
all 48 (year, circuit_key) pairs in data/raw/openf1/*/sessions.csv resolve to a map
(2024 and 2025, 24 circuits each). Re-check any time with:

    python3 src/visual/circuit.py

If that ever reports a gap, the honest fix is to add geometry for that circuit — not
to reinstate the derived outline, which truncated Monaco to 80% of the lap.
"""

import json
import math
from pathlib import Path
from typing import Optional

import requests

ROOT = Path(__file__).resolve().parent.parent.parent
CACHE = ROOT / "data" / "raw" / "circuits"
BASE = "https://api.multiviewer.app/api/v1/circuits"
UA = "f1-dfs-personal/0.1 (personal DFS project)"


def fetch(circuit_key: int, year: int) -> Optional[dict]:
    """Official outline for a circuit, cached forever. None if unavailable."""
    CACHE.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE / f"{circuit_key}_{year}.json"
    if cache_file.exists():
        try:
            return json.loads(cache_file.read_text())
        except json.JSONDecodeError:
            cache_file.unlink()

    try:
        resp = requests.get(f"{BASE}/{circuit_key}/{year}",
                            headers={"User-Agent": UA}, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        # No fallback exists any more — the position-derived outline was removed once
        # this map was confirmed to cover every crawled circuit. frames.build() will
        # refuse to build rather than draw a wrong shape.
        print(f"    circuit map unavailable ({type(exc).__name__}) — the replay "
              f"needs it; retry when api.multiviewer.app is reachable")
        return None

    if not (data.get("x") and data.get("y")):
        return None
    cache_file.write_text(json.dumps(data))
    return data


def outline(circuit_key: int, year: int) -> tuple[list, Optional[float]]:
    """([[x, y], …], rotation_degrees). ([], None) if the map isn't available.

    The published polyline is open and contains a few sub-metre backtrack wiggles
    (a 22 cm reversal at Monaco registers as a self-intersection), so points closer
    than 5 units are dropped and the loop is closed explicitly.
    """
    data = fetch(circuit_key, year)
    if not data:
        return [], None

    pts = []
    for x, y in zip(data["x"], data["y"]):
        p = [int(x), int(y)]
        if not pts or math.dist(pts[-1], p) >= 5:
            pts.append(p)
    if len(pts) > 2 and math.dist(pts[0], pts[-1]) > 5:
        pts.append(list(pts[0]))       # close the lap

    rot = data.get("rotation")
    return pts, (float(rot) if rot is not None else None)


def corners(circuit_key: int, year: int) -> list:
    """[{number, x, y, angle, distance}, …] — corner markers, empty if unavailable."""
    data = fetch(circuit_key, year)
    if not data:
        return []
    out = []
    for c in data.get("corners", []):
        tp = c.get("trackPosition") or {}
        if tp.get("x") is None:
            continue
        out.append({"number": c.get("number"), "x": int(tp["x"]), "y": int(tp["y"]),
                    "angle": c.get("angle"), "distance": c.get("length")})
    return out


def coverage() -> tuple[list, list]:
    """(covered, missing) for every circuit in the crawled OpenF1 session index.

    Each entry is (year, circuit_key, location). `missing` MUST stay empty: the
    replay has no outline fallback, so a gap here means that race cannot be built.
    """
    import pandas as pd

    keys = set()
    root = ROOT / "data" / "raw" / "openf1"
    for f in sorted(root.glob("*/sessions.csv")):
        df = pd.read_csv(f)
        races = df[df.get("session_name", "Race") == "Race"]
        for y, ck, loc in zip(races.year, races.circuit_key, races.location):
            if pd.notna(ck):
                keys.add((int(y), int(ck), loc))

    covered, missing = [], []
    for entry in sorted(keys):
        (covered if outline(entry[1], entry[0])[0] else missing).append(entry)
    return covered, missing


if __name__ == "__main__":
    covered, missing = coverage()
    for year, ck, loc in covered:
        pts, rot = outline(ck, year)
        km = sum(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1)) / 10000
        print(f"  ok   {year} key={ck:<4} {loc:<18} {len(pts):>4} pts  "
              f"{km:.3f} km  rot {rot:.0f}°")
    for year, ck, loc in missing:
        print(f"  MISS {year} key={ck:<4} {loc}")
    print(f"\n{len(covered)} covered, {len(missing)} missing")
    if missing:
        raise SystemExit("Circuit map coverage is INCOMPLETE — these races cannot be "
                         "replayed. Add geometry; do not reinstate a derived outline.")
