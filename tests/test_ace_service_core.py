import pytest
from ace_lib.services.ace_service import ACEService
from ace_lib.models.schemas import TaskType


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


def test_service_init(ace_service):
    assert ace_service.ace_dir.exists()
    assert ace_service.cursor_rules_dir.exists()


def test_agent_creation(ace_service):
    agent = ace_service.create_agent(
        id="test-agent",
        name="Test Agent",
        role="tester",
        responsibilities=["testing things"],
    )
    assert agent.id == "test-agent"
    assert agent.role == "tester"

    agents_config = ace_service.load_agents()
    assert len(agents_config.agents) == 1
    assert agents_config.agents[0].id == "test-agent"


def test_ownership_resolution(ace_service):
    ace_service.assign_ownership("src/auth", "auth-agent")
    ace_service.assign_ownership("src/auth/utils", "utils-agent")

    assert ace_service.resolve_owner("src/auth/login.py") == "auth-agent"
    assert ace_service.resolve_owner("src/auth/utils/hash.py") == "utils-agent"
    assert ace_service.resolve_owner("src/other.py") is None


def test_context_building(ace_service):
    # Setup global rules
    global_rules = ace_service.cursor_rules_dir / "_global.mdc"
    global_rules.write_text("Global Rule 1")

    # Setup agent and playbook
    ace_service.create_agent(id="a1", name="A1", role="r1")
    playbook = ace_service.cursor_rules_dir / "r1.mdc"
    playbook.write_text("Playbook Strategy 1")

    context, agent_id = ace_service.build_context(
        agent_id="a1", task_type=TaskType.IMPLEMENT
    )

    assert "Global Rule 1" in context
    assert "Playbook Strategy 1" in context
    assert agent_id == "a1"


def test_memory_synthesis_logic(ace_service, monkeypatch):
    # Mock anthropic client to avoid API calls
    class MockClient:
        class Messages:
            def create(self, **kwargs):
                class MockMessage:
                    content = [
                        type(
                            "obj",
                            (object,),
                            {
                                "text": (
                                    '[{"type": "str", "description": "Synthesized Strategy", '
                                    '"justification": "Because test"}]'
                                )
                            },
                        )
                    ]

                return MockMessage()

        messages = Messages()

    monkeypatch.setattr(ace_service, "get_anthropic_client", lambda: MockClient())

    # Setup agent with some learnings
    agent = ace_service.create_agent(id="a1", name="A1", role="r1")
    playbook_path = ace_service.base_path / agent.memory_file
    playbook_path.parent.mkdir(parents=True, exist_ok=True)
    playbook_path.write_text("""
## Strategier & patterns
<!-- [str-001] helpful=10 harmful=0 :: Good strategy -->
<!-- [str-002] helpful=8 harmful=0 :: Another good one -->
""")

    synthesized = ace_service.synthesize_memories("a1")
    assert len(synthesized) == 1
    assert synthesized[0]["description"] == "Synthesized Strategy"

    shared_file = ace_service.ace_dir / "shared-learnings.mdc"
    assert shared_file.exists()
    assert "Synthesized Strategy" in shared_file.read_text()
