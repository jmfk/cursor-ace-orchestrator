import typer
from pathlib import Path
import os
from datetime import datetime
from typing import Optional, List, Dict
import subprocess
import tempfile
import re
import requests
from rich.console import Console
from rich.table import Table

from ace_lib.services.ace_service import ACEService
from ace_lib.models.schemas import TokenMode, TaskType, OwnershipConfig

app = typer.Typer(no_args_is_help=True)
console = Console()
service = ACEService()


def get_service() -> ACEService:
    return service


def reset_service(base_path: Path):
    global service
    service = ACEService(base_path)


def save_ownership(config: OwnershipConfig):
    get_service().save_ownership(config)


def load_config():
    return get_service().load_config()


def load_agents():
    return get_service().load_agents()


def parse_reflection_output(text: str):
    return get_service().parse_reflection_output(text)


def update_playbook(playbook_path: Path, updates: List[Dict]):
    return get_service().update_playbook(playbook_path, updates)


# --- Meta Mode Enhancements ---

meta_app = typer.Typer(help="Meta-mode commands for ACE working on itself")
app.add_typer(meta_app, name="meta")


@meta_app.command("self-audit")
def meta_self_audit():
    """ACE performs a self-audit of its own codebase and memory."""
    console.print("🚀 [bold blue]Starting ACE Self-Audit[/bold blue]")
    svc = get_service()
    agents_config = svc.load_agents()
    
    for agent in agents_config.agents:
        console.print(f"Auditing agent: [green]{agent.id}[/green]")
        audit_file = svc.audit_agent(agent.id)
        console.print(f"  Audit SOP generated: [dim]{audit_file}[/dim]")
        
        # Run a specialized self-reflection on the agent's memory
        playbook_path = svc.base_path / agent.memory_file
        if playbook_path.exists():
            content = playbook_path.read_text()
            console.print(f"  Analyzing playbook: [dim]{playbook_path.name}[/dim]")
            # Here we could call an LLM to analyze the playbook for consistency
            # For now, we just report the size and count of strategies
            strategies = re.findall(r"\[str-\d+\]", content)
            pitfalls = re.findall(r"\[mis-\d+\]", content)
            decisions = re.findall(r"\[dec-\d+\]", content)
            console.print(f"    Strategies: {len(strategies)}")
            console.print(f"    Pitfalls: {len(pitfalls)}")
            console.print(f"    Decisions: {len(decisions)}")

    console.print("\n[bold green]Self-Audit complete.[/bold green]")


@meta_app.command("cross-project-export")
def meta_export(
    agent_id: str = typer.Argument(..., help="Agent ID to export learnings from"),
    target_dir: str = typer.Option(".ace-meta/cross-project", "--target", "-t")
):
    """Export learnings for cross-project sharing."""
    svc = get_service()
    target_path = Path(target_dir)
    learnings = svc.export_learnings(agent_id, target_path)
    console.print(f"Exported [bold]{len(learnings)}[/bold] learnings to [blue]{target_path}[/blue]")


@meta_app.command("cross-project-import")
def meta_import(
    source_file: str = typer.Argument(..., help="Path to the exported learnings YAML"),
    agent_id: str = typer.Argument(..., help="Agent ID to import learnings into")
):
    """Import learnings from another project."""
    svc = get_service()
    count = svc.import_learnings(Path(source_file), agent_id)
    console.print(f"Imported [bold]{count}[/bold] learnings into agent [green]{agent_id}[/green]")


@app.command()
def token_stats(
    agent_id: Optional[str] = typer.Option(None, "--agent", "-a", help="Filter by agent ID")
):
    """Track and report token usage per agent/session."""
    svc = get_service()
    usages = svc.get_token_report(agent_id)
    
    if not usages:
        console.print("No token usage data found.")
        return
        
    table = Table(title="Token Consumption Monitoring")
    table.add_column("Agent", style="green")
    table.add_column("Session", style="cyan")
    table.add_column("Prompt", style="yellow")
    table.add_column("Completion", style="yellow")
    table.add_column("Total", style="bold yellow")
    table.add_column("Cost ($)", style="magenta")
    table.add_column("Timestamp", style="dim")
    
    total_tokens = 0
    total_cost = 0.0
    
    for u in usages:
        table.add_row(
            u.agent_id,
            u.session_id[:8],
            str(u.prompt_tokens),
            str(u.completion_tokens),
            str(u.total_tokens),
            f"{u.cost:.4f}",
            u.timestamp
        )
        total_tokens += u.total_tokens
        total_cost += u.cost
        
    console.print(table)
    console.print(f"\n[bold]Grand Total Tokens:[/bold] {total_tokens}")
    console.print(f"[bold]Grand Total Cost:[/bold] ${total_cost:.4f}")


# --- CLI-to-API Bridge ---
API_BASE_URL = os.getenv("ACE_API_URL", "http://localhost:8000")


def api_call(method: str, endpoint: str, **kwargs):
    """Make an API call, fallback to local service if API is unavailable."""
    try:
        url = f"{API_BASE_URL}{endpoint}"
        response = requests.request(method, url, timeout=0.1, **kwargs)
        if response.status_code == 200:
            return response.json()
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
        pass
    return None


# --- CLI Wrappers ---


@app.command()
def init():
    """Initialize .ace/ and .ace-local/ directories."""
    svc = get_service()
    svc.ace_dir.mkdir(parents=True, exist_ok=True)
    svc.ace_local_dir.mkdir(exist_ok=True)

    # Check for GOOGLE_API_KEY
    cred_file = Path.home() / ".ace" / "credentials"
    google_key = os.getenv("GOOGLE_API_KEY")

    if not google_key and cred_file.exists():
        for line in cred_file.read_text().splitlines():
            if line.startswith("GOOGLE_API_KEY="):
                google_key = line.split("=", 1)[1].strip()
                break

    if not google_key:
        console.print("[yellow]GOOGLE_API_KEY not found.[/yellow]")
        google_key = typer.prompt(
            "Please enter your GOOGLE_API_KEY", hide_input=True
        )
        if google_key:
            cred_file.parent.mkdir(parents=True, exist_ok=True)
            # Simple append/update logic
            lines = []
            if cred_file.exists():
                lines = [
                    line for line in cred_file.read_text().splitlines()
                    if not line.startswith("GOOGLE_API_KEY=")
                ]
            lines.append(f"GOOGLE_API_KEY={google_key}")
            cred_file.write_text("\n".join(lines) + "\n")
            os.chmod(cred_file, 0o600)
            console.print(
                f"Saved GOOGLE_API_KEY to [green]{cred_file}[/green]"
            )

    # Check for CURSOR_API_KEY
    cursor_key = os.getenv("CURSOR_API_KEY")
    if not cursor_key and cred_file.exists():
        for line in cred_file.read_text().splitlines():
            if line.startswith("CURSOR_API_KEY="):
                cursor_key = line.split("=", 1)[1].strip()
                break

    if not cursor_key:
        console.print("[yellow]CURSOR_API_KEY not found.[/yellow]")
        cursor_key = typer.prompt(
            "Please enter your CURSOR_API_KEY", hide_input=True
        )
        if cursor_key:
            cred_file.parent.mkdir(parents=True, exist_ok=True)
            lines = []
            if cred_file.exists():
                lines = [
                    line for line in cred_file.read_text().splitlines()
                    if not line.startswith("CURSOR_API_KEY=")
                ]
            lines.append(f"CURSOR_API_KEY={cursor_key}")
            cred_file.write_text("\n".join(lines) + "\n")
            os.chmod(cred_file, 0o600)
            console.print(
                f"Saved CURSOR_API_KEY to [green]{cred_file}[/green]"
            )

    for subdir in ["mail", "sessions", "decisions", "specs"]:
        (svc.ace_dir / subdir).mkdir(parents=True, exist_ok=True)
        console.print(
            f"Created directory: [green]{svc.ace_dir / subdir}[/green]"
        )

    console.print(f"Created directory: [green]{svc.ace_local_dir}[/green]")

    # Initialize files if they don't exist
    if not (svc.ace_dir / "agents.yaml").exists():
        svc.save_agents(svc.load_agents())
    if not (svc.ace_dir / "config.yaml").exists():
        svc.save_config(svc.load_config())
    if not (svc.ace_dir / "ownership.yaml").exists():
        svc.save_ownership(svc.load_ownership())

    svc.cursor_rules_dir.mkdir(parents=True, exist_ok=True)
    console.print(f"Created directory: [green]{svc.cursor_rules_dir}[/green]")
    console.print(
        "[bold green]ACE Orchestrator initialized successfully![/bold green]"
    )


@app.command()
def own(path: str, agent: str):
    """Assign ownership of a path to an agent."""
    res = api_call(
        "POST", "/ownership", json={"path": path, "agent_id": agent}
    )
    if not res:
        get_service().assign_ownership(path, agent)
    console.print(
        f"Assigned [blue]{path}[/blue] to agent [green]{agent}[/green]"
    )


@app.command()
def who(path: str):
    """Find out who owns a path (longest prefix match)."""
    # Fallback to local for read-only if API fails
    owner = get_service().resolve_owner(path)
    if owner:
        console.print(
            f"Path [blue]{path}[/blue] is owned by "
            f"agent [green]{owner}[/green]"
        )
    else:
        console.print(
            f"Path [blue]{path}[/blue] is currently "
            f"[yellow]unowned[/yellow]"
        )


@app.command()
def list_owners():
    """List all ownership assignments."""
    res = api_call("GET", "/ownership")
    config = OwnershipConfig(**res) if res else get_service().load_ownership()
    if not config.modules:
        console.print("No ownership assignments found.")
        return

    table = Table(title="Ownership Registry")
    table.add_column("Path", style="cyan")
    table.add_column("Agent ID", style="green")
    table.add_column("Owned Since", style="magenta")

    for path, module in config.modules.items():
        table.add_row(path, module.agent_id, module.owned_since)
    console.print(table)


agent_app = typer.Typer(help="Agent management commands")
app.add_typer(agent_app, name="agent")


@agent_app.command("create")
def agent_create(
    name: str = typer.Option(..., "--name", "-n", help="Agent name"),
    role: str = typer.Option(..., "--role", "-r", help="Agent role"),
    id: str = typer.Option(..., "--id", "-i", help="Agent unique ID"),
    email: Optional[str] = typer.Option(
        None, "--email", "-e", help="Agent email"
    ),
    responsibilities: Optional[List[str]] = typer.Option(
        None, "--resp", "-p", help="Agent responsibilities"
    ),
):
    """Create a new agent in the registry."""
    res = api_call(
        "POST",
        "/agents",
        json={
            "id": id,
            "name": name,
            "role": role,
            "email": email,
            "responsibilities": responsibilities or [],
        },
    )
    if res:
        console.print(
            f"Created agent [green]{res['name']}[/green] (ID: {res['id']})"
        )
    else:
        try:
            agent = get_service().create_agent(
                id, name, role, email, responsibilities
            )
            console.print(
                f"Created agent [green]{agent.name}[/green] (ID: {agent.id})"
            )
        except ValueError as e:
            console.print(f"[red]Error: {e}[/red]")
            raise typer.Exit(code=1)


@agent_app.command("list")
def agent_list():
    """List all agents in the registry."""
    res = api_call("GET", "/agents")
    agents = res if res else get_service().load_agents().agents
    if not agents:
        console.print("No agents found.")
        return

    table = Table(title="Agent Registry")
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("Role", style="yellow")
    table.add_column("Email", style="blue")

    for agent in agents:
        if isinstance(agent, dict):
            table.add_row(
                agent["id"], agent["name"], agent["role"], agent["email"]
            )
        else:
            table.add_row(agent.id, agent.name, agent.role, agent.email)
    console.print(table)


@agent_app.command("onboard")
def agent_onboard(
    agent_id: str = typer.Argument(..., help="Agent ID to onboard")
):
    """Run onboarding SOP for an agent."""
    res = api_call("POST", f"/agents/{agent_id}/onboard")
    if res:
        console.print(
            f"Onboarding SOP started. File created: "
            f"[green]{res['onboarding_file']}[/green]"
        )
    else:
        try:
            onboarding_file = get_service().onboard_agent(agent_id)
            console.print(
                f"Onboarding SOP started. File created: "
                f"[green]{onboarding_file}[/green]"
            )
        except ValueError as e:
            console.print(f"[red]Error: {e}[/red]")


@agent_app.command("review")
def agent_review(
    pr_id: str = typer.Argument(..., help="PR ID to review"),
    agent_id: str = typer.Option(
        ..., "--agent", "-a", help="Agent ID to perform the review"
    ),
):
    """Run PR review SOP for an agent."""
    res = api_call(
        "POST",
        f"/pr/{pr_id}/review",
        json={"agent_id": agent_id}
    )
    if res:
        console.print(
            f"PR Review SOP started. File created: "
            f"[green]{res['review_file']}[/green]"
        )
    else:
        review_file = get_service().review_pr(pr_id, agent_id)
        console.print(
            f"PR Review SOP started. File created: [green]{review_file}[/green]"
        )


@agent_app.command("audit")
def agent_audit(agent_id: str = typer.Argument(..., help="Agent ID to audit")):
    """Run audit SOP for an agent."""
    res = api_call("POST", f"/agents/{agent_id}/audit")
    if res:
        console.print(
            f"Agent Audit SOP started. File created: "
            f"[green]{res['audit_file']}[/green]"
        )
    else:
        try:
            audit_file = get_service().audit_agent(agent_id)
            console.print(
                f"Agent Audit SOP started. File created: "
                f"[green]{audit_file}[/green]"
            )
        except ValueError as e:
            console.print(f"[red]Error: {e}[/red]")


@agent_app.command("security-audit")
def agent_security_audit(
    agent_id: str = typer.Argument(..., help="Agent ID to perform security audit")
):
    """Run security audit SOP for an agent."""
    res = api_call("POST", f"/agents/{agent_id}/security-audit")
    if res:
        console.print(
            f"Security Audit SOP started. File created: "
            f"[green]{res['security_audit_file']}[/green]"
        )
    else:
        try:
            security_audit_file = get_service().security_audit(agent_id)
            console.print(
                f"Security Audit SOP started. File created: "
                f"[green]{security_audit_file}[/green]"
            )
        except ValueError as e:
            console.print(f"[red]Error: {e}[/red]")


@agent_app.command("propose")
def agent_propose(
    parent_agent_id: str = typer.Argument(..., help="Parent agent ID"),
    new_agent_id: str = typer.Option(..., "--id", "-i", help="New agent ID"),
    new_agent_name: str = typer.Option(..., "--name", "-n", help="New agent name"),
    new_agent_role: str = typer.Option(..., "--role", "-r", help="New agent role"),
    responsibilities: List[str] = typer.Option(..., "--resp", "-p", help="Responsibilities"),
):
    """Propose a new agent for a sub-module."""
    svc = get_service()
    proposal = svc.propose_agent(
        parent_agent_id,
        new_agent_id,
        new_agent_name,
        new_agent_role,
        responsibilities
    )
    console.print(f"Agent proposal created: [green]{proposal.id}[/green]")
    console.print(f"MACP debate initiated for [blue]{new_agent_id}[/blue].")


@agent_app.command("check-expansion")
def agent_check_expansion(
    agent_id: str = typer.Argument(..., help="Agent ID to check for expansion"),
    threshold: int = typer.Option(10, "--threshold", "-t", help="Complexity threshold"),
):
    """Check if an agent's complexity exceeds threshold and propose expansion."""
    svc = get_service()
    sub_agent_id = svc.check_agent_expansion(agent_id, threshold)
    if sub_agent_id:
        console.print(f"Expansion triggered for [blue]{agent_id}[/blue].")
        console.print(f"Proposed sub-agent: [green]{sub_agent_id}[/green]")
    else:
        console.print(f"Agent [blue]{agent_id}[/blue] is within complexity limits.")


@app.command()
def config_tokens(
    mode: TokenMode = typer.Option(
        ..., "--mode", "-m", help="Token consumption mode"
    )
):
    """Set token consumption mode (low/medium/high)."""
    svc = get_service()
    config = svc.load_config()
    config.token_mode = mode
    svc.save_config(config)
    console.print(f"Token mode set to [bold blue]{mode.value}[/bold blue]")


@app.command()
def build_context(
    path: Optional[str] = typer.Option(
        None, "--path", "-p", help="Path to the file or module"
    ),
    task_type: TaskType = typer.Option(
        TaskType.IMPLEMENT, "--task-type", "-t", help="Type of task"
    ),
    agent_id: Optional[str] = typer.Option(
        None, "--agent", "-a", help="Explicit agent ID"
    ),
):
    """Compose the context slice for an agent call."""
    res = api_call(
        "GET",
        "/context",
        params={
            "path": path,
            "task_type": task_type.value,
            "agent_id": agent_id,
        },
    )
    if res:
        context, resolved_agent_id = res["context"], res["agent_id"]
    else:
        context, resolved_agent_id = get_service().build_context(
            path, task_type, agent_id
        )
    console.print(context)
    return context, resolved_agent_id


@app.command()
def run(
    command: str = typer.Argument(..., help="Command to run"),
    path: Optional[str] = typer.Option(
        None, "--path", "-p", help="Path to the file or module"
    ),
    task_type: TaskType = typer.Option(
        TaskType.IMPLEMENT, "--task-type", "-t", help="Type of task"
    ),
    agent_id: Optional[str] = typer.Option(
        None, "--agent", "-a", help="Explicit agent ID"
    ),
):
    """Execute an agent command with ACE context."""
    svc = get_service()
    context, resolved_agent_id = svc.build_context(path, task_type, agent_id)

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False
    ) as tmp:
        tmp.write(context)
        context_file = tmp.name

    console.print(f"Running command: [bold blue]{command}[/bold blue]")
    console.print(f"Context injected from: [dim]{context_file}[/dim]")

    try:
        process = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
        )
        output_lines = []
        for line in process.stdout:
            console.print(line, end="")
            output_lines.append(line)
        process.wait()
        exit_code = process.returncode
        full_output = "".join(output_lines)
    except Exception as e:
        console.print(f"[red]Error executing command: {e}[/red]")
        exit_code = 1
        full_output = str(e)

    session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_file = svc.sessions_dir / f"session_{session_id}.md"
    session_content = f"""# Session {session_id}
- **Command**: `{command}`
- **Path**: `{path}`
- **Agent ID**: `{resolved_agent_id}`
- **Task Type**: `{task_type.value}`
- **Exit Code**: {exit_code}
- **Timestamp**: {datetime.now().isoformat()}

## Context Provided
{context}

## Output
```
{full_output}
```
"""
    session_file.write_text(session_content)
    console.print(f"Session logged to: [green]{session_file}[/green]")

    if exit_code == 0:
        if svc.get_anthropic_client():
            _perform_reflection(session_file)
        else:
            console.print(
                "[yellow]Skipping reflection: "
                "ANTHROPIC_API_KEY not set and not in "
                "~/.ace/credentials.[/yellow]"
            )

    if exit_code != 0:
        raise typer.Exit(code=exit_code)


def _perform_reflection(session_file: Path):
    svc = get_service()
    session_content = session_file.read_text()
    output_match = re.search(
        r"## Output\n```\n(.*?)\n```", session_content, re.DOTALL
    )
    if not output_match:
        console.print(
            "[red]Could not find output section in session log.[/red]"
        )
        return

    reflection_text = svc.reflect_on_session(output_match.group(1))
    console.print("\n[bold]Reflection Output:[/bold]")
    console.print(reflection_text)

    updates = svc.parse_reflection_output(reflection_text)
    if updates:
        agent_id_match = re.search(
            r"- \*\*Agent ID\*\*: `(.*?)`", session_content
        )
        playbook_path = svc.cursor_rules_dir / "_global.mdc"
        if agent_id_match and agent_id_match.group(1) != "None":
            agents_config = svc.load_agents()
            agent = next(
                (
                    a
                    for a in agents_config.agents
                    if a.id == agent_id_match.group(1)
                ),
                None,
            )
            if agent:
                playbook_path = Path(agent.memory_file)

        svc.update_playbook(playbook_path, updates)
    else:
        console.print("[yellow]No new learnings extracted.[/yellow]")


@app.command()
def reflect(
    session_id: Optional[str] = typer.Option(
        None, "--session-id", "-s", help="Session ID to reflect on"
    )
):
    """Reflect on a session and extract learnings."""
    svc = get_service()
    if not session_id:
        res = api_call("GET", "/sessions")
        sessions = res if res else svc.list_sessions()
        if not sessions:
            console.print("[red]No sessions found to reflect on.[/red]")
            return
        session_id = sessions[0]["id"]

    console.print(f"Reflecting on session: [blue]{session_id}[/blue]")

    res = api_call("POST", f"/sessions/{session_id}/reflect")
    if res:
        console.print("\n[bold]Reflection Output:[/bold]")
        console.print(res["reflection"])
        if not res["updates"]:
            console.print("[yellow]No new learnings extracted.[/yellow]")
    else:
        session_file = svc.sessions_dir / f"session_{session_id}.md"
        if not session_file.exists():
            console.print(f"[red]Session {session_id} not found.[/red]")
            return
        _perform_reflection(session_file)


@app.command()
def decision_add(
    title: str = typer.Option(..., "--title", "-t", help="Decision title"),
    context: str = typer.Option(
        ..., "--context", "-c", help="Context for the decision"
    ),
    decision: str = typer.Option(
        ..., "--decision", "-d", help="The decision made"
    ),
    consequences: str = typer.Option(
        ..., "--consequences", "-q", help="Consequences of the decision"
    ),
    status: str = typer.Option(
        "accepted", "--status", "-s", help="Decision status"
    ),
    agent_id: Optional[str] = typer.Option(
        None, "--agent", "-a", help="Agent who made the decision"
    ),
):
    """Add a new Architectural Decision Record (ADR)."""
    svc = get_service()
    res = api_call(
        "POST",
        "/decisions",
        json={
            "title": title,
            "context": context,
            "decision": decision,
            "consequences": consequences,
            "status": status,
            "agent_id": agent_id,
        },
    )
    if res:
        console.print(
            f"Created ADR: "
            f"[green]{svc.decisions_dir / (res['id'] + '.md')}[/green]"
        )
    else:
        adr = svc.add_decision(
            title, context, decision, consequences, status, agent_id
        )
        console.print(
            f"Created ADR: "
            f"[green]{svc.decisions_dir / f'{adr.id}.md'}[/green]"
        )


@app.command()
def decision_list():
    """List all Architectural Decision Records."""
    svc = get_service()
    res = api_call("GET", "/decisions")
    adrs = res if res else svc.list_decisions()

    if not adrs:
        console.print("No ADRs found.")
        return

    table = Table(title="Architectural Decision Records")
    table.add_column("ID", style="cyan")
    table.add_column("Title", style="green")
    table.add_column("Status", style="yellow")
    table.add_column("Date", style="magenta")

    for adr in adrs:
        if isinstance(adr, dict):
            table.add_row(
                adr["id"],
                adr["title"],
                adr["status"],
                adr["created_at"],
            )
        else:
            table.add_row(
                adr.id,
                adr.title,
                adr.status,
                adr.created_at,
            )
    console.print(table)


memory_app = typer.Typer(help="Memory management commands")
app.add_typer(memory_app, name="memory")


@memory_app.command("index")
def memory_index(
    agent_id: str = typer.Argument(..., help="Agent ID to index memory for")
):
    """Index an agent's playbook into vectorized memory."""
    svc = get_service()
    success = svc.index_playbook(agent_id)
    if success:
        console.print(f"Indexed memory for agent [green]{agent_id}[/green]")
    else:
        console.print(f"[red]Failed to index memory for agent {agent_id}.[/red]")


@memory_app.command("search")
def memory_search(
    agent_id: str = typer.Argument(..., help="Agent ID to search memory for"),
    query: str = typer.Argument(..., help="Search query"),
    n: int = typer.Option(3, "--results", "-n", help="Number of results")
):
    """Search vectorized memory for relevant entries."""
    svc = get_service()
    results = svc.search_memory(agent_id, query, n)
    if not results:
        console.print(f"No relevant memory found for query: [italic]{query}[/italic]")
        return

    table = Table(title=f"Memory Search: {query}")
    table.add_column("ID", style="cyan")
    table.add_column("Content", style="green")
    table.add_column("Type", style="yellow")
    
    for res in results:
        table.add_row(res["id"], res["content"], res["metadata"].get("type", "unknown"))
    console.print(table)


@app.command()
def memory_prune(
    agent_id: Optional[str] = typer.Option(
        None, "--agent", "-a", help="Agent ID to prune memory for"
    ),
    threshold: int = typer.Option(
        0, "--threshold", "-t", help="Prune if harmful - helpful > threshold"
    ),
):
    """Archive or remove 'harmful' strategies."""
    res = api_call(
        "POST",
        "/memory/prune",
        params={"agent_id": agent_id, "threshold": threshold},
    )
    svc = get_service()
    if res:
        for aid, count in res.items():
            console.print(f"Pruning memory for agent: [blue]{aid}[/blue]")
            if count > 0:
                console.print(f"  [green]Done.[/green] Pruned {count} items.")
            else:
                console.print(
                    "  [yellow]No items met the pruning threshold.[/yellow]"
                )
    else:
        agents_config = svc.load_agents()
        agents = (
            [a for a in agents_config.agents if a.id == agent_id]
            if agent_id
            else agents_config.agents
        )

        for agent in agents:
            console.print(f"Pruning memory for agent: [blue]{agent.id}[/blue]")
            pruned_count = svc.prune_memory(agent, threshold)
            if pruned_count > 0:
                console.print(
                    f"  [green]Done.[/green] Pruned {pruned_count} items."
                )
            else:
                console.print(
                    "  [yellow]No items met the pruning threshold.[/yellow]"
                )


@app.command()
def memory_sync():
    """Keep AGENTS.md in sync with the Agent Registry and recent Decisions."""
    svc = get_service()
    svc.sync_shared_learnings()
    agents_config = svc.load_agents()
    content = ["# ACE Agents Registry", "", "## Active Agents"]
    if not agents_config.agents:
        content.append("No agents registered.")
    else:
        for agent in agents_config.agents:
            content.append(
                f"### {agent.name} (`{agent.id}`)\n"
                f"- **Role**: {agent.role}\n"
                f"- **Email**: {agent.email}\n"
                f"- **Memory**: `{agent.memory_file}`"
            )
            if agent.responsibilities:
                content.append("- **Responsibilities**:")
                for resp in agent.responsibilities:
                    content.append(f"  - {resp}")
            content.append("")

    content.append("## Recent Architectural Decisions")
    if not svc.decisions_dir.exists():
        content.append("No decisions found.")
    else:
        adrs = sorted(
            list(svc.decisions_dir.glob("ADR-*.md")), reverse=True
        )[:5]
        for adr_path in adrs:
            adr_content = adr_path.read_text()
            title_match = re.search(r"# (ADR-\d+: .*)", adr_content)
            status_match = re.search(r"- \*\*Status\*\*: (.*)", adr_content)
            title = (
                title_match.group(1)
                if title_match
                else adr_path.name
            )
            status = (
                status_match.group(1)
                if status_match
                else "unknown"
            )
            content.append(f"- **{title}** [{status}]")

    Path("AGENTS.md").write_text("\n".join(content))
    console.print("Updated [green]AGENTS.md[/green]")


@app.command()
def loop(
    prompt: str = typer.Argument(..., help="The prompt to solve"),
    test_cmd: str = typer.Option(
        ..., "--test", "-t", help="Command to run tests"
    ),
    max_iterations: int = typer.Option(
        10, "--max", "-m", help="Maximum number of iterations"
    ),
    path: Optional[str] = typer.Option(
        None, "--path", "-p", help="Path to the file or module"
    ),
    agent_id: Optional[str] = typer.Option(
        None, "--agent", "-a", help="Explicit agent ID"
    ),
    git_commit: bool = typer.Option(
        False, "--git-commit", "-g", help="Automatically commit on success"
    ),
):
    """
    Iteratively run: Context Refresh -> Execute -> Verify -> Reflect -> Repeat.
    """
    console.print("🚀 [bold blue]Starting RALPH Loop[/bold blue]")
    console.print(f"Prompt: [italic]{prompt}[/italic]")
    console.print(f"Test Command: [italic]{test_cmd}[/italic]")
    console.print(f"Max Iterations: [bold]{max_iterations}[/bold]")

    svc = get_service()
    
    # Check for API keys
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    if not anthropic_key:
        # Try to load from credentials
        cred_file = Path.home() / ".ace" / "credentials"
        if cred_file.exists():
            for line in cred_file.read_text().splitlines():
                if line.startswith("ANTHROPIC_API_KEY="):
                    anthropic_key = line.split("=", 1)[1].strip()
                    os.environ["ANTHROPIC_API_KEY"] = anthropic_key
                    break
    
    if not anthropic_key:
        console.print("[yellow]Warning: ANTHROPIC_API_KEY not set. Reflection will be skipped.[/yellow]")

    # Check for CURSOR_API_KEY
    cursor_key = os.getenv("CURSOR_API_KEY")
    if not cursor_key:
        cred_file = Path.home() / ".ace" / "credentials"
        if cred_file.exists():
            for line in cred_file.read_text().splitlines():
                if line.startswith("CURSOR_API_KEY="):
                    cursor_key = line.split("=", 1)[1].strip()
                    os.environ["CURSOR_API_KEY"] = cursor_key
                    break

    # Use the service to run the loop
    success, iterations = svc.run_loop(
        prompt, test_cmd, max_iterations, path, agent_id, git_commit
    )

    if success:
        console.print(
            f"\n✅ [bold green]RALPH Loop completed successfully in "
            f"{iterations} iterations![/bold green]"
        )
    else:
        console.print(
            f"\n❌ [bold red]RALPH Loop failed after "
            f"{iterations} iterations.[/bold red]"
        )
        raise typer.Exit(code=1)


@app.command()
def mail_send(
    to: str = typer.Option(..., "--to", "-t", help="Recipient agent ID"),
    sender: str = typer.Option(..., "--from", "-f", help="Sender agent ID"),
    subject: str = typer.Option(..., "--subject", "-s", help="Subject"),
    body: str = typer.Option(..., "--body", "-b", help="Body"),
):
    """Send a message to another agent."""
    res = api_call(
        "POST",
        "/mail",
        json={
            "to_agent": to,
            "from_agent": sender,
            "subject": subject,
            "body": body,
        },
    )
    if not res:
        get_service().send_mail(to, sender, subject, body)
    console.print(
        f"Message sent from [blue]{sender}[/blue] to [green]{to}[/green]"
    )


@app.command()
def mail_list(agent_id: str):
    """List messages in an agent's inbox."""
    res = api_call("GET", f"/mail/{agent_id}")
    svc = get_service()
    messages = res if res else svc.list_mail(agent_id)

    if not messages:
        console.print(f"No mail for agent [blue]{agent_id}[/blue]")
        return

    table = Table(title=f"Inbox: {agent_id}")
    table.add_column("ID", style="cyan")
    table.add_column("From", style="green")
    table.add_column("Subject", style="yellow")
    table.add_column("Status", style="magenta")

    for msg in messages:
        if isinstance(msg, dict):
            table.add_row(
                msg["id"], msg["from"], msg["subject"], msg["status"]
            )
        else:
            table.add_row(msg.id, msg.from_agent, msg.subject, msg.status)
    console.print(table)


@app.command()
def mail_read(agent_id: str, msg_id: str):
    """Read a specific message."""
    res = api_call("GET", f"/mail/{agent_id}/{msg_id}")
    svc = get_service()
    data = res if res else svc.read_mail(agent_id, msg_id)

    if not data:
        console.print(f"Message [red]{msg_id}[/red] not found.")
        return

    if isinstance(data, dict):
        from_val = data["from"]
        subject_val = data["subject"]
        timestamp_val = data["timestamp"]
        body_val = data["body"]
    else:
        from_val = data.from_agent
        subject_val = data.subject
        timestamp_val = data.timestamp
        body_val = data.body

    console.print(
        f"\n[bold]From:[/bold] {from_val}\n"
        f"[bold]Subject:[/bold] {subject_val}\n"
        f"[bold]Date:[/bold] {timestamp_val}\n"
        f"{'-' * 20}\n{body_val}\n{'-' * 20}"
    )


@app.command()
def debate(
    proposal_id: Optional[str] = typer.Argument(None, help="The MACP proposal ID to debate"),
    agents: List[str] = typer.Option(
        ..., "--agent", "-a", help="Agents to participate"
    ),
    turns: int = typer.Option(
        3, "--turns", "-t", help="Number of debate turns"
    ),
    proposal: Optional[str] = typer.Option(
        None, "--proposal", help="Legacy proposal content (alias for proposal_id)"
    ),
):
    """Initiate and mediate a multi-turn debate for an MACP proposal."""
    if proposal and not proposal_id:
        proposal_id = proposal

    if not proposal_id:
        console.print("[red]Error: Missing argument 'PROPOSAL_ID' or option '--proposal'.[/red]")
        raise typer.Exit(code=1)

    console.print(
        f"🚀 [bold blue]Initiating {turns}-turn debate on MACP proposal:"
        f"[/bold blue] {proposal_id}"
    )
    console.print(f"Participants: {', '.join(agents)}")

    res = api_call(
        "POST",
        f"/macp/{proposal_id}/debate",
        json={"agent_ids": agents, "turns": turns},
    )
    if res:
        consensus = res["consensus"]
    else:
        svc = get_service()
        with console.status("[bold green]Mediating debate..."):
            consensus = svc.debate(proposal_id, agents, turns)

    console.print("\n[bold]Consensus / Recommendation:[/bold]")
    console.print(consensus)


macp_app = typer.Typer(help="Multi-Agent Consensus Protocol (MACP) commands")
app.add_typer(macp_app, name="macp")


@macp_app.command("propose")
def macp_propose(
    title: str = typer.Option(..., "--title", "-t", help="Proposal title"),
    description: str = typer.Option(..., "--desc", "-d", help="Proposal description"),
    proposer: str = typer.Option(..., "--from", "-f", help="Proposer agent ID"),
    agents: List[str] = typer.Option(..., "--agent", "-a", help="Agents to participate"),
):
    """Create a new MACP proposal."""
    svc = get_service()
    proposal = svc.create_macp_proposal(proposer, title, description, agents)
    console.print(f"Created MACP Proposal: [green]{proposal.id}[/green]")


@macp_app.command("list")
def macp_list():
    """List all MACP proposals."""
    svc = get_service()
    proposals = svc.list_macp_proposals()
    if not proposals:
        console.print("No MACP proposals found.")
        return

    table = Table(title="MACP Proposals")
    table.add_column("ID", style="cyan")
    table.add_column("Title", style="green")
    table.add_column("Proposer", style="yellow")
    table.add_column("Status", style="magenta")
    table.add_column("Turns", style="dim")

    for p in proposals:
        table.add_row(p.id, p.title, p.proposer_id, p.status.value, str(p.turns_remaining))
    console.print(table)


@macp_app.command("show")
def macp_show(proposal_id: str = typer.Argument(..., help="Proposal ID")):
    """Show details of an MACP proposal."""
    svc = get_service()
    p = svc.get_macp_proposal(proposal_id)
    if not p:
        console.print(f"[red]Proposal {proposal_id} not found.[/red]")
        return

    console.print(f"\n[bold]MACP Proposal: {p.title} ({p.id})[/bold]")
    console.print(f"Status: [yellow]{p.status.value}[/yellow]")
    console.print(f"Proposer: [green]{p.proposer_id}[/green]")
    console.print(f"\n[bold]Description:[/bold]\n{p.description}")
    
    if p.votes:
        console.print("\n[bold]Votes:[/bold]")
        for aid, vote in p.votes.items():
            console.print(f"- {aid}: {vote}")
            
    if p.consensus_summary:
        console.print(f"\n[bold]Consensus Summary:[/bold]\n{p.consensus_summary}")


@macp_app.command("finalize")
def macp_finalize(proposal_id: str = typer.Argument(..., help="Proposal ID")):
    """Finalize an MACP proposal and reach a consensus."""
    svc = get_service()
    with console.status("[bold green]Finalizing consensus..."):
        consensus = svc.finalize_macp(proposal_id)
    console.print("\n[bold]Consensus reached:[/bold]")
    console.print(consensus)


ui_app = typer.Typer(help="UI integration commands")
app.add_typer(ui_app, name="ui")


@ui_app.command("mockup")
def ui_mockup(
    description: str = typer.Argument(
        ..., help="Description of the UI to mockup"
    ),
    agent_id: str = typer.Option(
        ..., "--agent", "-a", help="Agent to handle the mockup"
    ),
):
    """Generate a UI mockup."""
    console.print(
        f"Generating UI mockup for: [bold]{description}[/bold] "
        f"using agent [green]{agent_id}[/green]"
    )
    res = api_call(
        "POST",
        "/ui/mockup",
        json={"description": description, "agent_id": agent_id},
    )
    if res:
        url = res["url"]
    else:
        url = get_service().ui_mockup(description, agent_id)
    console.print(f"Mockup generated at: [blue]{url}[/blue]")


@ui_app.command("sync")
def ui_sync(
    url: str = typer.Argument(..., help="Stitch Canvas URL to sync from")
):
    """Sync UI code from Google Stitch."""
    console.print(f"Syncing UI code from: [blue]{url}[/blue]")
    res = api_call("GET", "/ui/sync", params={"url": url})
    if res:
        code = res["code"]
    else:
        code = get_service().ui_sync(url)
    console.print(f"Code synced successfully:\n[dim]{code}[/dim]")


spec_app = typer.Typer(help="Living Specs management commands")
app.add_typer(spec_app, name="spec")


@spec_app.command("create")
def spec_create(
    id: str = typer.Argument(..., help="Spec ID (e.g., auth-v2)"),
    title: str = typer.Option(..., "--title", "-t", help="Spec title"),
    intent: str = typer.Option(..., "--intent", "-i", help="Primary intent"),
    constraints: List[str] = typer.Option(
        None, "--constraint", "-c", help="Constraints (can be multiple)"
    ),
):
    """Create a new Living Spec."""
    svc = get_service()
    spec = svc.create_spec(id, title, intent, constraints)
    console.print(f"Created Living Spec: [green]{spec.id}[/green]")


@spec_app.command("list")
def spec_list():
    """List all Living Specs."""
    svc = get_service()
    specs = svc.list_specs()
    if not specs:
        console.print("No Living Specs found.")
        return

    table = Table(title="Living Specs")
    table.add_column("ID", style="cyan")
    table.add_column("Title", style="green")
    table.add_column("Status", style="yellow")
    table.add_column("Updated", style="magenta")

    for spec in specs:
        table.add_row(spec.id, spec.title, spec.status, spec.updated_at)
    console.print(table)


@spec_app.command("show")
def spec_show(id: str = typer.Argument(..., help="Spec ID")):
    """Show details of a Living Spec."""
    svc = get_service()
    spec = svc.get_spec(id)
    if not spec:
        console.print(f"[red]Spec {id} not found.[/red]")
        return

    console.print(f"\n[bold]Living Spec: {spec.title} ({spec.id})[/bold]")
    console.print(f"Status: [yellow]{spec.status}[/yellow]")
    console.print(f"Updated: [dim]{spec.updated_at}[/dim]")
    console.print(f"\n[bold]Intent:[/bold]\n{spec.intent}")
    console.print("\n[bold]Constraints:[/bold]")
    for c in spec.constraints:
        console.print(f"- {c}")
    
    if spec.implementation:
        console.print(
            f"\n[bold]Implementation:[/bold]\n{spec.implementation}"
        )
    if spec.verification:
        console.print(
            f"\n[bold]Verification:[/bold]\n{spec.verification}"
        )


@spec_app.command("update")
def spec_update(
    id: str = typer.Argument(..., help="Spec ID"),
    status: Optional[str] = typer.Option(None, "--status", "-s"),
    implementation: Optional[str] = typer.Option(None, "--impl", "-m"),
    verification: Optional[str] = typer.Option(None, "--verify", "-v"),
):
    """Update an existing Living Spec."""
    svc = get_service()
    spec = svc.get_spec(id)
    if not spec:
        console.print(f"[red]Spec {id} not found.[/red]")
        return

    if status:
        spec.status = status
    if implementation:
        spec.implementation = implementation
    if verification:
        spec.verification = verification

    svc.save_spec(spec)
    console.print(f"Updated Living Spec: [green]{spec.id}[/green]")


@app.command()
def subscribe(
    agent_id: str = typer.Argument(..., help="Agent ID to subscribe"),
    path: str = typer.Argument(..., help="Path or module to subscribe to"),
):
    """Subscribe an agent to changes in a specific module or path."""
    svc = get_service()
    success = svc.subscribe(agent_id, path)
    if success:
        console.print(
            f"Agent [green]{agent_id}[/green] subscribed to [blue]{path}[/blue]"
        )
    else:
        console.print(
            f"Agent [green]{agent_id}[/green] is already subscribed to [blue]{path}[/blue]"
        )


if __name__ == "__main__":
    app()
