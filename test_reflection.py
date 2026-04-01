from reflection import ReflectionEngine, ReflectionEntry, ReflectionResult, PlaybookUpdater


def test_reflection_engine_parse():
    """Test parsing of structured reflection output."""
    engine = ReflectionEngine()
    text = """
    I have completed the task.
    [str-001] helpful=1 harmful=0 :: Allways use strict mode.
    [mis-002] helpful=0 harmful=1 :: Don't forget to close the connection.
    [dec-003] :: Use PostgreSQL for all data storage.
    """
    result = engine.parse_output(text)

    assert len(result.entries) == 3

    str_entry = next(e for e in result.entries if e.type == "str")
    assert str_entry.id == "001"
    assert str_entry.helpful == 1
    assert str_entry.harmful == 0
    assert str_entry.content == "Allways use strict mode."

    mis_entry = next(e for e in result.entries if e.type == "mis")
    assert mis_entry.id == "002"
    assert mis_entry.helpful == 0
    assert mis_entry.harmful == 1
    assert mis_entry.content == "Don't forget to close the connection."

    dec_entry = next(e for e in result.entries if e.type == "dec")
    assert dec_entry.id == "003"
    assert dec_entry.content == "Use PostgreSQL for all data storage."


def test_update_playbook(tmp_path):
    """Test updating a playbook with new reflections."""
    playbook_file = tmp_path / "test.mdc"
    playbook_file.write_text("""---
description: "Test playbook"
---
# Test Playbook

## Arkitekturella beslut
<!-- [dec-001] :: Use SQLite for local storage -->

## Strategier & patterns

## Kända fallgropar
""")

    updater = PlaybookUpdater(str(playbook_file))

    # 1. Add new strategy
    reflections = ReflectionResult(
        entries=[
            ReflectionEntry(
                id="001",
                type="str",
                helpful=1,
                harmful=0,
                content="Use TDD.",
            ),
        ]
    )
    updater.update(reflections)
    content = playbook_file.read_text()
    assert "<!-- [str-001] helpful=1 harmful=0 :: Use TDD. -->" in content

    # 2. Update existing decision
    reflections = ReflectionResult(
        entries=[
            ReflectionEntry(
                id="001", type="dec", content="Use PostgreSQL."
            ),
        ]
    )
    updater.update(reflections)
    content = playbook_file.read_text()
    assert "<!-- [dec-001] :: Use PostgreSQL. -->" in content
    assert "Use SQLite" not in content


def test_add_missing_sections(tmp_path):
    """Test adding missing sections to a playbook."""
    playbook_file = tmp_path / "test.mdc"
    playbook_file.write_text("# Empty Playbook")

    updater = PlaybookUpdater(str(playbook_file))
    reflections = ReflectionResult(
        entries=[
            ReflectionEntry(
                id="001",
                type="str",
                helpful=1,
                harmful=0,
                content="Strategy 1",
            ),
            ReflectionEntry(id="001", type="dec", content="Decision 1"),
            ReflectionEntry(
                id="001",
                type="mis",
                helpful=0,
                harmful=1,
                content="Pitfall 1",
            ),
        ]
    )

    updater.update(reflections)
    content = playbook_file.read_text()

    assert "## Strategier & patterns" in content
    assert "<!-- [str-001] helpful=1 harmful=0 :: Strategy 1 -->" in content
    assert "## Arkitekturella beslut" in content
    assert "<!-- [dec-001] :: Decision 1 -->" in content
    assert "## Kända fallgropar" in content
    assert "<!-- [mis-001] helpful=0 harmful=1 :: Pitfall 1 -->" in content
