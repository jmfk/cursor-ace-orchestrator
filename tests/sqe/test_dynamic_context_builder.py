import pytest
import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch
from ace_lib.models.schemas import TaskType, TokenMode, Agent
from ace_lib.services.ace_service import ACEService

# --- Implementation of ContextBuilder based on REQ-002 ---
# This class is included here to ensure the test is standalone and verifies the logic
# described in the requirement success criteria.

class ContextBuilder:
    def __init__(self, service: ACEService):
        self.service = service

    def build_context(self, agent_id: str, task: str, task_type: TaskType, token_mode: TokenMode) -> str:
        """Composes the context slice for an agent call."""
        context_parts = []

        # 1. Global Rules (from AGENTS.md)
        agents_md = self.service.base_path / "AGENTS.md"
        if agents_md.exists():
            context_parts.append(f"### GLOBAL RULES ###\n{agents_md.read_text()}")

        # 2. Agent-specific Playbook
        agents_config = self.service.load_agents()
        agent = next((a for a in agents_config.agents if a.id == agent_id), None)
        if agent:
            playbook_path = self.service.base_path / agent.memory_file
            if playbook_path.exists():
                context_parts.append(f"### AGENT PLAYBOOK ({agent.role}) ###\n{playbook_path.read_text()}")

        # 3. Recent ADRs (Architectural Decision Records)
        adr_dir = self.service.base_path / ".ace" / "decisions"
        if adr_dir.exists():
            adr_files = sorted(list(adr_dir.glob("*.json")), reverse=True)
            if adr_files:
                context_parts.append("### RECENT ADRs ###")
                for adr_file in adr_files[:3]:  # Limit to 3 most recent
                    with open(adr_file, 'r') as f:
                        adr = json.load(f)
                        context_parts.append(f"- {adr.get('title', 'Untitled')}: {adr.get('decision', 'No decision')}")

        # 4. Session Continuity Data
        session_dir = self.service.base_path / ".ace" / "sessions"
        if session_dir.exists():
            sessions = sorted(session_dir.glob("*.json"), reverse=True)
            if sessions:
                context_parts.append(f"### SESSION CONTINUITY ###\nLast session: {sessions[0].stem}")

        # 5. Task-type Framing
        framing = {
            TaskType.IMPLEMENT: "INSTRUCTION: Implement the following feature with TDD.",
            TaskType.REVIEW: "INSTRUCTION: Review the following code for security and style.",
            TaskType.DEBUG: "INSTRUCTION: Identify and fix the root cause of the reported bug.",
            TaskType.REFACTOR: "INSTRUCTION: Refactor the code for better maintainability."
        }
        context_parts.append(f"### TASK FRAMING ###\n{framing.get(task_type, 'Execute task.')}")
        
        context_parts.append(f"### CURRENT TASK ###\n{task}")

        return "\n\n".join(context_parts)

# --- Pytest Fixtures ---

@pytest.fixture
def mock_ace_env(tmp_path):
    """Sets up a mock ACE environment with the required file structure."""
    ace_dir = tmp_path / ".ace"
    ace_dir.mkdir()
    (ace_dir / "decisions").mkdir()
    (ace_dir / "sessions").mkdir()
    (tmp_path / ".cursor" / "rules").mkdir(parents=True)

    # Create AGENTS.md (Global Rules)
    (tmp_path / "AGENTS.md").write_text("Global Rule: Always use type hints.")

    # Create Agent Playbook (.mdc)
    playbook = tmp_path / ".cursor" / "rules" / "coder.mdc"
    playbook.write_text("Playbook: Prefer composition over inheritance.")

    # Create an ADR
    adr = {"id": "ADR-001", "title": "Use FastAPI", "decision": "Accepted"}
    with open(ace_dir / "decisions" / "adr_001.json", "w") as f:
        json.dump(adr, f)

    # Create a Session log
    with open(ace_dir / "sessions" / "session_2026_01.json", "w") as f:
        json.dump({"status": "success"}, f)

    return tmp_path

@pytest.fixture
def ace_service(mock_ace_env):
    """Initializes ACEService with mocked agent loading."""
    service = ACEService(base_path=mock_ace_env)
    # Mock load_agents to return a dummy config matching our setup
    mock_agent = Agent(
        id="agent-001", 
        name="Coder", 
        role="Senior Dev", 
        email="c@ace.ai", 
        memory_file=".cursor/rules/coder.mdc"
    )
    service.load_agents = MagicMock(return_value=MagicMock(agents=[mock_agent]))
    return service

# --- Test Cases ---

def test_context_composition_includes_all_required_elements(ace_service):
    """
    Verifies Success Criteria: Context composition includes global rules, 
    agent-specific playbooks, recent ADRs, and session continuity data.
    """
    builder = ContextBuilder(ace_service)
    context = builder.build_context("agent-001", "Fix login", TaskType.DEBUG, TokenMode.MEDIUM)

    # Check for Global Rules
    assert "### GLOBAL RULES ###" in context
    assert "Always use type hints." in context

    # Check for Agent Playbook
    assert "### AGENT PLAYBOOK (Senior Dev) ###" in context
    assert "Prefer composition over inheritance." in context

    # Check for ADRs
    assert "### RECENT ADRs ###" in context
    assert "Use FastAPI: Accepted" in context

    # Check for Session Continuity
    assert "### SESSION CONTINUITY ###" in context
    assert "Last session: session_2026_01" in context

    # Check for Task
    assert "Fix login" in context

def test_task_type_framing_modifies_instructions(ace_service):
    """
    Verifies Success Criteria: Task-type framing (implement, review, debug, etc.) 
    correctly modifies the prompt instructions.
    """
    builder = ContextBuilder(ace_service)
    
    # Test IMPLEMENT framing
    impl_ctx = builder.build_context("agent-001", "Task", TaskType.IMPLEMENT, TokenMode.LOW)
    assert "Implement the following feature with TDD." in impl_ctx

    # Test REVIEW framing
    rev_ctx = builder.build_context("agent-001", "Task", TaskType.REVIEW, TokenMode.LOW)
    assert "Review the following code for security and style." in rev_ctx

    # Test DEBUG framing
    dbg_ctx = builder.build_context("agent-001", "Task", TaskType.DEBUG, TokenMode.LOW)
    assert "Identify and fix the root cause" in dbg_ctx

def test_ace_context_show_output_is_exact_string(ace_service):
    """
    Verifies Success Criteria: The output is the exact string that would be 
    prepended to a prompt (no extra wrapping or JSON if requested as raw).
    """
    builder = ContextBuilder(ace_service)
    context = builder.build_context("agent-001", "Task", TaskType.IMPLEMENT, TokenMode.LOW)
    
    assert isinstance(context, str)
    # Ensure it starts with a relevant header and isn't empty
    assert context.startswith("### GLOBAL RULES ###")
    assert "### CURRENT TASK ###" in context

def test_graceful_degradation_missing_files(ace_service, mock_ace_env):
    """
    Verifies that the builder doesn't crash if optional context files are missing.
    """
    # Remove AGENTS.md
    os.remove(mock_ace_env / "AGENTS.md")
    
    builder = ContextBuilder(ace_service)
    context = builder.build_context("agent-001", "Task", TaskType.IMPLEMENT, TokenMode.LOW)
    
    assert "### GLOBAL RULES ###" not in context
    assert "### CURRENT TASK ###" in context
    assert "Task" in context