import pytest
import subprocess
import json
import io
from unittest.mock import MagicMock, patch, ANY
from ralph_loop import run_cursor_agent, parse_usage_from_output, CONFIG
import ralph_loop

# --- Fixtures ---

@pytest.fixture
def mock_subprocess_popen():
    with patch("subprocess.Popen") as mock_popen:
        yield mock_popen

@pytest.fixture(autouse=True)
def reset_globals():
    """Reset global state before each test."""
    ralph_loop.LLM_CIRCUIT_BREAKER_TRIPPED = False
    ralph_loop.CONSECUTIVE_FAILURES = 0
    ralph_loop.PAID_ACCOUNT_REQUIRED = False
    # Ensure log file doesn't crash tests if it doesn't exist
    with patch("builtins.open", MagicMock()):
        yield

# --- Test Cases ---

def test_parse_usage_from_output_valid_json():
    """
    Verifies that token usage is correctly extracted from JSON-formatted stream output.
    """
    mock_output = '{"usage": {"input_tokens": 100, "output_tokens": 50}}\nSome other text\n{"usage": {"input_tokens": 10, "output_tokens": 5}}'
    in_tokens, out_tokens = parse_usage_from_output(mock_output)
    assert in_tokens == 110
    assert out_tokens == 55

def test_parse_usage_from_output_fallback():
    """
    Verifies that if no JSON usage is found, the system falls back to a character-based estimate.
    """
    mock_output = "This is a plain text response with no JSON usage data."
    in_tokens, out_tokens = parse_usage_from_output(mock_output)
    # Fallback is len(stdout) / 4
    expected = int(len(mock_output) / 4)
    assert in_tokens == expected
    assert out_tokens == expected

def test_run_cursor_agent_success(mock_subprocess_popen):
    """
    Verifies successful headless execution: 
    1. Command is constructed correctly.
    2. Output is captured and returned.
    3. Consecutive failures are reset.
    """
    # Setup mock process
    mock_process = MagicMock()
    mock_process.stdout = io.BytesIO(b"Line 1\n{\"usage\": {\"input_tokens\": 10, \"output_tokens\": 20}}\n")
    mock_process.returncode = 0
    mock_subprocess_popen.return_value = mock_process

    prompt = "Implement a login feature"
    result = run_cursor_agent(prompt)

    assert "Line 1" in result
    assert ralph_loop.CONSECUTIVE_FAILURES == 0
    mock_subprocess_popen.assert_called_once()
    # Check if --non-interactive is passed (Success Criteria: Headless)
    args, _ = mock_subprocess_popen.call_args
    cmd = args[0]
    assert "cursor-agent" in cmd
    assert "--non-interactive" in cmd

def test_run_cursor_agent_timeout(mock_subprocess_popen):
    """
    Verifies that the system handles headless execution timeouts gracefully.
    Success Criteria: System handles timeouts without crashing and returns None.
    """
    mock_process = MagicMock()
    mock_process.stdout = io.BytesIO(b"Processing...")
    # Simulate timeout on wait()
    mock_process.wait.side_effect = subprocess.TimeoutExpired(cmd="cursor-agent", timeout=300)
    mock_subprocess_popen.return_value = mock_process

    with patch("ralph_loop.log_message") as mock_log:
        result = run_cursor_agent("Slow task", timeout=1)
        
        assert result is None
        # Verify process was killed
        mock_process.kill.assert_called_once()
        # Verify timeout was logged
        mock_log.assert_any_call(ANY) # Should log the timeout error

def test_run_cursor_agent_retry_logic_failure_increment(mock_subprocess_popen):
    """
    Verifies that consecutive failures are tracked when the agent returns a non-zero exit code.
    This supports the 'graceful retry' requirement by allowing the loop to know when to stop or retry.
    """
    mock_process = MagicMock()
    mock_process.stdout = io.BytesIO(b"Error: API Key missing")
    mock_process.returncode = 1
    mock_subprocess_popen.return_value = mock_process

    run_cursor_agent("Failing task")
    
    assert ralph_loop.CONSECUTIVE_FAILURES == 1

def test_run_cursor_agent_circuit_breaker():
    """
    Verifies that the circuit breaker prevents execution if tripped.
    """
    ralph_loop.LLM_CIRCUIT_BREAKER_TRIPPED = True
    
    with patch("subprocess.Popen") as mock_popen:
        result = run_cursor_agent("Any task")
        assert result is None
        mock_popen.assert_not_called()

@patch("ralph_loop.update_stats")
def test_run_cursor_agent_streams_and_updates_stats(mock_update_stats, mock_subprocess_popen):
    """
    Verifies that output is captured and usage stats are updated after execution.
    Success Criteria: Output is captured for real-time processing (simulated by stats update).
    """
    mock_process = MagicMock()
    # Simulate a stream of output
    mock_process.stdout = io.BytesIO(b'Step 1\n{"usage": {"input_tokens": 50, "output_tokens": 50}}\n')
    mock_process.returncode = 0
    mock_subprocess_popen.return_value = mock_process

    run_cursor_agent("Task with stats")

    # Verify stats were updated with the parsed tokens
    mock_update_stats.assert_called_once()
    args, _ = mock_update_stats.call_args
    assert args[0] == 50 # input_tokens
    assert args[1] == 50 # output_tokens
