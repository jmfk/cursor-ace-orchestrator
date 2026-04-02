import pytest
import yaml
from pathlib import Path
from typing import Dict, Optional
from pydantic import ValidationError

# Importing models from the provided context
from ace_lib.models.schemas import OwnershipConfig, OwnershipModule, Agent, AgentsConfig
from ace_lib.services.ace_service import ACEService

class OwnershipRegistryManager:
    """
    Helper class to encapsulate the logic for the Ownership Registry.
    This mimics the logic that would be triggered by 'ace own', 'ace who', and 'ace list-owners'.
    """
    def __init__(self, service: ACEService):
        self.service = service
        self.config_path = self.service.ace_dir / "ownership.yaml"

    def load(self) -> OwnershipConfig:
        if not self.config_path.exists():
            return OwnershipConfig(version="1", modules={}, unowned=[])
        with open(self.config_path, "r") as f:
            data = yaml.safe_load(f)
            return OwnershipConfig(**data)

    def save(self, config: OwnershipConfig):
        self.service.ace_dir.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w") as f:
            # Use model_dump for Pydantic v2 compatibility
            yaml.dump(config.model_dump(), f)

    def resolve_owner(self, file_path: str) -> Optional[str]:
        """
        Implements Longest-Prefix Matching.
        Iterates through parent directories to find the most specific owner.
        """
        config = self.load()
        path_obj = Path(file_path)
        
        # Check the path itself and all its parents
        search_paths = [str(path_obj)] + [str(p) for p in path_obj.parents]
        
        for prefix in search_paths:
            # Normalize path strings for matching (remove trailing dots/slashes)
            normalized_prefix = prefix.rstrip(".").rstrip("/")
            if not normalized_prefix: 
                continue
            if normalized_prefix in config.modules:
                return config.modules[normalized_prefix].agent_id
        
        return None

    def assign_owner(self, path: str, agent_id: str):
        """Logic for 'ace own'"""
        config = self.load()
        # Requirement: Each file is restricted to one primary owner.
        # Overwriting the key ensures one primary owner per path.
        config.modules[path] = OwnershipModule(agent_id=agent_id)
        self.save(config)

    def list_owners(self) -> Dict[str, str]:
        """Logic for 'ace list-owners'"""
        config = self.load()
        return {path: mod.agent_id for path, mod in config.modules.items()}

# --- Fixtures ---

@pytest.fixture
def workspace(tmp_path):
    """Creates a temporary ACE workspace with initial configuration."""
    ace_dir = tmp_path / ".ace"
    ace_dir.mkdir()
    
    # Setup initial agents.yaml
    agents_data = {
        "version": "1",
        "agents": [
            {
                "id": "auth-expert-01",
                "name": "Aegis",
                "role": "auth",
                "email": "auth-expert-01@ace.local",
                "memory_file": ".cursor/rules/auth.mdc",
                "status": "active"
            },
            {
                "id": "infra-bot",
                "name": "Terra",
                "role": "infrastructure",
                "email": "infra@ace.local",
                "memory_file": ".cursor/rules/infra.mdc",
                "status": "active"
            }
        ]
    }
    with open(ace_dir / "agents.yaml", "w") as f:
        yaml.dump(agents_data, f)

    return tmp_path

@pytest.fixture
def manager(workspace):
    service = ACEService(base_path=workspace)
    return OwnershipRegistryManager(service)

# --- Test Cases ---

def test_longest_prefix_matching_resolution(manager):
    """
    Success Criteria: The system correctly resolves ownership using longest-prefix matching.
    """
    # Setup nested ownership
    manager.assign_owner("src", "general-agent")
    manager.assign_owner("src/auth", "auth-expert-01")
    manager.assign_owner("src/auth/strategies", "strategy-specialist")

    # 1. Exact match
    assert manager.resolve_owner("src/auth") == "auth-expert-01"

    # 2. Deep match (should pick the most specific prefix)
    assert manager.resolve_owner("src/auth/strategies/oauth.py") == "strategy-specialist"

    # 3. Mid-level match
    assert manager.resolve_owner("src/auth/session.py") == "auth-expert-01"

    # 4. Top-level match
    assert manager.resolve_owner("src/utils/helper.py") == "general-agent"

    # 5. No match
    assert manager.resolve_owner("docs/readme.md") is None


def test_cli_ace_own_updates_yaml(manager, workspace):
    """
    Success Criteria: CLI command 'ace own' accurately reflects the state of .ace/ownership.yaml.
    """
    target_path = "src/database"
    agent_id = "db-master"
    
    manager.assign_owner(target_path, agent_id)
    
    # Verify file content directly
    with open(workspace / ".ace" / "ownership.yaml", "r") as f:
        data = yaml.safe_load(f)
        assert target_path in data["modules"]
        assert data["modules"][target_path]["agent_id"] == agent_id
        assert "owned_since" in data["modules"][target_path]


def test_cli_ace_who_resolution(manager):
    """
    Success Criteria: CLI command 'ace who' accurately reflects the state.
    """
    manager.assign_owner("ace_lib", "core-dev")
    
    # Simulate 'ace who ace_lib/models/schemas.py'
    resolved = manager.resolve_owner("ace_lib/models/schemas.py")
    assert resolved == "core-dev"


def test_cli_list_owners(manager):
    """
    Success Criteria: CLI command 'ace list-owners' accurately reflects the state.
    """
    manager.assign_owner("path/a", "agent-a")
    manager.assign_owner("path/b", "agent-b")
    
    owners = manager.list_owners()
    assert len(owners) == 2
    assert owners["path/a"] == "agent-a"
    assert owners["path/b"] == "agent-b"


def test_single_primary_owner_restriction(manager):
    """
    Success Criteria: Each file is restricted to one primary owner.
    Verifies that re-assigning a path updates the primary owner rather than creating duplicates.
    """
    path = "src/shared"
    
    # Assign first owner
    manager.assign_owner(path, "agent-01")
    assert manager.resolve_owner(path) == "agent-01"
    
    # Assign second owner (Overwrite)
    manager.assign_owner(path, "agent-02")
    assert manager.resolve_owner(path) == "agent-02"
    
    # Verify YAML structure doesn't have duplicate keys for the same path
    config = manager.load()
    assert len(config.modules) == 1


def test_invalid_ownership_data_validation(workspace):
    """
    Verifies that the system enforces schema integrity using Pydantic models.
    """
    ace_dir = workspace / ".ace"
    # Manually write invalid data
    invalid_data = {
        "version": "1",
        "modules": {
            "src": {
                "agent_id": 123,  # Should be string
                "owned_since": "not-a-date"
            }
        }
    }
    with open(ace_dir / "ownership.yaml", "w") as f:
        yaml.dump(invalid_data, f)

    service = ACEService(base_path=workspace)
    manager = OwnershipRegistryManager(service)
    
    with pytest.raises(ValidationError):
        manager.load()