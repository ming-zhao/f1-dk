"""Shared HTTP + CSV helpers for the per-source fetchers."""

import json
import time
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent.parent
DATA = ROOT / "data"


def get_json(url: str, cache_file: Path, sleep: float,
             max_retries: int = 8, max_backoff: int = 60) -> Optional[object]:
    """Fetch + cache a URL's JSON.

    Returns None rather than raising if the request keeps failing, so one bad
    round can't kill a long backfill. A cached file is returned as-is, which is
    what makes re-runs cheap.
    """
    if cache_file.exists():
        try:
            return json.loads(cache_file.read_text())
        except json.JSONDecodeError:
            cache_file.unlink()  # corrupt cache, refetch

    resp = None
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, timeout=120)
        except requests.RequestException as exc:
            wait = min(5 * (attempt + 1), max_backoff)
            print(f"      {type(exc).__name__}, retrying in {wait}s...")
            time.sleep(wait)
            continue
        if resp.status_code in (429, 500, 502, 503, 504):
            wait = min(5 * (attempt + 1), max_backoff)
            print(f"      HTTP {resp.status_code}, waiting {wait}s...")
            time.sleep(wait)
            continue
        break

    if resp is None or not resp.ok:
        code = resp.status_code if resp is not None else "no response"
        print(f"      WARNING: giving up on {url} ({code})")
        return None

    data = resp.json()
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(data))
    time.sleep(sleep)
    return data


def write_csv(rows: list[dict], path: Path) -> None:
    """Write rows, replacing whatever was there."""
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)
    print(f"    wrote {len(rows):>6} rows -> {path.relative_to(ROOT)}")


def merge_csv(rows: list[dict], path: Path, keys: list[str]) -> None:
    """Merge rows into an existing CSV instead of truncating it.

    Fetching a single round must not wipe the rest of the season, so when the
    file already exists we concatenate, drop duplicates on `keys`, and re-sort.
    """
    if not rows:
        return
    df = pd.DataFrame(rows)
    if path.exists():
        try:
            old = pd.read_csv(path)
            df = pd.concat([old, df], ignore_index=True)
            have = [k for k in keys if k in df.columns]
            if have:
                df = df.drop_duplicates(subset=have, keep="last").sort_values(have)
        except (OSError, pd.errors.ParserError) as exc:
            print(f"    WARNING: couldn't merge into {path.name} ({exc}), overwriting")
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    print(f"    wrote {len(df):>6} rows -> {path.relative_to(ROOT)}")
