import pytest
import yaml
from pathlib import Path
from typer.testing import CliRunner
from ace import app, reset_service
from ace_lib.services.ace_service import ACEService
from ace_lib.models.schemas import Agent, AgentsConfig

# Initialize the Typer CLI runner
runner = CliRunner()

@pytest.fixture
def temp_ace_env(tmp_path):
    """
    Sets up a temporary ACE environment with the required directory structure.
    """
    ace_dir = tmp_path / ".ace"
    ace_dir.mkdir()
    
    # Create initial empty agents.yaml
    agents_file = ace_dir / "agents.yaml"
    agents_file.write_text("version: '1'\nagents: []")
    
    # Create cursor rules directory for memory files
    cursor_rules = tmp_path / ".cursor" / "rules"
    cursor_rules.mkdir(parents=True)
    
    # Reset the global service in ace.py to use this temp path
    reset_service(tmp_path)
    
    return tmp_path

def test_agent_creation_persistence(temp_ace_env):
    """
    Verifies that an agent created via the service is correctly persisted to .ace/agents.yaml
    with all required metadata.
    """
    service = ACEService(temp_ace_env)
    
    agent_id = "test-agent-01"
    agent_data = {
        "id": agent_id,
        "name": "Test Agent",
        "role": "tester",
        "email": "test-agent-01@ace.local",
        "memory_file": ".cursor/rules/test.mdc"
    }
    
    # Create the agent
    service.create_agent(**agent_data)
    
    # Verify file existence
    yaml_path = temp_ace_env / ".ace" / "agents.yaml"
    assert yaml_path.exists()
    
    # Verify YAML content
    with open(yaml_path, 'r') as f:
        data = yaml.safe_load(f)
        
    agents = data.get("agents", [])
    assert len(agents) == 1
    assert agents[0]["id"] == agent_id
    assert agents[0]["email"] == "test-agent-01@ace.local"
    assert agents[0]["role"] == "tester"
    assert agents[0]["memory_file"] == ".cursor/rules/test.mdc"

def test_agent_metadata_includes_unique_email(temp_ace_env):
    """
    Verifies that the Agent model enforces the presence of an email address
    and that the registry can distinguish agents by email.
    """
    service = ACEService(temp_ace_env)
    
    # Create two different agents
    service.create_agent(id="a1", name="A1", role="r1", email="a1@ace.local", memory_file="m1.mdc")
    service.create_agent(id="a2", name="A2", role="r2", email="a2@ace.local", memory_file="m2.mdc")
    
    agents_config = service.load_agents()
    emails = [a.email for a in agents_config.agents]
    
    assert "a1@ace.local" in emails
    assert "a2@ace.local" in emails
    assert len(set(emails)) == 2  # Ensure uniqueness in the list

def test_cli_agent_create_command(temp_ace_env):
    """
    Verifies the 'ace agent create' CLI command correctly updates the registry.
    Note: This assumes the CLI implementation follows the requirement 'ace agent create'.
    """
    # Simulate CLI command: ace agent create test-cli-01 --role developer --email cli@ace.local --memory .cursor/rules/cli.mdc
    # Since the exact CLI arguments for 'create' aren't in the snippet, we use a standard implementation pattern
    result = runner.invoke(app, [
        "agent", "create", 
        "test-cli-01", 
        "--name", "CLI Agent",
        "--role", "developer", 
        "--email", "cli@ace.local", 
        "--memory", ".cursor/rules/cli.mdc"
    ])
    
    # Check if command succeeded (exit code 0)
    # If the command is not yet implemented in the provided snippet, this test will fail, 
    # which is correct for a TDD approach.
    assert result.exit_code == 0
    
    # Verify persistence
    service = ACEService(temp_ace_env)
    agents_config = service.load_agents()
    cli_agent = next((a for a in agents_config.agents if a.id == "test-cli-01"), None)
    
    assert cli_agent is not None
    assert cli_agent.email == "cli@ace.local"
    assert cli_agent.role == "developer"

def test_registry_schema_validation(temp_ace_env):
    """
    Ensures that the Agent model correctly validates required fields.
    """
    from pydantic import ValidationError
    
    # Missing email should raise ValidationError based on Agent(BaseModel) in schemas.py
    with pytest.raises(ValidationError):
        Agent(
            id="fail-agent",
            name="Fail",
            role="error",
            # email is missing
            memory_file="fail.mdc"
        )

def test_agent_registry_loading(temp_ace_env):
    """
    Verifies that the service can load existing agents from a pre-populated YAML file.
    """
    yaml_content = """
version: '1'
agents:
- id: existing-01
  name: Old Guard
  role: security
  email: guard@ace.local
  memory_file: .cursor/rules/security.mdc
  status: active
"""
    (temp_ace_env / ".ace" / "agents.yaml").write_text(yaml_content)
    
    service = ACEService(temp_ace_env)
    agents_config = service.load_agents()
    
    assert len(agents_config.agents) == 1
    assert agents_config.agents[0].id == "existing-01"
    assert agents_config.agents[0].email == "guard@ace.local"
