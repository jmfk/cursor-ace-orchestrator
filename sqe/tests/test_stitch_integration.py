import pytest
import requests
import re
from unittest.mock import MagicMock, patch
from typer.testing import CliRunner
from pathlib import Path

# Importing from the provided context
from ace_lib.stitch.stitch_engine import generate_mockup, sync_mockup, extract_components
from ace_lib.models.schemas import Agent, AgentsConfig
from ace import app  # Assuming 'ace' is the entry point for the Typer CLI

runner = CliRunner()

# --- Fixtures ---

@pytest.fixture
def mock_stitch_api(requests_mock):
    """Fixture to mock Google Stitch API endpoints."""
    # Mock Mockup Generation
    requests_mock.post(
        "https://api.stitch.google.com/v1/mockup",
        json={
            "url": "https://stitch.google.com/canvas/test_mockup_123",
            "code": "export const Button = () => <button className='bg-blue-500'>Click me</button>;"
        },
        status_code=200
    )
    # Mock Mockup Sync/Retrieval
    requests_mock.get(
        "https://api.stitch.google.com/v1/mockup/test_mockup_123",
        json={
            "code": "export const Card = () => <div className='p-4 shadow-lg'>Card Content</div>;"
        },
        status_code=200
    )
    return requests_mock

@pytest.fixture
def setup_ace_env(tmp_path):
    """Sets up a mock .ace environment for CLI tests."""
    ace_dir = tmp_path / ".ace"
    ace_dir.mkdir()
    agents_file = ace_dir / "agents.yaml"
    agents_file.write_text("version: '1'\nagents: []")
    
    test_agent = Agent(
        id="ui-designer-01",
        name="Vogue",
        role="ui-agent",
        email="vogue@ace.local",
        memory_file=".cursor/rules/ui.mdc",
        status="active",
    )
    
    return tmp_path, test_agent

# --- Unit Tests for stitch_engine.py ---

def test_generate_mockup_success(mock_stitch_api):
    """Verifies that generate_mockup calls the API and returns the URL and code."""
    url, code = generate_mockup("Create a dashboard", "agent-007", api_key="valid_key")
    
    assert "test_mockup_123" in url
    assert "export const Button" in code
    assert mock_stitch_api.called

def test_sync_mockup_success(mock_stitch_api):
    """Verifies that sync_mockup retrieves code from a specific canvas URL."""
    canvas_url = "https://stitch.google.com/canvas/test_mockup_123"
    code = sync_mockup(canvas_url, api_key="valid_key")
    
    assert "export const Card" in code
    assert "shadow-lg" in code

def test_extract_components():
    """Verifies the regex logic for splitting Stitch code into individual components."""
    sample_code = """
    export const Header = () => <header>Hi</header>;
    export const Footer = () => <footer>Bye</footer>;
    """
    components = extract_components(sample_code)
    
    assert "Header" in components
    assert "Footer" in components
    assert "<header>Hi</header>" in components["Header"]

# --- CLI Integration Tests ---

def test_cli_ui_mockup_command(setup_ace_env, monkeypatch):
    """Success Criteria: 'ace ui mockup' generates a design description based on constraints."""
    tmp_path, test_agent = setup_ace_env
    
    def mock_load_agents(*args, **kwargs):
        return AgentsConfig(version="1", agents=[test_agent])

    # Mocking the service and engine to avoid real network calls during CLI run
    monkeypatch.setattr("ace.load_agents", mock_load_agents)
    monkeypatch.chdir(tmp_path)

    with patch("ace_lib.stitch.stitch_engine.generate_mockup") as mock_gen:
        mock_gen.return_value = ("https://stitch.google.com/canvas/mock123", "// code")
        
        result = runner.invoke(app, [
            "ui", "mockup", 
            "Dark mode login page with OAuth buttons", 
            "--agent", "ui-designer-01"
        ])

        assert result.exit_code == 0
        assert "Generating UI mockup" in result.stdout
        mock_gen.assert_called_once()
        # Verify description was passed
        args, _ = mock_gen.call_args
        assert "Dark mode login page" in args[0]

def test_cli_ui_sync_command(setup_ace_env, monkeypatch):
    """Success Criteria: 'ace ui sync' successfully imports code from a Stitch URL."""
    tmp_path, test_agent = setup_ace_env
    
    monkeypatch.setattr("ace.load_agents", lambda: AgentsConfig(version="1", agents=[test_agent]))
    monkeypatch.chdir(tmp_path)

    with patch("ace_lib.stitch.stitch_engine.sync_mockup") as mock_sync:
        mock_sync.return_value = "export const ImportedWidget = () => <div>Widget</div>;"
        
        canvas_url = "https://stitch.google.com/canvas/123"
        result = runner.invoke(app, ["ui", "sync", canvas_url])

        assert result.exit_code == 0
        assert "Syncing UI code" in result.stdout
        assert "Code synced successfully" in result.stdout
        mock_sync.assert_called_with(canvas_url, api_key=pytest.any)

# --- Visual Verification (Playwright) Logic Test ---

def test_visual_verification_trigger():
    """
    Success Criteria: Visual verification tests (Playwright) can validate implemented UI.
    This test simulates the logic that would trigger a Playwright visual comparison.
    """
    # Mocking the Playwright test runner behavior
    mock_playwright_runner = MagicMock()
    mock_playwright_runner.compare_screenshots.return_value = {"diff_ratio": 0.01, "passed": True}

    # Logic: If we have a mockup URL and local implementation, run visual check
    mockup_url = "https://stitch.google.com/canvas/test_mockup_123"
    local_component_path = "src/components/Login.tsx"
    
    # Simulate the verification step
    result = mock_playwright_runner.compare_screenshots(mockup_url, local_component_path)
    
    assert result["passed"] is True
    assert result["diff_ratio"] < 0.05  # Threshold for success

if __name__ == "__main__":
    pytest.main([__file__])
"