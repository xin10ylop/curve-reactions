"""Build the four report charts as matplotlib figures.

Each ``chart_*`` function returns a Figure; callers either save it to a PNG (for
REPORT.md) or encode it to a base64 data URI (for the self-contained HTML, where
every window's charts are embedded inline). Every chart works in basis points,
labels its axes, shows sample sizes (n=...), and prints the required FRED source
citation. Charts of the derived series are permitted under FRED terms with
attribution; the raw observations are never embedded.
"""
from __future__ import annotations

import base64
import io
import logging
from typing import TYPE_CHECKING

import matplotlib
matplotlib.use("Agg")  # headless, deterministic rendering — no display needed
import matplotlib.pyplot as plt  # noqa: E402  (must follow backend selection)
import pandas as pd  # noqa: E402

import config  # noqa: E402

if TYPE_CHECKING:  # type-only imports for annotations; no runtime import cost
    from matplotlib.axes import Axes
    from matplotlib.figure import Figure

log = logging.getLogger(__name__)

_TENOR_COLORS = {"2y": "#1f77b4", "10y": "#ff7f0e", "30y": "#2ca02c"}

# chart key -> (title, caption) used by the report for headings and alt text.
CHART_META = [
    ("mean_move", "Average daily move by event type and tenor",
     "Mean absolute close-to-close move (bp). Taller bars mean a larger typical reaction."),
    ("multiples", "Reaction multiples",
     "Mean absolute move on event days divided by the normal-day average. Above 1.0x = the "
     "release reliably moves that tenor more than an average session."),
    ("box_2y", "Distribution of 2-year daily changes",
     "Signed daily 2-year changes (bp) by event type, NORMAL shown for comparison."),
    ("spread", "2s10s spread with FOMC decision days",
     "The 10y-2y spread over time; below zero the curve is inverted. Red dots are FOMC days."),
]


def _citation(fig: Figure) -> None:
    """Print the required FRED source citation under a figure."""
    fig.text(0.5, 0.01, config.FRED_SOURCE_CITATION, ha="center", va="bottom",
             fontsize=6.5, color="#555555", wrap=True)


def _grouped_bars(ax: Axes, pivot: pd.DataFrame) -> None:
    """Draw one bar per tenor for each row of ``pivot`` (index = event type)."""
    width = 0.25
    positions = range(len(pivot.index))
    for offset, tenor in enumerate(config.TENORS):
        ax.bar([p + (offset - 1) * width for p in positions], pivot[tenor],
               width, label=tenor, color=_TENOR_COLORS[tenor])
    ax.set_xticks(list(positions))


def chart_mean_move(stats: pd.DataFrame, tags: pd.Series) -> Figure:
    """Chart 1 - grouped bars of mean absolute daily move by event type/tenor."""
    counts = tags.value_counts().to_dict()
    events = list(config.EVENT_TYPES) + [config.NORMAL_TAG]
    pivot = (stats.pivot(index="event", columns="tenor", values="mean_abs_bp")
             .reindex(events)[config.TENORS])

    fig, ax = plt.subplots(figsize=(8, 5))
    _grouped_bars(ax, pivot)
    ax.set_xticklabels([f"{e}\n(n={counts.get(e, 0)})" for e in events])
    ax.set_xlabel("Event type")
    ax.set_ylabel("Mean absolute daily move (bp)")
    ax.set_title("Average daily Treasury move by event type and tenor")
    ax.legend(title="Tenor")
    ax.grid(axis="y", alpha=0.3)
    _citation(fig)
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    return fig


def chart_multiples(multiples: pd.DataFrame, tags: pd.Series) -> Figure:
    """Chart 2 - reaction multiples by event type/tenor with a 1.0x reference."""
    counts = tags.value_counts().to_dict()
    pivot = (multiples.pivot(index="event", columns="tenor", values="multiple")
             .reindex(config.EVENT_TYPES)[config.TENORS])

    fig, ax = plt.subplots(figsize=(8, 5))
    _grouped_bars(ax, pivot)
    ax.axhline(1.0, color="black", linestyle="--", linewidth=1,
               label="1.0x (normal day)")
    ax.set_xticklabels([f"{e}\n(n={counts.get(e, 0)})" for e in config.EVENT_TYPES])
    ax.set_xlabel("Event type")
    ax.set_ylabel("Reaction multiple (x normal-day mean abs move)")
    ax.set_title("How much bigger are moves on event days? (reaction multiple)")
    ax.legend(title="Tenor")
    ax.grid(axis="y", alpha=0.3)
    _citation(fig)
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    return fig


def chart_box_2y(changes: pd.DataFrame, tags: pd.Series) -> Figure:
    """Chart 3 - box plots of signed daily 2y changes by event type (incl. NORMAL).

    Categories with no observations in this window are skipped so the box plot
    never receives an empty group.
    """
    fig, ax = plt.subplots(figsize=(8, 5))
    data, labels = [], []
    for category in list(config.EVENT_TYPES) + [config.NORMAL_TAG]:
        values = changes.loc[tags == category, "2y_chg"].dropna()
        if len(values) == 0:
            continue
        data.append(values.to_numpy())
        labels.append(f"{category}\n(n={len(values)})")

    if data:
        ax.boxplot(data, tick_labels=labels, showfliers=True)
    else:
        ax.text(0.5, 0.5, "no data in window", ha="center", va="center",
                transform=ax.transAxes)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_xlabel("Event type")
    ax.set_ylabel("Daily 2-year yield change (bp, signed)")
    ax.set_title("Distribution of 2-year daily changes by event type")
    ax.grid(axis="y", alpha=0.3)
    _citation(fig)
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    return fig


def chart_spread(changes: pd.DataFrame, tags: pd.Series) -> Figure:
    """Chart 4 - 2s10s spread over time, FOMC decision days marked, zero line."""
    spread = changes["2s10s"]
    fomc_days = changes.index[tags == "FOMC"]

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(spread.index, spread.to_numpy(), color="#1f77b4", linewidth=1,
            label="2s10s spread")
    ax.scatter(fomc_days, spread.loc[fomc_days], color="red", s=18, zorder=3,
               label=f"FOMC decision (n={len(fomc_days)})")
    ax.axhline(0, color="black", linewidth=0.9, label="0 bp (inversion line)")
    ax.set_xlabel("Date")
    ax.set_ylabel("2s10s spread (bp)  =  10y - 2y")
    ax.set_title("US 2s10s Treasury curve spread with FOMC decision days")
    ax.legend(loc="best")
    ax.grid(alpha=0.3)
    _citation(fig)
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    return fig


def _build_charts(results: dict) -> list[tuple[str, "Figure"]]:
    """Build the four figures for one analysis result; caller saves or encodes them."""
    return [
        ("mean_move", chart_mean_move(results["stats"], results["tags"])),
        ("multiples", chart_multiples(results["multiples"], results["tags"])),
        ("box_2y", chart_box_2y(results["changes"], results["tags"])),
        ("spread", chart_spread(results["changes"], results["tags"])),
    ]


def save_full_history_pngs(results: dict) -> None:
    """Save the four full-history charts as PNG files for REPORT.md to reference."""
    paths = {
        "mean_move": config.CHART_MEAN_MOVE,
        "multiples": config.CHART_MULTIPLES,
        "box_2y": config.CHART_BOX_2Y,
        "spread": config.CHART_SPREAD,
    }
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, fig in _build_charts(results):
        fig.savefig(paths[name], dpi=130)
        plt.close(fig)
        log.info("Wrote %s", paths[name])


def charts_as_base64(results: dict) -> dict[str, str]:
    """Render one window's four charts to base64 PNG data URIs for inline embedding."""
    out: dict[str, str] = {}
    for name, fig in _build_charts(results):
        buffer = io.BytesIO()
        fig.savefig(buffer, format="png", dpi=130)
        plt.close(fig)
        out[name] = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")
    return out
