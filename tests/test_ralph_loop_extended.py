import pytest
from ace_lib.services.ace_service import ACEService
from ace_lib.models.schemas import TaskType

@pytest.fixture
def service(tmp_path):
    """Initialize ACEService in a temporary workspace."""
    return ACEService(base_path=tmp_path)

def test_ralph_loop_stagnation_detection(service, monkeypatch):
    """Test that RALPH loop detects stagnation when git state doesn't change."""
    import subprocess
    from unittest.mock import MagicMock

    # Mock subprocess.run
    def mock_run(cmd, *args, **kwargs):
        mock_res = MagicMock()
        if isinstance(cmd, list) and "status" in cmd:
            # Return same git status every time to trigger stagnation
            mock_res.stdout = "M file1.py\n"
            mock_res.returncode = 0
        elif "cursor-agent" in str(cmd):
            mock_res.stdout = "Agent output"
            mock_res.returncode = 0
        elif "pytest" in str(cmd):
            mock_res.stdout = "Tests failed"
            mock_res.returncode = 1 # Keep failing to continue loop
        else:
            mock_res.stdout = ""
            mock_res.returncode = 0
        return mock_res

    monkeypatch.setattr(subprocess, "run", mock_run)
    
    # Mock other dependencies
    monkeypatch.setattr(service, "get_anthropic_client", lambda: None)
    monkeypatch.setattr(service, "run_agent_task", lambda *args, **kwargs: True)

    # We need to capture the prompt passed to build_context to see if it contains STAGNATION
    prompts_captured = []
    
    def mock_build_context(path=None, task_type=TaskType.IMPLEMENT, agent_id=None, task_description=None):
        if task_description:
            prompts_captured.append(task_description)
        return "context", agent_id

    monkeypatch.setattr(service, "build_context", mock_build_context)

    # Run loop for 5 iterations
    success, iterations = service.run_loop(
        prompt="Fix bug",
        test_cmd="pytest",
        max_iterations=5,
        max_spend=10.0
    )

    assert success is False
    assert iterations == 5
    # Stagnation should be detected after 3 identical states
    assert any("STAGNATION DETECTED" in p for p in prompts_captured)

def test_ralph_loop_spending_limit(service, monkeypatch):
    """Test that RALPH loop respects the spending limit."""
    import subprocess
    from unittest.mock import MagicMock

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: MagicMock(returncode=1, stdout="fail"))
    monkeypatch.setattr(service, "run_agent_task", lambda *args, **kwargs: True)
    monkeypatch.setattr(service, "get_anthropic_client", lambda: None)

    # Run loop with very low spend limit
    success, iterations = service.run_loop(
        prompt="Fix bug",
        test_cmd="pytest",
        max_iterations=10,
        max_spend=0.0000001 # Extremely low
    )

    assert success is False
    # Should stop after first iteration or even before
    assert iterations <= 1
