import os
import re
import ast
import yaml
from datetime import datetime

class RalphDocsGenerator:
    def __init__(self, ralph_loop_path="ralph_loop.py", ralph_yaml_path="ralph.yaml", output_dir="ralph_docs/docs"):
        self.ralph_loop_path = ralph_loop_path
        self.ralph_yaml_path = ralph_yaml_path
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def parse_ralph_loop(self):
        """Parse ralph_loop.py to extract functions and their docstrings."""
        with open(self.ralph_loop_path, "r") as f:
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

    def parse_ralph_yaml(self):
        """Parse ralph.yaml to extract configuration parameters."""
        if os.path.exists(self.ralph_yaml_path):
            with open(self.ralph_yaml_path, "r") as f:
                return yaml.safe_load(f)
        return {}

    def generate_markdown(self):
        """Generate the Markdown documentation."""
        functions = self.parse_ralph_loop()
        config = self.parse_ralph_yaml()
        
        content = []
        content.append("# RALPH Loop Documentation")
        content.append(f"\n*Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")
        
        content.append("\n## Overview")
        content.append("`ralph_loop.py` is the bootstrapping orchestrator for the ACE project. It implements a simplified RALPH Cycle (Reasoning, Action, Learning, Progress, Halt) to iteratively build the core system.")

        content.append("\n## Usage")
        content.append("RALPH can be executed directly using Python or via the `ralph` command if installed.")
        content.append("\n### Basic Command")
        content.append("```bash\npython3 ralph_loop.py [PRD_PATH]\n```")
        content.append("\n### CLI Arguments")
        content.append("| Argument | Description |")
        content.append("| :--- | :--- |")
        content.append("| `prd` | Optional path to the PRD file (positional). |")
        content.append("| `--config` | Path to YAML config file (default: `ralph.yaml`). |")
        content.append("| `--model` | Override the LLM model. |")
        content.append("| `--max-spend` | Override the maximum budget in USD. |")
        content.append("| `--plan-file` | Override the plan file path. |")

        content.append("\n### Examples")
        content.append("Run with a specific PRD:")
        content.append("```bash\npython3 ralph_loop.py docs/my_prd.md\n```")
        content.append("Run with a custom budget:")
        content.append("```bash\npython3 ralph_loop.py --max-spend 5.0\n```")

        content.append("\n## Core Functions")
        for func in functions:
            content.append(f"\n### `{func['name']}({', '.join(func['args'])})`")
            content.append(f"{func['docstring']}")

        content.append("\n## Configuration (`ralph.yaml`)")
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
    generator = RalphDocsGenerator()
    generator.generate_markdown()
