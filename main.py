"""curve-reactions CLI — fetch, analyse and report end to end.

Examples
--------
    python main.py                      # default window 2018-01-01 .. today
    python main.py --start 2020-01-01   # custom start date
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
        description="Yield Curve Event Reaction Tracker — which scheduled US "
                    "releases move the Treasury curve, by how much, at which maturities."
    )
    parser.add_argument("--start", default=config.DEFAULT_START,
                        help="start date YYYY-MM-DD (default: 2018-01-01)")
    parser.add_argument("--end", default=dt.date.today().isoformat(),
                        help="end date YYYY-MM-DD (default: today)")
    parser.add_argument("--refresh", action="store_true",
                        help="force re-download of the FRED and calendar caches")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """Run the whole pipeline: yields -> events -> analysis -> charts -> report."""
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

    log.info("[3/5] Running analysis")
    results = analysis.run_analysis(yields, events)

    log.info("[4/5] Rendering charts")
    charts.make_all(results)

    log.info("[5/5] Writing reports")
    report.write_reports(results, args.start, horizon)

    log.info("Done. Open %s in a browser, or read %s", config.REPORT_HTML, config.REPORT_MD)


if __name__ == "__main__":
    main()
