"""Quality metric computation used for ranking and reporting."""

from typing import Any, Dict, Sequence, Tuple

from quality_rules import (
    MIN_EXPECTED_RESULTS,
    _lit_matches_text,
    _normalize_for_dedupe,
    _scenario_literals,
    compute_hallucination_score,
    compute_specificity_score,
)

def _clamp01(value: float) -> float:
    """Clamp numeric value to the inclusive range [0, 1]."""
    return max(0.0, min(1.0, float(value)))


def _executable_steps_score(parsed: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    """Score whether test steps are action-oriented rather than assertions."""
    steps = parsed.get("steps") or []
    if not isinstance(steps, list) or not steps:
        return 0.0, {"bad_steps": 0, "total_steps": 0}

    # Enforce that Test Steps read like executable actions (not assertions).
    allowed_action_patterns = (
        "run ",
        "execute ",
        "open ",
        "create ",
        "delete ",
        "update ",
        "list ",
        "set ",
        "check the exit",
        "check exit",
        "check status",
    )
    bad_start_patterns = (
        "verify ",
        "check if ",
        "ensure ",
        "output contains",
        "the output should",
        "the output contains",
    )

    bad = 0
    for s in steps:
        text = str(s or "").strip().lower()
        if not text:
            continue
        if text.startswith(allowed_action_patterns):
            continue
        if text.startswith(bad_start_patterns):
            bad += 1

    score = 1.0 - (bad / len(steps))
    return _clamp01(score), {"bad_steps": bad, "total_steps": len(steps)}


def _precondition_mapping_score(semantic_details: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    """Score coverage of Background/Given conditions in preconditions."""
    cov = semantic_details.get("preconditions_coverage") or {}
    if not isinstance(cov, dict):
        return 1.0, {"missing": 0, "total": 0, "merged": 0}

    missing_background = cov.get("missing_background") or []
    missing_given = cov.get("missing_given") or []
    background_count = int(cov.get("background_count") or 0)
    given_count = int(cov.get("given_count") or 0)
    total = background_count + given_count
    missing = (len(missing_background) if isinstance(missing_background, list) else 0) + (
        len(missing_given) if isinstance(missing_given, list) else 0
    )

    merged = int(semantic_details.get("merged_precondition_count") or 0)
    missing_ratio = (missing / total) if total else 0.0
    merged_penalty = min(1.0, 0.25 * merged) if merged else 0.0

    score = 1.0 - missing_ratio - merged_penalty
    return _clamp01(score), {"missing": missing, "total": total, "merged": merged}


def _literal_preservation_score(semantic_details: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    """Score how many key scenario literals are preserved in output."""
    literals = semantic_details.get("scenario_literals") or {}
    if not isinstance(literals, dict):
        return 1.0, {"missing": 0, "total": 0}

    keys = literals.get("key") or []
    total = len(keys) if isinstance(keys, list) else 0
    missing_keys = semantic_details.get("missing_key_literals_in_testcase") or []
    missing = len(missing_keys) if isinstance(missing_keys, list) else 0
    if total <= 0:
        return 1.0, {"missing": 0, "total": 0}
    score = 1.0 - (missing / total)
    return _clamp01(score), {"missing": missing, "total": total}


def _step_result_separation_score(parsed: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    """Score separation quality between steps and expected results."""
    steps = parsed.get("steps") or []
    expected = parsed.get("expected_results") or []
    if not isinstance(steps, list) or not isinstance(expected, list) or not expected:
        return 1.0, {"near_duplicates": 0, "total_expected": 0}

    norm_steps = [_normalize_for_dedupe(str(s)) for s in steps if str(s).strip()]
    near_dupes = 0
    for r in expected:
        rn = _normalize_for_dedupe(str(r))
        if rn and any(rn == sn for sn in norm_steps):
            near_dupes += 1

    score = 1.0 - (near_dupes / len(expected))
    return _clamp01(score), {"near_duplicates": near_dupes, "total_expected": len(expected)}


def compute_semantic_quality(
    warnings: Sequence[str],
    semantic_details: Dict[str, Any],
    scenario: Dict[str, Any],
    parsed: Dict[str, Any],
) -> Tuple[float, Dict[str, Any]]:
    """Compute semantic quality and supporting details for a parsed test case."""
    subscores: Dict[str, float] = {}
    details: Dict[str, Any] = {}

    executable_steps_score, exec_details = _executable_steps_score(parsed)
    subscores["executable_steps_score"] = executable_steps_score
    details["executable_steps"] = exec_details

    precondition_mapping_score, prec_details = _precondition_mapping_score(semantic_details)
    subscores["precondition_mapping_score"] = precondition_mapping_score
    details["precondition_mapping"] = prec_details

    literal_preservation_score, lit_details = _literal_preservation_score(semantic_details)
    subscores["literal_preservation_score"] = literal_preservation_score
    details["literal_preservation"] = lit_details

    step_result_separation_score, sep_details = _step_result_separation_score(parsed)
    subscores["step_result_separation_score"] = step_result_separation_score
    details["step_result_separation"] = sep_details

    semantic_quality = (
        0.30 * executable_steps_score
        + 0.25 * precondition_mapping_score
        + 0.25 * literal_preservation_score
        + 0.20 * step_result_separation_score
    )

    hard_penalties: Dict[str, float] = {}
    halluc = semantic_details.get("hallucination") or {}
    halluc_items = int(halluc.get("hallucinated_items") or 0) if isinstance(halluc, dict) else 0
    if halluc_items:
        p = min(0.50, 0.25 * halluc_items)
        semantic_quality -= p
        hard_penalties["hallucinated_items"] = p

    unlinked = int(semantic_details.get("unlinked_expected_results") or 0)
    expected_count = len(parsed.get("expected_results", []) or [])
    if expected_count and unlinked >= expected_count:
        semantic_quality -= 0.30
        hard_penalties["completely_unlinked_expected_results"] = 0.30
    elif expected_count and unlinked > 0:
        p = min(0.20, 0.10 * (unlinked / expected_count))
        semantic_quality -= p
        hard_penalties["partially_unlinked_expected_results"] = round(p, 3)

    missing_when = semantic_details.get("missing_when_actions") or []
    if isinstance(missing_when, list) and missing_when:
        p = min(0.20, 0.05 * len(missing_when))
        semantic_quality -= p
        hard_penalties["missing_when_actions"] = round(p, 3)

    missing_then = semantic_details.get("missing_then_assertions") or []
    if isinstance(missing_then, list) and missing_then:
        p = min(0.20, 0.05 * len(missing_then))
        semantic_quality -= p
        hard_penalties["missing_then_assertions"] = round(p, 3)

    missing_keys = semantic_details.get("missing_key_literals_in_testcase") or []
    if isinstance(missing_keys, list) and missing_keys:
        p = min(0.25, 0.05 * len(missing_keys))
        semantic_quality -= p
        hard_penalties["missing_key_literals_in_testcase"] = round(p, 3)


    ai_step = semantic_details.get("assertion_in_step") or {}
    if isinstance(ai_step, dict):
        cnt = int(ai_step.get("count") or 0)
        if cnt:
            p = min(0.20, 0.07 * cnt)
            semantic_quality -= p
            hard_penalties["assertion_in_step"] = round(p, 3)


    gsc = int(semantic_details.get("generic_step_count") or 0)
    if gsc:
        p = min(0.15, 0.03 * gsc)
        semantic_quality -= p
        hard_penalties["generic_step"] = round(p, 3)

    gec = int(semantic_details.get("generic_expected_result_count") or 0)
    if gec:
        p = min(0.15, 0.03 * gec)
        semantic_quality -= p
        hard_penalties["generic_expected_result"] = round(p, 3)

    action_in_expected = semantic_details.get("action_in_expected_result") or {}
    if isinstance(action_in_expected, dict):
        cnt = int(action_in_expected.get("count") or 0)
        if cnt:
            p = min(0.20, 0.05 * cnt)
            semantic_quality -= p
            hard_penalties["action_in_expected_result"] = round(p, 3)

    return _clamp01(semantic_quality), {
        "subscores": subscores,
        "details": details,
        "hard_penalties": hard_penalties,
    }


def compute_quality_metrics(
    critical_errors: Sequence[str],
    warnings: Sequence[str],
    scenario: Dict[str, Any],
    parsed: Dict[str, Any],
    semantic_details: Dict[str, Any],
    postprocess: Dict[str, bool] | None = None,
    include_debug_metrics: bool = False,
) -> Dict[str, Any]:
    """Compute the numeric quality metrics used in ranking and reporting."""
    steps_count = len(parsed.get("steps", []) or [])
    expected_count = len(parsed.get("expected_results", []) or [])

    completeness = 1.0
    if expected_count < MIN_EXPECTED_RESULTS:
        completeness -= 0.25
    if "missing_literal_value" in warnings:
        completeness -= 0.10
    pre_cov = semantic_details.get("preconditions_coverage") or {}
    missing_bg = pre_cov.get("missing_background") or []
    missing_g = pre_cov.get("missing_given") or []
    if missing_bg or missing_g:
        completeness -= 0.10

    if semantic_details.get("missing_when_actions"):
        completeness -= 0.10

    if semantic_details.get("missing_then_assertions"):
        completeness -= 0.10

    if semantic_details.get("missing_key_literals_in_testcase"):
        completeness -= 0.10

    if "merged_precondition" in warnings:
        completeness -= 0.05

    if "assertion_in_step" in warnings:
        completeness -= 0.03

    postprocess = postprocess or {}
    if postprocess.get("preconditions_enforced"):
        completeness -= 0.15
    if postprocess.get("expected_results_enforced"):
        completeness -= 0.15
    if postprocess.get("retry_for_quality"):
        completeness -= 0.1
    completeness = max(0.0, min(1.0, completeness))

    dup_steps = semantic_details.get("duplicate_steps", {})
    dup_expected = semantic_details.get("duplicate_expected_results", {})
    dup_count = (
        int(dup_steps.get("exact_duplicate_count", 0))
        + int(dup_steps.get("near_duplicate_count", 0))
        + int(dup_expected.get("exact_duplicate_count", 0))
        + int(dup_expected.get("near_duplicate_count", 0))
    )
    denom = steps_count + expected_count
    redundancy_score = 1.0 if denom == 0 else max(0.0, 1.0 - (dup_count / denom))

    literals = _scenario_literals(scenario)
    required_literals = literals.get("key", []) or []
    expected_blob = "\n".join(parsed.get("expected_results", []) or [])
    steps_blob = "\n".join(parsed.get("steps", []) or [])

    matched_expected = 0
    matched_steps = 0
    for lit in required_literals:
        if not lit:
            continue
        if _lit_matches_text(lit, expected_blob):
            matched_expected += 1
        if _lit_matches_text(lit, steps_blob):
            matched_steps += 1

    traceability_expected = (
        1.0 if not required_literals else matched_expected / len(required_literals)
    )
    traceability_steps = (
        1.0 if not required_literals else matched_steps / len(required_literals)
    )

    unlinked = semantic_details.get("unlinked_expected_results")
    if isinstance(unlinked, int) and expected_count > 0:
        linkage_score = max(0.0, 1.0 - (unlinked / expected_count))
    else:
        linkage_score = 1.0 if expected_count > 0 else 0.0

    traceability_score = 0.6 * traceability_expected + 0.4 * float(linkage_score)

    specificity_score = None
    if isinstance(semantic_details.get("specificity"), dict):
        raw = (semantic_details.get("specificity") or {}).get("score")
        if isinstance(raw, (int, float)):
            specificity_score = float(raw)
    if specificity_score is None:
        specificity_score, _ = compute_specificity_score(scenario, parsed)

    hallucination_score = None
    if isinstance(semantic_details.get("hallucination"), dict):
        raw = (semantic_details.get("hallucination") or {}).get("score")
        if isinstance(raw, (int, float)):
            hallucination_score = float(raw)
    if hallucination_score is None:
        hallucination_score, _ = compute_hallucination_score(scenario, parsed)

    _ = redundancy_score

    semantic_quality, semantic_quality_details = compute_semantic_quality(
        warnings=warnings,
        semantic_details=semantic_details,
        scenario=scenario,
        parsed=parsed,
    )

    metrics: Dict[str, Any] = {
        "completeness": round(completeness, 3),
        "traceability": round(traceability_score, 3),
        "specificity": round(float(specificity_score), 3),
        "hallucination": round(float(hallucination_score), 3),
        "semantic_coverage": round(float(semantic_quality), 3),
    }

    if include_debug_metrics:

        subscores = (semantic_quality_details or {}).get("subscores") or {}
        metrics["debug_metrics"] = {
            "semantic_penalties": (semantic_quality_details or {}).get("hard_penalties") or {},
            "traceability_expected_score": round(float(traceability_expected), 3),
            "traceability_steps_score": round(float(traceability_steps), 3),
            "redundancy_score": round(float(redundancy_score), 3),
            "semantic_subscores": {
                k: round(float(v), 3)
                for k, v in (subscores.items() if isinstance(subscores, dict) else [])
                if isinstance(v, (int, float))
            },
        }

    return metrics
