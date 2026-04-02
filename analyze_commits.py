import subprocess
import os
import re
import json
from typing import List, Dict, Any, Optional
from datetime import datetime
from pathlib import Path
import google.genai as genai
from google.genai import types
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
        "rolf_execution.log",
        "rolf_loop.py",
        "rolf_state_history.json",
        "rolf_stats.json"
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
            self.client = genai.Client(api_key=self.api_key)
            self.model_name = model
        else:
            self.client = None
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
        """Get diff stats, specific file changes, and the actual code diff."""
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

        # Actual code diff (excluding large/irrelevant files)
        # We use -- . ':(exclude)path' syntax for git show
        exclude_args = [f":(exclude){ex}" for ex in self.EXCLUDED_FILES]
        cmd_diff = ["git", "show", "--format=", commit_hash, "--"] + ["."] + exclude_args
        diff_content = ""
        try:
            res_diff = subprocess.run(cmd_diff, capture_output=True, text=True, check=True)
            diff_content = res_diff.stdout
            # Limit diff size to avoid blowing up the prompt
            if len(diff_content) > 10000:
                diff_content = diff_content[:10000] + "\n... [diff truncated] ..."
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

        return {"stats": stats, "files": files_content, "diff": diff_content}

    def analyze_improvement(self, commit: Dict[str, Any], details: Dict[str, Any]) -> Dict[str, Any]:
        """Use Gemini to measure improvement and suggest a better commit message."""
        if not self.client:
            return {"improvement_score": 0, "suggested_message": commit["subject"], "analysis": "LLM disabled"}

        # Heuristic override for zero-change commits (Phase 12)
        total_changes = details['stats']['added'] + details['stats']['deleted']
        if total_changes == 0:
            return {
                "improvement_score": 0,
                "analysis": "Administrative churn / No code changes (only excluded files or no changes).",
                "suggested_message": commit["subject"]
            }

        prompt = f"""
Analyze the following git commit for system value and feature progress.

RUBRIC (0-100):
- 0-10: Administrative churn (logs, placeholders, roadmap increments, formatting).
- 11-40: Documentation updates or minor refactoring with no functional change.
- 41-70: Functional bug fixes or incremental features/improvements.
- 71-100: Major architectural improvements or significant new features.

Commit Subject: {commit['subject']}
Files Changed: {details['stats']['files']}
Lines Added: {details['stats']['added']}
Lines Deleted: {details['stats']['deleted']}

--- plan.md content in this commit ---
{details['files'].get('plan.md', 'Not changed or not found')}

--- changelog.md content in this commit ---
{details['files'].get('changelog.md', 'Not changed or not found')}

--- ACTUAL CODE DIFF ---
{details.get('diff', 'No code diff available')}

Tasks:
1. Assign an improvement score (0-100) based on the RUBRIC.
2. Provide a brief (1-2 sentences) analysis. Evaluate if the code change actually improves the codebase.
3. Suggest a better, more descriptive git commit message if the current one is vague.

Return the result in JSON format:
{{
  "improvement_score": number,
  "analysis": "string",
  "suggested_message": "string"
}}
"""
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                )
            )
            
            # Track usage and cost
            usage = response.usage_metadata
            if usage:
                in_tokens = usage.prompt_token_count
                out_tokens = usage.candidates_token_count
                self.total_input_tokens += in_tokens
                self.total_output_tokens += out_tokens
                
                cost = (in_tokens / 1_000_000 * self.INPUT_COST_PER_1M) + (
                    out_tokens / 1_000_000 * self.OUTPUT_COST_PER_1M
                )
                self.total_cost += cost

            # Parse JSON from response
            return json.loads(response.text)
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
            "![Improvement Graph](improvement_graph.png)"
            if MATPLOTLIB_AVAILABLE
            else "Graph not available (matplotlib missing)",
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

    def get_total_commit_count(self) -> int:
        """Get the total number of commits in the current branch."""
        try:
            result = subprocess.run(["git", "rev-list", "--count", "HEAD"], capture_output=True, text=True, check=True)
            return int(result.stdout.strip())
        except (subprocess.CalledProcessError, ValueError):
            return 0

    def run(self, limit: int = 10) -> None:
        # Phase 12: Persistent Data Storage for Analysis
        # Create a session-specific subfolder with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        data_dir = Path("analysis_data") / timestamp
        
        # Interactive limit adjustment
        total_available = self.get_total_commit_count()
        print(f"\nTotal commits available in history: {total_available}")
        
        try:
            user_input = input(f"Enter limit (default {limit}, 'all' for {total_available}): ").strip().lower()
            if user_input == 'all':
                limit = total_available
            elif user_input:
                limit = int(user_input)
        except (ValueError, EOFError, KeyboardInterrupt):
            print(f"Using default limit: {limit}")

        print(f"Proceeding with analysis for {limit} commits...\n")
        data_dir.mkdir(parents=True, exist_ok=True)
        parent_data_dir = Path("analysis_data")
        parent_data_dir.mkdir(exist_ok=True)
        
        commits = self.get_commits(limit)
        all_results: List[Dict[str, Any]] = []
        
        for c in commits:
            commit_hash = c['hash']
            # Check for cache in any session subfolder
            cache_file = None
            for existing_session in parent_data_dir.iterdir():
                if existing_session.is_dir():
                    potential_cache = existing_session / f"{commit_hash}.json"
                    if potential_cache.exists():
                        cache_file = potential_cache
                        break
            
            if cache_file:
                try:
                    cached_data = json.loads(cache_file.read_text(encoding="utf-8"))
                    if isinstance(cached_data, dict) and 'analysis_result' in cached_data:
                        all_results.append(cached_data)
                        # Update totals from cache
                        self.total_cost += cached_data.get("cost", 0.0)
                        continue
                    else:
                        print(f"Cached data for {commit_hash[:8]} is invalid (not a dict or missing analysis_result). Re-analyzing...")
                except Exception as e:
                    print(f"Error reading cache for {commit_hash[:8]}: {e}")

            print(f"Analyzing commit {commit_hash[:8]}...")
            details = self.get_commit_details(commit_hash)
            
            # Capture cost before and after to store per-commit cost
            cost_before = self.total_cost
            analysis = self.analyze_improvement(c, details)
            commit_cost = self.total_cost - cost_before
            
            result = {
                "commit": c,
                "details": details,
                "analysis_result": analysis,
                "cost": commit_cost,
                "analyzed_at": datetime.now().isoformat()
            }
            all_results.append(result)
            
            # Save to the current session's subfolder
            session_cache_file = data_dir / f"{commit_hash}.json"
            session_cache_file.write_text(json.dumps(result, indent=2), encoding="utf-8")
            
            if isinstance(analysis, dict) and analysis.get('suggested_message') != c['subject']:
                # Optional: replace_commit_message(c['hash'], analysis['suggested_message'])
                pass

        # Save an index file to maintain the order of commits in this session
        index_file = data_dir / "index.json"
        index_data = {
            "session_timestamp": timestamp,
            "commit_order": [r['commit']['hash'] for r in all_results],
            "total_commits": len(all_results),
            "total_cost": self.total_cost
        }
        index_file.write_text(json.dumps(index_data, indent=2), encoding="utf-8")

        self.generate_report(all_results)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    analyzer = CommitAnalyzer()
    analyzer.run(limit=args.limit)
