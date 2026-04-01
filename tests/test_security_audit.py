import pytest
from ace_lib.services.ace_service import ACEService
from ace_lib.agents.security_audit import SecurityAuditService


@pytest.fixture
def temp_workspace(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return workspace


@pytest.fixture
def service(temp_workspace):
    return ACEService(base_path=temp_workspace)


def test_automated_security_audit_secrets(service, temp_workspace):
    """Test automated security audit for secrets."""
    service.create_agent(id="dev-1", name="Dev 1", role="developer")
    service.assign_ownership("src", "dev-1")

    # Create a file with a potential secret
    src_dir = temp_workspace / "src"
    src_dir.mkdir()
    secret_file = src_dir / "config.py"
    secret_file.write_text("API_KEY = 'abcdef1234567890'", encoding="utf-8")

    sec_service = SecurityAuditService(service)
    results = sec_service.run_automated_audit("dev-1")

    assert results["summary"]["failed"] == 1
    assert any(
        c["name"] == "Secret Scanning" and c["status"] == "failed"
        for c in results["checks"]
    )

    # Check if mail was sent
    messages = service.list_mail("dev-1")
    assert len(messages) == 1
    assert "SECURITY ALERT" in messages[0].subject


def test_automated_security_audit_clean(service, temp_workspace):
    """Test automated security audit with no issues."""
    service.create_agent(id="dev-1", name="Dev 1", role="developer")
    service.assign_ownership("src", "dev-1")

    src_dir = temp_workspace / "src"
    src_dir.mkdir()
    clean_file = src_dir / "main.py"
    clean_file.write_text("print('Hello')", encoding="utf-8")

    sec_service = SecurityAuditService(service)
    results = sec_service.run_automated_audit("dev-1")

    assert results["summary"]["failed"] == 0
    assert results["summary"]["passed"] >= 1

    # Check no mail sent
    messages = service.list_mail("dev-1")
    assert len(messages) == 0
