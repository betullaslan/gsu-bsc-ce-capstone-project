"""Figure generation for the test-generation experiment analysis."""

from pathlib import Path
from typing import Any, Dict, List

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from test_generation_config import FIGURES_DIR
from test_generation_utils import _as_float


def _bar_png(title: str, labels: List[str], values: List[float], ylabel: str, out_path: Path) -> None:
    """Write a single bar chart PNG file."""
    # Simple bar-chart writer used by multiple report sections.
    plt.figure(figsize=(10, 5))
    plt.bar(labels, values)
    plt.title(title)
    plt.ylabel(ylabel)
    plt.xticks(rotation=30, ha="right")
    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_path, dpi=150)
    plt.close()


def write_figures(strategy_rows: List[Dict[str, Any]], detailed_rows: List[Dict[str, Any]]) -> None:
    """Write PNG figures for the test-generation analysis reports."""
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    strategies = [str(r.get("strategy") or "") for r in strategy_rows]

    def fget(key: str) -> List[float]:
        """Extract one numeric metric column from strategy rows."""
        return [float(_as_float(r.get(key)) or 0.0) for r in strategy_rows]

    _bar_png(
        "Average final_score by strategy",
        strategies,
        fget("avg_final_score"),
        "avg_final_score",
        FIGURES_DIR / "final_score_by_strategy.png",
    )

    metrics = [
        ("avg_completeness", "completeness"),
        ("avg_traceability", "traceability"),
        ("avg_specificity", "specificity"),
        ("avg_hallucination", "hallucination"),
        ("avg_semantic_coverage", "semantic_coverage"),
    ]
    plt.figure(figsize=(10, 6))
    for key, label in metrics:
        plt.plot(strategies, fget(key), marker="o", label=label)
    plt.title("Metrics by strategy")
    plt.ylabel("Average value")
    plt.xticks(rotation=30, ha="right")
    plt.ylim(0.0, 1.0)
    plt.legend()
    plt.tight_layout()
    plt.savefig(FIGURES_DIR / "metrics_by_strategy.png", dpi=150)
    plt.close()

    _bar_png(
        "Average warning_count by strategy",
        strategies,
        fget("avg_warning_count"),
        "avg_warning_count",
        FIGURES_DIR / "warning_count_by_strategy.png",
    )

    _bar_png(
        "Average response_time_seconds by strategy",
        strategies,
        fget("avg_response_time_seconds"),
        "avg_response_time_seconds",
        FIGURES_DIR / "response_time_by_strategy.png",
    )

    _bar_png(
        "Average generation_attempts by strategy",
        strategies,
        fget("avg_generation_attempts"),
        "avg_generation_attempts",
        FIGURES_DIR / "generation_attempts_by_strategy.png",
    )

    by_strat: Dict[str, List[Dict[str, Any]]] = {}
    for r in detailed_rows:
        s = str(r.get("strategy") or "").strip()
        if not s:
            continue
        by_strat.setdefault(s, []).append(r)

    def _boxplot_png(title: str, key: str, ylabel: str, out_path: Path) -> None:
        """Write a per-strategy boxplot PNG for one metric."""
        data: List[List[float]] = []
        labels: List[str] = []
        for s in strategies:
            vals = [_as_float(x.get(key)) for x in by_strat.get(s, [])]
            clean_vals = [float(v) for v in vals if v is not None]
            if not clean_vals:
                continue
            labels.append(s)
            data.append(clean_vals)
        if not data:
            return
        plt.figure(figsize=(max(10, len(labels) * 1.2), 5))
        plt.boxplot(data, tick_labels=labels, showfliers=False)
        plt.title(title)
        plt.ylabel(ylabel)
        plt.xticks(rotation=30, ha="right")
        plt.tight_layout()
        plt.savefig(out_path, dpi=150)
        plt.close()

    _boxplot_png(
        "final_score distribution by strategy",
        "final_score",
        "final_score",
        FIGURES_DIR / "final_score_distribution_by_strategy.png",
    )
    _boxplot_png(
        "response_time_seconds distribution by strategy",
        "response_time_seconds",
        "response_time_seconds",
        FIGURES_DIR / "response_time_distribution_by_strategy.png",
    )

    status_order = ["clean", "clean_with_warnings", "needs_review", "invalid"]
    counts: Dict[str, int] = {k: 0 for k in status_order}
    for r in detailed_rows:
        s = str(r.get("quality_status") or "").strip()
        if s in counts:
            counts[s] += 1
    _bar_png(
        "Quality status distribution",
        status_order,
        [float(counts[k]) for k in status_order],
        "count",
        FIGURES_DIR / "quality_status_distribution.png",
    )
