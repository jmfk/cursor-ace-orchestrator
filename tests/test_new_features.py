import pytest
import os
from pathlib import Path
from ace_lib.services.ace_service import ACEService
from ace_lib.models.schemas import TaskType

@pytest.fixture
def service(tmp_path):
    return ACEService(base_path=tmp_path)

def test_onboard_agent_logic(service):
    """Test the logic of agent onboarding SOP generation."""
    service.create_agent(id="onboard-test", name="Onboard Test", role="developer")
    onboarding_file = service.onboard_agent("onboard-test")
    
    assert onboarding_file.exists()
    content = onboarding_file.read_text()
    assert "SOP: Agent Onboarding" in content
    assert "onboard-test" in content
    
    # Check if mail was sent
    messages = service.list_mail("onboard-test")
    assert len(messages) == 1
    assert "ONBOARDING SOP" in messages[0].subject

def test_review_pr_logic(service):
    """Test the logic of PR review SOP generation."""
    review_file = service.review_pr("PR-999", "reviewer-999")
    
    assert review_file.exists()
    content = review_file.read_text()
    assert "SOP: PR Review - PR-999" in content
    assert "reviewer-999" in content
    
    # Check if mail was sent
    messages = service.list_mail("reviewer-999")
    assert len(messages) == 1
    assert "PR REVIEW TASK: PR-999" in messages[0].subject

def test_ui_mockup_logic(service, monkeypatch):
    """Test UI mockup generation logic (simulated)."""
    # Mock subprocess.run to avoid calling cursor-agent
    import subprocess
    from unittest.mock import MagicMock
    
    def mock_run(cmd, **kwargs):
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_res.stdout = "```tsx\nexport const Mockup = () => <div>Mockup</div>;\n```"
        return mock_res
        
    monkeypatch.setattr(subprocess, "run", mock_run)
    
    url = service.ui_mockup("Test UI", "ui-agent")
    assert "stitch.google.com/canvas/" in url
    
    mockup_id = url.split("/")[-1]
    mockup_file = service.ace_dir / "ui_mockups" / f"{mockup_id}.md"
    assert mockup_file.exists()
    assert "Test UI" in mockup_file.read_text()

def test_ui_sync_logic(service):
    """Test UI sync logic from local mockup."""
    mockup_id = "sync_test"
    mockup_dir = service.ace_dir / "ui_mockups"
    mockup_dir.mkdir(parents=True, exist_ok=True)
    mockup_file = mockup_dir / f"{mockup_id}.md"
    mockup_file.write_text("```tsx\nexport const Sync = () => <div>Sync</div>;\n```")
    
    url = f"https://stitch.google.com/canvas/{mockup_id}"
    code = service.ui_sync(url)
    assert "export const Sync" in code
