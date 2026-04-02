import subprocess
import os
import math
import re
from typing import List, Dict, Any, Tuple
from datetime import datetime

# Try to import matplotlib for PNG generation
try:
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

class CommitEvaluator:
    """
    Evaluates the value of git commits based on heuristics and optional LLM analysis.
    Aggregates value by features, milestones, and time series.
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
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            commits = []
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

    def extract_milestone(self, subject: str) -> str:
        """Extract milestone or feature name from commit subject."""
        for pattern in self.MILESTONE_PATTERNS:
            match = re.search(pattern, subject, re.IGNORECASE)
            if match:
                return match.group(1).upper()
        
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
            added, deleted, files_changed, file_types = 0, 0, 0, {}

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

            return {"added": added, "deleted": deleted, "total_changes": added + deleted, "files_changed": files_changed, "file_types": file_types}
        except subprocess.CalledProcessError:
            return {"total_changes": 0, "files_changed": 0, "file_types": {}}

    def calculate_heuristic_score(self, stats: Dict[str, Any], subject: str) -> float:
        """Calculate a value score based on heuristics."""
        score = 0.0
        total_changes = stats.get("total_changes", 0)
        if total_changes > 0:
            score += math.log10(total_changes + 1) * 2.0
        files_changed = stats.get("files_changed", 0)
        score += min(files_changed, 10) * 0.5
        if 10 < len(subject) < 70:
            score += 1.0
        val_keywords = ["fix", "feat", "refactor", "implement", "add", "optimize", "improve"]
        if any(kw in subject.lower() for kw in val_keywords):
            score += 1.5
        for ext, count in stats.get("file_types", {}).items():
            if ext in [".py", ".ts", ".js", ".go", ".rs", ".java", ".cpp"]:
                score += count * 1.0
            elif ext in [".md", ".txt"]:
                score += count * 0.2
            elif ext in [".json", ".yaml", ".yml"]:
                score += count * 0.5
        return round(score, 2)

    def generate_time_series_graph(self, results: List[Dict], output_path: str):
        """Generate a PNG line chart for value over time."""
        if not MATPLOTLIB_AVAILABLE:
            return

        # Aggregate by date
        daily_value = {}
        for r in results:
            # Git date format: "Thu Apr 2 04:33:52 2026 +0200"
            # We need to parse this. A simpler way is to use git log --date=short
            try:
                # Re-fetch date in short format for easier parsing
                date_str = subprocess.run(
                    ["git", "show", "-s", "--format=%ad", "--date=short", r["commit"]["hash"]],
                    capture_output=True, text=True
                ).stdout.strip()
                dt = datetime.strptime(date_str, "%Y-%m-%d")
                daily_value[dt] = daily_value.get(dt, 0.0) + r["score"]
            except Exception:
                continue

        if not daily_value:
            return

        sorted_dates = sorted(daily_value.keys())
        values = [daily_value[d] for d in sorted_dates]

        plt.figure(figsize=(14, 7))
        plt.plot(sorted_dates, values, marker='o', linestyle='-', color='forestgreen', linewidth=2)
        plt.fill_between(sorted_dates, values, color='forestgreen', alpha=0.1)
        
        plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        plt.gca().xaxis.set_major_locator(mdates.DayLocator(interval=max(1, len(sorted_dates)//10)))
        plt.gcf().autofmt_xdate()
        
        plt.xlabel('Date')
        plt.ylabel('Total Value Score')
        plt.title('System Value Growth Over Time')
        plt.grid(True, linestyle='--', alpha=0.6)
        plt.tight_layout()
        plt.savefig(output_path)
        plt.close()
        print(f"Time series graph saved: {output_path}")

    def generate_commit_value_graph(self, results: List[Dict], output_path: str):
        """Generate a PNG bar chart for individual commit values."""
        if not MATPLOTLIB_AVAILABLE:
            return
        plot_results = results[-30:] if len(results) > 30 else results
        hashes = [r["commit"]["hash"][:8] for r in plot_results]
        scores = [r["score"] for r in plot_results]
        plt.figure(figsize=(14, 7))
        plt.bar(hashes, scores, color='skyblue')
        plt.xlabel('Commit Hash')
        plt.ylabel('Value Score')
        plt.title('Recent Commit Value Analysis')
        plt.xticks(rotation=45, ha='right')
        plt.grid(axis='y', linestyle='--', alpha=0.6)
        plt.tight_layout()
        plt.savefig(output_path)
        plt.close()

    def generate_milestone_graph(self, sorted_milestones: List[Tuple], output_path: str):
        """Generate a PNG bar chart for milestone values."""
        if not MATPLOTLIB_AVAILABLE:
            return
        names = [m[0] for m in sorted_milestones[:15]]
        scores = [m[1]["score"] for m in sorted_milestones[:15]]
        plt.figure(figsize=(14, 7))
        colors = plt.cm.viridis([i/len(names) for i in range(len(names))])
        plt.bar(names, scores, color=colors)
        plt.xlabel('Milestone / Feature')
        plt.ylabel('Aggregated Value Score')
        plt.title('Value Contribution by Milestone/Feature')
        plt.xticks(rotation=45, ha='right')
        plt.grid(axis='y', linestyle='--', alpha=0.6)
        plt.tight_layout()
        plt.savefig(output_path)
        plt.close()

    def generate_comprehensive_report(self, limit: int = None, output_file: str = "comprehensive_value_report.md"):
        """Generate a report covering commits, milestones, and time-series."""
        commits = self.get_commits(limit)
        print(f"Analyzing {len(commits)} commits...")
        
        results = []
        milestones = {}
        
        for c in commits:
            stats = self.get_commit_diff_stats(c["hash"])
            score = self.calculate_heuristic_score(stats, c["subject"])
            results.append({"commit": c, "stats": stats, "score": score})
            
            m_name = self.extract_milestone(c["subject"])
            if m_name not in milestones:
                milestones[m_name] = {"score": 0.0, "count": 0, "files": 0, "commits": []}
            milestones[m_name]["score"] += score
            milestones[m_name]["count"] += 1
            milestones[m_name]["files"] += stats["files_changed"]
            milestones[m_name]["commits"].append({"hash": c["hash"], "subject": c["subject"], "score": score})

        # Generate Graphs
        self.generate_commit_value_graph(results, "commit_value_graph.png")
        self.generate_milestone_graph(sorted(milestones.items(), key=lambda x: x[1]["score"], reverse=True), "milestone_value_graph.png")
        self.generate_time_series_graph(results, "value_over_time.png")

        # Generate Markdown
        report = [
            "# Comprehensive System Value Report",
            f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"Total Commits Analyzed: {len(commits)}",
            "",
            "## 1. Value Growth Over Time",
            "![Value Over Time](value_over_time.png)",
            "",
            "## 2. Value by Milestone / Feature",
            "![Milestone Value Graph](milestone_value_graph.png)",
            "",
            "| Milestone | Total Value | Commits | Avg Value |",
            "| :--- | :--- | :--- | :--- |"
        ]

        sorted_milestones = sorted(milestones.items(), key=lambda x: x[1]["score"], reverse=True)
        for m_name, data in sorted_milestones:
            avg_val = round(data["score"] / data["count"], 2) if data["count"] > 0 else 0
            report.append(f"| **{m_name}** | {round(data['score'], 2)} | {data['count']} | {avg_val} |")

        report.extend([
            "",
            "## 3. Recent Commit Value",
            "![Recent Commit Graph](commit_value_graph.png)",
            "",
            "| Hash | Score | Subject |",
            "| :--- | :--- | :--- |"
        ])

        for r in results[:20]: # Show last 20 in table
            report.append(f"| `{r['commit']['hash'][:8]}` | **{r['score']}** | {r['commit']['subject']} |")

        with open(output_file, "w") as f:
            f.write("\n".join(report))
        
        print(f"Comprehensive report generated: {output_file}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true", help="Generate comprehensive report")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--output", type=str, default="comprehensive_value_report.md")
    args = parser.parse_args()

    evaluator = CommitEvaluator()
    evaluator.generate_comprehensive_report(limit=args.limit, output_file=args.output)
