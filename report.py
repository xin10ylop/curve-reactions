"""Render output/REPORT.md and a self-contained output/report.html.

Both documents contain only derivative analysis (computed statistics) and the
four charts — never raw FRED observations. The HTML embeds the charts as base64
PNGs with inline CSS and no JavaScript, so it works as a single standalone file
that can be hosted as a static page (e.g. GitHub Pages) and linked on a CV.
"""
from __future__ import annotations

import base64
import datetime as dt
import logging
from pathlib import Path

import pandas as pd

import config

log = logging.getLogger(__name__)

_CHARTS = [
    (config.CHART_MEAN_MOVE, "Average daily move by event type and tenor",
     "Mean absolute close-to-close move (bp). Taller bars mean a larger typical reaction."),
    (config.CHART_MULTIPLES, "Reaction multiples",
     "Mean absolute move on event days divided by the normal-day average. Above 1.0x = the "
     "release reliably moves that tenor more than an average session."),
    (config.CHART_BOX_2Y, "Distribution of 2-year daily changes",
     "Signed daily 2-year changes (bp) by event type, NORMAL shown for comparison."),
    (config.CHART_SPREAD, "2s10s spread with FOMC decision days",
     "The 10y−2y spread over time; below zero the curve is inverted. Red dots are FOMC days."),
]

# Column headers for the reaction-statistics table (no "|" — it breaks MD tables).
_STATS_HEADERS = ["Event", "Tenor", "n", "Mean abs move (bp)",
                  "Median abs move (bp)", "Std dev (bp)", "Reaction multiple"]

_METHODOLOGY = [
    "Moves are end-of-day, close-to-close changes of FRED daily constant-maturity "
    "yields (DGS2/DGS10/DGS30), converted to basis points (1 percentage point = 100 bp).",
    "Absolute moves capture the *size* of the reaction, not its direction; the box plot "
    "and the regime table preserve direction.",
    "No surprise / forecast (consensus) data in v1 — the tool measures realized moves on "
    "release days, not moves conditioned on how far the print beat or missed expectations.",
    "Event dates are taken from official published calendars (BLS yearly schedules and the "
    "Federal Reserve FOMC calendar), including the late-2025 US shutdown-affected dates where "
    "CPI and the jobs report were delayed or merged. Days with more than one release are kept "
    "separate as MULTI; cancelled / unscheduled / notation-vote FOMC actions are excluded.",
    "A move on a release day is associated with that release, not proven to be caused by it; "
    "the NORMAL baseline excludes every event day.",
]


def _fmt(value: float, decimals: int = 1) -> str:
    """Format a number, or return an em dash for NaN/None."""
    if value is None or (isinstance(value, float) and value != value):
        return "—"
    return f"{value:.{decimals}f}"


def _combined_rows(results: dict) -> list[list[str]]:
    """Build the reaction-statistics table rows (one per event type × tenor)."""
    multiples = results["multiples"].set_index(["event", "tenor"])["multiple"]
    rows = []
    for _, r in results["stats"].iterrows():
        mult = multiples.get((r["event"], r["tenor"]))
        rows.append([
            r["event"], r["tenor"], str(int(r["n"])),
            _fmt(r["mean_abs_bp"]), _fmt(r["median_abs_bp"]), _fmt(r["std_bp"]),
            _fmt(mult, 2) + ("x" if mult is not None and mult == mult else ""),
        ])
    return rows


def _summary_paragraph(results: dict, start: str, end: str, n_days: int) -> str:
    """Plain-English summary with the headline numbers filled in programmatically."""
    headline = results["headline"]

    def mult(event: str, tenor: str) -> str:
        """Format an event/tenor reaction multiple as 'N.Nx' (or 'n/a')."""
        value = headline["multiples"].get(event, {}).get(tenor, float("nan"))
        return f"{value:.1f}x" if value == value else "n/a"

    top = headline.get("top_multiple")
    top_text = (
        f" The single largest reaction was on {top['event']} days at the {top['tenor']} "
        f"point — {top['multiple']:.1f}x a normal day's move." if top else ""
    )
    normal_n = headline["counts"].get(config.NORMAL_TAG, 0)
    return (
        f"Between {start} and {end} this tool examined {n_days:,} US Treasury trading days. "
        f"On CPI release days the 2-year yield moved {mult('CPI', '2y')} its typical daily "
        f"range; the jobs report (NFP) moved it {mult('NFP', '2y')}, and FOMC decision days "
        f"{mult('FOMC', '2y')}. At the long end the 30-year moved {mult('FOMC', '30y')} on "
        f"FOMC days.{top_text} A reaction multiple above 1.0x means the release reliably "
        f"moves that part of the curve more than an average session; multiples are measured "
        f"against a baseline of {normal_n:,} non-event (NORMAL) days."
    )


# --- Markdown ----------------------------------------------------------------

def _md_table(headers: list[str], rows: list[list[str]]) -> str:
    """Render a GitHub-flavoured Markdown table from headers and string rows."""
    lines = ["| " + " | ".join(headers) + " |",
             "| " + " | ".join("---" for _ in headers) + " |"]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join(lines)


def _regime_rows(regimes: pd.DataFrame) -> list[list[str]]:
    """Turn the event×regime count table into string rows for rendering."""
    return [[event] + [str(int(regimes.loc[event, col])) for col in regimes.columns]
            for event in regimes.index]


def _write_markdown(results: dict, start: str, end: str, generated: str) -> None:
    """Write output/REPORT.md (summary, tables, embedded charts, methodology)."""
    n_days = len(results["changes"])
    regimes = results["regimes"]
    stats_table = _md_table(_STATS_HEADERS, _combined_rows(results))
    regime_table = _md_table(["Event"] + list(regimes.columns), _regime_rows(regimes))
    chart_blocks = "\n\n".join(
        f"### {i}. {title}\n\n![{title}]({path.name})\n\n_{caption}_"
        for i, (path, title, caption) in enumerate(_CHARTS, start=1)
    )
    methodology = "\n".join(f"- {item}" for item in _METHODOLOGY)

    md = f"""# Yield Curve Event Reaction Tracker — Report

_Generated {generated}. Analysis window: {start} → {end} ({n_days:,} trading days)._

## Summary

{_summary_paragraph(results, start, end, n_days)}

## Reaction statistics

{stats_table}

_|Δ| = absolute daily change in basis points. Reaction multiple = mean |Δ| on that event type
÷ mean |Δ| on NORMAL days. MULTI days (more than one release) are excluded from single-event rows._

## Curve regime frequency (event days)

{regime_table}

_Dead-band = {config.REGIME_DEADBAND_BPS:.1f} bp: 2y/30y moves smaller than this count as flat._

## Charts

{chart_blocks}

_{config.FRED_SOURCE_CITATION}_

## Methodology & limitations

{methodology}

---

{config.FRED_ATTRIBUTION}
"""
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    config.REPORT_MD.write_text(md)
    log.info("Wrote %s", config.REPORT_MD)


# --- HTML --------------------------------------------------------------------

_CSS = """
:root { --ink:#1a1a1a; --muted:#666; --line:#e2e2e2; --accent:#1f4e79; }
* { box-sizing: border-box; }
body { max-width: 820px; margin: 0 auto; padding: 40px 22px 64px;
       font: 16px/1.6 -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
       color: var(--ink); background: #fff; }
h1 { font-size: 1.7rem; margin: 0 0 .2em; }
h2 { font-size: 1.25rem; margin: 2.2em 0 .6em; padding-bottom: .25em;
     border-bottom: 2px solid var(--accent); color: var(--accent); }
h3 { font-size: 1.02rem; margin: 1.6em 0 .5em; }
p.meta { color: var(--muted); margin-top: 0; }
table { border-collapse: collapse; width: 100%; margin: .6em 0 1em; font-size: .9rem; }
th, td { border: 1px solid var(--line); padding: 6px 10px; text-align: right; }
th { background: #f6f8fa; }
td:first-child, th:first-child, td:nth-child(2), th:nth-child(2) { text-align: left; }
figure { margin: 1em 0 1.4em; }
img { width: 100%; height: auto; border: 1px solid var(--line); border-radius: 4px; }
figcaption { color: var(--muted); font-size: .85rem; margin-top: .4em; }
ul { padding-left: 1.2em; }
li { margin: .35em 0; }
.note { color: var(--muted); font-size: .85rem; }
footer { margin-top: 2.5em; padding-top: 1em; border-top: 1px solid var(--line);
         color: var(--muted); font-size: .82rem; }
"""


def _html_table(headers: list[str], rows: list[list[str]]) -> str:
    """Render an HTML table from headers and string rows."""
    head = "".join(f"<th>{h}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _data_uri(path: Path) -> str:
    """Return a PNG file as an inline base64 data URI."""
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def _write_html(results: dict, start: str, end: str, generated: str) -> None:
    """Write the self-contained output/report.html (inline base64 charts, no JS)."""
    n_days = len(results["changes"])
    regimes = results["regimes"]
    stats_table = _html_table(_STATS_HEADERS, _combined_rows(results))
    regime_table = _html_table(["Event"] + list(regimes.columns), _regime_rows(results["regimes"]))
    figures = "".join(
        f"<figure><h3>{i}. {title}</h3>"
        f'<img alt="{title}" src="{_data_uri(path)}">'
        f"<figcaption>{caption}</figcaption></figure>"
        for i, (path, title, caption) in enumerate(_CHARTS, start=1)
    )
    methodology = "".join(f"<li>{item}</li>" for item in _METHODOLOGY)

    html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Yield Curve Event Reaction Tracker</title>
<style>{_CSS}</style>
</head>
<body>
<h1>Yield Curve Event Reaction Tracker</h1>
<p class="meta">Generated {generated} &middot; window {start} &rarr; {end} &middot; {n_days:,} trading days</p>

<h2>Summary</h2>
<p>{_summary_paragraph(results, start, end, n_days)}</p>

<h2>Reaction statistics</h2>
{stats_table}
<p class="note">|&Delta;| = absolute daily change in basis points. Reaction multiple = mean |&Delta;|
on that event type &divide; mean |&Delta;| on NORMAL days. MULTI days (more than one release) are
excluded from single-event rows.</p>

<h2>Curve regime frequency (event days)</h2>
{regime_table}
<p class="note">Dead-band = {config.REGIME_DEADBAND_BPS:.1f} bp: 2y/30y moves smaller than this count as flat.</p>

<h2>Charts</h2>
{figures}
<p class="note">{config.FRED_SOURCE_CITATION}</p>

<h2>Methodology &amp; limitations</h2>
<ul>{methodology}</ul>

<footer>{config.FRED_ATTRIBUTION}</footer>
</body>
</html>
"""
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    config.REPORT_HTML.write_text(html_doc)
    log.info("Wrote %s", config.REPORT_HTML)


def write_reports(results: dict, start: str, end: str) -> None:
    """Write both the Markdown and the self-contained HTML report."""
    generated = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    _write_markdown(results, start, end, generated)
    _write_html(results, start, end, generated)
