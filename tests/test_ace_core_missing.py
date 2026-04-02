import pytest
from ace_lib.services.ace_service import ACEService

@pytest.fixture
def ace_service(tmp_path):
    """Create a temporary ACE service for testing."""
    service = ACEService(tmp_path)
    service.ace_dir.mkdir(parents=True, exist_ok=True)
    service.cursor_rules_dir.mkdir(parents=True, exist_ok=True)
    return service

def test_onboarding_sop_generation(ace_service):
    """Test generating onboarding SOP with formal instructions."""
    ace_service.create_agent(id="dev-1", name="Developer 1", role="developer", responsibilities=["auth", "api"])
    onboarding_file = ace_service.onboard_agent("dev-1")
    
    assert onboarding_file.exists()
    content = onboarding_file.read_text(encoding="utf-8")
    assert "SOP: Agent Onboarding - Developer 1 (dev-1)" in content
    assert "## 1. Context Acquisition" in content
    assert "## 2. Role-Specific Setup" in content
    assert "auth, api" in content

def test_pr_review_sop_generation(ace_service):
    """Test generating PR review SOP with formal instructions."""
    ace_service.create_agent(id="reviewer-1", name="Reviewer 1", role="reviewer")
    review_file = ace_service.review_pr("PR-555", "reviewer-1")
    
    assert review_file.exists()
    content = review_file.read_text(encoding="utf-8")
    assert "SOP: PR Review - PR-555" in content
    assert "## 1. Strategy Alignment" in content
    assert "## 3. Security Check" in content
    assert "reviewer-1" in content

def test_ralph_loop_native_integration(ace_service, monkeypatch):
    """Test RALPH loop native integration in ACEService."""
    import subprocess
    from unittest.mock import MagicMock

    # Mock subprocess.run to simulate agent and test execution
    def mock_run(cmd, shell=True, capture_output=True, text=True, env=None):
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_res.stdout = "Success"
        mock_res.stderr = ""
        return mock_res

    monkeypatch.setattr(subprocess, "run", mock_run)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    
    # Mock reflection to avoid API calls
    monkeypatch.setattr(ace_service, "reflect_on_session", lambda x: "[str-001] helpful=1 harmful=0 :: Test strategy")

    ace_service.create_agent(id="agent-1", name="Agent 1", role="developer")
    
    # Create dummy PRD and plan
    prd_path = ace_service.base_path / "PRD.md"
    prd_path.write_text("# PRD content")
    plan_path = ace_service.base_path / "plan.md"
    plan_path.write_text("# Plan content")

    success, iterations = ace_service.run_loop(
        prompt="Implement feature X",
        test_cmd="echo 'tests passed'",
        max_iterations=1,
        agent_id="agent-1",
        prd_path=str(prd_path),
        plan_file=str(plan_path)
    )

    assert success is True
    assert iterations == 1
    
    # Verify session was logged
    sessions = list(ace_service.sessions_dir.glob("session_*.md"))
    assert len(sessions) > 0

def test_stitch_integration_mockup(ace_service, monkeypatch):
    """Test Google Stitch integration for mockups."""
    from ace_lib.stitch import stitch_engine
    
    mock_url = "https://stitch.google.com/canvas/stitch_test"
    mock_code = "export const TestComp = () => <div>Test</div>;"
    
    monkeypatch.setattr(stitch_engine, "generate_mockup", lambda desc, aid, key: (mock_url, mock_code))
    monkeypatch.setattr(ace_service, "get_stitch_key", lambda: "test-key")
    
    url = ace_service.ui_mockup("Test UI", "agent-1")
    assert url == mock_url
    
    # Verify files created
    mockup_id = "stitch_test"
    mockup_file = ace_service.ace_dir / "ui_mockups" / f"{mockup_id}.md"
    assert mockup_file.exists()
    assert "Test UI" in mockup_file.read_text()
    
    comp_file = ace_service.ace_dir / "ui_mockups" / "components" / mockup_id / "TestComp.tsx"
    assert comp_file.exists()
    assert "TestComp" in comp_file.read_text()
