import pytest
import os
import re
from pathlib import Path
import yaml

# Constants for testing
AGENTS_FILENAME = "AGENTS.md"
AGENTS_YAML_PATH = ".ace/agents.yaml"

@pytest.fixture
def mock_project_root(tmp_path):
    """
    Sets up a mock project structure with AGENTS.md and .ace/agents.yaml
    based on the provided requirement context.
    """
    # Create .ace directory
    ace_dir = tmp_path / ".ace"
    ace_dir.mkdir()

    # Create agents.yaml
    agents_data = {
        "version": "1",
        "agents": [
            {
                "id": "auth-expert-01",
                "name": "Aegis",
                "role": "auth",
                "email": "auth-expert-01@ace.local",
                "responsibilities": ["Authentication flows", "JWT Management"],
                "memory_file": ".cursor/rules/auth.mdc",
                "status": "active"
            }
        ]
    }
    with open(ace_dir / "agents.yaml", "w") as f:
        yaml.dump(agents_data, f)

    # Create AGENTS.md with required sections
    agents_md_content = """# ACE Agents Registry

## Active Agents
| Agent ID | Name | Role | Responsibilities | Memory |
| --- | --- | --- | --- | --- |
| auth-expert-01 | Aegis | auth | Authentication flows, JWT Management | .cursor/rules/auth.mdc |

## Recent Architectural Decisions
- [ADR-001] Use FastAPI for the orchestration layer.
- [ADR-002] Implement RALPH cycle for agent loops.

## Write-back Protocol
All agents must follow this protocol after completing a task:
1. Reflect on the outcome (Success/Failure).
2. Extract new strategies [str-XXX] or pitfalls [mis-XXX].
3. Update the respective .mdc file in .cursor/rules/.
4. Log the session in .ace/sessions/.
"""
    with open(tmp_path / AGENTS_FILENAME, "w") as f:
        f.write(agents_md_content)

    return tmp_path

def test_agents_md_exists(mock_project_root):
    """Verifies that AGENTS.md exists at the root of the project."""
    agents_md = mock_project_root / AGENTS_FILENAME
    assert agents_md.exists(), "AGENTS.md should exist at the project root."

def test_agents_md_contains_agent_table(mock_project_root):
    """
    Verifies that AGENTS.md contains a table of agent roles and responsibilities.
    Matches the content against the source of truth (agents.yaml).
    """
    agents_md_path = mock_project_root / AGENTS_FILENAME
    agents_yaml_path = mock_project_root / AGENTS_YAML_PATH

    with open(agents_md_path, "r") as f:
        content = f.read()

    with open(agents_yaml_path, "r") as f:
        registry = yaml.safe_load(f)

    # Check for table headers
    assert "| Agent ID | Name | Role | Responsibilities |" in content

    # Verify each agent from YAML is represented in the MD table
    for agent in registry['agents']:
        assert agent['id'] in content
        assert agent['name'] in content
        assert agent['role'] in content
        for resp in agent['responsibilities']:
            assert resp in content

def test_agents_md_contains_active_adrs(mock_project_root):
    """
    Verifies that AGENTS.md includes a section for Recent Architectural Decisions (ADRs).
    """
    agents_md_path = mock_project_root / AGENTS_FILENAME
    with open(agents_md_path, "r") as f:
        content = f.read()

    # Check for ADR section header
    assert "## Recent Architectural Decisions" in content
    
    # Check for at least one ADR entry (pattern matching ADR-XXX)
    assert re.search(r"\[ADR-\d+\]", content), "AGENTS.md should list active ADRs."

def test_agents_md_contains_write_back_protocol(mock_project_root):
    """
    Verifies that AGENTS.md includes the standardized 'Write-back Protocol' instruction.
    """
    agents_md_path = mock_project_root / AGENTS_FILENAME
    with open(agents_md_path, "r") as f:
        content = f.read()

    # Check for the specific section header
    assert "## Write-back Protocol" in content
    
    # Verify key components of the protocol are mentioned
    assert "Reflect" in content
    assert ".mdc" in content
    assert "Update" in content

def test_agents_md_is_cross_tool_accessible(mock_project_root):
    """
    Verifies the file is in a standard Markdown format at the root, 
    ensuring accessibility for various AI tools (Cursor, Claude, etc.).
    """
    agents_md_path = mock_project_root / AGENTS_FILENAME
    
    # Check file extension and location
    assert agents_md_path.suffix == ".md"
    assert agents_md_path.parent == mock_project_root

    # Basic Markdown structure check (starts with a H1 header)
    with open(agents_md_path, "r") as f:
        first_line = f.readline()
        assert first_line.startswith("# "), "AGENTS.md should start with a Markdown H1 header."
