import pytest
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

def test_service_initialization(service, temp_workspace):
    """Test that ACEService initializes correctly and creates necessary directories."""
    assert service.base_path == temp_workspace
    assert service.ace_dir == temp_workspace / ".ace"
    assert service.ace_local_dir == temp_workspace / ".ace-local"
    # Directories are created on demand or during init, but let's check if they exist after some operations
    service.create_agent(id="test-agent", name="Test Agent", role="tester")
    assert (service.ace_dir / "agents.yaml").exists()

def test_agent_lifecycle(service):
    """Test creating and retrieving agents."""
    agent = service.create_agent(
        id="dev-1", 
        name="Developer One", 
        role="developer", 
        responsibilities=["src/core"]
    )
    assert agent.id == "dev-1"
    assert agent.name == "Developer One"
    
    agents_config = service.load_agents()
    assert len(agents_config.agents) == 1
    assert agents_config.agents[0].id == "dev-1"

def test_ownership_resolution(service):
    """Test assigning and resolving ownership using longest-prefix matching."""
    service.assign_ownership("src/auth", "auth-agent")
    service.assign_ownership("src/auth/providers", "provider-agent")
    
    assert service.resolve_owner("src/auth/login.ts") == "auth-agent"
    assert service.resolve_owner("src/auth/providers/google.ts") == "provider-agent"
    assert service.resolve_owner("src/other/file.ts") is None

def test_onboarding_sop(service):
    """Test generating onboarding SOP and verifying memory file creation."""
    service.create_agent(id="dev-1", name="Developer 1", role="developer", responsibilities=["src/core"])
    onboarding_file = service.onboard_agent("dev-1")
    
    assert onboarding_file.exists()
    content = onboarding_file.read_text()
    assert "SOP: Agent Onboarding - Developer 1 (dev-1)" in content
    
    # Check if memory file was created
    memory_file = service.base_path / ".cursor/rules/developer.mdc"
    assert memory_file.exists()
    assert "# Developer 1 Playbook (developer)" in memory_file.read_text()

def test_pr_review_sop(service):
    """Test generating PR review SOP."""
    review_file = service.review_pr("PR-101", "reviewer-1")
    assert review_file.exists()
    content = review_file.read_text()
    assert "SOP: PR Review - PR-101" in content
    assert "Reviewer**: reviewer-1" in content

def test_context_building(service):
    """Test building context for an agent task."""
    service.create_agent(id="auth-agent", name="Auth Agent", role="auth")
    service.assign_ownership("src/auth", "auth-agent")
    
    # Create a dummy playbook
    playbook_path = service.base_path / ".cursor/rules/auth.mdc"
    playbook_path.parent.mkdir(parents=True, exist_ok=True)
    playbook_path.write_text("Auth strategies here.")
    
    context, agent_id = service.build_context(path="src/auth/login.ts", task_type=TaskType.IMPLEMENT)
    
    assert agent_id == "auth-agent"
    assert "Auth strategies here." in context
    assert "You are implementing new functionality" in context
