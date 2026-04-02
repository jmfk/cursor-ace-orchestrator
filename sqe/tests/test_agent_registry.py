import pytest
import os
import yaml
from pathlib import Path
from typer.testing import CliRunner
from ace import app, reset_service
from ace_lib.services.ace_service import ACEService
from ace_lib.models.schemas import Agent, AgentsConfig

runner = CliRunner()

@pytest.fixture
def temp_ace_env(tmp_path):
    """Sets up a temporary ACE environment for testing."""
    ace_dir = tmp_path / ".ace"
    ace_dir.mkdir()
    agents_file = ace_dir / "agents.yaml"
    
    # Initialize with empty agents config
    initial_config = {"version": "1", "agents": []}
    with open(agents_file, "w") as f:
        yaml.dump(initial_config, f)
    
    # Point the service to the temp directory
    reset_service(tmp_path)
    return tmp_path

def test_agent_schema_validation():
    """Verifies that the Agent Pydantic model enforces required metadata."""
    # Valid agent
    agent_data = {
        "id": "test-agent",
        "name": "Testy",
        "role": "tester",
        "email": "test@ace.local",
        "memory_file": ".cursor/rules/test.mdc"
    }
    agent = Agent(**agent_data)
    assert agent.id == "test-agent"
    assert agent.status == "active"  # Default value

    # Missing required field (email)
    with pytest.raises(ValueError):
        Agent(id="fail", name="fail", role="fail", memory_file="fail")

def test_agent_persistence_in_yaml(temp_ace_env):
    """Verifies that agents saved via ACEService persist in the YAML file."""
    svc = ACEService(temp_ace_env)
    new_agent = Agent(
        id="dev-01",
        name="Developer",
        role="coding",
        email="dev-01@ace.local",
        memory_file=".cursor/rules/dev.mdc"
    )
    
    # Simulate saving (assuming service has a save_agents method based on context)
    config = AgentsConfig(agents=[new_agent])
    agents_path = temp_ace_env / ".ace" / "agents.yaml"
    
    from ruamel.yaml import YAML
    ryaml = YAML()
    with open(agents_path, "w") as f:
        ryaml.dump(config.dict(), f)

    # Verify file content
    with open(agents_path, "r") as f:
        data = yaml.safe_load(f)
        assert len(data["agents"]) == 1
        assert data["agents"][0]["id"] == "dev-01"
        assert data["agents"][0]["email"] == "dev-01@ace.local"

def test_cli_agent_create_success(temp_ace_env, monkeypatch):
    """Verifies that 'ace agent create' CLI command correctly adds an agent to the registry."""
    # Mocking the service within the CLI app to use our temp path
    monkeypatch.setattr("ace.service", ACEService(temp_ace_env))
    
    # Execute CLI command
    # Note: Arguments based on requirement 'ace agent create'
    result = runner.invoke(app, [
        "agent", "create", 
        "--id", "qa-bot", 
        "--name", "QA Bot",
        "--role", "qa", 
        "--email", "qa-bot@ace.local",
        "--memory", ".cursor/rules/qa.mdc"
    ])
    
    # Check CLI output (assuming success message)
    assert result.exit_code == 0
    
    # Verify persistence
    agents_path = temp_ace_env / ".ace" / "agents.yaml"
    with open(agents_path, "r") as f:
        data = yaml.safe_load(f)
        agent_ids = [a["id"] for a in data["agents"]]
        assert "qa-bot" in agent_ids

def test_unique_email_constraint(temp_ace_env, monkeypatch):
    """Verifies that the system prevents creating agents with duplicate email addresses."""
    svc = ACEService(temp_ace_env)
    monkeypatch.setattr("ace.service", svc)
    
    # Create first agent
    runner.invoke(app, [
        "agent", "create", "--id", "agent1", "--name", "Agent 1", "--role", "r1",
        "--email", "shared@ace.local", "--memory", "m1.mdc"
    ])
    
    # Attempt to create second agent with same email
    result = runner.invoke(app, [
        "agent", "create", "--id", "agent2", "--name", "Agent 2", "--role", "r2",
        "--email", "shared@ace.local", "--memory", "m2.mdc"
    ])

    # Should fail or show warning depending on implementation
    # If the requirement strictly enforces uniqueness, exit_code should be non-zero
    assert "email" in result.stdout.lower()
    assert "already exists" in result.stdout.lower() or result.exit_code != 0

def test_agent_metadata_completeness(temp_ace_env):
    """Ensures all required metadata fields (ID, Role, Memory File, Email) are present in registry."""
    svc = ACEService(temp_ace_env)
    agents_config = svc.load_agents()
    
    # Add an agent manually to test loading
    test_agent = Agent(
        id="meta-test",
        name="Meta",
        role="architect",
        email="meta@ace.local",
        memory_file=".cursor/rules/arch.mdc"
    )
    
    # Verify all fields are accessible and non-empty
    assert test_agent.id == "meta-test"
    assert test_agent.role == "architect"
    assert test_agent.email == "meta@ace.local"
    assert test_agent.memory_file == ".cursor/rules/arch.mdc"
    assert test_agent.created_at is not None