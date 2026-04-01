import os
import subprocess
import sys
import time
import json
import hashlib
import re
import requests
from datetime import datetime

# Configuration
MODEL = "gemini-3-flash"
MAX_SPEND_USD = 20.0
PLAN_FILE = "plan.md"
CHANGELOG_FILE = "changelog.md"
LOG_FILE = "ralph_execution.log"
STATS_FILE = "ralph_stats.json"
STATE_HISTORY_FILE = "ralph_state_history.json"
DEFAULT_PRD = "PRD-01 - Cursor-ace-orchestrator-prd.md"
STAGNATION_THRESHOLD = 2  # Number of iterations with same state before alert
MAX_CONSECUTIVE_FAILURES = 3  # Max LLM failures before circuit breaker trips
QUIT_ON_RATE_LIMIT = True  # If True, stop the loop on rate limit detection

# Global State
LLM_CIRCUIT_BREAKER_TRIPPED = False
CONSECUTIVE_FAILURES = 0
PAID_ACCOUNT_REQUIRED = False

# NOTE: This script is a temporary bootstrapping tool.
# Once the core ACE Orchestrator is built, this script should be
# manually removed and replaced by the system's own 'ace loop' command.

# Pricing for gemini-3-flash (approximate 2026 pricing)
# $0.10 per 1M input tokens, $0.40 per 1M output tokens
PRICE_INPUT_1M = 0.10
PRICE_OUTPUT_1M = 0.40


def log_message(message: str):
    """Log a message with timestamp to console and file."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted_msg = f"[{timestamp}] {message}"
    print(formatted_msg)
    with open(LOG_FILE, "a") as f:
        f.write(formatted_msg + "\n")


def update_stats(input_tokens: int, output_tokens: int, elapsed_time: float):
    """Update execution statistics and cost."""
    stats = {
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "total_cost_usd": 0.0,
        "total_time_sec": 0.0,
        "iterations": 0,
    }
    if os.path.exists(STATS_FILE):
        with open(STATS_FILE, "r") as f:
            stats = json.load(f)

    cost = (input_tokens / 1_000_000 * PRICE_INPUT_1M
            + output_tokens / 1_000_000 * PRICE_OUTPUT_1M)

    stats["total_input_tokens"] += input_tokens
    stats["total_output_tokens"] += output_tokens
    stats["total_cost_usd"] += cost
    stats["total_time_sec"] += elapsed_time
    stats["iterations"] += 1

    with open(STATS_FILE, "w") as f:
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

    # ... existing cmd setup ...
    cmd = [
        "cursor-agent",
        "--api-key",
        os.getenv("CURSOR_API_KEY", ""),
        "--print",
        "--model",
        MODEL,
        "--output-format",
        "stream-json",
        "--force",
        "--trust",
        prompt,
    ]

    try:
        # Execute the command and capture both stdout and stderr
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

            if CONSECUTIVE_FAILURES >= MAX_CONSECUTIVE_FAILURES:
                LLM_CIRCUIT_BREAKER_TRIPPED = True
                log_message("🚨 CIRCUIT BREAKER TRIPPED! Too many consecutive failures.")

            log_message(f"--- STDOUT ---\n{result.stdout}")
            log_message(f"--- STDERR ---\n{result.stderr}")
            return None

        # Reset failures on success
        CONSECUTIVE_FAILURES = 0
        # If successful, extract simulated stats
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
        
        if CONSECUTIVE_FAILURES >= MAX_CONSECUTIVE_FAILURES:
            LLM_CIRCUIT_BREAKER_TRIPPED = True
            log_message("🚨 CIRCUIT BREAKER TRIPPED! Too many consecutive failures.")
            
        return None


def generate_commit_message(task_name: str):
    """Generate a descriptive commit message using direct Gemini API or cursor-agent."""
    global LLM_CIRCUIT_BREAKER_TRIPPED, CONSECUTIVE_FAILURES, PAID_ACCOUNT_REQUIRED

    # Check for Gemini API key in multiple possible environment variables
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

    # ... existing key loading ...
    if not api_key:
        try:
            from dotenv import load_dotenv
            load_dotenv()
            api_key = (os.getenv("GEMINI_API_KEY") or
                       os.getenv("GOOGLE_API_KEY"))
        except ImportError:
            # If dotenv is not installed, we can try a simple manual parse of .env
            if os.path.exists(".env"):
                with open(".env", "r") as f:
                    for line in f:
                        if (line.startswith("GOOGLE_API_KEY=") or
                                line.startswith("GEMINI_API_KEY=")):
                            api_key = line.split("=", 1)[1].strip().strip('"').strip("'")
                            break

    # Get git diff for context
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
            response = requests.post(url, headers=headers, json=data,
                                     timeout=30)
            if response.status_code == 200:
                result = response.json()
                msg = (result['candidates'][0]['content']['parts'][0]['text']
                       .strip())
                CONSECUTIVE_FAILURES = 0 # Reset on success
                return msg
            else:
                CONSECUTIVE_FAILURES += 1
                error_text = response.text
                log_message(f"⚠️ Direct Gemini API failed (Status "
                            f"{response.status_code}). Error: {error_text} "
                            f"(Consecutive failures: {CONSECUTIVE_FAILURES})")
                
                if response.status_code == 429 or "RESOURCE_EXHAUSTED" in error_text:
                    PAID_ACCOUNT_REQUIRED = True
                    log_message("🚨 Detected Free Tier rate limit (429/RESOURCE_EXHAUSTED).")
                
                if CONSECUTIVE_FAILURES >= MAX_CONSECUTIVE_FAILURES:
                    LLM_CIRCUIT_BREAKER_TRIPPED = True
                    log_message("🚨 CIRCUIT BREAKER TRIPPED! Too many consecutive failures.")
                log_message("Falling back to iteration-based message.")
        except Exception as e:
            CONSECUTIVE_FAILURES += 1
            log_message(f"⚠️ Error calling Gemini API: {e}. "
                        f"(Consecutive failures: {CONSECUTIVE_FAILURES})")
            if CONSECUTIVE_FAILURES >= MAX_CONSECUTIVE_FAILURES:
                LLM_CIRCUIT_BREAKER_TRIPPED = True
                log_message("🚨 CIRCUIT BREAKER TRIPPED! Too many consecutive failures.")
            log_message("Falling back to iteration-based message.")

    # Fallback to iteration-based message
    log_message("Using iteration-based commit message fallback.")
    return f"RALPH Loop: Task {task_name[:50]}"

    # Clean the message
    if msg:
        if "{" in msg and "}" in msg:
            try:
                msg_match = re.search(r'}(.*)', msg, re.DOTALL)
                if msg_match and msg_match.group(1).strip():
                    msg = msg_match.group(1).strip()
                else:
                    data = json.loads(msg)
                    if isinstance(data, dict) and "message" in data:
                        msg = data["message"]
            except Exception:
                pass

        msg = re.sub(r'^.*?commit message:?\s*', '', msg, flags=re.IGNORECASE)
        msg = msg.strip().split("\n")[0]

    return msg


def get_file_content(path: str):
    """Read and return file content if it exists."""
    if os.path.exists(path):
        with open(path, "r") as f:
            return f.read()
    return ""


def get_current_task():
    """Extract the first uncompleted task from plan.md."""
    plan = get_file_content(PLAN_FILE)
    if not plan:
        return "Unknown task"

    for line in plan.splitlines():
        line = line.strip()
        if line.startswith("- [ ]"):
            # Extract task description, removing the checkbox and bold markers if present
            task = line.replace("- [ ]", "").strip()
            task = re.sub(r'\*\*(.*?)\*\*:', r'\1', task) # Remove bold markers and colon
            return task
    return "No active task found"


def get_project_state_hash():
    """Generate a hash of the current project state (git status)."""
    try:
        status = subprocess.run(
            ["git", "status", "--porcelain"], capture_output=True, text=True
        )
        # Include a hash of the plan.md file to detect if the agent is
        # stuck on the same task
        plan_content = get_file_content(PLAN_FILE)
        state_str = status.stdout + plan_content
        return hashlib.sha256(state_str.encode()).hexdigest()
    except Exception:
        return ""


def check_stagnation(current_hash: str):
    """Check if the project state has stagnated."""
    if not current_hash:
        return False

    history = []
    if os.path.exists(STATE_HISTORY_FILE):
        with open(STATE_HISTORY_FILE, "r") as f:
            history = json.load(f)

    history.append(current_hash)
    if len(history) > 5:
        history = history[-5:]

    with open(STATE_HISTORY_FILE, "w") as f:
        json.dump(history, f)

    if len(history) >= STAGNATION_THRESHOLD + 1:
        last_n = history[-(STAGNATION_THRESHOLD + 1):]
        if all(h == last_n[0] for h in last_n):
            return True
    return False


def get_total_cost():
    """Get total cost from stats file."""
    if os.path.exists(STATS_FILE):
        with open(STATS_FILE, "r") as f:
            stats = json.load(f)
            return stats.get("total_cost_usd", 0.0)
    return 0.0


def main():
    """Main execution loop for RALPH."""
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

    # Simple argument parsing
    prd_path = DEFAULT_PRD
    if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        prd_path = sys.argv[1]

    if "--help" in sys.argv or "-h" in sys.argv:
        print("RALPH Loop for Cursor ACE Orchestrator")
        print("Usage: python ralph_loop.py [PRD_PATH]")
        print(f"Default PRD: {DEFAULT_PRD}")
        return

    if not os.path.exists(prd_path):
        log_message(f"🚨 PRD file not found: {prd_path}")
        return

    log_message(
        f"🚀 Starting RALPH Loop for Cursor ACE Orchestrator using "
        f"{prd_path}...")

    # Step 0: Initial State Analysis & Resumption Logic
    log_message("Step 0: Analyzing current project state...")
    plan_content = get_file_content(PLAN_FILE)

    analysis_prompt = (
        f"Analyze the current codebase and project structure relative to "
        f"{prd_path}. "
        f"The existing plan is:\n"
        f"{plan_content if plan_content else 'No plan yet.'}\n\n"
        f"1. Identify which features from {prd_path} are already implemented "
        "(e.g., ace.py, .ace/ structure, context builder, write-back).\n"
        "2. Identify what is currently missing or partially implemented "
        "(e.g., TDD/tests, native ace loop, SOP logic, Google Stitch).\n"
        "3. Update 'plan.md' to reflect this reality, marking completed tasks "
        "as [x] and adding missing ones. "
        f"Ensure the plan is sorted by priority for full {prd_path} "
        "implementation."
    )
    run_cursor_agent(analysis_prompt)

    iteration = 0
    while True:
        if PAID_ACCOUNT_REQUIRED and QUIT_ON_RATE_LIMIT:
            log_message("🚨 STOPPED: Gemini API Free Tier quota exceeded. Please upgrade to a paid plan or wait for the quota to reset.")
            break

        current_cost = get_total_cost()
        if current_cost >= MAX_SPEND_USD:
            log_message(f"Reached maximum spending limit (${MAX_SPEND_USD}). Stopping.")
            break

        iteration += 1
        log_message(f"=== Iteration {iteration} (Current Cost: ${current_cost:.4f}) ===")

        # Get current task for context and commit messages
        current_task = get_current_task()
        log_message(f"📍 Current Task: {current_task}")

        # Step 1: Planning
        plan_content = get_file_content(PLAN_FILE)
        if not plan_content or "[ ]" not in plan_content:
            log_message("Step 1: Planning (or re-planning)...")
            prompt = (
                f"Based on {prd_path} (primary), and SPECS.md, create or "
                "update the detailed, sorted list of implementation steps for "
                "the Cursor ACE Orchestrator. The system should be built in "
                "Python, supporting CLI first but architected for FastAPI "
                "later. Save the plan as 'plan.md' as a sorted list of tasks. "
                "If a plan already exists, only add tasks that are missing to "
                "reach 100% completion."
            )
            run_cursor_agent(prompt)
            plan_content = get_file_content(PLAN_FILE)
            if not plan_content:
                log_message("Failed to create/update plan.md. Retrying...")
                continue

        # Step 2: Build next step
        log_message("Step 2: Building next task...")

        # Stagnation detection
        current_hash = get_project_state_hash()
        if check_stagnation(current_hash):
            log_message(
                "⚠️ Stagnation detected! Activating Architect/Debugger "
                "recovery..."
            )
            prompt = (
                f"The project state has not changed for "
                f"{STAGNATION_THRESHOLD} iterations. "
                "You are now in Architect/Debugger mode. Analyze the current "
                "codebase, "
                f"the target PRD ({prd_path}), and the current plan "
                f"({PLAN_FILE}). "
                "Identify why the implementation is stuck. Are there missing "
                "dependencies? "
                "Conflicting rules? Ambiguous requirements? "
                "Provide a clear analysis and propose a new strategy to break "
                "the loop. "
                "Then, implement the necessary changes to move forward."
            )
        else:
            prompt = (
                f"Current plan:\n{plan_content}\n\n"
                f"Target PRD: {prd_path}\n\n"
                "Implement the next (first uncompleted) task from the plan. "
                f"CRITICAL: Focus on implementing the following missing core "
                f"areas from {prd_path}:\n"
                "1. TDD (Test-Driven Development): Establish the 'tests/' "
                "directory and write unit tests for ACEService.\n"
                "2. Native ace loop: Integrate the RALPH loop logic directly "
                "into 'ace.py' as a native command.\n"
                "3. SOP Logic: Implement formal instructions/SOPs for agent "
                "onboarding and PR reviews.\n"
                "4. Google Stitch Integration: Connect the CLI stubs to "
                "actual API or code extraction logic.\n\n"
                "Include necessary tests. Ensure the software remains "
                "runnable and testable. Use Python and follow the "
                "architecture described "
                f"in {prd_path} and ARCHITECTURE.md."
            )
        run_cursor_agent(prompt)

        # Step 3: Verify (Tests, Lint, Run)
        log_message("Step 3: Verifying implementation...")
        prompt = (
            "Run all tests, linter, and verify that the software is runnable. "
            "If there are any failures, fix them immediately. "
            "Do not proceed until all tests pass and the code is clean."
        )
        verification_result = run_cursor_agent(prompt)
        if verification_result is None:
            log_message("Verification failed. Retrying...")
            continue

        # Step 4: Commit
        log_message("Step 4: Committing changes...")
        try:
            # Check if there are changes to commit
            status = subprocess.run(
                ["git", "status", "--porcelain"], capture_output=True,
                text=True)
            if status.stdout.strip():
                commit_msg = generate_commit_message(current_task)

                # Final fallback if cleaning resulted in empty string
                if not commit_msg or len(commit_msg.strip()) < 5:
                    commit_msg = (f"RALPH Loop: Implementation iteration "
                                  f"{iteration} - {current_task[:50]}")

                subprocess.run(["git", "add", "."], check=True)
                subprocess.run(["git", "commit", "-m", commit_msg],
                               check=True)
                subprocess.run(["git", "push"], check=True)
                log_message(f"Committed with message: {commit_msg}")
            else:
                log_message("No changes to commit.")
        except subprocess.CalledProcessError as e:
            log_message(f"Git operation failed: {e}")

        # Step 5: Update Plan and Changelog
        log_message("Step 5: Updating plan and changelog...")
        prompt = (
            f"Update '{PLAN_FILE}' by marking the completed task as done "
            f"and keeping the list sorted. Write the completed task details "
            f"to '{CHANGELOG_FILE}'. Ensure the plan reflects what is left "
            "to do."
        )
        run_cursor_agent(prompt)

        log_message(f"Iteration {iteration} complete.")

        if (
            "[ ]" not in plan_content
            and "todo" not in plan_content.lower()
        ):
            log_message(
                "🎉 All tasks in the plan are completed! Checking if PRD is "
                "fully implemented..."
            )

            # Step 1.5: Final PRD Gap Analysis
            log_message("Step 1.5: Final PRD Gap Analysis...")
            gap_prompt = (
                f"Analyze the current codebase relative to {prd_path}. "
                "Is the PRD fully implemented? If not, identify the missing parts. "
                "If missing parts are found, update 'plan.md' with the new tasks. "
                "If fully implemented, respond with 'PRD_COMPLETE'."
            )
            gap_result = run_cursor_agent(gap_prompt)

            if gap_result and "PRD_COMPLETE" in gap_result:
                log_message("✅ PRD is fully implemented!")

                # Final Analysis Step
                log_message("Step 6: Final Implementation Analysis...")
                analysis_prompt = (
                    f"Analyze the current state of implementation relative to "
                    f"{prd_path}. "
                    "1. Summarize how much of the PRD is implemented "
                    "(percentage and key features).\n"
                    "2. Identify exactly what is missing to reach 100% "
                    "completion.\n"
                    "3. Recommend the final set of steps to achieve full "
                    "implementation.\n"
                    "Output this analysis as a markdown report in "
                    "'FINAL_ANALYSIS.md'."
                )
                run_cursor_agent(analysis_prompt)
                break
            else:
                log_message("🔄 PRD is not fully implemented. Re-planning...")
                continue

    # Final check after loop
    final_cost = get_total_cost()
    if final_cost >= MAX_SPEND_USD:
        print(f"Reached maximum spending limit (${MAX_SPEND_USD}). Stopping.")


if __name__ == "__main__":
    main()
