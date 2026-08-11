"""Precondition coverage validation and enforcement helpers."""

from typing import Any, Dict, List, Tuple

from quality_rules_text import _extract_quoted_literals, _jaccard, _token_set
from scenario_steps import split_steps


def _covers_condition(condition_text: str, precondition_item: str) -> bool:
    """Return True when a precondition sufficiently covers a scenario condition."""
    cond_literals = _extract_quoted_literals(condition_text)
    # If all quoted literals are present, treat it as a strong match.
    if cond_literals and all(lit in precondition_item for lit in cond_literals):
        return True

    a = _token_set(condition_text)
    b = _token_set(precondition_item)
    return _jaccard(a, b) >= 0.75


def validate_preconditions_coverage(
    scenario: Dict[str, Any], parsed: Dict[str, Any]
) -> Tuple[List[str], Dict[str, Any]]:
    """Check whether Background/Given conditions are covered by test preconditions."""
    warnings: List[str] = []
    details: Dict[str, Any] = {}

    preconditions: List[str] = parsed.get("preconditions", []) or []
    background_steps = [s.get("text", "") for s in (scenario.get("background") or [])]
    given_steps = [
        s.get("text", "")
        for s in (split_steps(scenario.get("steps") or []).get("given") or [])
    ]

    missing_background: List[str] = []
    for cond in background_steps:
        if cond and not any(_covers_condition(cond, p) for p in preconditions):
            missing_background.append(cond)

    missing_given: List[str] = []
    for cond in given_steps:
        if cond and not any(_covers_condition(cond, p) for p in preconditions):
            missing_given.append(cond)

    if missing_background:
        warnings.append("missing_background_preconditions")
    if missing_given:
        warnings.append("missing_given_preconditions")

    details["missing_background"] = missing_background
    details["missing_given"] = missing_given
    details["background_count"] = len(background_steps)
    details["given_count"] = len(given_steps)

    return warnings, details


def enforce_preconditions_coverage(
    scenario: Dict[str, Any], parsed: Dict[str, Any]
) -> Tuple[bool, Dict[str, Any]]:
    """Add missing Background/Given conditions to preconditions when possible."""
    warnings, details = validate_preconditions_coverage(scenario, parsed)

    changed = False
    preconditions: List[str] = parsed.get("preconditions", []) or []

    missing = []
    missing.extend(details.get("missing_background") or [])
    missing.extend(details.get("missing_given") or [])

    for cond in missing:
        if not cond:
            continue
        if any(_covers_condition(cond, p) for p in preconditions):
            continue
        preconditions.append(str(cond))
        changed = True

    parsed["preconditions"] = preconditions
    details["warnings"] = warnings
    return changed, details

