import pytest
import os
import shutil
from pathlib import Path
from ace_lib.services.ace_service import ACEService
from ace_lib.models.schemas import TaskType, TokenMode, Config

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
    assert service.cursor_rules_dir == temp_workspace / ".cursor" / "rules"

def test_config_management(service):
    """Test loading and saving configuration."""
    config = service.load_config()
    assert config.token_mode == TokenMode.LOW
    
    config.token_mode = TokenMode.HIGH
    service.save_config(config)
    
    service.clear_cache()
    new_config = service.load_config()
    assert new_config.token_mode == TokenMode.HIGH

def test_agent_registry(service):
    """Test creating and loading agents."""
    agent = service.create_agent(
        id="test-agent",
        name="Test Agent",
        role="tester",
        responsibilities=["tests/"]
    )
    assert agent.id == "test-agent"
    assert agent.role == "tester"
    
    agents_config = service.load_agents()
    assert len(agents_config.agents) == 1
    assert agents_config.agents[0].id == "test-agent"

def test_ownership_registry(service):
    """Test assigning and resolving module ownership."""
    service.assign_ownership("src/core", "core-agent")
    service.assign_ownership("src/core/utils", "utils-agent")
    
    assert service.resolve_owner("src/core/main.py") == "core-agent"
    assert service.resolve_owner("src/core/utils/helper.py") == "utils-agent"
    assert service.resolve_owner("src/other") is None

def test_context_building_basic(service):
    """Test building context with global rules and task framing."""
    service.cursor_rules_dir.mkdir(parents=True, exist_ok=True)
    (service.cursor_rules_dir / "_global.mdc").write_text("Global Rule Content")
    
    context, agent_id = service.build_context(path="src/app.py", task_type=TaskType.IMPLEMENT)
    
    assert "Global Rule Content" in context
    assert "TASK FRAMING" in context
    assert "implementing new functionality" in context

def test_adr_management(service):
    """Test adding and listing ADRs."""
    service.add_decision(
        title="Use FastAPI",
        context="Need a web framework",
        decision="Use FastAPI for the backend",
        consequences="Fast development"
    )
    
    decisions = service.list_decisions()
    assert len(decisions) == 1
    assert decisions[0].title == "Use FastAPI"
    assert decisions[0].id == "ADR-001"

def test_mail_system(service):
    """Test sending and reading mail between agents."""
    service.send_mail(
        to_agent="agent-b",
        from_agent="agent-a",
        subject="Hello",
        body="Test message"
    )
    
    messages = service.list_mail("agent-b")
    assert len(messages) == 1
    assert messages[0].subject == "Hello"
    assert messages[0].from_agent == "agent-a"
    
    msg = service.read_mail("agent-b", messages[0].id)
    assert msg.body == "Test message"
    assert msg.status == "read"

def test_macp_proposal_lifecycle(service):
    """Test creating and listing MACP proposals."""
    proposal = service.create_macp_proposal(
        proposer_id="agent-a",
        title="New Feature",
        description="Let's add X",
        agent_ids=["agent-b"]
    )
    
    assert proposal.id.startswith("MACP-")
    assert proposal.proposer_id == "agent-a"
    
    proposals = service.list_macp_proposals()
    assert len(proposals) == 1
    assert proposals[0].id == proposal.id

def test_rbac_restrictions(service, monkeypatch):
    """Test RBAC path and command restrictions."""
    service.create_agent(
        id="restricted-agent",
        name="Restricted",
        role="dev",
        allowed_paths=["src/allowed"],
        forbidden_commands=["rm -rf"]
    )
    
    # Mock subprocess.run to avoid actual execution
    class MockProcess:
        returncode = 0
        stdout = "Success"
        stderr = ""
    
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: MockProcess())
    
    # Test allowed path
    assert service.run_agent_task(
        command="ls",
        path="src/allowed/file.py",
        agent_id="restricted-agent"
    ) is True
    
    # Test forbidden path
    assert service.run_agent_task(
        command="ls",
        path="src/forbidden/file.py",
        agent_id="restricted-agent"
    ) is False
    
    # Test forbidden command
    assert service.run_agent_task(
        command="rm -rf /",
        path="src/allowed/file.py",
        agent_id="restricted-agent"
    ) is False
