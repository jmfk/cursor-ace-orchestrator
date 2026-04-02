import pytest
import subprocess
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

def test_ralph_loop_integration(service, monkeypatch):
    """Test the RALPH loop integration (Phase 4.1)."""
    # Mock the run_agent_task and reflect_on_session
    monkeypatch.setattr(service, "run_agent_task", lambda *args, **kwargs: True)
    monkeypatch.setattr(service, "reflect_on_session", lambda *args, **kwargs: "No new learnings.")
    monkeypatch.setattr(service, "get_anthropic_client", lambda: None)
    
    # Mock subprocess.run for the test command
    class MockResult:
        returncode = 0
        stdout = "Tests passed"
        stderr = ""
    
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: MockResult())
    
    # Create dummy PRD and plan files
    (service.base_path / "PRD-01 - Cursor-ace-orchestrator-prd.md").write_text("PRD Content")
    (service.base_path / "plan.md").write_text("Plan Content")
    
    success, iterations = service.run_loop(
        prompt="Test task",
        test_cmd="pytest",
        max_iterations=2,
        prd_path=str(service.base_path / "PRD-01 - Cursor-ace-orchestrator-prd.md"),
        plan_file=str(service.base_path / "plan.md")
    )
    
    assert success is True
    assert iterations == 1

def test_sop_onboarding_full(service):
    """Test full onboarding SOP flow (Phase 9.5)."""
    agent_id = "onboard-test"
    service.create_agent(id=agent_id, name="Onboarder", role="onboarder")
    
    onboarding_file = service.onboard_agent(agent_id)
    assert onboarding_file.exists()
    
    # Check if mail was sent
    mail_dir = service.mail_dir / agent_id
    assert mail_dir.exists()
    mail_files = list(mail_dir.glob("*.yaml"))
    assert len(mail_files) > 0
    
    # Check if memory file was initialized
    memory_path = service.base_path / ".cursor/rules/onboarder.mdc"
    assert memory_path.exists()
    assert "# Onboarder Playbook (onboarder)" in memory_path.read_text()

def test_ui_mockup_with_components(service, monkeypatch):
    """Test UI mockup generation with component extraction (Phase 4.5/8.3)."""
    from ace_lib.stitch import stitch_engine
    
    mock_url = "https://stitch.google.com/canvas/comp_test"
    mock_code = """
export const Button = () => <button>Click</button>;
export const Card = () => <div>Card</div>;
"""
    
    monkeypatch.setattr(stitch_engine, "generate_mockup", lambda *args, **kwargs: (mock_url, mock_code))
    monkeypatch.setattr(service, "get_stitch_key", lambda: "test-key")
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "true")
    
    url = service.ui_mockup("Component test", "agent-1")
    assert url == mock_url
    
    # Check if components were extracted
    comp_dir = service.ace_dir / "ui_mockups" / "components" / "comp_test"
    assert comp_dir.exists()
    assert (comp_dir / "Button.tsx").exists()
    assert (comp_dir / "Card.tsx").exists()
