import pytest
from pathlib import Path
from ace_lib.services.ace_service import ACEService
from ace_lib.models.schemas import Config

@pytest.fixture
def temp_workspace(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return workspace

@pytest.fixture
def service(temp_workspace):
    return ACEService(base_path=temp_workspace)

def test_sso_authentication(service):
    # Test with SSO disabled (default)
    assert service.authenticate_sso("any-token") is True

    # Enable SSO
    config = service.load_config()
    config.sso_enabled = True
    config.sso_provider = "github"
    config.sso_client_id = "test-client-id"
    service.save_config(config)

    # Test with invalid token
    assert service.authenticate_sso("invalid-token") is False

    # Test with valid token (mocked)
    assert service.authenticate_sso("valid-sso-token") is True

def test_sso_login_url(service):
    # Test with SSO disabled
    assert service.get_sso_login_url() == ""

    # Enable GitHub SSO
    config = service.load_config()
    config.sso_enabled = True
    config.sso_provider = "github"
    config.sso_client_id = "gh-123"
    service.save_config(config)
    assert "github.com" in service.get_sso_login_url()
    assert "gh-123" in service.get_sso_login_url()

    # Enable Google SSO
    config.sso_provider = "google"
    config.sso_client_id = "goog-456"
    service.save_config(config)
    assert "accounts.google.com" in service.get_sso_login_url()
    assert "goog-456" in service.get_sso_login_url()
