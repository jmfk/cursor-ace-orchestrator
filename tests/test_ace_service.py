import pytest
from ace_lib.services.ace_service import ACEService
from ace_lib.models.schemas import TokenMode, TaskType

@pytest.fixture
def temp_ace_dir(tmp_path):
    """Create a temporary .ace directory for testing."""
    ace_dir = tmp_path / ".ace"
    ace_dir.mkdir()
    return tmp_path


@pytest.fixture
def service(temp_ace_dir):
    return ACEService(base_path=temp_ace_dir)


def test_config_management(service):
    # Test default config
    config = service.load_config()
    assert config.token_mode == TokenMode.LOW

    # Test saving and loading config
    config.token_mode = TokenMode.HIGH
    service.save_config(config)
    
    loaded_config = service.load_config()
    assert loaded_config.token_mode == TokenMode.HIGH


def test_agent_management(service):
    # Test creating an agent
    agent = service.create_agent(id="test-agent", name="Test Agent", role="tester")
    assert agent.id == "test-agent"
    assert agent.name == "Test Agent"
    assert agent.role == "tester"
    assert agent.email == "test-agent@ace.local"
    assert agent.memory_file == ".cursor/rules/tester.mdc"

    # Test loading agents
    agents_config = service.load_agents()
    assert len(agents_config.agents) == 1
    assert agents_config.agents[0].id == "test-agent"

    # Test duplicate agent ID
    with pytest.raises(ValueError, match="Agent with ID test-agent already exists"):
        service.create_agent(id="test-agent", name="Duplicate", role="tester")


def test_ownership_management(service):
    service.assign_ownership("src/auth", "auth-agent")
    service.assign_ownership("src/auth/v2", "auth-v2-agent")

    assert service.resolve_owner("src/auth/file.py") == "auth-agent"
    assert service.resolve_owner("src/auth/v2/file.py") == "auth-v2-agent"
    assert service.resolve_owner("src/other/file.py") is None


def test_mail_system(service):
    service.send_mail(to_agent="agent-b", from_agent="agent-a", subject="Hello", body="Test message")
    
    messages = service.list_mail("agent-b")
    assert len(messages) == 1
    assert messages[0].subject == "Hello"
    assert messages[0].from_agent == "agent-a"
    assert messages[0].status == "unread"

    msg_id = messages[0].id
    read_msg = service.read_mail("agent-b", msg_id)
    assert read_msg.body == "Test message"
    assert read_msg.status == "read"


def test_adr_management(service):
    decision = service.add_decision(
        title="Use JWT",
        context="Need auth",
        decision="Use JWT tokens",
        consequences="Better scalability",
        agent_id="auth-agent"
    )
    assert decision.id == "ADR-001"
    assert decision.title == "Use JWT"

    decisions = service.list_decisions()
    assert len(decisions) == 1
    assert decisions[0].id == "ADR-001"


def test_context_building(service):
    # Setup: Create global rules and an agent playbook
    service.cursor_rules_dir.mkdir(parents=True, exist_ok=True)
    (service.cursor_rules_dir / "_global.mdc").write_text("Global rules content")
    
    service.create_agent(id="auth-agent", name="Auth Agent", role="auth")
    (service.cursor_rules_dir / "auth.mdc").write_text("Auth playbook content")
    
    service.assign_ownership("src/auth", "auth-agent")

    context, agent_id = service.build_context(path="src/auth/login.py", task_type=TaskType.IMPLEMENT)
    
    assert "### GLOBAL RULES" in context
    assert "Global rules content" in context
    assert "### AGENT PLAYBOOK (auth)" in context
    assert "Auth playbook content" in context


def test_google_stitch(service):
    url = service.ui_mockup("admin dashboard", "ui-agent")
    assert "stitch.google.com" in url
    
    code = service.ui_sync(url)
    assert "Synced from" in code
    assert "UI Mockup" in code


def test_sop_logic(service):
    service.create_agent(id="auth-agent", name="Auth Agent", role="auth")
    onboarding_file = service.onboard_agent("auth-agent")
    assert onboarding_file.exists()
    assert "SOP: Agent Onboarding - Auth Agent" in onboarding_file.read_text()

    review_file = service.review_pr("PR-123", "auth-agent")
    assert review_file.exists()
    assert "SOP: PR Review - PR-123" in review_file.read_text()


def test_ralph_loop(service):
    # Mock a successful test command
    success, iterations = service.run_loop("test task", "exit 0", max_iterations=2)
    assert success is True
    assert iterations == 1

    # Mock a failing test command
    success, iterations = service.run_loop("test task", "exit 1", max_iterations=2)
    assert success is False
    assert iterations == 2
