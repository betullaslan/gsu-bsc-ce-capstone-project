"""Generate test cases from scenarios using multiple prompting strategies.

Outputs are written under `outputs/llm_test_generation/` as one JSON file per scenario.
"""

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

import sys

BASE_DIR = Path(__file__).resolve().parent.parent

# Default input/output locations for generated artifacts.
INPUT_PATH = BASE_DIR / "data" / "scenarios_dataset.json"
OUTPUTS_DIR = BASE_DIR / "outputs"
GENERATED_DIR = OUTPUTS_DIR / "llm_test_generation"
NUM_SCENARIOS = 0

STRATEGIES = [
    "zero_shot_prompting",
    "few_shot_prompting",
    "instruction_based_prompting",
    "constraint_prompting",
    "step_by_step_prompting",
]


def _clamp01(value: float) -> float:
    """Clamp numeric value to [0, 1]."""
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return float(value)


def _warning_severity_counts(warnings: Any) -> Dict[str, int]:
    """Count low/medium/high severities from warning payload."""
    low = 0
    medium = 0
    high = 0
    if warnings is None:
        return {"low": 0, "medium": 0, "high": 0}

    items = warnings if isinstance(warnings, list) else [warnings]
    for w in items:
        if isinstance(w, dict):
            sev = str(w.get("severity") or "medium").strip().lower()
        else:
            sev = "medium"
        if sev == "low":
            low += 1
        elif sev == "high":
            high += 1
        else:
            medium += 1
    return {"low": low, "medium": medium, "high": high}


def _stability_from_warnings(warnings: Any) -> float:
    """Compute stability score from weighted warning severities."""
    counts = _warning_severity_counts(warnings)
    weighted = counts["low"] * 0.25 + counts["medium"] * 0.50 + counts["high"] * 1.00
    return round(1.0 / (1.0 + float(weighted)), 3)


def _as_float(value: Any) -> float | None:
    """Convert value to float when possible."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except ValueError:
        return None


def _compute_final_scores(results: List[Dict[str, Any]]) -> None:
    """Compute and store final score per strategy result item."""
    # Normalize timing-based speed within the current scenario (fastest strategy wins).
    times = [
        _as_float((r or {}).get("response_time_seconds"))
        for r in results
        if (
            _as_float((r or {}).get("response_time_seconds"))
            and _as_float((r or {}).get("response_time_seconds")) > 0
        )
    ]
    fastest_time = min(times) if times else None

    for r in results:
        if not isinstance(r, dict):
            continue
        validation = r.get("validation") if isinstance(r.get("validation"), dict) else {}
        metrics = (
            validation.get("quality_metrics")
            if isinstance(validation.get("quality_metrics"), dict)
            else {}
        )

        t = _as_float(r.get("response_time_seconds"))
        if fastest_time is None or t is None or t <= 0:
            speed = 0.0
        else:
            speed = round(_clamp01(float(fastest_time) / float(t)), 3)

        comp = float(_as_float(metrics.get("completeness")) or 0.0)
        trac = float(_as_float(metrics.get("traceability")) or 0.0)
        spec = float(_as_float(metrics.get("specificity")) or 0.0)
        hall = float(_as_float(metrics.get("hallucination")) or 0.0)
        semcov = float(_as_float(metrics.get("semantic_coverage")) or 0.0)
        stab = float(_stability_from_warnings(validation.get("warnings")) or 0.0)
        spd = float(speed or 0.0)

        final_score = round(
            0.20 * comp
            + 0.20 * trac
            + 0.15 * spec
            + 0.20 * semcov
            + 0.15 * hall
            + 0.05 * stab
            + 0.05 * spd,
            3,
        )

        validation["final_score"] = final_score
        r["validation"] = validation


def generate_outputs(
    num_scenarios: int = NUM_SCENARIOS,
    start_scenario: int = 1,
    end_scenario: int = 0,
) -> None:
    """Generate test-case outputs for scenarios using all prompting strategies."""

    src_dir = BASE_DIR / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))
    from generation_flow import run_one_strategy
    from llm_runner import MODEL_NAME

    if not INPUT_PATH.exists():
        raise FileNotFoundError(f"Dataset file not found: {INPUT_PATH}")

    try:
        with INPUT_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in dataset: {e}")

    if not isinstance(data, dict) or "scenarios" not in data:
        raise ValueError("Dataset must contain 'scenarios' key")

    if not isinstance(data["scenarios"], list) or len(data["scenarios"]) == 0:
        raise ValueError("Dataset 'scenarios' must be non-empty list")

    for s in data["scenarios"]:
        if not s.get("id"):
            raise ValueError("Scenario missing required 'id' field")

    scenarios = data["scenarios"]
    start_index = max(int(start_scenario or 1), 1) - 1
    end_index = (
        len(scenarios)
        if int(end_scenario or 0) in (0, None)
        else min(int(end_scenario), len(scenarios))
    )
    pool = scenarios[start_index:end_index]

    selected_scenarios = pool
    if num_scenarios and int(num_scenarios) > 0:
        selected_scenarios = selected_scenarios[: max(0, int(num_scenarios))]

    GENERATED_DIR.mkdir(parents=True, exist_ok=True)

    total_outputs = 0

    def _log(msg: str) -> None:
        """Write a progress log line."""
        print(msg)

    def run_one(scenario_obj: Dict[str, Any], strategy_name: str) -> Dict[str, Any]:
        """Run generation pipeline for one scenario/strategy pair."""
        return run_one_strategy(
            scenario_obj=scenario_obj,
            strategy_name=strategy_name,
            enforce_output=True,
        )

    for scenario in selected_scenarios:
        scenario_results: List[Dict[str, Any]] = []

        for strategy in STRATEGIES:
            sid = scenario.get("id") or "?"
            _log(f"[RUN ] {sid} | {strategy}")
            result = run_one(scenario, strategy)
            scenario_results.append(result)
            total_outputs += 1
            status = "DONE"
            if isinstance(result, dict):
                if result.get("error"):
                    status = "FAIL"
                else:
                    validation = (
                        result.get("validation")
                        if isinstance(result.get("validation"), dict)
                        else {}
                    )
                    is_valid = bool(validation.get("is_valid"))
                    status = "PASS" if is_valid else "WARN"

                details: List[str] = []
                validation = (
                    result.get("validation")
                    if isinstance(result.get("validation"), dict)
                    else {}
                )
                if "is_valid" in validation:
                    details.append(f"valid={1 if bool(validation.get('is_valid')) else 0}")
                if isinstance(validation.get("final_score"), (int, float)):
                    details.append(f"score={float(validation.get('final_score')):.3f}")
                if isinstance(result.get("response_time_seconds"), (int, float)):
                    details.append(f"t={float(result.get('response_time_seconds')):.1f}s")

                suffix = f" | {' | '.join(details)}" if details else ""
                _log(f"[{status}] {sid} | {strategy}{suffix}")
            else:
                _log(f"[DONE] {sid} | {strategy}")

        out_path = GENERATED_DIR / f"{scenario['id']}.json"

        payload = {
            "model": MODEL_NAME,
            "scenario_id": scenario["id"],
            "scenario_name": scenario.get("scenario", ""),
            "results": scenario_results,
        }
        _compute_final_scores(payload["results"])
        out_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
    )

    print(f"\nWrote outputs under: {GENERATED_DIR}")
    print(f"Total outputs: {total_outputs}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--num-scenarios", type=int, default=NUM_SCENARIOS)
    parser.add_argument(
        "--start",
        type=int,
        default=1,
        help="1-based start scenario index (inclusive).",
    )
    parser.add_argument(
        "--end",
        type=int,
        default=0,
        help="1-based end scenario index (inclusive); 0 means to the end.",
    )
    args = parser.parse_args()
    try:
        generate_outputs(
            num_scenarios=args.num_scenarios,
            start_scenario=args.start,
            end_scenario=args.end,
        )
    except Exception as e:
        print(f"Error: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
