import pytest
import json
import re
from unittest.mock import MagicMock, patch, ANY
from pathlib import Path
from typer.testing import CliRunner

# Mocking the ACE library components based on the provided context
from ace_lib.stitch.stitch_engine import generate_mockup, sync_mockup, extract_components
from ace_lib.models.schemas import Agent, AgentsConfig, LivingSpec

# Assuming 'ace' is the main CLI entry point
# In a real scenario, we would import the actual app object
# from ace import app
from ace import app 

runner = CliRunner()

@pytest.fixture
def mock_env(tmp_path):
    """Sets up a mock .ace environment with a UI agent."""
    ace_dir = tmp_path / ".ace"
    ace_dir.mkdir()
    specs_dir = ace_dir / "specs" / "login-page"
    specs_dir.mkdir(parents=True)
    
    # Create a dummy agents.yaml
    agents_file = ace_dir / "agents.yaml"
    agents_file.write_text("""
version: '1'
agents:
  - id: ui-agent-01
    name: Pixel
    role: ui-designer
    email: pixel@ace.local
    memory_file: .cursor/rules/ui.mdc
    responsibilities: ["UI Design", "Tailwind"]
""")
    
    # Create a dummy spec
    spec_file = specs_dir / "intent.md"
    spec_file.write_text("# Intent: Login Page\nConstraints: Dark mode, Tailwind.")
    
    return tmp_path

@pytest.fixture
def stitch_api_mock(requests_mock):
    """Mocks the Google Stitch API responses."""
    # Mock Mockup Generation
    requests_mock.post(
        "https://api.stitch.google.com/v1/mockup",
        json={
            "url": "https://stitch.google.com/canvas/mock_123",
            "code": "export const Button = () => <button className='bg-blue-500'>Click</button>;"
        },
        status_code=200
    )
    # Mock Mockup Sync/Retrieval
    requests_mock.get(
        "https://api.stitch.google.com/v1/mockup/mock_123",
        json={
            "code": "export const Navbar = () => <nav>Home</nav>;"
        },
        status_code=200
    )
    return requests_mock

# --- Unit Tests for Stitch Engine ---

def test_generate_mockup_logic(stitch_api_mock):
    """Verifies the core logic of calling the Stitch API for mockup generation."""
    url, code = generate_mockup(
        description="A sleek dashboard", 
        agent_id="ui-agent-01", 
        api_key="test-key"
    )
    assert "mock_123" in url
    assert "bg-blue-500" in code
    assert stitch_api_mock.called

def test_extract_components_regex():
    """Verifies that the engine can correctly parse individual React/Tailwind components from Stitch output."""
    stitch_code = """
    export const Header = () => <header>Head</header>;
    export const Footer = () => <footer>Foot</footer>;
    """
    components = extract_components(stitch_code)
    assert "Header" in components
    assert "Footer" in components
    assert "<header>Head</header>" in components["Header"]

# --- CLI Command Tests (Success Criteria 1 & 2) ---

def test_cli_ui_mockup_command(mock_env, monkeypatch):
    """
    Success Criteria: The 'ace ui mockup' command generates a design description based on project constraints.
    Verifies that the CLI correctly reads constraints and triggers the mockup generation.
    """
    monkeypatch.chdir(mock_env)
    
    # Mock the internal call to avoid real API usage during CLI test
    with patch("ace_lib.stitch.stitch_engine.generate_mockup") as mock_gen:
        mock_gen.return_value = ("https://stitch.google.com/canvas/mock_123", "// code")
        
        result = runner.invoke(app, [
            "ui", "mockup", 
            "Login page with dark mode", 
            "--agent", "ui-agent-01"
        ])

        assert result.exit_code == 0
        assert "Generating UI mockup" in result.stdout
        assert "https://stitch.google.com/canvas/mock_123" in result.stdout
        
        # Verify that the description passed to the engine includes the prompt
        mock_gen.assert_called_once()
        args, _ = mock_gen.call_args
        assert "Login page with dark mode" in args[0]

def test_cli_ui_sync_command(mock_env, monkeypatch):
    """
    Success Criteria: The 'ace ui sync' command successfully imports Tailwind/Flutter code from a Stitch canvas URL.
    """
    monkeypatch.chdir(mock_env)
    
    with patch("ace_lib.stitch.stitch_engine.sync_mockup") as mock_sync:
        mock_sync.return_value = "export const Imported = () => <div>Imported</div>;"
        
        canvas_url = "https://stitch.google.com/canvas/mock_123"
        result = runner.invoke(app, ["ui", "sync", canvas_url])

        assert result.exit_code == 0
        assert "Syncing UI code" in result.stdout
        assert "Code synced successfully" in result.stdout
        mock_sync.assert_called_with(canvas_url, api_key=ANY)

# --- Visual Verification Integration (Success Criteria 3) ---

def test_visual_verification_metadata_association(mock_env, monkeypatch):
    """
    Success Criteria: Visual verification tests (Playwright) can validate the implemented UI against the mockup intent.
    This test verifies that when a mockup is generated, the canvas URL is stored in the spec metadata 
    so that Playwright tests can access the 'source of truth' for visual comparison.
    """
    monkeypatch.chdir(mock_env)
    
    # Simulate the workflow where an agent generates a mockup for a specific feature spec
    feature_spec_path = mock_env / ".ace" / "specs" / "login-page" / "meta.json"
    
    # We invoke a command that links a mockup to a spec
    result = runner.invoke(app, [
        "spec", "link-mockup", "login-page", 
        "--url", "https://stitch.google.com/canvas/mock_123"
    ])
    
    assert result.exit_code == 0
    
    # Verify the metadata file now contains the Stitch URL for Playwright to use
    with open(feature_spec_path, "r") as f:
        meta = json.load(f)
        assert meta["stitch_canvas_url"] == "https://stitch.google.com/canvas/mock_123"

def test_visual_test_trigger_logic(mock_env, monkeypatch):
    """
    Verifies that the 'ace ui verify' command (which wraps Playwright) correctly identifies 
    the mockup URL to compare against.
    """
    monkeypatch.chdir(mock_env)
    
    # Setup metadata
    meta_path = mock_env / ".ace" / "specs" / "login-page" / "meta.json"
    meta_path.write_text(json.dumps({"stitch_canvas_url": "https://stitch.google.com/canvas/mock_123"}))

    with patch("subprocess.run") as mock_run:
        # Simulate running the playwright command
        mock_run.return_value = MagicMock(returncode=0)
        
        result = runner.invoke(app, ["ui", "verify", "login-page"])
        
        assert result.exit_code == 0
        # Verify that subprocess was called with playwright and the correct URL
        args, _ = mock_run.call_args
        command_str = " ".join(args[0])
        assert "playwright test" in command_str
        assert "https://stitch.google.com/canvas/mock_123" in command_str