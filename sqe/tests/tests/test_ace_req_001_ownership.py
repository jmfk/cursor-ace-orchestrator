import pytest
import time
import yaml
from pathlib import Path
from ace_lib.services.ace_service import ACEService
from ace_lib.models.schemas import AgentsConfig, OwnershipConfig
from typer.testing import CliRunner
from ace import app

# Initialize the Typer runner for CLI testing
runner = CliRunner()

@pytest.fixture
def setup_ace_env(tmp_path):
    """
    Sets up a temporary ACE environment with agents.yaml and ownership.yaml.
    """
    ace_dir = tmp_path / ".ace"
    ace_dir.mkdir()

    # 1. Define Agent Registry
    agents_data = {
        "version": "1",
        "agents": [
            {
                "id": "auth-expert-01",
                "name": "Aegis",
                "role": "auth",
                "email": "auth-expert-01@ace.local",
                "responsibilities": ["authentication", "authorization"],
                "memory_file": ".cursor/rules/auth.mdc",
                "status": "active"
            },
            {
                "id": "ui-specialist-02",
                "name": "Canvas",
                "role": "frontend",
                "email": "ui-specialist-02@ace.local",
                "responsibilities": ["react", "tailwind"],
                "memory_file": ".cursor/rules/ui.mdc",
                "status": "active"
            }
        ]
    }
    agents_file = ace_dir / "agents.yaml"
    with open(agents_file, "w") as f:
        yaml.dump(agents_data, f)

    # 2. Define Ownership Mapping
    # Testing longest-prefix: 'src' vs 'src/auth'
    ownership_data = {
        "version": "1",
        "modules": {
            "src": {"agent_id": "ui-specialist-02"},
            "src/auth": {"agent_id": "auth-expert-01"},
            "src/auth/protocols": {"agent_id": "auth-expert-01"}
        },
        "unowned": []
    }
    ownership_file = ace_dir / "ownership.yaml"
    with open(ownership_file, "w") as f:
        yaml.dump(ownership_data, f)

    return tmp_path

def test_agent_registry_integrity(setup_ace_env):
    """
    Verifies that .ace/agents.yaml correctly tracks required agent metadata.
    """
    service = ACEService(base_path=setup_ace_env)
    # Logic check: Load using Pydantic model defined in schemas.py
    agents_config = service.load_agents()
    
    assert isinstance(agents_config, AgentsConfig)
    assert len(agents_config.agents) == 2
    
    aegis = next(a for a in agents_config.agents if a.id == "auth-expert-01")
    assert aegis.name == "Aegis"
    assert aegis.role == "auth"
    assert "authentication" in aegis.responsibilities
    assert aegis.memory_file == ".cursor/rules/auth.mdc"

def test_ownership_longest_prefix_matching(setup_ace_env):
    """
    Verifies that ownership mapping uses longest-prefix matching.
    - src/ui/button.tsx -> ui-specialist-02 (matches 'src')
    - src/auth/login.py -> auth-expert-01 (matches 'src/auth', which is longer than 'src')
    """
    service = ACEService(base_path=setup_ace_env)
    
    # Case 1: Deep match
    owner_auth = service.get_owner_for_path("src/auth/login.py")
    assert owner_auth == "auth-expert-01"

    # Case 2: Shallow match
    owner_ui = service.get_owner_for_path("src/components/header.tsx")
    assert owner_ui == "ui-specialist-02"

    # Case 3: No match
    owner_none = service.get_owner_for_path("README.md")
    assert owner_none is None

def test_ace_who_performance_and_correctness(setup_ace_env):
    """
    Verifies 'ace who <path>' returns correct agent in < 100ms.
    """
    # Note: We need to mock the service inside the CLI app to use our temp path
    from ace import reset_service
    reset_service(setup_ace_env)

    start_time = time.time()
    # Execute CLI command
    result = runner.invoke(app, ["who", "src/auth/session.py"])
    end_time = time.time()

    duration_ms = (end_time - start_time) * 1000

    # Assert Success Criteria
    assert result.exit_code == 0
    assert "auth-expert-01" in result.stdout
    assert "Aegis" in result.stdout
    assert duration_ms < 100, f"CLI response too slow: {duration_ms:.2f}ms"

def test_ownership_config_loading(setup_ace_env):
    """
    Verifies that OwnershipConfig schema correctly parses the ownership.yaml file.
    """
    service = ACEService(base_path=setup_ace_env)
    config = service.load_ownership()
    
    assert isinstance(config, OwnershipConfig)
    assert "src/auth" in config.modules
    assert config.modules["src/auth"].agent_id == "auth-expert-01"
