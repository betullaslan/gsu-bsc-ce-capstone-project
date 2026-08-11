"""Semantic/constraint validation rules for generated test cases.

The functions in this module emit warning types and supporting details used by scoring
and analysis reports.
"""

import re
from typing import Any, Dict, List, Sequence, Tuple

from quality_rules_preconditions import (
    enforce_preconditions_coverage,
    validate_preconditions_coverage,
)
from quality_rules_text import (
    _collapse_ws,
    _extract_quoted_literals,
    _find_duplicates,
    _has_inline_literal,
    _jaccard,
    _lit_matches_text,
    _normalize_for_dedupe,
    _normalize_literal_for_match,
    _scenario_literals,
    _scenario_vocabulary,
    _token_set,
)
from scenario_steps import split_steps


MIN_TEST_STEPS = 2
MIN_EXPECTED_RESULTS = 2


# Regex patterns used for semantic validation and warning classification.
_GENERIC_STEP_PATTERNS: Sequence[re.Pattern[str]] = (
    re.compile(r"\bobserve\b.*\boutput\b", re.IGNORECASE),
    re.compile(r"\bexamine\b.*\boutput\b", re.IGNORECASE),
    re.compile(r"\binspect\b.*\boutput\b", re.IGNORECASE),
    re.compile(r"\breview\b.*\boutput\b", re.IGNORECASE),
    re.compile(r"\bsave\b.*\boutput\b", re.IGNORECASE),
    re.compile(r"\bcheck\b.*\boutput\b", re.IGNORECASE),
    re.compile(r"\bverify\b.*\boutput\b", re.IGNORECASE),
)

_GENERIC_EXPECTED_RESULT_PATTERNS: Sequence[re.Pattern[str]] = (
    re.compile(r"\b(no|without)\s+errors?\b", re.IGNORECASE),
    re.compile(r"\b(successfully|succeeds?)\b", re.IGNORECASE),
    re.compile(r"\b(output|details)\s+(is|are)\s+displayed\b", re.IGNORECASE),
    re.compile(r"\b(exit\s*(code|status))\b", re.IGNORECASE),
    re.compile(r"\bsuccessful\s+response\b", re.IGNORECASE),
    re.compile(r"\bcommand\s+should\s+succeed\b", re.IGNORECASE),
)

_VAGUE_STEP_PATTERNS: Sequence[re.Pattern[str]] = (
    re.compile(r"\bexpected\s+(ticket\s+)?(information|details)\b", re.IGNORECASE),
    re.compile(r"\b(ticket\s+)?(information|details)\b", re.IGNORECASE),
    re.compile(r"\bverify\b.*\bexpected\b", re.IGNORECASE),
    re.compile(r"\bcheck\b.*\bexpected\b", re.IGNORECASE),
    re.compile(r"\bverify\b.*\b(ticket\s+)?(information|details)\b", re.IGNORECASE),
    re.compile(r"\bcheck\b.*\b(ticket\s+)?(information|details)\b", re.IGNORECASE),
)

_CONCRETE_EXIT_CODE_PATTERNS: Sequence[re.Pattern[str]] = (
    re.compile(
        r"\bexit\s*(status\s*)?code\s*(of\s*)?(is\s*)?[:=]?\s*0\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bexit\s*/\s*status\s*code\s*(of\s*)?(is\s*)?[:=]?\s*0\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bstatus\s*code\s*(of\s*)?(is\s*)?[:=]?\s*0\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\breturn\s*code\s*(of\s*)?(is\s*)?[:=]?\s*0\b",
        re.IGNORECASE,
    ),
)

_VAGUE_WORDS_PATTERN = re.compile(
    r"\b(correct|valid|appropriate|expected|proper|successful response|as expected)\b",
    re.IGNORECASE,
)

_SUSPICIOUS_ACTION_TOKENS: Sequence[str] = (
    "login",
    "log",
    "dashboard",
    "browser",
    "username",
    "password",
    "redirect",
    "authentication",
    "profile",
    "navigate",
    "click",
    "submit",
)

_ALLOWED_PUBLIC_WARNINGS: set[str] = {
    "generic_step",
    "generic_expected_result",
    "missing_literal_value",
    "missing_background_preconditions",
    "missing_given_preconditions",
    "irrelevant_or_invented_step",
    "unsupported_precondition",
    "redundant_step",
    "redundant_expected_result",
    "duplicate_expected_result",
    "assertion_in_step",
    "action_in_expected_result",

    "contradictory_exit_expectations",
    "invented_expected_literal",
    "unsupported_action_step",
    "missing_when_action_literal",

    "min_test_steps_not_met",
    "min_expected_results_not_met",
    "max_5_steps_exceeded",
    "max_3_expected_results_exceeded",
}

_WARNING_METADATA: Dict[str, Dict[str, str]] = {
    "generic_step": {"severity": "low", "message": "Test step is too generic (observe/examine/save output)"},
    "generic_expected_result": {
        "severity": "low",
        "message": "Expected result is too generic (without errors/success)",
    },
    "missing_literal_value": {"severity": "high", "message": "Important literal value is missing"},
    "missing_background_preconditions": {
        "severity": "medium",
        "message": "Missing background conditions in preconditions",
    },
    "missing_given_preconditions": {"severity": "medium", "message": "Given preconditions are missing"},
    "irrelevant_or_invented_step": {
        "severity": "high",
        "message": "Step is not supported by the source scenario",
    },
    "redundant_step": {"severity": "low", "message": "Duplicate or near-duplicate test step"},
    "redundant_expected_result": {
        "severity": "low",
        "message": "Duplicate or near-duplicate expected result",
    },
    "duplicate_expected_result": {
        "severity": "low",
        "message": "Duplicate expected result removed during normalization",
    },
    "assertion_in_step": {"severity": "medium", "message": "Assertion should be in Expected Results"},
    "action_in_expected_result": {
        "severity": "medium",
        "message": "Expected result contains an action; move actions to Test Steps",
    },
    "contradictory_exit_expectations": {
        "severity": "high",
        "message": (
            "Expected Results contain both success (exit 0) and failure "
            "(non-zero exit) expectations"
        ),
    },
    "invented_expected_literal": {
        "severity": "high",
        "message": "Expected result contains a literal value not found in the scenario",
    },
    "unsupported_action_step": {
        "severity": "high",
        "message": (
            "Test step includes an action not implied by the scenario "
            "(e.g., update directory, open editor)"
        ),
    },
    "unsupported_precondition": {
        "severity": "high",
        "message": (
            "Precondition includes an unsupported invented context "
            "(e.g., directory/location)"
        ),
    },
    "missing_when_action_literal": {
        "severity": "high",
        "message": "When-step literal action from the scenario is missing or changed",
    },
    "min_test_steps_not_met": {"severity": "low", "message": "Minimum test steps not met"},
    "min_expected_results_not_met": {
        "severity": "medium",
        "message": "Minimum number of expected results not met",
    },
    "max_5_steps_exceeded": {
        "severity": "low",
        "message": "Exceeded max 5 test steps for constraint strategy",
    },
    "max_3_expected_results_exceeded": {
        "severity": "low",
        "message": "Exceeded max 3 expected results for constrained strategies",
    },
}


_DIRECTORY_CONTEXT_PATTERNS: Sequence[re.Pattern[str]] = (
    re.compile(r"\b(current|root)\s+directory\b", re.IGNORECASE),
    re.compile(r"\bworking\s+directory\b", re.IGNORECASE),
    re.compile(r"\b(subdirectory|sub-directory)\b", re.IGNORECASE),
    re.compile(r"\bfrom\s+subdirectory\b", re.IGNORECASE),
    re.compile(r"\bin\s+subdirectory\b", re.IGNORECASE),
    re.compile(r"\btickets\s+directory\s+root\b", re.IGNORECASE),
    re.compile(r"\bsrc\b", re.IGNORECASE),
)

_STDERR_CAPTURE_PATTERNS: Sequence[re.Pattern[str]] = (
    re.compile(r"\bcapture\b.*\bstderr\b", re.IGNORECASE),
    re.compile(r"\bstderr\b", re.IGNORECASE),
)

_INVENTED_CONTEXT_PATTERNS: Sequence[re.Pattern[str]] = (

    re.compile(r"\b(environment|env|setup|configuration|config)\b", re.IGNORECASE),
    re.compile(r"\b(auth|authentication|login|log\s*in|sign\s*in)\b", re.IGNORECASE),
)

_INVENTED_HELPER_CMD_PATTERNS: Sequence[re.Pattern[str]] = (
    re.compile(r"^\s*(echo|cat|type|touch)\b", re.IGNORECASE),
    re.compile(r"\b(echo|cat|type|touch)\b", re.IGNORECASE),

    re.compile(r"[<>]{1,2}", re.IGNORECASE),
    re.compile(r"\boutput\.txt\b", re.IGNORECASE),

    re.compile(r"\b[a-z]:\\", re.IGNORECASE),
    re.compile(r"\b\./|\b\.\.\/", re.IGNORECASE),
)


def _scenario_mentions_directory_context(scenario_text: str) -> bool:
    """Check whether scenario text explicitly mentions directory context."""
    if not scenario_text:
        return False


    # Treat directory/location context as invented unless the scenario explicitly mentions it.
    return bool(
        re.search(
            (
                r"\b(subdirectory|sub-directory|working\s+directory|current\s+directory|root\s+directory|"
                r"from\s+subdirectory|\bin\s+subdirectory|\bcd\b)\b"
            ),
            scenario_text,
            flags=re.IGNORECASE,
        )
    )


def _scenario_mentions_stderr(scenario_text: str) -> bool:
    """Check whether scenario text explicitly mentions stderr usage."""
    return bool(re.search(r"\bstderr\b", scenario_text or "", flags=re.IGNORECASE))


def _scenario_mentions_helper_commands(scenario_text: str) -> bool:
    """Check whether helper shell commands are explicitly present."""
    if not scenario_text:
        return False
    # Helper shell commands are allowed only when explicitly present in the scenario text.
    return bool(
        re.search(
            r"\b(echo|cat|type|touch|output\.txt)\b|[<>]{1,2}",
            scenario_text,
            flags=re.IGNORECASE,
        )
    )
















def detect_expected_failure(scenario: Dict[str, Any]) -> bool:
    """Return True if Then-steps indicate a non-zero/failed outcome is expected."""
    then_steps = split_steps(scenario.get("steps") or []).get("then") or []
    then_blob = "\n".join((s.get("text") or "") for s in then_steps)
    then_blob = then_blob.lower()




    return bool(
        re.search(
            r"\b(should\s+fail|command\s+should\s+fail|fails?|failure|non[-\s]?zero)\b",
            then_blob,
            flags=re.IGNORECASE,
        )
        or re.search(
            r"\b(exit|status|return)\s*(code)?\s*(is\s*)?(non[-\s]?zero|[1-9]\d*)\b",
            then_blob,
            flags=re.IGNORECASE,
        )
    )


def _has_exit_expectation(expected_blob: str, expected_failure: bool) -> bool:
    """Return True when expected results include an exit/status expectation."""
    if expected_failure:
        return bool(
            re.search(
                r"\b(exit|status|return)\s*(code)?\s*(is\s*)?(non[-\s]?zero|[1-9]\d*)\b",
                expected_blob,
                flags=re.IGNORECASE,
            )
            or re.search(r"\bfail(s|ed|ure)?\b", expected_blob, flags=re.IGNORECASE)
        )
    return bool(any(p.search(expected_blob) for p in _CONCRETE_EXIT_CODE_PATTERNS))
















def enforce_expected_results_checks(
    strategy: str,
    scenario: Dict[str, Any],
    parsed: Dict[str, Any],
    expected_failure: bool = False,
) -> Tuple[bool, Dict[str, Any]]:
    """Ensure Expected Results contain required exit/output/literal checks."""
    changed = False
    expected: List[str] = parsed.get("expected_results", []) or []

    lits = _scenario_literals(scenario)
    ids = lits.get("ids") or []
    contents = lits.get("contents") or []
    output_assertions = lits.get("output_assertions") or []
    output_negative_assertions = lits.get("output_negative_assertions") or []
    field_assertions = lits.get("field_assertions") or []
    field_negative_assertions = lits.get("field_negative_assertions") or []
    relation_assertions = lits.get("relation_assertions") or []
    relation_negative_assertions = lits.get("relation_negative_assertions") or []

    required_checks: List[str] = []


    if output_assertions:
        required_checks.append(f'Output contains "{output_assertions[0]}"')

    if output_negative_assertions:
        required_checks.append(f'Output does not contain "{output_negative_assertions[0]}"')



    if expected_failure and not output_assertions and not output_negative_assertions:
        then_steps = split_steps(scenario.get("steps") or []).get("then") or []
        then_blob = " ".join(str(s.get("text") or "") for s in then_steps if isinstance(s, dict))
        then_quoted = _extract_quoted_literals(then_blob)
        if then_quoted:
            required_checks.append(f'Output contains "{then_quoted[0]}"')


    if field_assertions:
        required_checks.append(field_assertions[0])
    if field_negative_assertions:
        required_checks.append(field_negative_assertions[0])


    if relation_assertions:
        required_checks.append(relation_assertions[0])
    if relation_negative_assertions:
        required_checks.append(relation_negative_assertions[0])



    if not expected_failure:
        if ids:

            required_checks.append(f'Output contains "{ids[0]}"')
        if contents:
            required_checks.append(f'Output contains "{contents[0]}"')


    max_expected = 3 if strategy == "constraint_prompting" else 12

    blob = "\n".join(expected)
    missing_checks = [c for c in required_checks if c.split('"')[1] not in blob]

    if not _has_exit_expectation(blob, expected_failure):
        if expected_failure:
            missing_checks.append("Exit/status code is non-zero")
        else:
            missing_checks.append("Exit/status code is 0")

    if not missing_checks:
        return False, {"missing": []}

    for check in missing_checks:
        if len(expected) < max_expected:
            expected.append(check)
            changed = True
        else:
            expected[0] = _collapse_ws(f"{expected[0]} and {check.lower()}")
            changed = True

    if changed:
        parsed["expected_results"] = expected

    return changed, {"missing": missing_checks[:10]}


def compute_hallucination_score(
    scenario: Dict[str, Any], parsed: Dict[str, Any]
) -> Tuple[float, Dict[str, Any]]:
    """Score hallucinations by counting unsupported literals/details in the test case."""
    scenario_vocab = _scenario_vocabulary(scenario)
    scenario_lits = _scenario_literals(scenario)
    allowed_literals = set(scenario_lits.get("all", []) or [])
    allowed_quoted = set(
        _extract_quoted_literals(
            " ".join([s.get("text", "") for s in (scenario.get("steps") or [])])
        )
    )
    allowed_literal_keys = {
        _normalize_literal_for_match(x)
        for x in (list(allowed_literals) + list(allowed_quoted))
        if _normalize_literal_for_match(x)
    }
    scenario_fields = set(
        m.group(1).strip().lower()
        for m in re.finditer(
            r"\b([a-z][a-z0-9_-]{1,20})\s*:\s*\S",
            " ".join([str(s.get("text") or "") for s in (scenario.get("steps") or [])]),
            flags=re.IGNORECASE,
        )
    )

    items: List[Tuple[str, str]] = []
    for s in parsed.get("steps", []) or []:
        items.append(("step", s))
    for r in parsed.get("expected_results", []) or []:
        items.append(("expected_result", r))

    hallucinated: List[Dict[str, Any]] = []
    for kind, text in items:
        norm_tokens = set(_normalize_for_dedupe(text).split())
        suspicious = [
            t
            for t in _SUSPICIOUS_ACTION_TOKENS
            if t in norm_tokens and t not in scenario_vocab
        ]

        invented_literals: List[str] = []
        for q in _extract_quoted_literals(text):
            q_key = _normalize_literal_for_match(q)
            if "<" in q and ">" in q:
                invented_literals.append(q)
            elif q_key and q_key not in allowed_literal_keys:
                invented_literals.append(q)

        invented_fields: List[str] = []


        unquoted_text = re.sub(r"\"[^\"]*\"", " ", str(text or ""))
        for m in re.finditer(
            r"\b([a-z][a-z0-9_-]{1,20})\s*:\s*\S",
            unquoted_text,
            flags=re.IGNORECASE,
        ):
            key = m.group(1).strip().lower()

            if key not in scenario_fields:
                invented_fields.append(key)

        if suspicious or invented_literals or invented_fields:
            hallucinated.append(
                {
                    "type": kind,
                    "text": text[:200],
                    "suspicious_tokens": suspicious,
                    "invented_literals": invented_literals[:10],
                    "invented_fields": invented_fields[:10],
                }
            )

    total_items = len(items)
    hallucinated_items = len(hallucinated)
    score = (
        1.0
        if total_items == 0
        else max(0.0, 1.0 - (hallucinated_items / total_items))
    )
    return round(score, 3), {
        "hallucinated_items": hallucinated_items,
        "total_items": total_items,
        "samples": hallucinated[:10],
    }


def _has_concrete_expected_result(text: str, key_literals: Sequence[str]) -> bool:
    """Return True when expected-result text contains concrete assertions."""
    if any(lit and lit in text for lit in key_literals):
        return True
    if any(p.search(text) for p in _CONCRETE_EXIT_CODE_PATTERNS):
        return True
    if _has_inline_literal(text):
        return True
    if re.search(r"\b(id|content|body)\s*:\s*\S", text, flags=re.IGNORECASE):
        return True
    return False


def _has_concrete_step(text: str, key_literals: Sequence[str]) -> bool:
    """Return True when step text is concrete and literal-grounded."""
    if any(lit and lit in text for lit in key_literals):
        return True
    if _has_inline_literal(text):
        return True
    if any(p.search(text) for p in _CONCRETE_EXIT_CODE_PATTERNS):
        return True
    if re.search(r"\bticket\s+show\b", text, flags=re.IGNORECASE):
        return True
    return False


def compute_specificity_score(
    scenario: Dict[str, Any], parsed: Dict[str, Any]
) -> Tuple[float, Dict[str, Any]]:
    """Score specificity based on concrete actions/assertions and preserved literals."""
    lits = _scenario_literals(scenario)
    key_literals = lits.get("key", []) or []

    items: List[Tuple[str, str]] = []
    for s in parsed.get("steps", []) or []:
        items.append(("step", s))
    for r in parsed.get("expected_results", []) or []:
        items.append(("expected_result", r))

    concrete = 0
    vague = 0
    samples: List[Dict[str, Any]] = []

    for kind, text in items:
        is_concrete = (
            _has_concrete_expected_result(text, key_literals)
            if kind == "expected_result"
            else _has_concrete_step(text, key_literals)
        )

        if is_concrete:
            concrete += 1
        if _VAGUE_WORDS_PATTERN.search(text):
            vague += 1
            if len(samples) < 10:
                samples.append({"type": kind, "text": text[:200]})

    total_items = len(items)
    base = 1.0 if total_items == 0 else concrete / total_items
    penalty = 0.0 if total_items == 0 else min(0.5, vague / total_items * 0.5)
    score = max(0.0, base - penalty)
    return round(score, 3), {
        "concrete_items": concrete,
        "total_items": total_items,
        "vague_items": vague,
        "vague_samples": samples,
    }


def validate_semantic_quality(
    scenario: Dict[str, Any], parsed: Dict[str, Any], expected_failure: bool = False
) -> Tuple[List[str], Dict[str, Any]]:
    """Validate semantic quality and grounding; returns (warnings, semantic_details)."""
    warnings: List[str] = []

    scenario_text_blob = " ".join(
        [
            str(s.get("text") or "")
            for s in (list(scenario.get("background") or []) + list(scenario.get("steps") or []))
            if isinstance(s, dict)
        ]
    )
    scenario_supports_dir_context = _scenario_mentions_directory_context(scenario_text_blob)
    scenario_supports_stderr = _scenario_mentions_stderr(scenario_text_blob)
    scenario_supports_helpers = _scenario_mentions_helper_commands(scenario_text_blob)

    steps: List[str] = parsed.get("steps", []) or []
    expected: List[str] = parsed.get("expected_results", []) or []
    preconditions: List[str] = parsed.get("preconditions", []) or []

    step_dupes = _find_duplicates(steps)
    expected_dupes = _find_duplicates(expected)

    if step_dupes["exact_duplicate_count"] or step_dupes["near_duplicate_count"]:
        warnings.append("redundant_step")
    if expected_dupes["exact_duplicate_count"] or expected_dupes["near_duplicate_count"]:
        warnings.append("redundant_expected_result")

    literals = _scenario_literals(scenario)
    key_literals = literals["key"]

    assertion_like_step_count = 0
    assertion_like_step_samples: List[str] = []
    _ASSERTION_IN_STEP_PATTERNS: Sequence[re.Pattern[str]] = (
        re.compile(r"^\s*(verify|check|ensure|confirm|validate|assert|expect)\b", re.IGNORECASE),
        re.compile(r"\b(verify|check|ensure|confirm|validate|assert)\b", re.IGNORECASE),
        re.compile(r"\b(output|stdout|stderr)\s+contains\b", re.IGNORECASE),
        re.compile(r"\b(the\s+)?output\s+should\b", re.IGNORECASE),
        re.compile(r"\bexit\s*(status\s*)?code\b", re.IGNORECASE),
        re.compile(r"\bstatus\s*code\b", re.IGNORECASE),
    )
    for s in steps:
        if not s:
            continue
        if any(p.search(s) for p in _ASSERTION_IN_STEP_PATTERNS):
            assertion_like_step_count += 1
            if len(assertion_like_step_samples) < 5:
                assertion_like_step_samples.append(s[:160])
    if assertion_like_step_count:
        warnings.append("assertion_in_step")

    unsupported_action_count = 0
    _UNSUPPORTED_STEP_PATTERNS: Sequence[re.Pattern[str]] = (
        re.compile(r"\b(update|change|set)\s+(the\s+)?working\s+directory\b", re.IGNORECASE),
        re.compile(r"\bchange\s+directory\b", re.IGNORECASE),
        re.compile(r"^\s*cd\s+\S+", re.IGNORECASE),
        re.compile(r"\b(from|in)\s+(the\s+)?subdirectory\b", re.IGNORECASE),
    )
    scenario_mentions_dir_change = bool(
        re.search(
            r"\b(working\s+directory|change\s+directory|\bcd\b)\b",
            scenario_text_blob,
            flags=re.IGNORECASE,
        )
    )
    if not scenario_mentions_dir_change:
        for s in steps:
            if not s:
                continue
            if any(p.search(s) for p in _UNSUPPORTED_STEP_PATTERNS):
                unsupported_action_count += 1
    if unsupported_action_count:
        warnings.append("unsupported_action_step")


    unsupported_precondition_count = 0
    if not scenario_supports_dir_context:
        for p in preconditions:
            if not p:
                continue
            if any(rx.search(p) for rx in _DIRECTORY_CONTEXT_PATTERNS):
                unsupported_precondition_count += 1
            if any(rx.search(p) for rx in _INVENTED_CONTEXT_PATTERNS):
                unsupported_precondition_count += 1
    if unsupported_precondition_count:
        warnings.append("unsupported_precondition")

    if not scenario_supports_dir_context:
        for s in steps:
            if not s:
                continue
            if any(rx.search(s) for rx in _DIRECTORY_CONTEXT_PATTERNS):
                warnings.append("irrelevant_or_invented_step")
                break


    if not scenario_supports_dir_context:
        for s in steps:
            if not s:
                continue
            if any(rx.search(s) for rx in _INVENTED_CONTEXT_PATTERNS):
                warnings.append("irrelevant_or_invented_step")
                break


    if not scenario_supports_stderr:
        for s in steps:
            if not s:
                continue
            if any(rx.search(s) for rx in _STDERR_CAPTURE_PATTERNS):
                warnings.append("irrelevant_or_invented_step")
                break


    if not scenario_supports_helpers:
        for p in preconditions:
            if not p:
                continue
            if any(rx.search(p) for rx in _INVENTED_HELPER_CMD_PATTERNS):
                if "unsupported_precondition" not in warnings:
                    warnings.append("unsupported_precondition")
                break
        for s in steps:
            if not s:
                continue
            if any(rx.search(s) for rx in _INVENTED_HELPER_CMD_PATTERNS):
                warnings.append("irrelevant_or_invented_step")
                break

    action_like_expected_count = 0
    action_like_expected_samples: List[str] = []
    _ACTION_IN_EXPECTED_PATTERNS: Sequence[re.Pattern[str]] = (
        re.compile(r"^\s*(run|execute|open|create|delete|update|list|set)\b", re.IGNORECASE),
        re.compile(r"^\s*(click|navigate|login|log in|sign in|submit)\b", re.IGNORECASE),
    )
    for r in expected:
        if not r:
            continue
        if any(p.search(r) for p in _ACTION_IN_EXPECTED_PATTERNS):
            action_like_expected_count += 1
            if len(action_like_expected_samples) < 5:
                action_like_expected_samples.append(r[:160])
    if action_like_expected_count:
        warnings.append("action_in_expected_result")

    generic_step_count = 0
    for s in steps:
        is_generic_output_step = any(p.search(s) for p in _GENERIC_STEP_PATTERNS)
        is_vague_step = any(p.search(s) for p in _VAGUE_STEP_PATTERNS)
        looks_generic = is_generic_output_step or is_vague_step

        if is_vague_step:
            has_key_value_check = bool(
                re.search(r"\b(id|content|body)\s*:", s, flags=re.IGNORECASE)
            )
            concrete = bool(
                any(lit and lit in s for lit in key_literals)
                or has_key_value_check
                or re.search(r"\bticket\s+show\b", s, flags=re.IGNORECASE)
                or _has_inline_literal(s)
            )
        else:
            concrete = _has_concrete_step(s, key_literals)

        if looks_generic and not concrete:
            generic_step_count += 1
    if generic_step_count:
        warnings.append("generic_step")

    generic_expected_without_literals = 0
    for r in expected:
        looks_generic = any(p.search(r) for p in _GENERIC_EXPECTED_RESULT_PATTERNS) or len(
            r
        ) <= 45
        if looks_generic and not _has_concrete_expected_result(r, key_literals):
            generic_expected_without_literals += 1
    if generic_expected_without_literals:
        warnings.append("generic_expected_result")

    missing_literals: List[str] = []
    expected_blob = "\n".join(expected)

    then_steps = split_steps(scenario.get("steps") or []).get("then") or []
    then_texts = [str(s.get("text") or "") for s in then_steps if isinstance(s, dict)]
    then_blob = " ".join(then_texts)
    then_quoted_literals = _extract_quoted_literals(then_blob)


    required_then_literals = (
        (literals.get("output_assertions") or [])
        + (literals.get("output_negative_assertions") or [])
    ) or then_quoted_literals

    for lit in required_then_literals:
        if lit and not _lit_matches_text(lit, expected_blob):
            missing_literals.append(lit)


    def _covers_assertion(assertion: str, blob: str) -> bool:
        """Match assertion against blob using exact or token-similarity checks."""
        if not assertion or not blob:
            return False
        a = _collapse_ws(assertion).lower()
        b = _collapse_ws(blob).lower()
        if a in b:
            return True

        aset = _token_set(a)
        bset = _token_set(b)
        return _jaccard(aset, bset) >= 0.85

    for assertion in (literals.get("field_assertions") or [])[:1]:
        if assertion and not _covers_assertion(assertion, expected_blob):
            missing_literals.append(assertion)
    for assertion in (literals.get("field_negative_assertions") or [])[:1]:
        if assertion and not _covers_assertion(assertion, expected_blob):
            missing_literals.append(assertion)
    for assertion in (literals.get("relation_assertions") or [])[:1]:
        if assertion and not _covers_assertion(assertion, expected_blob):
            missing_literals.append(assertion)
    for assertion in (literals.get("relation_negative_assertions") or [])[:1]:
        if assertion and not _covers_assertion(assertion, expected_blob):
            missing_literals.append(assertion)
    if missing_literals:
        warnings.append("missing_literal_value")

    prec_warnings, prec_details = validate_preconditions_coverage(scenario, parsed)
    for w in prec_warnings:
        if w not in warnings:
            warnings.append(w)

    halluc_score, halluc_details = compute_hallucination_score(scenario, parsed)
    if halluc_details.get("hallucinated_items"):
        warnings.append("irrelevant_or_invented_step")

    specificity_score, specificity_details = compute_specificity_score(scenario, parsed)


    scenario_when_text = " ".join(
        [
            str(s.get("text") or "")
            for s in (scenario.get("steps") or [])
            if isinstance(s, dict) and str(s.get("type") or "").strip().lower() == "when"
        ]
    )
    scenario_then_text = " ".join(
        [
            str(s.get("text") or "")
            for s in (scenario.get("steps") or [])
            if isinstance(s, dict) and str(s.get("type") or "").strip().lower() == "then"
        ]
    )
    when_literals = _extract_quoted_literals(scenario_when_text)
    then_literals = _extract_quoted_literals(scenario_then_text)

    steps_blob = "\n".join(steps)
    expected_blob2 = "\n".join(expected)

    missing_when_actions = [lit for lit in when_literals if lit and lit not in steps_blob]
    missing_then_assertions = [lit for lit in then_literals if lit and lit not in expected_blob2]

    if missing_when_actions:
        warnings.append("missing_when_action_literal")

    missing_key_literals_in_testcase = [
        lit
        for lit in (key_literals or [])
        if lit and (lit not in steps_blob) and (lit not in expected_blob2)
    ]


    step_token_sets = [_token_set(s) for s in steps if s]
    unlinked_expected_results = 0
    for r in expected:
        rset = _token_set(r)
        if not rset:
            continue
        if step_token_sets and all(len(rset & sset) == 0 for sset in step_token_sets):
            unlinked_expected_results += 1

    details = {
        "duplicate_steps": step_dupes,
        "duplicate_expected_results": expected_dupes,
        "scenario_literals": literals,
        "generic_step_count": generic_step_count,
        "generic_expected_result_count": generic_expected_without_literals,
        "preconditions_coverage": prec_details,
        "missing_literal_values": missing_literals[:10],
        "hallucination": {"score": halluc_score, **halluc_details},
        "specificity": {"score": specificity_score, **specificity_details},
        "assertion_in_step": {
            "count": assertion_like_step_count,
            "samples": assertion_like_step_samples,
        },
        "action_in_expected_result": {
            "count": action_like_expected_count,
            "samples": action_like_expected_samples,
        },
        "missing_when_actions": missing_when_actions[:10],
        "missing_then_assertions": missing_then_assertions[:10],
        "missing_key_literals_in_testcase": missing_key_literals_in_testcase[:10],
        "unlinked_expected_results": unlinked_expected_results,
    }

    return warnings, details


def normalize_public_warnings(raw_warnings: Sequence[str]) -> List[str]:
    """Filter and de-duplicate warnings to the public warning set used in reports."""
    out: List[str] = []
    seen: set[str] = set()
    for w in raw_warnings:
        if w not in _ALLOWED_PUBLIC_WARNINGS:
            continue
        if w in seen:
            continue
        out.append(w)
        seen.add(w)
    return out


def enrich_warnings(warnings: Sequence[str]) -> List[Dict[str, str]]:
    """Convert warning types to rich objects including severity and message."""
    enriched = []
    for w in warnings:
        # Preserve a stable schema so reporting can treat all warnings uniformly.
        meta = _WARNING_METADATA.get(w, {"severity": "medium", "message": w})
        enriched.append(
            {
                "type": w,
                "severity": meta["severity"],
                "message": meta["message"],
            }
        )
    return enriched


def validate_constraints(strategy: str, parsed: Dict[str, Any]) -> List[str]:
    """Validate strategy-specific formatting constraints and return warning types."""
    issues: List[str] = []

    steps_count = len(parsed.get("steps", []) or [])
    expected_count = len(parsed.get("expected_results", []) or [])

    if steps_count < MIN_TEST_STEPS:
        issues.append("min_test_steps_not_met")

    if expected_count < MIN_EXPECTED_RESULTS:
        issues.append("min_expected_results_not_met")

    if strategy == "constraint_prompting":
        if steps_count > 5:
            issues.append("max_5_steps_exceeded")

    if strategy == "few_shot_prompting":


        pass

    return issues
