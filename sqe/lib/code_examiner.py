import os
import json
import subprocess
from typing import List, Dict, Any, Optional
from .gemini_client import GeminiClient
from .context_curator import ContextCurator

class CodeExaminer:
    """
    Analyzes existing code against PRD requirements and maps requirements to code.
    """
    def __init__(self, model_name: str = "gemini-3-flash-preview"):
        self.client = GeminiClient(model_name=model_name, memory_path=".ace/sqe_memory.jsonl")
        self.curator = ContextCurator(self.client)

    def examine(self, decomposition: Dict[str, Any]) -> Dict[str, Any]:
        """
        Maps requirements to code and evaluates implementation quality.
        """
        repo_structure = self.curator._get_repo_structure()
        
        # Flatten requirements for easier processing
        flat_requirements = self._flatten_requirements(decomposition.get("requirements", []))
        
        results = []
        for req in flat_requirements:
            # Ensure the prefix is SQE if it was ACE in the PRD
            req_id = req['id']
            print(f"Examining requirement: {req_id} - {req['title']}", flush=True)
            
            # Select relevant context for this requirement
            context_prompt = f"Requirement: {req['title']}\nDescription: {req['description']}\nSuccess Criteria: {', '.join(req.get('success_criteria', []))}"
            
            # We need a dummy node for select_context
            from .plan_tree import PlanNode
            dummy_node = PlanNode(id=req['id'], title=req['title'], description=req['description'])
            
            # Use curator to find relevant files
            # Note: select_context expects a PlanTree, but we can pass a mock or just use the logic
            relevant_files = self.client.select_context(dummy_node.to_dict(), repo_structure)
            
            # Read the content of relevant files
            code_snippets = ""
            for file_path in relevant_files:
                if os.path.exists(file_path):
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()
                        # Limit snippet size
                        if len(content) > 5000:
                            content = content[:5000] + "\n... [truncated] ..."
                        code_snippets += f"\n--- File: {file_path} ---\n{content}\n"

            # Evaluate the implementation of this requirement
            evaluation_prompt = f"""
Evaluate the implementation of the following requirement based on the provided code snippets.

Requirement: {req['title']}
Description: {req['description']}
Success Criteria: {', '.join(req.get('success_criteria', []))}

Code Snippets:
{code_snippets}

Tasks:
1. Determine if the requirement is implemented (Full/Partial/None).
2. Rate the implementation quality (0-100).
3. Identify which files and functions implement this requirement.
4. Provide a brief analysis of the implementation quality and any gaps.

Return the result as a JSON object:
{{
  "requirement_id": "{req['id']}",
  "status": "string",
  "quality_score": number,
  "mapped_files": ["string"],
  "analysis": "string",
  "gaps": ["string"]
}}
"""
            response_text = self.client._call_gemini(evaluation_prompt, "You are a senior code reviewer and quality evaluator.")
            
            try:
                json_str = response_text.strip()
                if "```json" in json_str:
                    json_str = json_str.split("```json")[1].split("```")[0].strip()
                elif "```" in json_str:
                    json_str = json_str.split("```")[1].split("```")[0].strip()
                
                eval_result = json.loads(json_str)
                results.append(eval_result)
            except Exception as e:
                results.append({
                    "requirement_id": req['id'],
                    "error": f"Failed to parse evaluation: {str(e)}",
                    "raw_response": response_text
                })

        return {
            "project_name": decomposition.get("project_name"),
            "evaluations": results
        }

    def _flatten_requirements(self, requirements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Flattens a hierarchical requirements list."""
        flat = []
        for req in requirements:
            flat.append(req)
            if "sub_requirements" in req:
                flat.extend(self._flatten_requirements(req["sub_requirements"]))
        return flat

    def save_examination(self, results: Dict[str, Any], output_path: str):
        """Saves the examination results to a JSON file."""
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
