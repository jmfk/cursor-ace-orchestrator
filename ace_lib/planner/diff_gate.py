import subprocess
import dataclasses
from typing import List, Set

@dataclasses.dataclass
class DiffResult:
    is_meaningful: bool
    source_files_changed: List[str]
    churn_files_changed: List[str]
    total_source_lines: int

CHURN_PATTERNS: Set[str] = {
    "plan.md",
    "changelog.md",
    "profiling.jsonl",
    "ralph_execution.log",
    "ralph_stats.json",
    "ralph_state_history.json",
    "roadmap.md",
}

def evaluate(churn_patterns: Set[str] = CHURN_PATTERNS) -> DiffResult:
    """
    Evaluates whether the current git diff (staged or unstaged) contains meaningful changes.
    """
    try:
        # Get list of changed files (both staged and unstaged)
        # We check against HEAD to see what would be committed
        res = subprocess.run(
            ["git", "diff", "HEAD", "--name-only"],
            capture_output=True,
            text=True,
            check=True
        )
        changed_files = res.stdout.splitlines()
        
        source_files = []
        churn_files = []
        total_source_lines = 0
        
        for file in changed_files:
            if any(pattern in file for pattern in churn_patterns):
                churn_files.append(file)
            else:
                source_files.append(file)
                # Get line count for source files
                try:
                    diff_stat = subprocess.run(
                        ["git", "diff", "HEAD", "--numstat", "--", file],
                        capture_output=True,
                        text=True,
                        check=True
                    )
                    for line in diff_stat.stdout.splitlines():
                        parts = line.split()
                        if len(parts) >= 2:
                            added = int(parts[0]) if parts[0] != "-" else 0
                            deleted = int(parts[1]) if parts[1] != "-" else 0
                            total_source_lines += (added + deleted)
                except (subprocess.CalledProcessError, ValueError):
                    pass

        is_meaningful = len(source_files) > 0
        
        return DiffResult(
            is_meaningful=is_meaningful,
            source_files_changed=source_files,
            churn_files_changed=churn_files,
            total_source_lines=total_source_lines
        )
        
    except subprocess.CalledProcessError:
        # If not a git repo or other error, assume not meaningful for safety
        return DiffResult(False, [], [], 0)
