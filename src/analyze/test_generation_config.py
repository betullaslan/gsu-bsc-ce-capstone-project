"""Centralized paths and table schemas for test-generation analysis outputs."""

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
OUTPUTS_DIR = BASE_DIR / "outputs"
ANALYSIS_DIR = BASE_DIR / "analysis" / "llm_test_generation"
SCENARIOS_DATASET = BASE_DIR / "data" / "scenarios_dataset.json"

# Output locations (generated artifacts).
TABLES_DIR = ANALYSIS_DIR / "tables"
DETAILED_CSV_PATH = TABLES_DIR / "results_detailed.csv"
SUMMARY_CSV_PATH = TABLES_DIR / "results_by_strategy.csv"
SUMMARY_MD_PATH = ANALYSIS_DIR / "analysis.md"
WARNING_SUMMARY_CSV_PATH = TABLES_DIR / "warnings_by_type.csv"
SCENARIO_SUMMARY_CSV_PATH = TABLES_DIR / "results_by_scenario.csv"
FIGURES_DIR = ANALYSIS_DIR / "figures"

DETAILED_COLUMNS = [
    "scenario_id",
    "scenario_name",
    "strategy",
    "model",
    "response_time_seconds",
    "generation_attempts",
    "is_valid",
    "quality_status",
    "warning_types",
    "warning_count",
    "completeness",
    "traceability",
    "specificity",
    "hallucination",
    "semantic_coverage",
    "stability",
    "speed",
    "final_score",
]

SUMMARY_COLUMNS = [
    "strategy",
    "avg_response_time_seconds",
    "median_response_time_seconds",
    "p95_response_time_seconds",
    "std_response_time_seconds",
    "avg_warning_count",
    "valid_rate",
    "clean_rate",
    "clean_with_warnings_rate",
    "needs_review_rate",
    "invalid_rate",
    "avg_generation_attempts",
    "avg_completeness",
    "avg_traceability",
    "avg_specificity",
    "avg_hallucination",
    "avg_semantic_coverage",
    "avg_stability",
    "avg_speed",
    "avg_final_score",
    "avg_final_score_ci_low",
    "avg_final_score_ci_high",
    "median_final_score",
    "std_final_score",
]
