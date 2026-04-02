import os
import json
from pathlib import Path
from ace_lib.planner.hierarchical_planner import HierarchicalPlanner
from ace_lib.planner.plan_tree import PlanNode
from reflection import ReflectionEntry, ReflectionResult

def test_hierarchical_planner_reflection(tmp_path):
    # Setup mock environment
    ace_dir = tmp_path / ".ace"
    ace_dir.mkdir()
    
    rules_dir = tmp_path / ".cursor" / "rules"
    rules_dir.mkdir(parents=True)
    
    global_mdc = rules_dir / "_global.mdc"
    global_mdc.write_text("# Global Rules\n\n## Strategier & patterns\n")
    
    # Mock agents.yaml
    agents_yaml = ace_dir / "agents.yaml"
    agents_yaml.write_text("""
version: "1"
agents:
  - id: auth-agent
    name: Aegis
    role: auth
    email: auth@ace.local
    memory_file: .cursor/rules/auth.mdc
""")
    
    auth_mdc = rules_dir / "auth.mdc"
    auth_mdc.write_text("# Auth Rules\n\n## Strategier & patterns\n")
    
    # Mock run_cursor_agent_fn
    def mock_run_agent(prompt, model):
        if "auth" in prompt.lower():
            return "Task completed. [str-001] helpful=1 harmful=0 :: Use JWT."
        return "Task completed. [str-002] helpful=1 harmful=0 :: Use TDD."

    # Initialize planner
    # We need to mock os.getcwd() or change directory
    os.chdir(tmp_path)
    
    planner = HierarchicalPlanner(
        prd_path="PRD.md",
        run_cursor_agent_fn=mock_run_agent,
        planner_model="test-model",
        validator_model="test-model",
        context_model="test-model",
        executor_model="test-model"
    )
    
    # Test reflection for a generic node
    node = PlanNode(id="0001", title="Generic Task", description="A generic task")
    # We'll manually call the reflection part or a method that triggers it
    # Since run() is a loop, we can't easily test it without more mocks
    
    # Let's test _resolve_agent_for_node
    assert planner._resolve_agent_for_node(PlanNode(id="0002", title="Auth Task")) == "auth-agent"
    
    # Test reflection extraction and update
    output = "Completed. [str-001] helpful=1 harmful=0 :: Use JWT."
    reflections = planner.reflection_engine.parse_output(output)
    assert len(reflections.entries) == 1
    
    # Manually trigger the update logic as it would happen in run()
    agent_id = planner._resolve_agent_for_node(PlanNode(id="0002", title="Auth Task"))
    assert agent_id == "auth-agent"
    
    # Verify playbook update
    from reflection import PlaybookUpdater
    playbook_path = tmp_path / ".cursor" / "rules" / "auth.mdc"
    updater = PlaybookUpdater(str(playbook_path))
    updater.update(reflections)
    
    content = playbook_path.read_text()
    assert "<!-- [str-001] helpful=1 harmful=0 :: Use JWT. -->" in content

if __name__ == "__main__":
    import pytest
    pytest.main([__file__])
