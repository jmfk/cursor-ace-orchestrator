import pytest
import os
import json
import subprocess
import signal
from unittest.mock import MagicMock, patch
import ralph_loop

@pytest.fixture
def mock_config(tmp_path):
    stats_file = tmp_path / "stats.json"
    history_file = tmp_path / "history.json"
    plan_file = tmp_path / "plan.md"
    
    config = {
        "stats_file": str(stats_file),
        "state_history_file": str(history_file),
        "plan_file": str(plan_file),
        "max_iterations": 5,
        "max_spend_usd": 10.0,
        "model": "test-model",
        "stagnation_threshold": 3
    }
    
    with patch.dict(ralph_loop.CONFIG, config):
        yield config

def test_process_cleanup_on_timeout(mock_config, monkeypatch):
    """Test that process group is killed on timeout."""
    mock_popen = MagicMock()
    mock_popen.pid = 1234
    mock_popen.communicate.side_effect = subprocess.TimeoutExpired(cmd="test", timeout=1)
    
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: mock_popen)
    
    # Mock os.killpg and os.getpgid
    mock_killpg = MagicMock()
    mock_getpgid = MagicMock(return_value=1234)
    monkeypatch.setattr(os, "killpg", mock_killpg)
    monkeypatch.setattr(os, "getpgid", mock_getpgid)
    
    # Mock log_message to avoid print
    monkeypatch.setattr(ralph_loop, "log_message", MagicMock())
    
    result = ralph_loop.run_cursor_agent("test prompt", timeout=1)
    
    assert result is None
    # killpg should be called twice: once in except, once in finally
    assert mock_killpg.call_count >= 1
    mock_killpg.assert_any_call(1234, signal.SIGTERM)

def test_iteration_cap(mock_config, monkeypatch):
    """Test that the loop respects max_iterations."""
    # Mock all agent calls to return success
    monkeypatch.setattr(ralph_loop, "run_cursor_agent", MagicMock(return_value="success"))
    monkeypatch.setattr(ralph_loop, "get_total_cost", MagicMock(return_value=0.0))
    monkeypatch.setattr(ralph_loop, "get_current_task", MagicMock(return_value="task"))
    monkeypatch.setattr(ralph_loop, "get_project_state_hash", MagicMock(return_value="hash"))
    monkeypatch.setattr(ralph_loop, "check_stagnation", MagicMock(return_value=False))
    monkeypatch.setattr(ralph_loop, "get_file_content", MagicMock(return_value="- [ ] task"))
    monkeypatch.setattr(ralph_loop, "generate_commit_message", MagicMock(return_value="msg"))
    
    # Mock git operations
    mock_run = MagicMock()
    mock_run.returncode = 0
    mock_run.stdout = ""
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: mock_run)
    
    # Mock log_message to track iterations
    log_mock = MagicMock()
    monkeypatch.setattr(ralph_loop, "log_message", log_mock)
    
    # Mock PRD check
    monkeypatch.setattr(os.path, "exists", lambda x: True)
    
    # We need to mock main's dependencies to run it partially
    with patch("argparse.ArgumentParser.parse_args", return_value=MagicMock(prd="prd.md", config="ralph.yaml", model=None, max_spend=None, plan_file=None)):
        with patch("ralph_loop.load_config"):
            with patch("fcntl.flock"):
                with patch("builtins.open", MagicMock()):
                    # Run main but catch SystemExit if any
                    try:
                        ralph_loop.main()
                    except SystemExit:
                        pass
    
    # Check if it stopped at max_iterations (5)
    # The log message "Reached maximum iterations (5). Stopping." should be present
    assert any("Reached maximum iterations (5). Stopping." in str(call) for call in log_mock.call_args_list)

def test_stagnation_on_same_task(mock_config, monkeypatch):
    """Test that stagnation is detected when the same task repeats."""
    history_file = mock_config["state_history_file"]
    
    # Initial history
    with open(history_file, "w") as f:
        json.dump([], f)
        
    # First call
    assert ralph_loop.check_stagnation("hash1", "task1") is False
    # Second call
    assert ralph_loop.check_stagnation("hash2", "task1") is False
    # Third call - should trigger stagnation (threshold 3)
    assert ralph_loop.check_stagnation("hash3", "task1") is True

def test_cost_tracking_parsing(mock_config):
    """Test parsing of token usage from stream-json."""
    stdout = '{"usage": {"input_tokens": 100, "output_tokens": 200}}\n{"other": "data"}\n{"usage": {"input_tokens": 50, "output_tokens": 50}}'
    in_t, out_t = ralph_loop.parse_usage_from_output(stdout)
    assert in_t == 150
    assert out_t == 250

def test_cost_tracking_fallback(mock_config):
    """Test fallback cost estimation."""
    stdout = "This is a plain text output with no JSON usage info."
    in_t, out_t = ralph_loop.parse_usage_from_output(stdout)
    # Conservative estimate: len / 4
    expected = int(len(stdout) / 4)
    assert in_t == expected
    assert out_t == expected
