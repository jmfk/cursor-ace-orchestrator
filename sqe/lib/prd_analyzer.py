import os
import json
import re
from typing import List, Dict, Any, Optional
from .gemini_client import GeminiClient

class PRDAnalyzer:
    """
    Decomposes a PRD into a hierarchical structure of requirements and success criteria.
    """
    def __init__(self, model_name: str = "gemini-3-flash-preview"):
        self.client = GeminiClient(model_name=model_name, memory_path=".ace/sqe_memory.jsonl")

    def analyze(self, prd_path: str) -> Dict[str, Any]:
        """
        Reads the PRD and returns a structured decomposition.
        """
        if not os.path.exists(prd_path):
            raise FileNotFoundError(f"PRD not found at {prd_path}")

        with open(prd_path, "r", encoding="utf-8") as f:
            prd_content = f.read()

        prompt = f"""
Analyze the following Product Requirements Document (PRD) and decompose it into a hierarchical structure of requirements.
For each requirement, identify specific "Success Criteria" that can be used to evaluate if the requirement is met.

PRD Content:
{prd_content}

Return the result as a JSON object with the following structure:
{{
  "project_name": "string",
  "overview": "string",
  "requirements": [
    {{
      "id": "REQ-001",
      "title": "Requirement Title",
      "description": "Detailed description",
      "priority": "High/Medium/Low",
      "success_criteria": [
        "Criterion 1",
        "Criterion 2"
      ],
      "sub_requirements": []
    }}
  ]
}}
"""
        response_text = self.client._call_gemini(prompt, "You are a senior system architect and quality evaluator.")
        
        try:
            # Clean up markdown if present
            json_str = response_text.strip()
            if "```json" in json_str:
                json_str = json_str.split("```json")[1].split("```")[0].strip()
            elif "```" in json_str:
                json_str = json_str.split("```")[1].split("```")[0].strip()
            
            decomposition = json.loads(json_str)
            return decomposition
        except Exception as e:
            return {
                "error": f"Failed to parse PRD decomposition: {str(e)}",
                "raw_response": response_text
            }

    def save_decomposition(self, decomposition: Dict[str, Any], output_path: str):
        """Saves the decomposition to a JSON file."""
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(decomposition, f, indent=2)
