import pytest
import subprocess
from unittest.mock import MagicMock
from ace_lib.services.ace_service import ACEService

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

def test_aceservice_initialization(service, temp_workspace):
    """Test that ACEService initializes with correct paths."""
    assert service.base_path == temp_workspace
    assert service.ace_dir == temp_workspace / ".ace"
    assert service.cursor_rules_dir == temp_workspace / ".cursor" / "rules"

def test_agent_onboarding_sop(service):
    """Test generating onboarding SOP (Phase 9.5)."""
    service.create_agent(id="dev-1", name="Developer 1", role="developer")
    onboarding_file = service.onboard_agent("dev-1")

    assert onboarding_file.exists()
    content = onboarding_file.read_text()
    assert "SOP: Agent Onboarding - Developer 1 (dev-1)" in content
    assert "## 1. Context Acquisition" in content
    
    # Check if memory file was created
    memory_file = service.base_path / ".cursor/rules/developer.mdc"
    assert memory_file.exists()
    assert "# Developer 1 Playbook (developer)" in memory_file.read_text()

def test_pr_review_sop(service):
    """Test generating PR review SOP (Phase 9.5)."""
    review_file = service.review_pr("PR-123", "reviewer-1")
    assert review_file.exists()
    content = review_file.read_text()
    assert "SOP: PR Review - PR-123" in content
    assert "**Reviewer**: reviewer-1" in content

def test_ralph_loop_native_integration(service, monkeypatch):
    """Test native RALPH loop integration (Phase 4.1)."""
    def mock_run(cmd, shell=True, capture_output=True, text=True, env=None, **kwargs):
        mock_res = MagicMock()
        if "cursor-agent" in cmd:
            mock_res.returncode = 0
            mock_res.stdout = "Agent success output"
            mock_res.stderr = ""
        elif "pytest" in cmd:
            mock_res.returncode = 0
            mock_res.stdout = "Test success output"
            mock_res.stderr = ""
        return mock_res

    monkeypatch.setattr(subprocess, "run", mock_run)
    
    # Mock reflection and LLM client
    monkeypatch.setattr(service, "get_anthropic_client", lambda: MagicMock())
    monkeypatch.setattr(service, "reflect_on_session", lambda x: "[str-001] helpful=1 harmful=0 :: New strategy")
    
    # Setup agent
    service.create_agent(id="dev-1", name="Dev 1", role="developer")
    
    success, iterations = service.run_loop(
        prompt="Implement feature X",
        test_cmd="pytest",
        max_iterations=1,
        agent_id="dev-1"
    )
    
    assert success is True
    assert iterations == 1
    
    # Verify session was logged
    sessions = list(service.sessions_dir.glob("*.md"))
    assert len(sessions) > 0

def test_google_stitch_mockup_integration(service, monkeypatch):
    """Test Google Stitch mockup generation (Phase 4.5)."""
    from ace_lib.stitch import stitch_engine

    mock_url = "https://stitch.google.com/canvas/test_mockup"
    mock_code = "export const Mockup = () => <div>Mockup</div>;"
    
    monkeypatch.setattr(stitch_engine, "generate_mockup", lambda *args, **kwargs: (mock_url, mock_code))
    monkeypatch.setattr(stitch_engine, "extract_components", lambda *args, **kwargs: {"Mockup": mock_code})
    monkeypatch.setattr(service, "get_stitch_key", lambda: "test-key")

    url = service.ui_mockup("Login page", "agent-1")
    assert url == mock_url
    
    mockup_id = url.split("/")[-1]
    mockup_file = service.ace_dir / "ui_mockups" / f"{mockup_id}.md"
    assert mockup_file.exists()
    assert "export const Mockup" in mockup_file.read_text()
