import subprocess
import json
import os
import re
import requests
from typing import List, Dict, Any, Optional

class CommitEvaluator:
    """
    Evaluates the value of git commits based on heuristics and optional LLM analysis.
    """

    def __init__(self, model: str = "gemini-2.0-flash", use_llm: bool = False):
        self.model = model
        self.use_llm = use_llm
        self.api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

    def get_commits(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Fetch recent commits with their metadata."""
        cmd = ["git", "log", f"-n {limit}", "--pretty=format:%H|%an|%ad|%s"]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            commits = []
            for line in result.stdout.splitlines():
                parts = line.split("|")
                if len(parts) == 4:
                    commits.append({
                        "hash": parts[0],
                        "author": parts[1],
                        "date": parts[2],
                        "subject": parts[3]
                    })
            return commits
        except subprocess.CalledProcessError:
            return []

    def get_commit_diff_stats(self, commit_hash: str) -> Dict[str, Any]:
        """Get line change statistics for a commit."""
        cmd = ["git", "show", "--numstat", "--format=", commit_hash]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            added = 0
            deleted = 0
            files_changed = 0
            file_types = {}

            for line in result.stdout.splitlines():
                parts = line.split()
                if len(parts) >= 3:
                    try:
                        a = int(parts[0]) if parts[0] != "-" else 0
                        d = int(parts[1]) if parts[1] != "-" else 0
                        added += a
                        deleted += d
                        files_changed += 1
                        
                        ext = os.path.splitext(parts[2])[1] or "no_ext"
                        file_types[ext] = file_types.get(ext, 0) + 1
                    except ValueError:
                        continue

            return {
                "added": added,
                "deleted": deleted,
                "total_changes": added + deleted,
                "files_changed": files_changed,
                "file_types": file_types
            }
        except subprocess.CalledProcessError:
            return {"added": 0, "deleted": 0, "total_changes": 0, "files_changed": 0, "file_types": {}}

    def calculate_heuristic_score(self, stats: Dict[str, Any], subject: str) -> float:
        """
        Calculate a value score based on heuristics:
        - Complexity (number of files and lines)
        - Meaningfulness of the subject (length, keywords)
        - File types (code vs docs/config)
        """
        score = 0.0
        
        # 1. Volume of changes (logarithmic to avoid over-rewarding massive churn)
        import math
        total_changes = stats.get("total_changes", 0)
        if total_changes > 0:
            score += math.log10(total_changes + 1) * 2.0

        # 2. File diversity
        files_changed = stats.get("files_changed", 0)
        score += min(files_changed, 10) * 0.5

        # 3. Subject quality
        subject_len = len(subject)
        if 10 < subject_len < 70:
            score += 1.0
        
        # Keywords that suggest value
        val_keywords = ["fix", "feat", "refactor", "implement", "add", "optimize", "improve"]
        if any(kw in subject.lower() for kw in val_keywords):
            score += 1.5
            
        # 4. File type weighting
        file_types = stats.get("file_types", {})
        for ext, count in file_types.items():
            if ext in [".py", ".ts", ".js", ".go", ".rs", ".java", ".cpp"]:
                score += count * 1.0  # Logic changes
            elif ext in [".md", ".txt"]:
                score += count * 0.2  # Documentation
            elif ext in [".json", ".yaml", ".yml"]:
                score += count * 0.5  # Configuration

        return round(score, 2)

    def get_llm_evaluation(self, commit: Dict[str, Any], stats: Dict[str, Any]) -> str:
        """Use Gemini Flash to evaluate the semantic value of a commit."""
        if not self.use_llm or not self.api_key:
            return "LLM evaluation skipped."

        # Get the actual diff for better context
        try:
            diff = subprocess.run(
                ["git", "show", "--format=", "--unified=1", commit["hash"]],
                capture_output=True, text=True, check=True
            ).stdout[:3000] # Limit context
        except:
            diff = "Diff unavailable"

        prompt = (
            f"Analyze the following git commit and evaluate its value to the system on a scale of 1-10.\n"
            f"Commit Subject: {commit['subject']}\n"
            f"Stats: {json.dumps(stats)}\n"
            f"Diff Snippet:\n{diff}\n\n"
            "Provide a brief 1-sentence justification and a score (Value: X/10)."
        )

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        headers = {"Content-Type": "application/json"}
        data = {"contents": [{"parts": [{"text": prompt}]}]}

        try:
            response = requests.post(url, headers=headers, json=data, timeout=15)
            if response.status_code == 200:
                result = response.json()
                return result["candidates"][0]["content"]["parts"][0]["text"].strip()
            return f"LLM Error: {response.status_code}"
        except Exception as e:
            return f"LLM Exception: {str(e)}"

    def evaluate_history(self, limit: int = 20):
        """Evaluate and print the value of recent commits."""
        commits = self.get_commits(limit)
        print(f"{'Hash':<10} | {'Score':<6} | {'Subject':<50} | {'Analysis'}")
        print("-" * 120)
        
        for c in commits:
            stats = self.get_commit_diff_stats(c["hash"])
            h_score = self.calculate_heuristic_score(stats, c["subject"])
            
            if self.use_llm:
                analysis = self.get_llm_evaluation(c, stats)
            else:
                # Heuristic summary
                analysis = f"Files: {stats['files_changed']}, Changes: {stats['total_changes']}"
            
            print(f"{c['hash'][:8]:<10} | {h_score:<6} | {c['subject'][:50]:<50} | {analysis}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--llm", action="store_true", help="Use Gemini Flash for evaluation")
    args = parser.parse_args()

    evaluator = CommitEvaluator(use_llm=args.llm)
    evaluator.evaluate_history(limit=args.limit)
