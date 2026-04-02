import pytest
from ace_lib.services.ace_service import ACEService

@pytest.fixture
def temp_workspace(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return workspace

@pytest.fixture
def service(temp_workspace):
    return ACEService(base_path=temp_workspace)

def test_run_loop_basic(service, monkeypatch):
    """Test the native run_loop (RALPH loop) integration."""
    import subprocess
    from unittest.mock import MagicMock

    # Mock subprocess.run to simulate agent and test execution
    def mock_run(cmd, shell=True, capture_output=True, text=True, env=None, check=False):
        mock_res = MagicMock()
        if "cursor-agent" in cmd:
            mock_res.returncode = 0
            mock_res.stdout = "Agent success output with code block: ```tsx\nconst x = 1;\n```"
            mock_res.stderr = ""
        elif "pytest" in cmd:
            mock_res.returncode = 0
            mock_res.stdout = "Test success output"
            mock_res.stderr = ""
        elif "git status" in cmd:
            mock_res.returncode = 0
            mock_res.stdout = "M file.py"
        elif "git" in cmd:
            mock_res.returncode = 0
            mock_res.stdout = ""
        return mock_res

    monkeypatch.setattr(subprocess, "run", mock_run)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    
    # Mock reflection to avoid API calls
    monkeypatch.setattr(service, "reflect_on_session", lambda x: "No new learnings.")

    # Setup necessary files
    prd_file = service.base_path / "PRD.md"
    prd_file.write_text("# PRD\nImplement feature X")
    plan_file = service.base_path / "plan.md"
    plan_file.write_text("- [ ] Task 1")

    success, iterations = service.run_loop(
        prompt="Implement feature X",
        test_cmd="pytest",
        max_iterations=1,
        prd_path=str(prd_file),
        plan_file=str(plan_file)
    )

    assert success is True
    assert iterations == 1

def test_sop_generation(service):
    """Test formal SOP generation for onboarding and PR reviews."""
    service.create_agent(id="dev-1", name="Dev 1", role="developer")
    
    # Onboarding
    onboarding_file = service.onboard_agent("dev-1")
    assert onboarding_file.exists()
    assert "SOP: Agent Onboarding" in onboarding_file.read_text()
    
    # PR Review
    review_file = service.review_pr("PR-1", "dev-1")
    assert review_file.exists()
    assert "SOP: PR Review" in review_file.read_text()
    
    # Audit
    audit_file = service.audit_agent("dev-1")
    assert audit_file.exists()
    assert "SOP: Agent Audit" in audit_file.read_text()

def test_stitch_integration_stubs(service, monkeypatch):
    """Test Google Stitch integration stubs."""
    from ace_lib.stitch import stitch_engine
    
    mock_url = "https://stitch.google.com/canvas/test"
    mock_code = "export const App = () => <div>Test</div>;"
    
    monkeypatch.setattr(stitch_engine, "generate_mockup", lambda *args: (mock_url, mock_code))
    monkeypatch.setattr(stitch_engine, "extract_components", lambda *args: {"App": mock_code})
    monkeypatch.setattr(service, "get_stitch_key", lambda: "test-key")

    url = service.ui_mockup("Test UI", "dev-1")
    assert url == mock_url
    
    mockup_id = url.split("/")[-1]
    mockup_file = service.ace_dir / "ui_mockups" / f"{mockup_id}.md"
    assert mockup_file.exists()
    assert mock_code in mockup_file.read_text()

def test_rbac_enforcement(service, monkeypatch):
    """Test RBAC enforcement in run_agent_task."""
    service.create_agent(id="restricted-agent", name="Restricted", role="dev")
    agents_config = service.load_agents()
    agent = agents_config.agents[0]
    agent.allowed_paths = ["src/allowed"]
    agent.forbidden_commands = ["rm -rf"]
    service.save_agents(agents_config)
    service.clear_cache()

    # Test path restriction
    success = service.run_agent_task(
        command="ls",
        path="src/forbidden/file.py",
        agent_id="restricted-agent"
    )
    assert success is False

    # Test command restriction
    success = service.run_agent_task(
        command="rm -rf /",
        path="src/allowed/file.py",
        agent_id="restricted-agent"
    )
    assert success is False
