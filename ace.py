import typer
from pathlib import Path
import os
from datetime import datetime
from typing import Optional, List, Dict
from enum import Enum
from pydantic import BaseModel, Field
from rich.console import Console
from rich.table import Table
from ruamel.yaml import YAML
import subprocess
import tempfile
import anthropic
import re

app = typer.Typer(no_args_is_help=True)
console = Console()
yaml = YAML()
yaml.preserve_quotes = True

# --- Reflection Engine (Phase 2.1) ---

REFLECTION_PROMPT = """You are an ACE Reflection Engine. Your task is to analyze the output of a coding agent session and extract structured learnings.

Look for:
1. **Strategies [str-XXX]**: Successful patterns, helpful libraries, or effective approaches.
2. **Pitfalls [mis-XXX]**: Bugs encountered, harmful patterns, or things to avoid.
3. **Decisions [dec-XXX]**: Architectural choices made during the task.

Format your output EXACTLY as follows:
[str-NEW] helpful=1 harmful=0 :: <description of the strategy>
[mis-NEW] helpful=0 harmful=1 :: <description of the pitfall>
[dec-NEW] :: <description of the decision>

Only include items that are clearly supported by the session output. If no new learnings are found, return "No new learnings."

Session Output:
{session_output}
"""

def get_anthropic_client():
    """Initialize and return the Anthropic client."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        console.print("[red]Error: ANTHROPIC_API_KEY environment variable not set.[/red]")
        raise typer.Exit(code=1)
    return anthropic.Anthropic(api_key=api_key)

def reflect_on_session(session_output: str) -> str:
    """Use Claude to extract learnings from session output."""
    client = get_anthropic_client()

    prompt = REFLECTION_PROMPT.format(session_output=session_output)

    try:
        message = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1024,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        # Extract text from the response
        if isinstance(message.content, list):
            return "".join([
                block.text for block in message.content
                if hasattr(block, 'text')
            ])
        return str(message.content)
    except Exception as e:
        console.print(f"[red]Error during reflection: {e}[/red]")
        return "Error during reflection."

@app.command()
def reflect(
    session_id: Optional[str] = typer.Option(
        None,
        "--session-id",
        "-s",
        help="Session ID to reflect on"
    )
):
    """Reflect on a session and extract learnings."""
    sessions_dir = Path(".ace/sessions")
    if not session_id:
        # Get most recent session
        session_files = sorted(
            list(sessions_dir.glob("*.md")),
            key=lambda x: x.stat().st_mtime,
            reverse=True
        )
        if not session_files:
            console.print("[red]No sessions found to reflect on.[/red]")
            return
        session_file = session_files[0]
    else:
        session_file = sessions_dir / f"session_{session_id}.md"
        if not session_file.exists():
            console.print(f"[red]Session {session_id} not found.[/red]")
            return

    console.print(f"Reflecting on session: [blue]{session_file.name}[/blue]")
    session_content = session_file.read_text()

    # Extract the Output section from the session log
    output_match = re.search(
        r"## Output\n```\n(.*?)\n```",
        session_content,
        re.DOTALL
    )
    if not output_match:
        console.print("[red]Could not find output section in session log.[/red]")
        return

    session_output = output_match.group(1)
    reflection_text = reflect_on_session(session_output)

    console.print("\n[bold]Reflection Output:[/bold]")
    console.print(reflection_text)

    # Parse and update playbooks
    updates = parse_reflection_output(reflection_text)
    if updates:
        # For now, we update the agent associated with the session
        # We can extract the path from the session log to find the agent
        path_match = re.search(r"- \*\*Path\*\*: `(.*?)`", session_content)
        path = path_match.group(1) if path_match else None

        if path and path != "None":
            # Find agent for this path
            ownership = load_ownership()
            best_match_len = -1
            resolved_agent_id = None
            for module_path in ownership.modules:
                if path.startswith(module_path):
                    if len(module_path) > best_match_len:
                        best_match_len = len(module_path)
                        resolved_agent_id = ownership.modules[
                            module_path
                        ].agent_id

            if resolved_agent_id:
                agents_config = load_agents()
                agent = next(
                    (a for a in agents_config.agents if a.id == resolved_agent_id),
                    None
                )
                if agent:
                    playbook_path = Path(agent.memory_file)
                    update_playbook(playbook_path, updates)
                else:
                    console.print(
                        f"[yellow]Agent {resolved_agent_id} not found.[/yellow]"
                    )
            else:
                console.print(
                    "[yellow]No agent found for path. Skipping update.[/yellow]"
                )
        else:
            console.print(
                "[yellow]No path found. Skipping playbook update.[/yellow]"
            )
    else:
        console.print("[yellow]No new learnings extracted.[/yellow]")

# --- Delta Update Parser (Phase 2.2) ---

def parse_reflection_output(reflection_text: str) -> List[Dict]:
    """Parse structured reflection output into a list of update dicts."""
    updates = []
    # Regex to match [type-ID] helpful=X harmful=Y :: description
    pattern = r"\[(str|mis|dec)-([^\]]+)\](?:\s+helpful=(\d+)\s+harmful=(\d+))?\s*::\s*(.*)"
    
    for line in reflection_text.splitlines():
        match = re.search(pattern, line)
        if match:
            update_type = match.group(1)
            update_id = match.group(2)
            helpful = int(match.group(3)) if match.group(3) else 0
            harmful = int(match.group(4)) if match.group(4) else 0
            description = match.group(5).strip()
            
            updates.append({
                "type": update_type,
                "id": update_id,
                "helpful": helpful,
                "harmful": harmful,
                "description": description
            })
    return updates

# --- Playbook Updater (Phase 2.3 & 2.4) ---

def update_playbook(playbook_path: Path, updates: List[Dict]):
    """Safely update an .mdc playbook with new learnings."""
    if not playbook_path.exists():
        console.print(f"[yellow]Warning: Playbook {playbook_path} not found. Skipping update.[/yellow]")
        return

    content = playbook_path.read_text()
    
    for update in updates:
        update_id = update['id']
        update_type = update['type']

        # Check if it's a new item or an update to an existing one
        # Pattern for existing item:
        # <!-- [type-ID] helpful=X harmful=Y :: description -->
        # Or for decisions: <!-- [dec-ID] :: description -->

        existing_pattern = rf"<!-- \[{update_type}-{update_id}\](?:\s+helpful=(\d+)\s+harmful=(\d+))?\s*::\s*(.*?) -->"
        match = re.search(existing_pattern, content)

        if match:
            # Update existing item
            old_helpful = int(match.group(1)) if match.group(1) else 0
            old_harmful = int(match.group(2)) if match.group(2) else 0

            new_helpful = old_helpful + update['helpful']
            new_harmful = old_harmful + update['harmful']

            new_line = f"<!-- [{update_type}-{update_id}]"
            if update_type != 'dec':
                new_line += f" helpful={new_helpful} harmful={new_harmful}"
            new_line += f" :: {update['description']} -->"

            content = content.replace(match.group(0), new_line)
            console.print(
                f"Updated existing {update_type} [blue]{update_id}[/blue]"
            )
        else:
            # Add new item
            # Generate a unique ID if it's "NEW"
            if update_id == "NEW":
                # Simple ID generation: count existing items of same type
                existing_ids = re.findall(rf"\[{update_type}-(\d+)\]", content)
                next_id = max([int(i) for i in existing_ids] + [0]) + 1
                update_id = f"{next_id:03d}"

            update_str = f"[{update_type}-{update_id}]"
            if update_type != 'dec':
                update_str += f" helpful={update['helpful']} harmful={update['harmful']}"
            update_str += f" :: {update['description']}"

            new_line = f"<!-- {update_str} -->"

            # Determine which section to add to
            section_map = {
                "str": "## Strategier & patterns",
                "mis": "## Kända fallgropar",
                "dec": "## Arkitekturella beslut"
            }

            section_header = section_map.get(update_type)
            if section_header and section_header in content:
                parts = content.split(section_header)
                content = (
                    parts[0] + section_header + "\n" + new_line + parts[1]
                )
                console.print(f"Added new {update_type} [green]{update_id}[/green]")
            else:
                # If section not found, append to end
                content += f"\n\n{section_header}\n{new_line}"
                console.print(
                    f"Created section and added new {update_type} [green]{update_id}[/green]"
                )
            
    playbook_path.write_text(content)
    console.print(f"Updated playbook: [green]{playbook_path}[/green]")

app = typer.Typer(no_args_is_help=True)
console = Console()
yaml = YAML()
yaml.preserve_quotes = True

class TokenMode(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

class TaskType(str, Enum):
    IMPLEMENT = "implement"
    REVIEW = "review"
    DEBUG = "debug"
    REFACTOR = "refactor"
    PLAN = "plan"

class Config(BaseModel):
    token_mode: TokenMode = TokenMode.LOW

class Decision(BaseModel):
    id: str
    title: str
    status: str = "proposed"
    context: str
    decision: str
    consequences: str
    created_at: str = Field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
    agent_id: Optional[str] = None

# Models
class Agent(BaseModel):
    id: str
    name: str
    role: str
    email: str
    created_by: str = "user"
    created_at: str = Field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
    responsibilities: List[str] = Field(default_factory=list)
    memory_file: str
    status: str = "active"

class AgentsConfig(BaseModel):
    version: str = "1"
    agents: List[Agent] = Field(default_factory=list)

class OwnershipModule(BaseModel):
    agent_id: str
    owned_since: str = Field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
    last_active: str = Field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))

class OwnershipConfig(BaseModel):
    version: str = "1"
    modules: Dict[str, OwnershipModule] = Field(default_factory=dict)
    unowned: List[str] = Field(default_factory=list)

# Helper to load/save configs
def load_ownership() -> OwnershipConfig:
    """Load ownership configuration from YAML."""
    ownership_file = Path(".ace/ownership.yaml")
    if not ownership_file.exists():
        return OwnershipConfig()
    with open(ownership_file, "r") as f:
        data = yaml.load(f)
        if data is None:
            return OwnershipConfig()
        return OwnershipConfig(**data)

def save_ownership(config: OwnershipConfig):
    """Save ownership configuration to YAML."""
    ownership_file = Path(".ace/ownership.yaml")
    with open(ownership_file, "w") as f:
        # Pydantic model_dump() to dict, then yaml.dump
        yaml.dump(config.model_dump(), f)

def load_agents() -> AgentsConfig:
    """Load agents configuration from YAML."""
    agents_file = Path(".ace/agents.yaml")
    if not agents_file.exists():
        return AgentsConfig()
    with open(agents_file, "r") as f:
        data = yaml.load(f)
        if data is None:
            return AgentsConfig()
        return AgentsConfig(**data)

def save_agents(config: AgentsConfig):
    """Save agents configuration to YAML."""
    agents_file = Path(".ace/agents.yaml")
    with open(agents_file, "w") as f:
        yaml.dump(config.model_dump(), f)

def load_config() -> Config:
    """Load general configuration from YAML."""
    config_file = Path(".ace/config.yaml")
    if not config_file.exists():
        return Config()
    with open(config_file, "r") as f:
        data = yaml.load(f)
        if data is None:
            return Config()
        return Config(**data)

def save_config(config: Config):
    """Save general configuration to YAML."""
    config_file = Path(".ace/config.yaml")
    with open(config_file, "w") as f:
        # Use model_dump(mode="json") to ensure Enums are serialized as strings
        yaml.dump(config.model_dump(mode="json"), f)

def get_task_framing(task_type: TaskType, module: str) -> str:
    """Get the framing prompt for a specific task type and module."""
    framing = {
        TaskType.IMPLEMENT: f"You are implementing new functionality in {module}. Follow the playbook strategies. Write back new learnings in the write-back section.",
        TaskType.REVIEW: f"You are reviewing code in {module}. Identify deviations from playbook strategies. Add any new pitfalls to the write-back section.",
        TaskType.DEBUG: f"You are debugging an issue in {module}. If the root cause reveals a new pattern, document it as [mis-XXX] in write-back.",
        TaskType.REFACTOR: f"You are refactoring code in {module}. Ensure that the refactoring adheres to the architectural decisions and strategies in the playbook.",
        TaskType.PLAN: f"You are planning a task in {module}. Outline the steps and consider the impact on existing strategies and decisions."
    }
    return framing.get(task_type, "")

@app.command()
def init():
    """Initialize .ace/ and .ace-local/ directories."""
    ace_dir = Path(".ace")
    ace_local_dir = Path(".ace-local")
    
    subdirs = [
        ace_dir / "mail",
        ace_dir / "sessions",
        ace_dir / "decisions",
    ]
    
    for subdir in subdirs:
        subdir.mkdir(parents=True, exist_ok=True)
        console.print(f"Created directory: [green]{subdir}[/green]")
        
    ace_local_dir.mkdir(exist_ok=True)
    console.print(f"Created directory: [green]{ace_local_dir}[/green]")
    
    # Initialize agents.yaml
    agents_file = ace_dir / "agents.yaml"
    if not agents_file.exists():
        agents_data = AgentsConfig()
        save_agents(agents_data)
        console.print(f"Created file: [green]{agents_file}[/green]")
        
    # Initialize config.yaml
    config_file = ace_dir / "config.yaml"
    if not config_file.exists():
        config_data = Config()
        save_config(config_data)
        console.print(f"Created file: [green]{config_file}[/green]")
        
    # Initialize ownership.yaml
    ownership_file = ace_dir / "ownership.yaml"
    if not ownership_file.exists():
        ownership_data = OwnershipConfig()
        save_ownership(ownership_data)
        console.print(f"Created file: [green]{ownership_file}[/green]")

    # Create .cursor/rules directory if it doesn't exist
    cursor_rules_dir = Path(".cursor/rules")
    cursor_rules_dir.mkdir(parents=True, exist_ok=True)
    console.print(f"Created directory: [green]{cursor_rules_dir}[/green]")

    console.print("[bold green]ACE Orchestrator initialized successfully![/bold green]")

@app.command()
def own(path: str, agent: str):
    """Assign ownership of a path to an agent."""
    config = load_ownership()
    config.modules[path] = OwnershipModule(agent_id=agent)
    save_ownership(config)
    console.print(f"Assigned [blue]{path}[/blue] to agent [green]{agent}[/green]")

@app.command()
def who(path: str):
    """Find out who owns a path (longest prefix match)."""
    config = load_ownership()
    
    # Simple longest prefix match
    best_match_id = None
    best_match_len = -1
    
    for module_path in config.modules:
        if path.startswith(module_path):
            if len(module_path) > best_match_len:
                best_match_len = len(module_path)
                best_match_id = config.modules[module_path].agent_id
                
    if best_match_id:
        console.print(f"Path [blue]{path}[/blue] is owned by agent [green]{best_match_id}[/green]")
    else:
        console.print(f"Path [blue]{path}[/blue] is currently [yellow]unowned[/yellow]")

@app.command()
def list_owners():
    """List all ownership assignments."""
    config = load_ownership()
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

@app.command()
def unown(path: str):
    """Remove ownership of a path."""
    config = load_ownership()
    if path in config.modules:
        del config.modules[path]
        save_ownership(config)
        console.print(f"Removed ownership for [blue]{path}[/blue]")
    else:
        console.print(f"Path [blue]{path}[/blue] was not owned.")

@app.command()
def agent_create(
    name: str = typer.Option(..., "--name", "-n", help="Agent name"),
    role: str = typer.Option(..., "--role", "-r", help="Agent role"),
    id: str = typer.Option(..., "--id", "-i", help="Agent unique ID"),
    email: Optional[str] = typer.Option(None, "--email", "-e", help="Agent email"),
):
    """Create a new agent in the registry."""
    config = load_agents()
    
    if any(a.id == id for a in config.agents):
        console.print(f"[red]Error: Agent with ID {id} already exists.[/red]")
        raise typer.Exit(code=1)
        
    if not email:
        email = f"{id}@ace.local"
        
    memory_file = f".cursor/rules/{role}.mdc"
    
    new_agent = Agent(
        id=id,
        name=name,
        role=role,
        email=email,
        memory_file=memory_file
    )
    
    config.agents.append(new_agent)
    save_agents(config)
    console.print(f"Created agent [green]{name}[/green] (ID: {id})")

@app.command()
def agent_list():
    """List all agents in the registry."""
    config = load_agents()
    if not config.agents:
        console.print("No agents found.")
        return
    
    table = Table(title="Agent Registry")
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("Role", style="yellow")
    table.add_column("Email", style="blue")
    
    for agent in config.agents:
        table.add_row(agent.id, agent.name, agent.role, agent.email)
        
    console.print(table)

@app.command()
def config_tokens(mode: TokenMode = typer.Option(..., "--mode", "-m", help="Token consumption mode")):
    """Set token consumption mode (low/medium/high)."""
    config = load_config()
    config.token_mode = mode
    save_config(config)
    console.print(f"Token mode set to [bold blue]{mode.value}[/bold blue]")

@app.command()
def build_context(
    path: Optional[str] = typer.Option(None, "--path", "-p", help="Path to the file or module"),
    task_type: TaskType = typer.Option(TaskType.IMPLEMENT, "--task-type", "-t", help="Type of task"),
    agent_id: Optional[str] = typer.Option(None, "--agent", "-a", help="Explicit agent ID"),
):
    """Compose the context slice for an agent call."""
    # 1. Global rules
    context_parts = []
    global_rules_file = Path(".cursor/rules/_global.mdc")
    if global_rules_file.exists():
        context_parts.append(f"### GLOBAL RULES\n{global_rules_file.read_text()}")
    
    # 2. Resolve agent and playbook
    resolved_agent_id = agent_id
    if not resolved_agent_id and path:
        # Longest prefix match logic (reused from who)
        ownership = load_ownership()
        best_match_len = -1
        for module_path in ownership.modules:
            if path.startswith(module_path):
                if len(module_path) > best_match_len:
                    best_match_len = len(module_path)
                    resolved_agent_id = ownership.modules[
                        module_path
                    ].agent_id

    if resolved_agent_id:
        agents_config = load_agents()
        agent = next(
            (a for a in agents_config.agents if a.id == resolved_agent_id),
            None
        )
        if agent:
            playbook_path = Path(agent.memory_file)
            if playbook_path.exists():
                context_parts.append(
                    f"### AGENT PLAYBOOK ({agent.role})\n"
                    f"{playbook_path.read_text()}"
                )
            else:
                # Fallback to .cursor/rules/<role>.mdc
                playbook_path = Path(f".cursor/rules/{agent.role}.mdc")
                if playbook_path.exists():
                    context_parts.append(
                        f"### AGENT PLAYBOOK ({agent.role})\n"
                        f"{playbook_path.read_text()}"
                    )

    # 3. Recent decisions (ADRs)
    decisions_dir = Path(".ace/decisions")
    if decisions_dir.exists():
        decisions = sorted(
            list(decisions_dir.glob("*.md")),
            key=lambda x: x.stat().st_mtime,
            reverse=True
        )[:3]
        if decisions:
            context_parts.append("### RECENT DECISIONS")
            for d in decisions:
                context_parts.append(f"#### {d.name}\n{d.read_text()}")

    # 4. Session continuity
    config = load_config()
    sessions_dir = Path(".ace/sessions")
    if sessions_dir.exists():
        # Get recent session logs based on token mode
        session_files = sorted(
            list(sessions_dir.glob("*.md")),
            key=lambda x: x.stat().st_mtime,
            reverse=True
        )

        num_sessions = 1
        if config.token_mode == TokenMode.MEDIUM:
            num_sessions = 3
        elif config.token_mode == TokenMode.HIGH:
            num_sessions = 5

        recent_sessions = session_files[:num_sessions]
        if recent_sessions:
            context_parts.append("### RECENT SESSIONS")
            for s in recent_sessions:
                context_parts.append(f"#### Session: {s.name}\n{s.read_text()}")
    
    # 5. Task framing
    module_name = path if path else "the project"
    framing = get_task_framing(task_type, module_name)
    context_parts.append(f"### TASK FRAMING\n{framing}")
    
    full_context = "\n\n".join(context_parts)
    console.print(full_context)
    # Return both context and resolved agent ID
    return full_context, resolved_agent_id

@app.command()
def run(
    command: str = typer.Argument(..., help="Command to run"),
    path: Optional[str] = typer.Option(
        None,
        "--path",
        "-p",
        help="Path to the file or module"
    ),
    task_type: TaskType = typer.Option(
        TaskType.IMPLEMENT,
        "--task-type",
        "-t",
        help="Type of task"
    ),
    agent_id: Optional[str] = typer.Option(
        None,
        "--agent",
        "-a",
        help="Explicit agent ID"
    ),
):
    """Execute an agent command with ACE context."""
    # 1. Build context
    context, resolved_agent_id = build_context(
        path=path,
        task_type=task_type,
        agent_id=agent_id
    )

    # 2. Prepare the command
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".txt",
        delete=False
    ) as tmp:
        tmp.write(context)
        context_file = tmp.name

    console.print(f"Running command: [bold blue]{command}[/bold blue]")
    console.print(f"Context injected from: [dim]{context_file}[/dim]")

    # 3. Execute and capture output
    try:
        process = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True
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

    # 4. Log the session
    session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    sessions_dir = Path(".ace/sessions")
    sessions_dir.mkdir(parents=True, exist_ok=True)
    session_file = sessions_dir / f"session_{session_id}.md"

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

    # 5. Trigger reflection
    if exit_code == 0:
        # Skip reflection in tests if ANTHROPIC_API_KEY is not set
        if os.getenv("ANTHROPIC_API_KEY"):
            _perform_reflection(session_file)
        else:
            console.print(
                "[yellow]Skipping reflection: ANTHROPIC_API_KEY not set.[/yellow]"
            )

    if exit_code != 0:
        raise typer.Exit(code=exit_code)

def _perform_reflection(session_file: Path):
    """Internal helper to perform reflection on a session file."""
    session_content = session_file.read_text()
    
    # Extract the Output section from the session log
    output_match = re.search(r"## Output\n```\n(.*?)\n```", session_content, re.DOTALL)
    if not output_match:
        console.print("[red]Could not find output section in session log.[/red]")
        return
    
    session_output = output_match.group(1)
    reflection_text = reflect_on_session(session_output)
    
    console.print("\n[bold]Reflection Output:[/bold]")
    console.print(reflection_text)
    
    # Parse and update playbooks
    updates = parse_reflection_output(reflection_text)
    if updates:
        # Find the agent/playbook to update
        agent_id_match = re.search(r"- \*\*Agent ID\*\*: `(.*?)`", session_content)
        if agent_id_match:
            agent_id = agent_id_match.group(1)
            if agent_id != "None":
                agents_config = load_agents()
                agent = next((a for a in agents_config.agents if a.id == agent_id), None)
                if agent:
                    update_playbook(Path(agent.memory_file), updates)
                    return
        
        # Fallback: update global rules
        update_playbook(Path(".cursor/rules/_global.mdc"), updates)
    else:
        console.print("[yellow]No new learnings extracted.[/yellow]")

@app.command()
def reflect_cmd(
    session_id: Optional[str] = typer.Option(
        None,
        "--session-id",
        "-s",
        help="Session ID to reflect on"
    )
):
    """Reflect on a session and extract learnings."""
    sessions_dir = Path(".ace/sessions")
    if not session_id:
        # Get most recent session
        session_files = sorted(
            list(sessions_dir.glob("*.md")),
            key=lambda x: x.stat().st_mtime,
            reverse=True
        )
        if not session_files:
            console.print("[red]No sessions found to reflect on.[/red]")
            return
        session_file = session_files[0]
    else:
        session_file = sessions_dir / f"session_{session_id}.md"
        if not session_file.exists():
            console.print(f"[red]Session {session_id} not found.[/red]")
            return

    console.print(f"Reflecting on session: [blue]{session_file.name}[/blue]")
    _perform_reflection(session_file)


@app.command()
def decision_add(
    title: str = typer.Option(..., "--title", "-t", help="Decision title"),
    context: str = typer.Option(..., "--context", "-c", help="Context for the decision"),
    decision: str = typer.Option(..., "--decision", "-d", help="The decision made"),
    consequences: str = typer.Option(..., "--consequences", "-q", help="Consequences of the decision"),
    status: str = typer.Option("accepted", "--status", "-s", help="Decision status (proposed/accepted/deprecated)"),
    agent_id: Optional[str] = typer.Option(None, "--agent", "-a", help="Agent who made the decision"),
):
    """Add a new Architectural Decision Record (ADR)."""
    decisions_dir = Path(".ace/decisions")
    decisions_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate ID: ADR-001, ADR-002, etc.
    existing_adrs = list(decisions_dir.glob("ADR-*.md"))
    next_num = 1
    if existing_adrs:
        nums = [int(re.search(r"ADR-(\d+)", f.name).group(1)) for f in existing_adrs if re.search(r"ADR-(\d+)", f.name)]
        if nums:
            next_num = max(nums) + 1
    
    adr_id = f"ADR-{next_num:03d}"
    
    new_decision = Decision(
        id=adr_id,
        title=title,
        status=status,
        context=context,
        decision=decision,
        consequences=consequences,
        agent_id=agent_id
    )
    
    adr_file = decisions_dir / f"{adr_id}.md"
    
    content = f"""# {adr_id}: {title}
- **Status**: {status}
- **Date**: {new_decision.created_at}
- **Agent**: {agent_id or "User"}

## Context
{context}

## Decision
{decision}

## Consequences
{consequences}
"""
    adr_file.write_text(content)
    console.print(f"Created ADR: [green]{adr_file}[/green]")

@app.command()
def decision_list():
    """List all Architectural Decision Records."""
    decisions_dir = Path(".ace/decisions")
    if not decisions_dir.exists():
        console.print("No decisions found.")
        return
        
    adrs = sorted(list(decisions_dir.glob("ADR-*.md")))
    if not adrs:
        console.print("No ADRs found.")
        return
        
    table = Table(title="Architectural Decision Records")
    table.add_column("ID", style="cyan")
    table.add_column("Title", style="green")
    table.add_column("Status", style="yellow")
    table.add_column("Date", style="magenta")
    
    for adr_path in adrs:
        content = adr_path.read_text()
        title_match = re.search(r"# ADR-\d+: (.*)", content)
        status_match = re.search(r"- \*\*Status\*\*: (.*)", content)
        date_match = re.search(r"- \*\*Date\*\*: (.*)", content)
        
        title = title_match.group(1) if title_match else adr_path.name
        status = status_match.group(1) if status_match else "unknown"
        date = date_match.group(1) if date_match else "unknown"
        
        table.add_row(adr_path.stem, title, status, date)
        
    console.print(table)

@app.command()
def memory_prune(
    agent_id: Optional[str] = typer.Option(None, "--agent", "-a", help="Agent ID to prune memory for"),
    threshold: int = typer.Option(0, "--threshold", "-t", help="Prune if harmful - helpful > threshold"),
):
    """Archive or remove 'harmful' strategies (harmful > helpful)."""
    agents_config = load_agents()
    
    if agent_id:
        agents = [a for a in agents_config.agents if a.id == agent_id]
        if not agents:
            console.print(f"[red]Agent {agent_id} not found.[/red]")
            return
    else:
        agents = agents_config.agents
        
    for agent in agents:
        playbook_path = Path(agent.memory_file)
        if not playbook_path.exists():
            continue
            
        console.print(f"Pruning memory for agent: [blue]{agent.id}[/blue] ([dim]{playbook_path}[/dim])")
        content = playbook_path.read_text()
        
        # Pattern for strategies and pitfalls: <!-- [type-ID] helpful=X harmful=Y :: description -->
        pattern = r"<!-- \[(str|mis)-([^\]]+)\]\s+helpful=(\d+)\s+harmful=(\d+)\s*::\s*(.*?) -->"
        
        pruned_count = 0
        def prune_match(match):
            nonlocal pruned_count
            update_type = match.group(1)
            update_id = match.group(2)
            helpful = int(match.group(3))
            harmful = int(match.group(4))
            description = match.group(5)
            
            if harmful - helpful > threshold:
                console.print(f"  [red]Pruning[/red] {update_type} [blue]{update_id}[/blue]: {description} (h={helpful}, m={harmful})")
                pruned_count += 1
                return f"<!-- [PRUNED] {match.group(0)} -->"
            return match.group(0)
            
        new_content = re.sub(pattern, prune_match, content)
        
        if pruned_count > 0:
            playbook_path.write_text(new_content)
            console.print(f"  [green]Done.[/green] Pruned {pruned_count} items.")
        else:
            console.print("  [yellow]No items met the pruning threshold.[/yellow]")

@app.command()
def memory_sync():
    """Keep AGENTS.md in sync with the Agent Registry and recent Decisions."""
    agents_config = load_agents()
    decisions_dir = Path(".ace/decisions")
    
    content = ["# ACE Agents Registry", ""]
    
    # Agents Section
    content.append("## Active Agents")
    if not agents_config.agents:
        content.append("No agents registered.")
    else:
        for agent in agents_config.agents:
            content.append(f"### {agent.name} (`{agent.id}`)")
            content.append(f"- **Role**: {agent.role}")
            content.append(f"- **Email**: {agent.email}")
            content.append(f"- **Memory**: `{agent.memory_file}`")
            if agent.responsibilities:
                content.append("- **Responsibilities**:")
                for resp in agent.responsibilities:
                    content.append(f"  - {resp}")
            content.append("")
            
    # Decisions Section
    content.append("## Recent Architectural Decisions")
    if not decisions_dir.exists():
        content.append("No decisions found.")
    else:
        adrs = sorted(list(decisions_dir.glob("ADR-*.md")), reverse=True)[:5]
        if not adrs:
            content.append("No ADRs found.")
        else:
            for adr_path in adrs:
                adr_content = adr_path.read_text()
                title_match = re.search(r"# (ADR-\d+: .*)", adr_content)
                status_match = re.search(r"- \*\*Status\*\*: (.*)", adr_content)
                
                title = title_match.group(1) if title_match else adr_path.name
                status = status_match.group(1) if status_match else "unknown"
                
                content.append(f"- **{title}** [{status}]")
    
    Path("AGENTS.md").write_text("\n".join(content))
    console.print("Updated [green]AGENTS.md[/green]")

if __name__ == "__main__":
    app()
