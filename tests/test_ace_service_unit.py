import pytest
from ace_lib.services.ace_service import ACEService
from ace_lib.models.schemas import TaskType

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

def test_service_initialization(service, temp_workspace):
    """Test that ACEService initializes correctly and creates necessary directories."""
    assert service.base_path == temp_workspace
    assert service.ace_dir == temp_workspace / ".ace"
    assert service.cursor_rules_dir == temp_workspace / ".cursor" / "rules"

def test_agent_lifecycle(service):
    """Test creating and loading agents."""
    agent_id = "test-agent"
    service.create_agent(
        id=agent_id,
        name="Test Agent",
        role="tester",
        responsibilities=["tests/"]
    )
    
    agents_config = service.load_agents()
    assert len(agents_config.agents) == 1
    assert agents_config.agents[0].id == agent_id
    assert agents_config.agents[0].role == "tester"

def test_ownership_resolution(service):
    """Test assigning and resolving module ownership."""
    service.assign_ownership("src/core", "core-agent")
    service.assign_ownership("src/core/utils", "utils-agent")
    
    assert service.resolve_owner("src/core/main.py") == "core-agent"
    assert service.resolve_owner("src/core/utils/helper.py") == "utils-agent"
    assert service.resolve_owner("src/other") is None

def test_context_building(service):
    """Test building context for an agent task."""
    service.create_agent(id="dev", name="Dev", role="developer")
    service.assign_ownership("src", "dev")
    
    # Create a dummy global rule
    service.cursor_rules_dir.mkdir(parents=True, exist_ok=True)
    (service.cursor_rules_dir / "_global.mdc").write_text("Global Rule Content")
    
    context, agent_id = service.build_context(path="src/app.py", task_type=TaskType.IMPLEMENT)
    
    assert agent_id == "dev"
    assert "Global Rule Content" in context
    assert "TASK FRAMING" in context

def test_adr_management(service):
    """Test adding and listing ADRs."""
    service.add_decision(
        title="Use FastAPI",
        context="Need a web framework",
        decision="Use FastAPI for the backend",
        consequences="Fast development, but requires async knowledge"
    )
    
    decisions = service.list_decisions()
    assert len(decisions) == 1
    assert decisions[0].title == "Use FastAPI"
    assert "ADR-001" in decisions[0].id

def test_onboarding_sop_generation(service):
    """Test generating onboarding SOP (Phase 9.5)."""
    service.create_agent(id="dev-1", name="Developer 1", role="developer", responsibilities=["src/core"])
    onboarding_file = service.onboard_agent("dev-1")

    assert onboarding_file.exists()
    content = onboarding_file.read_text()
    assert "SOP: Agent Onboarding - Developer 1 (dev-1)" in content
    assert "## 1. Context Acquisition" in content
    assert "src/core" in content
    
    # Check if memory file was created with correct sections
    memory_file = service.base_path / ".cursor/rules/developer.mdc"
    assert memory_file.exists()
    assert "## Strategier & patterns" in memory_file.read_text()
    assert "## Kända fallgropar" in memory_file.read_text()

def test_pr_review_sop_generation(service):
    """Test generating PR review SOP (Phase 9.5)."""
    review_file = service.review_pr("PR-123", "reviewer-1")
    assert review_file.exists()
    content = review_file.read_text()
    assert "SOP: PR Review - PR-123" in content
    assert "**Reviewer**: reviewer-1" in content
    assert "## 3. Security Check" in content

def test_audit_sop_generation(service):
    """Test generating audit SOP (Phase 9.5)."""
    service.create_agent(id="dev-1", name="Developer 1", role="developer")
    audit_file = service.audit_agent("dev-1")
    assert audit_file.exists()
    content = audit_file.read_text()
    assert "SOP: Agent Audit - Developer 1 (dev-1)" in content
    assert "## 1. Playbook Quality" in content

def test_google_stitch_mockup_logic(service, monkeypatch):
    """Test Google Stitch mockup generation logic (Phase 4.5)."""
    from ace_lib.stitch import stitch_engine

    # Mock generate_mockup
    mock_url = "https://stitch.google.com/canvas/test_mockup"
    mock_code = "export const Mockup = () => <div>Mockup</div>;"
    
    def mock_gen(*args, **kwargs):
        return mock_url, mock_code
        
    monkeypatch.setattr(stitch_engine, "generate_mockup", mock_gen)
    monkeypatch.setattr(service, "get_stitch_key", lambda: "test-key")

    url = service.ui_mockup("Login page", "agent-1")
    assert url == mock_url
    
    mockup_id = url.split("/")[-1]
    mockup_file = service.ace_dir / "ui_mockups" / f"{mockup_id}.md"
    assert mockup_file.exists()
    assert mock_code in mockup_file.read_text()

def test_google_stitch_sync_logic(service, monkeypatch):
    """Test Google Stitch code sync logic (Phase 8.3)."""
    from ace_lib.stitch import stitch_engine

    mockup_id = "test_mockup"
    new_code = "export const Test = () => <div>New Test</div>;"
    
    monkeypatch.setattr(stitch_engine, "sync_mockup", lambda *args, **kwargs: new_code)
    monkeypatch.setattr(service, "get_stitch_key", lambda: "test-key")

    url = f"https://stitch.google.com/canvas/{mockup_id}"
    code = service.ui_sync(url)
    assert code == new_code
    
    mockup_file = service.ace_dir / "ui_mockups" / f"{mockup_id}.md"
    assert mockup_file.exists()
    assert "New Test" in mockup_file.read_text()
