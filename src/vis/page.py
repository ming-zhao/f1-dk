"""Assemble a replay page from the assets in `assets/` plus one JSON payload.

Replaces both `template.py`'s 830-line format string and `player.py`'s 18 string
surgery operations. There are exactly two pages and they share every asset:

    standalone(...)  dashboard/replay_<year>_<loc>.html — data inlined
    picker()         dashboard/replay.html — data fetched from a payload dir

The only difference reaching the browser is the `mode` field of the JSON blob, which
`replay.js` branches on once. Nothing here rewrites JS or CSS: the assets are the
single source of truth, and the slots below are the whole interface to them.
"""

from __future__ import annotations

import json
from pathlib import Path

ASSETS = Path(__file__).resolve().parent / "assets"
OUT_DIR = Path(__file__).resolve().parent.parent.parent / "dashboard"
# Where track_replay.py writes payloads, as a URL path relative to a page in
# OUT_DIR. Must match REPLAY_DIR there — a mismatch gives a picker that 404s.
DEFAULT_DATA_DIR = "../data/replay"

# Extra styling the picker needs for its dropdowns. Kept next to the page that uses
# it rather than in replay.css, since the standalone page has no picker.
PICKER_CSS = """  .picker { display:flex; gap:16px; align-items:center; margin-top:6px;
             flex-wrap:wrap; }
  .picker label { color:var(--dim); font-size:12px; }
  .picker select { background:#24242a; color:#f0f0f2; border:1px solid #33333b;
                    border-radius:6px; padding:4px 8px; font-size:13px;
                    margin-left:4px; }"""

PICKER_HEADER = """  <h1>F1 race replay</h1>
  <div class="picker">
    <label>Year <select id="pickYear"></select></label>
    <label>Race <select id="pickRace"></select></label>
    <span class="sub" id="meta">loading…</span>
    <b class="sub" id="lap" style="color:#f0f0f2">lap –</b>
  </div>"""


def _asset(name: str) -> str:
    return (ASSETS / name).read_text(encoding="utf-8")


def _fill(slots: dict[str, str]) -> str:
    """Substitute the @@SLOT@@ markers in the skeleton. Every slot must be used."""
    html = _asset("replay.html")
    for key, value in slots.items():
        token = f"@@{key}@@"
        if token not in html:
            raise ValueError(f"replay.html has no {token} slot")
        html = html.replace(token, value)
    left = [s for s in html.split("@@")[1::2] if s.isupper()]
    if left:
        raise ValueError(f"unfilled slots in replay.html: {left}")
    return html


def _page(title: str, header: str, data: dict, w: int, h: int, last: int,
          extra_css: str = "") -> str:
    css = _asset("replay.css").rstrip("\n")
    if extra_css:
        css += "\n\n" + extra_css
    return _fill({
        "TITLE": title,
        "CSS": css,
        "HEADER": header,
        "W": str(w),
        "H": str(h),
        "LAST": str(last),
        # separators: the payload is megabytes, and </script> can't appear inside it.
        "DATA": json.dumps(data, separators=(",", ":")).replace("</", "<\\/"),
        "JS": _asset("replay.js"),
    })


def standalone(title: str, subtitle: str, race: dict) -> str:
    """A self-contained page: this one race's data is baked in."""
    header = (f'  <h1>{title}</h1>\n'
              f'  <div class="sub">{subtitle} · '
              f'<b id="lap" style="color:#f0f0f2">lap –</b></div>')
    return _page(title, header, {"mode": "inline", "race": race},
                 race["w"], race["h"], max(0, len(race["frames"]) - 1))


def picker(data_dir: str = DEFAULT_DATA_DIR) -> str:
    """The multi-race page: dropdowns fetch payloads from `data_dir` at runtime.

    `data_dir` is a URL path relative to the page, so payloads can live outside
    dashboard/ without this module needing to know where.
    """
    return _page("F1 race replay", PICKER_HEADER,
                 {"mode": "picker", "dataDir": data_dir},
                 1150, 620, 0, extra_css=PICKER_CSS)


def build_player(data_dir: str = DEFAULT_DATA_DIR) -> Path:
    """Write dashboard/replay.html. Name kept for track_replay.py's hook."""
    out = OUT_DIR / "replay.html"
    out.write_text(picker(data_dir), encoding="utf-8")
    return out


if __name__ == "__main__":
    p = build_player()
    print(f"Wrote {p} ({p.stat().st_size / 1024:.0f} KB) — open it and pick a race.")
