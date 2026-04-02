import pytest
import subprocess
from ace_lib.services.ace_service import ACEService


@pytest.fixture
def ace_service(tmp_path):
    """Create a temporary ACE service for testing."""
    service = ACEService(tmp_path)
    service.ace_dir.mkdir(parents=True, exist_ok=True)
    service.cursor_rules_dir.mkdir(parents=True, exist_ok=True)
    return service


def test_run_loop_success(ace_service, monkeypatch):
    """Test RALPH loop success flow."""

    # Mock subprocess.run for agent and tests
    def mock_run(cmd, shell=True, capture_output=True, text=True, env=None):
        class MockResult:
            def __init__(self, returncode, stdout, stderr=""):
                self.returncode = returncode
                self.stdout = stdout
                self.stderr = stderr

        if "cursor-agent" in cmd:
            return MockResult(0, "Agent finished task.")
        elif "pytest" in cmd:
            return MockResult(0, "Tests passed.")
        return MockResult(0, "")

    monkeypatch.setattr(subprocess, "run", mock_run)
    monkeypatch.setattr(ace_service, "get_anthropic_client", lambda: None)

    success, iterations = ace_service.run_loop(
        prompt="Test prompt", test_cmd="pytest", max_iterations=2
    )

    assert success is True
    assert iterations == 1
    # Check if session was logged
    sessions = list(ace_service.sessions_dir.glob("*.md"))
    assert len(sessions) == 1


def test_run_loop_failure_then_success(ace_service, monkeypatch):
    """Test RALPH loop recovery after failure."""
    call_count = {"test": 0}

    def mock_run(cmd, shell=True, capture_output=True, text=True, env=None):
        class MockResult:
            def __init__(self, returncode, stdout, stderr=""):
                self.returncode = returncode
                self.stdout = stdout
                self.stderr = stderr

        if "cursor-agent" in cmd:
            return MockResult(0, "Agent attempt.")
        elif "pytest" in cmd:
            call_count["test"] += 1
            if call_count["test"] == 1:
                return MockResult(1, "Tests failed.")
            return MockResult(0, "Tests passed.")
        return MockResult(0, "")

    monkeypatch.setattr(subprocess, "run", mock_run)
    monkeypatch.setattr(ace_service, "get_anthropic_client", lambda: None)

    success, iterations = ace_service.run_loop(
        prompt="Test prompt", test_cmd="pytest", max_iterations=3
    )

    assert success is True
    assert iterations == 2
    assert call_count["test"] == 2


def test_sop_onboarding_logic(ace_service):
    """Test onboarding SOP logic."""
    agent = ace_service.create_agent(id="a1", name="Agent 1", role="coder")
    sop_path = ace_service.onboard_agent("a1")

    assert sop_path.exists()
    content = sop_path.read_text()
    assert "SOP: Agent Onboarding" in content
    assert "Agent 1" in content

    # Verify memory file was initialized
    memory_path = ace_service.base_path / agent.memory_file
    assert memory_path.exists()
    assert "## Strategier & patterns" in memory_path.read_text()


def test_stitch_mockup_logic(ace_service, monkeypatch):
    """Test Google Stitch mockup logic."""

    def mock_run(cmd, shell=True, capture_output=True, text=True, env=None):
        class MockResult:
            stdout = "```tsx\nexport const MyComponent = () => <div>Test</div>;\n```"
            returncode = 0

        return MockResult()

    monkeypatch.setattr(subprocess, "run", mock_run)
    monkeypatch.setattr(ace_service, "get_stitch_key", lambda: None)
    monkeypatch.setenv("STITCH_TEST_NO_BYPASS", "1")

    url = ace_service.ui_mockup("A test UI", "a1")
    assert "stitch.google.com" in url

    mockup_id = url.split("/")[-1]
    mockup_file = ace_service.ace_dir / "ui_mockups" / f"{mockup_id}.md"
    assert mockup_file.exists()
    assert "export const MyComponent" in mockup_file.read_text()
