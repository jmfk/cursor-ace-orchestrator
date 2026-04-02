import pytest
import os
import re
from pathlib import Path
from reflection import ReflectionEngine, PlaybookUpdater, ReflectionResult, ReflectionEntry

@pytest.fixture
def temp_playbook(tmp_path):
    """Creates a temporary .mdc playbook file with initial content."""
    playbook_path = tmp_path / "test_agent.mdc"
    content = """# Test Agent Playbook
Description: This is a test agent.

## Strategier & patterns
<!-- [str-001] helpful=2 harmful=0 :: Use early returns to reduce nesting. -->

## Kända fallgropar
- Manual pitfall: Don't forget to mock external APIs.

## Arkitekturella beslut
"""
    playbook_path.write_text(content)
    return playbook_path

class TestWriteBackPipeline:
    """
    Test suite for the Write-back Pipeline requirement.
    Verifies extraction of strategies/pitfalls, incremental updates, and counter management.
    """

    def test_reflection_extraction_logic(self):
        """
        Success Criteria: The reflection prompt successfully extracts new strategies [str-XXX] 
        and pitfalls [mis-XXX] in structured format.
        """
        engine = ReflectionEngine()
        raw_output = """
        During this task, I discovered a new approach.
        [str-NEW_PATTERN] helpful=1 harmful=0 :: Use composition over inheritance for plugins.
        I also hit a snag:
        [mis-TIMEOUT_ERR] helpful=0 harmful=1 :: Large file uploads timeout without chunking.
        And a decision was made:
        [dec-FASTAPI] :: Use FastAPI for all new microservices.
        """

        result = engine.parse_output(raw_output)

        # Verify Strategies
        strategies = [e for e in result.entries if e.type == "str"]
        assert len(strategies) == 1
        assert strategies[0].id == "NEW_PATTERN"
        assert strategies[0].content == "Use composition over inheritance for plugins."
        assert strategies[0].helpful == 1

        # Verify Pitfalls
        pitfalls = [e for e in result.entries if e.type == "mis"]
        assert len(pitfalls) == 1
        assert pitfalls[0].id == "TIMEOUT_ERR"
        assert pitfalls[0].harmful == 1

        # Verify Decisions
        decisions = [e for e in result.entries if e.type == "dec"]
        assert len(decisions) == 1
        assert decisions[0].id == "FASTAPI"

    def test_incremental_update_preserves_manual_content(self, temp_playbook):
        """
        Success Criteria: The orchestrator performs incremental updates to .mdc files 
        without overwriting existing manual content.
        """
        updater = PlaybookUpdater(str(temp_playbook))
        new_reflections = ReflectionResult(entries=[
            ReflectionEntry(id="002", type="str", helpful=1, harmful=0, content="New strategy added.")
        ])

        updater.update(new_reflections)
        content = temp_playbook.read_text()

        # Verify manual content is still there
        assert "Description: This is a test agent." in content
        assert "- Manual pitfall: Don't forget to mock external APIs." in content
        # Verify new content is added
        assert "<!-- [str-002] helpful=1 harmful=0 :: New strategy added. -->" in content
        # Verify old automated content is still there
        assert "<!-- [str-001] helpful=2 harmful=0 :: Use early returns to reduce nesting. -->" in content

    def test_counter_updates_on_existing_entries(self, temp_playbook):
        """
        Success Criteria: Helpful/Harmful counters are updated based on the success or failure of the task.
        This test verifies that if an entry with the same ID exists, the counters are incremented.
        """
        updater = PlaybookUpdater(str(temp_playbook))
        
        # Existing entry [str-001] has helpful=2, harmful=0
        # We simulate a new success for the same strategy
        update_entry = ReflectionResult(entries=[
            ReflectionEntry(id="001", type="str", helpful=1, harmful=0, content="Use early returns to reduce nesting.")
        ])

        updater.update(update_entry)
        content = temp_playbook.read_text()

        # The logic in PlaybookUpdater._update_section (from context) increments existing values
        # helpful: 2 + 1 = 3
        assert "helpful=3" in content
        assert "harmful=0" in content
        # Ensure we didn't duplicate the line
        assert content.count("[str-001]") == 1

    def test_missing_section_creation(self, tmp_path):
        """
        Verifies that if a required section (e.g. Kända fallgropar) is missing, 
        the updater creates it instead of failing.
        """
        playbook_path = tmp_path / "minimal.mdc"
        playbook_path.write_text("# Minimal Playbook\n")
        
        updater = PlaybookUpdater(str(playbook_path))
        new_reflections = ReflectionResult(entries=[
            ReflectionEntry(id="BUG01", type="mis", helpful=0, harmful=1, content="Missing null check in parser.")
        ])

        updater.update(new_reflections)
        content = playbook_path.read_text()

        assert "## Kända fallgropar" in content
        assert "<!-- [mis-BUG01] helpful=0 harmful=1 :: Missing null check in parser. -->" in content

    def test_decision_extraction_and_storage(self, temp_playbook):
        """
        Verifies that architectural decisions [dec-XXX] are stored correctly without counters.
        """
        updater = PlaybookUpdater(str(temp_playbook))
        new_reflections = ReflectionResult(entries=[
            ReflectionEntry(id="ARCH-01", type="dec", content="Use Event-Driven architecture for notifications.")
        ])

        updater.update(new_reflections)
        content = temp_playbook.read_text()

        assert "## Arkitekturella beslut" in content
        assert "<!-- [dec-ARCH-01] :: Use Event-Driven architecture for notifications. -->" in content
        # Decisions should not have helpful/harmful counters according to the regex in reflection.py
        assert "helpful=" not in content.split("## Arkitekturella beslut")[1]