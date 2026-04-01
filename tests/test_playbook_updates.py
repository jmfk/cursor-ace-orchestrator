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

    updates = [
        {
            "type": "str",
            "id": "NEW",
            "helpful": 1,
            "harmful": 0,
            "description": "Always use type hints.",
        }
    ]

    service.update_playbook(playbook_path, updates)
    content = playbook_path.read_text()

    assert "<!-- [str-001] helpful=1 harmful=0 :: Always use type hints. -->" in content


def test_update_playbook_existing_strategy(service):
    playbook_path = service.cursor_rules_dir / "test_role.mdc"
    playbook_path.write_text(
        "# Test Playbook\n\n## Strategier & patterns\n"
        "<!-- [str-001] helpful=1 harmful=0 :: Always use type hints. -->\n"
    )

    updates = [
        {
            "type": "str",
            "id": "001",
            "helpful": 1,
            "harmful": 0,
            "description": "Always use type hints.",
        }
    ]

    service.update_playbook(playbook_path, updates)
    content = playbook_path.read_text()

    assert "<!-- [str-001] helpful=2 harmful=0 :: Always use type hints. -->" in content


def test_update_playbook_new_pitfall(service):
    playbook_path = service.cursor_rules_dir / "test_role.mdc"
    playbook_path.write_text("# Test Playbook\n\n## Kända fallgropar\n")

    updates = [
        {
            "type": "mis",
            "id": "NEW",
            "helpful": 0,
            "harmful": 1,
            "description": "Avoid global variables.",
        }
    ]

    service.update_playbook(playbook_path, updates)
    content = playbook_path.read_text()

    assert (
        "<!-- [mis-001] helpful=0 harmful=1 :: Avoid global variables. -->" in content
    )


def test_update_playbook_new_decision(service):
    playbook_path = service.cursor_rules_dir / "test_role.mdc"
    playbook_path.write_text("# Test Playbook\n\n## Arkitekturella beslut\n")

    updates = [
        {"type": "dec", "id": "NEW", "description": "Use FastAPI for the backend."}
    ]

    service.update_playbook(playbook_path, updates)
    content = playbook_path.read_text()

    assert "<!-- [dec-001] :: Use FastAPI for the backend. -->" in content


def test_update_playbook_complex_markdown(service):
    """Test updating a playbook with complex markdown structures."""
    playbook_path = service.cursor_rules_dir / "complex.mdc"
    playbook_path.write_text("""# Complex Playbook
---
description: Test
globs: ["**/*.py"]
---

## Strategier & patterns
- Existing bullet point
- Another point

## Kända fallgropar
1. Numbered list
2. Another item

## Arkitekturella beslut
> Some blockquote
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
        {"type": "dec", "id": "NEW", "description": "New decision"},
    ]

    service.update_playbook(playbook_path, updates)
    content = playbook_path.read_text()

    # Verify sections and new entries
    assert "## Strategier & patterns" in content
    assert "<!-- [str-001] helpful=1 harmful=0 :: New strategy -->" in content
    assert "- Existing bullet point" in content

    assert "## Kända fallgropar" in content
    assert "<!-- [mis-001] helpful=0 harmful=1 :: New pitfall -->" in content
    assert "1. Numbered list" in content

    assert "## Arkitekturella beslut" in content
    assert "<!-- [dec-001] :: New decision -->" in content
    assert "> Some blockquote" in content
    assert "---" in content  # Frontmatter preserved


def test_update_playbook_no_existing_sections(service):
    """Test updating a playbook that has no headers at all."""
    playbook_path = service.cursor_rules_dir / "empty.mdc"
    playbook_path.write_text("# Empty Playbook\nJust some text.")

    updates = [
        {
            "type": "str",
            "id": "NEW",
            "helpful": 1,
            "harmful": 0,
            "description": "Strategy 1",
        }
    ]

    service.update_playbook(playbook_path, updates)
    content = playbook_path.read_text()

    assert "## Strategier & patterns" in content
    assert "<!-- [str-001] helpful=1 harmful=0 :: Strategy 1 -->" in content
    assert "Just some text." in content


def test_update_playbook_mixed_updates(service):
    """Test a mix of new and existing updates in one call."""
    playbook_path = service.cursor_rules_dir / "mixed.mdc"
    playbook_path.write_text("""# Mixed Playbook

## Strategier & patterns
<!-- [str-001] helpful=1 harmful=0 :: Existing strategy -->

## Kända fallgropar
<!-- [mis-001] helpful=0 harmful=1 :: Existing pitfall -->
""")

    updates = [
        {
            "type": "str",
            "id": "001",
            "helpful": 1,
            "harmful": 0,
            "description": "Existing strategy",
        },
        {
            "type": "str",
            "id": "NEW",
            "helpful": 1,
            "harmful": 0,
            "description": "New strategy",
        },
        {
            "type": "mis",
            "id": "001",
            "helpful": 0,
            "harmful": 1,
            "description": "Existing pitfall",
        },
        {"type": "dec", "id": "NEW", "description": "New decision"},
    ]

    service.update_playbook(playbook_path, updates)
    content = playbook_path.read_text()

    assert "<!-- [str-001] helpful=2 harmful=0 :: Existing strategy -->" in content
    assert "<!-- [str-002] helpful=1 harmful=0 :: New strategy -->" in content
    assert "<!-- [mis-001] helpful=0 harmful=2 :: Existing pitfall -->" in content
    assert "<!-- [dec-001] :: New decision -->" in content


def test_update_playbook_duplicate_new_ids(service):
    """Test that multiple 'NEW' updates of same type get unique IDs."""
    playbook_path = service.cursor_rules_dir / "dupes.mdc"
    playbook_path.write_text("# Dupes Playbook\n\n## Strategier & patterns\n")

    updates = [
        {
            "type": "str",
            "id": "NEW",
            "helpful": 1,
            "harmful": 0,
            "description": "Strategy A",
        },
        {
            "type": "str",
            "id": "NEW",
            "helpful": 1,
            "harmful": 0,
            "description": "Strategy B",
        },
    ]

    service.update_playbook(playbook_path, updates)
    content = playbook_path.read_text()

    assert "<!-- [str-001] helpful=1 harmful=0 :: Strategy A -->" in content
    assert "<!-- [str-002] helpful=1 harmful=0 :: Strategy B -->" in content
