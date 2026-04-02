import pytest
import os
from pathlib import Path
from typer.testing import CliRunner
from ruamel.yaml import YAML

# Import the CLI app and service control from the provided context
from ace import app, reset_service
from ace_lib.models.schemas import AgentsConfig

yaml = YAML()
yaml.preserve_quotes = True

@pytest.fixture
def runner():
    """Provides a Typer CliRunner for testing CLI commands."""
    return CliRunner()

@pytest.fixture
def temp_workspace(tmp_path):
    """
    Sets up a temporary directory structure mimicking an ACE project.
    Initializes .ace/agents.yaml and redirects the ACEService to this path.
    """
    ace_dir = tmp_path / ".ace"
    ace_dir.mkdir()
    
    # Initialize agents.yaml with version header
    agents_file = ace_dir / "agents.yaml"
    agents_file.write_text("version: '1'\nagents: []")
    
    # Reset the global service instance in ace.py to use the temp directory
    reset_service(tmp_path)
    
    return tmp_path

def test_ace_agent_create_manual(runner, temp_workspace):
    """
    Verifies that 'ace agent create' successfully adds a new agent entry 
    to the agents.yaml file with the correct metadata.
    """
    agent_id = "test-agent-001"
    agent_name = "TestBot"
    agent_role = "qa-specialist"
    agent_email = "testbot@ace.local"
    memory_file = ".cursor/rules/qa.mdc"

    # Execute the CLI command
    # Note: Using arguments as defined by typical Typer implementations of this requirement
        result = runner.invoke(app, [
            "agent", "create",
            agent_id,
            "--name", agent_name,
            "--role", agent_role,
            "--email", agent_email,
            "--memory", memory_file
        ])

    # Check CLI output status
    assert result.exit_code == 0, f"Command failed with: {result.stdout}"
    assert f"Agent {agent_id} created" in result.stdout

    # Verify file system persistence
    agents_yaml_path = temp_workspace / ".ace" / "agents.yaml"
    assert agents_yaml_path.exists()
    
    with open(agents_yaml_path, 'r') as f:
        data = yaml.load(f)
        
    # Validate structure using Pydantic model implicitly through the YAML content
    agents_config = AgentsConfig(**data)
    created_agent = next((a for a in agents_config.agents if a.id == agent_id), None)
    
    assert created_agent is not None
    assert created_agent.name == agent_name
    assert created_agent.role == agent_role
    assert created_agent.email == agent_email
    assert created_agent.memory_file == memory_file
    assert created_agent.status == "active"

def test_ace_agent_list_display(runner, temp_workspace):
    """
    Verifies that 'ace agent list' correctly displays all active agents 
    and their metadata in the console output.
    """
    # 1. Pre-populate agents.yaml
    agents_yaml_path = temp_workspace / ".ace" / "agents.yaml"
    agent_data = {
        "version": "1",
        "agents": [
            {
                "id": "dev-bot",
                "name": "Builder",
                "role": "developer",
                "email": "dev@ace.local",
                "created_by": "user",
                "created_at": "2026-01-01",
                "responsibilities": [],
                "memory_file": ".cursor/rules/dev.mdc",
                "status": "active"
            },
            {
                "id": "sec-bot",
                "name": "Guardian",
                "role": "security",
                "email": "sec@ace.local",
                "created_by": "autonomous",
                "created_at": "2026-01-02",
                "responsibilities": ["scan"],
                "memory_file": ".cursor/rules/sec.mdc",
                "status": "active"
            }
        ]
    }
    with open(agents_yaml_path, 'w') as f:
        yaml.dump(agent_data, f)

    # 2. Execute CLI command
    result = runner.invoke(app, ["agent", "list"])

    # 3. Assertions
    assert result.exit_code == 0
    # Verify both agents are mentioned in the output
    assert "dev-bot" in result.stdout
    assert "Builder" in result.stdout
    assert "sec-bot" in result.stdout
    assert "Guardian" in result.stdout
    assert "security" in result.stdout

def test_autonomous_agent_creation_flow(runner, temp_workspace):
    """
    Verifies the requirement for 'autonomous' creation.
    Usually triggered via expansion thresholds. We test if the CLI 
    correctly reports an agent created through the service's autonomous logic.
    """
    from ace_lib.services.ace_service import ACEService
    svc = ACEService(temp_workspace)
    
    # Trigger autonomous creation through the service logic
    # (Using the service directly to simulate the autonomous backend process)
    svc.create_agent(
        id="auto-agent-01",
        name="AutoBot",
        role="optimizer",
        email="auto@ace.local",
        responsibilities=["performance"]
    )

    # Verify that the CLI 'list' command picks up the autonomously created agent
    result = runner.invoke(app, ["agent", "list"])
    
    assert "auto-agent-01" in result.stdout
    assert "optimizer" in result.stdout
