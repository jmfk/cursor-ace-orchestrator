from fastapi import FastAPI, HTTPException
from typing import List, Optional, Dict
import re
from pathlib import Path
from ace_lib.services.ace_service import ACEService
from ace_lib.models.schemas import (
    Agent, Decision, TokenMode, TaskType, Config, OwnershipConfig, MailMessage
)

app = FastAPI(title="ACE Orchestrator API")
service = ACEService()

@app.get("/agents", response_model=List[Agent])
async def list_agents():
    return service.load_agents().agents


@app.post("/agents", response_model=Agent)
async def create_agent(id: str, name: str, role: str, email: Optional[str] = None):
    try:
        return service.create_agent(id, name, role, email)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/ownership", response_model=OwnershipConfig)
async def get_ownership():
    return service.load_ownership()


@app.post("/ownership")
async def assign_ownership(path: str, agent_id: str):
    return service.assign_ownership(path, agent_id)


@app.get("/context")
async def build_context(path: Optional[str] = None, task_type: TaskType = TaskType.IMPLEMENT, agent_id: Optional[str] = None):
    context, resolved_agent_id = service.build_context(path, task_type, agent_id)
    return {"context": context, "agent_id": resolved_agent_id}


@app.get("/decisions", response_model=List[Decision])
async def list_decisions():
    return service.list_decisions()


@app.post("/decisions", response_model=Decision)
async def add_decision(title: str, context: str, decision: str, consequences: str, status: str = "accepted", agent_id: Optional[str] = None):
    return service.add_decision(title, context, decision, consequences, status, agent_id)


@app.get("/config", response_model=Config)
async def get_config():
    return service.load_config()


@app.post("/config/tokens")
async def set_token_mode(mode: TokenMode):
    config = service.load_config()
    config.token_mode = mode
    service.save_config(config)
    return config


@app.get("/mail/{agent_id}", response_model=List[MailMessage])
async def list_mail(agent_id: str):
    return service.list_mail(agent_id)


@app.get("/mail/{agent_id}/{msg_id}", response_model=MailMessage)
async def read_mail(agent_id: str, msg_id: str):
    msg = service.read_mail(agent_id, msg_id)
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    return msg


@app.post("/mail", response_model=MailMessage)
async def send_mail(to_agent: str, from_agent: str, subject: str, body: str):
    return service.send_mail(to_agent, from_agent, subject, body)


@app.get("/sessions", response_model=List[Dict])
async def list_sessions():
    return service.list_sessions()


@app.get("/sessions/{session_id}")
async def get_session(session_id: str):
    content = service.get_session(session_id)
    if not content:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"content": content}


@app.post("/sessions/{session_id}/reflect")
async def reflect_session(session_id: str):
    content = service.get_session(session_id)
    if not content:
        raise HTTPException(status_code=404, detail="Session not found")
    
    output_match = re.search(r"## Output\n```\n(.*?)\n```", content, re.DOTALL)
    if not output_match:
        raise HTTPException(status_code=400, detail="Could not find output section in session log")
        
    reflection_text = service.reflect_on_session(output_match.group(1))
    updates = service.parse_reflection_output(reflection_text)
    
    # Update playbook if updates found
    if updates:
        agent_id_match = re.search(r"- \*\*Agent ID\*\*: `(.*?)`", content)
        playbook_path = service.cursor_rules_dir / "_global.mdc"
        if agent_id_match and agent_id_match.group(1) != "None":
            agents_config = service.load_agents()
            agent = next((a for a in agents_config.agents if a.id == agent_id_match.group(1)), None)
            if agent:
                playbook_path = Path(agent.memory_file)
        service.update_playbook(playbook_path, updates)
        
    return {"reflection": reflection_text, "updates": updates}


@app.post("/memory/prune")
async def prune_memory(agent_id: Optional[str] = None, threshold: int = 0):
    agents_config = service.load_agents()
    agents = [a for a in agents_config.agents if a.id == agent_id] if agent_id else agents_config.agents
    
    results = {}
    for agent in agents:
        pruned_count = service.prune_memory(agent, threshold)
        results[agent.id] = pruned_count
    return results

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
