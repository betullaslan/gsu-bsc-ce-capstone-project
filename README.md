# Automated Testing Process Analysis Using Generative Artificial Intelligence

**BSc Capstone Project — Computer Engineering, Galatasaray University (2026)**

## Overview

This project explores the use of generative AI in software testing. It uses a large language model (LLM) through [Ollama](https://ollama.com/) to generate structured test cases from Gherkin scenarios and classify scenarios by `test_level` and `test_type`.

The project compares different prompting strategies and evaluates the generated results using rule-based validation and quality metrics. The analysis produces reports, tables, and figures.

## Dataset

The dataset contains **120 test scenarios**:

- **The first 100 scenarios** were taken from the open-source [wedow/ticket](https://github.com/wedow/ticket) project, licensed under the MIT License.
- **The last 20 scenarios** were written manually to cover test categories missing from the original dataset.

The Gherkin scenarios are stored in `data/scenarios.feature`. The `data/` directory also contains a structured dataset and manual labels used in the analysis.

## Project Structure

```text
.
├── analysis/      # Analysis reports, tables, and figures
├── data/          # Scenarios and manual labels
├── outputs/       # Generated model responses
├── prompts/       # Prompt templates
├── scripts/       # Scripts for running the pipeline
├── src/           # Shared Python code
├── third_party/   # MIT license notice for wedow/ticket
└── README.md
```

Each main directory has its own README with additional details.

## Requirements & Installation

**Requirements:** Python 3.x, [Ollama](https://ollama.com/), and the Python packages `requests`, `numpy`, and `matplotlib`.

The commands below are for **Windows PowerShell**. Run them from the repository's root directory.

1. Create and activate a virtual environment:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

2. Install the Python dependencies:

   ```powershell
   python -m pip install requests numpy matplotlib
   ```

3. Download the default Ollama model:

   ```powershell
   ollama pull llama3.2:3b
   ```

Ensure Ollama is running before executing the scripts. If needed, start it in a separate terminal using `ollama serve`.

The default model is `llama3.2:3b`. To use another model, set `OLLAMA_MODEL` in your terminal. The optional `OLLAMA_MAX_ATTEMPTS` variable controls the maximum number of request attempts (default: `5`).

## Running the Project

Run the following commands from the repository's root directory, in order.

**1. Build the scenario dataset**

```powershell
python scripts/build_scenarios_dataset.py
```

**2. Generate test cases**

```powershell
python scripts/generate_test_cases.py
```

**3. Classify scenarios**

```powershell
python scripts/classify_scenarios.py
```

**4. Analyze test case generation**

```powershell
python scripts/analyze_test_generation.py
python scripts/analyze_test_generation_by_class.py
```

**5. Analyze scenario classification**

```powershell
python scripts/analyze_classification.py
```

## Results

The pipeline saves generated model responses in `outputs/` and produces analysis reports, CSV tables, and PNG figures in `analysis/`.

The main reports are:

- [Test generation analysis](analysis/llm_test_generation/analysis.md)
- [Test generation analysis by manual labels](analysis/llm_test_generation/by_manual_labels/analysis.md)
- [Scenario classification analysis](analysis/llm_classification/analysis.md)

The files in `outputs/` and `analysis/` are generated from the scenarios, prompts, and analysis scripts. Rerun the relevant steps after changing those inputs or the evaluation logic.

## Reference

- wedow. *ticket — Open-source GitHub repository.* [GitHub](https://github.com/wedow/ticket). Accessed May 18, 2026.

The original wedow/ticket project is licensed under the MIT License. See [LICENSE-wedow-ticket.txt](third_party/LICENSE-wedow-ticket.txt).

