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


def test_onboarding_sop_full_flow(service, temp_workspace):
    """Test the full onboarding flow including file creation and mail notification."""
    agent = service.create_agent(
        id="dev-1",
        name="Developer One",
        role="developer",
        responsibilities=["src/core"],
    )
    sop_file = service.onboard_agent("dev-1")

    assert sop_file.exists()
    assert "SOP: Agent Onboarding - Developer One (dev-1)" in sop_file.read_text()

    # Check if memory file was created with template
    memory_path = temp_workspace / agent.memory_file
    assert memory_path.exists()
    assert "# Developer One Playbook (developer)" in memory_path.read_text()

    # Check if notification mail was sent
    messages = service.list_mail("dev-1")
    assert len(messages) == 1
    assert messages[0].subject == "ONBOARDING SOP"


def test_pr_review_sop_full_flow(service, temp_workspace):
    """Test the PR review SOP generation and notification."""
    review_file = service.review_pr("PR-42", "reviewer-1")
    assert review_file.exists()
    assert "SOP: PR Review - PR-42" in review_file.read_text()

    # Check if notification mail was sent
    messages = service.list_mail("reviewer-1")
    assert len(messages) == 1
    assert "PR REVIEW TASK: PR-42" in messages[0].subject


def test_audit_sop_full_flow(service, temp_workspace):
    """Test the agent audit SOP generation and notification."""
    service.create_agent(id="dev-1", name="Developer One", role="developer")
    audit_file = service.audit_agent("dev-1")
    assert audit_file.exists()
    assert "SOP: Agent Audit - Developer One (dev-1)" in audit_file.read_text()

    # Check if notification mail was sent
    messages = service.list_mail("dev-1")
    assert len(messages) == 1
    assert "AGENT AUDIT INITIATED" in messages[0].subject


def test_security_audit_sop(service, temp_workspace):
    """Test the security audit SOP generation."""
    service.create_agent(id="dev-1", name="Developer One", role="developer")
    sec_audit_file = service.security_audit("dev-1")
    assert sec_audit_file.exists()
    assert "SOP: Security Audit - Developer One (dev-1)" in sec_audit_file.read_text()
