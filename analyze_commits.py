import subprocess
import os
import re
import json
from typing import List, Dict, Any, Optional
from datetime import datetime
from pathlib import Path
import google.generativeai as genai
from dotenv import load_dotenv

# Try to import matplotlib for PNG generation
try:
    import matplotlib.pyplot as plt
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

class CommitAnalyzer:
    """
    Analyzes git commits using gemini-3-flash-preview to measure feature improvements.
    Looks at plan.md and changelog.md changes in each commit.
    Calculates line change stats excluding specific files.
    Generates a markdown report with a graph.
    Optionally replaces old git messages with better ones.
    """

    EXCLUDED_FILES = {
        "ralph_execution.log",
        "ralph_loop.py",
        "ralph_state_history.json",
        "ralph_stats.json"
    }

    # Cost configuration (USD per 1M tokens)
    INPUT_COST_PER_1M = 0.25
    OUTPUT_COST_PER_1M = 1.50

    def __init__(self, model: str = "gemini-3-flash-preview"):
        load_dotenv()
        self.model_name = model
        self.api_key = self._get_api_key()
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_cost = 0.0
        if self.api_key:
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel(self.model_name)
        else:
            self.model = None
            print("⚠️ Warning: GOOGLE_API_KEY not found. LLM features will be disabled.")

    def _get_api_key(self) -> Optional[str]:
        api_key: Optional[str] = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            cred_file = Path.home() / ".ace" / "credentials"
            if cred_file.exists():
                for line in cred_file.read_text(encoding="utf-8").splitlines():
                    if line.startswith("GOOGLE_API_KEY="):
                        return line.split("=", 1)[1].strip()
        return api_key

    def get_commits(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Fetch recent commits."""
        cmd = ["git", "log", "--pretty=format:%H|%an|%ad|%s", "-n", str(limit)]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            commits: List[Dict[str, Any]] = []
            for line in result.stdout.splitlines():
                parts = line.split("|")
                if len(parts) >= 4:
                    commits.append({
                        "hash": parts[0],
                        "author": parts[1],
                        "date": parts[2],
                        "subject": "|".join(parts[3:])
                    })
            return commits
        except subprocess.CalledProcessError:
            return []

    def get_commit_details(self, commit_hash: str) -> Dict[str, Any]:
        """Get diff stats and specific file changes (plan.md, changelog.md)."""
        # Stats
        cmd_stats = ["git", "show", "--numstat", "--format=", commit_hash]
        stats: Dict[str, int] = {"added": 0, "deleted": 0, "files": 0}
        
        try:
            res_stats = subprocess.run(cmd_stats, capture_output=True, text=True, check=True)
            for line in res_stats.stdout.splitlines():
                parts = line.split()
                if len(parts) >= 3:
                    filename = parts[2]
                    if any(ex in filename for ex in self.EXCLUDED_FILES):
                        continue
                    try:
                        a = int(parts[0]) if parts[0] != "-" else 0
                        d = int(parts[1]) if parts[1] != "-" else 0
                        stats["added"] += a
                        stats["deleted"] += d
                        stats["files"] += 1
                    except ValueError:
                        continue
        except subprocess.CalledProcessError:
            pass

        # File contents (plan.md, changelog.md)
        files_content: Dict[str, str] = {}
        for target in ["plan.md", "changelog.md"]:
            cmd_file = ["git", "show", f"{commit_hash}:{target}"]
            try:
                res_file = subprocess.run(cmd_file, capture_output=True, text=True)
                if res_file.returncode == 0:
                    files_content[target] = res_file.stdout
            except Exception:
                pass

        return {"stats": stats, "files": files_content}

    def analyze_improvement(self, commit: Dict[str, Any], details: Dict[str, Any]) -> Dict[str, Any]:
        """Use Gemini to measure improvement and suggest a better commit message."""
        if not self.model:
            return {"improvement_score": 0, "suggested_message": commit["subject"], "analysis": "LLM disabled"}

        prompt = f"""
Analyze the following git commit and its impact on the project based on changes in plan.md and changelog.md.

Commit Subject: {commit['subject']}
Files Changed: {details['stats']['files']}
Lines Added: {details['stats']['added']}
Lines Deleted: {details['stats']['deleted']}

--- plan.md content in this commit ---
{details['files'].get('plan.md', 'Not changed or not found')}

--- changelog.md content in this commit ---
{details['files'].get('changelog.md', 'Not changed or not found')}

Tasks:
1. Provide an improvement score from 0 to 100 based on feature progress and system value.
2. Provide a brief (1-2 sentences) analysis of the improvement.
3. Suggest a better, more descriptive git commit message if the current one is vague.

Return the result in JSON format:
{{
  "improvement_score": number,
  "analysis": "string",
  "suggested_message": "string"
}}
"""
        try:
            response = self.model.generate_content(prompt)
            
            # Track usage and cost
            usage: Any = getattr(response, 'usage_metadata', None)
            if usage:
                in_tokens = usage.prompt_token_count
                out_tokens = usage.candidates_token_count
                self.total_input_tokens += in_tokens
                self.total_output_tokens += out_tokens
                
                cost = (in_tokens / 1_000_000 * self.INPUT_COST_PER_1M) + \
                       (out_tokens / 1_000_000 * self.OUTPUT_COST_PER_1M)
                self.total_cost += cost

            # Extract JSON from response (handling potential markdown blocks)
            text = response.text
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                return json.loads(match.group(0))
            return {"improvement_score": 0, "analysis": "Failed to parse JSON", "suggested_message": commit["subject"]}
        except Exception as e:
            return {"improvement_score": 0, "analysis": f"Error: {e}", "suggested_message": commit["subject"]}

    def replace_commit_message(self, commit_hash: str, new_message: str):
        """Replaces the commit message using git filter-repo or a temporary rebase if possible."""
        # For the latest commit, it's easy:
        latest_hash = self.get_commits(1)[0]['hash']
        if commit_hash == latest_hash:
            print(f"Amending latest commit {commit_hash[:8]} message...")
            subprocess.run(["git", "commit", "--amend", "-m", new_message])
        else:
            # For older commits, we'd need to use something like:
            # git filter-branch --msg-filter 'sed "s/old/new/g"' HEAD
            # or interactive rebase which is not supported here.
            # We'll use a simple 'git filter-repo' style approach if available,
            # but for now, we just log it as "would replace" for safety on older commits.
            print(f"Would replace older commit {commit_hash[:8]} message with: {new_message}")

    def generate_report(self, results: List[Dict[str, Any]], output_file: str = "improvement_report.md"):
        """Generates the markdown report and graph."""
        if MATPLOTLIB_AVAILABLE and results:
            scores = [r['analysis_result']['improvement_score'] for r in reversed(results)]
            labels = [r['commit']['hash'][:8] for r in reversed(results)]

            plt.figure(figsize=(12, 6))
            plt.plot(labels, scores, marker='o', linestyle='-', color='blue')
            plt.title("Feature Improvement Score per Commit")
            plt.xlabel("Commit Hash")
            plt.ylabel("Improvement Score (0-100)")
            plt.grid(True, alpha=0.3)
            plt.xticks(rotation=45)
            plt.tight_layout()
            plt.savefig("improvement_graph.png")
            plt.close()

        report = [
            "# Feature Improvement Analysis Report",
            f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "## Summary",
            f"- **Total Commits Analyzed**: {len(results)}",
            f"- **Total Input Tokens**: {self.total_input_tokens:,}",
            f"- **Total Output Tokens**: {self.total_output_tokens:,}",
            f"- **Estimated Total Cost**: ${self.total_cost:.4f} USD",
            "",
            "## Improvement Trend",
            "![Improvement Graph](improvement_graph.png)" if MATPLOTLIB_AVAILABLE else "Graph not available (matplotlib missing)",
            "",
            "| Commit | Score | Lines +/- | Suggested Message | Analysis |",
            "| :--- | :--- | :--- | :--- | :--- |"
        ]

        for r in results:
            c = r['commit']
            res = r['analysis_result']
            stats = r['details']['stats']
            line_stats = f"+{stats['added']} / -{stats['deleted']}"
            report.append(
                f"| `{c['hash'][:8]}` | **{res['improvement_score']}** | {line_stats} | "
                f"{res['suggested_message']} | {res['analysis']} |"
            )

        with open(output_file, "w") as f:
            f.write("\n".join(report))
        print(f"Report generated: {output_file}")

    def run(self, limit: int = 10) -> None:
        commits = self.get_commits(limit)
        all_results: List[Dict[str, Any]] = []
        
        for c in commits:
            print(f"Analyzing commit {c['hash'][:8]}...")
            details = self.get_commit_details(c['hash'])
            analysis = self.analyze_improvement(c, details)
            all_results.append({
                "commit": c,
                "details": details,
                "analysis_result": analysis
            })
            
            if analysis['suggested_message'] != c['subject']:
                # Optional: replace_commit_message(c['hash'], analysis['suggested_message'])
                pass

        self.generate_report(all_results)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    analyzer = CommitAnalyzer()
    analyzer.run(limit=args.limit)
