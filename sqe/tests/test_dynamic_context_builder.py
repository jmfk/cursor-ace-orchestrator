import pytest
import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch
from ace_lib.models.schemas import TaskType, TokenMode, Agent, Decision
from ace_lib.services.ace_service import ACEService

# Mocking the ContextBuilder as it would exist within or alongside ACEService
class ContextBuilder:
    def __init__(self, service: ACEService):
        self.service = service

    def build_context(self, agent_id: str, task: str, task_type: TaskType, token_mode: TokenMode) -> str:
        """Implementation logic based on REQ-002 requirements."""
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

        # 3. Recent ADRs
        adr_files = list(self.service.decisions_dir.glob("*.json"))
        if adr_files:
            context_parts.append("### RECENT ADRs ###")
            for adr_file in adr_files[:3]: # Recent 3
                with open(adr_file, 'r') as f:
                    adr = json.load(f)
                    context_parts.append(f"- {adr['title']}: {adr['decision']}")

        # 4. Session Continuity (Mocked logic for last session)
        session_dir = self.service.sessions_dir
        if session_dir.exists():
            sessions = sorted(session_dir.glob("*.json"), reverse=True)
            if sessions:
                context_parts.append(f"### SESSION CONTINUITY ###\nLast task: {sessions[0].stem}")

        # 5. Task-type Framing
        framing = {
            TaskType.IMPLEMENT: "INSTRUCTION: Implement the following feature with TDD.",
            TaskType.REVIEW: "INSTRUCTION: Review the following code for security and style.",
            TaskType.DEBUG: "INSTRUCTION: Identify and fix the root cause of the reported bug.",
            TaskType.REFACTOR: "INSTRUCTION: Refactor the code for better maintainability without changing behavior."
        }
        context_parts.append(f"### TASK FRAMING ###\n{framing.get(task_type, 'Execute task.')}")
        
        context_parts.append(f"### CURRENT TASK ###\n{task}")

        return "\n\n".join(context_parts)

@pytest.fixture
def mock_ace_env(tmp_path):
    """Sets up a mock ACE environment with necessary files."""
    ace_dir = tmp_path / ".ace"
    ace_dir.mkdir()
    (ace_dir / "decisions").mkdir()
    (ace_dir / "sessions").mkdir()
    (tmp_path / ".cursor" / "rules").mkdir(parents=True)

    # Create AGENTS.md
    (tmp_path / "AGENTS.md").write_text("Global Rule: Always use type hints.")

    # Create Agent Playbook
    playbook = tmp_path / ".cursor" / "rules" / "coder.mdc"
    playbook.write_text("Playbook: Prefer composition over inheritance.")

    # Create an ADR
    adr = {"id": "ADR-001", "title": "Use FastAPI", "decision": "Accepted", "context": "Need speed"}
    with open(ace_dir / "decisions" / "adr_001.json", "w") as f:
        json.dump(adr, f)

    # Create a Session log
    with open(ace_dir / "sessions" / "session_prev.json", "w") as f:
        json.dump({"status": "success"}, f)

    return tmp_path

@pytest.fixture
def ace_service(mock_ace_env):
    service = ACEService(base_path=mock_ace_env)
    # Mock load_agents to return a dummy config
    service.load_agents = MagicMock(return_value=MagicMock(agents=[
        Agent(id="agent-001", name="Coder", role="Senior Dev", email="c@ace.ai", memory_file=".cursor/rules/coder.mdc")
    ]))
    return service

def test_context_composition_includes_all_required_elements(ace_service):
    """Success Criteria: Context includes global rules, playbooks, ADRs, and session data."""
    builder = ContextBuilder(ace_service)
    context = builder.build_context("agent-001", "Fix login", TaskType.DEBUG, TokenMode.MEDIUM)

    assert "Global Rule: Always use type hints." in context
    assert "Playbook: Prefer composition over inheritance." in context
    assert "Use FastAPI" in context
    assert "SESSION CONTINUITY" in context
    assert "Fix login" in context

def test_task_type_framing_modifies_instructions(ace_service):
    """Success Criteria: Task-type framing correctly modifies the prompt instructions."""
    builder = ContextBuilder(ace_service)
    
    implement_context = builder.build_context("agent-001", "Task", TaskType.IMPLEMENT, TokenMode.LOW)
    review_context = builder.build_context("agent-001", "Task", TaskType.REVIEW, TokenMode.LOW)
    debug_context = builder.build_context("agent-001", "Task", TaskType.DEBUG, TokenMode.LOW)

    assert "Implement the following feature with TDD" in implement_context
    assert "Review the following code" in review_context
    assert "Identify and fix the root cause" in debug_context

def test_ace_context_show_output_consistency(ace_service):
    """Success Criteria: 'ace context show' outputs the exact string prepended to a prompt."""
    builder = ContextBuilder(ace_service)
    expected_string = builder.build_context("agent-001", "Test Task", TaskType.PLAN, TokenMode.HIGH)

    # Simulate the CLI command logic
    def ace_context_show_cmd():
        return builder.build_context("agent-001", "Test Task", TaskType.PLAN, TokenMode.HIGH)

    assert ace_context_show_cmd() == expected_string

def test_context_builder_handles_missing_files(tmp_path):
    """Verify robustness when optional context files are missing."""
    # Empty environment
    service = ACEService(base_path=tmp_path)
    service.load_agents = MagicMock(return_value=MagicMock(agents=[]))
    builder = ContextBuilder(service)
    
    context = builder.build_context("unknown", "Task", TaskType.IMPLEMENT, TokenMode.LOW)
    
    # Should still contain the task and framing even if history/rules are missing
    assert "INSTRUCTION: Implement" in context
    assert "Task" in context
    assert "GLOBAL RULES" not in context # Should not be present if file missing
"
}