"""Classify scenarios into (test_level, test_type) using an LLM backend.

Writes both combined and per-strategy JSON outputs under `outputs/llm_classification/`.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from string import Template
from typing import Any, Dict, List, Tuple

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DATASET_PATH = BASE_DIR / "data" / "scenarios_dataset.json"
DEFAULT_OUT_PATH = BASE_DIR / "outputs" / "llm_classification" / "scenarios_classified_llm.json"
DEFAULT_OUT_BY_STRATEGY_DIR = BASE_DIR / "outputs" / "llm_classification"

# Supported label taxonomies for downstream evaluation/reporting.
TEST_LEVELS = ("Unit", "Integration", "System", "Acceptance")
TEST_TYPES = ("Functional", "Regression", "End-to-End", "Error Handling", "Performance", "Security")

DEFAULT_STRATEGY_TO_PROMPT_PATH: Dict[str, Path] = {
    "zero_shot": BASE_DIR / "prompts" / "llm_classification" / "zero_shot_prompting.txt",
    "instruction_based": BASE_DIR / "prompts" / "llm_classification" / "instruction_based_prompting.txt",
    "constraint": BASE_DIR / "prompts" / "llm_classification" / "constraint_prompting.txt",
    "step_by_step": BASE_DIR / "prompts" / "llm_classification" / "step_by_step_prompting.txt",
    "few_shot": BASE_DIR / "prompts" / "llm_classification" / "few_shot_prompting.txt",
}
DEFAULT_PRIMARY_STRATEGY = "instruction_based"


def _import_llm_runner() -> Any:
    """Temporarily load `src/llm_runner.py` and return the module."""
    src_dir = BASE_DIR / "src"
    sys.path.insert(0, str(src_dir))
    try:
        import llm_runner

        return llm_runner
    finally:
        try:
            sys.path.remove(str(src_dir))
        except ValueError:
            pass


def _format_steps(step_list: List[Dict[str, Any]] | None) -> str:
    """Render scenario steps as newline-separated `keyword text` lines."""
    if not step_list:
        return ""
    lines: List[str] = []
    for step in step_list:
        kw = str((step or {}).get("keyword") or "").strip()
        txt = str((step or {}).get("text") or "").strip()
        if not txt:
            continue
        lines.append(f"{kw} {txt}".strip())
    return "\n".join(lines).strip()


def _extract_first_json_object(text: str) -> Tuple[Dict[str, Any] | None, str | None]:
    """Parse the first JSON object from LLM output with fallback scanning."""
    raw = (text or "").strip()
    if not raw:
        return None, "Empty LLM response"

    # Fast path: response is already a JSON object.
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            return obj, None
    except Exception:
        pass

    # Fallback: locate and parse the first JSON object substring.
    start = raw.find("{")
    if start < 0:
        return None, "No JSON object start '{' found in LLM response"

    depth = 0
    in_str = False
    esc = False
    for i, ch in enumerate(raw[start:], start=start):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue

        if ch == '"':
            in_str = True
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                candidate = raw[start : i + 1]
                try:
                    obj2 = json.loads(candidate)
                except Exception as exc:
                    return None, f"Failed to parse JSON object: {exc}"
                if not isinstance(obj2, dict):
                    return None, "LLM JSON is not an object"
                return obj2, None

    return None, "Unbalanced JSON braces in LLM response"


def _get_first_str(obj: Dict[str, Any], keys: List[str]) -> str:
    """Return the first non-empty string value among candidate keys."""
    for k in keys:
        v = obj.get(k)
        if v is None:
            continue
        s = str(v).strip()
        if s != "":
            return s
    return ""


def _norm_key(s: str) -> str:
    """Normalize keys/labels for robust canonical matching."""
    return " ".join(str(s or "").strip().lower().replace("_", " ").split())


def _normalize_test_level(raw: str) -> str:
    """Normalize free-form test-level labels to taxonomy values."""
    s = _norm_key(raw)
    if not s:
        return ""
    direct = {
        "unit": "Unit",
        "integration": "Integration",
        "system": "System",
        "acceptance": "Acceptance",
    }
    if s in direct:
        return direct[s]

    variants = {

        "unit test": "Unit",
        "unit-level": "Unit",
        "unit level": "Unit",
        "unit testing": "Unit",

        "integration test": "Integration",
        "integration-level": "Integration",
        "integration level": "Integration",
        "integration testing": "Integration",

        "system test": "System",
        "system-level": "System",
        "system level": "System",
        "system testing": "System",

        "acceptance test": "Acceptance",
        "acceptance-level": "Acceptance",
        "acceptance level": "Acceptance",
        "acceptance testing": "Acceptance",
        "user acceptance test": "Acceptance",
        "uat": "Acceptance",
    }
    if s in variants:
        return variants[s]


    if "acceptance" in s or s == "uat":
        return "Acceptance"
    if "integration" in s:
        return "Integration"
    if "system" in s:
        return "System"
    if "unit" in s:
        return "Unit"
    return raw.strip()


def _normalize_test_type(raw: str) -> str:
    """Normalize free-form test-type labels to taxonomy values."""
    s = _norm_key(raw)
    if not s:
        return ""
    direct = {
        "functional": "Functional",
        "regression": "Regression",
        "end-to-end": "End-to-End",
        "end to end": "End-to-End",
        "e2e": "End-to-End",
        "error handling": "Error Handling",
        "performance": "Performance",
        "security": "Security",
    }
    if s in direct:
        return direct[s]

    variants = {
        "end-to-end test": "End-to-End",
        "end to end test": "End-to-End",
        "end-to-end testing": "End-to-End",
        "error": "Error Handling",
        "error-handling": "Error Handling",
        "error handling test": "Error Handling",
        "negative test": "Error Handling",
        "failure handling": "Error Handling",
        "functional test": "Functional",
        "functionality": "Functional",
        "regression test": "Regression",
        "regression testing": "Regression",
        "performance test": "Performance",
        "performance testing": "Performance",
        "latency": "Performance",
        "load test": "Performance",
        "security test": "Security",
        "security testing": "Security",
        "authorization": "Security",
        "authentication": "Security",
        "permission": "Security",
    }
    if s in variants:
        return variants[s]


    if "e2e" in s or ("end" in s and "to" in s and "end" in s):
        return "End-to-End"
    if "error" in s or "negative" in s or "failure" in s:
        return "Error Handling"
    if "regression" in s:
        return "Regression"
    if "performance" in s or "latency" in s or "load" in s:
        return "Performance"
    if "security" in s or "auth" in s or "permission" in s:
        return "Security"
    if "functional" in s:
        return "Functional"
    return raw.strip()


def _validate_classification(obj: Dict[str, Any]) -> Tuple[Dict[str, str], str | None]:
    """Validate and normalize classifier output into final label fields."""
    raw_level = _get_first_str(obj, ["test_level", "level", "testLevel", "test level"])
    raw_type = _get_first_str(obj, ["test_type", "type", "testType", "test type"])

    test_level = _normalize_test_level(raw_level)
    test_type = _normalize_test_type(raw_type)

    errors: List[str] = []
    if test_level not in TEST_LEVELS:
        errors.append(f"Invalid test_level: {raw_level!r}")
        test_level = "Unknown"
    if test_type not in TEST_TYPES:
        errors.append(f"Invalid test_type: {raw_type!r}")
        test_type = "Unknown"

    err = "; ".join(errors) if errors else None
    return {"test_level": test_level, "test_type": test_type}, err


def main() -> None:
    """CLI entrypoint: run LLM-based scenario classification (test_level/test_type)."""
    parser = argparse.ArgumentParser(
        description=(
            "Classify scenarios via Ollama LLM (test_level + test_type).\n"
            "- Default: runs all built-in prompting strategies over the full dataset.\n"
            "- Output: always writes a combined JSON + per-strategy JSON files under --out-dir.\n"
        )
    )
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_PATH)
    parser.add_argument(
        "--strategy",
        type=str,
        default="",
        help=(
            "Run a single strategy (otherwise runs all). "
            f"Available: {', '.join(sorted(DEFAULT_STRATEGY_TO_PROMPT_PATH.keys()))}"
        ),
    )
    parser.add_argument("--start", type=int, default=1, help="1-based start index (inclusive)")
    parser.add_argument(
        "--end",
        type=int,
        default=0,
        help="1-based end index (inclusive); 0 means to the end",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_OUT_BY_STRATEGY_DIR,
        help="Output directory for combined + per-strategy JSON files.",
    )
    args = parser.parse_args()

    dataset_path: Path = args.dataset
    if not dataset_path.exists():
        raise SystemExit(f"Dataset not found: {dataset_path}")

    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    scenarios: List[Dict[str, Any]] = list(dataset.get("scenarios") or [])

    start_i = max(args.start, 1) - 1
    end_i = len(scenarios) if args.end in (0, None) else min(args.end, len(scenarios))
    selected = scenarios[start_i:end_i]

    llm_runner = _import_llm_runner()

    requested_strategy = str(args.strategy or "").strip()
    if requested_strategy:
        if requested_strategy not in DEFAULT_STRATEGY_TO_PROMPT_PATH:
            raise SystemExit(
                f"--strategy must be one of: {', '.join(sorted(DEFAULT_STRATEGY_TO_PROMPT_PATH.keys()))}"
            )
        strategy_order = [requested_strategy]
        primary_strategy = requested_strategy
    else:
        strategy_order = list(DEFAULT_STRATEGY_TO_PROMPT_PATH.keys())
        primary_strategy = DEFAULT_PRIMARY_STRATEGY

    strategy_to_prompt_template = {
        key: Template(DEFAULT_STRATEGY_TO_PROMPT_PATH[key].read_text(encoding="utf-8"))
        for key in strategy_order
    }

    total_calls = len(selected) * len(strategy_to_prompt_template)
    completed_calls = 0
    started_at = time.time()

    print(
        f"Running classification: scenarios={len(selected)} | "
        f"strategies={len(strategy_to_prompt_template)} | "
        f"out_dir={args.out_dir}"
    )

    for scenario in selected:
        scenario_started = time.time()
        strategy_results: Dict[str, Dict[str, str]] = {}
        strategy_errors: Dict[str, str] = {}

        scenario_ok = 0
        scenario_warn = 0
        scenario_failed = 0
        scenario_parse_error = 0

        for strategy_key, prompt_template in strategy_to_prompt_template.items():
            call_started = time.time()
            filled = prompt_template.safe_substitute(
                scenario_name=str(scenario.get("scenario") or "").strip(),
                feature=str(scenario.get("feature") or "").strip(),
                background=_format_steps(scenario.get("background") or []),
                steps=_format_steps(scenario.get("steps") or []),
            )

            try:
                raw = llm_runner.call_ollama(filled)
            except Exception as exc:
                strategy_results[strategy_key] = {"test_level": "Unknown", "test_type": "Unknown"}
                strategy_errors[strategy_key] = f"LLM call failed: {exc}"
                scenario_failed += 1
                completed_calls += 1
                continue

            obj, parse_err = _extract_first_json_object(raw)
            if parse_err is not None or obj is None:
                strategy_results[strategy_key] = {"test_level": "Unknown", "test_type": "Unknown"}
                strategy_errors[strategy_key] = parse_err or "Unknown parse error"
                scenario_parse_error += 1
                completed_calls += 1
                continue

            classification, validation_err = _validate_classification(obj)
            strategy_results[strategy_key] = classification
            if validation_err is not None:
                strategy_errors[strategy_key] = validation_err
                scenario_warn += 1
            else:
                scenario_ok += 1

            completed_calls += 1

        elapsed_total = time.time() - started_at
        scenario_elapsed = time.time() - scenario_started
        processed_scenarios = max(1, (completed_calls // max(len(strategy_to_prompt_template), 1)))
        avg_scenario = elapsed_total / processed_scenarios if processed_scenarios else 0.0
        remaining_scenarios = max(len(selected) - processed_scenarios, 0)
        eta_s = remaining_scenarios * avg_scenario
        sid = str(scenario.get("id") or "").strip() or "?"
        print(
            f"[{processed_scenarios}/{len(selected)}] {sid} DONE | "
            f"ok={scenario_ok} warn={scenario_warn} failed={scenario_failed} parse={scenario_parse_error} | "
            f"({scenario_elapsed:.1f}s) | avg/scenario={avg_scenario:.1f}s | ETA~{eta_s/60:.1f}m"
        )

        scenario["llm_classification_by_strategy"] = strategy_results
        if strategy_errors:
            scenario["classification_error_by_strategy"] = strategy_errors
        else:
            scenario.pop("classification_error_by_strategy", None)


        primary = strategy_results.get(primary_strategy) or {"test_level": "Unknown", "test_type": "Unknown"}
        scenario["llm_classification"] = primary
        err_primary = strategy_errors.get(primary_strategy)
        if err_primary:
            scenario["classification_error"] = err_primary
        else:
            scenario.pop("classification_error", None)

    out_payload = dict(dataset)
    out_payload["scenarios"] = scenarios

    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)


    for strategy_key in strategy_to_prompt_template.keys():
        strat_payload = dict(dataset)
        strat_scenarios: List[Dict[str, Any]] = []
        for s in scenarios:
            if not isinstance(s, dict):
                continue
            by_strat = s.get("llm_classification_by_strategy") or {}
            if not isinstance(by_strat, dict):
                by_strat = {}
            cls = by_strat.get(strategy_key) if isinstance(by_strat.get(strategy_key), dict) else None
            cls = cls or {"test_level": "Unknown", "test_type": "Unknown"}

            err_by = s.get("classification_error_by_strategy") or {}
            if not isinstance(err_by, dict):
                err_by = {}
            err = err_by.get(strategy_key) if isinstance(err_by.get(strategy_key), str) else None

            strat_scenarios.append(
                {
                    "id": s.get("id"),
                    "feature": s.get("feature"),
                    "scenario": s.get("scenario"),
                    "llm_classification": cls,
                    **({"classification_error": err} if err else {}),
                }
            )

        strat_payload["scenarios"] = strat_scenarios
        strat_payload["classification_strategy"] = strategy_key
        out_path = out_dir / f"llm_{strategy_key}.json"
        out_path.write_text(json.dumps(strat_payload, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Wrote {len(strategy_to_prompt_template)} strategy JSON files under: {out_dir}")


if __name__ == "__main__":
    main()
