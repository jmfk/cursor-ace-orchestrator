import os
import subprocess
import sys
import time
import json
import hashlib
import re
import requests
import argparse
from datetime import datetime

# Try to import yaml, but provide a fallback or install it if missing
try:
    import yaml
except ImportError:
    print("PyYAML not found. Installing...")
    subprocess.run([sys.executable, "-m", "pip", "install", "pyyaml"], check=True)
    import yaml

# Default Configuration
DEFAULTS = {
    "model": "gemini-3-flash",
    "max_spend_usd": 20.0,
    "plan_file": "plan.md",
    "changelog_file": "changelog.md",
    "log_file": "ralph_execution.log",
    "stats_file": "ralph_stats.json",
    "state_history_file": "ralph_state_history.json",
    "default_prd": "PRD-01 - Cursor-ace-orchestrator-prd.md",
    "stagnation_threshold": 2,
    "max_consecutive_failures": 3,
    "quit_on_rate_limit": True,
    "price_input_1m": 0.10,
    "price_output_1m": 0.40,
}

# Global Config Object
CONFIG = DEFAULTS.copy()

# Global State
LLM_CIRCUIT_BREAKER_TRIPPED = False
CONSECUTIVE_FAILURES = 0
PAID_ACCOUNT_REQUIRED = False

def load_config(config_path="ralph.yaml"):
    """Load configuration from YAML file and override defaults."""
    global CONFIG
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                yaml_config = yaml.safe_load(f)
                if yaml_config:
                    CONFIG.update(yaml_config)
                    log_message(f"Loaded config from {config_path}")
        except Exception as e:
            log_message(f"Error loading {config_path}: {e}")

def log_message(message: str):
    """Log a message with timestamp to console and file."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted_msg = f"[{timestamp}] {message}"
    print(formatted_msg)
    log_file = CONFIG.get("log_file", "ralph_execution.log")
    with open(log_file, "a") as f:
        f.write(formatted_msg + "\n")

def update_stats(input_tokens: int, output_tokens: int, elapsed_time: float):
    """Update execution statistics and cost."""
    stats_file = CONFIG.get("stats_file", "ralph_stats.json")
    stats = {
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "total_cost_usd": 0.0,
        "total_time_sec": 0.0,
        "iterations": 0,
    }
    if os.path.exists(stats_file):
        with open(stats_file, "r") as f:
            stats = json.load(f)

    price_in = CONFIG.get("price_input_1m", 0.10)
    price_out = CONFIG.get("price_output_1m", 0.40)
    
    cost = (input_tokens / 1_000_000 * price_in
            + output_tokens / 1_000_000 * price_out)

    stats["total_input_tokens"] += input_tokens
    stats["total_output_tokens"] += output_tokens
    stats["total_cost_usd"] += cost
    stats["total_time_sec"] += elapsed_time
    stats["iterations"] += 1

    with open(stats_file, "w") as f:
        json.dump(stats, f, indent=2)

    log_message(
        f"Stats Update: +{input_tokens}in, +{output_tokens}out | "
        f"Cost: ${cost:.6f} | Time: {elapsed_time:.2f}s"
    )
    log_message(f"Total Cost so far: ${stats['total_cost_usd']:.4f}")

def run_cursor_agent(prompt: str):
    """Runs cursor-agent in non-interactive mode and tracks usage."""
    global LLM_CIRCUIT_BREAKER_TRIPPED, CONSECUTIVE_FAILURES, PAID_ACCOUNT_REQUIRED

    if LLM_CIRCUIT_BREAKER_TRIPPED:
        log_message("🚫 Circuit breaker is TRIPPED. Skipping LLM call.")
        return None
    
    if PAID_ACCOUNT_REQUIRED:
        log_message("🚫 Paid account required. Skipping LLM call.")
        return None

    start_time = time.time()
    log_message(f"Running Cursor Agent: {prompt[:100]}...")

    cmd = [
        "cursor-agent",
        "--api-key",
        os.getenv("CURSOR_API_KEY", ""),
        "--print",
        "--model",
        CONFIG["model"],
        "--output-format",
        "stream-json",
        "--force",
        "--trust",
        prompt,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        elapsed = time.time() - start_time

        if result.returncode != 0:
            CONSECUTIVE_FAILURES += 1
            error_output = result.stdout + result.stderr
            log_message(
                f"❌ Cursor Agent failed with Exit Code {result.returncode} "
                f"(Consecutive failures: {CONSECUTIVE_FAILURES})")
            
            if "429" in error_output or "RESOURCE_EXHAUSTED" in error_output or "rate limit" in error_output.lower():
                PAID_ACCOUNT_REQUIRED = True
                log_message("🚨 Detected rate limit from Cursor Agent (429/RESOURCE_EXHAUSTED).")

            if CONSECUTIVE_FAILURES >= CONFIG["max_consecutive_failures"]:
                LLM_CIRCUIT_BREAKER_TRIPPED = True
                log_message("🚨 CIRCUIT BREAKER TRIPPED! Too many consecutive failures.")

            log_message(f"--- STDOUT ---\n{result.stdout}")
            log_message(f"--- STDERR ---\n{result.stderr}")
            return None

        CONSECUTIVE_FAILURES = 0
        input_tokens = len(prompt.split()) * 1.3
        output_tokens = len(result.stdout.split()) * 1.3
        update_stats(int(input_tokens), int(output_tokens), elapsed)
        log_message("✅ Cursor Agent completed successfully.")
        return result.stdout

    except Exception as e:
        CONSECUTIVE_FAILURES += 1
        log_message(
            f"🚨 Unexpected error during subprocess execution: {str(e)} "
            f"(Consecutive failures: {CONSECUTIVE_FAILURES})")
        
        if CONSECUTIVE_FAILURES >= CONFIG["max_consecutive_failures"]:
            LLM_CIRCUIT_BREAKER_TRIPPED = True
            log_message("🚨 CIRCUIT BREAKER TRIPPED! Too many consecutive failures.")
            
        return None

def generate_commit_message(task_name: str):
    """Generate a descriptive commit message using direct Gemini API or cursor-agent."""
    global LLM_CIRCUIT_BREAKER_TRIPPED, CONSECUTIVE_FAILURES, PAID_ACCOUNT_REQUIRED

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

    if not api_key:
        try:
            from dotenv import load_dotenv
            load_dotenv()
            api_key = (os.getenv("GEMINI_API_KEY") or
                       os.getenv("GOOGLE_API_KEY"))
        except ImportError:
            if os.path.exists(".env"):
                with open(".env", "r") as f:
                    for line in f:
                        if (line.startswith("GOOGLE_API_KEY=") or
                                line.startswith("GEMINI_API_KEY=")):
                            api_key = line.split("=", 1)[1].strip().strip('"').strip("'")
                            break

    try:
        diff = subprocess.run(["git", "diff", "--cached"], capture_output=True, text=True).stdout
        if not diff:
            diff = subprocess.run(["git", "diff"], capture_output=True, text=True).stdout
    except Exception:
        diff = "No diff available"

    prompt = (
        f"Generate a concise, one-line git commit message for the following task: {task_name}\n\n"
        f"Git Diff context:\n{diff[:2000]}\n\n"
        "Output ONLY the commit message string. No JSON, no markdown, no quotes."
    )

    if api_key and not LLM_CIRCUIT_BREAKER_TRIPPED and not PAID_ACCOUNT_REQUIRED:
        log_message("Generating commit message via direct Gemini API...")
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"gemini-2.5-flash:generateContent?key={api_key}")
        headers = {'Content-Type': 'application/json'}
        data = {
            "contents": [{"parts": [{"text": prompt}]}]
        }
        try:
            response = requests.post(url, headers=headers, json=data, timeout=30)
            if response.status_code == 200:
                result = response.json()
                msg = (result['candidates'][0]['content']['parts'][0]['text'].strip())
                CONSECUTIVE_FAILURES = 0 
                return msg
            else:
                CONSECUTIVE_FAILURES += 1
                error_text = response.text
                log_message(f"⚠️ Direct Gemini API failed (Status {response.status_code}). Error: {error_text}")
                
                if response.status_code == 429 or "RESOURCE_EXHAUSTED" in error_text:
                    PAID_ACCOUNT_REQUIRED = True
                
                if CONSECUTIVE_FAILURES >= CONFIG["max_consecutive_failures"]:
                    LLM_CIRCUIT_BREAKER_TRIPPED = True
                log_message("Falling back to iteration-based message.")
        except Exception as e:
            CONSECUTIVE_FAILURES += 1
            log_message(f"⚠️ Error calling Gemini API: {e}.")
            if CONSECUTIVE_FAILURES >= CONFIG["max_consecutive_failures"]:
                LLM_CIRCUIT_BREAKER_TRIPPED = True
            log_message("Falling back to iteration-based message.")

    log_message("Using iteration-based commit message fallback.")
    return f"RALPH Loop: Task {task_name[:50]}"

def get_file_content(path: str):
    """Read and return file content if it exists."""
    if os.path.exists(path):
        with open(path, "r") as f:
            return f.read()
    return ""

def get_current_task():
    """Extract the first uncompleted task from plan.md."""
    plan = get_file_content(CONFIG["plan_file"])
    if not plan:
        return "Unknown task"

    for line in plan.splitlines():
        line = line.strip()
        if line.startswith("- [ ]"):
            task = line.replace("- [ ]", "").strip()
            task = re.sub(r'\*\*(.*?)\*\*:', r'\1', task)
            return task
    return "No active task found"

def get_project_state_hash():
    """Generate a hash of the current project state (git status)."""
    try:
        status = subprocess.run(
            ["git", "status", "--porcelain"], capture_output=True, text=True
        )
        plan_content = get_file_content(CONFIG["plan_file"])
        state_str = status.stdout + plan_content
        return hashlib.sha256(state_str.encode()).hexdigest()
    except Exception:
        return ""

def check_stagnation(current_hash: str):
    """Check if the project state has stagnated."""
    if not current_hash:
        return False

    history_file = CONFIG["state_history_file"]
    history = []
    if os.path.exists(history_file):
        with open(history_file, "r") as f:
            history = json.load(f)

    history.append(current_hash)
    if len(history) > 5:
        history = history[-5:]

    with open(history_file, "w") as f:
        json.dump(history, f)

    threshold = CONFIG["stagnation_threshold"]
    if len(history) >= threshold + 1:
        last_n = history[-(threshold + 1):]
        if all(h == last_n[0] for h in last_n):
            return True
    return False

def get_total_cost():
    """Get total cost from stats file."""
    stats_file = CONFIG["stats_file"]
    if os.path.exists(stats_file):
        with open(stats_file, "r") as f:
            stats = json.load(f)
            return stats.get("total_cost_usd", 0.0)
    return 0.0

def main():
    """Main execution loop for RALPH."""
    parser = argparse.ArgumentParser(description="RALPH Loop for Cursor ACE Orchestrator")
    parser.add_argument("prd", nargs="?", help="Path to the PRD file")
    parser.add_argument("--config", default="ralph.yaml", help="Path to YAML config file")
    parser.add_argument("--model", help="Override LLM model")
    parser.add_argument("--max-spend", type=float, help="Override max spend USD")
    parser.add_argument("--plan-file", help="Override plan file path")
    
    args = parser.parse_args()

    # 1. Load YAML config
    load_config(args.config)

    # 2. Override with CLI parameters
    if args.prd:
        CONFIG["default_prd"] = args.prd
    if args.model:
        CONFIG["model"] = args.model
    if args.max_spend:
        CONFIG["max_spend_usd"] = args.max_spend
    if args.plan_file:
        CONFIG["plan_file"] = args.plan_file

    # Load .env if it exists
    if os.path.exists(".env"):
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            with open(".env", "r") as f:
                for line in f:
                    if "=" in line and not line.startswith("#"):
                        key, value = line.split("=", 1)
                        os.environ[key.strip()] = value.strip().strip('"').strip("'")

    prd_path = CONFIG["default_prd"]
    if not os.path.exists(prd_path):
        log_message(f"🚨 PRD file not found: {prd_path}")
        return

    log_message(f"🚀 Starting RALPH Loop using {prd_path} (Model: {CONFIG['model']})...")

    # Step 0: Initial State Analysis
    log_message("Step 0: Analyzing current project state...")
    plan_file = CONFIG["plan_file"]
    plan_content = get_file_content(plan_file)

    analysis_prompt = (
        f"Analyze the current codebase and project structure relative to {prd_path}. "
        f"The existing plan is:\n{plan_content if plan_content else 'No plan yet.'}\n\n"
        f"1. Identify implemented features. 2. Identify missing parts. 3. Update '{plan_file}'."
    )
    run_cursor_agent(analysis_prompt)

    iteration = 0
    while True:
        if PAID_ACCOUNT_REQUIRED and CONFIG["quit_on_rate_limit"]:
            log_message("🚨 STOPPED: Rate limit exceeded.")
            break

        current_cost = get_total_cost()
        if current_cost >= CONFIG["max_spend_usd"]:
            log_message(f"Reached maximum spending limit (${CONFIG['max_spend_usd']}). Stopping.")
            break

        iteration += 1
        log_message(f"=== Iteration {iteration} (Cost: ${current_cost:.4f}) ===")

        current_task = get_current_task()
        log_message(f"📍 Current Task: {current_task}")

        # Step 1: Planning
        plan_content = get_file_content(plan_file)
        if not plan_content or "[ ]" not in plan_content:
            log_message("Step 1: Planning...")
            prompt = f"Update '{plan_file}' based on {prd_path} and SPECS.md."
            run_cursor_agent(prompt)
            plan_content = get_file_content(plan_file)
            if not plan_content:
                continue

        # Step 2: Build
        log_message("Step 2: Building...")
        current_hash = get_project_state_hash()
        if check_stagnation(current_hash):
            log_message("⚠️ Stagnation detected!")
            prompt = f"Stagnation detected. Analyze {prd_path} and {plan_file} to recover."
        else:
            prompt = f"Implement next task from {plan_file}. Target PRD: {prd_path}."
        run_cursor_agent(prompt)

        # Step 3: Verify
        log_message("Step 3: Verifying...")
        run_cursor_agent("Run all tests and linter. Fix any failures.")

        # Step 4: Commit
        log_message("Step 4: Committing...")
        try:
            status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
            if status.stdout.strip():
                commit_msg = generate_commit_message(current_task)
                subprocess.run(["git", "add", "."], check=True)
                subprocess.run(["git", "commit", "-m", commit_msg], check=True)
                subprocess.run(["git", "push"], check=True)
                log_message(f"Committed: {commit_msg}")
        except Exception as e:
            log_message(f"Git failed: {e}")

        # Step 5: Update Plan
        log_message("Step 5: Updating plan...")
        run_cursor_agent(f"Update '{plan_file}' and '{CONFIG['changelog_file']}'.")

        if "[ ]" not in plan_content:
            log_message("🎉 Plan complete! Checking PRD...")
            gap_result = run_cursor_agent(f"Is {prd_path} fully implemented? Respond 'PRD_COMPLETE' if yes.")
            if gap_result and "PRD_COMPLETE" in gap_result:
                log_message("✅ PRD Complete!")
                break

if __name__ == "__main__":
    main()
