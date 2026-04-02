import os
import json
import pytest
from datetime import datetime

def get_baseline_stats():
    """Calculates baseline stats from existing analysis_data/."""
    analysis_dir = "analysis_data"
    if not os.path.exists(analysis_dir):
        return None
        
    sessions = sorted([d for d in os.listdir(analysis_dir) if os.path.isdir(os.path.join(analysis_dir, d))], reverse=True)
    if not sessions:
        return None
        
    session_dir = os.path.join(analysis_dir, sessions[0])
    commit_files = [f for f in os.listdir(session_dir) if f.endswith(".json") and f != "index.json"]
    
    scores = []
    for cf in commit_files:
        with open(os.path.join(session_dir, cf), "r") as f:
            data = json.load(f)
            score = data.get("analysis_result", {}).get("improvement_score", 0)
            scores.append(score)
            
    if not scores:
        return None
        
    return {
        "mean_score": sum(scores) / len(scores),
        "median_score": sorted(scores)[len(scores)//2],
        "percent_above_40": len([s for s in scores if s >= 41]) / len(scores) * 100,
        "total_commits": len(scores)
    }

def test_improvement_trend():
    """
    Compares the quality of new commits (post-gate) against the historical baseline.
    This is intended to be run manually or as a post-execution check.
    """
    baseline = get_baseline_stats()
    if not baseline:
        pytest.skip("Baseline data not found in analysis_data/")
        
    # In a real scenario, we would run the CommitAnalyzer on the latest N commits
    # For now, we'll just report the comparison if new data exists.
    
    print(f"\n--- Baseline Stats (Historical) ---")
    print(f"Mean Score: {baseline['mean_score']:.2f}")
    print(f"Median Score: {baseline['median_score']}")
    print(f"Percent Above 40 (Functional): {baseline['percent_above_40']:.2f}%")
    print(f"Total Commits: {baseline['total_commits']}")
    
    # Check for a "latest_post_gate" session if it exists
    # This would be populated by running analyze_commits.py after the gate is active
    # For the purpose of this test, we just provide the harness.
    
    # Save the baseline for future comparison
    with open("quality_comparison_baseline.json", "w") as f:
        json.dump(baseline, f, indent=2)
        
    # Assertions could be added here once we have post-gate data to compare against.
    # For now, we just ensure the harness can read the baseline.
    assert baseline["total_commits"] > 0
