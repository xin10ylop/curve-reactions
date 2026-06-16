"""Turn cached yields and events into the statistics the report needs.

Pure, deterministic transforms: daily basis-point changes per tenor, the 2s10s
and 2s30s curve spreads, per-event reaction statistics, reaction multiples
versus a clean NORMAL baseline, and a steepener/flattener regime classification.
"""
from __future__ import annotations

import logging

import pandas as pd

import config

log = logging.getLogger(__name__)

# Regime labels, in a fixed display order.
REGIMES = ["bull steepener", "bull flattener", "bear flattener",
           "bear steepener", "mixed/flat"]


def compute_changes(yields: pd.DataFrame) -> pd.DataFrame:
    """Return yields, daily bp changes per tenor, and the curve spreads.

    Daily change = (today − previous trading day) in basis points. The yields
    frame holds only trading days, so ``.diff()`` already compares against the
    previous *available* trading day. Adds 2s10s and 2s30s spreads (bp) and
    their daily changes. Absolute moves >= 100 bp are logged as a data red flag
    (not raised — a genuine large move should not crash the pipeline).
    """
    out = pd.DataFrame(index=yields.index)
    for series_id, tenor in config.YIELD_SERIES.items():
        out[f"{tenor}_yield"] = yields[series_id]
        out[f"{tenor}_chg"] = yields[series_id].diff() * config.BPS_PER_PCT
    out["2s10s"] = (yields["DGS10"] - yields["DGS2"]) * config.BPS_PER_PCT
    out["2s30s"] = (yields["DGS30"] - yields["DGS2"]) * config.BPS_PER_PCT
    out["2s10s_chg"] = out["2s10s"].diff()
    out["2s30s_chg"] = out["2s30s"].diff()
    _flag_large_moves(out)
    return out


def _flag_large_moves(changes: pd.DataFrame) -> None:
    """Log (do not raise) any absolute daily move >= the plausible limit."""
    limit = config.MAX_PLAUSIBLE_DAILY_MOVE_BPS
    for tenor in config.TENORS:
        col = changes[f"{tenor}_chg"]
        for day, value in col[col.abs() >= limit].items():
            log.warning("Large %s move on %s: %+.1f bp (>= %.0f bp limit)",
                        tenor, day.date(), value, limit)


def tag_days(changes: pd.DataFrame, events: dict) -> pd.Series:
    """Label each trading day CPI / NFP / FOMC / MULTI / NORMAL.

    A day with two or more events becomes MULTI so it cannot contaminate the
    single-event averages. Event dates absent from the yield data (a market
    holiday or a missing print) are logged and skipped — never reassigned.
    """
    event_map: dict[str, list[str]] = events["events"]
    trading_days = {ts.date().isoformat() for ts in changes.index}
    for iso, types in event_map.items():
        if iso not in trading_days:
            log.info("Event %s on %s not in yield data (holiday/missing) — skipped",
                     "+".join(types), iso)

    tags: list[str] = []
    for ts in changes.index:
        types = event_map.get(ts.date().isoformat(), [])
        if not types:
            tags.append(config.NORMAL_TAG)
        elif len(types) == 1:
            tags.append(types[0])
        else:
            tags.append(config.MULTI_TAG)
    return pd.Series(tags, index=changes.index, name="tag")


def reaction_stats(changes: pd.DataFrame, tags: pd.Series) -> pd.DataFrame:
    """Per (event type, tenor): count, mean |Δ|, median |Δ|, std(Δ), all in bp.

    Computed on single-event days only. NORMAL is the baseline; it already
    excludes every event day (including MULTI).
    """
    rows = []
    for category in list(config.EVENT_TYPES) + [config.NORMAL_TAG]:
        selected = changes[tags == category]
        for tenor in config.TENORS:
            col = selected[f"{tenor}_chg"].dropna()
            rows.append({
                "event": category,
                "tenor": tenor,
                "n": int(col.shape[0]),
                "mean_abs_bp": float(col.abs().mean()) if len(col) else float("nan"),
                "median_abs_bp": float(col.abs().median()) if len(col) else float("nan"),
                "std_bp": float(col.std()) if len(col) > 1 else float("nan"),
            })
    return pd.DataFrame(rows)


def reaction_multiples(stats: pd.DataFrame) -> pd.DataFrame:
    """mean |Δ| on each event type ÷ mean |Δ| on NORMAL days, per tenor."""
    normal = stats[stats["event"] == config.NORMAL_TAG].set_index("tenor")["mean_abs_bp"]
    rows = []
    for event in config.EVENT_TYPES:
        sub = stats[stats["event"] == event].set_index("tenor")
        for tenor in config.TENORS:
            base = normal.get(tenor, float("nan"))
            mean_abs = sub.loc[tenor, "mean_abs_bp"] if tenor in sub.index else float("nan")
            multiple = mean_abs / base if base else float("nan")
            rows.append({"event": event, "tenor": tenor, "multiple": float(multiple)})
    return pd.DataFrame(rows)


def classify_regimes(changes: pd.DataFrame, tags: pd.Series) -> pd.DataFrame:
    """Classify each event day's curve move and return an event × regime table.

    Uses the 2y and 30y daily changes with a ±dead-band (moves within it are
    flat):

      * both down, 2y falls more  -> bull steepener; 30y falls more -> bull flattener
      * both up,   2y rises more  -> bear flattener; 30y rises more -> bear steepener
      * mixed-direction or both inside the dead-band -> mixed/flat
    """
    deadband = config.REGIME_DEADBAND_BPS

    def regime(d2: float, d30: float) -> str:
        """Map a (2y, 30y) bp-change pair to a regime label, applying the dead-band."""
        down2, down30 = d2 < -deadband, d30 < -deadband
        up2, up30 = d2 > deadband, d30 > deadband
        if down2 and down30:
            return "bull steepener" if abs(d2) > abs(d30) else "bull flattener"
        if up2 and up30:
            return "bear flattener" if abs(d2) > abs(d30) else "bear steepener"
        return "mixed/flat"

    categories = list(config.EVENT_TYPES) + [config.MULTI_TAG]
    table = pd.DataFrame(0, index=categories, columns=REGIMES)
    for ts in changes.index:
        category = tags.loc[ts]
        if category == config.NORMAL_TAG or category not in table.index:
            continue
        d2, d30 = changes.loc[ts, "2y_chg"], changes.loc[ts, "30y_chg"]
        if pd.isna(d2) or pd.isna(d30):
            continue
        # Round away floating-point noise (a 1 bp move can surface as
        # -1.0000000000000231) so the dead-band comparison is deterministic at
        # the boundary instead of being decided by representation error.
        table.loc[category, regime(round(d2, 6), round(d30, 6))] += 1
    table.index.name = "event"
    return table


def _headline_numbers(stats: pd.DataFrame, multiples: pd.DataFrame,
                      tags: pd.Series) -> dict:
    """Extract a few figures for the report's plain-English summary."""
    counts = tags.value_counts().to_dict()
    mult = multiples.set_index(["event", "tenor"])["multiple"]
    headline: dict = {"counts": counts, "multiples": {}}
    for event in config.EVENT_TYPES:
        headline["multiples"][event] = {
            tenor: float(mult.get((event, tenor), float("nan"))) for tenor in config.TENORS
        }
    valid = multiples.dropna(subset=["multiple"])
    if not valid.empty:
        top = valid.loc[valid["multiple"].idxmax()]
        headline["top_multiple"] = {
            "event": top["event"], "tenor": top["tenor"], "multiple": float(top["multiple"])
        }
    return headline


def _analyze_from(changes: pd.DataFrame, tags: pd.Series) -> dict:
    """Assemble statistics, multiples, regimes and headline figures from one slice."""
    stats = reaction_stats(changes, tags)
    multiples = reaction_multiples(stats)
    regimes = classify_regimes(changes, tags)
    headline = _headline_numbers(stats, multiples, tags)
    return {
        "changes": changes,
        "tags": tags,
        "stats": stats,
        "multiples": multiples,
        "regimes": regimes,
        "headline": headline,
    }


def run_analysis(yields: pd.DataFrame, events: dict) -> dict:
    """Run the full analysis on every supplied trading day (used for REPORT.md)."""
    changes = compute_changes(yields)
    tags = tag_days(changes, events)
    log.info("Analysis: %d trading days; tag counts %s",
             len(changes), tags.value_counts().to_dict())
    return _analyze_from(changes, tags)


def run_windows(yields: pd.DataFrame, events: dict,
                windows: list[dict]) -> dict[str, dict]:
    """Analyse each named window by slicing one shared changes/tags frame.

    Daily changes are computed once on the full dataset, so an event on a
    window's first day still references its true previous trading day. Each
    window's statistics are then computed only on the rows within its date
    range. Methodology is identical to ``run_analysis``; only the row subset
    differs. Empty windows are skipped with a warning.
    """
    changes = compute_changes(yields)
    tags = tag_days(changes, events)
    results: dict[str, dict] = {}
    for window in windows:
        start, end = pd.Timestamp(window["start"]), pd.Timestamp(window["end"])
        mask = (changes.index >= start) & (changes.index <= end)
        if not bool(mask.any()):
            log.warning("Window '%s' (%s..%s) has no trading days; skipping",
                        window["key"], window["start"], window["end"])
            continue
        result = _analyze_from(changes.loc[mask], tags.loc[mask])
        result["window"] = window
        results[window["key"]] = result
        log.info("Window '%s': %d trading days", window["key"], int(mask.sum()))
    return results


def small_sample_types(stats: pd.DataFrame, threshold: int) -> list[tuple[str, int]]:
    """Return (event_type, n) for single-event types with fewer than ``threshold`` days."""
    out: list[tuple[str, int]] = []
    for event in config.EVENT_TYPES:
        sub = stats[(stats["event"] == event) & (stats["tenor"] == config.TENORS[0])]
        if not sub.empty:
            n = int(sub["n"].iloc[0])
            if n < threshold:
                out.append((event, n))
    return out
