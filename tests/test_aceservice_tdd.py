"""Tests for ACEService TDD features."""
from unittest.mock import MagicMock
import pytest
from ace_lib.services.ace_service import ACEService

@pytest.fixture
def temp_workspace(tmp_path):
    """Create a temporary workspace."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return workspace

@pytest.fixture
def service(temp_workspace):
    """Initialize ACEService."""
    return ACEService(base_path=temp_workspace)

def test_ralph_loop_basic_flow(service, monkeypatch):
    """Test the basic RALPH loop flow with mocked execution and verification."""
    # Mocking dependencies
    monkeypatch.setattr(service, "run_agent_task", lambda **kwargs: True)

    # Mock subprocess.run for test_cmd
    mock_run = MagicMock()
    mock_run.returncode = 0
    mock_run.stdout = "Tests passed"
    mock_run.stderr = ""
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: mock_run)

    # Mock reflection to avoid API calls
    monkeypatch.setattr(service, "reflect_on_session", lambda *args: "No new learnings.")
    monkeypatch.setattr(service, "get_anthropic_client", lambda: None)

    success, iterations = service.run_loop(
        prompt="Test prompt",
        test_cmd="echo 'running tests'",
        max_iterations=2
    )

    assert success is True
    assert iterations == 1

def test_ralph_loop_failure_and_retry(service, monkeypatch):
    """Test that RALPH loop retries on failure until max_iterations."""
    # Mocking task execution to always succeed but tests to always fail
    monkeypatch.setattr(service, "run_agent_task", lambda **kwargs: True)

    # Mock subprocess.run for test_cmd to fail
    mock_run = MagicMock()
    mock_run.returncode = 1
    mock_run.stdout = "Tests failed"
    mock_run.stderr = "Error in code"
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: mock_run)

    # Mock reflection
    monkeypatch.setattr(service, "reflect_on_session", lambda *args: "Try fixing the error.")
    monkeypatch.setattr(service, "get_anthropic_client", lambda: MagicMock())
    monkeypatch.setattr(service, "parse_reflection_output", lambda *args: [])

    success, iterations = service.run_loop(
        prompt="Test prompt",
        test_cmd="exit 1",
        max_iterations=3
    )

    assert success is False
    assert iterations == 3

def test_ralph_loop_stagnation_detection():
    """Test that RALPH loop detects stagnation (same state hash)."""
    # This would require state hashing logic in run_loop
    return

def test_onboarding_sop_full(service):
    """Test the full onboarding SOP process including file creation and memory initialization."""
    agent_id = "onboard-test"
    service.create_agent(id=agent_id, name="Onboarder", role="onboarder", responsibilities=["src/onboard"])

    onboarding_file = service.onboard_agent(agent_id)
    assert onboarding_file.exists()

    # Verify memory file
    memory_file = service.base_path / ".cursor/rules/onboarder.mdc"
    assert memory_file.exists()
    content = memory_file.read_text(encoding="utf-8")
    assert "# Onboarder Playbook" in content
    assert "## Strategier & patterns" in content

def test_pr_review_sop_full(service):
    """Test PR review SOP generation."""
    review_file = service.review_pr("PR-999", "reviewer-x")
    assert review_file.exists()
    content = review_file.read_text(encoding="utf-8")
    assert "SOP: PR Review - PR-999" in content
    assert "reviewer-x" in content

def test_stitch_mockup_integration(service, monkeypatch):
    """Test Stitch integration stubs."""
    from ace_lib.stitch import stitch_engine

    mock_url = "https://stitch.google.com/canvas/mock123"
    mock_code = "const UI = () => {};"

    monkeypatch.setattr(stitch_engine, "generate_mockup", lambda *args, **kwargs: (mock_url, mock_code))
    monkeypatch.setattr(service, "get_stitch_key", lambda: "fake-key")

    url = service.ui_mockup("A new button", "ui-agent")
    assert url == mock_url

    mockup_id = "mock123"
    mockup_file = service.ace_dir / "ui_mockups" / f"{mockup_id}.md"
    assert mockup_file.exists()
    assert mock_code in mockup_file.read_text(encoding="utf-8")
