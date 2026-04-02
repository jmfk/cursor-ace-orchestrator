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
    """Test that ACEService initializes directories correctly."""
    assert service.ace_dir == temp_workspace / ".ace"
    assert service.ace_local_dir == temp_workspace / ".ace-local"
    assert service.sessions_dir == temp_workspace / ".ace/sessions"
    assert service.decisions_dir == temp_workspace / ".ace/decisions"

def test_agent_lifecycle(service):
    """Test agent creation and retrieval."""
    agent = service.create_agent(
        id="test-agent",
        name="Test Agent",
        role="tester",
        responsibilities=["testing"]
    )
    assert agent.id == "test-agent"
    assert agent.role == "tester"
    
    agents_config = service.load_agents()
    assert len(agents_config.agents) == 1
    assert agents_config.agents[0].id == "test-agent"

def test_ownership_resolution(service):
    """Test longest-prefix matching for ownership."""
    service.assign_ownership("src/core", "core-agent")
    service.assign_ownership("src/core/auth", "auth-agent")
    
    assert service.resolve_owner("src/core/utils.py") == "core-agent"
    assert service.resolve_owner("src/core/auth/login.py") == "auth-agent"
    assert service.resolve_owner("src/other") is None

def test_context_building(service, temp_workspace):
    """Test that context is built with relevant sections."""
    # Setup global rules
    service.cursor_rules_dir.mkdir(parents=True)
    (service.cursor_rules_dir / "_global.mdc").write_text("Global rules content")
    
    # Setup agent and playbook
    service.create_agent(id="dev", name="Dev", role="developer")
    playbook_path = temp_workspace / ".cursor/rules/developer.mdc"
    playbook_path.parent.mkdir(parents=True, exist_ok=True)
    playbook_path.write_text("Developer playbook content")
    
    context, resolved_agent_id = service.build_context(path="src/main.py", agent_id="dev")
    
    assert "Global rules content" in context
    assert "Developer playbook content" in context
    assert resolved_agent_id == "dev"

def test_run_agent_task_logging(service, temp_workspace, monkeypatch):
    """Test that run_agent_task logs sessions correctly."""
    def mock_run(*args, **kwargs):
        return MagicMock(returncode=0, stdout="Success", stderr="")
    
    monkeypatch.setattr(subprocess, "run", mock_run)
    
    success = service.run_agent_task(command="echo hello", agent_id="test-agent")
    assert success is True
    
    sessions = list(service.sessions_dir.glob("*.md"))
    assert len(sessions) == 1
    content = sessions[0].read_text()
    assert "echo hello" in content
    assert "Success" in content

def test_sop_generation(service):
    """Test SOP generation for onboarding and PR review."""
    service.create_agent(id="dev", name="Dev", role="developer")
    onboarding_path = service.onboard_agent("dev")
    assert onboarding_path.exists()
    assert "SOP: Agent Onboarding" in onboarding_path.read_text()
    
    review_path = service.review_pr("PR-1", "dev")
    assert review_path.exists()
    assert "SOP: PR Review - PR-1" in review_path.read_text()

def test_google_stitch_integration(service, monkeypatch):
    """Test Google Stitch integration stubs."""
    from ace_lib.stitch import stitch_engine
    
    monkeypatch.setattr(stitch_engine, "generate_mockup", lambda d, a, k: ("http://stitch/1", "code"))
    monkeypatch.setattr(service, "get_stitch_key", lambda: "key")
    
    url = service.ui_mockup("Dashboard", "dev")
    assert url == "http://stitch/1"
    
    mockup_file = service.ace_dir / "ui_mockups" / "1.md"
    assert mockup_file.exists()
    assert "code" in mockup_file.read_text()
