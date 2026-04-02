import os
import json
import re
from typing import List, Dict, Any, Optional, Callable
from .gemini_client import GeminiClient
from .plan_tree import PlanTree, PlanNode
from .context_curator import ContextCurator

class HierarchicalPlanner:
    """
    Orchestrates the hierarchical planning and execution loop.
    """
    def __init__(
        self,
        prd_path: str,
        run_cursor_agent_fn: Callable[[str, str], Optional[str]],
        planner_model: str,
        validator_model: str,
        context_model: str,
        executor_model: str,
        max_retries: int = 3
    ):
        self.prd_path = prd_path
        self.run_cursor_agent = run_cursor_agent_fn
        self.planner_model = planner_model
        self.executor_model = executor_model
        self.max_retries = max_retries
        
        # Stagnation monitoring
        self.last_node_id = None
        self.node_visit_count = 0
        self.max_node_visits = 3
        
        self.validator = GeminiClient(model_name=validator_model)
        self.curator = ContextCurator(GeminiClient(model_name=context_model))
        self.tree = PlanTree.load_or_create(prd_path)
        
        # Purge placeholders on startup
        self.tree.purge_placeholders()

    def parse_plan_output(self, output: str) -> List[Dict[str, Any]]:
        """Parses a list of plan nodes from cursor-agent output."""
        # Look for JSON block or a simple list
        tasks = []
        try:
            # Try to find a JSON block
            json_match = re.search(r"```json\n(.*?)\n```", output, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(1))
                if isinstance(data, list):
                    tasks = data
                elif isinstance(data, dict) and "tasks" in data:
                    tasks = data["tasks"]
            
            if not tasks:
                # Fallback to a simpler regex for - [ ] tasks
                for line in output.splitlines():
                    if "- [ ]" in line:
                        title = line.replace("- [ ]", "").strip()
                        tasks.append({"title": title, "description": ""})
            
            # Filter out garbage nodes (JSON-like titles, tool calls, or extremely long titles)
            valid_tasks = []
            for task in tasks:
                title = str(task.get("title", ""))
                # Filter out JSON-like titles or extremely long titles
                if title.startswith("{") or title.startswith("[") or len(title) > 200 or not title:
                    continue
                valid_tasks.append(task)
            return valid_tasks
        except Exception:
            return []

    def exit_with_analysis(self, reason: str):
        """Analyzes the failure and exits the loop."""
        print(f"\n🛑 EXITING: {reason}")
        
        # Get the current node
        node = self.tree.get_next_incomplete()
        node_info = json.dumps(node.to_dict(), indent=2) if node else "No active node"
        
        # Get the last few lines of the log
        log_content = ""
        log_file = "ralph_execution.log"
        if os.path.exists(log_file):
            try:
                with open(log_file, "r") as f:
                    lines = f.readlines()
                    log_content = "".join(lines[-50:])
            except Exception:
                log_content = "Could not read log file."
        
        prompt = (
            f"The RALPH hierarchical planner has STAGNATED and is exiting.\n"
            f"Reason: {reason}\n\n"
            f"Current Node State:\n{node_info}\n\n"
            f"Last 50 lines of Execution Log:\n{log_content}\n\n"
            f"Analyze why the planner is stuck. Is it a parsing issue? A model failure? "
            f"A bad task description? Suggest a specific fix or manual intervention."
        )
        
        # Use the validator model for analysis as it's usually more capable
        print("Generating post-mortem analysis...")
        analysis = self.validator._call_gemini(prompt, "You are a senior systems architect analyzing a failure in an autonomous agent loop.")
        
        print("\n--- POST-MORTEM ANALYSIS ---")
        print(analysis)
        print("----------------------------\n")
        
        import sys
        sys.exit(1)

    def run(self):
        """Main loop for hierarchical planning and execution."""
        if self.tree.is_empty():
            plan_md_path = "plan.md"
            if os.path.exists(plan_md_path):
                print(f"Migrating existing flat plan from {plan_md_path}...")
                with open(plan_md_path, "r", encoding="utf-8") as f:
                    content = f.read()
                self.tree.ingest_flat_plan(content)
            else:
                print(f"Step 0: Initial PRD decomposition for {self.prd_path}...")
                context = self.curator.select_context_for_prd(self.prd_path)
                prompt = (
                    f"Decompose the following PRD into high-level implementation phases.\n"
                    f"PRD: {self.prd_path}\n"
                    f"Context:\n{context}\n\n"
                    f"Return a JSON list of tasks with 'title' and 'description'."
                )
                output = self.run_cursor_agent(prompt, self.planner_model)
                if output:
                    nodes_data = self.parse_plan_output(output)
                    validation = self.validator.validate_plan(nodes_data, f"PRD: {self.prd_path}")
                    if validation.get("valid", False):
                        self.tree.add_root_nodes(nodes_data)
                    else:
                        print(f"Validation failed: {validation.get('feedback')}")
                        # In a real scenario, we might retry or ask for clarification
                        self.tree.add_root_nodes(nodes_data) # Proceed anyway for now

        while True:
            node = self.tree.get_next_incomplete()
            if not node:
                print("🎉 All tasks in the hierarchical plan are completed!")
                break
                
            # Stagnation monitoring
            if node.id == self.last_node_id:
                self.node_visit_count += 1
            else:
                self.last_node_id = node.id
                self.node_visit_count = 1

            if self.node_visit_count > self.max_node_visits:
                self.exit_with_analysis(f"Stagnation detected: Processed node {node.id} {self.max_node_visits} times without progress.")

            print(f"Processing Node: {node.id} - {node.title}")
            
            if not node.actionable:
                # Check if it's actionable or needs decomposition
                actionable = self.validator.is_actionable(node.to_dict())
                if not actionable:
                    print(f"Decomposing node {node.id}...")
                    context = self.curator.select_context(node, self.tree)
                    prompt = (
                        f"Decompose the following task into smaller, more actionable sub-tasks.\n"
                        f"Task: {node.title}\n"
                        f"Description: {node.description}\n"
                        f"Context:\n{context}\n\n"
                        f"Return a JSON list of sub-tasks with 'title' and 'description'."
                    )
                    output = self.run_cursor_agent(prompt, self.planner_model)
                    if output:
                        sub_nodes_data = self.parse_plan_output(output)
                        if sub_nodes_data:
                            # Check if we actually added children (might fail due to max_depth)
                            before_count = len(node.children)
                            self.tree.add_children(node.id, sub_nodes_data)
                            if len(self.tree.nodes[node.id].children) > before_count:
                                continue # Success, move to first child
                    
                    # If we are here, decomposition failed or hit max_depth
                    print(f"Node {node.id} could not be decomposed further. Marking as actionable.")
                    node.actionable = True
                    self.tree.save_node(node)
                else:
                    node.actionable = True
                    self.tree.save_node(node)

            # Execute actionable node
            print(f"Executing actionable node {node.id}...")
            context = self.curator.select_context(node, self.tree)
            prompt = (
                f"Implement the following task.\n"
                f"Task: {node.title}\n"
                f"Description: {node.description}\n"
                f"Context:\n{context}\n\n"
                f"Follow the PRD: {self.prd_path}"
            )
            
            # This is where the actual implementation happens
            output = self.run_cursor_agent(prompt, self.executor_model)
            
            from .diff_gate import evaluate as evaluate_diff
            diff_result = evaluate_diff()
            
            if diff_result.is_meaningful:
                # After execution, we'd normally verify and commit
                # For the purpose of this orchestration, we mark it complete
                # The actual ralph_loop will handle the git/stats part
                self.tree.mark_complete(node.id)
                print(f"Completed node {node.id} ({len(diff_result.source_files_changed)} source files changed)")
            else:
                node.retry_count = getattr(node, 'retry_count', 0) + 1
                if node.retry_count >= self.max_retries:
                    self.tree.mark_skipped(node.id)
                    print(f"Skipped node {node.id} after {node.retry_count} churn-only attempts")
                else:
                    self.tree.save_node(node)
                    print(f"Rejected churn-only output for {node.id} (attempt {node.retry_count})")

