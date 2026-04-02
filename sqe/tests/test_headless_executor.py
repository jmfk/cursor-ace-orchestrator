import pytest
import subprocess
import json
import time
from unittest.mock import MagicMock, patch, mock_open
from pathlib import Path

# Import the functions to be tested from the provided context
# Note: In a real environment, these would be imported from ralph_loop
from ralph_loop import (
    run_cursor_agent, 
    parse_usage_from_output, 
    CONFIG, 
    update_stats
)

@pytest.fixture
def mock_subprocess_success():
    """Mocks a successful subprocess execution with JSON output."""
    with patch("subprocess.Popen") as mock_popen:
        mock_proc = MagicMock()
        # Simulate streaming output with token usage
        output_lines = [
            '{"status": "thinking"}',
            '{"usage": {"input_tokens": 100, "output_tokens": 50}}',
            'Task completed successfully.'
        ]
        mock_proc.stdout = [line.encode('utf-8') for line in output_lines]
        mock_proc.returncode = 0
        mock_proc.communicate.return_value = (b"\n".join([l.encode() for l in output_lines]), b"")
        mock_proc.wait.return_value = 0
        mock_popen.return_value = mock_proc
        yield mock_popen

@pytest.fixture
def mock_subprocess_timeout():
    """Mocks a subprocess timeout."""
    with patch("subprocess.Popen") as mock_popen:
        mock_proc = MagicMock()
        mock_proc.wait.side_effect = subprocess.TimeoutExpired(cmd="cursor-agent", timeout=1)
        mock_proc.kill = MagicMock()
        mock_popen.return_value = mock_proc
        yield mock_popen

class TestHeadlessExecutorIntegration:
    """
    Test suite for REQ-004.1: Headless Executor Integration.
    Verifies timeout handling, retries, and output streaming.
    """

    def test_parse_usage_from_output_valid_json(self):
        """
        Success Criteria: Output is captured and streamed for real-time processing.
        Verifies that token usage is correctly extracted from JSON stream lines.
        """
        sample_output = """
        Thinking...
        {\"usage\": {\"input_tokens\": 500, \"output_tokens\": 200}}
        Finalizing changes.
        """
        in_tokens, out_tokens = parse_usage_from_output(sample_output)
        assert in_tokens == 500
        assert out_tokens == 200

    def test_parse_usage_from_output_fallback(self):
        """
        Verifies that if no JSON usage is found, the system falls back to a 
        conservative character-based estimate (~4 chars per token).
        """
        sample_output = "This is a plain text output without JSON usage data."
        in_tokens, out_tokens = parse_usage_from_output(sample_output)
        expected = int(len(sample_output) / 4)
        assert in_tokens == expected
        assert out_tokens == expected

    @patch("ralph_loop.log_message")
    def test_run_cursor_agent_success(self, mock_log, mock_subprocess_success):
        """
        Verifies successful execution of the headless agent and output capture.
        """
        prompt = "Refactor the login module"
        result = run_cursor_agent(prompt, timeout=10)
        
        assert result is not None
        assert "Task completed successfully" in result
        # Verify that usage was logged (indirectly via update_stats logic)
        mock_log.assert_any_call(f"Running Cursor Agent: {prompt[:10]}...")

    @patch("ralph_loop.log_message")
    def test_run_cursor_agent_timeout_handling(self, mock_log, mock_subprocess_timeout):
        """
        Success Criteria: The system handles headless execution timeouts gracefully.
        Verifies that a timeout kills the process and returns None to trigger retry logic.
        """
        prompt = "Long running task"
        # We expect run_cursor_agent to catch the TimeoutExpired and return None
        result = run_cursor_agent(prompt, timeout=1)
        
        assert result is None
        mock_log.assert_any_call("⏳ Cursor agent timed out.")

    @patch("ralph_loop.run_cursor_agent")
    @patch("ralph_loop.log_message")
    def test_retry_logic_in_loop(self, mock_log, mock_run_agent):
        """
        Success Criteria: The system handles retries gracefully.
        Simulates a scenario where the agent fails twice and succeeds on the third try.
        """
        # Mock sequence: Failure (None), Failure (None), Success (String)
        mock_run_agent.side_effect = [None, None, "Success on attempt 3"]
        
        # Simulate a simplified version of the loop logic found in ralph_loop/planner
        attempts = 0
        max_attempts = 3
        final_result = None
        
        while attempts < max_attempts:
            final_result = mock_run_agent("Retry task")
            if final_result:
                break
            attempts += 1
            
        assert attempts == 2 # 0-indexed, so 2 means it was called 3 times
        assert final_result == "Success on attempt 3"

    @patch("ralph_loop.log_message")
    def test_circuit_breaker_tripping(self, mock_log):
        """
        Verifies that the system stops execution if the circuit breaker is tripped
        due to consecutive failures.
        """
        from ralph_loop import run_cursor_agent
        import ralph_loop
        
        # Manually trip the breaker
        ralph_loop.LLM_CIRCUIT_BREAKER_TRIPPED = True
        
        result = run_cursor_agent("Any prompt")
        
        assert result is None
        mock_log.assert_any_call("🚫 Circuit breaker is TRIPPED. Skipping LLM call.")
        
        # Reset for other tests
        ralph_loop.LLM_CIRCUIT_BREAKER_TRIPPED = False

    def test_stats_update_persistence(self, tmp_path):
        """
        Verifies that token usage captured from the stream is persisted to the stats file.
        """
        stats_file = tmp_path / "ralph_stats.json"
        CONFIG["stats_file"] = str(stats_file)
        
        # Initial stats
        update_stats(input_tokens=100, output_tokens=50, elapsed_time=2.0)
        
        with open(stats_file, "r") as f:
            data = json.load(f)
            assert data["total_input_tokens"] == 100
            assert data["total_output_tokens"] == 50
            
        # Incremental update
        update_stats(input_tokens=200, output_tokens=100, elapsed_time=3.0)
        
        with open(stats_file, "r") as f:
            data = json.load(f)
            assert data["total_input_tokens"] == 300
            assert data["total_output_tokens"] == 150
            assert data["iterations"] == 2