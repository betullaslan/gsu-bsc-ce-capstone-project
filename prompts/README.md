# `prompts/` - LLM Prompt Templates

Text-based prompt templates for LLM-based tasks. Organized by workflow type.

## Structure

- `llm_test_generation/` - Prompting strategies for generating structured test cases from Gherkin scenarios.
  - `zero_shot_prompting.txt` - Direct generation without examples or reasoning output
  - `few_shot_prompting.txt` - Generation with an example test case
  - `instruction_based_prompting.txt` - Generation with explicit quality-focused instructions
  - `step_by_step_prompting.txt` - Generation with internal step-by-step extraction
  - `constraint_prompting.txt` - Constrained generation with strict mapping and formatting rules

- `llm_classification/` - Prompting strategies for labeling scenarios with `test_level` and `test_type` from Gherkin content.
  - `zero_shot_prompting.txt` - Direct classification without examples
  - `few_shot_prompting.txt` - Classification with labeled examples
  - `instruction_based_prompting.txt` - Classification with explicit decision rules
  - `step_by_step_prompting.txt` - Classification with internal step-by-step reasoning
  - `constraint_prompting.txt` - Classification with strict JSON/output constraints

## Usage

- Test generation: Loaded by `scripts/generate_test_cases.py` and written to `outputs/llm_test_generation/`.
- Classification: Loaded by `scripts/classify_scenarios.py` and written to `outputs/llm_classification/`.

The scripts substitute scenario content into prompt variables/placeholders (e.g., scenario name, background, steps) and send the final prompt to the configured LLM backend.

## Important

If you modify any prompt template, regenerate `outputs/` and rerun analysis scripts.
