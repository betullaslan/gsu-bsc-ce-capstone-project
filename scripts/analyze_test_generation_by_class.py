"""Analyze test generation quality grouped by manual labels.

Writes breakdown tables and figures under `analysis/llm_test_generation/by_manual_labels/`.
"""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import matplotlib


matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

BASE_DIR = Path(__file__).resolve().parent.parent

# Default input/output locations for the generated manual-label breakdown report.
DEFAULT_MANUAL_CSV = BASE_DIR / "data" / "scenario_manual_labels.csv"
DEFAULT_DETAILED_CSV = BASE_DIR / "analysis" / "llm_test_generation" / "tables" / "results_detailed.csv"
DEFAULT_OUT_DIR = BASE_DIR / "analysis" / "llm_test_generation" / "by_manual_labels"
DEFAULT_FIGURES_DIR = DEFAULT_OUT_DIR / "figures"


def _read_manual_csv(path: Path) -> Dict[str, Dict[str, str]]:
    """Read manual scenario labels keyed by scenario id."""
    rows: Dict[str, Dict[str, str]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = set(reader.fieldnames or [])
        id_key = "scenario_id" if "scenario_id" in fieldnames else (
            "id" if "id" in fieldnames else "scenario_id"
        )
        for r in reader:
            sid = str(r.get(id_key) or "").strip()
            if not sid:
                continue
            rows[sid] = {
                "scenario_id": sid,
                "test_level": str(r.get("test_level") or "").strip(),
                "test_type": str(r.get("test_type") or "").strip(),
            }
    return rows


def _as_float(value: Any) -> float | None:
    """Convert value to float when possible."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _as_bool(value: Any) -> bool:
    """Convert common truthy/falsy values to bool."""
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    if s in {"true", "1", "yes", "y"}:
        return True
    if s in {"false", "0", "no", "n"}:
        return False
    return bool(value)


def _mean(values: Iterable[float]) -> float:
    """Return arithmetic mean or 0 for empty input."""
    vals = list(values)
    if not vals:
        return 0.0
    return sum(vals) / len(vals)


def _write_rows(path: Path, rows: List[Dict[str, Any]], fieldnames: List[str]) -> None:
    """Write dictionary rows into a CSV file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def _group_summary(
    detailed_rows: List[Dict[str, Any]],
    manual: Dict[str, Dict[str, str]],
    group_key: str,
) -> List[Dict[str, Any]]:
    """Aggregate strategy metrics by one manual label dimension."""
    buckets: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    for r in detailed_rows:
        sid = str(r.get("scenario_id") or "").strip()
        strat = str(r.get("strategy") or "").strip()
        if not sid or not strat:
            continue
        m = manual.get(sid)
        if not m:
            continue
        label = str(m.get(group_key) or "").strip()
        if not label:
            label = "Unknown"
        buckets[(strat, label)].append(r)

    out: List[Dict[str, Any]] = []
    for (strategy, label), rows in sorted(buckets.items(), key=lambda x: (x[0][0], x[0][1])):
        final_scores = [_as_float(rr.get("final_score")) for rr in rows]
        final_scores_f = [x for x in final_scores if x is not None]
        valid_bools = [_as_bool(rr.get("is_valid")) for rr in rows]
        warning_counts = [_as_float(rr.get("warning_count")) for rr in rows]
        warning_counts_f = [x for x in warning_counts if x is not None]

        out.append(
            {
                "strategy": strategy,
                group_key: label,
                "n": len(rows),
                "avg_final_score": round(_mean(final_scores_f), 3),
                "valid_rate": round(
                    (_mean([1.0 if b else 0.0 for b in valid_bools]) if valid_bools else 0.0),
                    3,
                ),
                "avg_warning_count": round(_mean(warning_counts_f), 3),
            }
        )


    out.sort(
        key=lambda r: (
            str(r.get(group_key) or ""),
            -float(r.get("avg_final_score") or 0.0),
            str(r.get("strategy") or ""),
        )
    )
    return out


def _overall_summary(
    detailed_rows: List[Dict[str, Any]],
    manual: Dict[str, Dict[str, str]],
    group_key: str,
) -> List[Dict[str, Any]]:
    """Aggregate pooled metrics by one manual label dimension."""
    buckets: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in detailed_rows:
        sid = str(r.get("scenario_id") or "").strip()
        if not sid:
            continue
        m = manual.get(sid)
        if not m:
            continue
        label = str(m.get(group_key) or "").strip() or "Unknown"
        buckets[label].append(r)

    out: List[Dict[str, Any]] = []
    for label, rows in sorted(buckets.items(), key=lambda x: x[0]):
        final_scores = [_as_float(rr.get("final_score")) for rr in rows]
        final_scores_f = [x for x in final_scores if x is not None]
        valid_bools = [_as_bool(rr.get("is_valid")) for rr in rows]
        warning_counts = [_as_float(rr.get("warning_count")) for rr in rows]
        warning_counts_f = [x for x in warning_counts if x is not None]

        out.append(
            {
                group_key: label,
                "n": len(rows),
                "avg_final_score": round(_mean(final_scores_f), 3),
                "valid_rate": round(
                    (_mean([1.0 if b else 0.0 for b in valid_bools]) if valid_bools else 0.0),
                    3,
                ),
                "avg_warning_count": round(_mean(warning_counts_f), 3),
            }
        )


    return out


def _write_grouped_bar_chart(
    *,
    rows: List[Dict[str, Any]],
    label_key: str,
    value_key: str,
    title: str,
    out_path: Path,
) -> None:
    """Write grouped bar chart (label x strategy) for one metric."""
    labels = sorted(
        {str(r.get(label_key) or "").strip() for r in rows if str(r.get(label_key) or "").strip()}
    )
    strategies = sorted(
        {str(r.get("strategy") or "").strip() for r in rows if str(r.get("strategy") or "").strip()}
    )
    if not labels or not strategies:
        return

    by_pair: Dict[Tuple[str, str], float] = {}
    for r in rows:
        lab = str(r.get(label_key) or "").strip()
        strat = str(r.get("strategy") or "").strip()
        if not lab or not strat:
            continue
        val = _as_float(r.get(value_key))
        if val is None:
            continue
        by_pair[(lab, strat)] = float(val)

    fig, ax = plt.subplots(1, 1, figsize=(max(8, len(labels) * 1.2), 4.8))
    x = list(range(len(labels)))
    group_width = 0.80
    bar_w = group_width / max(len(strategies), 1)

    for i, strat in enumerate(strategies):
        ys = [by_pair.get((lab, strat), 0.0) for lab in labels]
        xs = [xi - group_width / 2 + (i + 0.5) * bar_w for xi in x]
        ax.bar(xs, ys, width=bar_w, label=strat)

    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=30, ha="right")
    ax.set_ylim(0, 1)
    ax.set_ylabel(value_key)
    ax.set_title(title)
    ax.legend(ncols=min(3, len(strategies)), fontsize=8)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=200)
    plt.close(fig)


def _write_heatmap(
    *,
    rows: List[Dict[str, Any]],
    label_key: str,
    value_key: str,
    title: str,
    out_path: Path,
) -> None:
    """Write strategy-by-label heatmap for one metric."""
    labels = sorted(
        {str(r.get(label_key) or "").strip() for r in rows if str(r.get(label_key) or "").strip()}
    )
    strategies = sorted(
        {str(r.get("strategy") or "").strip() for r in rows if str(r.get("strategy") or "").strip()}
    )
    if not labels or not strategies:
        return

    by_pair: Dict[Tuple[str, str], float] = {}
    for r in rows:
        lab = str(r.get(label_key) or "").strip()
        strat = str(r.get("strategy") or "").strip()
        if not lab or not strat:
            continue
        val = _as_float(r.get(value_key))
        if val is None:
            continue
        by_pair[(strat, lab)] = float(val)

    matrix = np.full((len(strategies), len(labels)), np.nan, dtype=float)
    for i, strat in enumerate(strategies):
        for j, lab in enumerate(labels):
            v = by_pair.get((strat, lab))
            if v is None:
                continue
            matrix[i, j] = v

    fig_w = max(8, 1.2 * len(labels))
    fig_h = max(4.5, 0.65 * len(strategies))
    fig, ax = plt.subplots(1, 1, figsize=(fig_w, fig_h))
    im = ax.imshow(matrix, aspect="auto", interpolation="nearest")

    ax.set_title(title)
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=35, ha="right")
    ax.set_yticks(range(len(strategies)))
    ax.set_yticklabels(strategies)


    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            v = matrix[i, j]
            if np.isnan(v):
                continue
            ax.text(j, i, f"{v:.3f}", ha="center", va="center", fontsize=8, color="black")

    cbar = fig.colorbar(im, ax=ax)
    cbar.set_label(value_key)

    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=200)
    plt.close(fig)


def _write_overall_bar_chart(
    *,
    rows: List[Dict[str, Any]],
    label_key: str,
    value_key: str,
    title: str,
    out_path: Path,
) -> None:
    """Write pooled per-label bar chart for one metric."""
    labels = [str(r.get(label_key) or "").strip() for r in rows if str(r.get(label_key) or "").strip()]
    if not labels:
        return
    values = []
    for r in rows:
        lab = str(r.get(label_key) or "").strip()
        if not lab:
            continue
        v = _as_float(r.get(value_key))
        values.append(float(v) if v is not None else 0.0)

    fig, ax = plt.subplots(1, 1, figsize=(max(8, len(labels) * 1.2), 4.2))
    x = list(range(len(labels)))
    ax.bar(x, values, width=0.65)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=30, ha="right")
    ax.set_ylim(0, 1 if value_key != "avg_warning_count" else max(1.0, max(values) * 1.2))
    ax.set_ylabel(value_key)
    ax.set_title(title)

    for i, v in enumerate(values):
        ax.text(i, v, f"{v:.3f}", ha="center", va="bottom", fontsize=8)

    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=200)
    plt.close(fig)


def main() -> None:
    """Analyze test generation results grouped by manual labels."""
    parser = argparse.ArgumentParser(
        description=(
            "Analyze test generation quality metrics by manual scenario classification "
            "(which test_level/test_type performs better per strategy)."
        )
    )
    parser.add_argument("--manual-csv", type=Path, default=DEFAULT_MANUAL_CSV)
    parser.add_argument(
        "--detailed-csv",
        type=Path,
        default=DEFAULT_DETAILED_CSV,
        help=(
            "Path to analysis/llm_test_generation/tables/results_detailed.csv "
            "(run scripts/analyze_test_generation.py first)."
        ),
    )
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument(
        "--figures-dir",
        type=Path,
        default=DEFAULT_FIGURES_DIR,
        help="Where to write plots (defaults to analysis/llm_test_generation/by_manual_labels/figures).",
    )
    args = parser.parse_args()

    if not args.detailed_csv.exists():
        raise SystemExit(
            f"Missing detailed results CSV: {args.detailed_csv}\n"
            "First run: python scripts/analyze_test_generation.py"
        )

    manual = _read_manual_csv(args.manual_csv)
    with args.detailed_csv.open("r", encoding="utf-8-sig", newline="") as f:
        detailed_rows = list(csv.DictReader(f))

    by_level = _group_summary(detailed_rows, manual, group_key="test_level")
    by_type = _group_summary(detailed_rows, manual, group_key="test_type")
    overall_level = _overall_summary(detailed_rows, manual, group_key="test_level")
    overall_type = _overall_summary(detailed_rows, manual, group_key="test_type")

    tables_dir = args.out_dir / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)
    _write_rows(
        tables_dir / "by_test_level_and_strategy.csv",
        by_level,
        fieldnames=["test_level", "strategy", "n", "avg_final_score", "valid_rate", "avg_warning_count"],
    )
    _write_rows(
        tables_dir / "by_test_type_and_strategy.csv",
        by_type,
        fieldnames=["test_type", "strategy", "n", "avg_final_score", "valid_rate", "avg_warning_count"],
    )

    _write_rows(
        tables_dir / "overall_by_test_level.csv",
        overall_level,
        fieldnames=["test_level", "n", "avg_final_score", "valid_rate", "avg_warning_count"],
    )
    _write_rows(
        tables_dir / "overall_by_test_type.csv",
        overall_type,
        fieldnames=["test_type", "n", "avg_final_score", "valid_rate", "avg_warning_count"],
    )

    _write_grouped_bar_chart(
        rows=by_level,
        label_key="test_level",
        value_key="avg_final_score",
        title="Avg Final Score by Manual test_level (per strategy)",
        out_path=args.figures_dir / "final_score_by_test_level_per_strategy.png",
    )
    _write_grouped_bar_chart(
        rows=by_type,
        label_key="test_type",
        value_key="avg_final_score",
        title="Avg Final Score by Manual test_type (per strategy)",
        out_path=args.figures_dir / "final_score_by_test_type_per_strategy.png",
    )
    _write_heatmap(
        rows=by_level,
        label_key="test_level",
        value_key="avg_final_score",
        title="Heatmap: Avg Final Score (strategy x test_level)",
        out_path=args.figures_dir / "heatmap_final_score_by_test_level_and_strategy.png",
    )
    _write_heatmap(
        rows=by_type,
        label_key="test_type",
        value_key="avg_final_score",
        title="Heatmap: Avg Final Score (strategy x test_type)",
        out_path=args.figures_dir / "heatmap_final_score_by_test_type_and_strategy.png",
    )
    _write_overall_bar_chart(
        rows=sorted(overall_level, key=lambda r: -float(r.get("avg_final_score") or 0.0)),
        label_key="test_level",
        value_key="avg_final_score",
        title="Overall: Avg Final Score by test_level (all strategies)",
        out_path=args.figures_dir / "overall_final_score_by_test_level.png",
    )
    _write_overall_bar_chart(
        rows=sorted(overall_type, key=lambda r: -float(r.get("avg_final_score") or 0.0)),
        label_key="test_type",
        value_key="avg_final_score",
        title="Overall: Avg Final Score by test_type (all strategies)",
        out_path=args.figures_dir / "overall_final_score_by_test_type.png",
    )

    def _quick_best_table(rows: List[Dict[str, Any]], label_key: str) -> List[str]:
        """Build markdown table of best strategy per label value."""
        labels = sorted(
            {str(r.get(label_key) or "").strip() for r in rows if str(r.get(label_key) or "").strip()}
        )
        best_rows: List[Dict[str, Any]] = []
        for lab in labels:
            subset = [r for r in rows if str(r.get(label_key) or "").strip() == lab]
            subset.sort(
                key=lambda r: (
                    -float(r.get("avg_final_score") or 0.0),
                    -float(r.get("valid_rate") or 0.0),
                    float(r.get("avg_warning_count") or 0.0),
                    str(r.get("strategy") or ""),
                )
            )
            if subset:
                best_rows.append(subset[0])

        lines: List[str] = []
        lines.append(
            f"| {label_key} | best_strategy | avg_final_score | valid_rate | "
            "avg_warning_count | n |"
        )
        lines.append("|---|---|---:|---:|---:|---:|")
        for r in best_rows:
            label_value = str(r.get(label_key) or "").strip()
            lines.append(
                f"| {label_value} | `{r['strategy']}` | {float(r['avg_final_score']):.3f} | "
                f"{float(r['valid_rate']):.1%} | {float(r['avg_warning_count']):.2f} | {int(r['n'])} |"
            )
        return lines

    md_lines: List[str] = []
    md_lines.append("# Test Generation Quality - By Manual Labels")
    md_lines.append("")
    md_lines.append(
        "This report groups test generation results by your manual labels (`test_level`, `test_type`) "
        "and links the relevant `.png` figures."
    )
    md_lines.append(
        "All scores are based on `final_score` from "
        "`analysis/llm_test_generation/tables/results_detailed.csv`."
    )
    md_lines.append("")
    md_lines.append("## 1) Quick read (how to interpret)")
    md_lines.append("")
    md_lines.append(
        "- Treat categories with **very small `n`** (e.g., `n=1`) as illustrative, not definitive."
    )
    md_lines.append("- For broad conclusions, use the **overall summaries** and the **heatmaps**.")
    md_lines.append("")
    md_lines.append("## 2) Best strategy per category (avg `final_score`)")
    md_lines.append("")
    md_lines.append("### By `test_type`")
    md_lines.append("")
    md_lines.extend(_quick_best_table(by_type, label_key="test_type"))
    md_lines.append("")
    md_lines.append("### By `test_level`")
    md_lines.append("")
    md_lines.extend(_quick_best_table(by_level, label_key="test_level"))
    md_lines.append("")
    md_lines.append("## 3) Overall performance by category (all strategies pooled)")
    md_lines.append("")
    md_lines.append("### By `test_level`")
    md_lines.append("")
    for r in sorted(
        overall_level,
        key=lambda x: (
            -float(x.get("avg_final_score") or 0.0),
            str(x.get("test_level") or ""),
        ),
    ):
        md_lines.append(
            f"- `{r['test_level']}`: avg_final_score={float(r['avg_final_score']):.3f}, "
            f"valid_rate={float(r['valid_rate']):.1%}, "
            f"avg_warning_count={float(r['avg_warning_count']):.2f}, "
            f"n={r['n']}"
        )
    md_lines.append("")
    md_lines.append("### By `test_type`")
    md_lines.append("")
    for r in sorted(
        overall_type,
        key=lambda x: (
            -float(x.get("avg_final_score") or 0.0),
            str(x.get("test_type") or ""),
        ),
    ):
        md_lines.append(
            f"- `{r['test_type']}`: avg_final_score={float(r['avg_final_score']):.3f}, "
            f"valid_rate={float(r['valid_rate']):.1%}, "
            f"avg_warning_count={float(r['avg_warning_count']):.2f}, "
            f"n={r['n']}"
        )
    md_lines.append("")
    md_lines.append("## 4) Quick takeaways")
    md_lines.append("")

    def _top_overall(rows: List[Dict[str, Any]], label_key: str) -> Dict[str, Any] | None:
        """Return top row by avg_final_score for a label dimension."""
        if not rows:
            return None
        rows_sorted = sorted(
            rows,
            key=lambda r: (-float(r.get("avg_final_score") or 0.0), str(r.get(label_key) or "")),
        )
        return rows_sorted[0] if rows_sorted else None

    def _lowest_valid(rows: List[Dict[str, Any]], label_key: str) -> Dict[str, Any] | None:
        """Return row with lowest valid_rate for a label dimension."""
        if not rows:
            return None
        rows_sorted = sorted(
            rows,
            key=lambda r: (
                float(r.get("valid_rate") or 0.0),
                -float(r.get("avg_final_score") or 0.0),
                str(r.get(label_key) or ""),
            ),
        )
        return rows_sorted[0] if rows_sorted else None

    top_level = _top_overall(overall_level, "test_level")
    top_type = _top_overall(overall_type, "test_type")
    low_valid_level = _lowest_valid(overall_level, "test_level")
    low_valid_type = _lowest_valid(overall_type, "test_type")

    if top_level:
        md_lines.append(
            f"- Best overall `test_level` by avg `final_score`: `{top_level['test_level']}` "
            f"({float(top_level['avg_final_score']):.3f})."
        )
    if top_type:
        md_lines.append(
            f"- Best overall `test_type` by avg `final_score`: `{top_type['test_type']}` "
            f"({float(top_type['avg_final_score']):.3f})."
        )
    if low_valid_level:
        md_lines.append(
            f"- Lowest overall `valid_rate` by `test_level`: `{low_valid_level['test_level']}` "
            f"({float(low_valid_level['valid_rate']):.1%})."
        )
    if low_valid_type:
        md_lines.append(
            f"- Lowest overall `valid_rate` by `test_type`: `{low_valid_type['test_type']}` "
            f"({float(low_valid_type['valid_rate']):.1%})."
        )

    md_lines.append("")
    md_lines.append("## 5) Figures (PNG)")
    md_lines.append("")
    md_lines.append("### High-level comparisons")
    md_lines.append("")
    md_lines.append("- `final_score` (per strategy):")
    md_lines.append("  - `figures/final_score_by_test_level_per_strategy.png`")
    md_lines.append("  - `figures/final_score_by_test_type_per_strategy.png`")
    md_lines.append("")
    md_lines.append(
        "![Avg final_score by manual test_level (per strategy)]"
        "(figures/final_score_by_test_level_per_strategy.png)"
    )
    md_lines.append(
        "![Avg final_score by manual test_type (per strategy)]"
        "(figures/final_score_by_test_type_per_strategy.png)"
    )
    md_lines.append("")
    md_lines.append("- `final_score` (overall, all strategies pooled):")
    md_lines.append("  - `figures/overall_final_score_by_test_level.png`")
    md_lines.append("  - `figures/overall_final_score_by_test_type.png`")
    md_lines.append("")
    md_lines.append("![Overall avg final_score by test_level](figures/overall_final_score_by_test_level.png)")
    md_lines.append("![Overall avg final_score by test_type](figures/overall_final_score_by_test_type.png)")
    md_lines.append("")
    md_lines.append("### Heatmaps (strategy x category)")
    md_lines.append("")
    md_lines.append("- `final_score`:")
    md_lines.append("  - `figures/heatmap_final_score_by_test_level_and_strategy.png`")
    md_lines.append("  - `figures/heatmap_final_score_by_test_type_and_strategy.png`")
    md_lines.append("")
    md_lines.append(
        "![Heatmap: avg final_score (strategy x test_level)]"
        "(figures/heatmap_final_score_by_test_level_and_strategy.png)"
    )
    md_lines.append("")
    md_lines.append("- `valid_rate`: use the tables above (`valid_rate` column) instead of extra plots.")
    md_lines.append("")
    (args.out_dir / "analysis.md").write_text("\n".join(md_lines) + "\n", encoding="utf-8-sig")
    print(f"Wrote: {tables_dir}")
    print(f"Wrote: {args.figures_dir}")
    print(f"Wrote: {args.out_dir / 'analysis.md'}")


if __name__ == "__main__":
    main()
