"""Analyze manual vs LLM classification results and write analysis artifacts.

Produces accuracy summaries, per-strategy drill-down tables, and comparison figures under
`analysis/llm_classification/`.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import matplotlib


matplotlib.use("Agg")
import matplotlib.pyplot as plt

BASE_DIR = Path(__file__).resolve().parent.parent

# Default input/output locations for reproducible, script-generated artifacts.
DEFAULT_MANUAL_CSV = BASE_DIR / "data" / "scenario_manual_labels.csv"
DEFAULT_LLM_JSON = BASE_DIR / "outputs" / "llm_classification"
DEFAULT_OUT_DIR = BASE_DIR / "analysis" / "llm_classification"
DEFAULT_TABLES_DIR = DEFAULT_OUT_DIR / "tables"
DEFAULT_FIGURES_DIR = DEFAULT_OUT_DIR / "figures"


def _write_manual_label_distribution_csv(manual: Dict[str, Dict[str, str]], out_path: Path) -> None:
    """Write manual label distribution (class balance) to a CSV file.

    Output columns:
    - `dimension`: `test_level` or `test_type`
    - `label`: the label value
    - `count`: number of scenarios with that label
    - `rate`: count / total_manual_scenarios
    """
    level_counts: Counter[str] = Counter()
    type_counts: Counter[str] = Counter()

    for r in manual.values():
        lvl = str((r or {}).get("test_level") or "").strip() or "Unknown"
        typ = str((r or {}).get("test_type") or "").strip() or "Unknown"
        level_counts[lvl] += 1
        type_counts[typ] += 1

    rows: List[Dict[str, Any]] = []
    total = max(1, len(manual))
    for label, cnt in sorted(level_counts.items(), key=lambda kv: (-kv[1], kv[0])):
        rows.append(
            {
                "dimension": "test_level",
                "label": label,
                "count": int(cnt),
                "rate": round(float(cnt) / float(total), 6),
            }
        )
    for label, cnt in sorted(type_counts.items(), key=lambda kv: (-kv[1], kv[0])):
        rows.append(
            {
                "dimension": "test_type",
                "label": label,
                "count": int(cnt),
                "rate": round(float(cnt) / float(total), 6),
            }
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    _write_rows(out_path, rows, fieldnames=["dimension", "label", "count", "rate"])


def _rel_to_base(path: Path) -> str:
    """Return path relative to repository root when possible."""
    try:
        return str(path.resolve().relative_to(BASE_DIR.resolve())).replace("\\", "/")
    except Exception:
        return str(path).replace("\\", "/")


def _read_manual_csv(path: Path) -> Dict[str, Dict[str, str]]:
    """Load manual labels CSV keyed by scenario_id."""
    rows: Dict[str, Dict[str, str]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = set(reader.fieldnames or [])
        # Support both `scenario_id` and `id` depending on CSV provenance.
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


def _extract_llm_rows(data: Dict[str, Any], strategy_key: str | None = None) -> Dict[str, Dict[str, str]]:
    """Extract LLM label rows keyed by scenario_id from JSON payload."""
    scenarios = list(data.get("scenarios") or [])
    out: Dict[str, Dict[str, str]] = {}
    for s in scenarios:
        if not isinstance(s, dict):
            continue
        sid = str(s.get("id") or "").strip()
        if not sid:
            continue
        if strategy_key is None:
            llm = s.get("llm_classification") or {}
        else:
            # Some outputs include a combined JSON with a per-strategy map.
            by_strat = s.get("llm_classification_by_strategy") or {}
            if not isinstance(by_strat, dict):
                by_strat = {}
            llm = (
                by_strat.get(strategy_key)
                if isinstance(by_strat.get(strategy_key), dict)
                else {}
            )
        if not isinstance(llm, dict):
            llm = {}
        out[sid] = {
            "scenario_id": sid,
            "feature": str(s.get("feature") or "").strip(),
            "scenario": str(s.get("scenario") or "").strip(),
            "llm_test_level": str(llm.get("test_level") or "").strip(),
            "llm_test_type": str(llm.get("test_type") or "").strip(),
        }
    return out


def _read_llm_json(path: Path) -> Dict[str, Any]:
    """Read LLM classification JSON file."""
    return json.loads(path.read_text(encoding="utf-8"))


def _read_csv_rows(path: Path) -> List[Dict[str, str]]:
    """Read CSV rows into dictionaries."""
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return [dict(r) for r in reader]


def _top_confusions_from_comparison_csv(
    path: Path,
    *,
    manual_col: str,
    llm_col: str,
    top_n: int = 5,
) -> Tuple[int, List[Tuple[str, str, int, float]]]:
    """Return top label confusion pairs from comparison CSV."""
    rows = _read_csv_rows(path)
    counts: Counter[Tuple[str, str]] = Counter()
    mismatch_total = 0
    for r in rows:
        m = str(r.get(manual_col) or "").strip()
        l = str(r.get(llm_col) or "").strip()
        if not m or not l or m == l:
            continue
        mismatch_total += 1
        counts[(m, l)] += 1

    pairs: List[Tuple[str, str, int, float]] = []
    for (m, l), cnt in counts.most_common(top_n):
        pct = (cnt / mismatch_total * 100.0) if mismatch_total else 0.0
        pairs.append((m, l, int(cnt), float(pct)))
    return mismatch_total, pairs


def _analyze_one(
    *,
    manual: Dict[str, Dict[str, str]],
    llm_rows: Dict[str, Dict[str, str]],
    out_dir: Path,
    confusion_matrix: bool,
    manual_csv_path: Path,
    llm_json_path: Path,
    strategy_label: str | None = None,
) -> Tuple[float, float, float, int]:
    """Run one manual-vs-LLM comparison and write artifacts."""
    manual_ids = set(manual.keys())
    llm_ids = set(llm_rows.keys())
    common_ids = sorted(manual_ids & llm_ids)
    missing_in_llm = sorted(manual_ids - llm_ids)
    missing_in_manual = sorted(llm_ids - manual_ids)

    comparison_rows: List[Dict[str, Any]] = []

    manual_levels: List[str] = []
    llm_levels: List[str] = []
    manual_types: List[str] = []
    llm_types: List[str] = []

    for sid in common_ids:
        m = manual[sid]
        l = llm_rows[sid]
        m_level = m.get("test_level") or ""
        l_level = l.get("llm_test_level") or ""
        m_type = m.get("test_type") or ""
        l_type = l.get("llm_test_type") or ""
        manual_levels.append(m_level)
        llm_levels.append(l_level)
        manual_types.append(m_type)
        llm_types.append(l_type)

        comparison_rows.append(
            {
                "scenario_id": sid,
                "feature": l.get("feature") or "",
                "scenario": l.get("scenario") or "",
                "manual_test_level": m_level,
                "llm_test_level": l_level,
                "level_match": str(m_level == l_level),
                "manual_test_type": m_type,
                "llm_test_type": l_type,
                "type_match": str(m_type == l_type),
                "both_match": str((m_level == l_level) and (m_type == l_type)),
            }
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    tables_dir = out_dir / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)

    _write_rows(
        tables_dir / "classification_comparison.csv",
        comparison_rows,
        fieldnames=[
            "scenario_id",
            "feature",
            "scenario",
            "manual_test_level",
            "llm_test_level",
            "level_match",
            "manual_test_type",
            "llm_test_type",
            "type_match",
            "both_match",
        ],
    )

    level_ok, n, level_acc = _accuracy([r["level_match"] == "True" for r in comparison_rows])
    type_ok, _, type_acc = _accuracy([r["type_match"] == "True" for r in comparison_rows])
    both_ok, _, both_acc = _accuracy([r["both_match"] == "True" for r in comparison_rows])

    dist_rows: List[Dict[str, str]] = []
    for label, m_cnt, l_cnt in _label_counts(comparison_rows, "manual_test_level", "llm_test_level"):
        dist_rows.append(
            {
                "dimension": "test_level",
                "label": label,
                "manual_count": str(m_cnt),
                "llm_count": str(l_cnt),
            }
        )
    for label, m_cnt, l_cnt in _label_counts(comparison_rows, "manual_test_type", "llm_test_type"):
        dist_rows.append(
            {
                "dimension": "test_type",
                "label": label,
                "manual_count": str(m_cnt),
                "llm_count": str(l_cnt),
            }
        )
    _write_rows(
        tables_dir / "classification_distribution.csv",
        dist_rows,
        fieldnames=["dimension", "label", "manual_count", "llm_count"],
    )

    _ = confusion_matrix
    lvl_pairs_all = _confusion_pairs(manual_levels, llm_levels, only_mismatches=False)
    typ_pairs_all = _confusion_pairs(manual_types, llm_types, only_mismatches=False)

    def _labels(a: List[str], b: List[str]) -> List[str]:
        """Create frequency-sorted label list from two series."""
        freq = Counter(a) + Counter(b)
        labels = list(freq.keys())
        labels.sort(key=lambda x: (-freq[x], x))
        return labels

    _write_confusion_matrix_csv(
        tables_dir / "level_confusion_matrix.csv",
        _labels(manual_levels, llm_levels),
        lvl_pairs_all,
    )
    _write_confusion_matrix_csv(
        tables_dir / "type_confusion_matrix.csv",
        _labels(manual_types, llm_types),
        typ_pairs_all,
    )

    _write_figures(comparison_rows, out_dir)

    summary_md = out_dir / "classification_summary.md"
    lines: List[str] = []
    lines.append("# Classification Summary")
    lines.append("")
    if strategy_label is not None:
        lines.append(f"- Strategy: `{strategy_label}`")

    lines.append(f"- Manual CSV: `{manual_csv_path.name}`")
    lines.append(f"- LLM JSON: `{llm_json_path.name}`")
    lines.append(f"- Compared (common scenario_id): {len(common_ids)}")
    lines.append(f"- Missing in LLM JSON: {len(missing_in_llm)}")
    lines.append(f"- Missing in Manual CSV: {len(missing_in_manual)}")
    lines.append("")
    lines.append("## Accuracy (only common scenario_id)")
    lines.append("")
    lines.append(f"- test_level accuracy: {level_ok}/{n} = {level_acc:.1%}")
    lines.append(f"- test_type accuracy: {type_ok}/{n} = {type_acc:.1%}")
    lines.append(f"- both_match accuracy: {both_ok}/{n} = {both_acc:.1%}")
    lines.append("")
    lines.append("## Files")
    lines.append("")
    lines.append("- Tables: `tables/`")
    lines.append("- Figures: `figures/`")
    summary_md.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")

    return level_acc, type_acc, both_acc, n


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


def _write_strategy_accuracy_figures(
    *,
    summary_rows: List[Dict[str, Any]],
    figures_dir: Path,
) -> None:
    """Write cross-strategy accuracy comparison figures."""
    if not summary_rows:
        return
    figures_dir.mkdir(parents=True, exist_ok=True)


    strategies = [
        str(r.get("strategy") or "").strip()
        for r in summary_rows
        if str(r.get("strategy") or "").strip()
    ]
    if not strategies:
        return

    def col(name: str) -> List[float]:
        """Extract one numeric column from summary rows."""
        out: List[float] = []
        for r in summary_rows:
            v = _as_float(r.get(name))
            out.append(float(v) if v is not None else 0.0)
        return out

    level = col("test_level_accuracy")
    typ = col("test_type_accuracy")
    exact = col("exact_match_accuracy")

    x = list(range(len(strategies)))
    fig, ax = plt.subplots(1, 1, figsize=(max(8, len(strategies) * 1.2), 4.6))
    w = 0.25
    ax.bar([i - w for i in x], exact, width=w, label="exact_match_accuracy")
    ax.bar(x, typ, width=w, label="test_type_accuracy")
    ax.bar([i + w for i in x], level, width=w, label="test_level_accuracy")
    ax.set_xticks(x)
    ax.set_xticklabels(strategies, rotation=25, ha="right")
    ax.set_ylim(0, 1)
    ax.set_title("Classification Accuracy by Strategy")
    ax.set_ylabel("accuracy")
    ax.legend(ncols=3, fontsize=8)
    fig.tight_layout()
    fig.savefig(figures_dir / "strategies_accuracy_comparison.png", dpi=200)
    plt.close(fig)


    metrics = ["exact", "type", "level"]
    matrix = [exact, typ, level]
    heat = [[matrix[m][i] for m in range(len(metrics))] for i in range(len(strategies))]
    fig, ax = plt.subplots(1, 1, figsize=(8.0, max(3.8, 0.55 * len(strategies))))
    im = ax.imshow(heat, aspect="auto", interpolation="nearest", vmin=0.0, vmax=1.0)
    ax.set_title("Heatmap: Accuracy (strategy x metric)")
    ax.set_xticks(range(len(metrics)))
    ax.set_xticklabels(metrics)
    ax.set_yticks(range(len(strategies)))
    ax.set_yticklabels(strategies)
    for i in range(len(strategies)):
        for j in range(len(metrics)):
            ax.text(j, i, f"{heat[i][j]:.3f}", ha="center", va="center", fontsize=8)
    fig.colorbar(im, ax=ax, label="accuracy")
    fig.tight_layout()
    fig.savefig(figures_dir / "strategies_accuracy_heatmap.png", dpi=200)
    plt.close(fig)


def _accuracy(matches: Iterable[bool]) -> Tuple[int, int, float]:
    """Return (ok, total, accuracy) from boolean match flags."""
    vals = list(matches)
    n = len(vals)
    ok = sum(1 for x in vals if x)
    acc = (ok / n) if n else 0.0
    return ok, n, acc


def _confusion_pairs(
    manual: Iterable[str],
    llm: Iterable[str],
    only_mismatches: bool = False,
) -> Counter[Tuple[str, str]]:
    """Count manual-vs-LLM label pairs."""
    c: Counter[Tuple[str, str]] = Counter()
    for a, b in zip(manual, llm):
        if only_mismatches and a == b:
            continue
        c[(a, b)] += 1
    return c


def _write_confusion_matrix_csv(
    out_path: Path,
    labels: List[str],
    pairs: Counter[Tuple[str, str]],
) -> None:
    """Write confusion matrix counts to CSV."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["manual\\llm", *labels])
        for a in labels:
            row = [a]
            for b in labels:
                row.append(pairs.get((a, b), 0))
            writer.writerow(row)


def _write_rows(path: Path, rows: List[Dict[str, Any]], fieldnames: List[str]) -> None:
    """Write dict rows to CSV with given field order."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def _label_counts(rows: List[Dict[str, Any]], key_manual: str, key_llm: str) -> List[Tuple[str, int, int]]:
    """Compute per-label manual and LLM counts."""
    manual = Counter((str(r.get(key_manual) or "")).strip() for r in rows)
    llm = Counter((str(r.get(key_llm) or "")).strip() for r in rows)
    labels = sorted(set(manual) | set(llm))
    return [(lab, manual.get(lab, 0), llm.get(lab, 0)) for lab in labels if lab]


def _write_figures(rows: List[Dict[str, Any]], out_dir: Path) -> None:
    """Write distribution and accuracy figures for one run."""
    figures_dir = out_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)


    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    for ax, key_m, key_l, title in [
        (axes[0], "manual_test_level", "llm_test_level", "Test Level Distribution"),
        (axes[1], "manual_test_type", "llm_test_type", "Test Type Distribution"),
    ]:
        counts = _label_counts(rows, key_m, key_l)
        labels = [c[0] for c in counts]
        manual_counts = [c[1] for c in counts]
        llm_counts = [c[2] for c in counts]
        x = list(range(len(labels)))
        width = 0.4
        ax.bar([i - width / 2 for i in x], manual_counts, width=width, label="Manual")
        ax.bar([i + width / 2 for i in x], llm_counts, width=width, label="LLM")
        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=30, ha="right")
        ax.set_title(title)
        ax.set_ylabel("Count")
        ax.legend()
    fig.tight_layout()
    fig.savefig(figures_dir / "label_distribution.png", dpi=200)
    plt.close(fig)


    level_ok = sum(1 for r in rows if (r.get("level_match") or "") == "True")
    type_ok = sum(1 for r in rows if (r.get("type_match") or "") == "True")
    both_ok = sum(1 for r in rows if (r.get("both_match") or "") == "True")
    n = len(rows) or 1
    level_acc = level_ok / n
    type_acc = type_ok / n
    both_acc = both_ok / n

    fig2, ax2 = plt.subplots(1, 1, figsize=(6, 4))
    labels = ["test_level", "test_type", "exact_match"]
    vals = [level_acc, type_acc, both_acc]
    ax2.bar(labels, vals)
    ax2.set_ylim(0, 1)
    ax2.set_ylabel("Accuracy")
    ax2.set_title("Classification Accuracy")
    for i, v in enumerate(vals):
        ax2.text(i, v + 0.02, f"{v:.1%}", ha="center", va="bottom", fontsize=9)
    fig2.tight_layout()
    fig2.savefig(figures_dir / "classification_accuracy.png", dpi=200)
    plt.close(fig2)


def main() -> None:
    """CLI entrypoint for manual vs LLM classification analysis."""
    parser = argparse.ArgumentParser(
        description=(
            "Compare manual vs LLM scenario classification and write analysis artifacts."
        )
    )
    parser.add_argument("--manual-csv", type=Path, default=DEFAULT_MANUAL_CSV)
    parser.add_argument("--llm-json", type=Path, default=DEFAULT_LLM_JSON)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--tables-dir", type=Path, default=DEFAULT_TABLES_DIR)
    parser.add_argument(
        "--figures-dir",
        type=Path,
        default=DEFAULT_FIGURES_DIR,
        help=(
            "Where to write cross-strategy comparison figures "
            "(defaults to analysis/llm_classification/figures)."
        ),
    )
    parser.add_argument(
        "--confusion-matrix",
        action="store_true",
        help="Also write confusion matrix CSV files (level_confusion_matrix.csv, type_confusion_matrix.csv).",
    )
    args = parser.parse_args()

    manual = _read_manual_csv(args.manual_csv)


    if args.llm_json.is_dir():
        llm_dir = args.llm_json
        candidates = sorted(llm_dir.glob("llm_*.json"))
        if not candidates:
            raise SystemExit(f"No per-strategy JSON files found under: {llm_dir}")

        index_lines: List[str] = []
        index_lines.append("# LLM Classification - Manual vs LLM (By Strategy)")
        index_lines.append("")
        index_lines.append("This report compares manual labels against LLM-predicted labels for:")
        index_lines.append("")
        index_lines.append(f"- Manual labels: `{_rel_to_base(args.manual_csv)}`")
        index_lines.append(f"- LLM outputs: `{_rel_to_base(llm_dir)}` (`llm_*.json`)")
        index_lines.append("")
        index_lines.append("## How to read")
        index_lines.append("")
        index_lines.append("- `test_level accuracy`: match rate for the `test_level` label.")
        index_lines.append("- `test_type accuracy`: match rate for the `test_type` label.")
        index_lines.append("- `exact (both)`: both labels match simultaneously (stricter).")
        index_lines.append(
            "- `Unknown`: the LLM output can use `Unknown` as a label; "
            "see `tables/strategies_summary.csv` for rates."
        )
        index_lines.append(
            "- Accuracy is computed only over scenario IDs present in both sources (manual AND LLM)."
        )
        index_lines.append("")
        index_lines.append("## Inputs / label taxonomy")
        index_lines.append("")
        index_lines.append(f"- Manual label source-of-truth: `{_rel_to_base(args.manual_csv)}`")
        index_lines.append("- Prompt templates defining label meanings: `prompts/llm_classification/*.txt`")
        index_lines.append(
            "- Allowed labels (used by generation script): `scripts/classify_scenarios.py` "
            "(`TEST_LEVELS`, `TEST_TYPES`)"
        )
        index_lines.append(
            "- Class balance: `tables/manual_label_distribution.csv` "
            "(imbalanced labels can inflate/deflate accuracy)."
        )
        index_lines.append("")
        index_lines.append("## Accuracy summary")
        index_lines.append("")

        summary_rows: List[Dict[str, Any]] = []
        for path in candidates:

            strategy = path.stem[len("llm_") :] if path.stem.startswith("llm_") else path.stem
            data = _read_llm_json(path)
            llm_rows = _extract_llm_rows(data, strategy_key=None)

            unknown_level = sum(1 for r in llm_rows.values() if (r.get("llm_test_level") or "") == "Unknown")
            unknown_type = sum(1 for r in llm_rows.values() if (r.get("llm_test_type") or "") == "Unknown")
            unknown_any = sum(
                1
                for r in llm_rows.values()
                if (r.get("llm_test_level") or "") == "Unknown" or (r.get("llm_test_type") or "") == "Unknown"
            )
            n_llm = len(llm_rows)
            unknown_any_rate = (unknown_any / n_llm) if n_llm else 0.0

            manual_ids = set(manual.keys())
            llm_ids = set(llm_rows.keys())
            missing_in_llm_count = len(manual_ids - llm_ids)
            missing_in_manual_count = len(llm_ids - manual_ids)

            strat_out_dir = args.out_dir / "by_strategy" / strategy
            level_acc, type_acc, both_acc, n = _analyze_one(
                manual=manual,
                llm_rows=llm_rows,
                out_dir=strat_out_dir,
                confusion_matrix=bool(args.confusion_matrix),
                manual_csv_path=args.manual_csv,
                llm_json_path=path,
                strategy_label=strategy,
            )
            summary_rows.append(
                {
                    "strategy": strategy,
                    "n": n,
                    "test_level_accuracy": round(level_acc, 3),
                    "test_type_accuracy": round(type_acc, 3),
                    "exact_match_accuracy": round(both_acc, 3),
                    "unknown_level_count": unknown_level,
                    "unknown_type_count": unknown_type,
                    "unknown_any_count": unknown_any,
                    "unknown_any_rate": round(unknown_any_rate, 3),
                    "missing_in_llm_count": int(missing_in_llm_count),
                    "missing_in_manual_count": int(missing_in_manual_count),
                }
            )
            index_lines.append(
                f"- `{strategy}`: level={level_acc:.1%}, type={type_acc:.1%}, exact={both_acc:.1%}"
            )


        def _rank_key(r: Dict[str, Any]) -> Tuple[float, float, float, str]:
            """Sort key for best-strategy ranking."""
            return (
                float(r.get("exact_match_accuracy") or 0.0),
                float(r.get("test_type_accuracy") or 0.0),
                float(r.get("test_level_accuracy") or 0.0),
                str(r.get("strategy") or ""),
            )

        summary_rows_sorted = sorted(summary_rows, key=_rank_key, reverse=True)
        if summary_rows_sorted:
            best = summary_rows_sorted[0]

            def _pct(v: Any) -> str:
                """Format a numeric value as percentage."""
                try:
                    return f"{float(v) * 100.0:.1f}%"
                except Exception:
                    return "N/A"

            index_lines.append("")
            index_lines.append("## Summary table")
            index_lines.append("")
            index_lines.append(
                "| strategy | n | exact (both) | test_type | test_level | unknown_any_rate | "
                "missing_in_llm | missing_in_manual |"
            )
            index_lines.append("|---|---:|---:|---:|---:|---:|---:|---:|")
            for r in summary_rows_sorted:
                index_lines.append(
                    "| "
                    + " | ".join(
                        [
                            f"`{str(r.get('strategy') or '').strip()}`",
                            str(int(r.get("n") or 0)),
                            _pct(r.get("exact_match_accuracy")),
                            _pct(r.get("test_type_accuracy")),
                            _pct(r.get("test_level_accuracy")),
                            _pct(r.get("unknown_any_rate")),
                            str(int(r.get("missing_in_llm_count") or 0)),
                            str(int(r.get("missing_in_manual_count") or 0)),
                        ]
                    )
                    + " |"
                )
            index_lines.append("")
            index_lines.append("- Full metrics: `tables/strategies_summary.csv`")
            index_lines.append("")
            index_lines.append("## Best Strategy (Ranked)")
            index_lines.append("")
            index_lines.append(
                "- Ranking: exact_match > test_type > test_level"
            )
            index_lines.append(
                f"- Best: `{best['strategy']}` (exact={best['exact_match_accuracy']:.1%}, "
                f"type={best['test_type_accuracy']:.1%}, level={best['test_level_accuracy']:.1%})"
            )

            worst = summary_rows_sorted[-1]
            index_lines.append("")
            index_lines.append("## Quick takeaways")
            index_lines.append("")
            index_lines.append(
                f"- Best overall: `{best['strategy']}` (exact={best['exact_match_accuracy']:.1%})."
            )
            index_lines.append(
                f"- Worst overall: `{worst['strategy']}` (exact={worst['exact_match_accuracy']:.1%})."
            )
            index_lines.append(
                (
                    f"- Unknown label usage: "
                    f"min={min(float(r.get('unknown_any_rate') or 0.0) for r in summary_rows_sorted):.1%}, "
                    f"max={max(float(r.get('unknown_any_rate') or 0.0) for r in summary_rows_sorted):.1%}."
                )
            )
            index_lines.append(
                "- Recommended default: use the best overall strategy unless you have a known "
                "label-specific weakness."
            )


            best_strategy = str(best.get("strategy") or "").strip()
            if best_strategy:
                comp_path = (
                    args.out_dir
                    / "by_strategy"
                    / best_strategy
                    / "tables"
                    / "classification_comparison.csv"
                )
                if comp_path.exists():
                    index_lines.append("")
                    index_lines.append("## Top confusions (best strategy)")
                    index_lines.append("")

                    lvl_total, lvl_pairs = _top_confusions_from_comparison_csv(
                        comp_path,
                        manual_col="manual_test_level",
                        llm_col="llm_test_level",
                        top_n=5,
                    )
                    typ_total, typ_pairs = _top_confusions_from_comparison_csv(
                        comp_path,
                        manual_col="manual_test_type",
                        llm_col="llm_test_type",
                        top_n=5,
                    )

                    def _emit(
                        title: str,
                        total: int,
                        pairs: List[Tuple[str, str, int, float]],
                    ) -> None:
                        """Append a markdown confusion table section."""
                        index_lines.append(f"### {title}")
                        index_lines.append("")
                        if not pairs:
                            index_lines.append("- No mismatches found.")
                            index_lines.append("")
                            return
                        index_lines.append(f"- Total mismatches: {total}")
                        index_lines.append("")
                        index_lines.append("| manual | llm | count | % of mismatches |")
                        index_lines.append("|---|---|---:|---:|")
                        for m, l, cnt, pct in pairs:
                            index_lines.append(f"| `{m}` | `{l}` | {cnt} | {pct:.1f}% |")
                        index_lines.append("")

                    _emit("test_level", lvl_total, lvl_pairs)
                    _emit("test_type", typ_total, typ_pairs)


        args.tables_dir.mkdir(parents=True, exist_ok=True)
        summary_csv = args.tables_dir / "strategies_summary.csv"
        _write_rows(
            summary_csv,
            summary_rows_sorted,
            fieldnames=[
                "strategy",
                "n",
                "test_level_accuracy",
                "test_type_accuracy",
                "exact_match_accuracy",
                "unknown_level_count",
                "unknown_type_count",
                "unknown_any_count",
                "unknown_any_rate",
                "missing_in_llm_count",
                "missing_in_manual_count",
            ],
        )

        args.out_dir.mkdir(parents=True, exist_ok=True)

        _write_manual_label_distribution_csv(manual, args.tables_dir / "manual_label_distribution.csv")

        _write_strategy_accuracy_figures(
            summary_rows=summary_rows_sorted,
            figures_dir=args.figures_dir,
        )

        index_lines.append("")
        index_lines.append("## Figures")
        index_lines.append("")
        index_lines.append("![Accuracy comparison](figures/strategies_accuracy_comparison.png)")
        index_lines.append("![Accuracy heatmap](figures/strategies_accuracy_heatmap.png)")
        index_lines.append("")
        index_lines.append("## Drill-down (per strategy)")
        index_lines.append("")
        index_lines.append("Per-strategy details are in `by_strategy/<strategy>/`:")
        index_lines.append("")
        index_lines.append("- `classification_summary.md`: quick per-strategy overview")
        index_lines.append(
            "- `tables/level_confusion_matrix.csv` / `tables/type_confusion_matrix.csv`: label confusions"
        )
        index_lines.append("- `tables/classification_comparison.csv`: row-level audit (largest file)")
        index_lines.append("")
        index_lines.append("## Data distribution (manual labels)")
        index_lines.append("")
        index_lines.append(
            "- `tables/manual_label_distribution.csv` (class balance for `test_level` / `test_type`)"
        )
        index_lines.append("")
        index_lines.append("## Reproduce")
        index_lines.append("")
        index_lines.append(
            "- `python scripts/analyze_classification.py --llm-json outputs/llm_classification`"
        )

        (args.out_dir / "analysis.md").write_text("\n".join(index_lines) + "\n", encoding="utf-8-sig")
        print(f"Wrote: {args.out_dir / 'analysis.md'}")
        print(f"Wrote: {args.tables_dir}")
        print(f"Wrote: {args.figures_dir}")
        print(f"Wrote: {args.out_dir / 'by_strategy'}")
        return


    llm_data = _read_llm_json(args.llm_json)
    llm_rows = _extract_llm_rows(llm_data, strategy_key=None)

    _analyze_one(
        manual=manual,
        llm_rows=llm_rows,
        out_dir=args.out_dir,
        confusion_matrix=bool(args.confusion_matrix),
        manual_csv_path=args.manual_csv,
        llm_json_path=args.llm_json,
        strategy_label=None,
    )

    strategies: List[str] = []
    for s in list(llm_data.get("scenarios") or []):
        if not isinstance(s, dict):
            continue
        by_strat = s.get("llm_classification_by_strategy")
        if isinstance(by_strat, dict) and by_strat:
            strategies = sorted(str(k) for k in by_strat.keys())
            break

    if not strategies:
        return

    index_lines: List[str] = []
    index_lines.append("# LLM Classification - Manual vs LLM (By Strategy)")
    index_lines.append("")
    index_lines.append(
        "This report compares manual labels against LLM-predicted labels embedded in a single JSON file."
    )
    index_lines.append("")
    index_lines.append(f"- Manual labels: `{_rel_to_base(args.manual_csv)}`")
    index_lines.append(f"- LLM JSON: `{_rel_to_base(args.llm_json)}`")
    index_lines.append("")
    index_lines.append("## How to read")
    index_lines.append("")
    index_lines.append("- `test_level accuracy`: match rate for the `test_level` label.")
    index_lines.append("- `test_type accuracy`: match rate for the `test_type` label.")
    index_lines.append("- `exact (both)`: both labels match simultaneously (stricter).")
    index_lines.append("- `Unknown`: the LLM output can use `Unknown` as a label.")
    index_lines.append(
        "- Accuracy is computed only over scenario IDs present in both sources (manual AND LLM)."
    )
    index_lines.append("")
    index_lines.append("## Inputs / label taxonomy")
    index_lines.append("")
    index_lines.append("- Prompt templates defining label meanings: `prompts/llm_classification/*.txt`")
    index_lines.append(
        "- Allowed labels (used by generation script): `scripts/classify_scenarios.py` "
        "(`TEST_LEVELS`, `TEST_TYPES`)"
    )
    index_lines.append(
        "- Class balance: `tables/manual_label_distribution.csv` "
        "(imbalanced labels can inflate/deflate accuracy)."
    )
    index_lines.append("")
    index_lines.append("## Accuracy summary")
    index_lines.append("")

    for strategy in strategies:
        strat_out_dir = args.out_dir / "by_strategy" / strategy
        llm_s = _extract_llm_rows(llm_data, strategy_key=strategy)
        level_acc, type_acc, both_acc, n = _analyze_one(
            manual=manual,
            llm_rows=llm_s,
            out_dir=strat_out_dir,
            confusion_matrix=bool(args.confusion_matrix),
            manual_csv_path=args.manual_csv,
            llm_json_path=args.llm_json,
            strategy_label=strategy,
        )
        index_lines.append(
            f"- `{strategy}`: level={level_acc:.1%}, type={type_acc:.1%}, exact={both_acc:.1%}"
        )

    args.out_dir.mkdir(parents=True, exist_ok=True)
    args.tables_dir.mkdir(parents=True, exist_ok=True)
    _write_manual_label_distribution_csv(manual, args.tables_dir / "manual_label_distribution.csv")
    (args.out_dir / "analysis.md").write_text("\n".join(index_lines) + "\n", encoding="utf-8-sig")
    print(f"Wrote: {args.out_dir / 'analysis.md'}")
    print(f"Wrote: {args.tables_dir}")
    print(f"Wrote: {args.figures_dir}")
    print(f"Wrote: {args.out_dir / 'by_strategy'}")


if __name__ == "__main__":
    main()
