import pytest
from pathlib import Path
import os
from ace import save_ownership, OwnershipConfig, OwnershipModule

@pytest.fixture
def temp_ace_dir(tmp_path):
    """Fixture to create a temporary .ace directory for testing."""
    ace_dir = tmp_path / ".ace"
    ace_dir.mkdir()
    
    # Mock the Path in ace.py or change working directory
    original_cwd = os.getcwd()
    os.chdir(tmp_path)
    
    yield tmp_path
    
    os.chdir(original_cwd)

def test_ownership_longest_prefix_match(temp_ace_dir):
    # Setup ownership
    config = OwnershipConfig()
    config.modules["src/auth"] = OwnershipModule(agent_id="auth-agent")
    config.modules["src/auth/special"] = OwnershipModule(agent_id="special-agent")
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

def test_agent_registry(temp_ace_dir):
    from ace import app
    from typer.testing import CliRunner
    runner = CliRunner()
    
    # Create agent
    result = runner.invoke(app, ["agent-create", "--name", "Test", "--role", "tester", "--id", "test-01"])
    assert result.exit_code == 0
    assert "Created agent Test" in result.stdout
    
    # List agents
    result = runner.invoke(app, ["agent-list"])
    assert "test-01" in result.stdout
    assert "tester" in result.stdout
    
    # Duplicate ID
    result = runner.invoke(app, ["agent-create", "--name", "Test2", "--role", "tester", "--id", "test-01"])
    assert result.exit_code == 1
    assert "already exists" in result.stdout

def test_config_tokens(temp_ace_dir):
    from ace import app
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

def test_build_context(temp_ace_dir):
    from ace import app
    from typer.testing import CliRunner
    runner = CliRunner()
    
    # Setup global rules
    rules_dir = Path(".cursor/rules")
    rules_dir.mkdir(parents=True, exist_ok=True)
    global_rules = rules_dir / "_global.mdc"
    global_rules.write_text("Global rules content")
    
    # Setup agent and playbook
    runner.invoke(app, ["agent-create", "--name", "Auth", "--role", "auth", "--id", "auth-01"])
    playbook = rules_dir / "auth.mdc"
    playbook.write_text("Auth playbook content")
    
    # Setup ownership
    runner.invoke(app, ["own", "src/auth", "auth-01"])
    
    # Build context
    result = runner.invoke(app, ["build-context", "--path", "src/auth/login.ts", "--task-type", "implement"])
    assert result.exit_code == 0
    assert "GLOBAL RULES" in result.stdout
    assert "Global rules content" in result.stdout
    assert "AGENT PLAYBOOK (auth)" in result.stdout
    assert "Auth playbook content" in result.stdout
    assert "TASK FRAMING" in result.stdout
    assert "You are implementing new functionality in src/auth/login.ts" in result.stdout

def test_run_session_logging(temp_ace_dir):
    from ace import app
    from typer.testing import CliRunner
    runner = CliRunner()
    
    # Setup global rules
    rules_dir = Path(".cursor/rules")
    rules_dir.mkdir(parents=True, exist_ok=True)
    global_rules = rules_dir / "_global.mdc"
    global_rules.write_text("Global rules content")
    
    # Run a simple command
    result = runner.invoke(app, ["run", "echo 'Hello ACE'"])
    assert result.exit_code == 0
    assert "Hello ACE" in result.stdout
    
    # Verify session log
    sessions_dir = Path(".ace/sessions")
    session_files = list(sessions_dir.glob("*.md"))
    assert len(session_files) == 1
    session_log = session_files[0].read_text()
    assert "echo 'Hello ACE'" in session_log
    assert "Hello ACE" in session_log
    assert "GLOBAL RULES" in session_log

def test_session_continuity(temp_ace_dir):
    from ace import app
    from typer.testing import CliRunner
    runner = CliRunner()
    
    # Setup global rules
    rules_dir = Path(".cursor/rules")
    rules_dir.mkdir(parents=True, exist_ok=True)
    global_rules = rules_dir / "_global.mdc"
    global_rules.write_text("Global rules content")
    
    # Run first command to create a session
    runner.invoke(app, ["run", "echo 'Session 1'"])
    
    # Run second command and check context for session continuity
    result = runner.invoke(app, ["build-context"])
    assert "RECENT SESSIONS" in result.stdout
    assert "Session 1" in result.stdout

def test_parse_reflection_output():
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
    from ace import update_playbook
    playbook = tmp_path / "test.mdc"
    playbook.write_text("""
## Strategier & patterns
## Kända fallgropar
## Arkitekturella beslut
""")
    
    updates = [
        {"type": "str", "id": "NEW", "helpful": 1, "harmful": 0, "description": "New strategy"},
        {"type": "dec", "id": "001", "helpful": 0, "harmful": 0, "description": "Existing decision"}
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
