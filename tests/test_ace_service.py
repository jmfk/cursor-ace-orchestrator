import pytest
from pathlib import Path
import os
import shutil
from ace_lib.services.ace_service import ACEService
from ace_lib.models.schemas import Agent, AgentsConfig, TokenMode, TaskType

@pytest.fixture
def temp_workspace(tmp_path):
    """Create a temporary workspace for testing."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return workspace

@pytest.fixture
def service(temp_workspace):
    """Initialize ACEService in a temporary workspace."""
    return ACEService(base_path=temp_workspace)

def test_init_directories(service, temp_workspace):
    """Test that directories are correctly identified."""
    assert service.ace_dir == temp_workspace / ".ace"
    assert service.ace_local_dir == temp_workspace / ".ace-local"

def test_agent_creation(service):
    """Test creating an agent."""
    agent = service.create_agent(id="test-agent", name="Test Agent", role="tester")
    assert agent.id == "test-agent"
    assert agent.role == "tester"

    agents_config = service.load_agents()
    assert len(agents_config.agents) == 1
    assert agents_config.agents[0].id == "test-agent"

def test_ownership_resolution(service):
    """Test path ownership resolution."""
    service.assign_ownership("src/core", "agent-1")
    service.assign_ownership("src/core/utils", "agent-2")

    assert service.resolve_owner("src/core/main.py") == "agent-1"
    assert service.resolve_owner("src/core/utils/helper.py") == "agent-2"
    assert service.resolve_owner("src/other/file.py") is None

def test_onboarding_sop(service):
    """Test generating onboarding SOP (Phase 9.5)."""
    service.create_agent(id="dev-1", name="Developer 1", role="developer")
    onboarding_file = service.onboard_agent("dev-1")

    assert onboarding_file.exists()
    content = onboarding_file.read_text()
    assert "SOP: Agent Onboarding - Developer 1 (dev-1)" in content
    assert "## 1. Context Acquisition" in content

    # Check if memory file was created
    memory_file = service.base_path / ".cursor/rules/developer.mdc"
    assert memory_file.exists()
    assert "# Developer 1 Playbook (developer)" in memory_file.read_text()

def test_pr_review_sop(service):
    """Test generating PR review SOP (Phase 9.5)."""
    review_file = service.review_pr("PR-123", "reviewer-1")
    assert review_file.exists()
    content = review_file.read_text()
    assert "SOP: PR Review - PR-123" in content
    assert "**Reviewer**: reviewer-1" in content
    assert "## 3. Security Check" in content

def test_audit_sop(service):
    """Test generating audit SOP (Phase 9.5)."""
    service.create_agent(id="dev-1", name="Developer 1", role="developer")
    audit_file = service.audit_agent("dev-1")
    assert audit_file.exists()
    content = audit_file.read_text()
    assert "SOP: Agent Audit - Developer 1 (dev-1)" in content

def test_mail_system(service):
    """Test sending and reading mail."""
    service.send_mail(
        to_agent="agent-b", from_agent="agent-a", subject="Hello", body="Test body"
    )

    messages = service.list_mail("agent-b")
    assert len(messages) == 1
    assert messages[0].subject == "Hello"
    assert messages[0].from_agent == "agent-a"

    msg = service.read_mail("agent-b", messages[0].id)
    assert msg.body == "Test body"
    assert msg.status == "read"

def test_decision_management(service):
    """Test adding and listing decisions (ADRs)."""
    decision = service.add_decision(
        title="Use FastAPI",
        context="Need a web framework",
        decision="Use FastAPI for the backend",
        consequences="Fast and type-safe",
        agent_id="architect-1",
    )
    assert decision.id == "ADR-001"
    assert decision.title == "Use FastAPI"

    decisions = service.list_decisions()
    assert len(decisions) == 1
    assert decisions[0].title == "Use FastAPI"

def test_context_building(service):
    """Test building context for an agent."""
    # Setup global rules
    service.cursor_rules_dir.mkdir(parents=True, exist_ok=True)
    global_rules = service.cursor_rules_dir / "_global.mdc"
    global_rules.write_text("Global project rules")

    # Setup agent and playbook
    service.create_agent(id="dev-1", name="Dev 1", role="developer")
    playbook = service.cursor_rules_dir / "developer.mdc"
    playbook.write_text("Developer playbook")

    context, agent_id = service.build_context(path="src/main.py", agent_id="dev-1")

    assert agent_id == "dev-1"
    assert "GLOBAL RULES" in context
    assert "Global project rules" in context
    assert "AGENT PLAYBOOK (developer)" in context
    assert "Developer playbook" in context

def test_reflection_parsing(service):
    """Test parsing reflection output from LLM."""
    reflection_text = """
[str-001] helpful=1 harmful=0 :: Use pytest for testing.
[mis-002] helpful=0 harmful=1 :: Avoid global state.
[dec-003] :: Use PostgreSQL for database.
"""
    updates = service.parse_reflection_output(reflection_text)
    assert len(updates) == 3
    assert updates[0]["type"] == "str"
    assert updates[0]["id"] == "001"
    assert updates[0]["description"] == "Use pytest for testing."
    assert updates[1]["type"] == "mis"
    assert updates[2]["type"] == "dec"

def test_playbook_update(service):
    """Test updating a playbook with new learnings."""
    service.cursor_rules_dir.mkdir(parents=True, exist_ok=True)
    playbook_path = service.cursor_rules_dir / "developer.mdc"
    playbook_path.write_text("""# Developer Playbook
## Strategier & patterns
## Kända fallgropar
## Arkitekturella beslut
""")

    updates = [
        {
            "type": "str",
            "id": "NEW",
            "helpful": 1,
            "harmful": 0,
            "description": "New strategy",
        },
        {
            "type": "mis",
            "id": "NEW",
            "helpful": 0,
            "harmful": 1,
            "description": "New pitfall",
        },
    ]

    success = service.update_playbook(playbook_path, updates)
    assert success is True

    content = playbook_path.read_text()
    assert "[str-001]" in content
    assert "New strategy" in content
    assert "[mis-001]" in content
    assert "New pitfall" in content

def test_memory_pruning(service):
    """Test pruning harmful strategies from memory."""
    service.cursor_rules_dir.mkdir(parents=True, exist_ok=True)
    playbook_path = service.cursor_rules_dir / "developer.mdc"
    playbook_path.write_text("""# Developer Playbook
## Strategier & patterns
<!-- [str-001] helpful=1 harmful=5 :: Harmful strategy -->
<!-- [str-002] helpful=5 harmful=1 :: Helpful strategy -->
""")

    agent = service.create_agent(id="dev-1", name="Dev 1", role="developer")
    # Threshold 0 means harmful - helpful > 0
    pruned_count = service.prune_memory(agent, threshold=0)

    assert pruned_count == 1
    content = playbook_path.read_text()
    assert "[PRUNED] <!-- [str-001]" in content
    assert "<!-- [str-002]" in content

def test_stitch_mockup(service, monkeypatch):
    """Test Google Stitch mockup generation (Phase 4.5)."""
    from ace_lib.stitch import stitch_engine

    # Mock generate_mockup
    mock_url = "https://stitch.google.com/canvas/test_mockup"
    mock_code = (
        "// Generated via Stitch API\nexport const Mockup = () => <div>Mockup</div>;"
    )
    monkeypatch.setattr(
        stitch_engine, "generate_mockup", lambda *args, **kwargs: (mock_url, mock_code)
    )

    # Mock extract_components
    monkeypatch.setattr(
        stitch_engine,
        "extract_components",
        lambda *args, **kwargs: {
            "Mockup": "export const Mockup = () => <div>Mockup</div>;"
        },
    )

    # Mock get_stitch_key
    monkeypatch.setattr(service, "get_stitch_key", lambda: "test-key")

    url = service.ui_mockup("Login page", "agent-1")
    assert url == mock_url

    mockup_id = url.split("/")[-1]
    mockup_file = service.ace_dir / "ui_mockups" / f"{mockup_id}.md"
    assert mockup_file.exists()
    content = mockup_file.read_text(encoding="utf-8")
    assert "// Generated via Stitch API" in content

def test_stitch_sync(service, monkeypatch):
    """Test Google Stitch code sync (Phase 8.3)."""
    from ace_lib.stitch import stitch_engine

    mockup_id = "test_mockup"
    mockup_dir = service.ace_dir / "ui_mockups"
    mockup_dir.mkdir(parents=True, exist_ok=True)
    mockup_file = mockup_dir / f"{mockup_id}.md"
    mockup_file.write_text(
        """# UI Mockup
## Design & Code
```tsx
export const Test = () => <div>Old Test</div>;
```
""",
        encoding="utf-8",
    )

    new_code = "export const Test = () => <div>New Test</div>;"
    monkeypatch.setattr(stitch_engine, "sync_mockup", lambda *args, **kwargs: new_code)
    monkeypatch.setattr(
        stitch_engine, "extract_components", lambda *args, **kwargs: {"Test": new_code}
    )

    # Mock get_stitch_key
    monkeypatch.setattr(service, "get_stitch_key", lambda: "test-key")

    url = f"https://stitch.google.com/canvas/{mockup_id}"
    code = service.ui_sync(url)
    assert code == new_code

    # Check if file was updated
    content = mockup_file.read_text(encoding="utf-8")
    assert "New Test" in content

def test_ralph_loop_native(service, monkeypatch):
    """Test native RALPH loop integration (Phase 4.1)."""
    import subprocess
    from unittest.mock import MagicMock

    def mock_run(cmd, shell=True, capture_output=True, text=True, env=None, **kwargs):
        mock_res = MagicMock()
        if "cursor-agent" in cmd:
            mock_res.returncode = 0
            mock_res.stdout = "Agent success output"
            mock_res.stderr = ""
        elif "pytest" in cmd:
            mock_res.returncode = 0
            mock_res.stdout = "Test success output"
            mock_res.stderr = ""
        return mock_res

    monkeypatch.setattr(subprocess, "run", mock_run)
    
    # Mock reflect_on_session
    monkeypatch.setattr(
        service,
        "reflect_on_session",
        lambda x: "[str-NEW] helpful=1 harmful=0 :: New strategy from loop",
    )
    
    # Setup agent and playbook
    service.create_agent(id="dev-1", name="Dev 1", role="developer")
    service.cursor_rules_dir.mkdir(parents=True, exist_ok=True)
    playbook_path = service.cursor_rules_dir / "developer.mdc"
    playbook_path.write_text("# Developer Playbook\n## Strategier & patterns\n")

    # Dummy plan.md
    plan_path = service.base_path / "plan.md"
    plan_path.write_text("# Plan")

    success, iterations = service.run_loop(
        prompt="Fix bug",
        test_cmd="pytest",
        max_iterations=1,
        agent_id="dev-1",
        plan_file=str(plan_path),
    )

    assert success is True
    assert iterations == 1
    assert "[str-001]" in playbook_path.read_text()
