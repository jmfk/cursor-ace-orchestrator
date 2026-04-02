import pytest
from pathlib import Path
from ace_lib.services.ace_service import ACEService
from ace_lib.models.schemas import TaskType, Agent

@pytest.fixture
def service(tmp_path):
    """Initialize ACEService in a temporary workspace."""
    return ACEService(base_path=tmp_path)

def test_rbac_path_restriction(service, monkeypatch):
    """Test RBAC path restriction in run_agent_task."""
    # Create agent with restricted paths
    agent_id = "restricted-agent"
    service.create_agent(
        id=agent_id,
        name="Restricted Agent",
        role="developer",
        responsibilities=["frontend"]
    )
    
    # Update agent with allowed_paths
    agents_config = service.load_agents()
    agent = next(a for a in agents_config.agents if a.id == agent_id)
    agent.allowed_paths = ["src/frontend"]
    service.save_agents(agents_config)
    service.clear_cache()

    # Mock build_context to avoid real logic
    monkeypatch.setattr(service, "build_context", lambda *args, **kwargs: ("context", agent_id))

    # Test allowed path
    # We don't actually want to run a command, so we'll mock subprocess.run
    import subprocess
    from unittest.mock import MagicMock
    
    mock_res = MagicMock()
    mock_res.returncode = 0
    mock_res.stdout = "Success"
    mock_res.stderr = ""
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: mock_res)

    success = service.run_agent_task(
        command="ls",
        path="src/frontend/components",
        agent_id=agent_id
    )
    assert success is True

    # Test forbidden path
    success = service.run_agent_task(
        command="ls",
        path="src/backend/api",
        agent_id=agent_id
    )
    assert success is False

def test_rbac_command_restriction(service, monkeypatch):
    """Test RBAC command restriction in run_agent_task."""
    agent_id = "no-delete-agent"
    service.create_agent(
        id=agent_id,
        name="No Delete Agent",
        role="developer"
    )
    
    agents_config = service.load_agents()
    agent = next(a for a in agents_config.agents if a.id == agent_id)
    agent.forbidden_commands = ["rm", "delete"]
    service.save_agents(agents_config)
    service.clear_cache()

    monkeypatch.setattr(service, "build_context", lambda *args, **kwargs: ("context", agent_id))

    # Test allowed command
    import subprocess
    from unittest.mock import MagicMock
    mock_res = MagicMock()
    mock_res.returncode = 0
    mock_res.stdout = "Success"
    mock_res.stderr = ""
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: mock_res)

    success = service.run_agent_task(
        command="ls -la",
        path="src",
        agent_id=agent_id
    )
    assert success is True

    # Test forbidden command
    success = service.run_agent_task(
        command="rm -rf .",
        path="src",
        agent_id=agent_id
    )
    assert success is False
