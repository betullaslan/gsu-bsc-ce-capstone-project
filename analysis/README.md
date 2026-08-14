# `analysis/` - Generated Reports & Artifacts

This folder contains *generated* analysis outputs produced by the runnable scripts under `scripts/`.

It is intended for **human-readable reports** (`.md`) as well as **machine-friendly tables** (`.csv`) and **figures** (`.png`)
that summarize the current snapshot of model outputs under `outputs/`.

## Structure

- `analysis/llm_test_generation/`
  - `analysis.md`: Main report for test-generation quality and ranking.
  - `tables/`: CSV tables used by the report (detailed results, summaries, warning breakdowns, etc.).
  - `figures/`: PNG plots derived from the tables.
  - `by_manual_labels/`: Breakdowns grouped by manual labels (`test_level`, `test_type`) when generated.

- `analysis/llm_classification/`
  - `analysis.md`: Main report comparing manual labels vs LLM classification.
  - `tables/`: CSV tables (per-strategy summary, unknown rates, accuracy tables, etc.).
  - `figures/`: PNG plots (accuracy bars, comparisons).
  - `by_strategy/`: Per-strategy sub-reports (when `--llm-json` points to a directory of `llm_*.json` files).

## How These Files Are Produced

The analysis reports are regenerated from the latest `outputs/` snapshot:

- Test generation analysis:
  - Input: `outputs/llm_test_generation/`
  - Script: `scripts/analyze_test_generation.py`
  - Output: `analysis/llm_test_generation/`
  - Manual-label breakdown script: `scripts/analyze_test_generation_by_class.py`
  - Output: `analysis/llm_test_generation/by_manual_labels/`

- Classification analysis:
  - Inputs:
    - Manual labels: `data/scenario_manual_labels.csv`
    - LLM outputs: `outputs/llm_classification/`
  - Script: `scripts/analyze_classification.py`
  - Output: `analysis/llm_classification/`

## Regenerating

Run from the repo root:

```powershell
# Test generation
python scripts/analyze_test_generation.py

# Test generation (manual label breakdown)
python scripts/analyze_test_generation_by_class.py

# Classification
python scripts/analyze_classification.py
```

Notes:

- Command-line flags exist to change inputs/outputs; see each script's `--help`.
- These artifacts are derived data; if you change `outputs/` or the scoring/analysis code, regenerate the reports.
- It is safe to delete files under `analysis/` and rerun the scripts to reproduce them.
