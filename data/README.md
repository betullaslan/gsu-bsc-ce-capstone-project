# `data/`

Source-of-truth inputs for the project.

## Files

- `scenarios.feature` - Source-of-truth scenario file. Gherkin (BDD) definitions that describe each scenario in a readable spec format.
- `scenarios_dataset.json` - Generated dataset (JSON). Produced by running `build_scenarios_dataset.py`, which parses `scenarios.feature` and enriches scenarios with metadata (each scenario is identified by a stable `scenario_id`). This is the primary machine-readable input for automated analysis/output generation.
- `scenario_manual_labels.csv` - Human-provided classifications/labels. Joins to `scenarios_dataset.json` via `scenario_id`.
  - Expected columns: `scenario_id`, `test_level`, `test_type`
  - Purpose: Provides a ground-truth/reference label set for validating or evaluating automated outputs.
  - Observed values:
    - `test_level`: `Unit`, `Integration`, `System`, `Acceptance`
    - `test_type`: `Functional`, `Error Handling`, `End-to-End`, `Regression`, `Performance`, `Security`

## Important

Keep `scenario_id` values stable. If you add/remove scenarios, regenerate `outputs/` and rerun analyses.
