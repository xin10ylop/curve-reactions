"""Render the four report charts as labelled PNGs in output/.

Every chart works in basis points, labels its axes, shows sample sizes (n=...),
and prints the required FRED source citation underneath. Charts (graphs) of the
derived series are permitted under FRED terms with attribution; the underlying
raw observations are never embedded.
"""
from __future__ import annotations

import logging

import matplotlib
matplotlib.use("Agg")  # headless, deterministic rendering — no display needed
import matplotlib.pyplot as plt  # noqa: E402  (must follow backend selection)
import pandas as pd  # noqa: E402

import config  # noqa: E402

log = logging.getLogger(__name__)

_TENOR_COLORS = {"2y": "#1f77b4", "10y": "#ff7f0e", "30y": "#2ca02c"}


def _citation(fig) -> None:
    """Print the required FRED source citation under a figure."""
    fig.text(0.5, 0.01, config.FRED_SOURCE_CITATION, ha="center", va="bottom",
             fontsize=6.5, color="#555555", wrap=True)


def _grouped_bars(ax, pivot: pd.DataFrame) -> None:
    """Draw one bar per tenor for each row of ``pivot`` (index = event type)."""
    width = 0.25
    positions = range(len(pivot.index))
    for offset, tenor in enumerate(config.TENORS):
        ax.bar([p + (offset - 1) * width for p in positions], pivot[tenor],
               width, label=tenor, color=_TENOR_COLORS[tenor])
    ax.set_xticks(list(positions))


def chart_mean_move(stats: pd.DataFrame, tags: pd.Series) -> None:
    """Chart 1 — grouped bars of mean absolute daily move by event type/tenor."""
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
    fig.savefig(config.CHART_MEAN_MOVE, dpi=130)
    plt.close(fig)
    log.info("Wrote %s", config.CHART_MEAN_MOVE)


def chart_multiples(multiples: pd.DataFrame, tags: pd.Series) -> None:
    """Chart 2 — reaction multiples by event type/tenor with a 1.0x reference."""
    counts = tags.value_counts().to_dict()
    pivot = (multiples.pivot(index="event", columns="tenor", values="multiple")
             .reindex(config.EVENT_TYPES)[config.TENORS])

    fig, ax = plt.subplots(figsize=(8, 5))
    _grouped_bars(ax, pivot)
    ax.axhline(1.0, color="black", linestyle="--", linewidth=1,
               label="1.0x (normal day)")
    ax.set_xticklabels([f"{e}\n(n={counts.get(e, 0)})" for e in config.EVENT_TYPES])
    ax.set_xlabel("Event type")
    ax.set_ylabel("Reaction multiple (× normal-day mean abs move)")
    ax.set_title("How much bigger are moves on event days? (reaction multiple)")
    ax.legend(title="Tenor")
    ax.grid(axis="y", alpha=0.3)
    _citation(fig)
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    fig.savefig(config.CHART_MULTIPLES, dpi=130)
    plt.close(fig)
    log.info("Wrote %s", config.CHART_MULTIPLES)


def chart_box_2y(changes: pd.DataFrame, tags: pd.Series) -> None:
    """Chart 3 — box plots of signed daily 2y changes by event type (incl. NORMAL)."""
    categories = list(config.EVENT_TYPES) + [config.NORMAL_TAG]
    data, labels = [], []
    for category in categories:
        values = changes.loc[tags == category, "2y_chg"].dropna()
        data.append(values.to_numpy())
        labels.append(f"{category}\n(n={len(values)})")

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.boxplot(data, tick_labels=labels, showfliers=True)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_xlabel("Event type")
    ax.set_ylabel("Daily 2-year yield change (bp, signed)")
    ax.set_title("Distribution of 2-year daily changes by event type")
    ax.grid(axis="y", alpha=0.3)
    _citation(fig)
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    fig.savefig(config.CHART_BOX_2Y, dpi=130)
    plt.close(fig)
    log.info("Wrote %s", config.CHART_BOX_2Y)


def chart_spread(changes: pd.DataFrame, tags: pd.Series) -> None:
    """Chart 4 — 2s10s spread over time, FOMC decision days marked, zero line."""
    spread = changes["2s10s"]
    fomc_days = changes.index[tags == "FOMC"]

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(spread.index, spread.to_numpy(), color="#1f77b4", linewidth=1,
            label="2s10s spread")
    ax.scatter(fomc_days, spread.loc[fomc_days], color="red", s=18, zorder=3,
               label=f"FOMC decision (n={len(fomc_days)})")
    ax.axhline(0, color="black", linewidth=0.9, label="0 bp (inversion line)")
    ax.set_xlabel("Date")
    ax.set_ylabel("2s10s spread (bp)  =  10y − 2y")
    ax.set_title("US 2s10s Treasury curve spread with FOMC decision days")
    ax.legend(loc="best")
    ax.grid(alpha=0.3)
    _citation(fig)
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    fig.savefig(config.CHART_SPREAD, dpi=130)
    plt.close(fig)
    log.info("Wrote %s", config.CHART_SPREAD)


def make_all(results: dict) -> None:
    """Render all four charts from an analysis results dict."""
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    chart_mean_move(results["stats"], results["tags"])
    chart_multiples(results["multiples"], results["tags"])
    chart_box_2y(results["changes"], results["tags"])
    chart_spread(results["changes"], results["tags"])
