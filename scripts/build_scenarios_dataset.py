"""Convert a Gherkin-like `.feature` file into a minimal JSON dataset.

This is intentionally small and stable so downstream generation/analysis scripts can
operate without depending on a full Gherkin parser.
"""

from pathlib import Path
import json
import argparse
from typing import Any, Dict, List, Optional

BASE_DIR = Path(__file__).resolve().parent.parent
FEATURE_PATH = BASE_DIR / "data" / "scenarios.feature"
JSON_OUTPUT = BASE_DIR / "data" / "scenarios_dataset.json"


def parse_feature_file(text: str) -> Dict[str, Any]:
    """Parse `scenarios.feature` content into a JSON dataset structure."""
    scenarios: List[Dict[str, Any]] = []
    features: List[str] = []

    # Track feature/scenario context while scanning line-by-line.
    current_feature: Optional[str] = None
    background_steps: List[Dict[str, Any]] = []
    background_last_primary: Optional[str] = None

    current_scenario: Optional[Dict[str, Any]] = None
    current_section: Optional[str] = None
    scenario_last_primary: Optional[str] = None

    step_keywords = {"Given", "When", "Then", "And", "But"}

    def keyword_to_type(keyword: str) -> Optional[str]:
        """Map Gherkin primary keyword to normalized step type."""
        # Normalize primary keywords to a stable lowercased type.
        if keyword == "Given":
            return "given"
        if keyword == "When":
            return "when"
        if keyword == "Then":
            return "then"
        return None

    def ensure_feature_list(feature_name: str) -> None:
        """Append feature name once while preserving source order."""
        if not features or features[-1] != feature_name:
            features.append(feature_name)

    def save_current_scenario() -> None:
        """Persist current scenario with copied background steps."""
        nonlocal current_scenario, scenario_last_primary
        if current_scenario is None:
            return
        current_scenario["background"] = background_steps.copy()
        scenarios.append(current_scenario)
        current_scenario = None
        scenario_last_primary = None

    def start_scenario(scenario_name: str) -> None:
        """Initialize a new scenario record and parser state."""
        nonlocal current_scenario, current_section, scenario_last_primary
        current_scenario = {
            "id": f"SCN-{len(scenarios) + 1:03d}",
            "feature": current_feature,
            "scenario": scenario_name,
            "steps": [],
        }
        current_section = "scenario"
        scenario_last_primary = None

    for raw_line in text.splitlines(keepends=True):
        stripped = raw_line.strip()

        if not stripped:
            continue

        if stripped.startswith("@"):
            continue

        if stripped.startswith("Feature:"):
            save_current_scenario()
            current_feature = stripped.replace("Feature:", "", 1).strip()
            ensure_feature_list(current_feature)
            background_steps = []
            background_last_primary = None
            current_section = None
            continue

        if stripped.startswith("Background:"):
            current_section = "background"
            background_steps = []
            background_last_primary = None
            continue

        if stripped.startswith("Scenario:"):
            save_current_scenario()
            scenario_name = stripped.split(":", 1)[1].strip()
            start_scenario(scenario_name)
            continue

        keyword = stripped.split(" ", 1)[0]
        if keyword in step_keywords:
            step_text = stripped[len(keyword) :].strip()
            if not step_text:
                continue
            step_obj: Dict[str, Any] = {"keyword": keyword, "text": step_text}

            if current_section == "background":
                background_steps.append(step_obj)
                if keyword in ("Given", "When", "Then"):
                    background_last_primary = keyword
                elif keyword in ("And", "But") and background_last_primary is not None:
                    step_obj["keyword_inferred"] = background_last_primary

                inferred_kw = step_obj.get("keyword_inferred") if keyword in ("And", "But") else None
                step_obj["type"] = (
                    keyword_to_type(str(inferred_kw)) if inferred_kw else keyword_to_type(keyword)
                ) or "other"
                continue

            if current_scenario is None:
                continue

            current_scenario["steps"].append(step_obj)

            if keyword in ("Given", "When", "Then"):
                scenario_last_primary = keyword
            elif keyword in ("And", "But") and scenario_last_primary is not None:
                step_obj["keyword_inferred"] = scenario_last_primary

            inferred_kw = step_obj.get("keyword_inferred") if keyword in ("And", "But") else None
            step_obj["type"] = (
                keyword_to_type(str(inferred_kw)) if inferred_kw else keyword_to_type(keyword)
            ) or "other"
            continue

    save_current_scenario()

    return {
        "features": features,
        "feature_count": len(features),
        "scenario_count": len(scenarios),
        "scenarios": scenarios,
    }


def main() -> None:
    """CLI entrypoint: convert `.feature` scenarios into `data/scenarios_dataset.json`."""
    parser = argparse.ArgumentParser(
        description="Parse Gherkin .feature content into a minimal JSON dataset."
    )
    parser.add_argument("--input", type=Path, default=FEATURE_PATH, help="Path to .feature file")
    parser.add_argument("--json", dest="json_out", type=Path, default=JSON_OUTPUT, help="Output JSON path")
    args = parser.parse_args()

    text = args.input.read_text(encoding="utf-8-sig")
    parsed = parse_feature_file(text)

    args.json_out.write_text(
        json.dumps(parsed, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"Parsed feature count: {parsed['feature_count']}")
    print(f"Parsed scenario count: {parsed['scenario_count']}")
    print(f"JSON written to: {args.json_out}")


if __name__ == "__main__":
    main()
