from fastapi import FastAPI, HTTPException
from typing import List, Optional
from ace_lib.services.ace_service import ACEService
from ace_lib.models.schemas import (
    Agent, Decision, TokenMode, TaskType, Config, OwnershipConfig
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
