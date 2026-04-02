import pytest
from ace_lib.services.ace_service import ACEService

@pytest.fixture
def ace_service(tmp_path):
    """Create a temporary ACE service for testing."""
    service = ACEService(tmp_path)
    service.ace_dir.mkdir(parents=True, exist_ok=True)
    service.cursor_rules_dir.mkdir(parents=True, exist_ok=True)
    for subdir in ["mail", "sessions", "decisions", "specs"]:
        (service.ace_dir / subdir).mkdir(parents=True, exist_ok=True)
    return service

def test_onboard_agent_sop(ace_service):
    """Test formal onboarding SOP generation (Phase 9.5)."""
    ace_service.create_agent(id="auth-expert", name="Aegis", role="auth")
    sop_path = ace_service.onboard_agent("auth-expert")
    
    assert sop_path.exists()
    content = sop_path.read_text()
    assert "# SOP: Agent Onboarding - Aegis (auth-expert)" in content
    assert "## 1. Context Acquisition" in content
    assert "## 2. Role-Specific Setup" in content
    
    # Verify mail notification
    messages = ace_service.list_mail("auth-expert")
    assert any(m.subject == "ONBOARDING SOP" for m in messages)

def test_pr_review_sop(ace_service):
    """Test formal PR review SOP generation (Phase 9.5)."""
    ace_service.create_agent(id="reviewer-1", name="Reviewer One", role="reviewer")
    sop_path = ace_service.review_pr("PR-456", "reviewer-1")
    
    assert sop_path.exists()
    content = sop_path.read_text()
    assert "# SOP: PR Review - PR-456" in content
    assert "- **Reviewer**: reviewer-1" in content
    assert "## 1. Strategy Alignment" in content
    
    # Verify mail notification
    messages = ace_service.list_mail("reviewer-1")
    assert any(m.subject == "PR REVIEW TASK: PR-456" for m in messages)

def test_ui_mockup_integration(ace_service, monkeypatch):
    """Test Google Stitch integration (Phase 4.5)."""
    # Mock the agent-based mockup generation to avoid subprocess call
    monkeypatch.setattr(
        ace_service,
        "_generate_mockup_with_agent",
        lambda desc: "export const Mock = () => <div>Mock</div>;"
    )
    
    mockup_url = ace_service.ui_mockup("Login Screen", "auth-expert")
    assert "stitch.google.com/canvas/stitch_" in mockup_url
    
    # Verify mockup file creation
    mockup_dir = ace_service.ace_dir / "ui_mockups"
    mockup_files = list(mockup_dir.glob("stitch_*.md"))
    assert len(mockup_files) == 1
    content = mockup_files[0].read_text()
    assert "# UI Mockup: Login Screen" in content
    assert "export const Mock" in content

def test_ui_sync_integration(ace_service, monkeypatch):
    """Test Google Stitch sync (Phase 8.3)."""
    mockup_id = "stitch_12345"
    url = f"https://stitch.google.com/canvas/{mockup_id}"
    
    # Create a local mockup file first
    mockup_dir = ace_service.ace_dir / "ui_mockups"
    mockup_dir.mkdir(parents=True, exist_ok=True)
    mockup_file = mockup_dir / f"{mockup_id}.md"
    mockup_file.write_text("# UI Mockup\n```tsx\nexport const Old = () => <div />;\n```")
    
    # Mock stitch_engine.sync_mockup
    import ace_lib.stitch.stitch_engine as stitch_engine
    monkeypatch.setattr(
        stitch_engine,
        "sync_mockup",
        lambda url, key: "export const New = () => <div />;"
    )
    
    synced_code = ace_service.ui_sync(url)
    assert "export const New" in synced_code
    
    # Verify file update
    content = mockup_file.read_text()
    assert "export const New" in content
    assert "(Synced)" in content
