import pytest
import os
import re
from pathlib import Path

# Configuration: The path to the AGENTS.md file relative to the project root
AGENTS_FILE = "AGENTS.md"

@pytest.fixture
def agents_content():
    """Fixture to read the AGENTS.md file content."""
    path = Path(AGENTS_FILE)
    if not path.exists():
        pytest.fail(f"{AGENTS_FILE} not found at project root.")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def test_agents_md_exists():
    """Verify that AGENTS.md exists at the root of the repository."""
    assert os.path.exists(AGENTS_FILE), "AGENTS.md must be located at the root."

def test_agents_md_has_agent_registry(agents_content):
    """
    Verify that AGENTS.md contains a registry of agent roles and responsibilities.
    Success Criteria: Contains a current table/list of agent roles and responsibilities.
    """
    # Check for a header related to Agents
    assert re.search(r"#.*Agents", agents_content, re.IGNORECASE), "Missing Agent Registry header."
    
    # Check for specific agent details (based on Aegis in context)
    # We look for the Role and Responsibilities keywords
    assert "Role" in agents_content, "Agent registry should define 'Role'."
    
    # The requirement specifically mentions 'responsibilities'
    # Even if empty in the current draft, the section/label must exist
    assert re.search(r"responsibilities", agents_content, re.IGNORECASE), "Agent registry must list 'Responsibilities'."

def test_agents_md_has_adr_section(agents_content):
    """
    Verify that AGENTS.md contains a section for Architectural Decisions (ADRs).
    Success Criteria: Includes active ADRs.
    """
    # Check for ADR or Architectural Decisions header
    adr_pattern = re.compile(r"(Architectural Decisions|ADR)", re.IGNORECASE)
    assert adr_pattern.search(agents_content), "AGENTS.md must contain a section for Architectural Decisions (ADRs)."

def test_agents_md_has_write_back_protocol(agents_content):
    """
    Verify that AGENTS.md includes the standardized 'Write-back Protocol'.
    Success Criteria: Includes a standardized 'Write-back Protocol' instruction for all agents.
    """
    # Check for the specific heading 'Write-back Protocol'
    assert "Write-back Protocol" in agents_content, "AGENTS.md is missing the mandatory 'Write-back Protocol' section."
    
    # Verify that it contains instructions (e.g., updating memory, .mdc files, or reflection)
    # Based on PRD/Workflow context, we expect instructions about updating context/memory
    keywords = ["instruction", "update", "memory", "agent", "task"]
    found_keywords = [word for word in keywords if word.lower() in agents_content.lower()]
    
    assert len(found_keywords) >= 2, f"Write-back Protocol section seems incomplete. Found keywords: {found_keywords}"

def test_agents_md_structure_integrity(agents_content):
    """
    Verify the file uses proper Markdown structure to ensure AI tools can parse it.
    """
    # Ensure there is at least one H1 header
    assert agents_content.startswith("# "), "AGENTS.md should start with a top-level Markdown header."
    
    # Ensure it's not just a copy of the PRD (it should be a summary/registry)
    assert "PRD:" not in agents_content[:50], "AGENTS.md should be a registry, not a duplicate of the PRD."
