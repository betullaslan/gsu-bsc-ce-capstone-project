"""Analyze LLM-generated test cases and write analysis artifacts.

Reads JSON outputs under `outputs/`, aggregates by prompting strategy, and produces
CSV/Markdown/PNG artifacts under `analysis/`.
"""

import argparse
import csv
import glob
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

BASE_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = BASE_DIR / "src"
ANALYZE_DIR = SRC_DIR / "analyze"

# Make the repo modules importable when invoked as a standalone script.
for p in (BASE_DIR, SRC_DIR, ANALYZE_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from src.analyze.test_generation_config import (
    DETAILED_CSV_PATH,
    FIGURES_DIR,
    OUTPUTS_DIR,
    SCENARIO_SUMMARY_CSV_PATH,
    SCENARIOS_DATASET,
    SUMMARY_CSV_PATH,
    SUMMARY_MD_PATH,
    WARNING_SUMMARY_CSV_PATH,
)
from src.analyze.test_generation_figures import write_figures
from src.analyze.test_generation_report import (
    write_detailed_csv,
    write_scenario_summary_csv,
    write_summary_csv,
    write_summary_text_and_ranking,
    write_warning_summary_csv,
)
from src.analyze.test_generation_utils import (
    _as_bool,
    _as_float,
    _clamp01,
    _join_warning_types,
    _join_warnings,
    _stability_from_warnings,
)


def _read_csv_rows(path: Path) -> List[Dict[str, str]]:
    """Read CSV rows or return empty list when file is missing."""
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return [dict(r) for r in reader]


def _self_check_hallucination_rules() -> None:
    """Run deterministic sanity checks for hallucination scoring rules."""
    src_dir = BASE_DIR / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))
    import quality_rules

    # Deterministic smoke-test for hallucination rules to catch regressions early.
    scenario = {
        "scenario": "Self-check: hallucination rules",
        "background": [],
        "steps": [
            {"keyword": "When", "text": 'I run "ticket show abc-1234"', "type": "when"},
            {"keyword": "Then", "text": "the command should succeed", "type": "then"},
            {"keyword": "And", "text": 'the output should contain "id: abc-1234"', "type": "then"},
        ],
    }
    parsed_ok = {
        "preconditions": [],
        "steps": ['Run "ticket show abc-1234"'],
        "expected_results": ['Exit/status code is 0', 'Output contains "id: abc-1234"'],
    }
    score, details = quality_rules.compute_hallucination_score(scenario, parsed_ok)
    assert details.get("hallucinated_items", 0) == 0
    assert score == 1.0

    parsed_bad = {
        "preconditions": [],
        "steps": ['Run "ticket show abc-1234"'],
        "expected_results": [
            'Exit/status code is 0',
            'Output contains "id: abc-1234"',
            "Output contains name: Test ticket",
            "Output contains status: open",
        ],
    }
    score2, details2 = quality_rules.compute_hallucination_score(scenario, parsed_bad)
    assert details2.get("hallucinated_items", 0) >= 1
    assert score2 < 1.0
    print("OK: hallucination rules self-check passed.")


def _iter_output_files() -> List[Path]:
    """Discover generated scenario output JSON files across known folders."""
    patterns = [
        str(OUTPUTS_DIR / "llm_test_generation" / "SCN-*.json"),

        str(OUTPUTS_DIR / "generated_tests" / "SCN-*.json"),

        str(OUTPUTS_DIR / "**" / "SCN-*.json"),
    ]
    paths: List[Path] = []
    for pattern in patterns:
        paths.extend([Path(p) for p in glob.glob(pattern, recursive=True)])


    unique: Dict[str, Path] = {}
    for p in paths:
        unique[str(p.resolve())] = p
    paths = list(unique.values())
    return sorted(paths, key=lambda p: (p.name, str(p.parent)))


def _critical_errors_from_parsed(parsed: Dict[str, Any]) -> List[str]:
    """Infer critical format errors from parsed test-case structure."""
    critical: List[str] = []
    if not (parsed.get("steps") or []):
        critical.append("missing_test_steps")
    if not (parsed.get("expected_results") or []):
        critical.append("missing_expected_results")
    if (
        not (parsed.get("preconditions") or [])
        and not (parsed.get("steps") or [])
        and not (parsed.get("expected_results") or [])
    ):
        critical.append("empty_test_case")
    return critical


def _load_scenarios_by_id() -> Dict[str, Dict[str, Any]]:
    """Load scenarios dataset and index by scenario id."""
    payload = json.loads(SCENARIOS_DATASET.read_text(encoding="utf-8"))
    scenarios = payload.get("scenarios") or []
    out: Dict[str, Dict[str, Any]] = {}
    for s in scenarios:
        sid = str(s.get("id") or "").strip()
        if sid:
            out[sid] = s
    return out


def read_rows(model_filter: str = "", recompute_eval: bool = False) -> List[Dict[str, Any]]:
    """Read all generated test-case outputs into flat per-strategy rows for analysis."""
    rows: List[Dict[str, Any]] = []

    # Used when recomputing evaluation to re-check grounding and literal preservation.
    scenarios_by_id: Dict[str, Dict[str, Any]] = _load_scenarios_by_id()
    compute_quality_metrics = None
    enrich_warnings = None
    normalize_public_warnings = None
    validate_constraints = None
    validate_semantic_quality = None

    if recompute_eval:
        # Optional: recompute evaluation instead of trusting metrics stored in the JSON outputs.
        sys.path.insert(0, str(BASE_DIR / "src"))
        from quality_metrics import compute_quality_metrics as _cqm
        from quality_rules import (
            enrich_warnings as _ew,
            normalize_public_warnings as _npw,
            validate_constraints as _vc,
            validate_semantic_quality as _vsq,
        )

        compute_quality_metrics = _cqm
        enrich_warnings = _ew
        normalize_public_warnings = _npw
        validate_constraints = _vc
        validate_semantic_quality = _vsq

    for path in _iter_output_files():
        payload = json.loads(path.read_text(encoding="utf-8"))

        scenario_id = str(payload.get("scenario_id") or "").strip()
        scenario_name = str(payload.get("scenario_name") or "").strip()
        model_name = str(payload.get("model") or "").strip()
        _ = model_filter

        results = payload.get("results") or []
        if not isinstance(results, list):
            continue

        for result in results:
            if not isinstance(result, dict):
                continue

            strategy = str(result.get("strategy") or "").strip()
            response_time_seconds = _as_float(result.get("response_time_seconds"))

            if (
                recompute_eval
                and compute_quality_metrics
                and enrich_warnings
                and normalize_public_warnings
                and validate_constraints
                and validate_semantic_quality
            ):
                scenario_obj = scenarios_by_id.get(scenario_id, {})

                parsed_tc = result.get("test_case") or {}
                if not isinstance(parsed_tc, dict):
                    parsed_tc = {}
                parsed_tc.setdefault("preconditions", [])
                parsed_tc.setdefault("steps", [])
                parsed_tc.setdefault("expected_results", [])

                critical_errors = _critical_errors_from_parsed(parsed_tc)

                warnings_raw: List[str] = []
                warnings_raw.extend(validate_constraints(strategy, parsed_tc))
                semantic_warnings, semantic_details = validate_semantic_quality(scenario_obj, parsed_tc)
                warnings_raw.extend([w for w in semantic_warnings if w not in warnings_raw])

                warnings_public = normalize_public_warnings(warnings_raw)
                warnings = enrich_warnings(warnings_public)
                qm = compute_quality_metrics(
                    critical_errors=critical_errors,
                    warnings=warnings_public,
                    scenario=scenario_obj,
                    parsed=parsed_tc,
                    semantic_details=semantic_details,
                    postprocess=None,
                    include_debug_metrics=False,
                )
                is_valid = len(critical_errors) == 0



                if not is_valid:
                    quality_status = "invalid"
                elif any(w.get("severity") == "high" for w in (warnings or []) if isinstance(w, dict)):
                    quality_status = "needs_review"
                elif warnings_public:
                    quality_status = "clean_with_warnings"
                else:
                    quality_status = "clean"

                validation = {
                    "is_valid": is_valid,
                    "quality_status": quality_status,
                    "warning_count": len(warnings_public),
                    "warning_types": warnings_public,
                }
            else:
                validation = result.get("validation") or {}
                if not isinstance(validation, dict):
                    validation = {}

                is_valid = _as_bool(validation.get("is_valid"))
                warnings = validation.get("warnings")

                qm = validation.get("quality_metrics") or {}
                if not isinstance(qm, dict):
                    qm = {}

            stability = _stability_from_warnings(warnings)

            completeness = _as_float(qm.get("completeness"))
            if completeness is None:
                completeness = _as_float(qm.get("completeness_score"))
            traceability = _as_float(qm.get("traceability"))
            if traceability is None:
                traceability = _as_float(qm.get("traceability_score"))
            specificity = _as_float(qm.get("specificity"))
            if specificity is None:
                specificity = _as_float(qm.get("specificity_score"))
            hallucination = _as_float(qm.get("hallucination"))
            if hallucination is None:
                hallucination = _as_float(qm.get("hallucination_score"))
            semantic_coverage = _as_float(qm.get("semantic_coverage"))
            if semantic_coverage is None:
                semantic_coverage = _as_float(qm.get("semantic_quality"))

            quality_status = str(validation.get("quality_status") or "").strip()
            warning_types = _join_warning_types(validation.get("warning_types"))
            if not warning_types:

                warning_types = _join_warnings(warnings)
            warning_count = int(validation.get("warning_count") or 0)
            generation_attempts = int(result.get("generation_attempts") or 0)

            warning_count_effective = warning_count
            if warning_count_effective == 0 and isinstance(warnings, list):
                warning_count_effective = len(warnings)

            rows.append(
                {
                    "scenario_id": scenario_id,
                    "scenario_name": scenario_name,
                    "strategy": strategy,
                    "model": model_name,
                    "response_time_seconds": response_time_seconds,
                    "generation_attempts": generation_attempts,
                    "validation": {
                        "is_valid": bool(is_valid),
                        "quality_status": quality_status,
                        "warning_count": int(warning_count_effective),
                        "warning_types": warning_types,
                        "warnings": warnings if isinstance(warnings, list) else [],
                        "quality_metrics": {
                            "completeness": completeness,
                            "traceability": traceability,
                            "specificity": specificity,
                            "hallucination": hallucination,
                            "semantic_coverage": semantic_coverage,
                            "stability": stability,
                            "speed": None,
                            "final_score": None,
                        },
                    },
                    "is_valid": bool(is_valid),
                    "quality_status": quality_status,
                    "warning_types": warning_types,
                    "warning_count": int(warning_count_effective),
                    "completeness": completeness,
                    "traceability": traceability,
                    "specificity": specificity,
                    "hallucination": hallucination,
                    "semantic_coverage": semantic_coverage,
                    "stability": stability,
                    "speed": None,
                    "final_score": None,
                }
            )

    by_scenario: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        key = str(row.get("scenario_id") or "")
        by_scenario.setdefault(key, []).append(row)

    for _, group in by_scenario.items():
        times = [
            _as_float(r.get("response_time_seconds"))
            for r in group
            if _as_float(r.get("response_time_seconds")) and _as_float(r.get("response_time_seconds")) > 0
        ]
        fastest_time = min(times) if times else None
        for r in group:
            t = _as_float(r.get("response_time_seconds"))
            if fastest_time is None or t is None or t <= 0:
                r["speed"] = 0.0
            else:
                r["speed"] = round(_clamp01(float(fastest_time) / float(t)), 3)

            validation_obj = r.get("validation") if isinstance(r.get("validation"), dict) else {}
            qm_obj = (
                validation_obj.get("quality_metrics")
                if isinstance(validation_obj.get("quality_metrics"), dict)
                else {}
            )
            qm_obj["speed"] = r.get("speed")

            comp = _as_float(qm_obj.get("completeness")) or 0.0
            trac = _as_float(qm_obj.get("traceability")) or 0.0
            spec = _as_float(qm_obj.get("specificity")) or 0.0
            hall = _as_float(qm_obj.get("hallucination")) or 0.0
            semcov = _as_float(qm_obj.get("semantic_coverage")) or 0.0
            stab = _as_float(qm_obj.get("stability")) or 0.0
            spd = _as_float(qm_obj.get("speed")) or 0.0

            r["final_score"] = round(
                0.20 * comp
                + 0.20 * trac
                + 0.15 * spec
                + 0.20 * semcov
                + 0.15 * hall
                + 0.05 * stab
                + 0.05 * spd,
                3,
            )
            qm_obj["final_score"] = r.get("final_score")

            validation_obj["quality_metrics"] = qm_obj
            r["validation"] = validation_obj

    return rows


def main() -> None:
    """CLI entrypoint for test-generation analysis."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=["extract", "summarize", "all"],
        default="all",
    )
    parser.add_argument("--model", type=str, default="")
    parser.add_argument("--recompute-eval", action="store_true")
    parser.add_argument("--self-check-hallucination", action="store_true")
    args = parser.parse_args()

    if bool(args.self_check_hallucination):
        _self_check_hallucination_rules()
        return

    if args.mode in {"extract", "all"}:
        # Extract/aggregate data and write tables + figures for the current outputs snapshot.
        rows = read_rows(model_filter=args.model.strip(), recompute_eval=bool(args.recompute_eval))
        write_detailed_csv(rows)
        write_summary_csv(rows)
        write_warning_summary_csv(rows)
        write_scenario_summary_csv(rows)

        strategy_rows_any: List[Dict[str, Any]] = []
        if SUMMARY_CSV_PATH.exists():
            strategy_rows_any = [dict(r) for r in _read_csv_rows(SUMMARY_CSV_PATH)]
        write_figures(strategy_rows_any, rows)
        print(f"Wrote: {DETAILED_CSV_PATH}")
        print(f"Wrote: {SUMMARY_CSV_PATH}")
        print(f"Wrote: {WARNING_SUMMARY_CSV_PATH}")
        print(f"Wrote: {SCENARIO_SUMMARY_CSV_PATH}")
        print(f"Wrote: {FIGURES_DIR}")

    if args.mode in {"summarize", "all"}:
        # Write the Markdown report and ranking based on the existing summary tables.
        write_summary_text_and_ranking(model_filter=args.model.strip())
        print(f"Wrote: {SUMMARY_MD_PATH}")


if __name__ == "__main__":
    main()
