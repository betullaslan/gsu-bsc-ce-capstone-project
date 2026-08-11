"""Markdown/CSV report writers for test-generation analysis."""

import csv
import sys
from pathlib import Path
from typing import Any, Dict, List

from test_generation_config import (
    DETAILED_COLUMNS,
    DETAILED_CSV_PATH,
    SCENARIO_SUMMARY_CSV_PATH,
    SUMMARY_COLUMNS,
    SUMMARY_CSV_PATH,
    SUMMARY_MD_PATH,
    TABLES_DIR,
    WARNING_SUMMARY_CSV_PATH,
)
from test_generation_utils import (
    _as_bool,
    _as_float,
    _as_int,
    _avg,
    _bootstrap_mean_ci95,
    _join_warning_types,
    _median,
    _percentile,
    _safe_div,
    _std,
)


def write_detailed_csv(rows: List[Dict[str, Any]]) -> None:
    """Write the detailed scenario x strategy table (`results_detailed.csv`)."""
    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    with DETAILED_CSV_PATH.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=DETAILED_COLUMNS)
        writer.writeheader()
        for r in rows:
            validation = r.get("validation") if isinstance(r.get("validation"), dict) else {}
            metrics = (
                validation.get("quality_metrics")
                if isinstance(validation.get("quality_metrics"), dict)
                else {}
            )
            scenario = r.get("scenario") if isinstance(r.get("scenario"), dict) else {}
            scenario_id = str(r.get("scenario_id") or scenario.get("id") or "")
            scenario_name = str(r.get("scenario_name") or scenario.get("scenario") or "")

            writer.writerow(
                {
                    "scenario_id": scenario_id,
                    "scenario_name": scenario_name,
                    "strategy": str(r.get("strategy") or ""),
                    "model": str(r.get("model") or ""),
                    "response_time_seconds": _as_float(r.get("response_time_seconds")) or 0.0,
                    "generation_attempts": _as_int(r.get("generation_attempts")) or 0,
                    "is_valid": bool(_as_bool(validation.get("is_valid"))),
                    "quality_status": str(validation.get("quality_status") or ""),
                    "warning_types": _join_warning_types(validation.get("warnings")),
                    "warning_count": int(_as_int(validation.get("warning_count")) or 0),
                    "completeness": float(_as_float(metrics.get("completeness")) or 0.0),
                    "traceability": float(_as_float(metrics.get("traceability")) or 0.0),
                    "specificity": float(_as_float(metrics.get("specificity")) or 0.0),
                    "hallucination": float(_as_float(metrics.get("hallucination")) or 0.0),
                    "semantic_coverage": float(_as_float(metrics.get("semantic_coverage")) or 0.0),
                    "stability": float(_as_float(metrics.get("stability")) or 0.0),
                    "speed": float(_as_float(metrics.get("speed")) or 0.0),
                    "final_score": float(_as_float(metrics.get("final_score")) or 0.0),
                }
            )


def write_summary_csv(rows: List[Dict[str, Any]]) -> None:
    """Write strategy-level summary metrics (`results_by_strategy.csv`)."""
    TABLES_DIR.mkdir(parents=True, exist_ok=True)

    # Group per-strategy so we can compute aggregate statistics for each prompt style.
    by_strategy: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        strat = str(r.get("strategy") or "")
        by_strategy.setdefault(strat, []).append(r)

    out_rows: List[Dict[str, Any]] = []
    for strategy, items in by_strategy.items():
        times = [_as_float(x.get("response_time_seconds")) for x in items]
        warn_counts = [
            _as_int(
                (
                    (x.get("validation") or {})
                    if isinstance(x.get("validation"), dict)
                    else {}
                ).get("warning_count")
            )
            for x in items
        ]

        valid = 0
        clean = 0
        clean_with_warnings = 0
        needs_review = 0
        invalid = 0

        attempts = []
        completeness = []
        traceability = []
        specificity = []
        hallucination = []
        semantic_coverage = []
        stability = []
        speed = []
        final_score = []

        for x in items:
            validation = x.get("validation") if isinstance(x.get("validation"), dict) else {}
            metrics = (
                validation.get("quality_metrics")
                if isinstance(validation.get("quality_metrics"), dict)
                else {}
            )

            if _as_bool(validation.get("is_valid")):
                valid += 1
            status = str(validation.get("quality_status") or "")
            if status == "clean":
                clean += 1
            elif status == "clean_with_warnings":
                clean_with_warnings += 1
            elif status == "needs_review":
                needs_review += 1
            elif status == "invalid":
                invalid += 1

            attempts.append(_as_float(x.get("generation_attempts")))
            completeness.append(_as_float(metrics.get("completeness")))
            traceability.append(_as_float(metrics.get("traceability")))
            specificity.append(_as_float(metrics.get("specificity")))
            hallucination.append(_as_float(metrics.get("hallucination")))
            semantic_coverage.append(_as_float(metrics.get("semantic_coverage")))
            stability.append(_as_float(metrics.get("stability")))
            speed.append(_as_float(metrics.get("speed")))
            final_score.append(_as_float(metrics.get("final_score")))

        valid_rate = _safe_div(valid, len(items))
        clean_rate = _safe_div(clean, len(items))
        clean_with_warnings_rate = _safe_div(clean_with_warnings, len(items))
        needs_review_rate = _safe_div(needs_review, len(items))
        invalid_rate = _safe_div(invalid, len(items))

        fs = [x for x in final_score if x is not None]
        ci_low, ci_high = _bootstrap_mean_ci95([float(x) for x in fs]) if fs else (0.0, 0.0)

        out_rows.append(
            {
                "strategy": strategy,
                "avg_response_time_seconds": round(float(_avg(times) or 0.0), 6),
                "median_response_time_seconds": round(float(_median(times)), 6),
                "p95_response_time_seconds": round(float(_percentile(times, 95.0)), 6),
                "std_response_time_seconds": round(float(_std(times) or 0.0), 6),
                "avg_warning_count": round(
                    float(
                        _avg([float(x) if x is not None else None for x in warn_counts])
                        or 0.0
                    ),
                    3,
                ),
                "valid_rate": round(float(valid_rate), 3),
                "clean_rate": round(float(clean_rate), 3),
                "clean_with_warnings_rate": round(float(clean_with_warnings_rate), 3),
                "needs_review_rate": round(float(needs_review_rate), 3),
                "invalid_rate": round(float(invalid_rate), 3),
                "avg_generation_attempts": round(float(_avg(attempts) or 0.0), 3),
                "avg_completeness": round(float(_avg(completeness) or 0.0), 3),
                "avg_traceability": round(float(_avg(traceability) or 0.0), 3),
                "avg_specificity": round(float(_avg(specificity) or 0.0), 3),
                "avg_hallucination": round(float(_avg(hallucination) or 0.0), 3),
                "avg_semantic_coverage": round(float(_avg(semantic_coverage) or 0.0), 3),
                "avg_stability": round(float(_avg(stability) or 0.0), 3),
                "avg_speed": round(float(_avg(speed) or 0.0), 3),
                "avg_final_score": round(float(_avg(final_score) or 0.0), 3),
                "avg_final_score_ci_low": round(float(ci_low), 3),
                "avg_final_score_ci_high": round(float(ci_high), 3),
                "median_final_score": round(float(_median(final_score)), 3),
                "std_final_score": round(float(_std(final_score) or 0.0), 3),
            }
        )

    with SUMMARY_CSV_PATH.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=SUMMARY_COLUMNS)
        writer.writeheader()
        for r in out_rows:
            writer.writerow(r)


def _read_csv_rows(path: Path) -> List[Dict[str, str]]:
    """Read a CSV file as list of dict rows, returning [] if missing."""
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return [dict(r) for r in reader]


def write_scenario_summary_csv(rows: List[Dict[str, Any]]) -> None:
    """Write scenario-level summary metrics (`results_by_scenario.csv`)."""
    TABLES_DIR.mkdir(parents=True, exist_ok=True)

    by_scenario: Dict[str, List[Dict[str, Any]]] = {}
    scenario_names: Dict[str, str] = {}

    for r in rows:
        scenario = r.get("scenario") if isinstance(r.get("scenario"), dict) else {}
        sid = str(r.get("scenario_id") or scenario.get("id") or "").strip()
        if not sid:
            continue
        scenario_name = str(r.get("scenario_name") or scenario.get("scenario") or "").strip()
        if scenario_name:
            scenario_names[sid] = scenario_name
        by_scenario.setdefault(sid, []).append(r)

    out_rows: List[Dict[str, Any]] = []
    def _fmt3(value: Any) -> str:
        """Format a numeric-like value to 3 decimals or empty string."""
        v = _as_float(value)
        if v is None:
            return ""
        return f"{float(v):.3f}"

    for sid, items in sorted(by_scenario.items(), key=lambda kv: kv[0]):
        scenario_name = str(scenario_names.get(sid) or "")

        final_values: List[float] = []
        resp_values: List[float] = []
        warning_counts: List[float] = []
        valid_count = 0

        for x in items:
            validation = x.get("validation") if isinstance(x.get("validation"), dict) else {}
            metrics = (
                validation.get("quality_metrics")
                if isinstance(validation.get("quality_metrics"), dict)
                else {}
            )

            fs = _as_float(x.get("final_score"))
            if fs is None:
                fs = _as_float(metrics.get("final_score"))
            if fs is not None:
                final_values.append(float(fs))

            rt = _as_float(x.get("response_time_seconds"))
            if rt is not None:
                resp_values.append(float(rt))

            wc = _as_int(x.get("warning_count"))
            if wc is None:
                wc = _as_int(validation.get("warning_count"))
            if wc is None:
                wc = _as_int(metrics.get("warning_count"))
            warning_counts.append(float(int(wc or 0)))

            iv = x.get("is_valid")
            if iv is None:
                iv = validation.get("is_valid")
            if _as_bool(iv):
                valid_count += 1

        n = len(items)
        avg_final_score = _avg([_as_float(v) for v in final_values])
        avg_warning_count = _avg([_as_float(v) for v in warning_counts])
        avg_response_time_seconds = _avg([_as_float(v) for v in resp_values])
        valid_rate = _safe_div(valid_count, n)
        out_rows.append(
            {
                "scenario_id": sid,
                "scenario_name": scenario_name,
                "n": n,
                "avg_final_score": _fmt3(avg_final_score),
                "valid_rate": _fmt3(valid_rate),
                "avg_warning_count": _fmt3(avg_warning_count),
                "avg_response_time_seconds": _fmt3(avg_response_time_seconds),
            }
        )

    fieldnames = [
        "scenario_id",
        "scenario_name",
        "n",
        "avg_final_score",
        "valid_rate",
        "avg_warning_count",
        "avg_response_time_seconds",
    ]

    with SCENARIO_SUMMARY_CSV_PATH.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in out_rows:
            writer.writerow({k: r.get(k) for k in fieldnames})


def write_summary_text_and_ranking(model_filter: str = "") -> None:
    """Write the main Markdown summary report and strategy ranking.

    This is the source of `analysis/llm_test_generation/analysis.md`.
    """
    if not SUMMARY_CSV_PATH.exists():
        raise SystemExit(f"Missing: {SUMMARY_CSV_PATH}")

    strategy_rows = _read_csv_rows(SUMMARY_CSV_PATH)
    if not strategy_rows:
        SUMMARY_MD_PATH.write_text("# Experiment Analysis Summary\n\nNo data available.\n", encoding="utf-8")
        return

    detailed_rows: List[Dict[str, str]] = []
    if DETAILED_CSV_PATH.exists():
        detailed_rows = _read_csv_rows(DETAILED_CSV_PATH)

    scenario_ids = {r.get("scenario_id", "").strip() for r in detailed_rows if r.get("scenario_id")}
    total_scenarios = len([s for s in scenario_ids if s])
    total_test_cases = len(detailed_rows)
    models = {r.get("model", "").strip() for r in detailed_rows if r.get("model")}

    parsed: List[Dict[str, Any]] = []
    for r in strategy_rows:
        parsed.append(
            {
                "strategy": (r.get("strategy") or "").strip(),
                "avg_response_time_seconds": _as_float(r.get("avg_response_time_seconds")),
                "median_response_time_seconds": _as_float(r.get("median_response_time_seconds")),
                "p95_response_time_seconds": _as_float(r.get("p95_response_time_seconds")),
                "avg_warning_count": _as_float(r.get("avg_warning_count")),
                "avg_completeness": _as_float(r.get("avg_completeness")),
                "avg_traceability": _as_float(r.get("avg_traceability")),
                "avg_specificity": _as_float(r.get("avg_specificity")),
                "avg_hallucination": _as_float(r.get("avg_hallucination")),
                "avg_semantic_coverage": _as_float(r.get("avg_semantic_coverage")),
                "avg_stability": _as_float(r.get("avg_stability")),
                "avg_speed": _as_float(r.get("avg_speed")),
                "avg_final_score": _as_float(r.get("avg_final_score")),
                "avg_final_score_ci_low": _as_float(r.get("avg_final_score_ci_low")),
                "avg_final_score_ci_high": _as_float(r.get("avg_final_score_ci_high")),
                "median_final_score": _as_float(r.get("median_final_score")),
                "std_final_score": _as_float(r.get("std_final_score")),
                "valid_rate": _as_float(r.get("valid_rate")),
                "clean_rate": _as_float(r.get("clean_rate")),
                "needs_review_rate": _as_float(r.get("needs_review_rate")),
                "avg_generation_attempts": _as_float(r.get("avg_generation_attempts")),
            }
        )

    def best_by(field: str, higher_is_better: bool) -> Dict[str, Any]:
        """Pick best strategy row by a numeric field."""
        candidates = [p for p in parsed if isinstance(p.get(field), (int, float))]
        if not candidates:
            return {"strategy": "", field: None}
        key_fn = lambda x: x[field]
        return max(candidates, key=key_fn) if higher_is_better else min(candidates, key=key_fn)

    def fmt(v: Any) -> str:
        """Format values for report display."""
        if v is None:
            return "N/A"
        if isinstance(v, (int, float)):
            return f"{float(v):.3f}"
        return str(v)

    def _pick_strength(strategy_name: str) -> str:
        """Return the primary strength label for a strategy."""
        fastest_name = best_by("avg_response_time_seconds", higher_is_better=False).get("strategy", "")
        cleanest_name = best_by("clean_rate", higher_is_better=True).get("strategy", "")
        semcov_name = best_by("avg_semantic_coverage", higher_is_better=True).get("strategy", "")
        hall_name = best_by("avg_hallucination", higher_is_better=True).get("strategy", "")
        final_name = best_by("avg_final_score", higher_is_better=True).get("strategy", "")
        if strategy_name == final_name:
            return "Final score"
        if strategy_name == fastest_name:
            return "Speed"
        if strategy_name == cleanest_name:
            return "Clean rate"
        if strategy_name == semcov_name:
            return "Semantic coverage"
        if strategy_name == hall_name:
            return "Hallucination score"
        return "Balanced"

    def _best_line(label: str, field: str, higher_is_better: bool) -> str:
        """Build a markdown line describing the best strategy for a metric."""
        b = best_by(field, higher_is_better=higher_is_better)
        name = str(b.get("strategy") or "")
        val = b.get(field)
        if not name or not isinstance(val, (int, float)):
            return f"- {label}: N/A"
        return f"- {label}: `{name}` ({field}={float(val):.3f})"

    def _warning_action(warning_type: str) -> str:
        """Map warning type to a short remediation suggestion."""
        actions = {
            "generic_expected_result": "force concrete assertions (exact literals, measurable outcomes).",
            "missing_literal_value": (
                "require literal values (IDs, exact strings, numbers) in steps/expected results."
            ),
            "irrelevant_or_invented_step": "tighten grounding: only allow steps traceable to the scenario.",
            "unsupported_precondition": "avoid preconditions not present in the scenario/background.",
            "missing_when_action_literal": (
                "ensure the 'When' action includes the concrete command/input literal."
            ),
        }
        return actions.get(warning_type, "review prompts/constraints to reduce this warning type.")

    for p in parsed:
        if p.get("invalid_rate") is None and isinstance(p.get("valid_rate"), (int, float)):
            p["invalid_rate"] = 1.0 - float(p["valid_rate"] or 0.0)

    ranked = sorted(parsed, key=lambda x: float(x.get("avg_final_score") or 0.0), reverse=True)

    warning_rows: List[Dict[str, Any]] = []
    if WARNING_SUMMARY_CSV_PATH.exists():
        for r in _read_csv_rows(WARNING_SUMMARY_CSV_PATH):
            warning_rows.append(
                {
                    "warning_type": (r.get("warning_type") or "").strip(),
                    "severity": (r.get("severity") or "").strip(),
                    "count": _as_int(r.get("count")) or 0,
                    "most_common_strategy": (r.get("most_common_strategy") or "").strip(),
                }
            )
    else:
        counts: Dict[str, int] = {}
        by_strategy: Dict[str, Dict[str, int]] = {}
        for dr in detailed_rows:
            strat = (dr.get("strategy") or "").strip()
            blob = str(dr.get("warning_types") or "")
            for wt in [x.strip() for x in blob.split("|") if x.strip()]:
                counts[wt] = counts.get(wt, 0) + 1
                by_strategy.setdefault(wt, {})
                by_strategy[wt][strat] = by_strategy[wt].get(strat, 0) + 1
        for wt, cnt in counts.items():
            strat_counts = by_strategy.get(wt, {})
            most_common = max(strat_counts.items(), key=lambda kv: kv[1])[0] if strat_counts else ""
            warning_rows.append(
                {
                    "warning_type": wt,
                    "severity": "medium",
                    "count": cnt,
                    "most_common_strategy": most_common,
                }
            )

    warning_rows = [r for r in warning_rows if r.get("warning_type")]
    warning_rows.sort(key=lambda r: int(r.get("count") or 0), reverse=True)

    lines: List[str] = []
    lines.append("# Test Generation Experiment - Analysis")
    lines.append("")
    lines.append("## Setup")
    lines.append("")
    lines.append(
        "- Counts are derived from `analysis/llm_test_generation/tables/results_detailed.csv` "
        "(unique `scenario_id` and total rows)."
    )
    lines.append(f"- Scenarios analyzed: **{total_scenarios}**")
    lines.append(f"- Generated test cases: **{total_test_cases}**")
    if models:
        lines.append(f"- Model(s): **{', '.join(sorted(models))}**")
    if model_filter:
        lines.append(f"- Model filter: **{model_filter}**")
    lines.append(f"- Strategies compared: **{len(parsed)}**")
    lines.append("")
    lines.append("## Scoring")
    lines.append("")
    lines.append("- `stability = 1 / (1 + (0.25*low + 0.50*medium + 1.00*high))`")
    lines.append("- `speed = fastest_time / time` (per scenario), clamped to `[0, 1]`")
    lines.append(
        "- `final_score = 0.20*completeness + 0.20*traceability + 0.15*specificity + "
        "0.20*semantic_coverage + 0.15*hallucination + 0.05*stability + 0.05*speed`"
    )
    lines.append("")
    lines.append("### Metric definitions (what the scores mean)")
    lines.append("")
    lines.append(
        "- `completeness`: penalizes missing required parts (e.g., too few expected results, "
        "missing key literals, missing preconditions/When/Then coverage)."
    )
    lines.append(
        "- `traceability`: measures whether key scenario literals are preserved in steps/expected results "
        "and whether expected results are linked to steps."
    )
    lines.append(
        "- `specificity`: rewards concrete, executable steps and concrete assertions (vs vague/generic text)."
    )
    lines.append("- `hallucination`: penalizes invented details not grounded in the scenario.")
    lines.append(
        "- `semantic_coverage`: composite semantic quality (executable steps, precondition mapping, "
        "literal preservation, step/result separation) with hard penalties for critical issues."
    )
    lines.append(
        "- `stability`: based only on warning severities (low/medium/high), independent of content length."
    )
    lines.append(
        "- `speed`: normalized per-scenario relative to the fastest strategy for that scenario; "
        "compare within the same run/hardware."
    )
    lines.append("")
    lines.append("### Quality status / rates")
    lines.append("")
    lines.append(
        "- `valid_rate`: fraction of generated test cases with no critical errors "
        "(e.g., missing steps/expected results)."
    )
    lines.append("- `clean_rate`: fraction with `quality_status == clean` (no warnings).")
    lines.append(
        "- `needs_review_rate`: fraction with `quality_status == needs_review` "
        "(at least one high-severity warning)."
    )
    lines.append("- `clean_with_warnings_rate`: tracked in CSV; warnings exist but none are high severity.")
    lines.append("")
    lines.append("## Executive summary")
    lines.append("")
    lines.append(_best_line("Best overall quality (avg final_score)", "avg_final_score", True))
    lines.append(_best_line("Cleanest outputs (clean_rate)", "clean_rate", True))
    lines.append(_best_line("Fastest typical (median response time)", "median_response_time_seconds", False))
    lines.append(_best_line("Fastest tail (p95 response time)", "p95_response_time_seconds", False))
    lines.append(_best_line("Most consistent scores (std final_score)", "std_final_score", False))
    lines.append(_best_line("Fewest warnings (avg warning_count)", "avg_warning_count", False))
    lines.append("")
    lines.append("## Ranking (avg `final_score`)")
    lines.append("")
    lines.append("| Rank | Strategy | Avg Final Score | Main Strength |")
    lines.append("|---:|---|---:|---|")
    for i, p in enumerate(ranked, start=1):
        s = str(p.get("strategy") or "")
        lines.append(f"| {i} | {s} | {fmt(p.get('avg_final_score'))} | {_pick_strength(s)} |")
    lines.append("")
    lines.append("![Final score by strategy](figures/final_score_by_strategy.png)")
    lines.append("")
    lines.append("## Strategy Comparison (key metrics)")
    lines.append("")
    lines.append(
        "| strategy | valid_rate | clean_rate | needs_review_rate | avg_final_score | "
        "avg_final_score_ci_low | avg_final_score_ci_high | median_final_score | "
        "avg_response_time_seconds | median_response_time_seconds | p95_response_time_seconds | "
        "avg_generation_attempts | avg_warning_count |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for p in ranked:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(p.get("strategy") or ""),
                    fmt(p.get("valid_rate")),
                    fmt(p.get("clean_rate")),
                    fmt(p.get("needs_review_rate")),
                    fmt(p.get("avg_final_score")),
                    fmt(p.get("avg_final_score_ci_low")),
                    fmt(p.get("avg_final_score_ci_high")),
                    fmt(p.get("median_final_score")),
                    fmt(p.get("avg_response_time_seconds")),
                    fmt(p.get("median_response_time_seconds")),
                    fmt(p.get("p95_response_time_seconds")),
                    fmt(p.get("avg_generation_attempts")),
                    fmt(p.get("avg_warning_count")),
                ]
            )
            + " |"
        )
    lines.append("")
    lines.append("![Metric profile by strategy](figures/metrics_by_strategy.png)")
    lines.append("![Quality status distribution](figures/quality_status_distribution.png)")
    lines.append("![Warning count by strategy](figures/warning_count_by_strategy.png)")
    lines.append("![Response time by strategy](figures/response_time_by_strategy.png)")
    lines.append("![Generation attempts by strategy](figures/generation_attempts_by_strategy.png)")
    lines.append("![Final score distribution by strategy](figures/final_score_distribution_by_strategy.png)")
    lines.append(
        "![Response time distribution by strategy]"
        "(figures/response_time_distribution_by_strategy.png)"
    )
    lines.append("")
    lines.append("## Warnings (top types)")
    lines.append("")
    lines.append("| warning_type | severity | count | % of test cases | most_common_strategy |")
    lines.append("|---|---|---:|---:|---|")
    denom = float(total_test_cases or 1)
    for r in warning_rows[:15]:
        cnt = int(r.get("count") or 0)
        pct = (cnt / denom) * 100.0
        lines.append(
            "| "
            + " | ".join(
                [
                    str(r.get("warning_type") or ""),
                    str(r.get("severity") or ""),
                    str(cnt),
                    f"{pct:.2f}%",
                    str(r.get("most_common_strategy") or ""),
                ]
            )
            + " |"
        )
    lines.append("")
    if warning_rows:
        lines.append("### What to fix first")
        lines.append("")
        for r in warning_rows[:3]:
            wt = str(r.get("warning_type") or "").strip()
            if not wt:
                continue
            lines.append(f"- `{wt}`: {_warning_action(wt)}")
    lines.append("")
    lines.append("## Takeaways")
    lines.append("")
    top = ranked[0]["strategy"] if ranked else ""
    second = ranked[1]["strategy"] if len(ranked) > 1 else ""
    best_hall = best_by("avg_hallucination", higher_is_better=True)
    if top:
        lines.append(f"- Default choice: `{top}` (best avg `final_score`).")
    if second:
        lines.append(f"- Close alternative: `{second}` (similar overall performance).")
    if best_hall.get("strategy"):
        lines.append(
            f"- Best hallucination score: `{best_hall.get('strategy')}` "
            "(interpret together with warnings/clean rate)."
        )
    lines.append("- Averages can hide variance; prefer the distribution boxplots for robustness checks.")
    lines.append("")
    lines.append("## Manual label breakdown")
    lines.append("")
    lines.append("- `by_manual_labels/analysis.md`")
    lines.append("")

    if SCENARIO_SUMMARY_CSV_PATH.exists():
        scenario_rows = _read_csv_rows(SCENARIO_SUMMARY_CSV_PATH)
        for r in scenario_rows:
            r["avg_final_score"] = _as_float(r.get("avg_final_score"))
            r["valid_rate"] = _as_float(r.get("valid_rate"))
            r["avg_warning_count"] = _as_float(r.get("avg_warning_count"))
        hardest = sorted(scenario_rows, key=lambda x: float(x.get("avg_final_score") or 0.0))[:10]
        if hardest:
            lines.append("## Hardest scenarios (across all strategies)")
            lines.append("")
            lines.append("| scenario_id | scenario_name | avg_final_score | valid_rate | avg_warning_count |")
            lines.append("|---|---|---:|---:|---:|")
            for r in hardest:
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            str(r.get("scenario_id") or ""),
                            str(r.get("scenario_name") or ""),
                            fmt(r.get("avg_final_score")),
                            fmt(r.get("valid_rate")),
                            fmt(r.get("avg_warning_count")),
                        ]
                    )
                    + " |"
                )
            lines.append("")
            lines.append("- Full list: `tables/results_by_scenario.csv`")
            lines.append("")

    lines.append("## Reproduce")
    lines.append("")
    lines.append("- Generate analysis + figures: `python scripts/analyze_test_generation.py`")
    lines.append("- Manual label breakdown: `python scripts/analyze_test_generation_by_class.py`")
    lines.append("")
    lines.append("## Outputs")
    lines.append("")
    lines.append("- `analysis/llm_test_generation/tables/results_detailed.csv`")
    lines.append("- `analysis/llm_test_generation/tables/results_by_strategy.csv`")
    lines.append("- `analysis/llm_test_generation/tables/results_by_scenario.csv`")
    if WARNING_SUMMARY_CSV_PATH.exists():
        lines.append("- `analysis/llm_test_generation/tables/warnings_by_type.csv`")
    lines.append("- `analysis/llm_test_generation/figures/`")
    lines.append("")

    SUMMARY_MD_PATH.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_MD_PATH.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def write_warning_summary_csv(rows: List[Dict[str, Any]]) -> None:
    """Write warning type counts and severities (`warnings_by_type.csv`)."""
    TABLES_DIR.mkdir(parents=True, exist_ok=True)

    counts: Dict[str, int] = {}
    severity_by_type: Dict[str, str] = {}
    by_type_strategy: Dict[str, Dict[str, int]] = {}

    total_warnings = 0
    total_test_cases = len(rows)

    base_dir = Path(__file__).resolve().parents[2]
    src_dir = base_dir / "src"
    sys.path.insert(0, str(src_dir))
    try:
        import quality_rules

        meta = getattr(quality_rules, "_WARNING_METADATA", {}) or {}
    finally:
        try:
            sys.path.remove(str(src_dir))
        except ValueError:
            pass

    for r in rows:
        strategy = str(r.get("strategy") or "").strip()
        validation = r.get("validation") if isinstance(r.get("validation"), dict) else {}
        items = validation.get("warnings") or []

        if items and isinstance(items, list):
            for w in items:
                if not isinstance(w, dict):
                    continue
                wt = str(w.get("type") or "").strip()
                if not wt:
                    continue
                sev = str(w.get("severity") or "medium").strip().lower()
                counts[wt] = counts.get(wt, 0) + 1
                severity_by_type.setdefault(wt, sev)
                by_type_strategy.setdefault(wt, {})
                by_type_strategy[wt][strategy] = by_type_strategy[wt].get(strategy, 0) + 1
                total_warnings += 1
            continue

        wt_blob = str(r.get("warning_types") or "").strip()
        if not wt_blob:
            wt_blob = str(validation.get("warning_types") or "").strip()
        if not wt_blob:
            continue
        for wt in [x.strip() for x in wt_blob.split("|") if x.strip()]:
            sev = "medium"
            if isinstance(meta, dict) and wt in meta:
                sev = str((meta.get(wt) or {}).get("severity") or "medium").strip().lower()
            counts[wt] = counts.get(wt, 0) + 1
            severity_by_type.setdefault(wt, sev)
            by_type_strategy.setdefault(wt, {})
            by_type_strategy[wt][strategy] = by_type_strategy[wt].get(strategy, 0) + 1
            total_warnings += 1

    out_rows: List[Dict[str, Any]] = []
    for wt, cnt in sorted(counts.items(), key=lambda x: x[1], reverse=True):
        strat_counts = by_type_strategy.get(wt) or {}
        most_common_strategy = ""
        if strat_counts:
            most_common_strategy = max(strat_counts.items(), key=lambda x: x[1])[0]
        pct_tc = (cnt / total_test_cases * 100.0) if total_test_cases else 0.0
        pct_all = (cnt / total_warnings * 100.0) if total_warnings else 0.0
        sev = severity_by_type.get(wt) or "medium"
        if (not sev or sev == "medium") and isinstance(meta, dict) and wt in meta:
            sev = str((meta.get(wt) or {}).get("severity") or "medium").strip().lower()
        out_rows.append(
            {
                "warning_type": wt,
                "severity": sev,
                "count": cnt,
                "percentage_of_test_cases": round(pct_tc, 2),
                "percentage_of_all_warnings": round(pct_all, 2),
                "most_common_strategy": most_common_strategy,
            }
        )

    with WARNING_SUMMARY_CSV_PATH.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "warning_type",
                "severity",
                "count",
                "percentage_of_test_cases",
                "percentage_of_all_warnings",
                "most_common_strategy",
            ],
        )
        writer.writeheader()
        for r in out_rows:
            writer.writerow(r)
