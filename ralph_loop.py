import os
import subprocess
import sys
import time
import json
import hashlib
import re
import requests
import argparse
import fcntl
import signal
from datetime import datetime

LOOP_LOCK_FILE = ".ace/loop.lock"

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
    "max_iterations": 50,
    "plan_file": "plan.md",
    "changelog_file": "changelog.md",
    "log_file": "ralph_execution.log",
    "stats_file": "ralph_stats.json",
    "state_history_file": "ralph_state_history.json",
    "default_prd": "PRD-01 - Cursor-ace-orchestrator-prd.md",
    "stagnation_threshold": 3,
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
    if os.path.exists(str(config_path)):
        try:
            with open(str(config_path), "r") as f:
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
    with open(str(log_file), "a") as f:
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
    if os.path.exists(str(stats_file)):
        with open(str(stats_file), "r") as f:
            stats = json.load(f)

    price_in = float(str(CONFIG.get("price_input_1m", 0.10)))
    price_out = float(str(CONFIG.get("price_output_1m", 0.40)))

    cost = input_tokens / 1_000_000 * price_in + output_tokens / 1_000_000 * price_out

    stats["total_input_tokens"] += input_tokens
    stats["total_output_tokens"] += output_tokens
    stats["total_cost_usd"] += cost
    stats["total_time_sec"] += elapsed_time
    stats["iterations"] += 1

    with open(str(stats_file), "w") as f:
        json.dump(stats, f, indent=2)

    log_message(
        f"Stats Update: +{input_tokens}in, +{output_tokens}out | "
        f"Cost: ${cost:.6f} | Time: {elapsed_time:.2f}s"
    )
    log_message(f"Total Cost so far: ${stats['total_cost_usd']:.4f}")


def parse_usage_from_output(stdout: str) -> tuple[int, int]:
    """Parse token usage from cursor-agent stream-json output."""
    input_tokens = 0
    output_tokens = 0
    found_usage = False
    for line in stdout.splitlines():
        try:
            obj = json.loads(line)
            if "usage" in obj:
                input_tokens += obj["usage"].get("input_tokens", 0)
                output_tokens += obj["usage"].get("output_tokens", 0)
                found_usage = True
        except json.JSONDecodeError:
            continue
    
    if not found_usage:
        # Fallback to conservative estimate: ~4 chars per token
        input_tokens = int(len(stdout) / 4)
        output_tokens = int(len(stdout) / 4)
        
    return input_tokens, output_tokens


def run_cursor_agent(prompt: str, timeout: int = 300):
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

    try:
        cmd_args = [
            "cursor-agent",
            "--api-key",
            os.getenv("CURSOR_API_KEY", ""),
            "--print",
            "--model",
            str(CONFIG["model"]),
            "--output-format",
            "stream-json",
            "--force",
            "--trust",
            prompt,
        ]
        
        # Use Popen with process group to ensure cleanup of sub-agents
        proc = subprocess.Popen(
            cmd_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            preexec_fn=os.setsid if hasattr(os, "setsid") else None,
        )
        
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
            elapsed = time.time() - start_time
        except subprocess.TimeoutExpired:
            if hasattr(os, "killpg"):
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            else:
                proc.terminate()
            stdout, stderr = proc.communicate()
            log_message(f"❌ Cursor Agent timed out after {timeout}s and was killed.")
            return None
        finally:
            # Ensure cleanup even on unexpected errors
            try:
                if hasattr(os, "killpg"):
                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                else:
                    proc.terminate()
            except (ProcessLookupError, OSError):
                pass

        if proc.returncode != 0:
            CONSECUTIVE_FAILURES += 1
            error_output = stdout + stderr
            log_message(
                f"❌ Cursor Agent failed with Exit Code {proc.returncode} "
                f"(Consecutive failures: {CONSECUTIVE_FAILURES})"
            )

            if (
                "429" in error_output
                or "RESOURCE_EXHAUSTED" in error_output
                or "rate limit" in error_output.lower()
            ):
                PAID_ACCOUNT_REQUIRED = True
                log_message(
                    "🚨 Detected rate limit from Cursor Agent (429/RESOURCE_EXHAUSTED)."
                )

            if CONSECUTIVE_FAILURES >= int(str(CONFIG.get("max_consecutive_failures", 3))):
                LLM_CIRCUIT_BREAKER_TRIPPED = True
                log_message(
                    "🚨 CIRCUIT BREAKER TRIPPED! Too many consecutive failures."
                )

            log_message(f"--- STDOUT ---\n{stdout}")
            log_message(f"--- STDERR ---\n{stderr}")
            return None

        CONSECUTIVE_FAILURES = 0
        input_tokens, output_tokens = parse_usage_from_output(stdout)
        update_stats(input_tokens, output_tokens, elapsed)
        log_message("✅ Cursor Agent completed successfully.")
        return stdout

    except Exception as e:
        CONSECUTIVE_FAILURES += 1
        log_message(
            f"🚨 Unexpected error during subprocess execution: {str(e)} "
            f"(Consecutive failures: {CONSECUTIVE_FAILURES})"
        )

        if CONSECUTIVE_FAILURES >= int(str(CONFIG.get("max_consecutive_failures", 3))):
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
            api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        except ImportError:
            if os.path.exists(".env"):
                with open(".env", "r") as f:
                    for line in f:
                        if line.startswith("GOOGLE_API_KEY=") or line.startswith(
                            "GEMINI_API_KEY="
                        ):
                            api_key = (
                                line.split("=", 1)[1].strip().strip('"').strip("'")
                            )
                            break

    try:
        diff = subprocess.run(
            ["git", "diff", "--cached"], capture_output=True, text=True
        ).stdout
        if not diff:
            diff = subprocess.run(
                ["git", "diff"], capture_output=True, text=True
            ).stdout
    except Exception:
        diff = "No diff available"

    prompt = (
        f"Generate a concise, one-line git commit message for the following task: {task_name}\n\n"
        f"Git Diff context:\n{diff[:2000]}\n\n"
        "Output ONLY the commit message string. No JSON, no markdown, no quotes."
    )

    url = None
    headers = None
    data = None

    if api_key and not LLM_CIRCUIT_BREAKER_TRIPPED and not PAID_ACCOUNT_REQUIRED:
        log_message("Generating commit message via direct Gemini API...")
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-2.5-flash:generateContent?key={api_key}"
        )
        headers = {"Content-Type": "application/json"}
        data = {"contents": [{"parts": [{"text": prompt}]}]}

    if not url:
        return f"update: {task_name}"

    try:
        response = requests.post(url, headers=headers, json=data, timeout=30)
        if response.status_code == 200:
            result = response.json()
            msg = result["candidates"][0]["content"]["parts"][0]["text"].strip()
            return msg
        else:
            CONSECUTIVE_FAILURES += 1
            error_text = response.text
            log_message(
                f"⚠️ Direct Gemini API failed (Status {response.status_code}). "
                f"Error: {error_text}"
            )

            if response.status_code == 429 or "RESOURCE_EXHAUSTED" in error_text:
                PAID_ACCOUNT_REQUIRED = True

            if CONSECUTIVE_FAILURES >= int(str(CONFIG.get("max_consecutive_failures", 3))):
                LLM_CIRCUIT_BREAKER_TRIPPED = True
            log_message("Falling back to iteration-based message.")
    except Exception as e:
        CONSECUTIVE_FAILURES += 1
        log_message(f"⚠️ Error calling Gemini API: {e}.")
        if CONSECUTIVE_FAILURES >= int(str(CONFIG.get("max_consecutive_failures", 3))):
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
            task = re.sub(r"\*\*(.*?)\*\*:", r"\1", task)
            return task
    return "No active task found"


def get_project_state_hash():
    """Generate a hash of the current project state (git diff)."""
    try:
        # Hash the actual diff content for better stagnation detection
        diff = subprocess.run(
            ["git", "diff", "HEAD"], capture_output=True, text=True
        ).stdout
        untracked = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"], capture_output=True, text=True
        ).stdout
        plan_content = get_file_content(CONFIG["plan_file"])
        state_str = diff + untracked + plan_content
        return hashlib.sha256(state_str.encode()).hexdigest()
    except Exception:
        return ""


def check_stagnation(current_hash: str, current_task: str):
    """Check if the project state or task has stagnated."""
    if not current_hash:
        return False

    history_file = CONFIG["state_history_file"]
    history = []
    if os.path.exists(str(history_file)):
        with open(str(history_file), "r") as f:
            history = json.load(f)

    # Track both hash and task
    history.append({"hash": current_hash, "task": current_task})
    if len(history) > 10:
        history = history[-10:]

    with open(str(history_file), "w") as f:
        json.dump(history, f)

    threshold = int(str(CONFIG.get("stagnation_threshold", 3)))
    if len(history) >= threshold:
        last_n = history[-threshold:]
        # Check if hash is identical across last N iterations
        if all(h["hash"] == last_n[0]["hash"] for h in last_n):
            return True
        # Check if task is identical across last N iterations (task stagnation)
        if all(h["task"] == last_n[0]["task"] for h in last_n):
            log_message(f"⚠️ Task stagnation detected for: {current_task}")
            return True
            
    return False


def get_total_cost() -> float:
    """Get total cost from stats file."""
    stats_file = CONFIG["stats_file"]
    if os.path.exists(str(stats_file)):
        with open(str(stats_file), "r") as f:
            stats = json.load(f)
            return float(stats.get("total_cost_usd", 0.0))
    return 0.0


def main():
    """Main execution loop for RALPH."""
    parser = argparse.ArgumentParser(
        description="RALPH Loop for Cursor ACE Orchestrator"
    )
    parser.add_argument("prd", nargs="?", help="Path to the PRD file")
    parser.add_argument(
        "--config", default="ralph.yaml", help="Path to YAML config file"
    )
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

    os.makedirs(os.path.dirname(LOOP_LOCK_FILE), exist_ok=True)
    lock_fd = open(LOOP_LOCK_FILE, "w")
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        lock_fd.write(f"ralph_loop pid={os.getpid()} started={datetime.now().isoformat()}\n")
        lock_fd.flush()
    except OSError:
        log_message("🚨 Another loop (ralph or ace) is already running. Exiting.")
        lock_fd.close()
        return

    log_message(
        f"🚀 Starting RALPH Loop using {prd_path} (Model: {CONFIG['model']})..."
    )

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

    max_iter = int(CONFIG.get("max_iterations", 50))
    for iteration in range(1, max_iter + 1):
        if PAID_ACCOUNT_REQUIRED and CONFIG["quit_on_rate_limit"]:
            log_message("🚨 STOPPED: Rate limit exceeded.")
            break

        current_cost = get_total_cost()
        if current_cost >= float(str(CONFIG.get("max_spend_usd", 20.0))):
            log_message(
                f"Reached maximum spending limit (${CONFIG['max_spend_usd']}). Stopping."
            )
            break

        log_message(f"=== Iteration {iteration}/{max_iter} (Cost: ${current_cost:.4f}) ===")

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

        # Step 2: Build, Verify, and Update Plan
        log_message("Step 2: Building, Verifying, and Updating Plan...")
        current_hash = get_project_state_hash()
        if check_stagnation(current_hash, current_task):
            log_message("⚠️ Stagnation detected!")
            prompt = (
                f"Stagnation detected for task '{current_task}'. Analyze {prd_path} and {plan_file} to recover. "
                f"Implement the next necessary change, run tests/linter to verify, and update '{plan_file}'."
            )
        else:
            prompt = (
                f"Implement the next task from {plan_file}: '{current_task}'. "
                f"Target PRD: {prd_path}. "
                f"After implementation, run all tests and linter, fix any failures, "
                f"and mark the task as completed in '{plan_file}' and update '{CONFIG['changelog_file']}'."
            )
        run_cursor_agent(prompt)

        # Step 3: Commit
        log_message("Step 3: Committing...")
        try:
            status = subprocess.run(
                ["git", "status", "--porcelain"], capture_output=True, text=True
            )
            if status.stdout.strip():
                commit_msg = generate_commit_message(current_task)
                subprocess.run(["git", "add", "."], check=True)
                subprocess.run(["git", "commit", "-m", commit_msg], check=True)
                subprocess.run(["git", "push"], check=True)
                log_message(f"Committed: {commit_msg}")
        except Exception as e:
            log_message(f"Git failed: {e}")

        # Check for completion
        plan_content = get_file_content(plan_file)
        if "[ ]" not in plan_content:
            log_message("🎉 Plan complete! Checking PRD...")
            gap_result = run_cursor_agent(
                f"Is {prd_path} fully implemented? Respond 'PRD_COMPLETE' if yes."
            )
            if gap_result and "PRD_COMPLETE" in gap_result:
                log_message("✅ PRD Complete!")
                break
    else:
        log_message(f"Reached maximum iterations ({max_iter}). Stopping.")

    fcntl.flock(lock_fd, fcntl.LOCK_UN)
    lock_fd.close()
    try:
        os.remove(LOOP_LOCK_FILE)
    except OSError:
        pass


if __name__ == "__main__":
    main()
