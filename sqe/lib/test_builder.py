import os
import json
import subprocess
from typing import List, Dict, Any, Optional
from .gemini_client import GeminiClient
from .context_curator import ContextCurator

class TestBuilder:
    """
    Generates and manages evaluation tests based on PRD requirements and success criteria.
    """
    def __init__(self, model_name: str = "gemini-3-flash-preview"):
        self.client = GeminiClient(model_name=model_name, memory_path=".ace/sqe_memory.jsonl")
        self.curator = ContextCurator(self.client)
        self.test_dir = os.getenv("SQE_TEST_DIR", "tests/sqe")

    def build_tests(self, decomposition: Dict[str, Any], examination: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generates automated tests for each requirement.
        """
        repo_structure = self.curator._get_repo_structure()
        
        # Flatten requirements for easier processing
        flat_requirements = self._flatten_requirements(decomposition.get("requirements", []))
        
        test_results = []
        for req in flat_requirements:
            # Ensure the prefix is SQE if it was ACE in the PRD
            req_id = req['id'].replace('ACE-', 'SQE-')
            print(f"Building tests for requirement: {req_id} - {req['title']}", flush=True)
            
            # Find the evaluation result for this requirement
            eval_result = next((e for e in examination.get("evaluations", []) if e.get("requirement_id") == req['id']), {})
            
            # Select relevant context for this requirement
            context_prompt = f"Requirement: {req['title']}\nDescription: {req['description']}\nSuccess Criteria: {', '.join(req.get('success_criteria', []))}"
            
            # Use curator to find relevant files
            from .plan_tree import PlanNode
            dummy_node = PlanNode(id=req['id'], title=req['title'], description=req['description'])
            relevant_files = self.client.select_context(dummy_node.to_dict(), repo_structure)
            
            # Read the content of relevant files
            code_snippets = ""
            for file_path in relevant_files:
                if os.path.exists(file_path):
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()
                        if len(content) > 5000:
                            content = content[:5000] + "\n... [truncated] ..."
                        code_snippets += f"\n--- File: {file_path} ---\n{content}\n"

            # Generate a test for this requirement
            test_prompt = f"""
Generate a Python test file (using pytest) to verify the implementation of the following requirement.

Requirement: {req['title']}
Description: {req['description']}
Success Criteria: {', '.join(req.get('success_criteria', []))}

Existing Code Context:
{code_snippets}

Tasks:
1. Generate a complete, standalone pytest file that tests this requirement.
2. The test should be as realistic as possible, mocking external dependencies if necessary.
3. Include comments explaining what each test case verifies.

Return the result as a JSON object:
{{
  "requirement_id": "{req['id']}",
  "test_filename": "test_{req['id'].lower().replace('-', '_')}.py",
  "test_code": "string",
  "test_description": "string"
}}
"""
            response_text = self.client._call_gemini(test_prompt, "You are a senior test engineer and quality evaluator.")
            
            try:
                json_str = response_text.strip()
                if "```json" in json_str:
                    json_str = json_str.split("```json")[1].split("```")[0].strip()
                elif "```" in json_str:
                    json_str = json_str.split("```")[1].split("```")[0].strip()
                
                test_data = json.loads(json_str)
                
                # Save the test file
                test_file_path = os.path.join(self.test_dir, test_data["test_filename"])
                os.makedirs(os.path.dirname(test_file_path), exist_ok=True)
                with open(test_file_path, "w", encoding="utf-8") as f:
                    f.write(test_data["test_code"])
                
                test_data["test_file_path"] = test_file_path
                test_results.append(test_data)
            except Exception as e:
                test_results.append({
                    "requirement_id": req['id'],
                    "error": f"Failed to parse test generation: {str(e)}",
                    "raw_response": response_text
                })

        return {
            "project_name": decomposition.get("project_name"),
            "tests": test_results
        }

    def run_tests(self, test_results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes the generated tests and captures results.
        """
        results = []
        for test in test_results.get("tests", []):
            if "test_file_path" not in test:
                continue
            
            test_file = test["test_file_path"]
            print(f"Running test: {test_file}", flush=True)
            
            try:
                # Run pytest on the generated test file
                res = subprocess.run(["pytest", test_file, "--json-report", "--json-report-file=sqe/data/last_test_report.json"], capture_output=True, text=True)
                
                # Capture results
                test_run_result = {
                    "requirement_id": test["requirement_id"],
                    "test_file": test_file,
                    "exit_code": res.returncode,
                    "stdout": res.stdout,
                    "stderr": res.stderr,
                    "passed": res.returncode == 0
                }
                results.append(test_run_result)
            except Exception as e:
                results.append({
                    "requirement_id": test["requirement_id"],
                    "test_file": test_file,
                    "error": str(e),
                    "passed": False
                })

        return {
            "project_name": test_results.get("project_name"),
            "test_run_results": results
        }

    def _flatten_requirements(self, requirements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Flattens a hierarchical requirements list."""
        flat = []
        for req in requirements:
            flat.append(req)
            if "sub_requirements" in req:
                flat.extend(self._flatten_requirements(req["sub_requirements"]))
        return flat

    def save_test_results(self, results: Dict[str, Any], output_path: str):
        """Saves the test results to a JSON file."""
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
