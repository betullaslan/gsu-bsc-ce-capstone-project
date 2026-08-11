"""Core generation helpers used by the end-to-end generation flow."""

from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Tuple

from llm_runner import call_ollama
from quality_rules import validate_constraints, validate_semantic_quality
from testcase_format import sanitize_output_text


def detect_direct_copy(scenario: Dict[str, Any], output_text: str) -> Dict[str, Any]:
    """Detect direct copying of scenario text into the model output."""
    output_text = sanitize_output_text(output_text)
    lower_output = output_text.lower()

    issues: List[str] = []
    copied_steps: List[str] = []

    if re.search(
        r"^\s*(scenario|background|given|when|then)\s*:",
        output_text,
        flags=re.IGNORECASE | re.MULTILINE,
    ):
        issues.append("contains_gherkin_headers")

    scenario_name = (scenario.get("scenario") or "").strip()

    step_sources: List[Dict[str, Any]] = []
    step_sources.extend(scenario.get("background", []) or [])
    step_sources.extend(scenario.get("steps", []) or [])

    for step in step_sources:
        step_text = (step.get("text") or "").strip()
        if step_text and len(step_text) >= 80 and step_text.lower() in lower_output:
            copied_steps.append(step_text)

    if len(copied_steps) >= 2:
        issues.append("gherkin_step_text_verbatim")

    return {
        "issues": issues,
        "scenario_name": scenario_name,
        "copied_steps": copied_steps[:20],
        "copied_steps_count": len(copied_steps),
    }


def run_generation(prompt: str) -> Tuple[str, float]:
    """Run a single model call and return (sanitized_output, elapsed_seconds)."""
    start = time.perf_counter()
    output = call_ollama(prompt)
    elapsed = time.perf_counter() - start
    return sanitize_output_text(output), elapsed


def _dedupe_preserve_order(items: List[str]) -> List[str]:
    """Remove duplicates while preserving first-seen order."""
    # Keep warning order stable so downstream reporting remains deterministic.
    out: List[str] = []
    seen: set[str] = set()
    for x in items:
        if x in seen:
            continue
        out.append(x)
        seen.add(x)
    return out


def compute_warnings(
    scenario_obj: Dict[str, Any],
    strategy_name: str,
    parsed: Dict[str, Any],
    raw_output: str,
    expected_failure: bool,
) -> Tuple[List[str], Dict[str, Any], Dict[str, Any]]:
    """Compute warnings + semantic details for one generated test case."""
    warnings: List[str] = []
    copy_check = detect_direct_copy(scenario_obj, raw_output)
    if copy_check.get("issues"):
        warnings.append("minor_text_similarity")

    warnings.extend(validate_constraints(strategy_name, parsed))
    semantic_warnings, semantic_details = validate_semantic_quality(
        scenario_obj, parsed, expected_failure=expected_failure
    )
    warnings.extend([w for w in semantic_warnings if w not in warnings])
    warnings = _dedupe_preserve_order(warnings)
    return warnings, semantic_details, copy_check

