"""Project-wide constants and small helpers for curve-reactions.

Everything another module might need to tweak — series IDs, URLs, file
locations, analysis thresholds, the required FRED attribution text — lives
here so the rest of the code reads cleanly. No data is fetched or computed in
this module.
"""
from __future__ import annotations

import os
from datetime import date, timedelta
from pathlib import Path

# --- FRED: daily Treasury constant-maturity yields ---------------------------
FRED_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"

# FRED series id -> human-readable tenor label. Insertion order is display order.
YIELD_SERIES: dict[str, str] = {
    "DGS2": "2y",
    "DGS10": "10y",
    "DGS30": "30y",
}
TENORS: list[str] = list(YIELD_SERIES.values())  # ["2y", "10y", "30y"]

FRED_HOLIDAY_MARKER = "."  # FRED marks non-trading days / missing values with "."

# --- BLS: CPI and Employment Situation (NFP) release calendars ----------------
# BLS publishes one schedule page per calendar year listing every release with
# its actual published date. (The older per-release archive URLs now return 404,
# so the yearly schedule page is the live, official source.)
BLS_YEAR_SCHEDULE_URL = "https://www.bls.gov/schedule/{year}/home.htm"

# Exact <strong> release name on the BLS schedule -> our event type.
BLS_RELEASE_TO_EVENT: dict[str, str] = {
    "Consumer Price Index": "CPI",
    "Employment Situation": "NFP",
}

# --- Federal Reserve: FOMC decision calendar ---------------------------------
FOMC_CALENDAR_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
FOMC_HISTORICAL_URL = (
    "https://www.federalreserve.gov/monetarypolicy/fomchistorical{year}.htm"
)

# Meeting annotations that are NOT scheduled rate decisions and must be skipped.
FOMC_SKIP_ANNOTATIONS = ("cancelled", "unscheduled", "notation")

# Hardcoded fallback of *scheduled* FOMC decision dates (the second/decision day
# of each meeting). Used only if the Fed pages fail to fetch or parse to an
# implausible count. Verified against the Fed calendar; verify again if edited.
FOMC_FALLBACK: dict[int, list[str]] = {
    2024: ["2024-01-31", "2024-03-20", "2024-05-01", "2024-06-12",
           "2024-07-31", "2024-09-18", "2024-11-07", "2024-12-18"],
    2025: ["2025-01-29", "2025-03-19", "2025-05-07", "2025-06-18",
           "2025-07-30", "2025-09-17", "2025-10-29", "2025-12-10"],
    2026: ["2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17",
           "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09"],
}

# --- HTTP --------------------------------------------------------------------
# BLS and the Fed block default Python user agents, so present a real browser.
BROWSER_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Upgrade-Insecure-Requests": "1",
}
HTTP_TIMEOUT = 30  # seconds

# --- Analysis thresholds ------------------------------------------------------
BPS_PER_PCT = 100.0          # 1 percentage point = 100 basis points
REGIME_DEADBAND_BPS = 1.0    # moves smaller than this count as flat
EVENT_TYPES = ("CPI", "NFP", "FOMC")  # single-event categories
MULTI_TAG = "MULTI"
NORMAL_TAG = "NORMAL"
SMALL_SAMPLE_THRESHOLD = 12  # event-day count below which reaction multiples are flagged noisy

# Sanity-check bounds.
YIELD_MIN_PCT, YIELD_MAX_PCT = 0.0, 15.0
MAX_PLAUSIBLE_DAILY_MOVE_BPS = 100.0

# Plausible per-*full*-year event counts. The late-2025 US shutdown legitimately
# reduced BLS releases (11 instead of 12), and 2020 held 7 FOMC meetings (the
# March meeting was cancelled), so the bands are intentionally a little loose.
BLS_COUNT_PER_FULL_YEAR = (10, 13)
FOMC_COUNT_PER_FULL_YEAR = (7, 8)

# --- Dates -------------------------------------------------------------------
DEFAULT_START = "2018-01-01"


def resolve_windows(start: str, end: str) -> list[dict[str, str]]:
    """Return the ordered, named analysis windows as dicts of key/label/start/end.

    ``start`` and ``end`` are ISO dates bounding the full-history (default) window
    and the fetched data. The fixed "era" windows are constant; the rolling and
    "...-today" windows are derived from ``end`` (the as-of date). Every window is
    later sliced from one shared dataset, so this only defines date ranges.
    """
    end_date = date.fromisoformat(end)
    start_year = date.fromisoformat(start).year
    return [
        {"key": "full", "label": f"Full history ({start_year}–today)", "start": start, "end": end},
        {"key": "y2019", "label": "2019 mid-cycle cuts", "start": "2019-01-01", "end": "2019-12-31"},
        {"key": "y2020", "label": "2020 COVID shock", "start": "2020-01-01", "end": "2020-12-31"},
        {"key": "y2021", "label": "2021 inflation build-up", "start": "2021-01-01", "end": "2021-12-31"},
        {"key": "y2022_23", "label": "2022–23 hiking cycle", "start": "2022-01-01", "end": "2023-12-31"},
        {"key": "y2024", "label": "2024 pivot to cuts", "start": "2024-01-01", "end": "2024-12-31"},
        {"key": "y2025_today", "label": "2025–today (shutdown era)", "start": "2025-01-01", "end": end},
        {"key": "last12m", "label": "Last 12 months", "start": (end_date - timedelta(days=365)).isoformat(), "end": end},
        {"key": "last3m", "label": "Last 3 months", "start": (end_date - timedelta(days=90)).isoformat(), "end": end},
    ]

# --- File locations ----------------------------------------------------------
ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"
YIELDS_CSV = DATA_DIR / "yields.csv"
EVENTS_JSON = DATA_DIR / "events.json"

CHART_MEAN_MOVE = OUTPUT_DIR / "chart1_mean_move.png"
CHART_MULTIPLES = OUTPUT_DIR / "chart2_reaction_multiples.png"
CHART_BOX_2Y = OUTPUT_DIR / "chart3_box_2y.png"
CHART_SPREAD = OUTPUT_DIR / "chart4_2s10s_spread.png"
REPORT_MD = OUTPUT_DIR / "REPORT.md"
REPORT_HTML = OUTPUT_DIR / "report.html"
DOCS_INDEX = ROOT / "docs" / "index.html"  # published, self-contained GitHub Pages copy

# --- Attribution (required by FRED terms; do not change the wording) ----------
FRED_ATTRIBUTION = (
    "This product uses the FRED® API but is not endorsed or certified by "
    "the Federal Reserve Bank of St. Louis."
)
FRED_SOURCE_CITATION = (
    "Source: Board of Governors of the Federal Reserve System (US) and U.S. "
    "Department of the Treasury, retrieved from FRED, Federal Reserve Bank of "
    "St. Louis (series DGS2, DGS10, DGS30)."
)


def get_fred_api_key() -> str:
    """Return the FRED API key from the FRED_API_KEY environment variable.

    Raises SystemExit with a clear, actionable message if the variable is not
    set. The key is only ever read from the environment — never hardcoded,
    written to a file, or logged.
    """
    key = os.environ.get("FRED_API_KEY", "").strip()
    if not key:
        raise SystemExit(
            "FRED_API_KEY is not set.\n"
            "Get a free key at https://fred.stlouisfed.org/docs/api/api_key.html\n"
            "then run:  export FRED_API_KEY=your_key_here"
        )
    return key
