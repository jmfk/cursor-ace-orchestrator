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


def test_decision_management(service):
    """Test adding and listing decisions (ADRs)."""
    decision = service.add_decision(
        title="Use FastAPI",
        context="Need a web framework",
        decision="Use FastAPI for the backend",
        consequences="Fast and type-safe",
        agent_id="architect-1"
    )
    assert decision.id == "ADR-001"
    assert decision.title == "Use FastAPI"

    decisions = service.list_decisions()
    assert len(decisions) == 1
    assert decisions[0].title == "Use FastAPI"


def test_context_building(service, temp_workspace):
    """Test building context for an agent."""
    # Setup global rules
    service.cursor_rules_dir.mkdir(parents=True, exist_ok=True)
    global_rules = service.cursor_rules_dir / "_global.mdc"
    global_rules.write_text("Global project rules")

    # Setup agent and playbook
    service.create_agent(id="dev-1", name="Dev 1", role="developer")
    playbook = service.cursor_rules_dir / "developer.mdc"
    playbook.write_text("Developer playbook")

    context, agent_id = service.build_context(
        path="src/main.py", agent_id="dev-1"
    )

    assert agent_id == "dev-1"
    assert "GLOBAL RULES" in context
    assert "Global project rules" in context
    assert "AGENT PLAYBOOK (developer)" in context
    assert "Developer playbook" in context


def test_reflection_parsing(service):
    """Test parsing reflection output from LLM."""
    reflection_text = """
[str-001] helpful=1 harmful=0 :: Use pytest for testing.
[mis-002] helpful=0 harmful=1 :: Avoid global state.
[dec-003] :: Use PostgreSQL for database.
"""
    updates = service.parse_reflection_output(reflection_text)
    assert len(updates) == 3
    assert updates[0]["type"] == "str"
    assert updates[0]["id"] == "001"
    assert updates[0]["description"] == "Use pytest for testing."
    assert updates[1]["type"] == "mis"
    assert updates[2]["type"] == "dec"


def test_playbook_update(service, temp_workspace):
    """Test updating a playbook with new learnings."""
    service.cursor_rules_dir.mkdir(parents=True, exist_ok=True)
    playbook_path = service.cursor_rules_dir / "developer.mdc"
    playbook_path.write_text("""# Developer Playbook
## Strategier & patterns
## Kända fallgropar
## Arkitekturella beslut
""")

    updates = [
        {
            "type": "str",
            "id": "NEW",
            "helpful": 1,
            "harmful": 0,
            "description": "New strategy"
        },
        {
            "type": "mis",
            "id": "NEW",
            "helpful": 0,
            "harmful": 1,
            "description": "New pitfall"
        }
    ]

    success = service.update_playbook(playbook_path, updates)
    assert success is True

    content = playbook_path.read_text()
    assert "[str-001]" in content
    assert "New strategy" in content
    assert "[mis-001]" in content
    assert "New pitfall" in content


def test_memory_pruning(service, temp_workspace):
    """Test pruning harmful strategies from memory."""
    service.cursor_rules_dir.mkdir(parents=True, exist_ok=True)
    playbook_path = service.cursor_rules_dir / "developer.mdc"
    playbook_path.write_text("""# Developer Playbook
## Strategier & patterns
<!-- [str-001] helpful=1 harmful=5 :: Harmful strategy -->
<!-- [str-002] helpful=5 harmful=1 :: Helpful strategy -->
""")

    agent = service.create_agent(id="dev-1", name="Dev 1", role="developer")
    # Threshold 0 means harmful - helpful > 0
    pruned_count = service.prune_memory(agent, threshold=0)

    assert pruned_count == 1
    content = playbook_path.read_text()
    assert "[PRUNED] <!-- [str-001]" in content
    assert "<!-- [str-002]" in content


def test_stitch_mockup(service, temp_workspace, monkeypatch):
    """Test Google Stitch mockup generation."""
    import os
    import requests
    from unittest.mock import MagicMock

    # Mock requests.post
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_json = {"code": "// Generated via Stitch API\nexport const Mockup = () => <div>Mockup</div>;"}
    mock_response.json.return_value = mock_json
    monkeypatch.setattr(requests, "post", lambda *args, **kwargs: mock_response)

    os.environ["STITCH_API_KEY"] = "test-key"
    try:
        url = service.ui_mockup("Login page", "agent-1")
        assert "stitch.google.com/canvas/" in url

        mockup_id = url.split("/")[-1]
        mockup_file = service.ace_dir / "ui_mockups" / f"{mockup_id}.md"
        assert mockup_file.exists()
        content = mockup_file.read_text()
        assert "// Generated via Stitch API" in content
        assert "Login page" in content
    finally:
        del os.environ["STITCH_API_KEY"]


def test_stitch_sync(service, temp_workspace):
    """Test Google Stitch code sync."""
    mockup_id = "test_mockup"
    mockup_dir = service.ace_dir / "ui_mockups"
    mockup_dir.mkdir(parents=True, exist_ok=True)
    mockup_file = mockup_dir / f"{mockup_id}.md"
    mockup_file.write_text("""# UI Mockup
## Design & Code
```tsx
export const Test = () => <div>Test</div>;
```
""")

    url = f"https://stitch.google.com/canvas/{mockup_id}"
    code = service.ui_sync(url)
    assert "export const Test" in code


def test_ralph_loop_reflection_integration(service, temp_workspace, monkeypatch):
    """Test RALPH loop reflection integration."""
    # Mock subprocess.run to simulate agent and test execution
    import subprocess
    from unittest.mock import MagicMock

    def mock_run(cmd, shell=True, capture_output=True, text=True, env=None):
        mock_res = MagicMock()
        if "cursor-agent" in cmd:
            mock_res.returncode = 0
            mock_res.stdout = "Agent success output"
            mock_res.stderr = ""
        elif "pytest" in cmd:
            mock_res.returncode = 0
            mock_res.stdout = "Test success output"
            mock_res.stderr = ""
        return mock_res

    monkeypatch.setattr(subprocess, "run", mock_run)

    # Mock reflect_on_session to avoid API call
    monkeypatch.setattr(
        service,
        "reflect_on_session",
        lambda x: (
            "[str-NEW] helpful=1 harmful=0 :: New strategy from loop"
        )
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    # Setup playbook
    service.cursor_rules_dir.mkdir(parents=True, exist_ok=True)
    playbook_path = service.cursor_rules_dir / "developer.mdc"
    playbook_path.write_text(
        "# Developer Playbook\n## Strategier & patterns\n"
    )

    service.create_agent(id="dev-1", name="Dev 1", role="developer")

    success, iterations = service.run_loop(
        prompt="Fix bug",
        test_cmd="pytest",
        max_iterations=1,
        agent_id="dev-1"
    )

    assert success is True
    assert iterations == 1


def test_multi_turn_debate(service, monkeypatch):
    """Test multi-turn debate mediation."""
    from unittest.mock import MagicMock
    from ace_lib.models.schemas import TokenMode

    # Mock anthropic client
    mock_client = MagicMock()
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text="Perspective or Consensus")]
    mock_client.messages.create.return_value = mock_message

    monkeypatch.setattr(service, "get_anthropic_client", lambda: mock_client)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    # Setup agents
    service.create_agent(id="agent-1", name="Agent 1", role="architect")
    service.create_agent(id="agent-2", name="Agent 2", role="developer")

    # Set token mode to HIGH to ensure full turns
    config = service.load_config()
    config.token_mode = TokenMode.HIGH
    service.save_config(config)

    consensus = service.debate(
        proposal="Use GraphQL",
        agent_ids=["agent-1", "agent-2"],
        turns=2
    )

    assert consensus == "Perspective or Consensus"
    # 2 turns * 2 agents + 1 referee call = 5 calls
    assert mock_client.messages.create.call_count == 5

    # Check that mail was sent to both agents
    messages_1 = service.list_mail("agent-1")
    messages_2 = service.list_mail("agent-2")
    assert len(messages_1) > 0
    assert len(messages_2) > 0
    
    def test_consensus_debate(self, service, monkeypatch):
        """Test consensus debate mediation."""
        from unittest.mock import MagicMock
        from ace_lib.models.schemas import TokenMode

        # Mock anthropic client
        mock_client = MagicMock()
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text="Consensus reached: Use FastAPI")]
        mock_client.messages.create.return_value = mock_message

        monkeypatch.setattr(service, "get_anthropic_client", lambda: mock_client)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

        # Setup agents
        service.create_agent(id="agent-1", name="Agent 1", role="architect")
        service.create_agent(id="agent-2", name="Agent 2", role="developer")

        # Set token mode
        config = service.load_config()
        config.token_mode = TokenMode.HIGH
        service.save_config(config)

        consensus = service.debate(
            proposal="Use FastAPI",
            agent_ids=["agent-1", "agent-2"],
            turns=1
        )

        assert "FastAPI" in consensus
        # 1 turn * 2 agents + 1 referee call = 3 calls
        assert mock_client.messages.create.call_count == 3

    def test_subscriptions_and_notifications(self, service):
        """Test agent subscriptions and notifications."""
        service.create_agent(id="sub-agent", name="Sub Agent", role="developer")
        
        # Subscribe
        success = service.subscribe("sub-agent", "src/auth")
        assert success is True
        
        # Notify
        service.notify_subscribers("src/auth/login.py", "Added login logic")
        
        # Check mail
        messages = service.list_mail("sub-agent")
        assert len(messages) == 1
        assert "SUBSCRIPTION NOTIFICATION" in messages[0].subject
        assert "Added login logic" in messages[0].body

    def test_token_usage_logging(self, service):
        """Test logging token usage."""
        from ace_lib.models.schemas import TokenUsage
        usage = TokenUsage(
            agent_id="test-agent",
            session_id="test-session",
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            cost=0.001
        )
        service.log_token_usage(usage)
        
        report = service.get_token_report("test-agent")
        assert len(report) == 1
        assert report[0].total_tokens == 150

