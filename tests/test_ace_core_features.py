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

def test_onboarding_sop_generation(service, temp_workspace):
    """Test Phase 9.5: Formal onboarding SOP generation."""
    agent_id = "auth-expert"
    service.create_agent(
        id=agent_id, 
        name="Aegis", 
        role="auth", 
        responsibilities=["src/auth"]
    )
    
    sop_path = service.onboard_agent(agent_id)
    
    assert sop_path.exists()
    content = sop_path.read_text()
    assert f"SOP: Agent Onboarding - Aegis ({agent_id})" in content
    assert "## 1. Context Acquisition" in content
    assert "## 2. Role-Specific Setup" in content
    
    # Verify mail notification
    messages = service.list_mail(agent_id)
    assert len(messages) == 1
    assert messages[0].subject == "ONBOARDING SOP"

def test_pr_review_sop_generation(service, temp_workspace):
    """Test Phase 9.5: Formal PR review SOP generation."""
    agent_id = "reviewer-agent"
    service.create_agent(id=agent_id, name="Reviewer", role="qa")
    
    review_path = service.review_pr("PR-500", agent_id)
    
    assert review_path.exists()
    content = review_path.read_text()
    assert "SOP: PR Review - PR-500" in content
    assert f"Reviewer**: {agent_id}" in content
    assert "## 3. Security Check" in content
    
    # Verify mail notification
    messages = service.list_mail(agent_id)
    assert len(messages) == 1
    assert messages[0].subject == "PR REVIEW TASK: PR-500"

def test_ui_mockup_integration(service, temp_workspace, monkeypatch):
    """Test Phase 4.5: Google Stitch mockup integration stub."""
    # Mock the stitch engine to avoid real API calls
    import ace_lib.stitch.stitch_engine as stitch_engine
    
    def mock_generate_mockup(description, agent_id, api_key=None):
        return f"https://stitch.google.com/canvas/mock_123", "export const Button = () => <button>Click</button>;"
    
    monkeypatch.setattr(stitch_engine, "generate_mockup", mock_generate_mockup)
    
    url = service.ui_mockup("A simple button", "ui-agent")
    assert url == "https://stitch.google.com/canvas/mock_123"
    
    mockup_file = temp_workspace / ".ace" / "ui_mockups" / "mock_123.md"
    assert mockup_file.exists()
    assert "export const Button" in mockup_file.read_text()

def test_native_loop_command_structure(service, temp_workspace, monkeypatch):
    """Test Phase 4.1: Native ace loop command exists in ACEService."""
    # We just verify the method exists and takes correct arguments
    import inspect
    sig = inspect.signature(service.run_loop)
    assert "prompt" in sig.parameters
    assert "test_cmd" in sig.parameters
    assert "max_iterations" in sig.parameters
