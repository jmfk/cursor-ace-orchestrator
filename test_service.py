import pytest
from ace_lib.services.ace_service import ACEService
from ace_lib.models.schemas import TaskType


@pytest.fixture
def ace_service(tmp_path):
    service = ACEService(base_path=tmp_path)
    # Mock directory structure
    (tmp_path / ".ace").mkdir()
    (tmp_path / ".cursor" / "rules").mkdir(parents=True)
    return service


def test_agent_creation(ace_service):
    agent = ace_service.create_agent(id="test-agent", name="Test Agent", role="tester")
    assert agent.id == "test-agent"
    assert agent.role == "tester"

    agents_config = ace_service.load_agents()
    assert len(agents_config.agents) == 1
    assert agents_config.agents[0].id == "test-agent"


def test_ownership_resolution(ace_service):
    ace_service.assign_ownership("src/auth", "auth-agent")
    ace_service.assign_ownership("src/auth/login", "login-agent")

    assert ace_service.resolve_owner("src/auth/utils.py") == "auth-agent"
    assert ace_service.resolve_owner("src/auth/login/form.py") == "login-agent"
    assert ace_service.resolve_owner("src/other.py") is None


def test_context_building(ace_service):
    # Setup
    ace_service.create_agent(id="auth-agent", name="Auth Agent", role="auth")
    ace_service.assign_ownership("src/auth", "auth-agent")

    playbook_path = ace_service.cursor_rules_dir / "auth.mdc"
    playbook_path.write_text("Auth Playbook Content")

    global_rules = ace_service.cursor_rules_dir / "_global.mdc"
    global_rules.write_text("Global Rules Content")

    context, agent_id = ace_service.build_context(
        path="src/auth/login.py", task_type=TaskType.IMPLEMENT
    )

    assert agent_id == "auth-agent"
    assert "Global Rules Content" in context
    assert "Auth Playbook Content" in context
    assert "implementing new functionality in src/auth/login.py" in context


def test_mail_system(ace_service):
    ace_service.send_mail(
        to_agent="agent-b", from_agent="agent-a", subject="Hello", body="Test body"
    )
    messages = ace_service.list_mail("agent-b")
    assert len(messages) == 1
    assert messages[0].subject == "Hello"
    assert messages[0].status == "unread"

    msg = ace_service.read_mail("agent-b", messages[0].id)
    assert msg.body == "Test body"
    assert msg.status == "read"


def test_decision_listing(ace_service):
    ace_service.add_decision(
        title="Title 1",
        context="Context 1",
        decision="Decision 1",
        consequences="Consequences 1",
    )
    ace_service.add_decision(
        title="Title 2",
        context="Context 2",
        decision="Decision 2",
        consequences="Consequences 2",
    )

    decisions = ace_service.list_decisions()
    assert len(decisions) == 2
    assert decisions[0].title == "Title 1"
    assert decisions[1].title == "Title 2"


def test_session_listing(ace_service):
    (ace_service.ace_dir / "sessions").mkdir(parents=True, exist_ok=True)
    session_file = ace_service.sessions_dir / "session_20240101_120000.md"
    session_file.write_text("# Session 20240101_120000\n- **Command**: `test`")

    sessions = ace_service.list_sessions()
    assert len(sessions) == 1
    assert sessions[0]["command"] == "test"
