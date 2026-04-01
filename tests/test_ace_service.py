import pytest
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


def test_init_directories(service, temp_workspace):
    """Test that directories are correctly identified."""
    assert service.ace_dir == temp_workspace / ".ace"
    assert service.ace_local_dir == temp_workspace / ".ace-local"


def test_agent_creation(service):
    """Test creating an agent."""
    agent = service.create_agent(
        id="test-agent", name="Test Agent", role="tester"
    )
    assert agent.id == "test-agent"
    assert agent.role == "tester"

    agents_config = service.load_agents()
    assert len(agents_config.agents) == 1
    assert agents_config.agents[0].id == "test-agent"


def test_ownership_resolution(service):
    """Test path ownership resolution."""
    service.assign_ownership("src/core", "agent-1")
    service.assign_ownership("src/core/utils", "agent-2")

    assert service.resolve_owner("src/core/main.py") == "agent-1"
    assert service.resolve_owner("src/core/utils/helper.py") == "agent-2"
    assert service.resolve_owner("src/other/file.py") is None


def test_onboarding_sop(service):
    """Test generating onboarding SOP."""
    service.create_agent(id="dev-1", name="Developer 1", role="developer")
    onboarding_file = service.onboard_agent("dev-1")

    assert onboarding_file.exists()
    content = onboarding_file.read_text()
    assert "SOP: Agent Onboarding - Developer 1 (dev-1)" in content
    assert "## 1. Context Acquisition" in content


def test_pr_review_sop(service):
    """Test generating PR review SOP."""
    review_file = service.review_pr("PR-123", "reviewer-1")
    assert review_file.exists()
    content = review_file.read_text()
    assert "SOP: PR Review - PR-123" in content
    assert "**Reviewer**: reviewer-1" in content


def test_mail_system(service):
    """Test sending and reading mail."""
    service.send_mail(
        to_agent="agent-b",
        from_agent="agent-a",
        subject="Hello",
        body="Test body"
    )

    messages = service.list_mail("agent-b")
    assert len(messages) == 1
    assert messages[0].subject == "Hello"
    assert messages[0].from_agent == "agent-a"

    msg = service.read_mail("agent-b", messages[0].id)
    assert msg.body == "Test body"
    assert msg.status == "read"
