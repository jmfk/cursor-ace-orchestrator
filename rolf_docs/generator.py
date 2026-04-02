import os
import re
import ast
import yaml
from datetime import datetime

class RolfDocsGenerator:
    def __init__(self, rolf_loop_path="rolf_loop.py", rolf_yaml_path="rolf.yaml", output_dir="rolf_docs/docs"):
        self.rolf_loop_path = rolf_loop_path
        self.rolf_yaml_path = rolf_yaml_path
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def parse_rolf_loop(self):
        """Parse rolf_loop.py to extract functions and their docstrings."""
        with open(self.rolf_loop_path, "r") as f:
            tree = ast.parse(f.read())

        functions = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                docstring = ast.get_docstring(node) or "No description available."
                args = [arg.arg for arg in node.args.args]
                functions.append({
                    "name": node.name,
                    "docstring": docstring,
                    "args": args
                })
        return functions

    def parse_rolf_yaml(self):
        """Parse rolf.yaml to extract configuration parameters."""
        if os.path.exists(self.rolf_yaml_path):
            with open(self.rolf_yaml_path, "r") as f:
                return yaml.safe_load(f)
        return {}

    def generate_markdown(self):
        """Generate the Markdown documentation."""
        functions = self.parse_rolf_loop()
        config = self.parse_rolf_yaml()
        
        content = []
        content.append("# ROLF Loop Documentation")
        content.append(f"\n*Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")
        
        content.append("\n## Overview")
        content.append("`rolf_loop.py` is the bootstrapping orchestrator for the ACE project. It implements a simplified ROLF Cycle (Reasoning, Action, Learning, Progress, Halt) to iteratively build the core system.")

        content.append("\n## Usage")
        content.append("ROLF can be executed directly using Python or via the `rolf` command if installed.")
        content.append("\n### Basic Command")
        content.append("```bash\npython3 rolf_loop.py [PRD_PATH]\n```")
        content.append("\n### CLI Arguments")
        content.append("| Argument | Description |")
        content.append("| :--- | :--- |")
        content.append("| `prd` | Optional path to the PRD file (positional). |")
        content.append("| `--config` | Path to YAML config file (default: `rolf.yaml`). |")
        content.append("| `--model` | Override the LLM model. |")
        content.append("| `--max-spend` | Override the maximum budget in USD. |")
        content.append("| `--plan-file` | Override the plan file path. |")

        content.append("\n### Examples")
        content.append("Run with a specific PRD:")
        content.append("```bash\npython3 rolf_loop.py docs/my_prd.md\n```")
        content.append("Run with a custom budget:")
        content.append("```bash\npython3 rolf_loop.py --max-spend 5.0\n```")

        content.append("\n## Core Functions")
        for func in functions:
            content.append(f"\n### `{func['name']}({', '.join(func['args'])})`")
            content.append(f"{func['docstring']}")

        content.append("\n## Configuration (`rolf.yaml`)")
        content.append("\n| Parameter | Description |")
        content.append("| :--- | :--- |")
        
        # Mapping common parameters to descriptions
        descriptions = {
            "model": "The default LLM model used for execution.",
            "max_spend_usd": "Maximum budget for the loop in USD.",
            "max_iterations": "Maximum number of iterations before halting.",
            "plan_file": "Path to the plan file (e.g., `plan.md`).",
            "changelog_file": "Path to the changelog file.",
            "log_file": "Path to the execution log file.",
            "stats_file": "Path to the statistics JSON file.",
            "state_history_file": "Path to the state history JSON file.",
            "default_prd": "The default PRD file to use for planning.",
            "stagnation_threshold": "Number of identical iterations before detecting stagnation.",
            "max_consecutive_failures": "Number of failures before tripping the circuit breaker.",
            "quit_on_rate_limit": "Whether to halt execution on 429 errors.",
            "price_input_1m": "Price per 1M input tokens in USD.",
            "price_output_1m": "Price per 1M output tokens in USD.",
            "planner_model": "Model used for high-level planning.",
            "validator_model": "Model used for task validation.",
            "context_model": "Model used for context gathering.",
            "executor_model": "Model used for task execution."
        }

        for key, value in config.items():
            desc = descriptions.get(key, "No description available.")
            content.append(f"| `{key}` | {desc} (Default: `{value}`) |")

        output_path = os.path.join(self.output_dir, "README.md")
        with open(output_path, "w") as f:
            f.write("\n".join(content))
        
        print(f"Documentation generated at {output_path}")

if __name__ == "__main__":
    generator = RolfDocsGenerator()
    generator.generate_markdown()
