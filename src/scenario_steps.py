"""Helpers for grouping scenario steps by effective keyword/type."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, TypedDict


primary_keyword = Literal["Given", "When", "Then"]


class Step(TypedDict, total=False):
    """A single step from the scenario dataset (Background/Given/When/Then)."""
    keyword: str
    keyword_inferred: str
    type: str
    text: str
    line: int


class SplitSteps(TypedDict):
    """Scenario steps grouped by effective keyword (given/when/then/other)."""
    given: List[Step]
    when: List[Step]
    then: List[Step]
    other: List[Step]


def _effective_keyword(step: Dict[str, Any]) -> str:
    """Resolve effective keyword, honoring inferred keyword for And/But steps."""
    kw = str(step.get("keyword") or "").strip()
    if kw in ("And", "But"):
        # Preserve the inferred primary keyword for chained steps.
        kw = str(step.get("keyword_inferred") or "").strip()
    return kw


def split_steps(steps: List[Dict[str, Any]] | None) -> SplitSteps:
    """Split a list of step dicts into groups by keyword or inferred type."""
    out: SplitSteps = {"given": [], "when": [], "then": [], "other": []}
    for step in steps or []:
        if not isinstance(step, dict):
            continue
        # Prefer explicit `type` if present; otherwise infer from keyword/inferred keyword.
        step_type = str(step.get("type") or "").strip().lower()
        if step_type in ("given", "when", "then"):
            kw = step_type
        else:
            kw = _effective_keyword(step)
            kw = {"Given": "given", "When": "when", "Then": "then"}.get(kw, "")

        if kw == "given":
            out["given"].append(step)
        elif kw == "when":
            out["when"].append(step)
        elif kw == "then":
            out["then"].append(step)
        else:
            out["other"].append(step)
    return out
