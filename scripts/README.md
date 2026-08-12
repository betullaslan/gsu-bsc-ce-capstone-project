# `scripts/` - CLI Entrypoints

Runnable command-line scripts for generation and analysis.

## Prerequisites

- Run commands from the repo root (so paths like `data/` and `outputs/` resolve correctly)
- Python 3.x available on PATH
- Ollama service running locally (required by generation/classification scripts)

## Core Scripts

**`build_scenarios_dataset.py`** - Builds/refreshes `data/scenarios_dataset.json`

**`generate_test_cases.py`** - Generates test cases into `outputs/llm_test_generation/`

**`classify_scenarios.py`** - Classifies scenarios into `outputs/llm_classification/`

**`analyze_test_generation.py`** - Analyzes test generation outputs, writes to `analysis/llm_test_generation/`

**`analyze_test_generation_by_class.py`** - Breaks down metrics by manual labels

**`analyze_classification.py`** - Compares predictions vs manual labels

## Environment Variables

- `OLLAMA_MODEL` - Model name (default: `llama3.2:3b`)
- `OLLAMA_MAX_ATTEMPTS` - Max retries for generation (default: `5`)
- `OLLAMA_TIMEOUT` - Request timeout in seconds (if supported by Ollama client)

PowerShell example:

```powershell
$env:OLLAMA_MODEL="llama3.2:3b"
python scripts/generate_test_cases.py
```

## Typical Workflow

```powershell
python scripts/build_scenarios_dataset.py
python scripts/generate_test_cases.py
python scripts/classify_scenarios.py
python scripts/analyze_test_generation.py 
python scripts/analyze_test_generation_by_class.py
python scripts/analyze_classification.py 
```

## Advanced Usage

Generate only first 10 scenarios:

```powershell
python scripts/generate_test_cases.py --start 1 --end 10
```

Use specific strategy:

```powershell
python scripts/classify_scenarios.py --strategy instruction_based
```

## Output Locations

- Dataset: `data/scenarios_dataset.json`
- Generated tests: `outputs/llm_test_generation/`
- Classification results: `outputs/llm_classification/`
- Analysis artifacts (test generation): `analysis/llm_test_generation/`
- Analysis artifacts (classification): `analysis/llm_classification/`

## Notes

All scripts add `src/` to Python path automatically. Requires active Ollama service.
