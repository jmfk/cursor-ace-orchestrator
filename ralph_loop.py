import os
import subprocess
import sys
import time
import json
from datetime import datetime
from pathlib import Path

# Configuration
MODEL = "gemini-3-flash"
MAX_ITERATIONS = 10
PLAN_FILE = "plan.md"
CHANGELOG_FILE = "changelog.md"
LOG_FILE = "ralph_execution.log"
STATS_FILE = "ralph_stats.json"

# NOTE: This script is a temporary bootstrapping tool.
# Once the core ACE Orchestrator is built, this script should be
# manually removed and replaced by the system's own 'ace loop' command.

# Pricing for gemini-3-flash (approximate 2026 pricing)
# $0.10 per 1M input tokens, $0.40 per 1M output tokens
PRICE_INPUT_1M = 0.10
PRICE_OUTPUT_1M = 0.40


def log_message(message: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted_msg = f"[{timestamp}] {message}"
    print(formatted_msg)
    with open(LOG_FILE, "a") as f:
        f.write(formatted_msg + "\n")


def update_stats(input_tokens: int, output_tokens: int, elapsed_time: float):
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

    cost = (input_tokens / 1_000_000 * PRICE_INPUT_1M) + (
        output_tokens / 1_000_000 * PRICE_OUTPUT_1M
    )

    stats["total_input_tokens"] += input_tokens
    stats["total_output_tokens"] += output_tokens
    stats["total_cost_usd"] += cost
    stats["total_time_sec"] += elapsed_time
    stats["iterations"] += 1

    with open(STATS_FILE, "w") as f:
        json.dump(stats, f, indent=2)

    log_message(
        f"Stats Update: +{input_tokens}in, +{output_tokens}out | Cost: ${cost:.6f} | Time: {elapsed_time:.2f}s"
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
        "--model", MODEL,
        "--output-format", "stream-json",
        "--force",
        "--trust",
        prompt
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
    if os.path.exists(path):
        with open(path, "r") as f:
            return f.read()
    return ""


def main():
    log_message("🚀 Starting RALPH Loop for Cursor ACE Orchestrator...")

    iteration = 0
    while iteration < MAX_ITERATIONS:
        iteration += 1
        log_message(f"=== Iteration {iteration}/{MAX_ITERATIONS} ===")

        # Step 1: Planning (if plan.md doesn't exist or needs update)
        plan_content = get_file_content(PLAN_FILE)
        if not plan_content:
            log_message("Step 1: Planning...")
            prompt = (
                "Based on PRD-01 - Cursor-ace-orchestrator-prd.md (primary), PRD-02, and SPECS.md, "
                "create a detailed, sorted list of implementation steps for the Cursor ACE Orchestrator. "
                "The system should be built in Python, supporting CLI first but architected for FastAPI later. "
                "Save the plan as 'plan.md' as a sorted list of tasks."
            )
            run_cursor_agent(prompt)
            plan_content = get_file_content(PLAN_FILE)
            if not plan_content:
                log_message("Failed to create plan.md. Retrying...")
                continue

        # Step 2: Build next step
        log_message("Step 2: Building next task...")
        prompt = (
            f"Current plan:\n{plan_content}\n\n"
            "Implement the next (first uncompleted) task from the plan. "
            "Include necessary tests. Ensure the software remains runnable and testable. "
            "Use Python and follow the architecture described in PRD-01 and ARCHITECTURE.md."
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

        # Step 4: Commit
        log_message("Step 4: Committing changes...")
        try:
            # Check if there are changes to commit
            status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
            if status.stdout.strip():
                subprocess.run(["git", "add", "."], check=True)
                commit_msg = f"RALPH Loop: Implementation iteration {iteration}"
                subprocess.run(["git", "commit", "-m", commit_msg], check=True)
                subprocess.run(["git", "push"], check=True)
            else:
                log_message("No changes to commit.")
        except subprocess.CalledProcessError as e:
            log_message(f"Git operation failed: {e}")

        # Step 5: Update Plan and Changelog
        log_message("Step 5: Updating plan and changelog...")
        prompt = (
            f"Update '{PLAN_FILE}' by marking the completed task as done and keeping the list sorted. "
            f"Write the completed task details to '{CHANGELOG_FILE}'. "
            "Ensure the plan reflects what is left to do."
        )
        run_cursor_agent(prompt)

        log_message(f"Iteration {iteration} complete.")

        # Check if plan is finished
        plan_content = get_file_content(PLAN_FILE)
        if "[ ]" not in plan_content and "todo" not in plan_content.lower():
            print("🎉 All tasks in the plan are completed!")
            break

    if iteration >= MAX_ITERATIONS:
        print(f"Reached maximum iterations ({MAX_ITERATIONS}). Stopping.")


if __name__ == "__main__":
    main()
