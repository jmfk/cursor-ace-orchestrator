import pytest
import subprocess
from ace_lib.services.ace_service import ACEService
from ace_lib.models.schemas import TokenUsage


@pytest.fixture
def ace_service(tmp_path):
    """Create a temporary ACE service for testing."""
    service = ACEService(tmp_path)
    # Initialize basic structure
    service.ace_dir.mkdir(parents=True, exist_ok=True)
    (service.ace_dir / "agents.yaml").touch()
    (service.ace_dir / "config.yaml").touch()
    (service.ace_dir / "ownership.yaml").touch()
    service.cursor_rules_dir.mkdir(parents=True, exist_ok=True)
    return service


def test_onboarding_sop_generation(ace_service):
    """Test that onboarding SOP is generated and sent via mail."""
    agent = ace_service.create_agent(
        id="dev-01",
        name="Developer One",
        role="developer",
        responsibilities=["coding", "testing"],
    )

    sop_file = ace_service.onboard_agent("dev-01")

    assert sop_file.exists()
    assert "SOP: Agent Onboarding - Developer One (dev-01)" in sop_file.read_text()
    assert "**Responsibilities**: coding, testing" in sop_file.read_text()

    # Check if memory file was created
    memory_path = ace_service.base_path / agent.memory_file
    assert memory_path.exists()
    assert "# Developer One Playbook (developer)" in memory_path.read_text()

    # Check if mail was sent
    messages = ace_service.list_mail("dev-01")
    assert len(messages) == 1
    assert messages[0].subject == "ONBOARDING SOP"


def test_pr_review_sop_generation(ace_service):
    """Test that PR review SOP is generated and sent via mail."""
    ace_service.create_agent(id="reviewer-01", name="Reviewer One", role="reviewer")

    review_file = ace_service.review_pr("PR-123", "reviewer-01")

    assert review_file.exists()
    assert "SOP: PR Review - PR-123" in review_file.read_text()
    assert "**Reviewer**: reviewer-01" in review_file.read_text()

    # Check if mail was sent
    messages = ace_service.list_mail("reviewer-01")
    assert len(messages) == 1
    assert messages[0].subject == "PR REVIEW TASK: PR-123"


def test_token_usage_logging(ace_service):
    """Test that token usage is correctly logged and reported."""
    usage = TokenUsage(
        agent_id="test-agent",
        session_id="session-001",
        prompt_tokens=100,
        completion_tokens=50,
        total_tokens=150,
        cost=0.0005,
    )

    ace_service.log_token_usage(usage)

    report = ace_service.get_token_report()
    assert len(report) == 1
    assert report[0].agent_id == "test-agent"
    assert report[0].total_tokens == 150
    assert report[0].cost == 0.0005

    # Test filtering by agent
    report_filtered = ace_service.get_token_report("test-agent")
    assert len(report_filtered) == 1

    report_empty = ace_service.get_token_report("non-existent")
    assert len(report_empty) == 0


def test_ui_mockup_generation_fallback(ace_service, monkeypatch):
    """Test UI mockup generation with agent fallback (no API key)."""

    # Mock the agent command execution
    class MockProcess:
        stdout = "```tsx\nexport const App = () => <div>Hello</div>;\n```"
        returncode = 0

    def mock_run(*args, **kwargs):
        return MockProcess()

    monkeypatch.setattr(subprocess, "run", mock_run)
    monkeypatch.setattr(ace_service, "get_stitch_key", lambda: None)
    # Ensure we don't trigger the test environment bypass in ace_service.py
    monkeypatch.setenv("STITCH_TEST_NO_BYPASS", "1")
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    mockup_url = ace_service.ui_mockup("A simple button", "designer-01")

    assert "stitch.google.com/canvas/" in mockup_url

    mockup_id = mockup_url.split("/")[-1]
    mockup_file = ace_service.ace_dir / "ui_mockups" / f"{mockup_id}.md"

    assert mockup_file.exists()
    assert "## Design & Code" in mockup_file.read_text()
    assert "export const App" in mockup_file.read_text()

    # Check if component was extracted
    component_file = (
        ace_service.ace_dir
        / "ui_mockups"
        / "components"
        / mockup_id
        / "App.tsx"
    )
    assert component_file.exists()
    assert "export const App" in component_file.read_text()


def test_context_pruning(ace_service):
    """Test that context is pruned when it exceeds the limit."""
    long_context = "### GLOBAL RULES\n" + "x" * 5000 + "\n"
    long_context += "### AGENT PLAYBOOK\n" + "y" * 5000 + "\n"
    long_context += "### RECENT SESSIONS\n" + "z" * 10000 + "\n"
    long_context += "### TASK FRAMING\n" + "f" * 1000 + "\n"

    # Limit to 12000 chars
    pruned = ace_service.prune_context(long_context, 12000)

    assert len(pruned) <= 12000
    assert "### GLOBAL RULES" in pruned
    assert "### AGENT PLAYBOOK" in pruned
    assert "### TASK FRAMING" in pruned
    # RECENT SESSIONS should be pruned or truncated
    assert "### RECENT SESSIONS" in pruned or "z" * 10000 not in pruned
