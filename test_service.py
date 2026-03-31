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
    agent = ace_service.create_agent("test-agent", "Test Agent", "tester")
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
    ace_service.create_agent("auth-agent", "Auth Agent", "auth")
    ace_service.assign_ownership("src/auth", "auth-agent")

    playbook_path = ace_service.cursor_rules_dir / "auth.mdc"
    playbook_path.write_text("Auth Playbook Content")

    global_rules = ace_service.cursor_rules_dir / "_global.mdc"
    global_rules.write_text("Global Rules Content")

    context, agent_id = ace_service.build_context(path="src/auth/login.py", task_type=TaskType.IMPLEMENT)

    assert agent_id == "auth-agent"
    assert "Global Rules Content" in context
    assert "Auth Playbook Content" in context
    assert "implementing new functionality in src/auth/login.py" in context
