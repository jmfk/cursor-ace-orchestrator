import pytest
import os
from pathlib import Path
from reflection import ReflectionEngine, PlaybookUpdater, ReflectionResult, ReflectionEntry

@pytest.fixture
def mock_playbook(tmp_path):
    """Creates a temporary .mdc playbook file with initial content for testing."""
    playbook_path = tmp_path / "agent_memory.mdc"
    content = """# Agent Playbook\nThis is manual documentation that should never be overwritten.\n\n## Strategier & patterns\n<!-- [str-001] helpful=5 harmful=0 :: Use early returns. -->\n\n## Kända fallgropar\n<!-- [mis-001] helpful=0 harmful=2 :: Forgetting to close DB connections. -->\n\n## Arkitekturella beslut\n"""
    playbook_path.write_text(content)
    return playbook_path

class TestWriteBackPipeline:
    """
    Tests the Write-back Pipeline requirement: extraction of learnings, 
    incremental updates, and counter management.
    """

    def test_extraction_of_strategies_and_pitfalls(self):
        """
        Success Criteria: The reflection prompt successfully extracts new 
        strategies [str-XXX] and pitfalls [mis-XXX] in structured format.
        """
        engine = ReflectionEngine()
        agent_output = """
        Task completed successfully.
        [str-ASYNC_RETRY] helpful=1 harmful=0 :: Implement exponential backoff for async calls.
        [mis-MEMORY_LEAK] helpful=0 harmful=1 :: Large loops without generators cause OOM.
        [dec-LINT_STRICT] :: Enforce strict linting on all new modules.
        """

        result = engine.parse_output(agent_output)

        # Verify Strategy Extraction
        strategy = next(e for e in result.entries if e.id == "ASYNC_RETRY")
        assert strategy.type == "str"
        assert strategy.helpful == 1
        assert "exponential backoff" in strategy.content

        # Verify Pitfall Extraction
        pitfall = next(e for e in result.entries if e.id == "MEMORY_LEAK")
        assert pitfall.type == "mis"
        assert pitfall.harmful == 1

        # Verify Decision Extraction
        decision = next(e for e in result.entries if e.id == "LINT_STRICT")
        assert decision.type == "dec"

    def test_incremental_update_preserves_manual_content(self, mock_playbook):
        """
        Success Criteria: The orchestrator performs incremental updates to .mdc files 
        without overwriting existing manual content.
        """
        updater = PlaybookUpdater(str(mock_playbook))
        new_entry = ReflectionEntry(
            id="002", 
            type="str", 
            helpful=1, 
            harmful=0, 
            content="New incremental strategy."
        )
        result = ReflectionResult(entries=[new_entry])

        updater.update(result)
        updated_content = mock_playbook.read_text()

        # Verify manual content is preserved
        assert "This is manual documentation that should never be overwritten." in updated_content
        # Verify existing automated content is preserved
        assert "[str-001]" in updated_content
        # Verify new content is added
        assert "[str-002]" in updated_content
        assert "New incremental strategy." in updated_content

    def test_counter_updates_on_success_failure(self, mock_playbook):
        """
        Success Criteria: Helpful/Harmful counters are updated based on the success or failure of the task.
        This verifies that existing entries have their counters incremented rather than duplicated.
        """
        updater = PlaybookUpdater(str(mock_playbook))
        
        # Existing [str-001] has helpful=5. We simulate another successful use (+1).
        update_entry = ReflectionEntry(
            id="001", 
            type="str", 
            helpful=1, 
            harmful=0, 
            content="Use early returns."
        )
        
        # Existing [mis-001] has harmful=2. We simulate another failure (+1).
        fail_entry = ReflectionEntry(
            id="001", 
            type="mis", 
            helpful=0, 
            harmful=1, 
            content="Forgetting to close DB connections."
        )

        updater.update(ReflectionResult(entries=[update_entry, fail_entry]))
        updated_content = mock_playbook.read_text()

        # Verify counters incremented (5+1=6 and 2+1=3)
        assert "[str-001] helpful=6 harmful=0" in updated_content
        assert "[mis-001] helpful=0 harmful=3" in updated_content
        
        # Ensure no duplication of IDs
        assert updated_content.count("[str-001]") == 1
        assert updated_content.count("[mis-001]") == 1

    def test_missing_section_auto_creation(self, tmp_path):
        """
        Verifies that if a playbook is missing a required section header, 
        the updater creates it automatically.
        """
        playbook_path = tmp_path / "empty.mdc"
        playbook_path.write_text("# Empty Playbook\n")
        
        updater = PlaybookUpdater(str(playbook_path))
        entry = ReflectionEntry(id="NEW", type="mis", helpful=0, harmful=1, content="New pitfall.")
        
        updater.update(ReflectionResult(entries=[entry]))
        content = playbook_path.read_text()

        assert "## Kända fallgropar" in content
        assert "[mis-NEW]" in content

    def test_decision_extraction_without_counters(self):
        """
        Verifies that architectural decisions [dec-XXX] are extracted 
        without requiring helpful/harmful counters.
        """
        engine = ReflectionEngine()
        raw = "[dec-SQLITE] :: Use SQLite for local caching to reduce latency."
        
        result = engine.parse_output(raw)
        assert len(result.entries) == 1
        assert result.entries[0].type == "dec"
        assert result.entries[0].id == "SQLITE"
        assert "local caching" in result.entries[0].content