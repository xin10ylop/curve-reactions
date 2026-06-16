"""curve-reactions CLI - fetch, analyse and report end to end.

Fetches the Treasury yield data once for the full range, then analyses several
named date windows (rate regimes and recent periods) by slicing that one dataset
in memory. Writes a full-history REPORT.md plus a single self-contained
report.html with a dropdown that switches between windows, and publishes a copy
to docs/index.html for GitHub Pages.

Examples
--------
    python main.py                      # default window 2018-01-01 .. today
    python main.py --refresh            # force re-download of all caches

Requires the FRED API key in the environment:
    export FRED_API_KEY=your_key_here   (free key: https://fred.stlouisfed.org/docs/api/api_key.html)
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging

import analysis
import charts
import config
import fetch_events
import fetch_yields
import report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Yield Curve Event Reaction Tracker - which scheduled US "
                    "releases move the Treasury curve, by how much, at which maturities."
    )
    parser.add_argument("--start", default=config.DEFAULT_START,
                        help="start date YYYY-MM-DD for the full-history window (default: 2018-01-01)")
    parser.add_argument("--end", default=dt.date.today().isoformat(),
                        help="end / as-of date YYYY-MM-DD (default: today)")
    parser.add_argument("--refresh", action="store_true",
                        help="force re-download of the FRED and calendar caches")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """Run the whole pipeline: yields -> events -> windowed analysis -> charts -> reports."""
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    log = logging.getLogger("main")
    horizon = min(args.end, dt.date.today().isoformat())

    log.info("[1/5] Fetching Treasury yields from FRED")
    yields = fetch_yields.fetch_yields(args.start, args.end, refresh=args.refresh)

    log.info("[2/5] Building event calendar (CPI / NFP / FOMC)")
    events = fetch_events.build_events(args.start, args.end, refresh=args.refresh)

    windows = config.resolve_windows(args.start, horizon)
    log.info("[3/5] Analysing %d windows", len(windows))
    window_results = analysis.run_windows(yields, events, windows)
    full_results = window_results.get("full") or analysis.run_analysis(yields, events)

    log.info("[4/5] Rendering charts (full-history PNGs + per-window base64)")
    charts.save_full_history_pngs(full_results)
    charts_by_window = {key: charts.charts_as_base64(res)
                        for key, res in window_results.items()}

    log.info("[5/5] Writing reports")
    report.write_reports(full_results, window_results, windows,
                         charts_by_window, args.start, horizon)

    # Publish the self-contained HTML to docs/ for GitHub Pages.
    config.DOCS_INDEX.parent.mkdir(parents=True, exist_ok=True)
    config.DOCS_INDEX.write_text(config.REPORT_HTML.read_text())
    log.info("Published %s -> %s", config.REPORT_HTML, config.DOCS_INDEX)

    log.info("Done. Windows rendered: %s", ", ".join(window_results))


if __name__ == "__main__":
    main()
