"""Render output/REPORT.md (full history) and a self-contained output/report.html.

REPORT.md is the full-history report for the repo. report.html embeds every
named window (statistics table, regime table, four charts) and a dropdown that
switches between them with a few lines of inline vanilla JavaScript: no
frameworks, no external requests, no server. It works opened as a lone local
file and hosts as a static page. Both documents contain only derivative
analysis and charts, never raw FRED observations.
"""
from __future__ import annotations

import datetime as dt
import logging

import pandas as pd

import analysis
import charts
import config

log = logging.getLogger(__name__)

# Column headers for the reaction-statistics table (no "|" - it breaks MD tables).
_STATS_HEADERS = ["Event", "Tenor", "n", "Mean abs move (bp)",
                  "Median abs move (bp)", "Std dev (bp)", "Reaction multiple"]

# Full-history chart key -> PNG path that REPORT.md references by filename.
_FULL_PNG = {
    "mean_move": config.CHART_MEAN_MOVE,
    "multiples": config.CHART_MULTIPLES,
    "box_2y": config.CHART_BOX_2Y,
    "spread": config.CHART_SPREAD,
}

_METHODOLOGY = [
    "Moves are end-of-day, close-to-close changes of FRED daily constant-maturity "
    "yields (DGS2/DGS10/DGS30), converted to basis points (1 percentage point = 100 bp).",
    "Absolute moves capture the *size* of the reaction, not its direction; the box plot "
    "and the regime table preserve direction.",
    "No surprise / forecast (consensus) data in v1 - the tool measures realized moves on "
    "release days, not moves conditioned on how far the print beat or missed expectations.",
    "Event dates are taken from official published calendars (BLS yearly schedules and the "
    "Federal Reserve FOMC calendar), including the late-2025 US shutdown-affected dates where "
    "CPI and the jobs report were delayed or merged. Days with more than one release are kept "
    "separate as MULTI; cancelled / unscheduled / notation-vote FOMC actions are excluded.",
    "A move on a release day is associated with that release, not proven to be caused by it; "
    "the NORMAL baseline excludes every event day. Short windows hold few releases, so their "
    "reaction multiples are noisy - tables flag any event type with fewer than "
    f"{config.SMALL_SAMPLE_THRESHOLD} occurrences.",
]


def _fmt(value: float, decimals: int = 1) -> str:
    """Format a number, or return an em dash for NaN/None."""
    if value is None or (isinstance(value, float) and value != value):
        return "—"
    return f"{value:.{decimals}f}"


def _combined_rows(results: dict) -> list[list[str]]:
    """Build the reaction-statistics table rows (one per event type x tenor)."""
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
        f"Between {start} and {end} this window covers {n_days:,} US Treasury trading days. "
        f"On CPI release days the 2-year yield moved {mult('CPI', '2y')} its typical daily "
        f"range; the jobs report (NFP) moved it {mult('NFP', '2y')}, and FOMC decision days "
        f"{mult('FOMC', '2y')}. At the long end the 30-year moved {mult('FOMC', '30y')} on "
        f"FOMC days.{top_text} A reaction multiple above 1.0x means the release reliably "
        f"moves that part of the curve more than an average session; multiples are measured "
        f"against a baseline of {normal_n:,} non-event (NORMAL) days."
    )


def _regime_rows(regimes: pd.DataFrame) -> list[list[str]]:
    """Turn the event x regime count table into string rows for rendering."""
    return [[event] + [str(int(regimes.loc[event, col])) for col in regimes.columns]
            for event in regimes.index]


# --- Markdown (full history) -------------------------------------------------

def _md_table(headers: list[str], rows: list[list[str]]) -> str:
    """Render a GitHub-flavoured Markdown table from headers and string rows."""
    lines = ["| " + " | ".join(headers) + " |",
             "| " + " | ".join("---" for _ in headers) + " |"]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join(lines)


def _write_markdown(results: dict, start: str, end: str, generated: str) -> None:
    """Write output/REPORT.md (full history): summary, tables, charts, methodology."""
    n_days = len(results["changes"])
    regimes = results["regimes"]
    stats_table = _md_table(_STATS_HEADERS, _combined_rows(results))
    regime_table = _md_table(["Event"] + list(regimes.columns), _regime_rows(regimes))
    chart_blocks = "\n\n".join(
        f"### {i}. {title}\n\n![{title}]({_FULL_PNG[name].name})\n\n_{caption}_"
        for i, (name, title, caption) in enumerate(charts.CHART_META, start=1)
    )
    methodology = "\n".join(f"- {item}" for item in _METHODOLOGY)

    md = f"""# Yield Curve Event Reaction Tracker — Report

_Generated {generated}. Analysis window: {start} → {end} ({n_days:,} trading days)._

_An interactive version with selectable date windows (2019, 2020, the 2022–23 hiking
cycle, last 12 months, and more) is in `report.html`._

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


# --- HTML (all windows, switchable) ------------------------------------------

_CSS = """
:root { --ink:#1a1a1a; --muted:#666; --line:#e2e2e2; --accent:#1f4e79; }
* { box-sizing: border-box; }
body { max-width: 860px; margin: 0 auto; padding: 40px 22px 64px;
       font: 16px/1.6 -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
       color: var(--ink); background: #fff; }
h1 { font-size: 1.7rem; margin: 0 0 .2em; }
h2 { font-size: 1.3rem; margin: 1.6em 0 .5em; color: var(--accent); }
h3 { font-size: 1.05rem; margin: 1.5em 0 .5em; padding-bottom: .2em; border-bottom: 1px solid var(--line); }
h4 { font-size: .98rem; margin: 1.3em 0 .4em; }
p.meta { color: var(--muted); margin-top: 0; }
.controls { position: sticky; top: 0; background: #fff; padding: 14px 0; margin: 1em 0 1.4em;
            border-bottom: 2px solid var(--accent); z-index: 5; }
select { font-size: 1rem; padding: 5px 9px; border: 1px solid var(--line); border-radius: 5px; }
table { border-collapse: collapse; width: 100%; margin: .6em 0 1em; font-size: .9rem; }
th, td { border: 1px solid var(--line); padding: 6px 10px; text-align: right; }
th { background: #f6f8fa; }
td:first-child, th:first-child, td:nth-child(2), th:nth-child(2) { text-align: left; }
figure { margin: 1em 0 1.4em; }
img { width: 100%; height: auto; border: 1px solid var(--line); border-radius: 4px; }
figcaption { color: var(--muted); font-size: .85rem; margin-top: .4em; }
.note { color: var(--muted); font-size: .85rem; }
.smallnote { background: #fff7e6; border: 1px solid #f0c36d; border-radius: 4px;
             padding: 7px 11px; font-size: .87rem; color: #7a5b00; margin: .6em 0; }
ul { padding-left: 1.2em; }
li { margin: .35em 0; }
footer { margin-top: 2.5em; padding-top: 1em; border-top: 1px solid var(--line);
         color: var(--muted); font-size: .82rem; }
"""


def _html_table(headers: list[str], rows: list[list[str]]) -> str:
    """Render an HTML table from headers and string rows."""
    head = "".join(f"<th>{h}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _window_section(result: dict, charts_b64: dict[str, str], is_default: bool) -> str:
    """Build one switchable window section (heading, caption, tables, charts)."""
    window = result["window"]
    start, end, label, key = window["start"], window["end"], window["label"], window["key"]
    n_days = len(result["changes"])

    small = analysis.small_sample_types(result["stats"], config.SMALL_SAMPLE_THRESHOLD)
    caption = ""
    if small:
        listed = ", ".join(f"{event} n={n}" for event, n in small)
        caption = (f'<p class="smallnote">Small sample ({listed}): reaction multiples here '
                   f'are noisy, interpret with caution.</p>')

    stats_table = _html_table(_STATS_HEADERS, _combined_rows(result))
    regimes = result["regimes"]
    regime_table = _html_table(["Event"] + list(regimes.columns), _regime_rows(regimes))
    figures = "".join(
        f'<figure><h4>{i}. {title}</h4>'
        f'<img alt="{title}" src="{charts_b64[name]}">'
        f"<figcaption>{cap}</figcaption></figure>"
        for i, (name, title, cap) in enumerate(charts.CHART_META, start=1)
    )
    style = "" if is_default else ' style="display:none"'
    return (
        f'<section class="window" id="win-{key}"{style}>'
        f"<h2>{label}</h2>"
        f'<p class="meta">{start} to {end} &middot; {n_days:,} trading days</p>'
        f"{caption}"
        f"<p>{_summary_paragraph(result, start, end, n_days)}</p>"
        f"<h3>Reaction statistics</h3>{stats_table}"
        f'<p class="note">|&Delta;| = absolute daily change in bp. Reaction multiple = mean '
        f"|&Delta;| on that event type &divide; mean |&Delta;| on NORMAL days. MULTI days "
        f"(more than one release) are excluded from single-event rows.</p>"
        f"<h3>Curve regime frequency</h3>{regime_table}"
        f'<p class="note">Dead-band = {config.REGIME_DEADBAND_BPS:.1f} bp: 2y/30y moves '
        f"smaller than this count as flat.</p>"
        f"<h3>Charts</h3>{figures}"
        f"</section>"
    )


def _write_html(window_results: dict, windows: list[dict],
                charts_by_window: dict, generated: str) -> None:
    """Write the self-contained, switchable multi-window output/report.html."""
    ordered = [w for w in windows if w["key"] in window_results]
    options = "".join(
        f'<option value="{w["key"]}">{w["label"]}</option>' for w in ordered
    )
    sections = "".join(
        _window_section(window_results[w["key"]], charts_by_window[w["key"]],
                        is_default=(i == 0))
        for i, w in enumerate(ordered)
    )

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
<p class="meta">Generated {generated} UTC</p>
<p>Which scheduled US releases (CPI, the jobs report, FOMC decisions) move the Treasury
curve, by how much, and at which maturities. Use the dropdown to switch between rate
regimes and recent periods. Short windows hold only a few releases, so their reaction
multiples are noisy; a caption flags any window where that applies.</p>

<div class="controls">
<label for="window-select"><strong>Choose a period:</strong></label>
<select id="window-select" onchange="showWindow(this.value)">{options}</select>
</div>

{sections}

<footer>
<p>{config.FRED_SOURCE_CITATION}</p>
<p>{config.FRED_ATTRIBUTION}</p>
</footer>

<script>
function showWindow(key) {{
  var sections = document.querySelectorAll('.window');
  for (var i = 0; i < sections.length; i++) {{ sections[i].style.display = 'none'; }}
  var chosen = document.getElementById('win-' + key);
  if (chosen) {{ chosen.style.display = ''; }}
}}
</script>
</body>
</html>
"""
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    config.REPORT_HTML.write_text(html_doc)
    log.info("Wrote %s (%d windows, %.1f MB)",
             config.REPORT_HTML, len(ordered), len(html_doc) / 1e6)


def write_reports(full_results: dict, window_results: dict, windows: list[dict],
                  charts_by_window: dict, start: str, end: str) -> None:
    """Write the full-history Markdown report and the multi-window HTML report."""
    generated = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    _write_markdown(full_results, start, end, generated)
    _write_html(window_results, windows, charts_by_window, generated)
