# ROLF Loop Documentation

*Generated on 2026-04-02 15:45:36*

## Overview
`rolf_loop.py` is the bootstrapping orchestrator for the ACE project. It implements a simplified ROLF Cycle (Reasoning, Action, Learning, Progress, Halt) to iteratively build the core system.

## Usage
ROLF can be executed directly using Python or via the `rolf` command if installed.

### Basic Command
```bash
python3 rolf_loop.py [PRD_PATH]
```

### CLI Arguments
| Argument | Description |
| :--- | :--- |
| `prd` | Optional path to the PRD file (positional). |
| `--config` | Path to YAML config file (default: `rolf.yaml`). |
| `--model` | Override the LLM model. |
| `--max-spend` | Override the maximum budget in USD. |
| `--plan-file` | Override the plan file path. |

### Examples
Run with a specific PRD:
```bash
python3 rolf_loop.py docs/my_prd.md
```
Run with a custom budget:
```bash
python3 rolf_loop.py --max-spend 5.0
```

## Core Functions

### `load_config(config_path)`
Load configuration from YAML file and override defaults.

### `log_message(message)`
Log a message with timestamp to console and file.

### `update_stats(input_tokens, output_tokens, elapsed_time)`
Update execution statistics and cost.

### `parse_usage_from_output(stdout)`
Parse token usage from cursor-agent stream-json output.

### `run_cursor_agent(prompt, model_override, timeout)`
Runs cursor-agent in non-interactive mode and tracks usage.

### `generate_commit_message(task_name)`
Generate a descriptive commit message using direct Gemini API or cursor-agent.

### `get_file_content(path)`
Read and return file content if it exists.

### `get_current_task()`
Extract the first uncompleted task from plan.md.

### `get_project_state_hash()`
Generate a hash of the current project state (git diff).

### `check_stagnation(current_hash, current_task)`
Check if the project state or task has stagnated.

### `get_total_cost()`
Get total cost from stats file.

### `main()`
Main execution loop for ROLF.

## Configuration (`rolf.yaml`)

| Parameter | Description |
| :--- | :--- |
| `model` | The default LLM model used for execution. (Default: `gemini-3-flash`) |
| `max_spend_usd` | Maximum budget for the loop in USD. (Default: `20.0`) |
| `plan_file` | Path to the plan file (e.g., `plan.md`). (Default: `plan.md`) |
| `changelog_file` | Path to the changelog file. (Default: `changelog.md`) |
| `log_file` | Path to the execution log file. (Default: `rolf_execution.log`) |
| `stats_file` | Path to the statistics JSON file. (Default: `rolf_stats.json`) |
| `state_history_file` | Path to the state history JSON file. (Default: `rolf_state_history.json`) |
| `default_prd` | The default PRD file to use for planning. (Default: `PRD-01.md`) |
| `stagnation_threshold` | Number of identical iterations before detecting stagnation. (Default: `3`) |
| `max_consecutive_failures` | Number of failures before tripping the circuit breaker. (Default: `3`) |
| `max_iterations` | Maximum number of iterations before halting. (Default: `50`) |
| `quit_on_rate_limit` | Whether to halt execution on 429 errors. (Default: `True`) |
| `price_input_1m` | Price per 1M input tokens in USD. (Default: `0.1`) |
| `price_output_1m` | Price per 1M output tokens in USD. (Default: `0.4`) |
| `planner_model` | Model used for high-level planning. (Default: `gemini-3-flash`) |
| `validator_model` | Model used for task validation. (Default: `gemini-3-flash-preview`) |
| `context_model` | Model used for context gathering. (Default: `gemini-3-flash-preview`) |
| `executor_model` | Model used for task execution. (Default: `gemini-3-flash`) |