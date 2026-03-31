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
    ownership_file = Path(".ace/ownership.yaml")
    if not ownership_file.exists():
        return OwnershipConfig()
    with open(ownership_file, "r") as f:
        data = yaml.load(f)
        if data is None:
            return OwnershipConfig()
        return OwnershipConfig(**data)

def save_ownership(config: OwnershipConfig):
    ownership_file = Path(".ace/ownership.yaml")
    with open(ownership_file, "w") as f:
        # Pydantic model_dump() to dict, then yaml.dump
        yaml.dump(config.model_dump(), f)

def load_agents() -> AgentsConfig:
    agents_file = Path(".ace/agents.yaml")
    if not agents_file.exists():
        return AgentsConfig()
    with open(agents_file, "r") as f:
        data = yaml.load(f)
        if data is None:
            return AgentsConfig()
        return AgentsConfig(**data)

def save_agents(config: AgentsConfig):
    agents_file = Path(".ace/agents.yaml")
    with open(agents_file, "w") as f:
        yaml.dump(config.model_dump(), f)

def load_config() -> Config:
    config_file = Path(".ace/config.yaml")
    if not config_file.exists():
        return Config()
    with open(config_file, "r") as f:
        data = yaml.load(f)
        if data is None:
            return Config()
        return Config(**data)

def save_config(config: Config):
    config_file = Path(".ace/config.yaml")
    with open(config_file, "w") as f:
        # Use model_dump(mode="json") to ensure Enums are serialized as strings
        yaml.dump(config.model_dump(mode="json"), f)

def get_task_framing(task_type: TaskType, module: str) -> str:
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
                    resolved_agent_id = ownership.modules[module_path].agent_id
    
    if resolved_agent_id:
        agents_config = load_agents()
        agent = next((a for a in agents_config.agents if a.id == resolved_agent_id), None)
        if agent:
            playbook_path = Path(agent.memory_file)
            if playbook_path.exists():
                context_parts.append(f"### AGENT PLAYBOOK ({agent.role})\n{playbook_path.read_text()}")
            else:
                # Fallback to .cursor/rules/<role>.mdc if memory_file is not found
                playbook_path = Path(f".cursor/rules/{agent.role}.mdc")
                if playbook_path.exists():
                    context_parts.append(f"### AGENT PLAYBOOK ({agent.role})\n{playbook_path.read_text()}")
    
    # 3. Recent decisions (ADRs)
    decisions_dir = Path(".ace/decisions")
    if decisions_dir.exists():
        decisions = sorted(list(decisions_dir.glob("*.md")), key=lambda x: x.stat().st_mtime, reverse=True)[:3]
        if decisions:
            context_parts.append("### RECENT DECISIONS")
            for d in decisions:
                context_parts.append(f"#### {d.name}\n{d.read_text()}")
    
    # 4. Session continuity
    config = load_config()
    sessions_dir = Path(".ace/sessions")
    if sessions_dir.exists():
        # Get most recent session logs based on token mode
        session_files = sorted(list(sessions_dir.glob("*.md")), key=lambda x: x.stat().st_mtime, reverse=True)
        
        num_sessions = 1
        if config.token_mode == TokenMode.MEDIUM:
            num_sessions = 3
        elif config.token_mode == TokenMode.HIGH:
            num_sessions = 5
            
        recent_sessions = session_files[:num_sessions]
        if recent_sessions:
            context_parts.append("### RECENT SESSIONS")
            for s in recent_sessions:
                # Truncate session content if it's too long? For now just include it.
                context_parts.append(f"#### Session: {s.name}\n{s.read_text()}")
    
    # 5. Task framing
    module_name = path if path else "the project"
    framing = get_task_framing(task_type, module_name)
    context_parts.append(f"### TASK FRAMING\n{framing}")
    
    full_context = "\n\n".join(context_parts)
    console.print(full_context)
    return full_context

@app.command()
def run(
    command: str = typer.Argument(..., help="Command to run (e.g. 'cursor-agent' or 'claude-code')"),
    path: Optional[str] = typer.Option(None, "--path", "-p", help="Path to the file or module"),
    task_type: TaskType = typer.Option(TaskType.IMPLEMENT, "--task-type", "-t", help="Type of task"),
    agent_id: Optional[str] = typer.Option(None, "--agent", "-a", help="Explicit agent ID"),
):
    """Execute an agent command with ACE context."""
    # 1. Build context
    context = build_context(path=path, task_type=task_type, agent_id=agent_id)
    
    # 2. Prepare the command
    # For now, we'll just print it. In a real implementation, we'd use subprocess.
    # We might want to inject the context as an environment variable or a temporary file.
    import subprocess
    import tempfile
    
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as tmp:
        tmp.write(context)
        context_file = tmp.name
        
    console.print(f"Running command: [bold blue]{command}[/bold blue]")
    console.print(f"Context injected from: [dim]{context_file}[/dim]")
    
    # In a real scenario, we'd pass the context file to the agent
    # For example: cursor-agent --context-file context_file "the actual task"
    # For this implementation, we'll just simulate the execution.
    
    # 3. Execute and capture output
    # This is a simplified version. We'd need to handle arguments properly.
    # For now, let's just run the command and capture its output.
    try:
        # We'll prepend the context to the agent's input or pass it via a flag if supported.
        # Since we don't know the exact agent CLI, we'll just run the command as is for now.
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
    
    if exit_code != 0:
        raise typer.Exit(code=exit_code)

if __name__ == "__main__":
    app()
