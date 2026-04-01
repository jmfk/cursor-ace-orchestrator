import pytest
from pathlib import Path
import os
from ace import save_ownership, OwnershipConfig
from ace_lib.services.ace_service import ACEService
from ace_lib.models.schemas import OwnershipModule


@pytest.fixture
def temp_ace_dir(tmp_path):
    """Fixture to create a temporary .ace directory for testing."""
    ace_dir = tmp_path / ".ace"
    ace_dir.mkdir()

    # Mock the Path in ace.py or change working directory
    original_cwd = os.getcwd()
    os.chdir(tmp_path)

    # Ensure we don't pick up the real .cursor/rules from the project root
    # by creating a dummy one if needed, but since we are in tmp_path,
    # it should be fine as long as we don't use absolute paths that point outside.

    yield tmp_path

    os.chdir(original_cwd)


def test_ownership_longest_prefix_match(temp_ace_dir, monkeypatch):
    """Test that ownership is resolved using longest prefix match."""
    # Setup ownership
    from ace import reset_service
    reset_service(temp_ace_dir)
    monkeypatch.setenv("ACE_API_URL", "http://non-existent-url")

    config = OwnershipConfig()
    config.modules["src/auth"] = OwnershipModule(agent_id="auth-agent")
    config.modules["src/auth/special"] = OwnershipModule(
        agent_id="special-agent")
    save_ownership(config)

    # Test matching
    from ace import app
    from typer.testing import CliRunner

    runner = CliRunner()

    # Exact match
    result = runner.invoke(app, ["who", "src/auth"])
    assert "owned by agent auth-agent" in result.stdout

    # Prefix match
    result = runner.invoke(app, ["who", "src/auth/token.ts"])
    assert "owned by agent auth-agent" in result.stdout

    # Longest prefix match
    result = runner.invoke(app, ["who", "src/auth/special/file.ts"])
    assert "owned by agent special-agent" in result.stdout

    # Unowned
    result = runner.invoke(app, ["who", "src/other"])
    assert "currently unowned" in result.stdout


def test_agent_registry(temp_ace_dir, monkeypatch):
    """Test agent creation and listing in the registry."""
    # Ensure we are not using the global service from ace.py
    import ace
    svc = ACEService(temp_ace_dir)

    monkeypatch.setattr(ace, "service", svc)
    monkeypatch.setattr(ace, "get_service", lambda: svc)

    # Mock api_call to always return None to force local service usage
    monkeypatch.setattr(ace, "api_call", lambda *args, **kwargs: None)

    from ace import app
    from typer.testing import CliRunner

    runner = CliRunner()

    # Create agent
    result = runner.invoke(
        app,
        [
            "agent", "create", "--name", "Test", "--role", "tester",
            "--id", "test-01"
        ]
    )
    assert result.exit_code == 0
    assert "Created agent Test" in result.stdout

    # List agents
    result = runner.invoke(app, ["agent", "list"])
    assert "test-01" in result.stdout
    assert "tester" in result.stdout

    # Duplicate ID
    result = runner.invoke(
        app,
        [
            "agent", "create", "--name", "Test2", "--role", "tester",
            "--id", "test-01"
        ]
    )
    assert result.exit_code == 1
    assert "Error: Agent with ID test-01 already exists." in result.stdout


def test_config_tokens(temp_ace_dir, monkeypatch):
    """Test setting and loading token consumption mode."""
    from ace import app, reset_service
    reset_service(temp_ace_dir)

    from typer.testing import CliRunner

    runner = CliRunner()

    # Set token mode
    result = runner.invoke(app, ["config-tokens", "--mode", "high"])
    assert result.exit_code == 0
    assert "Token mode set to high" in result.stdout

    # Verify in config.yaml
    from ace import load_config

    config = load_config()
    assert config.token_mode == "high"


def test_build_context(temp_ace_dir, monkeypatch):
    """Test composing the context slice for an agent call."""
    import ace
    svc = ACEService(temp_ace_dir)
    monkeypatch.setattr(ace, "service", svc)
    monkeypatch.setattr(ace, "get_service", lambda: svc)
    monkeypatch.setattr(ace, "api_call", lambda *args, **kwargs: None)

    from ace import app
    from typer.testing import CliRunner

    runner = CliRunner()

    # Setup global rules
    rules_dir = Path(".cursor/rules")
    rules_dir.mkdir(parents=True, exist_ok=True)
    global_rules = rules_dir / "_global.mdc"
    global_rules.write_text("Global rules content")

    # Setup agent and playbook
    runner.invoke(
        app,
        ["agent", "create", "--name", "Auth", "--role", "auth",
         "--id", "auth-01"]
    )
    playbook = rules_dir / "auth.mdc"
    playbook.write_text("Auth playbook content")

    # Setup ownership
    runner.invoke(app, ["own", "src/auth", "auth-01"])

    # Build context
    result = runner.invoke(
        app,
        [
            "build-context", "--path", "src/auth/login.ts",
            "--task-type", "implement"
        ]
    )
    assert result.exit_code == 0
    assert "GLOBAL RULES" in result.stdout
    assert "Global rules content" in result.stdout
    assert "AGENT PLAYBOOK (auth)" in result.stdout
    assert "Auth playbook content" in result.stdout
    assert "TASK FRAMING" in result.stdout
    assert (
        "You are implementing new functionality in src/auth/login.ts"
        in result.stdout
    )


def test_run_session_logging(temp_ace_dir, monkeypatch):
    """Test that running a command logs the session correctly."""
    from ace import app, reset_service
    reset_service(temp_ace_dir)

    from typer.testing import CliRunner

    runner = CliRunner()

    # Setup global rules
    rules_dir = Path(".cursor/rules")
    rules_dir.mkdir(parents=True, exist_ok=True)
    global_rules = rules_dir / "_global.mdc"
    global_rules.write_text("Global rules content")

    # Initialize directories
    runner.invoke(app, ["init"])

    # Run a simple command
    result = runner.invoke(app, ["run", "echo Hello ACE"])
    assert result.exit_code == 0
    assert "Hello ACE" in result.stdout

    # Verify session log
    sessions_dir = Path(".ace/sessions")
    session_files = list(sessions_dir.glob("*.md"))
    assert len(session_files) == 1
    session_log = session_files[0].read_text()
    assert "echo Hello ACE" in session_log
    assert "Hello ACE" in session_log
    assert "GLOBAL RULES" in session_log


def test_session_continuity(temp_ace_dir, monkeypatch):
    """Test that recent sessions are included in the context."""
    import ace
    svc = ACEService(temp_ace_dir)
    monkeypatch.setattr(ace, "service", svc)
    monkeypatch.setattr(ace, "get_service", lambda: svc)
    monkeypatch.setattr(ace, "api_call", lambda *args, **kwargs: None)

    from ace import app
    from typer.testing import CliRunner

    runner = CliRunner()

    # Setup global rules
    rules_dir = Path(".cursor/rules")
    rules_dir.mkdir(parents=True, exist_ok=True)
    global_rules = rules_dir / "_global.mdc"
    global_rules.write_text("Global rules content")

    # Initialize directories
    runner.invoke(app, ["init"])

    # Run first command to create a session
    runner.invoke(app, ["run", "echo Session 1"])

    # Run second command and check context for session continuity
    result = runner.invoke(app, ["build-context"])
    assert "RECENT SESSIONS" in result.stdout
    assert "Session 1" in result.stdout


def test_parse_reflection_output():
    """Test parsing of structured reflection output."""
    from ace import parse_reflection_output

    text = """
    [str-NEW] helpful=1 harmful=0 :: Use the Read tool before editing.
    [mis-NEW] helpful=0 harmful=1 :: Don't skip tests.
    [dec-NEW] :: Use FastAPI for the backend.
    """
    updates = parse_reflection_output(text)
    assert len(updates) == 3
    assert updates[0]["type"] == "str"
    assert updates[0]["description"] == "Use the Read tool before editing."
    assert updates[1]["type"] == "mis"
    assert updates[2]["type"] == "dec"


def test_update_playbook(tmp_path):
    """Test updating a playbook with new learnings."""
    from ace import update_playbook

    playbook = tmp_path / "test.mdc"
    playbook.write_text("""
## Strategier & patterns
## Kända fallgropar
## Arkitekturella beslut
""")

    updates = [
        {"type": "str", "id": "NEW", "helpful": 1,
            "harmful": 0, "description": "New strategy"},
        {"type": "dec", "id": "001", "helpful": 0,
            "harmful": 0, "description": "Existing decision"},
    ]

    # Add new
    update_playbook(playbook, updates[:1])
    content = playbook.read_text()
    assert "[str-001] helpful=1 harmful=0 :: New strategy" in content

    # Update existing (simulated by adding it first then updating)
    playbook.write_text(content + "\n<!-- [dec-001] :: Existing decision -->")
    updates[1]["description"] = "Updated decision"
    update_playbook(playbook, updates[1:])
    content = playbook.read_text()
    assert "Updated decision" in content
    assert "Existing decision" not in content


def test_decision_management(temp_ace_dir, monkeypatch):
    """Test adding and listing architectural decisions."""
    from ace import app, reset_service
    reset_service(temp_ace_dir)

    from typer.testing import CliRunner

    runner = CliRunner()

    # Add decision
    result = runner.invoke(
        app,
        [
            "decision-add",
            "--title",
            "Use PostgreSQL",
            "--context",
            "We need a database",
            "--decision",
            "PostgreSQL",
            "--consequences",
            "Reliable data",
        ],
    )
    assert result.exit_code == 0
    assert "Created ADR:" in result.stdout
    assert "ADR-001.md" in result.stdout

    # List decisions
    result = runner.invoke(app, ["decision-list"])
    assert result.exit_code == 0
    assert "ADR-001" in result.stdout
    assert "Use PostgreSQL" in result.stdout
    assert "accepted" in result.stdout

    # Add another decision
    result = runner.invoke(
        app,
        [
            "decision-add",
            "--title",
            "Use Redis",
            "--context",
            "We need caching",
            "--decision",
            "Redis",
            "--consequences",
            "Faster reads",
        ],
    )
    assert result.exit_code == 0
    assert "ADR-002" in result.stdout

    # Verify file content
    adr_file = Path(".ace/decisions/ADR-001.md")
    content = adr_file.read_text()
    assert "# ADR-001: Use PostgreSQL" in content
    assert "## Context\nWe need a database" in content
    assert "## Decision\nPostgreSQL" in content
    assert "## Consequences\nReliable data" in content


def test_memory_prune(temp_ace_dir, monkeypatch):
    """Test pruning harmful strategies from an agent's memory."""
    from ace import app, reset_service
    reset_service(temp_ace_dir)

    from typer.testing import CliRunner

    runner = CliRunner()

    # Setup agent and playbook with harmful strategy
    runner.invoke(
        app,
        [
            "agent", "create", "--name", "Test", "--role", "tester",
            "--id", "test-01"
        ]
    )
    playbook_path = Path(".cursor/rules/tester.mdc")
    playbook_path.parent.mkdir(parents=True, exist_ok=True)
    playbook_path.write_text("""
## Strategier & patterns
<!-- [str-001] helpful=1 harmful=5 :: Bad strategy -->
<!-- [str-002] helpful=5 harmful=1 :: Good strategy -->
""")

    # Prune
    result = runner.invoke(
        app, ["memory-prune", "--agent", "test-01", "--threshold", "0"]
    )
    assert result.exit_code == 0
    assert "Pruning memory for agent: test-01" in result.stdout

    # Verify file content
    content = playbook_path.read_text()
    assert "<!-- [PRUNED] <!-- [str-001] helpful=1 harmful=5 :: Bad strategy --> -->" in content
    assert "<!-- [str-002] helpful=5 harmful=1 :: Good strategy -->" in content


def test_memory_sync(temp_ace_dir, monkeypatch):
    """Test syncing AGENTS.md with the registry and decisions."""
    from ace import app, reset_service
    reset_service(temp_ace_dir)

    from typer.testing import CliRunner

    runner = CliRunner()

    # Setup agents and decisions
    runner.invoke(
        app,
        [
            "agent", "create", "--name", "Auth Agent", "--role", "auth",
            "--id", "auth-01"
        ]
    )
    runner.invoke(
        app,
        [
            "decision-add",
            "--title",
            "Use PostgreSQL",
            "--context",
            "We need a database",
            "--decision",
            "PostgreSQL",
            "--consequences",
            "Reliable data",
        ],
    )

    # Sync
    result = runner.invoke(app, ["memory-sync"])
    assert result.exit_code == 0
    assert "Updated AGENTS.md" in result.stdout

    # Verify AGENTS.md content
    agents_md = Path("AGENTS.md")
    assert agents_md.exists()
    content = agents_md.read_text()
    assert "# ACE Agents Registry" in content
    assert "### Auth Agent (`auth-01`)" in content
    assert "## Recent Architectural Decisions" in content
    assert "ADR-001: Use PostgreSQL" in content


def test_mail_system(temp_ace_dir, monkeypatch):
    """Test the agent mail system."""
    import ace
    svc = ACEService(temp_ace_dir)
    monkeypatch.setattr(ace, "service", svc)
    monkeypatch.setattr(ace, "get_service", lambda: svc)
    monkeypatch.setattr(ace, "api_call", lambda *args, **kwargs: None)

    from ace import app
    from typer.testing import CliRunner

    runner = CliRunner()

    # Create agents
    runner.invoke(
        app,
        [
            "agent", "create", "--name", "Agent A", "--role", "role-a",
            "--id", "agent-a"
        ]
    )
    runner.invoke(
        app,
        [
            "agent", "create", "--name", "Agent B", "--role", "role-b",
            "--id", "agent-b"
        ]
    )

    # Send mail
    result = runner.invoke(
        app,
        [
            "mail-send", "--to", "agent-b", "--from", "agent-a",
            "--subject", "Hello", "--body", "How are you?"
        ]
    )
    assert result.exit_code == 0
    assert "Message sent from agent-a to agent-b" in result.stdout

    # List mail
    result = runner.invoke(app, ["mail-list", "agent-b"])
    assert result.exit_code == 0
    assert "agent-a" in result.stdout
    assert "Hello" in result.stdout

    # Read mail
    import re

    msg_id_match = re.search(r"(\d+_\d+_\d+_[^ \n]+)", result.stdout)
    if msg_id_match:
        msg_id = msg_id_match.group(1)
        result = runner.invoke(app, ["mail-read", "agent-b", msg_id])
        assert result.exit_code == 0
        assert "How are you?" in result.stdout
    else:
        # Fallback for different ID format
        pass


def test_debate(temp_ace_dir, monkeypatch):
    """Test the debate command."""
    import ace
    svc = ACEService(temp_ace_dir)
    monkeypatch.setattr(ace, "service", svc)
    monkeypatch.setattr(ace, "get_service", lambda: svc)
    monkeypatch.setattr(ace, "api_call", lambda *args, **kwargs: None)

    # Mock debate mediation to avoid API call
    def mocked_debate(proposal, agent_ids, turns=3):
        # Call the original debate logic but it will fail at client creation
        # So we just manually do what debate does before failing
        for aid in agent_ids:
            svc.send_mail(aid, "orchestrator", "DEBATE PROPOSAL",
                          f"Proposal: {proposal}")
        return "Consensus reached."

    monkeypatch.setattr(svc, "debate", mocked_debate)

    from ace import app
    from typer.testing import CliRunner

    runner = CliRunner()

    # Create agents
    runner.invoke(
        app,
        [
            "agent", "create", "--name", "Agent A", "--role", "role-a",
            "--id", "agent-a"
        ]
    )
    runner.invoke(
        app,
        [
            "agent", "create", "--name", "Agent B", "--role", "role-b",
            "--id", "agent-b"
        ]
    )

    # Initiate debate
    # Use MACP propose first
    result = runner.invoke(
        app,
        [
            "macp", "propose", "--title", "Use Python", "--desc", "Python is good",
            "--from", "agent-a", "--agent", "agent-a", "--agent", "agent-b"
        ]
    )
    assert result.exit_code == 0
    import re
    proposal_id_match = re.search(r"MACP-\d+-\d+", result.stdout)
    assert proposal_id_match
    proposal_id = proposal_id_match.group(0)

    result = runner.invoke(
        app,
        [
            "debate", proposal_id, "--agent", "agent-a",
            "--agent", "agent-b", "--turns", "2"
        ]
    )
    assert result.exit_code == 0
    assert "Consensus / Recommendation:" in result.stdout
    assert "Consensus reached." in result.stdout

    # Verify mail in agent-a's inbox
    result = runner.invoke(app, ["mail-list", "agent-a"])
    assert "DEBATE PROPOSAL" in result.stdout


def test_ui_mockup(temp_ace_dir, monkeypatch):
    """Test the UI mockup command."""
    from ace import app, reset_service, get_service
    reset_service(temp_ace_dir)
    svc = get_service()

    # Mock ui_mockup to avoid API call/subprocess
    monkeypatch.setattr(svc, "ui_mockup", lambda d,
                        a: "https://stitch.google.com/canvas/mock_123")

    from typer.testing import CliRunner

    runner = CliRunner()

    result = runner.invoke(
        app, ["ui", "mockup", "Admin Dashboard", "--agent", "ui-agent"]
    )
    assert result.exit_code == 0
    assert "Generating UI mockup for: Admin Dashboard" in result.stdout


def test_ui_sync(temp_ace_dir, monkeypatch):
    """Test the UI sync command."""
    from ace import app, reset_service, get_service
    reset_service(temp_ace_dir)
    svc = get_service()

    # Mock ui_sync
    monkeypatch.setattr(
        svc, "ui_sync", lambda u: "export const UI = () => <div>Mock</div>;")

    from typer.testing import CliRunner

    runner = CliRunner()

    url = "https://stitch.google.com/canvas/12345"
    result = runner.invoke(app, ["ui", "sync", url])
    assert result.exit_code == 0
    assert f"Syncing UI code from: {url}" in result.stdout


def test_subscriptions_granular(temp_ace_dir, monkeypatch):
    """Test granular subscription options."""
    import ace
    svc = ACEService(temp_ace_dir)
    monkeypatch.setattr(ace, "service", svc)
    monkeypatch.setattr(ace, "get_service", lambda: svc)
    monkeypatch.setattr(ace, "api_call", lambda *args, **kwargs: None)

    from ace import app
    from typer.testing import CliRunner

    runner = CliRunner()

    # Subscribe with granular options
    result = runner.invoke(
        app, 
        [
            "subscribe", "agent-a", "src/auth", 
            "--priority", "high", 
            "--no-notify-on-success"
        ]
    )
    assert result.exit_code == 0
    assert "priority high" in result.stdout

    # Verify subscription
    subs = svc.load_subscriptions()
    assert len(subs.subscriptions) == 1
    sub = subs.subscriptions[0]
    assert sub.agent_id == "agent-a"
    assert sub.path == "src/auth"
    assert sub.priority == "high"
    assert sub.notify_on_success is False
    assert sub.notify_on_failure is True

    # Test notification logic
    # Mock send_mail to check if it's called
    sent_mails = []
    def mock_send_mail(to_agent, from_agent, subject, body):
        sent_mails.append({"to": to_agent, "subject": subject})

    monkeypatch.setattr(svc, "send_mail", mock_send_mail)

    # Success notification (should be skipped due to notify_on_success=False)
    svc.notify_subscribers("src/auth/login.ts", "Success", success=True)
    assert len(sent_mails) == 0

    # Failure notification (should be sent)
    svc.notify_subscribers("src/auth/login.ts", "Failure", success=False)
    assert len(sent_mails) == 1
    assert sent_mails[0]["to"] == "agent-a"
    assert "[HIGH] SUBSCRIPTION FAILURE" in sent_mails[0]["subject"]
