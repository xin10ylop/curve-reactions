"""Download daily Treasury constant-maturity yields from FRED and cache them.

Fetches DGS2, DGS10 and DGS30 (in percent), drops FRED holiday markers ("."),
merges to a single date-indexed DataFrame keeping only dates present in all
three series, validates the values, and caches the result to data/yields.csv.

The cache is written by this program and refreshed with --refresh; it is never
edited by hand and never committed (see .gitignore). FRED terms permit personal
educational use but forbid redistributing the raw data, so yields.csv stays
local.
"""
from __future__ import annotations

import logging

import pandas as pd
import requests

import config

log = logging.getLogger(__name__)


def _fetch_series(series_id: str, start: str, end: str, api_key: str) -> pd.Series:
    """Fetch one FRED series as a date-indexed float Series (holidays dropped).

    Parameters
    ----------
    series_id : FRED series identifier, e.g. ``"DGS10"``.
    start, end : ISO date strings (YYYY-MM-DD) bounding the observation window.
    api_key : FRED API key, read from the environment by the caller.
    """
    resp = requests.get(
        config.FRED_BASE_URL,
        params={
            "series_id": series_id,
            "api_key": api_key,
            "file_type": "json",
            "observation_start": start,
            "observation_end": end,
        },
        timeout=config.HTTP_TIMEOUT,
    )
    resp.raise_for_status()
    observations = resp.json().get("observations", [])

    dates: list[pd.Timestamp] = []
    values: list[float] = []
    holidays = 0
    for obs in observations:
        if obs["value"] == config.FRED_HOLIDAY_MARKER:
            holidays += 1
            continue
        dates.append(pd.Timestamp(obs["date"]))
        values.append(float(obs["value"]))

    series = pd.Series(
        values, index=pd.DatetimeIndex(dates, name="Date"), name=series_id
    )
    log.info(
        "FRED %s: %d observations, dropped %d holiday rows, kept %d",
        series_id, len(observations), holidays, len(series),
    )
    return series


def fetch_yields(start: str, end: str, refresh: bool = False) -> pd.DataFrame:
    """Return the merged DGS2/DGS10/DGS30 yield DataFrame, using the local cache.

    On a cache miss (or when ``refresh`` is True) every series is re-downloaded
    from FRED, merged on date (inner join — only dates present in all three are
    kept), validated, and written to data/yields.csv. Re-running is idempotent:
    the cache is overwritten cleanly.
    """
    if config.YIELDS_CSV.exists() and not refresh:
        log.info("Loading cached yields from %s", config.YIELDS_CSV)
        df = pd.read_csv(config.YIELDS_CSV, index_col="Date", parse_dates=["Date"])
    else:
        api_key = config.get_fred_api_key()
        log.info("Downloading yields from FRED (%s to %s)", start, end)
        series = [_fetch_series(sid, start, end, api_key) for sid in config.YIELD_SERIES]
        df = pd.concat(series, axis=1, join="inner").sort_index().dropna(how="any")
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        df.to_csv(config.YIELDS_CSV)
        log.info(
            "Merged yields: %d trading days kept (%s to %s), cached to %s",
            len(df), df.index.min().date(), df.index.max().date(), config.YIELDS_CSV,
        )

    _validate_yields(df)
    return df


def _validate_yields(df: pd.DataFrame) -> None:
    """Assert the cache has all series and that every yield is in [0, 15]%."""
    missing = [sid for sid in config.YIELD_SERIES if sid not in df.columns]
    if missing:
        raise ValueError(f"Cached yields missing expected columns: {missing}")
    if df.empty:
        raise ValueError("No overlapping trading days across DGS2/DGS10/DGS30.")

    lo, hi = config.YIELD_MIN_PCT, config.YIELD_MAX_PCT
    out_of_range = (df < lo) | (df > hi)
    n_bad = int(out_of_range.sum().sum())
    if n_bad:
        bad_col = out_of_range.any()[out_of_range.any()].index[0]
        bad_idx = out_of_range[bad_col].idxmax()
        raise ValueError(
            f"{n_bad} yield value(s) outside [{lo}, {hi}]% "
            f"(e.g. {bad_col} on {bad_idx.date()} = {df.loc[bad_idx, bad_col]:.2f}). "
            "Refusing to proceed."
        )
