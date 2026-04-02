import subprocess
import json
import os
import requests
import math
import re
from typing import List, Dict, Any, Tuple
from datetime import datetime

# Try to import matplotlib for PNG generation
try:
    import matplotlib.pyplot as plt
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

class CommitEvaluator:
    """
    Evaluates the value of git commits based on heuristics and optional LLM analysis.
    Aggregates value by features and milestones found in the history.
    """

    # Files to exclude from diff analysis
    EXCLUDED_FILES = {
        "ralph_execution.log",
        "ralph_loop.py",
        "ralph_state_history.json",
        "ralph_stats.json",
        "plan.md",
        "changelog.md"
    }

    # Milestone patterns (e.g., M0, M1, Phase 1, Task 10.1)
    MILESTONE_PATTERNS = [
        r"(M[0-9]+)",           # M0, M1...
        r"(Phase\s+[0-9]+)",    # Phase 1, Phase 2...
        r"(Task\s+[0-9.]+)",    # Task 10.1, Task 11...
        r"([0-9]+\.[0-9]+)"     # 10.71, 11.2...
    ]

    def __init__(self, model: str = "gemini-2.0-flash", use_llm: bool = False):
        self.model = model
        self.use_llm = use_llm
        self.api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

    def get_commits(self, limit: int = None) -> List[Dict[str, Any]]:
        """Fetch commits from the history."""
        cmd = ["git", "log", "--pretty=format:%H|%an|%ad|%s"]
        if limit:
            cmd.extend(["-n", str(limit)])
        
        try:
            print(f"Running command: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            print(f"Command output length: {len(result.stdout)}")
            commits = []
            for line in result.stdout.splitlines():
                parts = line.split("|")
                if len(parts) >= 4:
                    commits.append({
                        "hash": parts[0],
                        "author": parts[1],
                        "date": parts[2],
                        "subject": "|".join(parts[3:]) # Rejoin in case subject contains pipes
                    })
            return commits
        except subprocess.CalledProcessError as e:
            print(f"Error running git log: {e}")
            print(f"Stderr: {e.stderr}")
            return []

    def extract_milestone(self, subject: str) -> str:
        """Extract milestone or feature name from commit subject."""
        for pattern in self.MILESTONE_PATTERNS:
            match = re.search(pattern, subject, re.IGNORECASE)
            if match:
                return match.group(1).upper()
        
        # Fallback: Check for common feature keywords
        features = ["auth", "api", "ui", "db", "stitch", "ralph", "ace", "memory", "consensus"]
        for feat in features:
            if feat in subject.lower():
                return f"FEAT:{feat.upper()}"
        
        return "GENERAL"

    def get_commit_diff_stats(self, commit_hash: str) -> Dict[str, Any]:
        """Get line change statistics for a commit, excluding specific files."""
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
                    filename = parts[2]
                    if any(excluded in filename for excluded in self.EXCLUDED_FILES):
                        continue

                    try:
                        a = int(parts[0]) if parts[0] != "-" else 0
                        d = int(parts[1]) if parts[1] != "-" else 0
                        added += a
                        deleted += d
                        files_changed += 1
                        
                        ext = os.path.splitext(filename)[1] or "no_ext"
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
        """Calculate a value score based on heuristics."""
        score = 0.0
        total_changes = stats.get("total_changes", 0)
        if total_changes > 0:
            score += math.log10(total_changes + 1) * 2.0
        files_changed = stats.get("files_changed", 0)
        score += min(files_changed, 10) * 0.5
        subject_len = len(subject)
        if 10 < subject_len < 70:
            score += 1.0
        val_keywords = ["fix", "feat", "refactor", "implement", "add", "optimize", "improve"]
        if any(kw in subject.lower() for kw in val_keywords):
            score += 1.5
        file_types = stats.get("file_types", {})
        for ext, count in file_types.items():
            if ext in [".py", ".ts", ".js", ".go", ".rs", ".java", ".cpp"]:
                score += count * 1.0
            elif ext in [".md", ".txt"]:
                score += count * 0.2
            elif ext in [".json", ".yaml", ".yml"]:
                score += count * 0.5
        return round(score, 2)

    def get_llm_evaluation(self, commit: Dict[str, Any], stats: Dict[str, Any]) -> str:
        """Use Gemini Flash to evaluate the semantic value of a commit."""
        if not self.use_llm or not self.api_key:
            return "LLM evaluation skipped."
        try:
            diff = subprocess.run(
                ["git", "show", "--format=", "--unified=1", commit["hash"]],
                capture_output=True, text=True, check=True
            ).stdout[:3000]
        except Exception:
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

    def generate_report(self, limit: int = 20, output_file: str = "commit_value_report.md"):
        """Evaluate history and generate a markdown report with ASCII graphs."""
        commits = self.get_commits(limit)
        results = []
        
        print(f"Evaluating {len(commits)} commits...")
        for c in commits:
            stats = self.get_commit_diff_stats(c["hash"])
            h_score = self.calculate_heuristic_score(stats, c["subject"])
            llm_analysis = self.get_llm_evaluation(c, stats) if self.use_llm else None
            results.append({
                "commit": c,
                "stats": stats,
                "score": h_score,
                "llm_analysis": llm_analysis
            })

        # Generate Markdown
        report = [
            "# Git Commit Value Report",
            f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"Analysis Depth: {limit} commits",
            f"LLM Analysis: {'Enabled' if self.use_llm else 'Disabled'}",
            "",
            "## Value Distribution (ASCII Graph)",
            "```"
        ]
        
        # Simple ASCII histogram of scores
        if results:
            max_score = max(r["score"] for r in results)
            for r in results:
                bar_len = int((r["score"] / max_score) * 40) if max_score > 0 else 0
                report.append(f"{r['commit']['hash'][:8]} [{r['score']:>5.2f}] | {'#' * bar_len}")
        
        report.extend([
            "```",
            "",
            "## Commit Details",
            "| Hash | Score | Subject | Analysis |",
            "| :--- | :--- | :--- | :--- |"
        ])
        
        for r in results:
            if r["llm_analysis"]:
                analysis = r["llm_analysis"]
            else:
                analysis = f"Files: {r['stats']['files_changed']}, Changes: {r['stats']['total_changes']}"
            # Escape pipes in analysis for markdown table
            analysis = analysis.replace("|", "\\|")
            report.append(f"| `{r['commit']['hash'][:8]}` | **{r['score']}** | {r['commit']['subject']} | {analysis} |")

        with open(output_file, "w") as f:
            f.write("\n".join(report))
        
        print(f"Report generated: {output_file}")

    def generate_aggregated_report(self, output_file: str = "milestone_value_report.md"):
        """Analyze full history, aggregate by milestone, and generate report."""
        commits = self.get_commits()
        print(f"Analyzing {len(commits)} commits from full history...")
        
        milestones = {} # milestone -> {score, commits, changes, files}
        
        for c in commits:
            m_name = self.extract_milestone(c["subject"])
            if m_name not in milestones:
                milestones[m_name] = {"score": 0.0, "count": 0, "changes": 0, "files": 0, "commits": []}
            
            stats = self.get_commit_diff_stats(c["hash"])
            score = self.calculate_heuristic_score(stats, c["subject"])
            
            milestones[m_name]["score"] += score
            milestones[m_name]["count"] += 1
            milestones[m_name]["changes"] += stats["total_changes"]
            milestones[m_name]["files"] += stats["files_changed"]
            milestones[m_name]["commits"].append({
                "hash": c["hash"],
                "subject": c["subject"],
                "score": score
            })

        # Sort milestones by total score
        sorted_milestones = sorted(milestones.items(), key=lambda x: x[1]["score"], reverse=True)

        # Generate PNG Graph
        self.generate_milestone_graph(sorted_milestones, "milestone_value_graph.png")

        # Generate Markdown
        report = [
            "# Milestone & Feature Value Report",
            f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"Total Commits Analyzed: {len(commits)}",
            "",
            "## Value by Milestone / Feature",
            "![Milestone Value Graph](milestone_value_graph.png)",
            "",
            "| Milestone | Total Value | Commits | Avg Value | Files Touched |",
            "| :--- | :--- | :--- | :--- | :--- |"
        ]

        for m_name, data in sorted_milestones:
            avg_val = round(data["score"] / data["count"], 2) if data["count"] > 0 else 0
            report.append(
                f"| **{m_name}** | {round(data['score'], 2)} | {data['count']} | {avg_val} | {data['files']} |"
            )

        report.append("\n## Top 10 High-Value Commits")
        report.append("| Hash | Score | Subject |")
        report.append("| :--- | :--- | :--- |")
        
        all_scored_commits = []
        for m_name, data in milestones.items():
            all_scored_commits.extend(data["commits"])
        
        top_commits = sorted(all_scored_commits, key=lambda x: x["score"], reverse=True)[:10]
        for tc in top_commits:
            report.append(f"| `{tc['hash'][:8]}` | **{tc['score']}** | {tc['subject']} |")

        with open(output_file, "w") as f:
            f.write("\n".join(report))
        
        print(f"Aggregated report generated: {output_file}")

    def generate_milestone_graph(self, sorted_milestones: List[Tuple], output_path: str):
        """Generate a PNG bar chart for milestone values."""
        if not MATPLOTLIB_AVAILABLE:
            return

        names = [m[0] for m in sorted_milestones[:15]] # Top 15
        scores = [m[1]["score"] for m in sorted_milestones[:15]]

        plt.figure(figsize=(14, 7))
        colors = plt.cm.viridis([i/len(names) for i in range(len(names))])
        bars = plt.bar(names, scores, color=colors)
        plt.xlabel('Milestone / Feature')
        plt.ylabel('Aggregated Value Score')
        plt.title('Value Contribution by Milestone/Feature')
        plt.xticks(rotation=45, ha='right')
        plt.grid(axis='y', linestyle='--', alpha=0.6)

        for bar in bars:
            yval = bar.get_height()
            plt.text(bar.get_x() + bar.get_width()/2, yval + 0.5, round(yval, 1), ha='center', va='bottom', fontsize=9)

        plt.tight_layout()
        plt.savefig(output_path)
        plt.close()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true", help="Analyze full history and aggregate by milestone")
    parser.add_argument("--limit", type=int, default=20, help="Number of commits to analyze for standard report")
    parser.add_argument("--report", action="store_true", help="Generate standard markdown report")
    parser.add_argument("--llm", action="store_true", help="Use Gemini Flash for evaluation")
    parser.add_argument("--output", type=str, default="commit_value_report.md", help="Report output file")
    args = parser.parse_args()

    evaluator = CommitEvaluator(use_llm=args.llm)
    if args.all:
        evaluator.generate_aggregated_report(output_file=args.output)
    elif args.report:
        evaluator.generate_report(limit=args.limit, output_file=args.output)
    else:
        evaluator.generate_aggregated_report(output_file=args.output)
