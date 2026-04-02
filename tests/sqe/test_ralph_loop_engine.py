import pytest
import os
import json
import yaml
import sys
from unittest.mock import MagicMock, patch, mock_open
from pathlib import Path

# Import the module under test
import ralph_loop
from ace_lib.planner.plan_tree import PlanNode

@pytest.fixture
def mock_env(tmp_path):
    """Sets up a temporary environment for RALPH loop testing."""
    # Create dummy config
    config_path = tmp_path / "ralph.yaml"
    config_data = {
        "max_iterations": 5,
        "max_spend_usd": 1.0,
        "stats_file": str(tmp_path / "ralph_stats.json"),
        "log_file": str(tmp_path / "ralph_execution.log"),
        "plan_file": str(tmp_path / "plan.md"),
        "state_history_file": str(tmp_path / "ralph_state_history.json"),
        "model": "gemini-3-flash",
        "price_input_1m": 0.10,
        "price_output_1m": 0.40
    }
    with open(config_path, "w") as f:
        yaml.dump(config_data, f)

    # Initialize stats file
    with open(config_data["stats_file"], "w") as f:
        json.dump({
            "total_input_tokens": 0, 
            "total_output_tokens": 0, 
            "total_cost_usd": 0.0, 
            "total_time_sec": 0.0, 
            "iterations": 0
        }, f)

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
    Simulates a 2-step process where the loop runs twice and then finishes.
    """
    # Setup Mock Planner
    mock_planner = MagicMock()
    mock_planner_cls.return_value = mock_planner
    
    # Define nodes for iterations
    node1 = PlanNode(id="001", title="Task 1", status="pending")
    node2 = PlanNode(id="002", title="Task 2", status="pending")
    
    # Mock the sequence of tasks: Task 1 -> Task 2 -> None (Done)
    mock_planner.tree.get_next_incomplete.side_effect = [node1, node2, None]
    mock_planner.run_step.return_value = node1 
    
    # Mock agent output (JSON stream format)
    mock_run_agent.return_value = '{"usage": {"input_tokens": 100, "output_tokens": 200}}'
    
    # Mock CLI arguments
    test_args = ["ralph_loop.py", "--config", str(mock_env["config_path"]), "dummy_prd.md"]
    
    with patch("sys.argv", test_args), \
         patch("fcntl.flock"): # Prevent lock file issues in test environment
        
        try:
            ralph_loop.main()
        except SystemExit:
            pass

    # Verify multiple iterations occurred (run_step called for each node)
    assert mock_planner.run_step.call_count == 2
    
    # Verify context refresh/logging indicating new iterations
    iteration_logs = [call.args[0] for call in mock_log.call_args_list if "RALPH Loop Iteration" in str(call.args[0])]
    assert len(iteration_logs) >= 2

@patch("ralph_loop.log_message")
@patch("ralph_loop.HierarchicalPlanner")
def test_ralph_loop_halts_immediately_on_success(mock_planner_cls, mock_log, mock_env):
    """
    Verifies Success Criterion: The engine halts immediately upon a successful test run (TDD approach).
    If the planner returns no more incomplete tasks, the loop must terminate without further execution.
    """
    mock_planner = MagicMock()
    mock_planner_cls.return_value = mock_planner
    
    # Immediately return None for next task (all tasks done)
    mock_planner.tree.get_next_incomplete.return_value = None
    
    test_args = ["ralph_loop.py", "--config", str(mock_env["config_path"]), "dummy_prd.md"]
    
    with patch("sys.argv", test_args), patch("fcntl.flock"):
        try:
            ralph_loop.main()
        except SystemExit:
            pass
            
    # Verify it logged completion and stopped before running any steps
    assert any("All tasks in the hierarchical plan are completed!" in str(call) for call in mock_log.call_args_list)
    assert mock_planner.run_step.call_count == 0

@patch("ralph_loop.run_cursor_agent")
@patch("ralph_loop.HierarchicalPlanner")
def test_ralph_loop_captures_failure_learning(mock_planner_cls, mock_run_agent, mock_env):
    """
    Verifies Success Criterion: The engine captures failure reasons in the learning phase.
    Simulates stagnation (repeatedly visiting the same node) and verifies that 
    the planner's 'exit_with_analysis' is triggered to inform the next steps.
    """
    mock_planner = MagicMock()
    mock_planner_cls.return_value = mock_planner
    
    node = PlanNode(id="fail_001", title="Failing Task", status="pending")
    mock_planner.tree.get_next_incomplete.return_value = node
    
    # Simulate a failure in the agent execution (returns None)
    mock_run_agent.return_value = None 
    
    # Force a stagnation trigger by mocking check_stagnation to return True
    # In the real code, this happens if the same node is visited too many times
    with patch("ralph_loop.check_stagnation", return_value=True), \
         patch("ralph_loop.log_message"), \
         patch("sys.argv", ["ralph_loop.py", "--config", str(mock_env["config_path"]), "dummy.md"]), \
         patch("fcntl.flock"):
        
        try:
            ralph_loop.main()
        except SystemExit:
            pass

    # Verify that the planner was asked to exit with analysis (the 'Learning' phase)
    # This method in hierarchical_planner.py generates the post-mortem analysis
    mock_planner.exit_with_analysis.assert_called_once()
    args, _ = mock_planner.exit_with_analysis.call_args
    assert "Stagnation detected" in args[0]

@patch("ralph_loop.run_cursor_agent")
def test_ralph_loop_updates_stats_between_iterations(mock_run_agent, mock_env):
    """
    Verifies that the engine refreshes context (stats/tokens) between iterations.
    """
    # Mock agent to return specific token usage
    mock_run_agent.return_value = '{"usage": {"input_tokens": 1000, "output_tokens": 500}}'
    
    # Manually trigger update_stats to verify logic
    ralph_loop.CONFIG = mock_env["config_data"]
    ralph_loop.update_stats(1000, 500, 10.5)
    
    with open(mock_env["config_data"]["stats_file"], "r") as f:
        stats = json.load(f)
        
    assert stats["total_input_tokens"] == 1000
    assert stats["total_output_tokens"] == 500
    assert stats["iterations"] == 1
    # Cost calculation: (1000/1M * 0.10) + (500/1M * 0.40) = 0.0001 + 0.0002 = 0.0003
    assert stats["total_cost_usd"] == pytest.approx(0.0003)
"
}