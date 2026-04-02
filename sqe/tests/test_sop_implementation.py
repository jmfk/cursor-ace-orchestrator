import pytest
import os
from pathlib import Path
from unittest.mock import MagicMock, patch
from ace_lib.services.ace_service import ACEService
from ace_lib.models.schemas import Agent, MailMessage

# --- Fixtures ---

@pytest.fixture
def temp_workspace(tmp_path):
    """Creates a temporary workspace for ACE metadata and files."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    # Create necessary directory structure expected by ACEService
    (workspace / ".ace").mkdir()
    (workspace / ".ace/mail").mkdir()
    (workspace / ".ace/sessions").mkdir()
    (workspace / "rules").mkdir(parents=True)
    return workspace

@pytest.fixture
def service(temp_workspace):
    """Initializes the ACEService with a mocked Anthropic client to avoid API calls."""
    with patch('anthropic.Anthropic'):
        svc = ACEService(base_path=temp_workspace)
        # Mocking internal methods that might trigger LLM calls during SOP generation
        # if the implementation uses them for 'reflection' or 'analysis'.
        return svc

# --- Test Cases ---

def test_onboarding_sop_generation_success(service, temp_workspace):
    """
    Requirement: The 'ace agent onboard' command generates a valid onboarding.md for new agents.
    Verifies:
    1. The onboarding file is created in the correct location.
    2. The content contains the specific SOP header and agent details.
    3. The agent's memory file (playbook) is initialized.
    4. A notification is sent to the agent's inbox.
    """
    agent_id = "dev-tester-01"
    agent_name = "Test Agent"
    
    # Setup: Create the agent in the registry
    service.create_agent(
        id=agent_id,
        name=agent_name,
        role="developer",
        responsibilities=["src/core", "src/utils"]
    )

    # Action: Trigger onboarding
    sop_file_path = service.onboard_agent(agent_id)

    # Assertions: File Integrity
    assert sop_file_path.exists(), "Onboarding SOP file should be created."
    content = sop_file_path.read_text()
    assert f"# SOP: Agent Onboarding - {agent_name} ({agent_id})" in content
    assert "- **Role**: developer" in content
    assert "src/core, src/utils" in content

    # Assertions: Playbook Initialization
    playbook_path = temp_workspace / "rules/developer.mdc"
    assert playbook_path.exists(), "Agent playbook (.mdc) should be initialized during onboarding."

    # Assertions: Notification
    messages = service.list_mail(agent_id)
    assert len(messages) > 0
    assert any("ONBOARDING" in msg.subject.upper() for msg in messages)


def test_pr_review_trigger_and_logging(service, temp_workspace):
    """
    Requirement: PR reviews are automatically triggered and logged when cross-module changes occur.
    Verifies:
    1. The service generates a PR Review SOP file.
    2. The SOP contains the correct PR ID and Reviewer ID.
    3. A mail notification is logged for the reviewer.
    """
    pr_id = "PR-101"
    reviewer_id = "qa-lead-01"

    # Action: Simulate a PR review trigger
    review_sop_path = service.review_pr(pr_id, reviewer_id)

    # Assertions
    assert review_sop_path.exists()
    content = review_sop_path.read_text()
    assert f"# SOP: PR Review - {pr_id}" in content
    assert f"- **Reviewer**: {reviewer_id}" in content
    
    # Verify logging via Mail System
    messages = service.list_mail(reviewer_id)
    assert len(messages) == 1
    assert pr_id in messages[0].subject


def test_cross_module_change_detection_logic(service, temp_workspace):
    """
    Requirement: PR reviews are triggered when cross-module changes occur.
    This test verifies the logic that identifies which agents need to be notified 
    based on file ownership when a PR touches multiple modules.
    """
    # Setup: Define ownership
    # Agent A owns 'src/auth'
    # Agent B owns 'src/database'
    service.create_agent(id="agent-a", name="A", role="auth", responsibilities=["src/auth"])
    service.create_agent(id="agent-b", name="B", role="db", responsibilities=["src/database"])
    
    # Manually set ownership in the mock/temp config if the service uses ownership.yaml
    # (Assuming service.assign_ownership exists based on WORKFLOW.md)
    service.assign_ownership("src/auth", "agent-a")
    service.assign_ownership("src/database", "agent-b")

    # Simulated PR touching both modules
    changed_files = ["src/auth/login.py", "src/database/schema.sql"]
    
    # Action: Identify reviewers for these files
    # This simulates the internal logic that would trigger 'review_pr' for each owner
    reviewers = service.identify_reviewers_for_files(changed_files)

    # Assertions
    assert "agent-a" in reviewers
    assert "agent-b" in reviewers
    assert len(reviewers) == 2, "Both module owners should be identified for cross-module changes."


def test_audit_sop_generation(service, temp_workspace):
    """
    Requirement: Formal instructions for audits.
    Verifies:
    1. Audit SOP generation for an existing agent.
    2. Content includes the Orchestrator as the auditor.
    """
    agent_id = "dev-1"
    service.create_agent(id=agent_id, name="Dev One", role="developer")

    # Action
    audit_file = service.audit_agent(agent_id)

    # Assertions
    assert audit_file.exists()
    content = audit_file.read_text()
    assert f"# SOP: Agent Audit - Dev One ({agent_id})" in content
    assert "- **Auditor**: Orchestrator" in content
    
    # Verify the agent is notified they are being audited
    messages = service.list_mail(agent_id)
    assert any("AUDIT" in msg.subject.upper() for msg in messages)


def test_sop_content_validity_dates(service, temp_workspace):
    """
    Verifies that generated SOPs contain ISO formatted timestamps as per implementation.
    """
    from datetime import datetime
    
    service.create_agent(id="test-id", name="Tester", role="tester")
    sop_path = service.onboard_agent("test-id")
    
    content = sop_path.read_text()
    # Search for ISO date pattern: YYYY-MM-DDTHH:MM:SS
    import re
    iso_date_pattern = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
    assert re.search(iso_date_pattern, content), "SOP should contain a valid ISO timestamp."
