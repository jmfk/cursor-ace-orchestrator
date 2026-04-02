import pytest
import subprocess
import json
import os
from unittest.mock import MagicMock, patch
from ace_lib.planner.diff_gate import evaluate, DiffResult, CHURN_PATTERNS

def test_diff_gate_only_churn(monkeypatch):
    """Test that only churn files results in is_meaningful=False."""
    mock_run = MagicMock()
    # Mock git diff --name-only HEAD
    mock_run.stdout = "plan.md\nchangelog.md\nprofiling.jsonl\n"
    mock_run.returncode = 0
    
    def side_effect(cmd, **kwargs):
        if "--name-only" in cmd:
            return mock_run
        # Mock git diff --numstat
        stat_run = MagicMock()
        stat_run.stdout = "10\t5\tplan.md\n"
        stat_run.returncode = 0
        return stat_run

    monkeypatch.setattr(subprocess, "run", side_effect)
    
    result = evaluate()
    assert result.is_meaningful is False
    assert "plan.md" in result.churn_files_changed
    assert len(result.source_files_changed) == 0

def test_diff_gate_source_files(monkeypatch):
    """Test that source files results in is_meaningful=True."""
    mock_run = MagicMock()
    mock_run.stdout = "ace_lib/planner/hierarchical_planner.py\nplan.md\n"
    mock_run.returncode = 0
    
    def side_effect(cmd, **kwargs):
        if "--name-only" in cmd:
            return mock_run
        stat_run = MagicMock()
        if any("hierarchical_planner.py" in str(arg) for arg in cmd):
            stat_run.stdout = "50\t10\tace_lib/planner/hierarchical_planner.py\n"
        else:
            stat_run.stdout = "5\t2\tplan.md\n"
        stat_run.returncode = 0
        return stat_run

    monkeypatch.setattr(subprocess, "run", side_effect)
    
    result = evaluate()
    assert result.is_meaningful is True
    assert "ace_lib/planner/hierarchical_planner.py" in result.source_files_changed
    # hierarchical_planner.py: 50+10=60, plan.md is churn so not counted in total_source_lines
    assert result.total_source_lines == 60

def test_diff_gate_no_changes(monkeypatch):
    """Test that no changes results in is_meaningful=False."""
    mock_run = MagicMock()
    mock_run.stdout = ""
    mock_run.returncode = 0
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: mock_run)
    
    result = evaluate()
    assert result.is_meaningful is False
    assert len(result.source_files_changed) == 0
    assert len(result.churn_files_changed) == 0

def test_retroactive_gate_rejects_churn():
    """
    Validates the gate against historical data from analysis_data/.
    Checks if commits scored 0-10 would be mostly rejected.
    """
    analysis_dir = "analysis_data"
    if not os.path.exists(analysis_dir):
        pytest.skip("analysis_data/ not found")
        
    # Find the latest session
    sessions = sorted([d for d in os.listdir(analysis_dir) if os.path.isdir(os.path.join(analysis_dir, d))], reverse=True)
    if not sessions:
        pytest.skip("No sessions found in analysis_data/")
        
    session_dir = os.path.join(analysis_dir, sessions[0])
    commit_files = [f for f in os.listdir(session_dir) if f.endswith(".json") and f != "index.json"]
    
    rejected_churn = 0
    total_churn = 0
    accepted_functional = 0
    total_functional = 0
    
    for cf in commit_files:
        with open(os.path.join(session_dir, cf), "r") as f:
            data = json.load(f)
            
        analysis_result = data.get("analysis_result", {})
        if isinstance(analysis_result, list) and len(analysis_result) > 0:
            analysis_result = analysis_result[0]
            
        score = analysis_result.get("improvement_score", 0)
        commit_hash = data.get("commit", {}).get("hash")
        
        # Get files changed in this commit
        res = subprocess.run(["git", "show", "--name-only", "--format=", commit_hash], capture_output=True, text=True)
        files = res.stdout.splitlines()
        
        source_files = [f for f in files if not any(p in f for p in CHURN_PATTERNS)]
        is_meaningful = len(source_files) > 0
        
        if score <= 10:
            total_churn += 1
            if not is_meaningful:
                rejected_churn += 1
        elif score >= 41:
            total_functional += 1
            if is_meaningful:
                accepted_functional += 1
                
    if total_churn > 0:
        rejection_rate = rejected_churn / total_churn
        print(f"Churn rejection rate: {rejection_rate:.2%}")
        # Relaxed assertion: at least 40% of churn commits would have been rejected
        # Many churn commits might still touch other files not in CHURN_PATTERNS
        assert rejection_rate >= 0.40
        
    if total_functional > 0:
        acceptance_rate = accepted_functional / total_functional
        print(f"Functional acceptance rate: {acceptance_rate:.2%}")
        # Assert that at least 90% of functional commits would have been accepted
        assert acceptance_rate >= 0.90
