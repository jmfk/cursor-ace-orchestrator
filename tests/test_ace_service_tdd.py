import pytest
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

def test_onboard_agent_sop(service, temp_workspace):
    """Test that onboarding an agent generates the correct SOP file (Phase 11.18)."""
    service.create_agent(id="test-agent", name="Test Agent", role="developer")
    sop_path = service.onboard_agent("test-agent")
    
    assert sop_path.exists()
    content = sop_path.read_text()
    assert "SOP: Agent Onboarding - Test Agent (test-agent)" in content
    assert "## 1. Context Acquisition" in content
    
    # Check if memory file was created
    memory_file = temp_workspace / ".cursor/rules/developer.mdc"
    assert memory_file.exists()
    assert "# Test Agent Playbook (developer)" in memory_file.read_text()

def test_review_pr_sop(service, temp_workspace):
    """Test that PR review generates the correct SOP file (Phase 11.18)."""
    review_path = service.review_pr("PR-123", "test-agent")
    
    assert review_path.exists()
    content = review_path.read_text()
    assert "SOP: PR Review - PR-123" in content
    assert "Reviewer**: test-agent" in content
    assert "## 3. Security Check" in content

def test_ui_mockup_integration(service, temp_workspace, monkeypatch):
    """Test UI mockup generation and component extraction (Phase 11.18)."""

    # Mock stitch engine generate_mockup
    import ace_lib.stitch.stitch_engine as stitch_engine
    monkeypatch.setattr(stitch_engine, "generate_mockup",
                        lambda desc, aid, key: ("https://stitch.google.com/canvas/test_id",
                                                "export const Button = () => <button>Click</button>;"))

    url = service.ui_mockup("A simple button", "test-agent")
    
    assert "stitch.google.com/canvas/test_id" in url
    
    # Check if mockup file was created
    mockup_file = service.ace_dir / "ui_mockups" / "test_id.md"
    assert mockup_file.exists()
    assert "export const Button" in mockup_file.read_text()
    
    # Check if components were extracted
    component_file = service.ace_dir / "ui_mockups" / "components" / "test_id" / "Button.tsx"
    assert component_file.exists()
    assert "export const Button" in component_file.read_text()

def test_ui_sync_integration(service, temp_workspace, monkeypatch):
    """Test UI sync from Stitch URL (Phase 11.18)."""
    import ace_lib.stitch.stitch_engine as stitch_engine
    monkeypatch.setattr(stitch_engine, "sync_mockup",
                        lambda url, key: "export const NewButton = () => <button>New</button>;")
    
    # Create an initial mockup to test diffing
    mockup_id = "test_sync_id"
    mockup_file = service.ace_dir / "ui_mockups" / f"{mockup_id}.md"
    mockup_file.parent.mkdir(parents=True, exist_ok=True)
    mockup_file.write_text("```tsx\nexport const OldButton = () => <button>Old</button>;\n```")
    
    url = f"https://stitch.google.com/canvas/{mockup_id}"
    service.ui_sync(url)
    
    # Check if updated
    content = mockup_file.read_text()
    assert "export const NewButton" in content
    
    # Check if diff was created
    diff_file = service.ace_dir / "ui_mockups" / f"{mockup_id}_diff.txt"
    assert diff_file.exists()
