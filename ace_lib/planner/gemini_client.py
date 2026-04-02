import os
import json
import time
from datetime import datetime
from typing import List, Dict, Any, Optional
import google.generativeai as genai
from pathlib import Path

class GeminiClient:
    """
    LLM wrapper for Gemini with local JSONL memory for reasoning traces.
    """
    def __init__(self, model_name: str, memory_path: str = ".ralph/planner_memory.jsonl"):
        self.model_name = model_name
        self.memory_path = Path(memory_path)
        self.memory_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Configure Gemini
        api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if not api_key:
            # Fallback to checking ~/.ace/credentials as seen in test_gemini_3_flash_preview.py
            cred_file = Path.home() / ".ace" / "credentials"
            if cred_file.exists():
                for line in cred_file.read_text(encoding="utf-8").splitlines():
                    if line.startswith("GOOGLE_API_KEY="):
                        api_key = line.split("=", 1)[1].strip()
                        break
        
        if not api_key:
            raise ValueError("GOOGLE_API_KEY or GEMINI_API_KEY not found in environment or ~/.ace/credentials")
            
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(model_name)

    def record_reasoning(self, role: str, action: str, node_id: str, input_summary: str, output: str, reasoning: str):
        """Appends a reasoning trace to the JSONL memory file."""
        entry = {
            "ts": datetime.now().isoformat(),
            "role": role,
            "action": action,
            "node_id": node_id,
            "input_summary": input_summary,
            "output": output,
            "reasoning": reasoning
        }
        with open(self.memory_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def _get_relevant_memory(self, node_id: str, limit: int = 20) -> str:
        """Loads last N relevant memory entries filtered by node lineage (prefix matching)."""
        if not self.memory_path.exists():
            return "No prior memory."
            
        relevant = []
        try:
            with open(self.memory_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
                # Search backwards for relevance
                for line in reversed(lines):
                    if len(relevant) >= limit:
                        break
                    entry = json.loads(line)
                    # Simple prefix matching for node lineage (e.g. 0001_001 matches 0001)
                    if node_id.startswith(entry.get("node_id", "")) or entry.get("node_id", "").startswith(node_id):
                        relevant.append(entry)
        except Exception:
            return "Error reading memory."
            
        if not relevant:
            return "No relevant prior memory for this node lineage."
            
        memory_str = "Prior relevant reasoning traces:\n"
        for entry in reversed(relevant):
            memory_str += f"- [{entry['ts']}] Action: {entry['action']} on Node: {entry['node_id']}\n"
            memory_str += f"  Reasoning: {entry['reasoning']}\n"
            memory_str += f"  Output: {entry['output'][:200]}...\n"
        return memory_str

    def _call_gemini(self, prompt: str, system_instruction: Optional[str] = None) -> str:
        """Internal helper to call Gemini API."""
        # Note: system_instruction is supported in newer GenerativeModel versions
        # If not supported, we prepend it to the prompt.
        try:
            if system_instruction:
                # Some versions of the SDK use system_instruction in the constructor
                # For simplicity and compatibility, we'll use it in the prompt if needed
                full_prompt = f"SYSTEM INSTRUCTION:\n{system_instruction}\n\nUSER PROMPT:\n{prompt}"
            else:
                full_prompt = prompt
                
            response = self.model.generate_content(full_prompt)
            return response.text
        except Exception as e:
            return f"Error calling Gemini: {str(e)}"

    def validate_plan(self, nodes: List[Dict[str, Any]], context: str) -> Dict[str, Any]:
        """Validates a list of proposed plan nodes against the context."""
        prompt = f"Context: {context}\n\nProposed Plan Nodes: {json.dumps(nodes, indent=2)}\n\nValidate these steps. Are they logical? Do they cover the requirements? Are there bogus or redundant steps? Return a JSON object with 'valid' (bool), 'feedback' (string), and 'reasoning' (string)."
        
        # Inject memory
        node_id = nodes[0].get("parent_id", "root") if nodes else "root"
        memory = self._get_relevant_memory(node_id)
        system_instruction = f"You are a plan validator for the RALPH hierarchical planner. {memory}"
        
        response_text = self._call_gemini(prompt, system_instruction)
        
        # Attempt to parse JSON from response
        try:
            # Simple cleanup in case of markdown blocks
            json_str = response_text.strip()
            if "```json" in json_str:
                json_str = json_str.split("```json")[1].split("```")[0].strip()
            elif "```" in json_str:
                json_str = json_str.split("```")[1].split("```")[0].strip()
            result = json.loads(json_str)
        except Exception:
            result = {"valid": False, "feedback": "Failed to parse validator response", "reasoning": response_text}
            
        self.record_reasoning("validator", "validate", node_id, f"Validating {len(nodes)} nodes", str(result.get("valid")), result.get("reasoning", ""))
        return result

    def is_actionable(self, node: Dict[str, Any]) -> bool:
        """Determines if a node is actionable or needs further decomposition."""
        prompt = f"Plan Node: {json.dumps(node, indent=2)}\n\nIs this task 'actionable' (can be implemented in one go by a coding agent) or does it need to be decomposed into smaller sub-steps? Return a JSON object with 'actionable' (bool) and 'reasoning' (string)."
        
        memory = self._get_relevant_memory(node.get("id", "unknown"))
        system_instruction = f"You are a task analyzer for the RALPH hierarchical planner. {memory}"
        
        response_text = self._call_gemini(prompt, system_instruction)
        
        try:
            json_str = response_text.strip()
            if "```json" in json_str:
                json_str = json_str.split("```json")[1].split("```")[0].strip()
            result = json.loads(json_str)
            actionable = result.get("actionable", False)
        except Exception:
            actionable = False
            result = {"reasoning": response_text}
            
        self.record_reasoning("analyzer", "is_actionable", node.get("id", "unknown"), f"Checking node {node.get('id')}", str(actionable), result.get("reasoning", ""))
        return actionable

    def select_context(self, node: Dict[str, Any], repo_structure: str) -> List[str]:
        """Selects relevant files and context for a given node."""
        prompt = f"Plan Node: {json.dumps(node, indent=2)}\n\nRepo Structure:\n{repo_structure}\n\nBased on the task, which files are most relevant to read or modify? Return a JSON list of file paths."
        
        memory = self._get_relevant_memory(node.get("id", "unknown"))
        system_instruction = f"You are a context curator for the RALPH hierarchical planner. {memory}"
        
        response_text = self._call_gemini(prompt, system_instruction)
        
        try:
            json_str = response_text.strip()
            if "```json" in json_str:
                json_str = json_str.split("```json")[1].split("```")[0].strip()
            result = json.loads(json_str)
            if not isinstance(result, list):
                result = []
        except Exception:
            result = []
            
        self.record_reasoning("curator", "select_context", node.get("id", "unknown"), f"Selecting context for {node.get('id')}", f"Selected {len(result)} files", "LLM selection")
        return result
