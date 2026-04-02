import pytest
from fastapi.testclient import TestClient
from ace_api.main import app
from ace_lib.services.ace_service import ACEService
import shutil
from pathlib import Path


@pytest.fixture
def client():
    # Setup a temporary .ace directory for tests
    test_ace_dir = Path(".ace_test")
    if test_ace_dir.exists():
        shutil.rmtree(test_ace_dir)
    test_ace_dir.mkdir()

    # Patch the service to use the test directory
    import ace_api.main

    old_service = ace_api.main.service
    ace_api.main.service = ACEService(base_path=test_ace_dir)

    with TestClient(app) as c:
        yield c

    # Cleanup
    try:
        shutil.rmtree(test_ace_dir)
    except FileNotFoundError:
        pass
    ace_api.main.service = old_service


def test_list_agents_empty(client):
    response = client.get("/agents")
    assert response.status_code == 200
    assert response.json() == []


def test_create_agent(client):
    response = client.post(
        "/agents",
        json={
            "id": "test-agent",
            "name": "Test Agent",
            "role": "tester",
            "email": "test@example.com",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "test-agent"
    assert data["name"] == "Test Agent"


def test_assign_ownership(client):
    response = client.post(
        "/ownership", json={"path": "src/test", "agent_id": "test-agent"}
    )
    assert response.status_code == 200

    response = client.get("/ownership")
    assert response.status_code == 200
    data = response.json()
    assert "src/test" in data["modules"]
    assert data["modules"]["src/test"]["agent_id"] == "test-agent"


def test_get_context(client):
    # Create agent first
    client.post(
        "/agents",
        json={"id": "test-agent", "name": "Test Agent", "role": "tester"},
    )
    client.post("/ownership", json={"path": "src/test", "agent_id": "test-agent"})

    response = client.get("/context", params={"path": "src/test"})
    assert response.status_code == 200
    data = response.json()
    assert "context" in data
    assert data["agent_id"] == "test-agent"


def test_onboard_agent(client):
    # Create agent first
    client.post(
        "/agents",
        json={"id": "test-agent", "name": "Test Agent", "role": "tester"},
    )
    response = client.post("/agents/test-agent/onboard")
    assert response.status_code == 200
    assert "onboarding_file" in response.json()


def test_audit_agent(client):
    # Create agent first
    client.post(
        "/agents",
        json={"id": "test-agent", "name": "Test Agent", "role": "tester"},
    )
    response = client.post("/agents/test-agent/audit")
    assert response.status_code == 200
    assert "audit_file" in response.json()


def test_review_pr(client):
    response = client.post("/pr/PR-1/review", json={"agent_id": "test-agent"})
    assert response.status_code == 200
    assert "review_file" in response.json()


def test_ui_mockup(client):
    response = client.post(
        "/ui/mockup", json={"description": "Login page", "agent_id": "test-agent"}
    )
    assert response.status_code == 200
    assert "url" in response.json()


def test_debate(client, monkeypatch):
    # Mock debate to avoid LLM call
    import ace_api.main

    monkeypatch.setattr(
        ace_api.main.service, "debate", lambda p, a, t=3: "Consensus reached"
    )

    response = client.post(
        "/debate", json={"proposal": "Use FastAPI", "agent_ids": ["agent-1", "agent-2"]}
    )
    assert response.status_code == 200
    assert response.json()["consensus"] == "Consensus reached"

