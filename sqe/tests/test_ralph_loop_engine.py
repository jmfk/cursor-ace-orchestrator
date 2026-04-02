import pytest
import os
import json
import yaml
from unittest.mock import MagicMock, patch, mock_open
from pathlib import Path
import ralph_loop
from ace_lib.planner.hierarchical_planner import HierarchicalPlanner
from ace_lib.planner.plan_tree import PlanNode

@pytest.fixture
def mock_env(tmp_path):
    """Sets up a temporary environment for RALPH loop testing."""
    # Create dummy config
    config_path = tmp_path / "ralph.yaml"
    config_data = {
        "max_iterations": 3,
        "max_spend_usd": 1.0,
        "stats_file": str(tmp_path / "stats.json"),
        "log_file": str(tmp_path / "ralph.log"),
        "plan_file": str(tmp_path / "plan.md"),
        "state_history_file": str(tmp_path / "history.json")
    }
    with open(config_path, "w") as f:
        yaml.dump(config_data, f)

    # Initialize stats file
    with open(config_data["stats_file"], "w") as f:
        json.dump({"total_cost_usd": 0.0, "iterations": 0}, f)

    return {
        "config_path": config_path,
        "tmp_path": tmp_path,
        "config_data": config_data
    }

@patch("ralph_loop.log_message")
@patch("ralph_loop.run_cursor_agent")
@patch("ralph_loop.HierarchicalPlanner")
def test_ralph_loop_multi_iteration_success(mock_planner_cls, mock_run_agent, mock_log, mock_env):
    """
    Verifies Success Criterion: The 'ace loop' command successfully executes multiple iterations.
    This test simulates a 2-step process where the loop runs twice and then finishes.
    """
    # Setup Mock Planner
    mock_planner = MagicMock()
    mock_planner_cls.return_value = mock_planner
    
    # Define nodes for iterations
    node1 = PlanNode(id="001", title="Task 1", status="pending")
    node2 = PlanNode(id="002", title="Task 2", status="pending")
    
    # Mock the sequence of tasks: Task 1 -> Task 2 -> None (Done)
    mock_planner.tree.get_next_incomplete.side_effect = [node1, node2, None]
    mock_planner.run_step.return_value = node1 # Simulate successful step execution
    
    # Mock agent output
    mock_run_agent.return_value = "Execution successful"
    
    # Mock CLI arguments
    test_args = ["ralph_loop.py", "--config", str(mock_env["config_path"]), "--prd", "dummy.md"]
    
    with patch("sys.argv", test_args), \
         patch("ralph_loop.load_config"), \
         patch("fcntl.flock"): # Prevent lock file issues in test
        
        try:
            ralph_loop.main()
        except SystemExit:
            pass

    # Verify multiple iterations occurred
    assert mock_planner.run_step.call_count == 2
    # Verify context refresh (log messages indicating new iterations)
    iteration_logs = [call.args[0] for call in mock_log.call_args_list if "RALPH Loop Iteration" in str(call.args[0])]
    assert len(iteration_logs) >= 2

def test_ralph_loop_halts_on_success(mock_env):
    """
    Verifies Success Criterion: The engine halts immediately upon a successful test run (TDD approach).
    If the planner returns no more incomplete tasks, the loop must terminate.
    """
    mock_planner = MagicMock()
    # Immediately return None for next task
    mock_planner.tree.get_next_incomplete.return_value = None
    
    with patch("ralph_loop.HierarchicalPlanner", return_value=mock_planner), \
         patch("ralph_loop.load_config"), \
         patch("ralph_loop.log_message") as mock_log, \
         patch("sys.argv", ["ralph_loop.py", "--config", str(mock_env["config_path"])]), \
         patch("fcntl.flock"):
        
        try:
            ralph_loop.main()
        except SystemExit:
            pass
            
    # Verify it logged completion and stopped
    assert any("✅ All tasks completed" in str(call) for call in mock_log.call_args_list)
    assert mock_planner.run_step.call_count == 0

@patch("ralph_loop.run_cursor_agent")
def test_ralph_loop_captures_failure_learning(mock_run_agent, mock_env):
    """
    Verifies Success Criterion: The engine captures failure reasons in the learning phase.
    We simulate a failure and check if the planner's exit_with_analysis is triggered 
    when stagnation or consecutive failures occur.
    """
    mock_planner = MagicMock()
    node = PlanNode(id="001", title="Failing Task", status="pending")
    mock_planner.tree.get_next_incomplete.return_value = node
    
    # Simulate a failure in the agent execution
    mock_run_agent.return_value = None 
    
    # Force a stagnation trigger by mocking check_stagnation to return True
    with patch("ralph_loop.HierarchicalPlanner", return_value=mock_planner), \
         patch("ralph_loop.check_stagnation", return_value=True), \
         patch("ralph_loop.load_config"), \
         patch("sys.argv", ["ralph_loop.py", "--config", str(mock_env["config_path"])]), \
         patch("fcntl.flock"):
        
        try:
            ralph_loop.main()
        except SystemExit:
            pass

    # Verify that the planner was asked to exit with analysis (the 'Learning' phase)
    mock_planner.exit_with_analysis.assert_called_once()
    args, _ = mock_planner.exit_with_analysis.call_args
    assert "Stagnation detected" in args[0]

def test_ralph_loop_respects_max_iterations(mock_env):
    """
    Verifies that the engine halts when limits (max_iterations) are reached.
    """
    mock_planner = MagicMock()
    node = PlanNode(id="001", title="Infinite Task", status="pending")
    mock_planner.tree.get_next_incomplete.return_value = node
    
    # Mock config to only allow 2 iterations
    with patch.dict(ralph_loop.CONFIG, {"max_iterations": 2, "stats_file": mock_env["config_data"]["stats_file"]}): 
        with patch("ralph_loop.HierarchicalPlanner", return_value=mock_planner), \
             patch("ralph_loop.run_cursor_agent", return_value="ok"), \
             patch("ralph_loop.load_config"), \
             patch("ralph_loop.log_message") as mock_log, \
             patch("sys.argv", ["ralph_loop.py"]), \
             patch("fcntl.flock"):
            
            try:
                ralph_loop.main()
            except SystemExit:
                pass

    # Verify it stopped at iteration 2
    assert any("Max iterations (2) reached" in str(call) for call in mock_log.call_args_list)
    assert mock_planner.run_step.call_count == 2