# `src/` - Shared Library

Core library code for test generation, quality assessment, and analysis.

## What Each File Does

- `generation_flow.py`: High-level orchestration for the generation pipeline (prompt → LLM call → parse/post-process → validate).
- `llm_runner.py`: Ollama-facing runner utilities (sending prompts and returning responses).
- `prompt_builder.py`: Prompt templating and scenario-to-prompt rendering helpers.
- `testcase_format.py`: Parsing/sanitization utilities for turning raw model output into a structured test case.
- `scenario_steps.py`: Scenario step normalization helpers shared by prompting and validation.
- `quality_rules.py`: Rule-based validation for generated test cases; emits warnings and overall status.
- `quality_rules_text.py`: Text-focused heuristics used by the validation rules.
- `quality_rules_preconditions.py`: Preconditions-specific validation rules and helpers.
- `quality_metrics.py`: Aggregates warnings into numeric metrics used by analysis/reporting.

### Packages

- `generation/`: LLM execution + post-processing pipeline pieces.
  - `generation/core.py`: Core generation implementation used by the orchestration layer.
  - `generation/postprocess.py`: Output cleanup (normalization, dedupe, formatting hygiene).
- `analyze/`: Shared analysis helpers for CSV/Markdown/PNG artifacts.
