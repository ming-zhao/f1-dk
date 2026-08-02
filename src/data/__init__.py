"""Per-source data fetchers.

One module per source, each exposing a `fetch(year, only_round=None, **opts)`
function. `src/data_crawler.py` is the entry point that drives them.

    jolpica     1950-present. Race + qualifying results.
    openf1      2023-present. Per-lap timing, tyres, pit, overtakes, weather, telemetry.
    draftkings  Upcoming race only. Salaries — cannot be backfilled.
"""

from . import draftkings, jolpica, openf1  # noqa: F401

SOURCES = {
    "jolpica": jolpica,
    "openf1": openf1,
    "draftkings": draftkings,
}
