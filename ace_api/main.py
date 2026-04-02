from fastapi import FastAPI, HTTPException, Body, Request, Depends, Header
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from typing import List, Optional, Dict
import logging
import time
import re
from pathlib import Path
from ace_lib.services.ace_service import ACEService
from ace_lib.models.schemas import (
    Agent,
    Decision,
    TokenMode,
    TaskType,
    Config,
    OwnershipConfig,
    MailMessage,
    SubscriptionsConfig,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("ace-api")

app = FastAPI(title="ACE Orchestrator API")
service = ACEService()

# Setup templates
templates = Jinja2Templates(directory="ace_api/templates")


# --- SSO & Authentication (Phase 10.3) ---

async def verify_sso(authorization: Optional[str] = Header(None)):
    """Middleware-style dependency to verify SSO tokens (Phase 10.3)."""
    config = service.load_config()
    if not config.sso_enabled:
        return True

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid SSO token")

    token = authorization.split(" ")[1]
    if not service.authenticate_sso(token):
        raise HTTPException(status_code=403, detail="SSO authentication failed")

    return True


@app.get("/auth/login-url")
async def get_login_url():
    """Get the SSO login URL for the configured provider."""
    url = service.get_sso_login_url()
    if not url:
        raise HTTPException(status_code=400, detail="SSO not enabled or provider not configured")
    return {"url": url}


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = (time.time() - start_time) * 1000
    logger.info(
        f"{request.method} {request.url.path} - "
        f"Status: {response.status_code} - "
        f"Time: {process_time:.2f}ms"
    )
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error", "message": str(exc)},
    )


@app.get("/agents", response_model=List[Agent], dependencies=[Depends(verify_sso)])
async def list_agents():
    return service.load_agents().agents


@app.post("/agents", response_model=Agent, dependencies=[Depends(verify_sso)])
async def create_agent(
    id: str = Body(...),
    name: str = Body(...),
    role: str = Body(...),
    email: Optional[str] = Body(None),
    responsibilities: List[str] = Body([]),
):
    try:
        return service.create_agent(id, name, role, email, responsibilities)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/ownership", response_model=OwnershipConfig)
async def get_ownership():
    return service.load_ownership()


@app.post("/ownership")
async def assign_ownership(path: str = Body(...), agent_id: str = Body(...)):
    return service.assign_ownership(path, agent_id)


@app.get("/context")
async def build_context(
    path: Optional[str] = None,
    task_type: TaskType = TaskType.IMPLEMENT,
    agent_id: Optional[str] = None,
):
    context, resolved_agent_id = service.build_context(path, task_type, agent_id)
    return {"context": context, "agent_id": resolved_agent_id}


@app.get("/decisions", response_model=List[Decision])
async def list_decisions():
    return service.list_decisions()


@app.post("/decisions", response_model=Decision)
async def add_decision(
    title: str = Body(...),
    context: str = Body(...),
    decision: str = Body(...),
    consequences: str = Body(...),
    status: str = Body("accepted"),
    agent_id: Optional[str] = Body(None),
):
    return service.add_decision(
        title, context, decision, consequences, status, agent_id
    )


@app.get("/config", response_model=Config)
async def get_config():
    return service.load_config()


@app.post("/config/tokens")
async def set_token_mode(mode: TokenMode = Body(...)):
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
async def send_mail(
    to_agent: str = Body(...),
    from_agent: str = Body(...),
    subject: str = Body(...),
    body: str = Body(...),
):
    return service.send_mail(to_agent, from_agent, subject, body)


@app.post("/debate")
async def debate(
    proposal: str = Body(...), agent_ids: List[str] = Body(...), turns: int = Body(3)
):
    consensus = service.debate(proposal, agent_ids, turns)
    return {"consensus": consensus}


@app.post("/loop")
async def run_loop(
    prompt: str = Body(...),
    test_cmd: str = Body(...),
    max_iterations: int = Body(10),
    path: Optional[str] = Body(None),
    agent_id: Optional[str] = Body(None),
):
    success, iterations = service.run_loop(
        prompt, test_cmd, max_iterations, path, agent_id
    )
    return {"success": success, "iterations": iterations}


@app.post("/agents/{agent_id}/onboard")
async def onboard_agent(agent_id: str):
    try:
        onboarding_file = service.onboard_agent(agent_id)
        return {"onboarding_file": str(onboarding_file)}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/agents/{agent_id}/audit")
async def audit_agent(agent_id: str):
    try:
        audit_file = service.audit_agent(agent_id)
        return {"audit_file": str(audit_file)}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/pr/{pr_id}/review")
async def review_pr(pr_id: str, agent_id: str = Body(..., embed=True)):
    review_file = service.review_pr(pr_id, agent_id)
    return {"review_file": str(review_file)}


@app.post("/ui/mockup")
async def ui_mockup(description: str = Body(...), agent_id: str = Body(...)):
    url = service.ui_mockup(description, agent_id)
    return {"url": url}


@app.get("/ui/sync")
async def ui_sync(url: str):
    code = service.ui_sync(url)
    return {"code": code}


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
        raise HTTPException(
            status_code=400, detail="Could not find output section in session log"
        )

    reflection_text = service.reflect_on_session(output_match.group(1))
    updates = service.parse_reflection_output(reflection_text)

    # Update playbook if updates found
    if updates:
        agent_id_match = re.search(r"- \*\*Agent ID\*\*: `(.*?)`", content)
        playbook_path = service.cursor_rules_dir / "_global.mdc"
        if agent_id_match and agent_id_match.group(1) != "None":
            agents_config = service.load_agents()
            agent = next(
                (a for a in agents_config.agents if a.id == agent_id_match.group(1)),
                None,
            )
            if agent:
                playbook_path = Path(agent.memory_file)
        service.update_playbook(playbook_path, updates)

    return {"reflection": reflection_text, "updates": updates}


@app.post("/memory/prune")
async def prune_memory(agent_id: Optional[str] = None, threshold: int = 0):
    agents_config = service.load_agents()
    agents = (
        [a for a in agents_config.agents if a.id == agent_id]
        if agent_id
        else agents_config.agents
    )

    results = {}
    for agent in agents:
        pruned_count = service.prune_memory(agent, threshold)
        results[agent.id] = pruned_count
    return results


@app.get("/subscriptions", response_model=SubscriptionsConfig)
async def get_subscriptions():
    return service.load_subscriptions()


@app.get("/profiler", response_class=HTMLResponse)
async def profiler_dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})


@app.get("/profiler/data")
async def profiler_data():
    return service.get_profiler_logs()


@app.post("/subscriptions")
async def subscribe(
    agent_id: str = Body(...),
    path: str = Body(...),
    priority: str = Body("medium"),
    notify_on_success: bool = Body(True),
    notify_on_failure: bool = Body(True),
):
    return service.subscribe(
        agent_id, path, priority, notify_on_success, notify_on_failure
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
