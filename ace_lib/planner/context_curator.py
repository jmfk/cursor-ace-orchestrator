import os
import subprocess
from typing import List, Dict, Any, Optional
from .gemini_client import GeminiClient
from .plan_tree import PlanTree, PlanNode

class ContextCurator:
    """
    Uses GeminiClient to analyze repo and select relevant files/snippets for cursor-agent prompts.
    """
    def __init__(self, gemini_client: GeminiClient):
        self.gemini_client = gemini_client

    def _get_repo_structure(self) -> str:
        """Gets a directory listing of the repo, excluding common ignored directories."""
        try:
            # Use git ls-files for a clean listing of tracked files
            res = subprocess.run(["git", "ls-files"], capture_output=True, text=True)
            if res.returncode == 0:
                return res.stdout
            else:
                # Fallback to a simple directory listing if not a git repo
                structure = []
                for root, dirs, files in os.walk("."):
                    # Skip common ignored dirs
                    dirs[:] = [d for d in dirs if d not in [".git", ".venv", "node_modules", "__pycache__", ".ace"]]
                    for file in files:
                        structure.append(os.path.join(root, file))
                return "\n".join(structure)
        except Exception:
            return "Could not determine repo structure."

    def select_context(self, node: PlanNode, tree: PlanTree) -> str:
        """
        Selects relevant files and builds a context prompt for the given node.
        """
        repo_structure = self._get_repo_structure()
        
        # Get ancestors for hierarchical context
        ancestors = tree.get_ancestors(node.id)
        ancestor_context = ""
        if ancestors:
            ancestor_context = "Parent Tasks:\n"
            for anc in reversed(ancestors):
                ancestor_context += f"- {anc.title}: {anc.description}\n"
        
        # Ask Gemini to select relevant files
        node_dict = node.to_dict()
        node_dict["ancestor_context"] = ancestor_context
        
        relevant_files = self.gemini_client.select_context(node_dict, repo_structure)
        
        # Build the final context string for cursor-agent
        context_str = f"Current Task: {node.title}\n"
        context_str += f"Description: {node.description}\n"
        if ancestor_context:
            context_str += ancestor_context
            
        if relevant_files:
            context_str += "\nRelevant Files to consider:\n"
            for file in relevant_files:
                context_str += f"- {file}\n"
                
        return context_str

    def select_context_for_prd(self, prd_path: str) -> str:
        """Selects context for the initial PRD decomposition."""
        repo_structure = self._get_repo_structure()
        
        # Read PRD content
        prd_content = ""
        if os.path.exists(prd_path):
            with open(prd_path, "r", encoding="utf-8") as f:
                prd_content = f.read()
                
        node_dict = {
            "id": "root",
            "title": "Initial PRD Decomposition",
            "description": f"Decomposing PRD: {prd_path}",
            "prd_content": prd_content
        }
        
        relevant_files = self.gemini_client.select_context(node_dict, repo_structure)
        
        context_str = f"PRD Path: {prd_path}\n"
        context_str += f"PRD Content Summary: {prd_content[:500]}...\n"
        
        if relevant_files:
            context_str += "\nRelevant Files to consider:\n"
            for file in relevant_files:
                context_str += f"- {file}\n"
                
        return context_str
