import pytest
import os
from pathlib import Path
from unittest.mock import MagicMock, patch
from ace_lib.services.ace_service import ACEService
from ace_lib.models.schemas import Agent, MailMessage

@pytest.fixture
def temp_workspace(tmp_path):
    """Creates a temporary workspace for ACE metadata and files."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    # Create necessary directory structure
    (workspace / ".ace").mkdir()
    (workspace / ".ace/mail").mkdir()
    (workspace / ".ace/sessions").mkdir()
    (workspace / ".cursor/rules").mkdir(parents=True)
    return workspace

@pytest.fixture
def service(temp_workspace):
    """Initializes the ACEService with the temporary workspace."""
    return ACEService(base_path=temp_workspace)

@pytest.fixture
def setup_agents(service):
    """Helper to setup multiple agents for cross-module testing."""
    agent_a = service.create_agent(
        id="auth-agent",
        name="Aegis",
        role="auth-expert",
        responsibilities=["src/auth"],
        memory_file=".cursor/rules/auth.mdc"
    )
    agent_b = service.create_agent(
        id="db-agent",
        name="Atlas",
        role="db-expert",
        responsibilities=["src/database"],
        memory_file=".cursor/rules/db.mdc"
    )
    return agent_a, agent_b

def test_onboarding_sop_generation(service, temp_workspace):
    """
    Success Criteria: The 'ace agent onboard' command generates a valid onboarding.md.
    Verifies that onboarding an agent creates the SOP file and sends a notification mail.
    """
    agent_id = "new-dev"
    service.create_agent(
        id=agent_id,
        name="New Developer",
        role="developer",
        responsibilities=["src/ui"],
        memory_file=".cursor/rules/ui.mdc"
    )

    # Trigger onboarding
    sop_path = service.onboard_agent(agent_id)

    # 1. Verify file existence and naming convention
    assert sop_path.exists()
    assert "onboarding" in sop_path.name.lower()

    # 2. Verify content structure (SOP Header and Sections)
    content = sop_path.read_text()
    assert f"SOP: Agent Onboarding - New Developer ({agent_id})" in content
    assert "## 1. Context Acquisition" in content
    assert "## 2. Role-Specific Setup" in content
    assert "- **Role**: developer" in content

    # 3. Verify notification mail was sent to the agent
    messages = service.list_mail(agent_id)
    assert len(messages) > 0
    assert any("ONBOARDING" in m.subject for m in messages)

def test_pr_review_sop_generation(service, temp_workspace):
    """
    Verifies that a PR review SOP is correctly generated with required checklists.
    """
    reviewer_id = "reviewer-1"
    pr_id = "PR-101"
    
    # Trigger PR review SOP generation
    review_sop_path = service.review_pr(pr_id, reviewer_id)

    assert review_sop_path.exists()
    content = review_sop_path.read_text()
    
    assert f"SOP: PR Review - {pr_id}" in content
    assert "## 1. Strategy Alignment" in content
    assert "## 3. Security Check" in content
    assert "[PENDING/APPROVED/REQUEST_CHANGES]" in content

def test_cross_module_pr_triggers_automatic_reviews(service, temp_workspace, setup_agents):
    """
    Success Criteria: PR reviews are automatically triggered and logged when cross-module changes occur.
    Simulates a PR touching multiple modules and verifies that both responsible agents receive review tasks.
    """
    agent_auth, agent_db = setup_agents
    
    # Simulate a PR that modifies files in both 'src/auth' and 'src/database'
    changed_files = ["src/auth/login.ts", "src/database/schema.sql"]
    pr_id = "PR-CROSS-MOD"

    # This method should internally identify owners and trigger SOPs/Mails
    # In a real implementation, this would be called by the 'ace' CLI or a git hook
    service.process_incoming_pr(pr_id=pr_id, files=changed_files)

    # 1. Check if Auth Agent received a review request
    auth_mail = service.list_mail(agent_auth.id)
    assert any(pr_id in m.subject and "REVIEW" in m.subject for m in auth_mail)

    # 2. Check if DB Agent received a review request
    db_mail = service.list_mail(agent_db.id)
    assert any(pr_id in m.subject and "REVIEW" in m.subject for m in db_mail)

    # 3. Verify that SOP files were logged in the sessions/PR directory
    pr_session_dir = temp_workspace / ".ace" / "sessions" / pr_id
    assert pr_session_dir.exists()
    sop_files = list(pr_session_dir.glob("*.md"))
    assert len(sop_files) >= 2 # One for each reviewer

def test_audit_sop_flow(service, temp_workspace):
    """
    Verifies the Agent Audit SOP generation and notification flow.
    """
    agent_id = "audit-target"
    service.create_agent(id=agent_id, name="Target Agent", role="worker")
    
    audit_sop_path = service.audit_agent(agent_id)
    
    assert audit_sop_path.exists()
    content = audit_sop_path.read_text()
    assert "SOP: Agent Audit" in content
    assert "## 1. Playbook Quality" in content
    
    # Verify mail notification
    messages = service.list_mail(agent_id)
    assert any("AUDIT" in m.subject for m in messages)

def test_sop_content_integrity_dates(service, temp_workspace):
    """
    Ensures that generated SOPs contain ISO formatted timestamps for audit trails.
    """
    sop_path = service.onboard_agent("test-agent")
    content = sop_path.read_text()
    
    # Simple regex check for ISO date format (YYYY-MM-DDTHH:MM:SS)
    import re
    iso_date_pattern = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
    assert re.search(iso_date_pattern, content) is not None