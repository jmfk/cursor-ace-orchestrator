import pytest
import subprocess
from unittest.mock import MagicMock, patch
from ace_lib.services.ace_service import ACEService

@pytest.fixture
def temp_workspace(tmp_path):
    """Create a temporary workspace for testing."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / ".ace").mkdir()
    return workspace

@pytest.fixture
def service(temp_workspace):
    """Initialize ACEService in a temporary workspace."""
    return ACEService(base_path=temp_workspace)

def test_onboarding_sop_generation(service, temp_workspace):
    """Test generating onboarding SOP (Phase 9.5)."""
    service.create_agent(id="dev-1", name="Developer 1", role="developer", responsibilities=["src/core"])
    sop_path = service.onboard_agent("dev-1")

    assert sop_path.exists()
    content = sop_path.read_text()
    assert "SOP: Agent Onboarding - Developer 1 (dev-1)" in content
    assert "## 1. Context Acquisition" in content
    assert "src/core" in content

    # Check if memory file was created with correct sections
    memory_file = temp_workspace / ".cursor/rules/developer.mdc"
    assert memory_file.exists()
    assert "## Strategier & patterns" in memory_file.read_text()
    assert "## Kända fallgropar" in memory_file.read_text()

def test_pr_review_sop_generation(service):
    """Test generating PR review SOP (Phase 9.5)."""
    review_path = service.review_pr("PR-123", "reviewer-1")
    assert review_path.exists()
    content = review_path.read_text()
    assert "SOP: PR Review - PR-123" in content
    assert "Reviewer**: reviewer-1" in content
    assert "## 3. Security Check" in content

def test_audit_sop_generation(service):
    """Test generating audit SOP (Phase 9.5)."""
    service.create_agent(id="dev-1", name="Developer 1", role="developer")
    audit_path = service.audit_agent("dev-1")
    assert audit_path.exists()
    content = audit_path.read_text()
    assert "SOP: Agent Audit - Developer 1 (dev-1)" in content
    assert "## 1. Playbook Quality" in content

def test_google_stitch_mockup_logic(service, monkeypatch):
    """Test Google Stitch mockup generation logic (Phase 4.5)."""
    from ace_lib.stitch import stitch_engine

    mock_url = "https://stitch.google.com/canvas/test_mockup"
    mock_code = "export const Mockup = () => <div>Mockup</div>;"

    monkeypatch.setattr(stitch_engine, "generate_mockup", lambda *args, **kwargs: (mock_url, mock_code))
    monkeypatch.setattr(service, "get_stitch_key", lambda: "test-key")

    url = service.ui_mockup("Login page", "agent-1")
    assert url == mock_url

    mockup_id = url.split("/")[-1]
    mockup_file = service.ace_dir / "ui_mockups" / f"{mockup_id}.md"
    assert mockup_file.exists()
    assert mock_code in mockup_file.read_text()

def test_google_stitch_sync_logic(service, monkeypatch):
    """Test Google Stitch code sync logic (Phase 8.3)."""
    from ace_lib.stitch import stitch_engine

    mockup_id = "test_mockup"
    new_code = "export const Test = () => <div>New Test</div>;"

    monkeypatch.setattr(stitch_engine, "sync_mockup", lambda *args, **kwargs: new_code)
    monkeypatch.setattr(service, "get_stitch_key", lambda: "test-key")

    url = f"https://stitch.google.com/canvas/{mockup_id}"
    code = service.ui_sync(url)
    assert code == new_code

    mockup_file = service.ace_dir / "ui_mockups" / f"{mockup_id}.md"
    assert mockup_file.exists()
    assert "New Test" in mockup_file.read_text()

def test_run_loop_native(service, temp_workspace, monkeypatch):
    """Test native RALPH loop integration (Phase 4.1)."""

    def mock_run_agent_task(*args, **kwargs):
        return True

    def mock_subprocess_run(cmd, *args, **kwargs):
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_res.stdout = "Test success"
        mock_res.stderr = ""
        return mock_res

    monkeypatch.setattr(service, "run_agent_task", mock_run_agent_task)
    monkeypatch.setattr(subprocess, "run", mock_subprocess_run)
    monkeypatch.setattr(service, "get_anthropic_client", lambda: MagicMock())
    monkeypatch.setattr(service, "reflect_on_session", lambda x: "No new learnings.")

    # Setup dummy PRD and plan
    prd_path = temp_workspace / "PRD.md"
    prd_path.write_text("# PRD")
    plan_path = temp_workspace / "plan.md"
    plan_path.write_text("# Plan")

    success, iterations = service.run_loop(
        prompt="Test prompt",
        test_cmd="pytest",
        max_iterations=1,
        prd_path=str(prd_path),
        plan_file=str(plan_path)
    )

    assert success is True
    assert iterations == 1

def test_rbac_path_restriction(service, temp_workspace):
    """Test RBAC path restriction (Phase 10.2)."""
    service.create_agent(
        id="restricted-agent",
        name="Restricted",
        role="dev",
        allowed_paths=["src/allowed"]
    )

    # Attempt to run task in forbidden path
    success = service.run_agent_task(
        command="ls",
        path="src/forbidden/file.py",
        agent_id="restricted-agent"
    )
    assert success is False

    # Attempt to run task in allowed path (mocking execution)
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
        success = service.run_agent_task(
            command="ls",
            path="src/allowed/file.py",
            agent_id="restricted-agent"
        )
        assert success is True

def test_rbac_command_restriction(service):
    """Test RBAC command restriction (Phase 10.2)."""
    service.create_agent(
        id="no-rm-agent",
        name="No RM",
        role="dev",
        forbidden_commands=["rm -rf"]
    )

    success = service.run_agent_task(
        command="rm -rf /",
        agent_id="no-rm-agent"
    )
    assert success is False
