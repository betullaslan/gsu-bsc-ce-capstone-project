"""Post-processing utilities for parsed test cases.

These helpers normalize formatting, remove duplication, and enforce separation between
actions (steps) and assertions (expected results).
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Sequence, Tuple


def _norm_for_dedupe(text: str) -> str:
    """Normalize text for duplicate comparison."""
    t = (text or "").strip().lower()
    prefixes = ["• ", "- ", "* ", ". "]
    for prefix in prefixes:
        if t.startswith(prefix):
            t = t[len(prefix):].lstrip()
            break
    t = re.sub(r"\s+", " ", t).strip()
    t = t.rstrip(".;").rstrip()
    return t


def _capitalize_leading_alpha(text: str) -> str:
    """Capitalize leading alpha char when appropriate."""
    t = (text or "").strip()
    if not t:
        return t
    if t[0] in {'"', "`"}:
        return t
    if "a" <= t[0] <= "z":
        return t[0].upper() + t[1:]
    return t


def _strip_leading_bullet(text: str) -> str:
    """Remove a leading bullet marker from a line."""
    t = (text or "").strip()
    if not t:
        return t
    prefixes = [
        "• ",
        "- ",
        "* ",
        ". ",
    ]
    for prefix in prefixes:
        if t.startswith(prefix):
            t = t[len(prefix):].lstrip()
            return t
    return t


def _strip_trailing_punct(text: str) -> str:
    """Trim trailing punctuation used as list sentence endings."""
    t = (text or "").strip()
    return t.rstrip(".;").rstrip()


def _dedupe_by_norm(items: List[str]) -> Tuple[List[str], int]:
    """Drop exact duplicates using normalized keys."""
    out: List[str] = []
    seen: set[str] = set()
    removed = 0
    for x in items:
        raw = str(x or "").strip()
        if not raw:
            continue
        key = _norm_for_dedupe(raw)
        if not key:
            continue
        if key in seen:
            removed += 1
            continue
        out.append(raw)
        seen.add(key)
    return out, removed


def _dedupe_near_duplicates(items: List[str], threshold: float = 0.85) -> Tuple[List[str], int]:
    """Drop near-duplicate items based on token-set Jaccard similarity."""
    # Stop words prevent generic glue words from inflating similarity.
    stop = {
        "the",
        "a",
        "an",
        "to",
        "of",
        "and",
        "or",
        "in",
        "on",
        "with",
        "is",
        "are",
        "be",
        "should",
        "must",
        "that",
        "this",
        "as",
        "for",
        "from",
    }

    def _tokset(s: str) -> set[str]:
        """Create normalized token set for similarity comparisons."""
        t = _norm_for_dedupe(s)
        t = re.sub(r"[`\"']", "", t)
        t = re.sub(r"[^a-z0-9\s:./_-]+", " ", t)
        t = re.sub(r"\s+", " ", t).strip()
        toks = [x for x in t.split() if x and x not in stop]
        return set(toks)

    kept: List[str] = []
    kept_sets: List[set[str]] = []
    removed = 0

    for raw in items:
        s = str(raw or "").strip()
        if not s:
            continue
        sset = _tokset(s)
        is_near_dupe = False
        for kset in kept_sets:
            if not sset or not kset:
                continue
            inter = len(sset & kset)
            union = len(sset | kset)
            sim = (inter / union) if union else 0.0
            if sim >= threshold:
                is_near_dupe = True
                break
        if is_near_dupe:
            removed += 1
            continue
        kept.append(s)
        kept_sets.append(sset)

    return kept, removed


def normalize_and_dedupe_test_case(parsed: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, int]]:
    """Normalize a parsed test case and remove duplicates in each section."""
    removed_counts: Dict[str, int] = {"preconditions": 0, "steps": 0, "expected_results": 0}

    pre = parsed.get("preconditions") or []
    st = parsed.get("steps") or []
    ex = parsed.get("expected_results") or []

    if isinstance(pre, list):
        deduped, removed = _dedupe_by_norm([str(x) for x in pre])
        parsed["preconditions"] = [
            _capitalize_leading_alpha(_strip_trailing_punct(_strip_leading_bullet(x)))
            for x in deduped
        ]
        removed_counts["preconditions"] = removed

    if isinstance(st, list):
        deduped, removed = _dedupe_by_norm([str(x) for x in st])
        parsed["steps"] = [
            _capitalize_leading_alpha(_strip_trailing_punct(_strip_leading_bullet(x)))
            for x in deduped
        ]
        removed_counts["steps"] = removed

    if isinstance(ex, list):
        deduped, removed = _dedupe_by_norm([str(x) for x in ex])
        parsed["expected_results"] = [
            _capitalize_leading_alpha(_strip_trailing_punct(_strip_leading_bullet(x)))
            for x in deduped
        ]
        removed_counts["expected_results"] = removed

    return parsed, removed_counts


def normalize_constraint_expected_results(parsed: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """Apply constraint-strategy normalization rules for expected results."""
    expected = parsed.get("expected_results") or []
    if not isinstance(expected, list) or not expected:
        return parsed, 0

    deduped, removed = _dedupe_near_duplicates([str(x) for x in expected], threshold=0.85)
    parsed["expected_results"] = [
        _capitalize_leading_alpha(_strip_trailing_punct(_strip_leading_bullet(x))) for x in deduped
    ]
    return parsed, removed


def split_atomic_expected_results(items: List[str]) -> List[str]:
    """Split multi-assertion expected-result lines into atomic assertions."""
    out: List[str] = []
    for raw in items:
        s = str(raw or "").strip()
        if not s:
            continue
        s = _strip_trailing_punct(_strip_leading_bullet(s))
        quotes = re.findall(r"\"([^\"]+)\"", s)
        if len(quotes) >= 2 and ("contain" in s.lower() or "contains" in s.lower()):
            for q in quotes:
                out.append(f'Output contains "{q}"')
            continue
        out.append(s)
    return out


def enforce_steps_expected_separation(parsed: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Move assertion-like text out of Test Steps into Expected Results."""
    steps = list(parsed.get("steps") or [])
    expected = list(parsed.get("expected_results") or [])

    moved_to_expected: List[str] = []
    removed_steps: List[str] = []

    def _norm(s: str) -> str:
        """Normalize a candidate step/assertion line."""
        return _strip_trailing_punct(_strip_leading_bullet(str(s or "").strip()))

    def _as_expected_from_step(step_text: str) -> str:
        """Convert assertion-like step text to expected-result phrasing."""
        t = _norm(step_text)
        low = t.lower()
        t = re.sub(r"^\s*(verify|check|ensure|confirm|assert|expect)\b\s*", "", t, flags=re.IGNORECASE)
        t = t.strip()
        low2 = t.lower()

        if "output contains" in low2:
            m = re.search(r"output\s+contains\s+(\"[^\"]+\"|`[^`]+`|.+)$", t, flags=re.IGNORECASE)
            return (
                f"Output contains {m.group(1).strip()}"
                if m
                else f"Output contains {t.split('contains',1)[-1].strip()}"
            )
        if "the output contains" in low2:
            m = re.search(r"the\s+output\s+contains\s+(\"[^\"]+\"|`[^`]+`|.+)$", t, flags=re.IGNORECASE)
            return (
                f"Output contains {m.group(1).strip()}"
                if m
                else f"Output contains {t.split('contains',1)[-1].strip()}"
            )
        if "exit/status code" in low or "exit code" in low or "status code" in low:
            if re.search(r"\b0\b", low):
                return "Exit/status code is 0"
            if re.search(r"\bnon-?zero\b", low):
                return "Exit/status code is non-zero"
            return "Exit/status code is as expected"

        return t

    assertion_like = ("verify ", "check ", "ensure ", "confirm ", "assert ", "expect ")

    new_steps: List[str] = []
    for raw in steps:
        s = _norm(str(raw))
        low = s.lower()
        if not s:
            continue
        if (
            low.startswith(assertion_like)
            or "output contains" in low
            or "exit/status code" in low
            or "exit code" in low
            or "status code" in low
        ):
            moved = _as_expected_from_step(s)
            if moved:
                moved_to_expected.append(moved)
            removed_steps.append(s)
            continue
        new_steps.append(s)

    if moved_to_expected:
        expected = expected + moved_to_expected
        expected = split_atomic_expected_results(expected)
        expected, _ = _dedupe_by_norm([str(x) for x in expected])

    parsed["steps"] = new_steps
    parsed["expected_results"] = expected

    return parsed, {
        "moved_step_assertions_to_expected": moved_to_expected[:10],
        "removed_steps": removed_steps[:10],
    }


def normalize_steps_strict_style(items: List[str]) -> List[str]:
    """Normalize step text to a strict executable-action style."""
    out: List[str] = []
    for raw in items:
        s = str(raw or "").strip()
        if not s:
            continue
        s = _strip_trailing_punct(_strip_leading_bullet(s))
        low = s.lower()
        if low.startswith("run the command "):
            s = "Run " + s[len("Run the command ") :].lstrip()
        if low.startswith("execute "):
            s = "Run " + s[len("Execute ") :].lstrip()
        out.append(s)
    return out


def enforce_no_invented_context(
    scenario_obj: Dict[str, Any],
    parsed: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Remove preconditions/steps that introduce context not present in the scenario."""
    scenario_text = " ".join(
        [
            str(s.get("text") or "")
            for s in (list(scenario_obj.get("background") or []) + list(scenario_obj.get("steps") or []))
            if isinstance(s, dict)
        ]
    )

    def _mentions(pattern: str) -> bool:
        """Return True if scenario text matches the given regex pattern."""
        return bool(re.search(pattern, scenario_text or "", flags=re.IGNORECASE))

    scenario_supports_dir = _mentions(
        (
            r"\b(subdirectory|sub-directory|working\s+directory|current\s+directory|root\s+directory|"
            r"from\s+subdirectory|\bin\s+subdirectory|\bcd\b|\bsrc\b)\b"
        )
    )
    scenario_supports_helpers = _mentions(r"\b(echo|cat|type|touch|output\.txt)\b|[<>]{1,2}")
    scenario_supports_env_auth = _mentions(
        r"\b(environment|env|setup|config|auth|authentication|login|log\s*in|sign\s*in)\b"
    )

    dir_patterns: Sequence[re.Pattern[str]] = (
        re.compile(r"\b(current|root)\s+directory\b", re.IGNORECASE),
        re.compile(r"\bworking\s+directory\b", re.IGNORECASE),
        re.compile(r"\b(subdirectory|sub-directory)\b", re.IGNORECASE),
        re.compile(r"\bfrom\s+subdirectory\b", re.IGNORECASE),
        re.compile(r"\bin\s+subdirectory\b", re.IGNORECASE),
        re.compile(r"\btickets\s+directory\s+root\b", re.IGNORECASE),
        re.compile(r"\bsrc\b", re.IGNORECASE),
        re.compile(r"^\s*cd\s+\S+", re.IGNORECASE),
    )
    helper_patterns: Sequence[re.Pattern[str]] = (
        re.compile(r"^\s*(echo|cat|type|touch)\b", re.IGNORECASE),
        re.compile(r"\boutput\.txt\b", re.IGNORECASE),
        re.compile(r"[<>]{1,2}", re.IGNORECASE),
        re.compile(r"\b[a-z]:\\", re.IGNORECASE),
        re.compile(r"\b\./|\b\.\.\/", re.IGNORECASE),
    )
    env_auth_patterns: Sequence[re.Pattern[str]] = (
        re.compile(r"\b(environment|env|setup|configuration|config)\b", re.IGNORECASE),
        re.compile(r"\b(auth|authentication|login|log\s*in|sign\s*in)\b", re.IGNORECASE),
    )

    removed_preconditions: List[str] = []
    removed_steps: List[str] = []

    preconditions = [
        str(x or "").strip()
        for x in (parsed.get("preconditions") or [])
        if str(x or "").strip()
    ]
    steps = [
        str(x or "").strip()
        for x in (parsed.get("steps") or [])
        if str(x or "").strip()
    ]

    def _drop_if_matches(
        items: List[str],
        removed: List[str],
        patterns: Sequence[re.Pattern[str]],
    ) -> List[str]:
        """Filter out items that match any forbidden pattern."""
        out: List[str] = []
        for item in items:
            if any(p.search(item) for p in patterns):
                removed.append(item)
                continue
            out.append(item)
        return out

    if not scenario_supports_dir:
        preconditions = _drop_if_matches(preconditions, removed_preconditions, dir_patterns)
        steps = _drop_if_matches(steps, removed_steps, dir_patterns)

    if not scenario_supports_helpers:
        preconditions = _drop_if_matches(preconditions, removed_preconditions, helper_patterns)
        steps = _drop_if_matches(steps, removed_steps, helper_patterns)

    if not scenario_supports_env_auth:
        preconditions = _drop_if_matches(preconditions, removed_preconditions, env_auth_patterns)
        steps = _drop_if_matches(steps, removed_steps, env_auth_patterns)

    parsed["preconditions"] = preconditions
    parsed["steps"] = steps

    return parsed, {
        "removed_preconditions": removed_preconditions[:10],
        "removed_steps": removed_steps[:10],
    }

