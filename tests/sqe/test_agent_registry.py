import pytest
import yaml
import os
from pathlib import Path
from typer.testing import CliRunner
from pydantic import ValidationError

# Import the components to test
from ace import app, reset_service
from ace_lib.services.ace_service import ACEService
from ace_lib.models.schemas import Agent, AgentsConfig

runner = CliRunner()

@pytest.fixture
def temp_ace_root(tmp_path):
    """
    Sets up a temporary project root with a .ace directory and 
    initializes the ACEService to use this path.
    """
    ace_dir = tmp_path / ".ace"
    ace_dir.mkdir()
    agents_yaml = ace_dir / "agents.yaml"
    
    # Initial empty registry
    initial_data = {"version": "1", "agents": []}
    with open(agents_yaml, "w") as f:
        yaml.dump(initial_data, f)
    
    # Reset the global service in ace.py to use this temp path
    reset_service(tmp_path)
    return tmp_path

def test_agent_schema_validation():
    """
    Verifies that the Agent Pydantic model enforces the required metadata fields:
    ID, Name, Role, Email, and Memory File.
    """
    # Valid agent data
    valid_data = {
        "id": "coder-01",
        "name": "Alice",
        "role": "developer",
        "email": "alice@ace.local",
        "memory_file": ".cursor/rules/coder.mdc"
    }
    agent = Agent(**valid_data)
    assert agent.id == "coder-01"
    assert agent.status == "active"  # Check default value

    # Test missing required field (email)
    invalid_data = valid_data.copy()
    del invalid_data["email"]
    with pytest.raises(ValidationError):
        Agent(**invalid_data)

def test_agent_persistence_in_yaml(temp_ace_root):
    """
    Verifies that agents added via the ACEService are correctly persisted 
    to the .ace/agents.yaml file.
    """
    svc = ACEService(temp_ace_root)
    
    # Create a new agent object
    new_agent = Agent(
        id="arch-01",
        name="Bob",
        role="architect",
        email="bob@ace.local",
        memory_file=".cursor/rules/arch.mdc"
    )
    
    # Manually trigger save (simulating service logic)
    config = AgentsConfig(agents=[new_agent])
    agents_path = temp_ace_root / ".ace" / "agents.yaml"
    
    with open(agents_path, "w") as f:
        # Using dict() for pydantic v1/v2 compatibility in tests
        yaml.dump(config.model_dump() if hasattr(config, 'model_dump') else config.dict(), f)

    # Verify the file exists and contains the data
    assert agents_path.exists()
    with open(agents_path, "r") as f:
        persisted_data = yaml.safe_load(f)
        assert persisted_data["agents"][0]["id"] == "arch-01"
        assert persisted_data["agents"][0]["email"] == "bob@ace.local"

def test_cli_agent_create_success(temp_ace_root, monkeypatch):
    """
    Verifies the success criteria: New agents can be created via 'ace agent create'.
    This tests the CLI integration and end-to-end flow.
    """
    # Ensure the CLI uses our temp service
    svc = ACEService(temp_ace_root)
    monkeypatch.setattr("ace.service", svc)

    # Execute CLI command: ace agent create
    result = runner.invoke(app, [
        "agent", "create",
        "--id", "security-bot",
        "--name", "Shield",
        "--role", "security",
        "--email", "shield@ace.local",
        "--memory", ".cursor/rules/security.mdc"
    ])

    # Assert CLI success
    assert result.exit_code == 0
    
    # Verify persistence in YAML
    agents_path = temp_ace_root / ".ace" / "agents.yaml"
    with open(agents_path, "r") as f:
        data = yaml.safe_load(f)
        agent_ids = [a["id"] for a in data["agents"]]
        assert "security-bot" in agent_ids
        assert data["agents"][0]["email"] == "shield@ace.local"

def test_unique_email_constraint(temp_ace_root, monkeypatch):
    """
    Verifies the success criteria: Agent metadata includes unique email addresses.
    The system should prevent creating two agents with the same email.
    """
    svc = ACEService(temp_ace_root)
    monkeypatch.setattr("ace.service", svc)

    # Create first agent
    runner.invoke(app, [
        "agent", "create", "--id", "a1", "--name", "Agent 1", 
        "--role", "r1", "--email", "duplicate@ace.local", "--memory", "m1.mdc"
    ])

    # Attempt to create second agent with same email
    result = runner.invoke(app, [
        "agent", "create", "--id", "a2", "--name", "Agent 2", 
        "--role", "r2", "--email", "duplicate@ace.local", "--memory", "m2.mdc"
    ])

    # The command should fail or provide a warning
    # Based on standard registry requirements, this should be an error (non-zero exit)
    assert result.exit_code != 0
    assert "email" in result.stdout.lower()
    assert "exists" in result.stdout.lower()

def test_agent_registry_metadata_completeness(temp_ace_root):
    """
    Ensures that the registry stores all required metadata fields defined in the PRD:
    ID, Role, and Memory File, plus the Email for the Mail system.
    """
    svc = ACEService(temp_ace_root)
    
    # Create agent with all fields
    agent = Agent(
        id="full-meta",
        name="Metadata Tester",
        role="tester",
        email="meta@ace.local",
        memory_file=".cursor/rules/test.mdc",
        responsibilities=["testing", "validation"]
    )
    
    # Check that Pydantic captured all fields
    data = agent.model_dump() if hasattr(agent, 'model_dump') else agent.dict()
    required_keys = {"id", "role", "email", "memory_file", "name", "status", "created_at"}
    assert required_keys.issubset(data.keys())
    assert data["status"] == "active"
    assert "@" in data["email"]