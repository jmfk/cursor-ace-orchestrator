import pytest
from ace_lib.services.ace_service import ACEService

@pytest.fixture
def ace_service(tmp_path):
    service = ACEService(tmp_path)
    service.ace_dir.mkdir(parents=True, exist_ok=True)
    (service.ace_dir / "agents.yaml").touch()
    service.cursor_rules_dir.mkdir(parents=True, exist_ok=True)
    return service

def test_cross_project_sync_advanced(ace_service, tmp_path):
    # 1. Setup source agent and playbook
    agent = ace_service.create_agent(id="a1", name="A1", role="r1")
    playbook_path = ace_service.base_path / agent.memory_file
    playbook_path.parent.mkdir(parents=True, exist_ok=True)
    playbook_path.write_text("""
## Strategier & patterns
<!-- [str-001] helpful=10 harmful=0 :: Good strategy with /Users/jmfk/path -->
<!-- [str-002] helpful=0 harmful=5 :: Bad strategy -->
""")
    
    # 2. Export learnings
    export_dir = tmp_path / "export"
    ace_service.export_learnings("a1", export_dir)
    
    export_file = next(export_dir.glob("*.yaml"))
    assert export_file.exists()
    
    # 3. Import into another agent/project
    agent2 = ace_service.create_agent(id="a2", name="A2", role="r2")
    playbook2_path = ace_service.base_path / agent2.memory_file
    playbook2_path.parent.mkdir(parents=True, exist_ok=True)
    playbook2_path.write_text("## Strategier & patterns\n")
    
    count = ace_service.import_learnings(export_file, "a2")
    
    # Should only import the good strategy (helpful > harmful)
    assert count == 1
    
    content2 = playbook2_path.read_text()
    # Should be anonymized
    assert "<PATH>" in content2
    assert "/Users/jmfk/path" not in content2
    # Should have source project prefix
    assert "[X-PROJ from" in content2
    
    # 4. Test duplicate prevention
    count_dup = ace_service.import_learnings(export_file, "a2")
    assert count_dup == 0
