import os
import subprocess
import sys
import time
import json
import hashlib
import re
from datetime import datetime

# Configuration
MODEL = "gemini-3-flash"
MAX_ITERATIONS = 10
PLAN_FILE = "plan.md"
CHANGELOG_FILE = "changelog.md"
LOG_FILE = "ralph_execution.log"
STATS_FILE = "ralph_stats.json"
STATE_HISTORY_FILE = "ralph_state_history.json"
DEFAULT_PRD = "PRD-01 - Cursor-ace-orchestrator-prd.md"
STAGNATION_THRESHOLD = 2  # Number of iterations with same state before alert

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

    cost = (input_tokens / 1_000_000 * PRICE_INPUT_1M) + (output_tokens / 1_000_000 * PRICE_OUTPUT_1M)

    stats["total_input_tokens"] += input_tokens
    stats["total_output_tokens"] += output_tokens
    stats["total_cost_usd"] += cost
    stats["total_time_sec"] += elapsed_time
    stats["iterations"] += 1

    with open(STATS_FILE, "w") as f:
        json.dump(stats, f, indent=2)

    log_message(
        f"Stats Update: +{input_tokens}in, +{output_tokens}out | " f"Cost: ${cost:.6f} | Time: {elapsed_time:.2f}s"
    )
    log_message(f"Total Cost so far: ${stats['total_cost_usd']:.4f}")


def run_cursor_agent(prompt: str):
    """Runs cursor-agent in non-interactive mode and tracks usage."""
    start_time = time.time()
    log_message(f"Running Cursor Agent: {prompt[:100]}...")

    # Corrected command structure based on cursor-agent --help
    cmd = [
        "cursor-agent",
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
            log_message(f"❌ Cursor Agent failed with Exit Code {result.returncode}")
            log_message(f"--- STDOUT ---\n{result.stdout}")
            log_message(f"--- STDERR ---\n{result.stderr}")
            return None

        # If successful, extract simulated stats
        input_tokens = len(prompt.split()) * 1.3
        output_tokens = len(result.stdout.split()) * 1.3

        update_stats(int(input_tokens), int(output_tokens), elapsed)
        log_message("✅ Cursor Agent completed successfully.")
        return result.stdout

    except Exception as e:
        log_message(f"🚨 Unexpected error during subprocess execution: {str(e)}")
        return None


def get_file_content(path: str):
    """Read and return file content if it exists."""
    if os.path.exists(path):
        with open(path, "r") as f:
            return f.read()
    return ""


def get_project_state_hash():
    """Generate a hash of the current project state (git status)."""
    try:
        status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
        # Also include a hash of the plan.md file to detect if the agent is stuck on the same task
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
    
    # Check if the last N hashes are identical
    if len(history) >= STAGNATION_THRESHOLD + 1:
        last_n = history[-(STAGNATION_THRESHOLD + 1):]
        if all(h == last_n[0] for h in last_n):
            return True
    return False


def main():
    """Main execution loop for RALPH."""
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

    log_message(f"🚀 Starting RALPH Loop for Cursor ACE Orchestrator using {prd_path}...")

    # Step 0: Initial State Analysis & Resumption Logic
    log_message("Step 0: Analyzing current project state...")
    plan_content = get_file_content(PLAN_FILE)
    
    analysis_prompt = (
        f"Analyze the current codebase and project structure relative to {prd_path}. "
        f"The existing plan is:\n{plan_content if plan_content else 'No plan yet.'}\n\n"
        f"1. Identify which features from {prd_path} are already implemented (e.g., ace.py, .ace/ structure, context builder, write-back).\n"
        "2. Identify what is currently missing or partially implemented (e.g., TDD/tests, native ace loop, SOP logic, Google Stitch).\n"
        "3. Update 'plan.md' to reflect this reality, marking completed tasks as [x] and adding missing ones. "
        f"Ensure the plan is sorted by priority for full {prd_path} implementation."
    )
    run_cursor_agent(analysis_prompt)
    
    iteration = 0
    while iteration < MAX_ITERATIONS:
        iteration += 1
        log_message(f"=== Iteration {iteration}/{MAX_ITERATIONS} ===")

        # Step 1: Planning
        plan_content = get_file_content(PLAN_FILE)
        if not plan_content or "[ ]" not in plan_content:
            log_message("Step 1: Planning (or re-planning)...")
            prompt = (
                f"Based on {prd_path} (primary), and SPECS.md, create or update the "
                "detailed, sorted list of implementation steps for the Cursor ACE Orchestrator. "
                "The system should be built in Python, supporting CLI first but architected for "
                "FastAPI later. Save the plan as 'plan.md' as a sorted list of tasks. "
                "If a plan already exists, only add tasks that are missing to reach 100% completion."
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
            log_message("⚠️ Stagnation detected! Activating Architect/Debugger recovery...")
            prompt = (
                f"The project state has not changed for {STAGNATION_THRESHOLD} iterations. "
                "You are now in Architect/Debugger mode. Analyze the current codebase, "
                f"the target PRD ({prd_path}), and the current plan ({PLAN_FILE}). "
                "Identify why the implementation is stuck. Are there missing dependencies? "
                "Conflicting rules? Ambiguous requirements? "
                "Provide a clear analysis and propose a new strategy to break the loop. "
                "Then, implement the necessary changes to move forward."
            )
        else:
            prompt = (
                f"Current plan:\n{plan_content}\n\n"
                f"Target PRD: {prd_path}\n\n"
                "Implement the next (first uncompleted) task from the plan. "
                f"CRITICAL: Focus on implementing the following missing core areas from {prd_path}:\n"
                "1. TDD (Test-Driven Development): Establish the 'tests/' directory and write unit tests for ACEService.\n"
                "2. Native ace loop: Integrate the RALPH loop logic directly into 'ace.py' as a native command.\n"
                "3. SOP Logic: Implement formal instructions/SOPs for agent onboarding and PR reviews.\n"
                "4. Google Stitch Integration: Connect the CLI stubs to actual API or code extraction logic.\n\n"
                "Include necessary tests. Ensure the software remains runnable "
                "and testable. Use Python and follow the architecture described "
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
            status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
            if status.stdout.strip():
                # Generate a descriptive commit message using the agent
                log_message("Generating descriptive commit message...")
                commit_prompt = (
                    "Based on the changes made in this iteration, generate a concise, "
                    "descriptive git commit message (one line). Focus on what was implemented "
                    "or fixed. Output ONLY the commit message string. "
                    "DO NOT output any JSON, system metadata, or extra text."
                )
                commit_msg = run_cursor_agent(commit_prompt)
                
                # Clean commit message if it contains JSON or extra text
                if commit_msg:
                    # Remove JSON if present
                    if "{" in commit_msg and "}" in commit_msg:
                        try:
                            # Try to find the message outside JSON if it's mixed
                            msg_match = re.search(r'}(.*)', commit_msg, re.DOTALL)
                            if msg_match and msg_match.group(1).strip():
                                commit_msg = msg_match.group(1).strip()
                            else:
                                # If it's pure JSON, it might have a 'message' field
                                data = json.loads(commit_msg)
                                if isinstance(data, dict) and "message" in data:
                                    commit_msg = data["message"]
                                else:
                                    commit_msg = ""
                        except Exception:
                            commit_msg = ""
                    
                    # Remove common system prefixes if any
                    commit_msg = re.sub(r'^.*?commit message:?\s*', '', commit_msg, flags=re.IGNORECASE)
                    commit_msg = commit_msg.strip().split('\n')[0]
                
                # Final fallback if cleaning resulted in empty string
                if not commit_msg or len(commit_msg.strip()) < 5:
                    commit_msg = f"RALPH Loop: Implementation iteration {iteration}"

                subprocess.run(["git", "add", "."], check=True)
                subprocess.run(["git", "commit", "-m", commit_msg], check=True)
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

        # Check if plan is finished
        plan_content = get_file_content(PLAN_FILE)
        if "[ ]" not in plan_content and "todo" not in plan_content.lower():
            log_message("🎉 All tasks in the plan are completed! Checking if PRD is fully implemented...")
            
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
                    f"Analyze the current state of implementation relative to {prd_path}. "
                    "1. Summarize how much of the PRD is implemented (percentage and key features).\n"
                    "2. Identify exactly what is missing to reach 100% completion.\n"
                    "3. Recommend the final set of steps to achieve full implementation.\n"
                    "Output this analysis as a markdown report in 'FINAL_ANALYSIS.md'."
                )
                run_cursor_agent(analysis_prompt)
                break
            else:
                log_message("🔄 PRD is not fully implemented. Re-planning...")
                continue

    if iteration >= MAX_ITERATIONS:
        print(f"Reached maximum iterations ({MAX_ITERATIONS}). Stopping.")


if __name__ == "__main__":
    main()
