# `outputs/`

Raw outputs produced by scripts (JSON). Analysis scripts read these files.

## Layout

- `llm_test_generation/` - Per-scenario LLM test generation results, written by `scripts/generate_test_cases.py`.
  - File naming: `SCN-XXX.json` (one JSON file per `scenario_id`)
  - Used by: `scripts/analyze_test_generation.py` (and downstream analysis scripts)
- `llm_classification/` - LLM classification results, written by `scripts/classify_scenarios.py`.
  - File naming: `llm_<strategy>.json` (one JSON per prompting/strategy, e.g. `llm_zero_shot.json`)
  - Used by: `scripts/analyze_classification.py`

## Important

Do not manually edit outputs. Update prompts/scripts and regenerate instead.
