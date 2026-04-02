import pytest
import subprocess
import json
import io
import os
from unittest.mock import MagicMock, patch, ANY

# Import the logic from the provided context
# In a real environment, ensure ralph_loop is in the PYTHONPATH
import ralph_loop
from ralph_loop import (
    run_cursor_agent, 
    parse_usage_from_output, 
    CONFIG, 
    DEFAULTS
)

# --- Fixtures ---

@pytest.fixture(autouse=True)
def reset_global_state():
    """Resets the global state of ralph_loop before each test to ensure isolation."""
    ralph_loop.LLM_CIRCUIT_BREAKER_TRIPPED = False
    ralph_loop.CONSECUTIVE_FAILURES = 0
    ralph_loop.PAID_ACCOUNT_REQUIRED = False
    # Reset config to defaults
    ralph_loop.CONFIG = DEFAULTS.copy()
    yield

@pytest.fixture
def mock_popen():
    """Fixture to mock subprocess.Popen."""
    with patch("subprocess.Popen") as mock:
        yield mock

# --- Test Cases ---

class TestHeadlessExecutor:

    def test_parse_usage_from_output_json_stream(self):
        """
        Verifies that token usage is correctly extracted from a stream of JSON objects.
        Success Criteria: Output is captured and processed for real-time usage tracking.
        """
        stream_output = (
            '{"status": "thinking"}\n'
            '{"usage": {"input_tokens": 1200, "output_tokens": 450}}\n'
            '{"status": "completed"}\n'
        )
        in_tokens, out_tokens = parse_usage_from_output(stream_output)
        
        assert in_tokens == 1200
        assert out_tokens == 450

    def test_parse_usage_from_output_fallback(self):
        """
        Verifies that if no JSON usage is found, the system falls back to a 
        conservative character-based estimate (~4 chars per token).
        """
        plain_text = "The quick brown fox jumps over the lazy dog."
        in_tokens, out_tokens = parse_usage_from_output(plain_text)
        
        expected = int(len(plain_text) / 4)
        assert in_tokens == expected
        assert out_tokens == expected

    def test_run_cursor_agent_success(self, mock_popen):
        """
        Verifies successful execution of the headless agent.
        Checks: Command construction, output capture, and failure counter reset.
        """
        # Setup mock process
        mock_proc = MagicMock()
        mock_proc.stdout = io.StringIO('{"usage": {"input_tokens": 10, "output_tokens": 10}}\nDone.')
        mock_proc.stderr = io.StringIO("")
        mock_proc.returncode = 0
        mock_proc.poll.return_value = 0
        mock_proc.communicate.return_value = ("Done.", "")
        mock_popen.return_value = mock_proc

        # Set a dummy API key
        with patch.dict(os.environ, {"CURSOR_API_KEY": "test-key"}):
            prompt = "Create a unit test for the auth module."
            result = run_cursor_agent(prompt)

        assert result is not None
        # Verify command arguments
        args, kwargs = mock_popen.call_args
        cmd = args[0]
        assert "cursor-agent" in cmd
        assert "--api-key" in cmd
        assert "test-key" in cmd
        assert prompt in cmd
        
        # Verify state
        assert ralph_loop.CONSECUTIVE_FAILURES == 0

    def test_run_cursor_agent_timeout_graceful_handling(self, mock_popen):
        """
        Success Criteria: The system handles headless execution timeouts gracefully.
        Verifies that a TimeoutExpired exception kills the process and returns None.
        """
        mock_proc = MagicMock()
        # Simulate timeout during communicate
        mock_proc.communicate.side_effect = subprocess.TimeoutExpired(cmd="cursor-agent", timeout=300)
        mock_popen.return_value = mock_proc

        with patch("ralph_loop.log_message") as mock_log:
            result = run_cursor_agent("Infinite loop task", timeout=1)

            assert result is None
            # Verify process was terminated
            mock_proc.kill.assert_called_once()
            mock_log.assert_any_call("⏳ Cursor agent timed out.")

    def test_run_cursor_agent_retry_logic_failure_tracking(self, mock_popen):
        """
        Verifies that consecutive failures are tracked to allow the loop to exit or retry.
        """
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.poll.return_value = 1
        mock_proc.communicate.return_value = ("", "Error: API Connection Failed")
        mock_popen.return_value = mock_proc

        # First failure
        run_cursor_agent("Failing task")
        assert ralph_loop.CONSECUTIVE_FAILURES == 1

        # Second failure
        run_cursor_agent("Failing task again")
        assert ralph_loop.CONSECUTIVE_FAILURES == 2

    def test_circuit_breaker_prevents_execution(self, mock_popen):
        """
        Verifies that if the circuit breaker is tripped (due to too many failures),
        no further headless calls are attempted.
        """
        ralph_loop.LLM_CIRCUIT_BREAKER_TRIPPED = True
        
        result = run_cursor_agent("Should not run")
        
        assert result is None
        mock_popen.assert_not_called()

    @patch("ralph_loop.update_stats")
    def test_real_time_stats_integration(self, mock_update_stats, mock_popen):
        """
        Verifies that output is captured and usage stats are updated immediately after execution.
        This ensures the write-back pipeline receives the necessary token data.
        """
        mock_proc = MagicMock()
        # Simulate output with specific token counts
        output = '{"usage": {"input_tokens": 500, "output_tokens": 250}}\nSuccess.'
        mock_proc.stdout = io.StringIO(output)
        mock_proc.returncode = 0
        mock_proc.poll.return_value = 0
        mock_proc.communicate.return_value = (output, "")
        mock_popen.return_value = mock_proc

        run_cursor_agent("Task with usage")

        # Verify update_stats was called with parsed tokens
        # Note: elapsed_time is dynamic, so we use ANY for the third arg
        mock_update_stats.assert_called_once_with(500, 250, ANY)

    def test_run_cursor_agent_handles_missing_api_key(self, mock_popen):
        """
        Verifies that the system still attempts to run even if the env var is missing,
        passing an empty string to the CLI as per implementation.
        """
        with patch.dict(os.environ, {}, clear=True):
            mock_proc = MagicMock()
            mock_proc.returncode = 0
            mock_proc.communicate.return_value = ("OK", "")
            mock_popen.return_value = mock_proc
            
            run_cursor_agent("Test prompt")
            
            args, _ = mock_popen.call_args
            cmd = args[0]
            # Find index of --api-key and check next element
            idx = cmd.index("--api-key")
            assert cmd[idx+1] == ""