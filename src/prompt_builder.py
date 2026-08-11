"""Prompt construction helpers for test-case generation."""

from pathlib import Path
from functools import lru_cache
from typing import Any, Dict, List

from scenario_steps import split_steps

BASE_DIR = Path(__file__).resolve().parent.parent
PROMPTS_DIR = BASE_DIR / "prompts" / "llm_test_generation"


@lru_cache(maxsize=32)
def load_prompt_template(strategy: str) -> str:
    """Load a test-generation prompt template for the given strategy name."""
    prompt_filename = f"{str(strategy).strip()}.txt"
    prompt_path = PROMPTS_DIR / prompt_filename

    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt template not found: {prompt_path}")

    return prompt_path.read_text(encoding="utf-8")


def format_steps(steps: List[Dict[str, Any]] | None) -> str:
    """Format scenario steps as Markdown bullet lines for prompt injection."""
    if not steps:
        return "-"

    return "\n".join(f"- {step['text']}" for step in steps)


def build_prompt(scenario: Dict[str, Any], strategy: str) -> str:
    """Build the full prompt text for one scenario and one prompting strategy."""
    template = load_prompt_template(strategy)
    # Steps are grouped so prompts can insert Background/Given/When/Then separately.
    buckets = split_steps(scenario.get("steps") or [])

    return template.format(
        scenario_name=scenario.get("scenario", ""),
        background=format_steps(scenario.get("background", [])),
        given_steps=format_steps(buckets.get("given") or []),
        when_steps=format_steps(buckets.get("when") or []),
        then_steps=format_steps(buckets.get("then") or []),
    )
