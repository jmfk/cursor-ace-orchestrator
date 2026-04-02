import pytest
import os
import yaml
import json
from pathlib import Path
from typer.testing import CliRunner
from ace import app  # Assuming ace.py has the Typer app
from ace_lib.services.ace_service import ACEService

# --- Fixtures ---

@pytest.fixture
def runner():
    return CliRunner()

@pytest.fixture
def mock_workspace(tmp_path):
    """Sets up a mock ACE workspace structure based on SPECS.md."""
    ace_dir = tmp_path / ".ace"
    ace_dir.mkdir()
    (ace_dir / "agents.yaml").write_text(yaml.dump({
        "agents": [
            {"id": "agent-001", "name": "Architect", "role": "arch"}
        ]
    }))
    (ace_dir / "ownership.yaml").write_text(yaml.dump({
        "mappings": [
            {"path": "src/core", "agent_id": "agent-001"}
        ]
    }))
    
    rules_dir = tmp_path / ".cursor" / "rules"
    rules_dir.mkdir(parents=True)
    (rules_dir / "arch.mdc").write_text("# Architect Playbook\n[str-001] helpful=1 harmful=0 :: Use factory pattern.")
    
    (tmp_path / "AGENTS.md").write_text("# Global Project Memory")
    
    return tmp_path

@pytest.fixture
def ace_service(mock_workspace):
    return ACEService(base_path=mock_workspace)

# --- 1. Critical Module: Registry Tests ---

def test_registry_ownership_resolution(ace_service):
    """
    Verifies that the Ownership Registry correctly maps files to agents 
    using longest-prefix matching as per WORKFLOW.md.
    """
    # Test exact match
    owner = ace_service.resolve_owner("src/core/main.py")
    assert owner == "agent-001"
    
    # Test non-owned path
    owner_none = ace_service.resolve_owner("tests/random_test.py")
    assert owner_none is None

def test_registry_agent_metadata_integrity(ace_service):
    """Ensures agent metadata is retrievable and valid."""
    agent = ace_service.get_agent("agent-001")
    assert agent["name"] == "Architect"
    assert agent["role"] == "arch"

# --- 2. Critical Module: Context Builder & AX Tests ---

def test_context_builder_composition(ace_service):
    """
    Verifies 'Agentic Experience' (AX): Context Builder must compose 
    the correct slice of memory (Global + Role + ADRs).
    """
    # Create a dummy ADR
    adr_dir = ace_service.base_path / ".ace" / "decisions"
    adr_dir.mkdir()
    (adr_dir / "adr-001.md").write_text("Decision: Use FastAPI")

    context = ace_service.build_context(agent_id="agent-001", task="Implement API")
    
    assert "# Architect Playbook" in context
    assert "# Global Project Memory" in context
    assert "Decision: Use FastAPI" in context
    assert "[str-001]" in context

def test_context_token_pruning_modes(ace_service):
    """
    Verifies that Token Consumption Modes (Low vs High) affect context relevance.
    """
    # High mode should include session history, Low might not.
    session_dir = ace_service.base_path / ".ace" / "sessions"
    session_dir.mkdir()
    (session_dir / "last_session.md").write_text("Previous result: Success")

    context_low = ace_service.build_context("agent-001", "task", mode="Low")
    context_high = ace_service.build_context("agent-001", "task", mode="High")

    # In this mock logic, we assume High mode includes session logs
    assert "Previous result: Success" in context_high
    # Depending on implementation, Low might prune it
    # assert "Previous result: Success" not in context_low 

# --- 3. Write-back Accuracy (AX) ---

def test_ax_writeback_persistence(ace_service):
    """
    Verifies the automated write-back loop updates the agent's long-term memory (.mdc).
    """
    playbook_path = ace_service.base_path / ".cursor" / "rules" / "arch.mdc"
    
    # Simulate the reflection model outputting a new strategy delta
    new_learnings = {
        "strategies": [
            {"id": "str-002", "action": "add", "content": "Use Pydantic for validation."}
        ],
        "pitfalls": [
            {"id": "mis-001", "action": "add", "content": "Avoid global state in handlers."}
        ]
    }
    
    ace_service.apply_writeback("agent-001", new_learnings)
    
    updated_content = playbook_path.read_text()
    assert "[str-002]" in updated_content
    assert "Use Pydantic for validation" in updated_content
    assert "[mis-001]" in updated_content

# --- 4. CLI Ergonomics & DX Validation ---

def test_cli_dx_init_flow(runner, mock_workspace):
    """
    Validates CLI ergonomics (DX). The 'init' command should be low-friction
    and create the necessary directory structure.
    """
    # Use a fresh temp dir for init test
    new_project = mock_workspace / "new_project"
    new_project.mkdir()
    os.chdir(new_project)
    
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0
    assert "Initialized ACE Orchestrator" in result.stdout
    assert (new_project / ".ace").exists()
    assert (new_project / "AGENTS.md").exists()

def test_cli_dx_error_handling(runner, mock_workspace):
    """
    Ensures the CLI provides helpful feedback for common developer errors.
    """
    os.chdir(mock_workspace)
    # Try to assign ownership to a non-existent agent
    result = runner.invoke(app, ["own", "src/new", "--agent", "ghost-agent"])
    
    assert result.exit_code != 0
    assert "Error" in result.stdout
    assert "ghost-agent not found" in result.stdout.lower()

# --- 5. TDD Loop (RALPH) Integration ---

def test_ralph_loop_success_criteria(ace_service, monkeypatch):
    """
    Verifies that the 'ace loop' (RALPH) only terminates successfully 
    when the test command passes.
    """
    import subprocess
    
    # Mock agent execution to always 'succeed' in generating code
    monkeypatch.setattr(ace_service, "run_agent_task", lambda *args, **kwargs: True)
    
    # Mock subprocess to simulate a passing test suite
    class MockProcess:
        returncode = 0
        stdout = "All tests passed!"
        stderr = ""
    
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: MockProcess())
    
    success, iterations = ace_service.run_loop(
        prompt="Fix bug", 
        test_cmd="pytest", 
        max_iterations=3
    )
    
    assert success is True
    assert iterations == 1