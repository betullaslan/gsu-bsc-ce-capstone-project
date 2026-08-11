"""End-to-end generation pipeline for a single scenario/strategy pair.

This module orchestrates prompt building, model invocation, parsing, post-processing,
and quality evaluation, including targeted retries when high-severity issues appear.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from generation.core import compute_warnings, detect_direct_copy, run_generation
from generation.postprocess import (
    enforce_no_invented_context,
    enforce_steps_expected_separation,
    normalize_and_dedupe_test_case,
    normalize_constraint_expected_results,
    normalize_steps_strict_style,
    split_atomic_expected_results,
)
from prompt_builder import build_prompt
from quality_metrics import compute_quality_metrics
from quality_rules import (
    MIN_EXPECTED_RESULTS,
    MIN_TEST_STEPS,
    detect_expected_failure,
    enrich_warnings,
    enforce_expected_results_checks,
    enforce_preconditions_coverage,
    normalize_public_warnings,
)
from testcase_format import parse_test_case, validate_structure


def run_one_strategy(
    scenario_obj: Dict[str, Any],
    strategy_name: str,
    enforce_output: bool,
) -> Dict[str, Any]:
    """Generate and post-process one test case for a single prompting strategy."""
    postprocess_flags: Dict[str, bool] = {
        "preconditions_enforced": False,
        "expected_results_enforced": False,
        "retry_for_quality": False,
    }

    expected_failure = detect_expected_failure(scenario_obj)
    total_response_time = 0.0
    generation_attempts = 0
    max_attempts = int(os.getenv("OLLAMA_MAX_ATTEMPTS", "5") or "5")
    if max_attempts < 1:
        max_attempts = 1

    def run_and_track(prompt: str) -> str:
        """Run one generation call and accumulate timing/attempt counters."""
        nonlocal total_response_time, generation_attempts
        generation_attempts += 1
        # Track total response time across retries to reflect actual strategy cost.
        output, elapsed = run_generation(prompt)
        total_response_time += elapsed
        return output

    try:
        base_prompt = build_prompt(scenario_obj, strategy_name)
        raw_output = run_and_track(base_prompt)
    except Exception as e:
        return {
            "strategy": strategy_name,
            "error": f"{type(e).__name__}: {e}",
            "response_time_seconds": None,
            "test_case": {"preconditions": [], "steps": [], "expected_results": []},
            "validation": {"is_valid": False, "warnings": [], "quality_metrics": {}},
        }

    parsed = parse_test_case(raw_output)
    # Normalize first so validators operate on a clean, de-duplicated representation.
    parsed, removed_counts = normalize_and_dedupe_test_case(parsed)
    if strategy_name == "constraint_prompting":
        parsed, removed_near = normalize_constraint_expected_results(parsed)
        removed_counts["expected_results"] = removed_counts.get("expected_results", 0) + removed_near

    critical_errors = validate_structure(raw_output, parsed)

    semantic_details: Dict[str, Any] = {}
    warnings: List[str] = []

    if critical_errors and generation_attempts < max_attempts:
        # Retry once with stricter formatting instructions if required sections are missing.
        retry_prompt = (
            base_prompt
            + "\n\nIMPORTANT:\n"
            + "- Your output must include all required section headings.\n"
            + "- Do not leave Test Steps or Expected Results empty.\n"
            + "- Return only the test case.\n"
        )
        raw_output = run_and_track(retry_prompt)
        parsed = parse_test_case(raw_output)
        parsed, removed_counts = normalize_and_dedupe_test_case(parsed)
        if strategy_name == "constraint_prompting":
            parsed, removed_near = normalize_constraint_expected_results(parsed)
            removed_counts["expected_results"] = removed_counts.get("expected_results", 0) + removed_near
        critical_errors = validate_structure(raw_output, parsed)

    warnings, semantic_details, _copy_check = compute_warnings(
        scenario_obj, strategy_name, parsed, raw_output, expected_failure
    )

    if (
        any(
            w in (warnings or [])
            for w in (
                "unsupported_action_step",
                "unsupported_precondition",
                "irrelevant_or_invented_step",
            )
        )
        and generation_attempts < max_attempts
    ):
        # Retry when the model invents context or actions not present in the scenario.
        postprocess_flags["retry_for_quality"] = True
        retry_lines = [
            (
                "- Do NOT invent directory/location context (no subdirectory/current directory/root "
                "directory/working directory/cd/src) unless explicitly present in the scenario."
            ),
            (
                "- Do NOT add helper steps not present in When (no 'wait for completion', no "
                "'capture stderr' unless stderr is explicitly mentioned)."
            ),
            (
                "- Test Steps must include only the literal When action(s) plus, if needed, exactly "
                "one 'Capture the command output (stdout)' step."
            ),
            (
                "- Preconditions must include only Background/Given conditions from the scenario "
                "(no extra environment/context)."
            ),
            "- Return only as many numbered items as needed; do not fill unused numbers.",
        ]
        retry_prompt = (
            base_prompt
            + "\n\nIMPORTANT:\n"
            + "\n".join(retry_lines)
            + "\n- Rewrite the full test case accordingly and keep all literal values unchanged.\n"
            + "- Return only the test case.\n"
        )
        raw_output = run_and_track(retry_prompt)
        parsed = parse_test_case(raw_output)
        parsed, removed_counts = normalize_and_dedupe_test_case(parsed)
        if strategy_name == "constraint_prompting":
            parsed, removed_near = normalize_constraint_expected_results(parsed)
            removed_counts["expected_results"] = removed_counts.get("expected_results", 0) + removed_near
        critical_errors = validate_structure(raw_output, parsed)
        warnings, semantic_details, _copy_check = compute_warnings(
            scenario_obj, strategy_name, parsed, raw_output, expected_failure
        )

    if (
        ("assertion_in_step" in warnings or "action_in_expected_result" in warnings)
        and generation_attempts < max_attempts
    ):
        postprocess_flags["retry_for_quality"] = True

        step_samples = (semantic_details.get("assertion_in_step") or {}).get("samples") or []
        exp_samples = (semantic_details.get("action_in_expected_result") or {}).get("samples") or []

        retry_lines: List[str] = [
            "- STRICT separation is required:",
            "- Test Steps MUST contain only executable actions (e.g., Run/Create/Update/Open/List/Set).",
            (
                "- Test Steps MUST NOT contain verification/assertion phrasing "
                "(verify/check/ensure/confirm/assert/expect/output contains/exit code)."
            ),
            "- Expected Results MUST contain only atomic assertions (one check per line).",
            (
                "- Expected Results MUST NOT contain actions "
                "(run/execute/open/create/delete/update/list/set/click/navigate/login/submit)."
            ),
            "- Rewrite the full test case accordingly and keep all literal values unchanged.",
        ]

        if step_samples:
            retry_lines.append(
                "- These are INVALID in Test Steps; move them to Expected Results "
                "and convert steps to actions:"
            )
            for s in step_samples[:3]:
                retry_lines.append(f"- {s}")

        if exp_samples:
            retry_lines.append("- These are INVALID in Expected Results; move them to Test Steps:")
            for s in exp_samples[:3]:
                retry_lines.append(f"- {s}")

        retry_prompt = (
            base_prompt
            + "\n\nIMPORTANT:\n"
            + "\n".join(retry_lines)
            + "\n- Return only the test case.\n"
        )
        raw_output = run_and_track(retry_prompt)
        parsed = parse_test_case(raw_output)
        parsed, removed_counts = normalize_and_dedupe_test_case(parsed)
        if strategy_name == "constraint_prompting":
            parsed, removed_near = normalize_constraint_expected_results(parsed)
            removed_counts["expected_results"] = removed_counts.get("expected_results", 0) + removed_near
        critical_errors = validate_structure(raw_output, parsed)
        warnings, semantic_details, _copy_check = compute_warnings(
            scenario_obj, strategy_name, parsed, raw_output, expected_failure
        )

    if (
        ("min_test_steps_not_met" in warnings or "min_expected_results_not_met" in warnings)
        and generation_attempts < max_attempts
    ):
        # Retry when the output is structurally valid but too short.
        postprocess_flags["retry_for_quality"] = True
        retry_prompt = (
            base_prompt
            + "\n\nIMPORTANT:\n"
            + (
                f"- Ensure at least {MIN_TEST_STEPS} test steps and at least "
                f"{MIN_EXPECTED_RESULTS} expected results.\n"
            )
            + "- Avoid redundant steps/results (do not repeat the same check in different words).\n"
            + "- Avoid generic \"observe/examine/save output\" steps unless required by the scenario.\n"
            + "- Return only the test case.\n"
        )
        raw_output = run_and_track(retry_prompt)
        parsed = parse_test_case(raw_output)
        parsed, removed_counts = normalize_and_dedupe_test_case(parsed)
        if strategy_name == "constraint_prompting":
            parsed, removed_near = normalize_constraint_expected_results(parsed)
            removed_counts["expected_results"] = removed_counts.get("expected_results", 0) + removed_near
        critical_errors = validate_structure(raw_output, parsed)
        warnings, semantic_details, _copy_check = compute_warnings(
            scenario_obj, strategy_name, parsed, raw_output, expected_failure
        )

    if (
        (
            "missing_literal_value" in warnings
            or "missing_background_preconditions" in warnings
            or "missing_given_preconditions" in warnings
            or "generic_expected_result" in warnings
            or "missing_when_action_literal" in warnings
        )
        and generation_attempts < max_attempts
    ):
        postprocess_flags["retry_for_quality"] = True
        scenario_lits = semantic_details.get("scenario_literals") or {}

        id_assertions = scenario_lits.get("output_assertions") or []
        ids = scenario_lits.get("ids") or []
        id_check: str = ""
        if id_assertions:
            id_check = id_assertions[0]
        elif ids:
            id_check = f"id: {ids[0]}"

        contents = scenario_lits.get("contents") or []
        content_check: str = contents[0] if contents else ""

        expected_result_instructions: List[str] = [
            (
                "- Expected Results MUST include these exact checks (as separate numbered items "
                "unless constrained by max items):"
            ),
        ]
        if expected_failure:
            expected_result_instructions.append("- Exit/status code is non-zero.")
        else:
            expected_result_instructions.append("- Exit/status code is 0.")
        if id_check:
            expected_result_instructions.append(f"- Output contains \"{id_check}\".")
        if content_check:
            expected_result_instructions.append(
                f"- Output contains the exact content/body \"{content_check}\"."
            )
        expected_result_instructions.append(
            (
                "- Avoid generic success-only expected results like \"The command should succeed\" "
                "or \"without errors\" unless combined with a concrete check (ID/content/body/exit code)."
            )
        )
        expected_result_instructions.append(
            (
                "- Keep Expected Results concise; if a max of 3 items is required, combine checks "
                "into fewer items without losing exact literals."
            )
        )

        missing_when = (semantic_details.get("missing_when_actions") or [])[:3]
        if missing_when:
            expected_result_instructions.append(
                (
                    "- Test Steps MUST include the exact When command/action literals "
                    "(do not paraphrase or drop arguments):"
                )
            )
            for lit in missing_when:
                expected_result_instructions.append(
                    f"- Include this exact literal in a Test Step: \"{lit}\""
                )

        missing_prec = (semantic_details.get("preconditions_coverage") or {}).get(
            "missing_background",
            [],
        ) + (semantic_details.get("preconditions_coverage") or {}).get("missing_given", [])
        if missing_prec:
            expected_result_instructions.append(
                (
                    "- Preconditions MUST preserve all Background/Given conditions. Include these as "
                    "preconditions (paraphrase allowed but keep exact literals):"
                )
            )
            for cond in missing_prec[:6]:
                expected_result_instructions.append(f"- {cond}")

        retry_prompt = (
            base_prompt
            + "\n\nIMPORTANT:\n"
            + "\n".join(expected_result_instructions)
            + "\n- Return only the test case.\n"
        )

        raw_output = run_and_track(retry_prompt)
        parsed = parse_test_case(raw_output)
        parsed, removed_counts = normalize_and_dedupe_test_case(parsed)
        if strategy_name == "constraint_prompting":
            parsed, removed_near = normalize_constraint_expected_results(parsed)
            removed_counts["expected_results"] = removed_counts.get("expected_results", 0) + removed_near
        critical_errors = validate_structure(raw_output, parsed)
        warnings, semantic_details, _copy_check = compute_warnings(
            scenario_obj, strategy_name, parsed, raw_output, expected_failure
        )

    parsed["steps"] = normalize_steps_strict_style(list(parsed.get("steps") or []))
    sep_details: Dict[str, Any] = {}
    if enforce_output:
        parsed["expected_results"] = split_atomic_expected_results(list(parsed.get("expected_results") or []))
        parsed, sep_details = enforce_steps_expected_separation(parsed)
    else:
        try:
            if any(w in (warnings or []) for w in ("assertion_in_step", "action_in_expected_result")):
                parsed, moved = enforce_steps_expected_separation(parsed)
                if moved.get("moved_step_assertions_to_expected"):
                    sep_details = moved
        except Exception:
            sep_details = {}

    parsed, removed_counts2 = normalize_and_dedupe_test_case(parsed)
    if strategy_name == "constraint_prompting":
        parsed, removed_near = normalize_constraint_expected_results(parsed)
        removed_counts2["expected_results"] = removed_counts2.get("expected_results", 0) + removed_near
    for k, v in removed_counts2.items():
        removed_counts[k] = int(removed_counts.get(k, 0)) + int(v or 0)
    if removed_counts.get("expected_results", 0) > 0:
        warnings.append("duplicate_expected_result")

    if enforce_output:
        prec_changed, _ = enforce_preconditions_coverage(scenario_obj, parsed)
        exp_changed, _ = enforce_expected_results_checks(
            strategy_name,
            scenario_obj,
            parsed,
            expected_failure=expected_failure,
        )
        postprocess_flags["preconditions_enforced"] = bool(prec_changed)
        postprocess_flags["expected_results_enforced"] = bool(exp_changed)

        parsed, invented_details = enforce_no_invented_context(scenario_obj, parsed)
        if invented_details.get("removed_preconditions") or invented_details.get("removed_steps"):
            postprocess_flags["invented_context_removed"] = True
            sep_details = {**(sep_details or {}), "invented_context_removed": invented_details}

        steps_list = list(parsed.get("steps") or [])
        if len(steps_list) < MIN_TEST_STEPS:
            steps_list.append("Capture the command output (stdout)")
            parsed["steps"] = steps_list

    scoring_parsed = json.loads(json.dumps(parsed, ensure_ascii=False))

    recomputed, semantic_details, _copy_check = compute_warnings(
        scenario_obj,
        strategy_name,
        scoring_parsed,
        raw_output,
        expected_failure,
    )
    public_warnings = normalize_public_warnings(recomputed)

    metrics = compute_quality_metrics(
        critical_errors=critical_errors,
        warnings=public_warnings,
        scenario=scenario_obj,
        parsed=scoring_parsed,
        semantic_details=semantic_details,
        postprocess=postprocess_flags,
    )

    is_valid = len(critical_errors) == 0

    def _env_bool(name: str, default: bool) -> bool:
        """Parse boolean-like environment values with a fallback default."""
        raw = os.getenv(name)
        if raw is None or str(raw).strip() == "":
            return default
        return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}

    strict_invalid_missing_literals = _env_bool("STRICT_INVALID_MISSING_LITERALS", False)
    strict_invalid_missing_given = _env_bool("STRICT_INVALID_MISSING_GIVEN_PRECONDITIONS", True)

    if strict_invalid_missing_literals and "missing_literal_value" in public_warnings:
        is_valid = False
    if strict_invalid_missing_given and "missing_given_preconditions" in public_warnings:
        is_valid = False

    warnings_enriched = enrich_warnings(public_warnings)
    has_high_or_medium = any(
        str((w or {}).get("severity") or "").strip().lower() in {"high", "medium"}
        for w in (warnings_enriched or [])
        if isinstance(w, dict)
    )
    has_any = bool(public_warnings)

    if not is_valid:
        quality_status = "invalid"
    elif has_high_or_medium:
        quality_status = "needs_review"
    elif has_any:
        quality_status = "clean_with_warnings"
    else:
        quality_status = "clean"

    validation: Dict[str, Any] = {
        "is_valid": is_valid,
        "quality_status": quality_status,
        "warning_count": len(public_warnings),
        "warnings": warnings_enriched,
        "quality_metrics": metrics,
    }

    minimal_test_case = {
        "preconditions": parsed.get("preconditions") or [],
        "steps": parsed.get("steps") or [],
        "expected_results": parsed.get("expected_results") or [],
    }

    return {
        "strategy": strategy_name,
        "response_time_seconds": round(total_response_time, 6),
        "generation_attempts": generation_attempts,
        "test_case": minimal_test_case,
        "validation": validation,
    }


__all__ = [
    "detect_direct_copy",
    "normalize_and_dedupe_test_case",
    "normalize_constraint_expected_results",
    "run_generation",
    "run_one_strategy",
]
