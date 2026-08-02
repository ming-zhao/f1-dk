"""Shared constants and helpers for the f1 project.

Single source of truth for name mappings, paths, and DK API access.
"""

from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent.parent
DK_SALARIES_DIR = ROOT / "data" / "raw" / "draftkings"
PROCESSED_DIR = ROOT / "data" / "processed"
RAW_DIR = ROOT / "data" / "raw"

# DK display name -> Jolpica driver code
NAME_TO_CODE = {
    "Max Verstappen": "VER", "Lando Norris": "NOR", "Oscar Piastri": "PIA",
    "Charles Leclerc": "LEC", "Lewis Hamilton": "HAM", "George Russell": "RUS",
    "Andrea Kimi Antonelli": "ANT", "Pierre Gasly": "GAS", "Esteban Ocon": "OCO",
    "Alexander Albon": "ALB", "Carlos Sainz Jr.": "SAI", "Fernando Alonso": "ALO",
    "Lance Stroll": "STR", "Nico Hulkenberg": "HUL", "Oliver Bearman": "BEA",
    "Franco Colapinto": "COL", "Valtteri Bottas": "BOT", "Sergio Perez": "PER",
    "Liam Lawson": "LAW", "Isack Hadjar": "HAD", "Gabriel Bortoleto": "BOR",
    "Arvid Lindblad": "LIN",
}

# DK constructor display name -> Jolpica constructor id, + short display name
TEAMS = {
    "Mercedes":             {"id": "mercedes",     "short": "Mercedes"},
    "Ferrari":              {"id": "ferrari",      "short": "Ferrari"},
    "McLaren":              {"id": "mclaren",      "short": "McLaren"},
    "Red Bull Racing":      {"id": "red_bull",     "short": "Red Bull"},
    "Racing Bulls F1 Team": {"id": "rb",           "short": "Racing Bulls"},
    "Alpine F1 Team":       {"id": "alpine",       "short": "Alpine"},
    "Aston Martin F1 Team": {"id": "aston_martin", "short": "Aston Martin"},
    "Haas F1 Team":         {"id": "haas",         "short": "Haas"},
    "Williams":             {"id": "williams",     "short": "Williams"},
    "Audi F1 Team":         {"id": "audi",         "short": "Audi"},
    "Cadillac":             {"id": "cadillac",     "short": "Cadillac"},
}
CONSTR_NAME_MAP = {name: t["id"] for name, t in TEAMS.items()}

# DK teamAbbreviation -> Jolpica constructor id (per-team, stable across seasons;
# driver-team pairings come from the salary CSV, never hardcode those)
DK_ABBREV_TO_ID = {
    "MERC": "mercedes", "FERR": "ferrari", "MCL": "mclaren", "RB": "red_bull",
    "VCARB": "rb", "ALPN": "alpine", "AM": "aston_martin", "HAAS": "haas",
    "WILL": "williams", "AUD": "audi", "CAD": "cadillac",
}

DK_HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
DK_LOBBY_URL = "https://www.draftkings.com/lobby/getcontests?sport=F1"
DK_DRAFTABLES_URL = "https://api.draftkings.com/draftgroups/v1/draftgroups/{}/draftables"


def fetch_dk_lobby() -> dict:
    resp = requests.get(DK_LOBBY_URL, headers=DK_HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json()


def latest_salary_file() -> Path:
    files = sorted(DK_SALARIES_DIR.glob("*.csv"))
    if not files:
        raise FileNotFoundError(
            "No salary files in data/raw/draftkings/. Run "
            "`python3 src/data/data_crawler.py --source draftkings` first.")
    return files[-1]


def load_raw(source: str, table: str, years=None):
    """Concatenate data/raw/<source>/<year>/<table>.csv across seasons.

    The crawler writes one CSV per source per year; downstream code usually wants
    every season in one frame. Pass `years` to limit it.
    """
    import pandas as pd

    src_dir = RAW_DIR / source
    if not src_dir.exists():
        raise FileNotFoundError(
            f"No crawled data at {src_dir}. Run "
            f"`python3 src/data/data_crawler.py --source {source}` first.")

    frames = []
    for year_dir in sorted(src_dir.iterdir()):
        if not year_dir.is_dir() or not year_dir.name.isdigit():
            continue
        if years and int(year_dir.name) not in years:
            continue
        f = year_dir / f"{table}.csv"
        if f.exists():
            frames.append(pd.read_csv(f))
    if not frames:
        raise FileNotFoundError(
            f"No {table}.csv under {src_dir}/<year>/. Run the crawler first.")
    return pd.concat(frames, ignore_index=True)
