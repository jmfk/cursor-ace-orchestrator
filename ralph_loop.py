import os
import subprocess
import sys
import time
from pathlib import Path

# Configuration
MODEL = "gemini-3-flash"
MAX_ITERATIONS = 5
PLAN_FILE = "plan.md"
CHANGELOG_FILE = "changelog.md"

def run_cursor_agent(prompt: str):
    """Runs cursor-agent in headless mode with the specified prompt."""
    print(f"\n--- Running Cursor Agent ({MODEL}) ---")
    print(f"Prompt: {prompt[:100]}...")
    
    # Construct the command for cursor-agent headless
    # Note: Adjust the command based on actual cursor-agent CLI availability
    cmd = [
        "cursor-agent",
        "headless",
        "--model", MODEL,
        "--prompt", prompt
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return result.stdout
    except subprocess.CalledProcessError as e:
        print(f"Error running cursor-agent: {e.stderr}")
        return None

def get_file_content(path: str):
    if os.path.exists(path):
        with open(path, "r") as f:
            return f.read()
    return ""

def main():
    print("🚀 Starting RALPH Loop for Cursor ACE Orchestrator...")
    
    iteration = 0
    while iteration < MAX_ITERATIONS:
        iteration += 1
        print(f"\n=== Iteration {iteration}/{MAX_ITERATIONS} ===")

        # Step 1: Planning (if plan.md doesn't exist or needs update)
        plan_content = get_file_content(PLAN_FILE)
        if not plan_content:
            print("Step 1: Planning...")
            prompt = (
                "Based on the PRDs (PRD-01, PRD-02) and SPECS.md, create a detailed, sorted list of implementation steps "
                "for the Cursor ACE Orchestrator. The system should be built in Python, supporting CLI first but "
                "architected for FastAPI later. Save the plan as 'plan.md' as a sorted list of tasks."
            )
            run_cursor_agent(prompt)
            plan_content = get_file_content(PLAN_FILE)
            if not plan_content:
                print("Failed to create plan.md. Retrying...")
                continue

        # Step 2: Build next step
        print("Step 2: Building next task...")
        prompt = (
            f"Current plan:\n{plan_content}\n\n"
            "Implement the next (first uncompleted) task from the plan. "
            "Include necessary tests. Ensure the software remains runnable and testable. "
            "Use Python and follow the architecture described in the PRDs."
        )
        run_cursor_agent(prompt)

        # Step 3: Verify (Tests, Lint, Run)
        print("Step 3: Verifying implementation...")
        prompt = (
            "Run all tests, linter, and verify that the software is runnable. "
            "If there are any failures, fix them immediately. "
            "Do not proceed until all tests pass and the code is clean."
        )
        verification_result = run_cursor_agent(prompt)
        
        # Step 4: Commit
        print("Step 4: Committing changes...")
        try:
            subprocess.run(["git", "add", "."], check=True)
            # Try to get the task name for the commit message
            commit_msg = f"RALPH Loop: Implementation iteration {iteration}"
            subprocess.run(["git", "commit", "-m", commit_msg], check=True)
            subprocess.run(["git", "push"], check=True)
        except subprocess.CalledProcessError as e:
            print(f"Git operation failed: {e}")

        # Step 5: Update Plan and Changelog
        print("Step 5: Updating plan and changelog...")
        prompt = (
            f"Update '{PLAN_FILE}' by marking the completed task as done and keeping the list sorted. "
            f"Write the completed task details to '{CHANGELOG_FILE}'. "
            "Ensure the plan reflects what is left to do."
        )
        run_cursor_agent(prompt)

        print(f"Iteration {iteration} complete.")
        
        # Check if plan is finished
        plan_content = get_file_content(PLAN_FILE)
        if "[ ]" not in plan_content and "todo" not in plan_content.lower():
            print("🎉 All tasks in the plan are completed!")
            break

    if iteration >= MAX_ITERATIONS:
        print(f"Reached maximum iterations ({MAX_ITERATIONS}). Stopping.")

if __name__ == "__main__":
    main()
