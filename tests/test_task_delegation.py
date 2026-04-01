from ace_lib.services.ace_service import ACEService
from ace_lib.models.schemas import Agent, AgentsConfig

def test_task_decomposition(tmp_path):
    svc = ACEService(tmp_path)
    # Mock anthropic client would be better, but we can test the fallback
    task = "Implement a new authentication system with JWT and OAuth2"
    subtasks = svc.decompose_task(task)
    
    assert len(subtasks) > 0
    assert "description" in subtasks[0]
    assert "status" in subtasks[0]

def test_task_delegation(tmp_path):
    svc = ACEService(tmp_path)
    # Create a few agents
    svc.save_agents(AgentsConfig(agents=[
        Agent(id="auth-agent", name="Auth Expert", role="auth",
              email="auth@ace.local", memory_file=".cursor/rules/auth.mdc"),
        Agent(id="base-agent", name="Base Agent", role="base",
              email="base@ace.local", memory_file=".cursor/rules/base.mdc")
    ]))
    
    subtasks = [
        {
            "id": "task-1",
            "description": "Implement JWT authentication",
            "estimated_complexity": 5
        },
        {
            "id": "task-2",
            "description": "General cleanup",
            "estimated_complexity": 2
        }
    ]
    
    delegations = svc.delegate_tasks(subtasks, "base-agent")
    
    assert delegations["task-1"] == "auth-agent"
    assert delegations["task-2"] == "base-agent"
    
    # Check if mail was sent
    auth_mail = svc.list_mail("auth-agent")
    assert len(auth_mail) == 1
    assert "task-1" in auth_mail[0].subject
