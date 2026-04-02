import pytest
import subprocess
from ace_lib.services.ace_service import ACEService


@pytest.fixture
def ace_service(tmp_path):
    """Create a temporary ACE service for testing."""
    service = ACEService(tmp_path)
    service.ace_dir.mkdir(parents=True, exist_ok=True)
    service.cursor_rules_dir.mkdir(parents=True, exist_ok=True)
    for subdir in ["mail", "sessions", "decisions", "specs"]:
        (service.ace_dir / subdir).mkdir(parents=True, exist_ok=True)
    return service


def test_ralph_loop_integration(ace_service, monkeypatch):
    """Test the native RALPH loop integration in ace.py via a mock."""
    # 1. Setup agent and playbook
    agent_id = "loop-agent"
    ace_service.create_agent(id=agent_id, name="Loop Agent", role="tester")
    playbook_path = ace_service.cursor_rules_dir / "tester.mdc"
    playbook_path.write_text("# Loop Agent Playbook\n## Strategier & patterns\n")

    # 2. Mock subprocess.run to simulate cursor-agent and test command
    def mock_run(cmd, shell=True, capture_output=True, text=True, env=None):
        class MockResult:
            def __init__(self, stdout, stderr, returncode):
                self.stdout = stdout
                self.stderr = stderr
                self.returncode = returncode

        if "cursor-agent" in cmd:
            return MockResult("Agent successfully implemented the fix.", "", 0)
        elif "pytest" in cmd:
            return MockResult("Tests passed!", "", 0)
        return MockResult("", "", 0)

    monkeypatch.setattr(subprocess, "run", mock_run)

    # 3. Mock reflect_on_session to avoid Anthropic API call
    monkeypatch.setattr(
        ace_service,
        "reflect_on_session",
        lambda x: "[str-NEW] helpful=1 harmful=0 :: New learning",
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    # 4. Run the loop via the service method (which ace.py calls)
    # We use a dummy plan.md
    plan_path = ace_service.base_path / "plan.md"
    plan_path.write_text("- [ ] Fix the bug")

    success, iterations = ace_service.run_loop(
        prompt="Fix the bug",
        test_cmd="pytest",
        max_iterations=2,
        agent_id=agent_id,
        plan_file=str(plan_path),
    )

    # 5. Verify results
    assert success is True
    assert iterations == 1

    # Check if session was logged
    sessions = list(ace_service.sessions_dir.glob("*.md"))
    assert len(sessions) > 0

    # Check if playbook was updated
    content = playbook_path.read_text()
    assert "[str-001]" in content
    assert "New learning" in content
