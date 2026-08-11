"""Shared text normalization and literal-extraction utilities used by quality rules."""

import re
from typing import Any, Dict, Iterable, List, Sequence, Tuple

def _has_inline_literal(text: str) -> bool:
    """Return True when text contains quoted or backticked literals."""
    return bool(re.search(r"\"[^\"]+\"|`[^`]+`", text))


def _normalize_for_dedupe(text: str) -> str:
    """Normalize text into a canonical form for duplicate checks."""
    t = text.lower()
    t = re.sub(r"[`\"']", "", t)
    t = re.sub(r"[^a-z0-9\s:./_-]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()

    # Map common synonyms into a canonical form to improve near-duplicate detection.
    synonym_map = {
        "observe": "check",
        "examine": "check",
        "inspect": "check",
        "review": "check",
        "validate": "check",
        "verify": "check",
        "ensure": "check",
        "displayed": "show",
        "shown": "show",
        "output": "output",
    }
    tokens = [synonym_map.get(tok, tok) for tok in t.split()]
    return " ".join(tokens)


def _token_set(text: str) -> set[str]:
    """Build a normalized token set with common stop words removed."""
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
    toks = [t for t in _normalize_for_dedupe(text).split() if t and t not in stop]
    return set(toks)


def _jaccard(a: set[str], b: set[str]) -> float:
    """Compute Jaccard similarity between two token sets."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    inter = len(a.intersection(b))
    union = len(a.union(b))
    return inter / union if union else 0.0


def _find_duplicates(items: Sequence[str]) -> Dict[str, Any]:
    """Detect exact and near-duplicate entries from an item list."""
    normalized_keys: Dict[str, List[int]] = {}
    for i, item in enumerate(items):
        key = _normalize_for_dedupe(item)
        normalized_keys.setdefault(key, []).append(i)

    exact_groups = [idxs for idxs in normalized_keys.values() if len(idxs) >= 2]

    near_pairs: List[Tuple[int, int]] = []
    token_sets = [_token_set(x) for x in items]
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            if _jaccard(token_sets[i], token_sets[j]) >= 0.85:
                if _normalize_for_dedupe(items[i]) != _normalize_for_dedupe(items[j]):
                    near_pairs.append((i, j))

    return {
        "exact_groups": exact_groups,
        "near_pairs": near_pairs[:50],
        "exact_duplicate_count": sum(len(g) - 1 for g in exact_groups),
        "near_duplicate_count": len(near_pairs),
    }


def _extract_quoted_literals(text: str) -> List[str]:
    """Extract double-quoted literals from text."""
    return [m.group(1) for m in re.finditer(r"\"([^\"]+)\"", text)]


def _collapse_ws(text: str) -> str:
    """Collapse repeated whitespace and trim leading/trailing spaces."""
    return re.sub(r"\s+", " ", (text or "").strip())


def _normalize_literal_for_match(text: str) -> str:
    """Normalize literal/assertion text for tolerant matching."""
    t = _collapse_ws((text or "").lower())
    t = re.sub(r"^(id|content|body)\s*:\s*", "", t, flags=re.IGNORECASE)
    t = re.sub(r"^the\s+output\s+should\s+contain\s+", "", t, flags=re.IGNORECASE)
    return t.strip('"`\' ')


def _scenario_vocabulary(scenario: Dict[str, Any]) -> set[str]:
    """Collect normalized vocabulary from scenario title and steps."""
    parts: List[str] = []
    parts.append(scenario.get("scenario") or "")
    for key in ["background", "steps"]:
        for s in scenario.get(key, []) or []:
            parts.append(s.get("text") or "")
    text = _normalize_for_dedupe(" ".join(parts))
    return set(text.split())


def _lit_matches_text(lit: str, text: str) -> bool:
    """Return True when a literal (or key part) appears in text."""
    if not lit:
        return False
    if lit in text:
        return True

    m = re.search(r"\b(id|content|body)\s*:\s*(.+)$", lit, flags=re.IGNORECASE)
    if m:
        value = m.group(2).strip()
        if value and value in text:
            return True

    for q in _extract_quoted_literals(lit):
        if q and q in text:
            return True

    return False


def _scenario_literals(scenario: Dict[str, Any]) -> Dict[str, List[str]]:
    """Extract categorized literals/assertions from scenario steps."""
    steps = scenario.get("steps") or []

    ids: List[str] = []
    contents: List[str] = []
    output_assertions: List[str] = []
    output_negative_assertions: List[str] = []
    field_assertions: List[str] = []
    field_negative_assertions: List[str] = []
    relation_assertions: List[str] = []
    relation_negative_assertions: List[str] = []
    other: List[str] = []

    for step in steps:
        if not isinstance(step, dict):
            continue
        step_text = str(step.get("text") or "")
        if not step_text.strip():
            continue

        m = re.search(r"\"([A-Za-z]{2,6}-\d{2,6})\"", step_text)
        if m:
            ids.append(m.group(1))

        low = step_text.lower()
        if "content" in low or "body" in low:
            for lit in _extract_quoted_literals(step_text):
                if lit:
                    contents.append(lit)

        if re.search(r"\bfield\b", step_text, flags=re.IGNORECASE):
            for lit in _extract_quoted_literals(step_text):
                if re.search(r"\bshould\s+not\s+contain\b", step_text, flags=re.IGNORECASE) or re.search(
                    r"\bnot\s+contain\b", step_text, flags=re.IGNORECASE
                ):
                    field_negative_assertions.append(lit)
                elif re.search(r"\bcontain\b", step_text, flags=re.IGNORECASE):
                    field_assertions.append(lit)

        if re.search(r"\brelationship\b|\brelation\b", step_text, flags=re.IGNORECASE):
            for lit in _extract_quoted_literals(step_text):
                if re.search(r"\bshould\s+not\s+contain\b", step_text, flags=re.IGNORECASE) or re.search(
                    r"\bnot\s+contain\b", step_text, flags=re.IGNORECASE
                ):
                    relation_negative_assertions.append(lit)
                elif re.search(r"\bcontain\b", step_text, flags=re.IGNORECASE):
                    relation_assertions.append(lit)

        quoted = _extract_quoted_literals(step_text)
        for lit in quoted:
            if re.fullmatch(r"[A-Za-z]{2,6}-\d{2,6}", lit):
                ids.append(lit)
                continue

            if re.search(r"\boutput\b", step_text, flags=re.IGNORECASE):
                if re.search(r"\bshould\s+not\s+contain\b", step_text, flags=re.IGNORECASE) or re.search(
                    r"\bnot\s+contain\b", step_text, flags=re.IGNORECASE
                ):
                    output_negative_assertions.append(lit)
                    continue
                if re.search(r"\bcontain\b", step_text, flags=re.IGNORECASE):
                    output_assertions.append(lit)
                    continue

            other.append(lit)

    def uniq(seq: Iterable[str]) -> List[str]:
        """Keep first occurrence order while removing duplicates."""
        seen: set[str] = set()
        out: List[str] = []
        for x in seq:
            if x not in seen:
                out.append(x)
                seen.add(x)
        return out

    uniq_ids = uniq(ids)
    uniq_contents = uniq(contents)
    uniq_output_assertions = uniq(output_assertions)
    uniq_output_negative_assertions = uniq(output_negative_assertions)
    uniq_field_assertions = uniq(field_assertions)
    uniq_field_negative_assertions = uniq(field_negative_assertions)
    uniq_relation_assertions = uniq(relation_assertions)
    uniq_relation_negative_assertions = uniq(relation_negative_assertions)
    uniq_other = uniq(other)

    id_related_assertions = [
        oa for oa in uniq_output_assertions if any(id_ in oa for id_ in uniq_ids)
    ]
    non_id_assertions = [
        oa for oa in uniq_output_assertions if not any(id_ in oa for id_ in uniq_ids)
    ]
    id_keys = id_related_assertions if id_related_assertions else uniq_ids

    key = uniq(id_keys + uniq_contents + non_id_assertions)

    return {
        "ids": uniq_ids,
        "contents": uniq_contents,
        "output_assertions": uniq_output_assertions,
        "output_negative_assertions": uniq_output_negative_assertions,
        "field_assertions": uniq_field_assertions,
        "field_negative_assertions": uniq_field_negative_assertions,
        "relation_assertions": uniq_relation_assertions,
        "relation_negative_assertions": uniq_relation_negative_assertions,
        "other": uniq_other,
        "key": key,
        "all": uniq(
            uniq_ids
            + uniq_output_assertions
            + uniq_output_negative_assertions
            + uniq_field_assertions
            + uniq_field_negative_assertions
            + uniq_relation_assertions
            + uniq_relation_negative_assertions
            + uniq_other
        ),
    }

