import pytest
from unittest.mock import MagicMock, patch
from ace_lib.services.ace_service import ACEService

@pytest.fixture
def temp_workspace(tmp_path):
    """Create a temporary workspace for testing."""
    workspace = tmp_path / "ace_test_ws"
    workspace.mkdir()
    return workspace

@pytest.fixture
def service(temp_workspace):
    """Initialize ACEService in a temporary workspace."""
    return ACEService(base_path=temp_workspace)

def test_service_initialization(service, temp_workspace):
    """Test that ACEService initializes with correct paths."""
    assert service.base_path == temp_workspace
    assert service.ace_dir == temp_workspace / ".ace"
    assert service.ace_local_dir == temp_workspace / ".ace-local"
    assert service.cursor_rules_dir == temp_workspace / ".cursor" / "rules"

def test_agent_lifecycle(service):
    """Test creating, loading, and listing agents."""
    agent_id = "test-agent-1"
    service.create_agent(
        id=agent_id,
        name="Test Agent",
        role="tester",
        email="test@ace.local",
        responsibilities=["testing", "validation"]
    )
    
    agents_config = service.load_agents()
    assert len(agents_config.agents) == 1
    assert agents_config.agents[0].id == agent_id
    assert agents_config.agents[0].role == "tester"
    
    # Test duplicate ID error
    with pytest.raises(ValueError, match=f"Agent with ID {agent_id} already exists"):
        service.create_agent(id=agent_id, name="Duplicate", role="none")

def test_ownership_registry(service):
    """Test assigning and resolving path ownership."""
    service.assign_ownership("src/auth", "auth-agent")
    service.assign_ownership("src/auth/utils", "utils-agent")
    
    # Longest prefix match
    assert service.resolve_owner("src/auth/login.ts") == "auth-agent"
    assert service.resolve_owner("src/auth/utils/crypto.ts") == "utils-agent"
    assert service.resolve_owner("src/api/main.py") is None

def test_sop_generation(service):
    """Test generating various SOPs."""
    service.create_agent(id="dev-1", name="Dev One", role="developer")
    
    # Onboarding SOP
    onboarding_path = service.onboard_agent("dev-1")
    assert onboarding_path.exists()
    assert "SOP: Agent Onboarding - Dev One (dev-1)" in onboarding_path.read_text()
    
    # PR Review SOP
    review_path = service.review_pr("PR-101", "dev-1")
    assert review_path.exists()
    assert "SOP: PR Review - PR-101" in review_path.read_text()
    
    # Audit SOP
    audit_path = service.audit_agent("dev-1")
    assert audit_path.exists()
    assert "SOP: Agent Audit - Dev One (dev-1)" in audit_path.read_text()

def test_mail_system(service):
    """Test the internal messaging system."""
    service.send_mail(
        to_agent="recipient",
        from_agent="sender",
        subject="Test Subject",
        body="Test Body"
    )
    
    messages = service.list_mail("recipient")
    assert len(messages) == 1
    assert messages[0].subject == "Test Subject"
    
    msg = service.read_mail("recipient", messages[0].id)
    assert msg.body == "Test Body"
    assert msg.status == "read"

def test_decision_records(service):
    """Test Architectural Decision Records (ADRs)."""
    service.add_decision(
        title="Use SQLite",
        context="Local storage needed",
        decision="Use SQLite for metadata",
        consequences="Easy to track in git",
        agent_id="arch-1"
    )
    
    decisions = service.list_decisions()
    assert len(decisions) == 1
    assert decisions[0].title == "Use SQLite"
    assert decisions[0].id == "ADR-001"

@patch("subprocess.run")
def test_rolf_loop_success(mock_run, service, temp_workspace):
    """Test successful ROLF loop execution."""
    # Mock successful agent run
    mock_agent_res = MagicMock()
    mock_agent_res.returncode = 0
    mock_agent_res.stdout = "Agent finished task"
    mock_agent_res.stderr = ""
    
    # Mock successful test run
    mock_test_res = MagicMock()
    mock_test_res.returncode = 0
    mock_test_res.stdout = "Tests passed"
    mock_test_res.stderr = ""
    
    # mock_run will be called:
    # 1. Inside run_agent_task (executing cursor-agent)
    # 2. Inside run_loop (executing test_cmd)
    mock_run.side_effect = [mock_agent_res, mock_test_res]
    
    # Setup dummy files - use filenames that won't trigger analysis step
    (temp_workspace / "other_plan.md").write_text("# Plan")
    (temp_workspace / "other_prd.md").write_text("# PRD")
    
    success, iterations = service.run_loop(
        prompt="Test task",
        test_cmd="pytest",
        max_iterations=1,
        plan_file="other_plan.md",
        prd_path="other_prd.md"
    )
    
    assert success is True
    assert iterations == 1

def test_stitch_integration_stubs(service):
    """Test Google Stitch integration stubs."""
    # Mocking environment for Stitch
    with patch("ace_lib.stitch.stitch_engine.generate_mockup") as mock_gen:
        mock_gen.return_value = ("https://stitch.google.com/canvas/test", "// Code")
        url = service.ui_mockup("Dashboard", "ui-agent")
        assert url == "https://stitch.google.com/canvas/test"
        
    with patch("ace_lib.stitch.stitch_engine.sync_mockup") as mock_sync:
        mock_sync.return_value = "// Updated Code"
        code = service.ui_sync("https://stitch.google.com/canvas/test")
        assert code == "// Updated Code"
