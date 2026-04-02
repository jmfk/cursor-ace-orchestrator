import pytest
from pathlib import Path
from ace_lib.services.ace_service import ACEService
from ace_lib.models.schemas import TokenMode


@pytest.fixture
def ace_service(tmp_path):
    """Create a temporary ACE service for testing."""
    service = ACEService(tmp_path)
    service.ace_dir.mkdir(parents=True, exist_ok=True)
    service.cursor_rules_dir.mkdir(parents=True, exist_ok=True)
    return service


def test_config_loading_saving(ace_service):
    config = ace_service.load_config()
    assert config.token_mode == TokenMode.LOW

    config.token_mode = TokenMode.HIGH
    ace_service.save_config(config)

    ace_service.clear_cache()
    new_config = ace_service.load_config()
    assert new_config.token_mode == TokenMode.HIGH


def test_ownership_longest_prefix(ace_service):
    ace_service.assign_ownership("src", "agent-src")
    ace_service.assign_ownership("src/components", "agent-components")
    ace_service.assign_ownership("src/components/ui", "agent-ui")

    assert ace_service.resolve_owner("src/main.py") == "agent-src"
    assert ace_service.resolve_owner("src/components/Button.tsx") == "agent-components"
    assert ace_service.resolve_owner("src/components/ui/Modal.tsx") == "agent-ui"
    assert ace_service.resolve_owner("tests/test_main.py") is None


def test_playbook_update_new_entry(ace_service):
    agent = ace_service.create_agent(id="a1", name="A1", role="r1")
    playbook_path = ace_service.base_path / agent.memory_file
    playbook_path.parent.mkdir(parents=True, exist_ok=True)
    playbook_path.write_text("## Strategier & patterns\n")

    updates = [
        {
            "type": "str",
            "id": "NEW",
            "helpful": 1,
            "harmful": 0,
            "description": "New Strategy",
        }
    ]

    ace_service.update_playbook(playbook_path, updates)
    content = playbook_path.read_text()
    assert "<!-- [str-001] helpful=1 harmful=0 :: New Strategy -->" in content


def test_playbook_update_existing_entry(ace_service):
    agent = ace_service.create_agent(id="a1", name="A1", role="r1")
    playbook_path = ace_service.base_path / agent.memory_file
    playbook_path.parent.mkdir(parents=True, exist_ok=True)
    playbook_path.write_text(
        "## Strategier & patterns\n<!-- [str-001] helpful=5 harmful=1 :: Existing Strategy -->"
    )

    updates = [
        {
            "type": "str",
            "id": "001",
            "helpful": 2,
            "harmful": 0,
            "description": "Updated Strategy",
        }
    ]

    ace_service.update_playbook(playbook_path, updates)
    content = playbook_path.read_text()
    assert "<!-- [str-001] helpful=7 harmful=1 :: Updated Strategy -->" in content


def test_mail_system(ace_service):
    ace_service.send_mail(
        to_agent="a2", from_agent="a1", subject="Hello", body="Test message"
    )
    messages = ace_service.list_mail("a2")
    assert len(messages) == 1
    assert messages[0].subject == "Hello"
    assert messages[0].from_agent == "a1"

    msg = ace_service.read_mail("a2", messages[0].id)
    assert msg.body == "Test message"
    assert msg.status == "read"


def test_adr_management(ace_service):
    ace_service.add_decision(
        title="Use FastAPI",
        context="Need a web framework",
        decision="Use FastAPI for the backend",
        consequences="Fast and type-safe",
    )

    decisions = ace_service.list_decisions()
    assert len(decisions) == 1
    assert decisions[0].title == "Use FastAPI"
    assert decisions[0].id == "ADR-001"


def test_onboard_agent(ace_service):
    ace_service.create_agent(id="a1", name="A1", role="r1")
    onboarding_file = ace_service.onboard_agent("a1")
    assert Path(onboarding_file).exists()
    assert "Agent Onboarding" in Path(onboarding_file).read_text()

    # Check mail
    messages = ace_service.list_mail("a1")
    assert any(m.subject == "ONBOARDING SOP" for m in messages)


def test_review_pr(ace_service):
    ace_service.create_agent(id="a1", name="A1", role="r1")
    review_file = ace_service.review_pr("PR-123", "a1")
    assert Path(review_file).exists()
    assert "PR Review" in Path(review_file).read_text()

    # Check mail
    messages = ace_service.list_mail("a1")
    assert any(m.subject == "PR REVIEW TASK: PR-123" for m in messages)
