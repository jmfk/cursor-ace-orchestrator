from ace import app
from ace_lib.models.schemas import Agent, AgentsConfig
from typer.testing import CliRunner

runner = CliRunner()


def test_ui_mockup_command(tmp_path, monkeypatch):
    # Setup mock .ace directory
    ace_dir = tmp_path / ".ace"
    ace_dir.mkdir()
    (ace_dir / "agents.yaml").write_text("version: '1'\nagents: []")

    # Mock load_agents to return a test agent
    test_agent = Agent(
        id="ui-agent-01", name="Vogue", role="ui-agent",
        email="vogue@ace.local", memory_file=".cursor/rules/ui.mdc",
        status="active"
    )

    def mock_load_agents():
        return AgentsConfig(version="1", agents=[test_agent])

    monkeypatch.setattr("ace.load_agents", mock_load_agents)
    monkeypatch.chdir(tmp_path)

    # Run ace ui mockup
    result = runner.invoke(
        app,
        [
            "ui",
            "mockup",
            "Create a login page",
            "--agent",
            "ui-agent-01",
        ],
    )

    assert result.exit_code == 0
    assert "Generating UI mockup" in result.stdout
    assert "Create a login page" in result.stdout
    assert "ui-agent-01" in result.stdout
    assert "Generating UI mockup" in result.stdout
    assert "Create a login page" in result.stdout
    assert "ui-agent-01" in result.stdout


def test_ui_sync_command(tmp_path, monkeypatch):
    # Setup mock .ace directory
    ace_dir = tmp_path / ".ace"
    ace_dir.mkdir()

    # Mock load_agents to return a test agent
    test_agent = Agent(
        id="ui-agent-01", name="Vogue", role="ui-agent",
        email="vogue@ace.local", memory_file=".cursor/rules/ui.mdc",
        status="active"
    )

    def mock_load_agents():
        return AgentsConfig(version="1", agents=[test_agent])

    monkeypatch.setattr("ace.load_agents", mock_load_agents)
    monkeypatch.chdir(tmp_path)

    # Run ace ui sync
    result = runner.invoke(
        app, ["ui", "sync", "https://stitch.google.com/canvas/123"]
    )

    assert result.exit_code == 0
    assert "Syncing UI code from:" in result.stdout
    assert "123" in result.stdout
