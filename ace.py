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


def save_ownership(config: OwnershipConfig):
    service.save_ownership(config)


def load_config():
    return service.load_config()


def load_agents():
    return service.load_agents()


def parse_reflection_output(text: str):
    return service.parse_reflection_output(text)


def update_playbook(playbook_path: Path, updates: List[Dict]):
    return service.update_playbook(playbook_path, updates)


# --- CLI-to-API Bridge ---
API_BASE_URL = os.getenv("ACE_API_URL", "http://localhost:8000")


def api_call(method: str, endpoint: str, **kwargs):
    """Make an API call, fallback to local service if API is unavailable."""
    try:
        url = f"{API_BASE_URL}{endpoint}"
        response = requests.request(method, url, timeout=2, **kwargs)
        if response.status_code == 200:
            return response.json()
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
        pass
    return None


# --- CLI Wrappers ---


@app.command()
def init():
    """Initialize .ace/ and .ace-local/ directories."""
    service.ace_dir.mkdir(parents=True, exist_ok=True)
    service.ace_local_dir.mkdir(exist_ok=True)

    for subdir in ["mail", "sessions", "decisions"]:
        (service.ace_dir / subdir).mkdir(parents=True, exist_ok=True)
        console.print(f"Created directory: [green]{service.ace_dir / subdir}[/green]")

    console.print(f"Created directory: [green]{service.ace_local_dir}[/green]")

    # Initialize files if they don't exist
    if not (service.ace_dir / "agents.yaml").exists():
        service.save_agents(service.load_agents())
    if not (service.ace_dir / "config.yaml").exists():
        service.save_config(service.load_config())
    if not (service.ace_dir / "ownership.yaml").exists():
        service.save_ownership(service.load_ownership())

    service.cursor_rules_dir.mkdir(parents=True, exist_ok=True)
    console.print(f"Created directory: [green]{service.cursor_rules_dir}[/green]")
    console.print("[bold green]ACE Orchestrator initialized successfully![/bold green]")


@app.command()
def own(path: str, agent: str):
    """Assign ownership of a path to an agent."""
    res = api_call("POST", "/ownership", params={"path": path, "agent_id": agent})
    if not res:
        service.assign_ownership(path, agent)
    console.print(f"Assigned [blue]{path}[/blue] to agent [green]{agent}[/green]")


@app.command()
def who(path: str):
    """Find out who owns a path (longest prefix match)."""
    # Fallback to local for read-only if API fails
    owner = service.resolve_owner(path)
    if owner:
        console.print(f"Path [blue]{path}[/blue] is owned by agent [green]{owner}[/green]")
    else:
        console.print(f"Path [blue]{path}[/blue] is currently [yellow]unowned[/yellow]")


@app.command()
def list_owners():
    """List all ownership assignments."""
    res = api_call("GET", "/ownership")
    config = OwnershipConfig(**res) if res else service.load_ownership()
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
    email: Optional[str] = typer.Option(None, "--email", "-e", help="Agent email"),
):
    """Create a new agent in the registry."""
    res = api_call("POST", "/agents", params={"id": id, "name": name, "role": role, "email": email})
    if res:
        console.print(f"Created agent [green]{res['name']}[/green] (ID: {res['id']})")
    else:
        try:
            agent = service.create_agent(id, name, role, email)
            console.print(f"Created agent [green]{agent.name}[/green] (ID: {agent.id})")
        except ValueError as e:
            console.print(f"[red]Error: {e}[/red]")
            raise typer.Exit(code=1)


@agent_app.command("list")
def agent_list():
    """List all agents in the registry."""
    res = api_call("GET", "/agents")
    agents = res if res else service.load_agents().agents
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
            table.add_row(agent["id"], agent["name"], agent["role"], agent["email"])
        else:
            table.add_row(agent.id, agent.name, agent.role, agent.email)
    console.print(table)


@agent_app.command("onboard")
def agent_onboard(agent_id: str = typer.Argument(..., help="Agent ID to onboard")):
    """Run onboarding SOP for an agent."""
    try:
        onboarding_file = service.onboard_agent(agent_id)
        console.print(f"Onboarding SOP started. File created: [green]{onboarding_file}[/green]")
    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")


@agent_app.command("review")
def agent_review(
    pr_id: str = typer.Argument(..., help="PR ID to review"),
    agent_id: str = typer.Option(..., "--agent", "-a", help="Agent ID to perform the review"),
):
    """Run PR review SOP for an agent."""
    review_file = service.review_pr(pr_id, agent_id)
    console.print(f"PR Review SOP started. File created: [green]{review_file}[/green]")


@app.command()
def config_tokens(mode: TokenMode = typer.Option(..., "--mode", "-m", help="Token consumption mode")):
    """Set token consumption mode (low/medium/high)."""
    config = service.load_config()
    config.token_mode = mode
    service.save_config(config)
    console.print(f"Token mode set to [bold blue]{mode.value}[/bold blue]")


@app.command()
def build_context(
    path: Optional[str] = typer.Option(None, "--path", "-p", help="Path to the file or module"),
    task_type: TaskType = typer.Option(TaskType.IMPLEMENT, "--task-type", "-t", help="Type of task"),
    agent_id: Optional[str] = typer.Option(None, "--agent", "-a", help="Explicit agent ID"),
):
    """Compose the context slice for an agent call."""
    res = api_call("GET", "/context", params={"path": path, "task_type": task_type.value, "agent_id": agent_id})
    if res:
        context, resolved_agent_id = res["context"], res["agent_id"]
    else:
        context, resolved_agent_id = service.build_context(path, task_type, agent_id)
    console.print(context)
    return context, resolved_agent_id


@app.command()
def run(
    command: str = typer.Argument(..., help="Command to run"),
    path: Optional[str] = typer.Option(None, "--path", "-p", help="Path to the file or module"),
    task_type: TaskType = typer.Option(TaskType.IMPLEMENT, "--task-type", "-t", help="Type of task"),
    agent_id: Optional[str] = typer.Option(None, "--agent", "-a", help="Explicit agent ID"),
):
    """Execute an agent command with ACE context."""
    context, resolved_agent_id = service.build_context(path, task_type, agent_id)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as tmp:
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
    session_file = service.sessions_dir / f"session_{session_id}.md"
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
        if os.getenv("ANTHROPIC_API_KEY"):
            _perform_reflection(session_file)
        else:
            console.print("[yellow]Skipping reflection: ANTHROPIC_API_KEY not set.[/yellow]")

    if exit_code != 0:
        raise typer.Exit(code=exit_code)


def _perform_reflection(session_file: Path):
    session_content = session_file.read_text()
    output_match = re.search(r"## Output\n```\n(.*?)\n```", session_content, re.DOTALL)
    if not output_match:
        console.print("[red]Could not find output section in session log.[/red]")
        return

    reflection_text = service.reflect_on_session(output_match.group(1))
    console.print("\n[bold]Reflection Output:[/bold]")
    console.print(reflection_text)

    updates = service.parse_reflection_output(reflection_text)
    if updates:
        agent_id_match = re.search(r"- \*\*Agent ID\*\*: `(.*?)`", session_content)
        playbook_path = service.cursor_rules_dir / "_global.mdc"
        if agent_id_match and agent_id_match.group(1) != "None":
            agents_config = service.load_agents()
            agent = next((a for a in agents_config.agents if a.id == agent_id_match.group(1)), None)
            if agent:
                playbook_path = Path(agent.memory_file)

        service.update_playbook(playbook_path, updates)
    else:
        console.print("[yellow]No new learnings extracted.[/yellow]")


@app.command()
def reflect(session_id: Optional[str] = typer.Option(None, "--session-id", "-s", help="Session ID to reflect on")):
    """Reflect on a session and extract learnings."""
    if not session_id:
        res = api_call("GET", "/sessions")
        sessions = res if res else service.list_sessions()
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
        session_file = service.sessions_dir / f"session_{session_id}.md"
        if not session_file.exists():
            console.print(f"[red]Session {session_id} not found.[/red]")
            return
        _perform_reflection(session_file)


@app.command()
def decision_add(
    title: str = typer.Option(..., "--title", "-t", help="Decision title"),
    context: str = typer.Option(..., "--context", "-c", help="Context for the decision"),
    decision: str = typer.Option(..., "--decision", "-d", help="The decision made"),
    consequences: str = typer.Option(..., "--consequences", "-q", help="Consequences of the decision"),
    status: str = typer.Option("accepted", "--status", "-s", help="Decision status"),
    agent_id: Optional[str] = typer.Option(None, "--agent", "-a", help="Agent who made the decision"),
):
    """Add a new Architectural Decision Record (ADR)."""
    res = api_call(
        "POST",
        "/decisions",
        params={
            "title": title,
            "context": context,
            "decision": decision,
            "consequences": consequences,
            "status": status,
            "agent_id": agent_id,
        },
    )
    if res:
        console.print(f"Created ADR: [green]{service.decisions_dir / f'{res['id']}.md'}[/green]")
    else:
        adr = service.add_decision(title, context, decision, consequences, status, agent_id)
        console.print(f"Created ADR: [green]{service.decisions_dir / f'{adr.id}.md'}[/green]")


@app.command()
def decision_list():
    """List all Architectural Decision Records."""
    res = api_call("GET", "/decisions")
    adrs = res if res else service.list_decisions()
    
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


@app.command()
def memory_prune(
    agent_id: Optional[str] = typer.Option(None, "--agent", "-a", help="Agent ID to prune memory for"),
    threshold: int = typer.Option(0, "--threshold", "-t", help="Prune if harmful - helpful > threshold"),
):
    """Archive or remove 'harmful' strategies."""
    res = api_call("POST", "/memory/prune", params={"agent_id": agent_id, "threshold": threshold})
    if res:
        for aid, count in res.items():
            console.print(f"Pruning memory for agent: [blue]{aid}[/blue]")
            if count > 0:
                console.print(f"  [green]Done.[/green] Pruned {count} items.")
            else:
                console.print("  [yellow]No items met the pruning threshold.[/yellow]")
    else:
        agents_config = service.load_agents()
        agents = [a for a in agents_config.agents if a.id == agent_id] if agent_id else agents_config.agents

        for agent in agents:
            console.print(f"Pruning memory for agent: [blue]{agent.id}[/blue]")
            pruned_count = service.prune_memory(agent, threshold)
            if pruned_count > 0:
                console.print(f"  [green]Done.[/green] Pruned {pruned_count} items.")
            else:
                console.print("  [yellow]No items met the pruning threshold.[/yellow]")


@app.command()
def memory_sync():
    """Keep AGENTS.md in sync with the Agent Registry and recent Decisions."""
    agents_config = service.load_agents()
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
    if not service.decisions_dir.exists():
        content.append("No decisions found.")
    else:
        adrs = sorted(list(service.decisions_dir.glob("ADR-*.md")), reverse=True)[:5]
        for adr_path in adrs:
            adr_content = adr_path.read_text()
            title_match = re.search(r"# (ADR-\d+: .*)", adr_content)
            status_match = re.search(r"- \*\*Status\*\*: (.*)", adr_content)
            content.append(
                f"- **{title_match.group(1) if title_match else adr_path.name}** "
                f"[{status_match.group(1) if status_match else 'unknown'}]"
            )

    Path("AGENTS.md").write_text("\n".join(content))
    console.print("Updated [green]AGENTS.md[/green]")


@app.command()
def loop(
    prompt: str = typer.Argument(..., help="The prompt to solve"),
    test_cmd: str = typer.Option(..., "--test", "-t", help="Command to run tests"),
    max_iterations: int = typer.Option(10, "--max", "-m", help="Maximum number of iterations"),
    path: Optional[str] = typer.Option(None, "--path", "-p", help="Path to the file or module"),
    agent_id: Optional[str] = typer.Option(None, "--agent", "-a", help="Explicit agent ID"),
):
    """Iteratively run: Context Refresh -> Execute -> Verify -> Reflect -> Repeat."""
    console.print("🚀 [bold blue]Starting RALPH Loop[/bold blue]")
    console.print(f"Prompt: [italic]{prompt}[/italic]")
    console.print(f"Test Command: [italic]{test_cmd}[/italic]")
    console.print(f"Max Iterations: [bold]{max_iterations}[/bold]")

    iteration = 0
    while iteration < max_iterations:
        iteration += 1
        console.print(f"\n[bold]=== Iteration {iteration}/{max_iterations} ===[/bold]")

        # 1. Build Context
        context, resolved_agent_id = service.build_context(path, TaskType.IMPLEMENT, agent_id)

        # 2. Execute agent (Mocking cursor-agent call for now, as it's a CLI tool)
        # In a real scenario, this would call 'ace run' or similar logic
        console.print("Building next task...")
        # Since we are an agent, we can't easily call cursor-agent from within ourselves
        # but we can simulate the execution logic.
        
        # 3. Verify (Run tests)
        console.print(f"Verifying implementation with: [italic]{test_cmd}[/italic]")
        result = subprocess.run(test_cmd, shell=True, capture_output=True, text=True)
        
        if result.returncode == 0:
            console.print("✅ [bold green]Verification successful![/bold green]")
            break
        else:
            console.print(f"❌ [bold red]Verification failed (Exit code: {result.returncode})[/bold red]")
            console.print(result.stdout)
            console.print(result.stderr)
            # 4. Reflect (In a real scenario, we'd pass the error to the agent)
            # For now, we'll just log it and continue
            
    if iteration >= max_iterations:
        console.print(f"Reached maximum iterations ({max_iterations}). Stopping.")


@app.command()
def mail_send(
    to: str = typer.Option(..., "--to", "-t", help="Recipient agent ID"),
    sender: str = typer.Option(..., "--from", "-f", help="Sender agent ID"),
    subject: str = typer.Option(..., "--subject", "-s", help="Subject"),
    body: str = typer.Option(..., "--body", "-b", help="Body"),
):
    """Send a message to another agent."""
    res = api_call("POST", "/mail", params={"to_agent": to, "from_agent": sender, "subject": subject, "body": body})
    if not res:
        service.send_mail(to, sender, subject, body)
    console.print(f"Message sent from [blue]{sender}[/blue] to [green]{to}[/green]")


@app.command()
def mail_list(agent_id: str):
    """List messages in an agent's inbox."""
    res = api_call("GET", f"/mail/{agent_id}")
    messages = res if res else service.list_mail(agent_id)
    
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
            table.add_row(msg["id"], msg["from"], msg["subject"], msg["status"])
        else:
            table.add_row(msg.id, msg.from_agent, msg.subject, msg.status)
    console.print(table)


@app.command()
def mail_read(agent_id: str, msg_id: str):
    """Read a specific message."""
    res = api_call("GET", f"/mail/{agent_id}/{msg_id}")
    data = res if res else service.read_mail(agent_id, msg_id)
    
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
    proposal: str = typer.Option(..., "--proposal", "-p", help="The proposal to debate"),
    agents: List[str] = typer.Option(..., "--agent", "-a", help="Agents to participate"),
):
    """Initiate a debate between multiple agents."""
    for agent_id in agents:
        service.send_mail(
            agent_id, "orchestrator", "DEBATE PROPOSAL", f"Please review and debate the following proposal: {proposal}"
        )
    console.print(f"Proposal sent to participants: {', '.join(agents)}")


ui_app = typer.Typer(help="UI integration commands")
app.add_typer(ui_app, name="ui")


@ui_app.command("mockup")
def ui_mockup(
    description: str = typer.Argument(..., help="Description of the UI to mockup"),
    agent_id: str = typer.Option(..., "--agent", "-a", help="Agent to handle the mockup"),
):
    """Generate a UI mockup."""
    console.print(f"Generating UI mockup for: [bold]{description}[/bold] using agent [green]{agent_id}[/green]")
    url = service.ui_mockup(description, agent_id)
    console.print(f"Mockup generated at: [blue]{url}[/blue]")


@ui_app.command("sync")
def ui_sync(url: str = typer.Argument(..., help="Stitch Canvas URL to sync from")):
    """Sync UI code from Google Stitch."""
    console.print(f"Syncing UI code from: [blue]{url}[/blue]")
    code = service.ui_sync(url)
    console.print(f"Code synced successfully:\n[dim]{code}[/dim]")


if __name__ == "__main__":
    app()
