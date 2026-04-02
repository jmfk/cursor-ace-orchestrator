import pytest
import subprocess
from unittest.mock import MagicMock
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

def test_onboard_agent_sop_full(service, temp_workspace):
    """Verify onboarding agent generates SOP and initializes playbook."""
    service.create_agent(id="dev-1", name="Dev One", role="developer", responsibilities=["core"])
    sop_path = service.onboard_agent("dev-1")
    
    assert sop_path.exists()
    content = sop_path.read_text()
    assert "SOP: Agent Onboarding - Dev One (dev-1)" in content
    assert "core" in content
    
    # Verify playbook creation
    playbook_path = temp_workspace / ".cursor/rules/developer.mdc"
    assert playbook_path.exists()
    assert "## Strategier & patterns" in playbook_path.read_text()

def test_review_pr_sop_full(service, temp_workspace):
    """Verify PR review generates SOP and sends notification."""
    review_path = service.review_pr("PR-999", "reviewer-1")
    
    assert review_path.exists()
    content = review_path.read_text()
    assert "SOP: PR Review - PR-999" in content
    assert "reviewer-1" in content
    
    # Verify mail notification
    messages = service.list_mail("reviewer-1")
    assert len(messages) == 1
    assert "PR REVIEW TASK: PR-999" in messages[0].subject

def test_run_loop_integration(service, temp_workspace, monkeypatch):
    """Verify RALPH loop integration with context, execution, and reflection."""
    # Mock subprocess.run for cursor-agent and test_cmd
    def mock_run(cmd, shell=True, capture_output=True, text=True, env=None, **kwargs):
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_res.stdout = "Success output"
        mock_res.stderr = ""
        return mock_res

    monkeypatch.setattr(subprocess, "run", mock_run)
    
    # Mock run_agent_task to simulate successful execution
    monkeypatch.setattr(service, "run_agent_task", lambda **kwargs: True)
    
    # Mock reflection
    monkeypatch.setattr(service, "reflect_on_session", lambda x: "[str-001] helpful=1 harmful=0 :: New strategy")
    monkeypatch.setattr(service, "get_anthropic_client", lambda: MagicMock())

    # Setup agent and playbook
    service.create_agent(id="dev-1", name="Dev 1", role="developer")
    playbook_path = temp_workspace / ".cursor/rules/developer.mdc"
    playbook_path.parent.mkdir(parents=True, exist_ok=True)
    playbook_path.write_text("# Playbook\n## Strategier & patterns\n")

    # Dummy PRD and plan
    prd_path = temp_workspace / "PRD.md"
    prd_path.write_text("# PRD")
    plan_path = temp_workspace / "plan.md"
    plan_path.write_text("# Plan")

    success, iterations = service.run_loop(
        prompt="Implement feature X",
        test_cmd="pytest",
        max_iterations=1,
        agent_id="dev-1",
        prd_path=str(prd_path),
        plan_file=str(plan_path)
    )

    assert success is True
    assert iterations == 1
    assert "[str-001]" in playbook_path.read_text()

def test_stitch_integration_logic(service, temp_workspace, monkeypatch):
    """Verify Stitch integration logic for mockup and sync."""
    from ace_lib.stitch import stitch_engine

    # Mock stitch_engine
    monkeypatch.setattr(
        stitch_engine,
        "generate_mockup",
        lambda d, a, k: (
            "https://stitch.google.com/canvas/mock_123",
            "export const App = () => <div>Mock</div>;",
        ),
    )
    monkeypatch.setattr(
        stitch_engine,
        "sync_mockup",
        lambda u, k: "export const App = () => <div>Synced</div>;",
    )
    monkeypatch.setattr(service, "get_stitch_key", lambda: "test-key")

    # Test mockup generation
    url = service.ui_mockup("Dashboard", "agent-1")
    assert url == "https://stitch.google.com/canvas/mock_123"
    
    mockup_file = temp_workspace / ".ace/ui_mockups/mock_123.md"
    assert mockup_file.exists()
    assert "Dashboard" in mockup_file.read_text()

    # Test sync
    code = service.ui_sync(url)
    assert "Synced" in code
    assert "Synced" in mockup_file.read_text()
