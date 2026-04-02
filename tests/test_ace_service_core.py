import pytest
from ace_lib.services.ace_service import ACEService
from ace_lib.models.schemas import TaskType

@pytest.fixture
def ace_service(tmp_path):
    """Create a temporary ACE service for testing."""
    service = ACEService(tmp_path)
    service.ace_dir.mkdir(parents=True, exist_ok=True)
    service.cursor_rules_dir.mkdir(parents=True, exist_ok=True)
    return service

def test_onboard_agent_creates_files(ace_service):
    # Setup
    agent_id = "test-agent"
    ace_service.create_agent(id=agent_id, name="Test Agent", role="tester")
    
    # Execute
    sop_path = ace_service.onboard_agent(agent_id)
    
    # Verify SOP file
    assert sop_path.exists()
    assert f"onboarding_{agent_id}.md" in sop_path.name
    content = sop_path.read_text()
    assert "# SOP: Agent Onboarding - Test Agent (test-agent)" in content
    
    # Verify Playbook file
    playbook_path = ace_service.cursor_rules_dir / "tester.mdc"
    assert playbook_path.exists()
    assert "# Test Agent Playbook (tester)" in playbook_path.read_text()
    
    # Verify Mail
    messages = ace_service.list_mail(agent_id)
    assert len(messages) == 1
    assert messages[0].subject == "ONBOARDING SOP"

def test_review_pr_creates_sop(ace_service):
    # Setup
    agent_id = "reviewer-agent"
    pr_id = "PR-999"
    ace_service.create_agent(id=agent_id, name="Reviewer", role="reviewer")
    
    # Execute
    review_path = ace_service.review_pr(pr_id, agent_id)
    
    # Verify
    assert review_path.exists()
    assert f"review_{pr_id}_{agent_id}.md" in review_path.name
    content = review_path.read_text()
    assert f"# SOP: PR Review - {pr_id}" in content
    assert f"- **Reviewer**: {agent_id}" in content
    
    # Verify Mail
    messages = ace_service.list_mail(agent_id)
    assert any(m.subject == f"PR REVIEW TASK: {pr_id}" for m in messages)

def test_build_context_with_agent(ace_service):
    # Setup
    agent_id = "context-agent"
    ace_service.create_agent(id=agent_id, name="Context Agent", role="context-role")
    playbook_path = ace_service.cursor_rules_dir / "context-role.mdc"
    playbook_path.write_text("### AGENT SPECIFIC STRATEGY\n<!-- [str-001] helpful=1 harmful=0 :: Test Strategy -->")
    
    # Execute
    context, resolved_id = ace_service.build_context(agent_id=agent_id, task_type=TaskType.IMPLEMENT)
    
    # Verify
    assert resolved_id == agent_id
    assert "### AGENT PLAYBOOK (context-role)" in context
    assert "### AGENT SPECIFIC STRATEGY" in context
    assert "### TASK FRAMING" in context
    assert "You are implementing new functionality" in context

def test_resolve_owner_longest_prefix(ace_service):
    ace_service.assign_ownership("src/auth", "auth-agent")
    ace_service.assign_ownership("src/auth/providers", "provider-agent")
    
    assert ace_service.resolve_owner("src/auth/login.py") == "auth-agent"
    assert ace_service.resolve_owner("src/auth/providers/google.py") == "provider-agent"
    assert ace_service.resolve_owner("src/other.py") is None
