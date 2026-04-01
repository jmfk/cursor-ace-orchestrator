import pytest
from pathlib import Path
import shutil
from ace_lib.services.ace_service import ACEService


@pytest.fixture
def service():
    test_dir = Path("test_playbook_dir")
    if test_dir.exists():
        shutil.rmtree(test_dir)
    test_dir.mkdir(parents=True)

    rules_dir = test_dir / ".cursor" / "rules"
    rules_dir.mkdir(parents=True)

    svc = ACEService(base_path=test_dir)
    yield svc

    shutil.rmtree(test_dir)


def test_update_playbook_new_strategy(service):
    playbook_path = service.cursor_rules_dir / "test_role.mdc"
    playbook_path.write_text("# Test Playbook\n\n## Strategier & patterns\n")

    updates = [{
        "type": "str",
        "id": "NEW",
        "helpful": 1,
        "harmful": 0,
        "description": "Always use type hints."
    }]

    service.update_playbook(playbook_path, updates)
    content = playbook_path.read_text()

    assert "<!-- [str-001] helpful=1 harmful=0 :: Always use type hints. -->" in content


def test_update_playbook_existing_strategy(service):
    playbook_path = service.cursor_rules_dir / "test_role.mdc"
    playbook_path.write_text(
        "# Test Playbook\n\n## Strategier & patterns\n"
        "<!-- [str-001] helpful=1 harmful=0 :: Always use type hints. -->\n"
    )

    updates = [{
        "type": "str",
        "id": "001",
        "helpful": 1,
        "harmful": 0,
        "description": "Always use type hints."
    }]

    service.update_playbook(playbook_path, updates)
    content = playbook_path.read_text()

    assert "<!-- [str-001] helpful=2 harmful=0 :: Always use type hints. -->" in content


def test_update_playbook_new_pitfall(service):
    playbook_path = service.cursor_rules_dir / "test_role.mdc"
    playbook_path.write_text("# Test Playbook\n\n## Kända fallgropar\n")

    updates = [{
        "type": "mis",
        "id": "NEW",
        "helpful": 0,
        "harmful": 1,
        "description": "Avoid global variables."
    }]

    service.update_playbook(playbook_path, updates)
    content = playbook_path.read_text()

    assert "<!-- [mis-001] helpful=0 harmful=1 :: Avoid global variables. -->" in content


def test_update_playbook_new_decision(service):
    playbook_path = service.cursor_rules_dir / "test_role.mdc"
    playbook_path.write_text("# Test Playbook\n\n## Arkitekturella beslut\n")

    updates = [{
        "type": "dec",
        "id": "NEW",
        "description": "Use FastAPI for the backend."
    }]

    service.update_playbook(playbook_path, updates)
    content = playbook_path.read_text()

    assert "<!-- [dec-001] :: Use FastAPI for the backend. -->" in content


def test_update_playbook_missing_sections(service):
    playbook_path = service.cursor_rules_dir / "test_role.mdc"
    playbook_path.write_text("# Test Playbook\n")

    updates = [
        {"type": "str", "id": "NEW", "helpful": 1, "harmful": 0, "description": "Strategy 1"},
        {"type": "mis", "id": "NEW", "helpful": 0, "harmful": 1, "description": "Pitfall 1"},
        {"type": "dec", "id": "NEW", "description": "Decision 1"}
    ]

    service.update_playbook(playbook_path, updates)
    content = playbook_path.read_text()

    assert "## Strategier & patterns" in content
    assert "## Kända fallgropar" in content
    assert "## Arkitekturella beslut" in content
    assert "[str-001]" in content
    assert "[mis-001]" in content
    assert "[dec-001]" in content
