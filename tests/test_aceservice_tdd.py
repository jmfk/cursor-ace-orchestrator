import pytest
from pathlib import Path
from ace_lib.services.ace_service import ACEService
from ace_lib.models.schemas import TaskType

@pytest.fixture
def temp_workspace(tmp_path):
    """Create a temporary workspace for testing."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return workspace

@pytest.fixture
def service(temp_workspace):
    """Initialize ACEService in a temporary workspace."""
    return ACEService(base_path=temp_workspace)

def test_onboarding_sop_generation(service):
    """Test generating onboarding SOP (Phase 9.5)."""
    service.create_agent(id="dev-1", name="Developer 1", role="developer", responsibilities=["src/core"])
    onboarding_file = service.onboard_agent("dev-1")

    assert onboarding_file.exists()
    content = onboarding_file.read_text()
    assert "SOP: Agent Onboarding - Developer 1 (dev-1)" in content
    assert "## 1. Context Acquisition" in content
    assert "src/core" in content
    
    # Check if memory file was created with correct sections
    memory_file = service.base_path / ".cursor/rules/developer.mdc"
    assert memory_file.exists()
    assert "## Strategier & patterns" in memory_file.read_text()
    assert "## Kända fallgropar" in memory_file.read_text()

def test_pr_review_sop_generation(service):
    """Test generating PR review SOP (Phase 9.5)."""
    review_file = service.review_pr("PR-123", "reviewer-1")
    assert review_file.exists()
    content = review_file.read_text()
    assert "SOP: PR Review - PR-123" in content
    assert "**Reviewer**: reviewer-1" in content
    assert "## 3. Security Check" in content

def test_google_stitch_mockup_logic(service, monkeypatch):
    """Test Google Stitch mockup generation logic (Phase 4.5)."""
    from ace_lib.stitch import stitch_engine

    # Mock generate_mockup
    mock_url = "https://stitch.google.com/canvas/test_mockup"
    mock_code = "export const Mockup = () => <div>Mockup</div>;"
    
    def mock_gen(*args, **kwargs):
        return mock_url, mock_code
        
    monkeypatch.setattr(stitch_engine, "generate_mockup", mock_gen)
    monkeypatch.setattr(service, "get_stitch_key", lambda: "test-key")

    url = service.ui_mockup("Login page", "agent-1")
    assert url == mock_url
    
    mockup_id = url.split("/")[-1]
    mockup_file = service.ace_dir / "ui_mockups" / f"{mockup_id}.md"
    assert mockup_file.exists()
    assert mock_code in mockup_file.read_text()

def test_ralph_loop_basic(service, monkeypatch):
    """Test a basic iteration of the RALPH loop (Phase 4.1)."""
    # Mock build_context to return a simple context
    monkeypatch.setattr(service, "build_context", lambda **kwargs: ("Test Context", "test-agent"))
    
    # Mock subprocess.Popen for the 'run' part of the loop
    import subprocess
    from unittest.mock import MagicMock
    
    mock_process = MagicMock()
    mock_process.stdout = ["Test output line"]
    mock_process.wait.return_value = 0
    mock_process.returncode = 0
    
    def mock_popen(*args, **kwargs):
        return mock_process
        
    monkeypatch.setattr(subprocess, "Popen", mock_popen)
    
    # Mock reflection to avoid LLM call
    monkeypatch.setattr(service, "reflect_on_session", lambda output: "Reflection result")
    monkeypatch.setattr(service, "parse_reflection_output", lambda text: [])
    
    # Run loop with 1 iteration
    success, iterations = service.run_loop(
        prompt="Test task",
        test_cmd="echo 'tests passed'",
        max_iterations=1,
        agent_id="test-agent"
    )
    
    assert iterations == 1
    # Note: success depends on test_cmd exit code which we also need to mock if it's called
    # In ACEService.run_loop, it likely calls subprocess for test_cmd too.
