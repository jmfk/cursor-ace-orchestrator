import os
import re
import subprocess
import tempfile
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Tuple
from ruamel.yaml import YAML
import anthropic
from ace_lib.models.schemas import (
    Config,
    Decision,
    Agent,
    AgentsConfig,
    OwnershipConfig,
    OwnershipModule,
    TokenMode,
    TaskType,
    MailMessage,
)

yaml = YAML()
yaml.preserve_quotes = True


class ACEService:
    def __init__(self, base_path: Path = Path(".")):
        self.base_path = base_path
        self.ace_dir = base_path / ".ace"
        self.ace_local_dir = base_path / ".ace-local"
        self.sessions_dir = self.ace_dir / "sessions"
        self.decisions_dir = self.ace_dir / "decisions"
        self.mail_dir = self.ace_dir / "mail"
        self.cursor_rules_dir = base_path / ".cursor" / "rules"

        # Reset any cached data if needed
        # (Though Pydantic models are usually fresh)

    # --- Config Management ---

    def load_config(self) -> Config:
        config_file = self.ace_dir / "config.yaml"
        if not config_file.exists():
            return Config()
        with open(config_file, "r") as f:
            data = yaml.load(f)
            return Config(**data) if data else Config()

    def save_config(self, config: Config):
        self.ace_dir.mkdir(parents=True, exist_ok=True)
        config_file = self.ace_dir / "config.yaml"
        with open(config_file, "w") as f:
            yaml.dump(config.model_dump(mode="json"), f)

    # --- Ownership Management ---

    def load_ownership(self) -> OwnershipConfig:
        ownership_file = self.ace_dir / "ownership.yaml"
        if not ownership_file.exists():
            return OwnershipConfig()
        with open(ownership_file, "r") as f:
            data = yaml.load(f)
            return OwnershipConfig(**data) if data else OwnershipConfig()

    def save_ownership(self, config: OwnershipConfig):
        self.ace_dir.mkdir(parents=True, exist_ok=True)
        ownership_file = self.ace_dir / "ownership.yaml"
        with open(ownership_file, "w") as f:
            yaml.dump(config.model_dump(), f)

    def assign_ownership(self, path: str, agent_id: str):
        config = self.load_ownership()
        config.modules[path] = OwnershipModule(agent_id=agent_id)
        self.save_ownership(config)
        return path, agent_id

    def resolve_owner(self, path: str) -> Optional[str]:
        config = self.load_ownership()
        best_match_id = None
        best_match_len = -1
        for module_path in config.modules:
            if path.startswith(module_path):
                if len(module_path) > best_match_len:
                    best_match_len = len(module_path)
                    best_match_id = config.modules[module_path].agent_id
        return best_match_id

    # --- Agent Management ---

    def load_agents(self) -> AgentsConfig:
        agents_file = self.ace_dir / "agents.yaml"
        if not agents_file.exists():
            return AgentsConfig()
        with open(agents_file, "r") as f:
            data = yaml.load(f)
            return AgentsConfig(**data) if data else AgentsConfig()

    def save_agents(self, config: AgentsConfig):
        self.ace_dir.mkdir(parents=True, exist_ok=True)
        agents_file = self.ace_dir / "agents.yaml"
        with open(agents_file, "w") as f:
            yaml.dump(config.model_dump(), f)

    def create_agent(
        self, id: str, name: str, role: str, email: Optional[str] = None
    ) -> Agent:
        config = self.load_agents()
        if any(a.id == id for a in config.agents):
            raise ValueError(f"Agent with ID {id} already exists.")

        if not email:
            email = f"{id}@ace.local"

        memory_file = f".cursor/rules/{role}.mdc"
        new_agent = Agent(
            id=id,
            name=name,
            role=role,
            email=email,
            memory_file=memory_file,
            status="active",
        )
        config.agents.append(new_agent)
        self.save_agents(config)
        return new_agent

    # --- Context & Execution ---

    def get_task_framing(self, task_type: TaskType, module: str) -> str:
        framing = {
            TaskType.IMPLEMENT: (
                f"You are implementing new functionality in {module}. "
                "Follow the playbook strategies. "
                "Write back new learnings in the write-back section."
            ),
            TaskType.REVIEW: (
                f"You are reviewing code in {module}. "
                "Identify deviations from playbook strategies. "
                "Add any new pitfalls to the write-back section."
            ),
            TaskType.DEBUG: (
                f"You are debugging an issue in {module}. "
                "If the root cause reveals a new pattern, "
                "document it as [mis-XXX] in write-back."
            ),
            TaskType.REFACTOR: (
                f"You are refactoring code in {module}. Ensure that the "
                "refactoring adheres to the architectural decisions and "
                "strategies in the playbook."
            ),
            TaskType.PLAN: (
                f"You are planning a task in {module}. Outline the steps "
                "and consider the impact on existing strategies and "
                "decisions."
            ),
        }
        return framing.get(task_type, "")

    def build_context(
        self,
        path: Optional[str] = None,
        task_type: TaskType = TaskType.IMPLEMENT,
        agent_id: Optional[str] = None,
    ) -> Tuple[str, Optional[str]]:
        context_parts = []

        # 1. Global rules
        global_rules_file = self.cursor_rules_dir / "_global.mdc"
        if global_rules_file.exists():
            context_parts.append(
                f"### GLOBAL RULES\n{global_rules_file.read_text()}"
            )

        # 2. Resolve agent and playbook
        resolved_agent_id = agent_id
        if not resolved_agent_id and path:
            resolved_agent_id = self.resolve_owner(path)

        if resolved_agent_id:
            agents_config = self.load_agents()
            agent = next(
                (a for a in agents_config.agents if a.id == resolved_agent_id),
                None,
            )
            if agent:
                playbook_path = self.base_path / agent.memory_file
                if not playbook_path.exists():
                    playbook_path = self.cursor_rules_dir / f"{agent.role}.mdc"

                if playbook_path.exists():
                    context_parts.append(
                        f"### AGENT PLAYBOOK ({agent.role})\n"
                        f"{playbook_path.read_text()}"
                    )

        # 3. Recent decisions (ADRs)
        if self.decisions_dir.exists():
            decisions = sorted(
                list(self.decisions_dir.glob("*.md")),
                key=lambda x: x.stat().st_mtime,
                reverse=True,
            )[:3]
            if decisions:
                context_parts.append("### RECENT DECISIONS")
                for d in decisions:
                    context_parts.append(f"#### {d.name}\n{d.read_text()}")

        # 4. Session continuity
        config = self.load_config()
        if self.sessions_dir.exists():
            session_files = sorted(
                list(self.sessions_dir.glob("*.md")),
                key=lambda x: x.stat().st_mtime,
                reverse=True,
            )
            token_map = {
                TokenMode.LOW: 1,
                TokenMode.MEDIUM: 3,
                TokenMode.HIGH: 5,
            }
            num_sessions = token_map.get(config.token_mode, 1)
            recent_sessions = session_files[:num_sessions]
            if recent_sessions:
                context_parts.append("### RECENT SESSIONS")
                for s in recent_sessions:
                    context_parts.append(
                        f"#### Session: {s.name}\n{s.read_text()}"
                    )

        # 5. Task framing
        module_name = path if path else "the project"
        framing = self.get_task_framing(task_type, module_name)
        context_parts.append(f"### TASK FRAMING\n{framing}")

        return "\n\n".join(context_parts), resolved_agent_id

    # --- Reflection Engine ---

    def list_sessions(self) -> List[Dict]:
        if not self.sessions_dir.exists():
            return []
        session_files = sorted(
            list(self.sessions_dir.glob("*.md")),
            key=lambda x: x.stat().st_mtime,
            reverse=True,
        )
        sessions = []
        for s in session_files:
            content = s.read_text()
            # Extract basic metadata from markdown
            command_match = re.search(r"- \*\*Command\*\*: `(.*?)`", content)
            agent_match = re.search(r"- \*\*Agent ID\*\*: `(.*?)`", content)
            sessions.append(
                {
                    "id": s.stem.replace("session_", ""),
                    "command": (
                        command_match.group(1) if command_match else "unknown"
                    ),
                    "agent_id": (
                        agent_match.group(1) if agent_match else "unknown"
                    ),
                    "timestamp": datetime.fromtimestamp(
                        s.stat().st_mtime
                    ).isoformat(),
                }
            )
        return sessions

    def get_session(self, session_id: str) -> Optional[str]:
        session_file = self.sessions_dir / f"session_{session_id}.md"
        if not session_file.exists():
            return None
        return session_file.read_text()

    def get_anthropic_client(self):
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable not set.")
        return anthropic.Anthropic(api_key=api_key)

    def reflect_on_session(self, session_output: str) -> str:
        client = self.get_anthropic_client()
        prompt = (
            "You are an ACE Reflection Engine. Your task is to analyze the "
            "output of a coding agent session and extract structured "
            "learnings.\n\n"
            "Look for:\n"
            "1. **Strategies [str-XXX]**: Successful patterns, helpful "
            "libraries, or effective approaches.\n"
            "2. **Pitfalls [mis-XXX]**: Bugs encountered, harmful "
            "patterns, or things to avoid.\n"
            "3. **Decisions [dec-XXX]**: Architectural choices made "
            "during the task.\n\n"
            "Format your output EXACTLY as follows:\n"
            "[str-NEW] helpful=1 harmful=0 :: <description of the strategy>\n"
            "[mis-NEW] helpful=0 harmful=1 :: <description of the pitfall>\n"
            "[dec-NEW] :: <description of the decision>\n\n"
            "Only include items that are clearly supported by the session "
            "output. If no new learnings are found, "
            'return "No new learnings."\n\n'
            f"Session Output:\n{session_output}\n"
        )
        try:
            message = client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )
            if isinstance(message.content, list):
                return "".join(
                    [
                        block.text
                        for block in message.content
                        if hasattr(block, "text")
                    ]
                )
            return str(message.content)
        except Exception as e:
            return f"Error during reflection: {e}"

    def parse_reflection_output(self, reflection_text: str) -> List[Dict]:
        updates = []
        pattern = (
            r"\[(str|mis|dec)-([^\]]+)\]"
            r"(?:\s+helpful=(\d+)\s+harmful=(\d+))?\s*::\s*(.*)"
        )
        for line in reflection_text.splitlines():
            match = re.search(pattern, line)
            if match:
                updates.append(
                    {
                        "type": match.group(1),
                        "id": match.group(2),
                        "helpful": (
                            int(match.group(3)) if match.group(3) else 0
                        ),
                        "harmful": (
                            int(match.group(4)) if match.group(4) else 0
                        ),
                        "description": match.group(5).strip(),
                    }
                )
        return updates

    def update_playbook(self, playbook_path: Path, updates: List[Dict]):
        if not playbook_path.exists():
            return False

        content = playbook_path.read_text()
        for update in updates:
            update_id, update_type = update["id"], update["type"]

            # Pattern to match existing entries
            existing_pattern = (
                rf"<!-- \[{update_type}-{update_id}\]"
                r"(?:\s+helpful=(\d+)\s+harmful=(\d+))?\s*::\s*(.*?) -->"
            )
            match = re.search(existing_pattern, content)

            if match:
                # Update existing entry
                old_h = int(match.group(1) or 0)
                old_m = int(match.group(2) or 0)
                new_h = old_h + update.get("helpful", 0)
                new_m = old_m + update.get("harmful", 0)

                new_line = (f"<!-- [{update_type}-{update_id}]"
                            + (f" helpful={new_h} harmful={new_m}"
                               if update_type != "dec" else "")
                            + f" :: {update['description']} -->")
                content = content.replace(match.group(0), new_line)
            else:
                # Handle NEW entries
                if update_id == "NEW":
                    existing_ids = re.findall(
                        rf"\[{update_type}-(\d+)\]", content
                    )
                    next_id = max([int(i) for i in existing_ids] + [0]) + 1
                    update_id = f"{next_id:03d}"

                update_str = f"[{update_type}-{update_id}]"
                if update_type != "dec":
                    update_str += (
                        f" helpful={update.get('helpful', 0)} "
                        f"harmful={update.get('harmful', 0)}"
                    )
                new_line = f"<!-- {update_str} :: {update['description']} -->"

                section_map = {
                    "str": "## Strategier & patterns",
                    "mis": "## Kända fallgropar",
                    "dec": "## Arkitekturella beslut",
                }
                header = section_map.get(update_type)
                if header and header in content:
                    parts = content.split(header, 1)
                    content = parts[0] + header + "\n" + new_line + parts[1]
                else:
                    content = content.rstrip() + f"\n\n{header}\n{new_line}\n"

        playbook_path.write_text(content)
        return True

    # --- ADR Management ---

    def list_decisions(self) -> List[Decision]:
        if not self.decisions_dir.exists():
            return []
        adrs = sorted(list(self.decisions_dir.glob("ADR-*.md")))
        decisions = []
        for adr_path in adrs:
            content = adr_path.read_text()
            title_match = re.search(r"# ADR-\d+: (.*)", content)
            status_match = re.search(r"- \*\*Status\*\*: (.*)", content)
            date_match = re.search(r"- \*\*Date\*\*: (.*)", content)
            agent_match = re.search(r"- \*\*Agent\*\*: (.*)", content)

            # Extract sections
            context_match = re.search(
                r"## Context\n(.*?)\n\n## Decision", content, re.DOTALL
            )
            decision_match = re.search(
                r"## Decision\n(.*?)\n\n## Consequences", content, re.DOTALL
            )
            consequences_match = re.search(
                r"## Consequences\n(.*)", content, re.DOTALL
            )

            decisions.append(
                Decision(
                    id=adr_path.stem,
                    title=(
                        title_match.group(1) if title_match else adr_path.name
                    ),
                    status=(
                        status_match.group(1) if status_match else "unknown"
                    ),
                    created_at=(
                        date_match.group(1)
                        if date_match
                        else datetime.now().isoformat()
                    ),
                    agent_id=agent_match.group(1) if agent_match else None,
                    context=(
                        context_match.group(1).strip() if context_match else ""
                    ),
                    decision=(
                        decision_match.group(1).strip()
                        if decision_match
                        else ""
                    ),
                    consequences=(
                        consequences_match.group(1).strip()
                        if consequences_match
                        else ""
                    ),
                )
            )
        return decisions

    def add_decision(
        self,
        title: str,
        context: str,
        decision: str,
        consequences: str,
        status: str = "accepted",
        agent_id: Optional[str] = None,
    ) -> Decision:
        self.decisions_dir.mkdir(parents=True, exist_ok=True)
        existing_adrs = list(self.decisions_dir.glob("ADR-*.md"))
        next_num = 1
        if existing_adrs:
            nums = [
                int(re.search(r"ADR-(\d+)", f.name).group(1))
                for f in existing_adrs
                if re.search(r"ADR-(\d+)", f.name)
            ]
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
            agent_id=agent_id,
        )

        adr_file = self.decisions_dir / f"{adr_id}.md"
        adr_content = (
            f"# {adr_id}: {title}\n"
            f"- **Status**: {status}\n"
            f"- **Date**: {new_decision.created_at}\n"
            f"- **Agent**: {agent_id or 'User'}\n\n"
            f"## Context\n{context}\n\n"
            f"## Decision\n{decision}\n\n"
            f"## Consequences\n{consequences}\n"
        )
        adr_file.write_text(adr_content)
        return new_decision

    # --- Mail System ---

    def list_mail(self, agent_id: str) -> List[MailMessage]:
        agent_mail_dir = self.mail_dir / agent_id
        if not agent_mail_dir.exists():
            return []
        mail_files = sorted(list(agent_mail_dir.glob("*.yaml")), reverse=True)
        messages = []
        for f in mail_files:
            with open(f, "r") as m:
                data = yaml.load(m)
                messages.append(MailMessage(**data))
        return messages

    def read_mail(self, agent_id: str, msg_id: str) -> Optional[MailMessage]:
        mail_file = self.mail_dir / agent_id / f"{msg_id}.yaml"
        if not mail_file.exists():
            return None
        with open(mail_file, "r") as f:
            data = yaml.load(f)

        # Mark as read
        data["status"] = "read"
        with open(mail_file, "w") as f:
            yaml.dump(data, f)

        return MailMessage(**data)

    def send_mail(
        self, to_agent: str, from_agent: str, subject: str, body: str
    ) -> MailMessage:
        agent_mail_dir = self.mail_dir / to_agent
        agent_mail_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        msg_id = f"{timestamp}_{from_agent}"
        msg = MailMessage(
            id=msg_id,
            **{"from": from_agent, "to": to_agent},
            subject=subject,
            body=body,
        )

        with open(agent_mail_dir / f"{msg_id}.yaml", "w") as f:
            yaml.dump(msg.model_dump(by_alias=True), f)
        return msg

    def debate(self, proposal: str, agent_ids: List[str]) -> str:
        """Mediate a debate between multiple agents."""
        # Send mail to participants about the debate
        for aid in agent_ids:
            self.send_mail(
                to_agent=aid,
                from_agent="orchestrator",
                subject="DEBATE PROPOSAL",
                body=(
                    f"A debate has been initiated on the following "
                    f"proposal: {proposal}"
                ),
            )

        client = self.get_anthropic_client()

        # 1. Gather agent perspectives (simulated via mail)
        perspectives = []
        for aid in agent_ids:
            # In a real scenario, we'd wait for agents to respond to mail.
            # Here we simulate their input based on their roles.
            agents_config = self.load_agents()
            agent = next(
                (a for a in agents_config.agents if a.id == aid), None
            )
            role = agent.role if agent else "expert"

            prompt = (
                f"You are agent {aid} with role {role}. "
                f"Review this proposal: {proposal}\n"
                "Provide a concise critique or support based on your role. "
                "Focus on architectural impact and project standards."
            )

            # Simulate agent response using Claude
        try:
            message = client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=512,
                messages=[{"role": "user", "content": prompt}],
            )
            perspective = "".join(
                [
                    block.text
                    for block in message.content
                    if hasattr(block, "text")
                ]
            )
            perspectives.append(f"Agent {aid} ({role}): {perspective}")
        except Exception as e:
            perspectives.append(
                f"Agent {aid}: Error getting perspective: {e}"
            )

        # 2. LLM-Referee logic
        referee_prompt = (
            "You are the ACE Orchestrator Referee. "
            "You must mediate a debate between multiple agents and reach "
            "a consensus.\n\n"
            f"Original Proposal: {proposal}\n\n"
            "Agent Perspectives:\n" + "\n".join(perspectives) + "\n\n"
            "Analyze the perspectives, identify common ground, and "
            "provide a final recommendation or consensus decision. "
            "If no consensus is reached, explain why and suggest next steps."
        )

        try:
            message = client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=1024,
                messages=[{"role": "user", "content": referee_prompt}],
            )
            consensus = "".join(
                [
                    block.text
                    for block in message.content
                    if hasattr(block, "text")
                ]
            )
            return consensus
        except Exception as e:
            return f"Error during debate mediation: {e}"

    # --- RALPH Loop Engine ---

    def run_loop(
        self,
        prompt: str,
        test_cmd: str,
        max_iterations: int = 10,
        path: Optional[str] = None,
        agent_id: Optional[str] = None,
    ):
        """Iteratively run: Context Refresh -> Execute -> Verify -> Reflect."""
        iteration = 0
        success = False

        # Initial state hash for stagnation detection
        history = []

        while iteration < max_iterations:
            iteration += 1
            print(f"\n[RALPH] Iteration {iteration}/{max_iterations}")

            # Stagnation detection (simplified for now)
            state_str = f"{prompt}_{path}_{agent_id}"
            current_hash = hashlib.sha256(
                state_str.encode()
            ).hexdigest()
            history.append(current_hash)
            if len(history) > 3 and all(
                h == history[-1] for h in history[-3:]
            ):
                print(
                    "[RALPH] ⚠️ Stagnation detected! Attempting recovery..."
                )
                prompt = (
                    f"RECOVERY MODE: The previous approach is stuck. "
                    "Try a different strategy.\n"
                    f"Original task: {prompt}"
                )

            # 1. Context Refresh & Build
            context, resolved_agent_id = self.build_context(
                path=path, task_type=TaskType.IMPLEMENT, agent_id=agent_id
            )

            # 2. Execute (using cursor-agent)
            print(f"[RALPH] Executing task: {prompt[:50]}...")

            # Write context to a temporary file
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", delete=False
            ) as tmp:
                tmp.write(context)
                context_file = tmp.name

            agent_cmd = (
                "cursor-agent --print --model gemini-3-flash --force --trust "
                f'--context-file {context_file} "{prompt}"'
            )

            print("[RALPH] Running agent command...")
            agent_proc = subprocess.run(
                agent_cmd, shell=True, capture_output=True, text=True
            )

            # 3. Verify (Run tests)
            print(f"[RALPH] Verifying with: {test_cmd}")
            result = subprocess.run(
                test_cmd, shell=True, capture_output=True, text=True
            )

            session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
            session_file = (
                self.sessions_dir
                / f"session_loop_{session_id}_{iteration}.md"
            )
            self.sessions_dir.mkdir(parents=True, exist_ok=True)

            session_content = (
                f"# Session Loop {session_id} (Iteration {iteration})\n"
                f"- **Prompt**: `{prompt}`\n"
                f"- **Test Command**: `{test_cmd}`\n"
                f"- **Agent ID**: `{resolved_agent_id}`\n"
                f"- **Agent Exit Code**: {agent_proc.returncode}\n"
                f"- **Test Exit Code**: {result.returncode}\n"
            )
            session_content += (
                f"- **Timestamp**: {datetime.now().isoformat()}\n\n"
                f"## Agent Output\n"
                f"### Stdout\n```\n{agent_proc.stdout}\n```\n"
                f"### Stderr\n```\n{agent_proc.stderr}\n```\n\n"
                f"## Test Output\n"
                f"### Stdout\n```\n{result.stdout}\n```\n"
                f"### Stderr\n```\n{result.stderr}\n```\n"
            )
            session_file.write_text(session_content)

            # 4. Reflection (Intermediate or Final)
            if os.getenv("ANTHROPIC_API_KEY"):
                print(
                    f"[RALPH] Performing reflection for "
                    f"iteration {iteration}..."
                )
                # Reflect on current iteration output
                reflection_text = self.reflect_on_session(
                    agent_proc.stdout + "\n" + result.stdout
                )
                updates = self.parse_reflection_output(reflection_text)
                if updates:
                    playbook_path = self.cursor_rules_dir / "_global.mdc"
                    if resolved_agent_id:
                        agents_config = self.load_agents()
                        agent = next(
                            (
                                a
                                for a in agents_config.agents
                                if a.id == resolved_agent_id
                            ),
                            None
                        )
                        if agent:
                            playbook_path = (
                                self.base_path / agent.memory_file
                            )
                    self.update_playbook(playbook_path, updates)
                    print(f"[RALPH] Updated playbook: {playbook_path.name}")

            if result.returncode == 0:
                print("[RALPH] ✅ Verification successful!")
                success = True
                break
            else:
                print(
                    f"[RALPH] ❌ Verification failed "
                    f"(Exit code: {result.returncode})"
                )
                # Update prompt for next iteration with failure info
                prompt = (
                    f"Previous attempt failed. Test output:\n"
                    f"{result.stdout}\n{result.stderr}\n\n"
                    f"Original task: {prompt}"
                )

            # Cleanup context file
            if os.path.exists(context_file):
                os.remove(context_file)

        return success, iteration

    # --- SOP Engine ---

    def onboard_agent(self, agent_id: str):
        """Run onboarding SOP for an agent."""
        agents_config = self.load_agents()
        agent = next(
            (a for a in agents_config.agents if a.id == agent_id), None
        )
        if not agent:
            raise ValueError(f"Agent {agent_id} not found.")

        self.ace_dir.mkdir(parents=True, exist_ok=True)
        onboarding_file = self.ace_dir / f"onboarding_{agent_id}.md"
        responsibilities = (
            ", ".join(agent.responsibilities)
            if agent.responsibilities
            else "None"
        )
        content = f"""# SOP: Agent Onboarding - {agent.name} ({agent.id})
- **Role**: {agent.role}
- **Responsibilities**: {responsibilities}
- **Memory File**: {agent.memory_file}
- **Status**: {agent.status}

## 1. Context Acquisition
- [ ] Read `AGENTS.md` to understand the current agent landscape.
- [ ] Read `.ace/decisions/*.md` for recent architectural decisions.
- [ ] Read `_global.mdc` for project-wide standards.

## 2. Role-Specific Setup
- [ ] Create/Verify `{agent.memory_file}` exists.
- [ ] Ensure the playbook contains sections for "Strategier & patterns", "Kända fallgropar", and "Arkitekturella beslut".

## 3. Initial Task
- [ ] Review existing codebase in assigned modules: {responsibilities}
- [ ] Identify initial technical debts and document as [mis-NEW] in playbook.
- [ ] Propose first strategy improvement as [str-NEW].

## 4. Handover & Verification
- [ ] Send a "Ready" message to the orchestrator via `ace mail-send`.
"""
        onboarding_file.write_text(content)

        # Inject SOP into agent's inbox
        self.send_mail(
            to_agent=agent_id,
            from_agent="orchestrator",
            subject="ONBOARDING SOP",
            body=(
                f"Your onboarding SOP has been generated: "
                f"{onboarding_file.name}\n\n"
                "Please follow the steps outlined in the file."
            )
        )

        return onboarding_file

    def audit_agent(self, agent_id: str):
        """Run audit SOP for an agent."""
        agents_config = self.load_agents()
        agent = next(
            (a for a in agents_config.agents if a.id == agent_id), None
        )
        if not agent:
            raise ValueError(f"Agent {agent_id} not found.")

        audit_file = (
            self.ace_dir /
            f"audit_{agent_id}_{datetime.now().strftime('%Y%m%d')}.md"
        )
        content = f"""# SOP: Agent Audit - {agent.name} ({agent.id})
- **Auditor**: Orchestrator
- **Date**: {datetime.now().isoformat()}

## 1. Memory Health
- [ ] Check `{agent.memory_file}` for structure and content.
- [ ] Verify that strategies have helpful/harmful counters.
- [ ] Identify stale or conflicting strategies.

## 2. Decision Alignment
- [ ] Review agent's recent contributions against `.ace/decisions/`.
- [ ] Ensure agent is not repeating previously rejected patterns.

## 3. Performance Review
- [ ] Analyze session logs for success/failure ratio.
- [ ] Identify recurring pitfalls [mis-XXX].

## 4. Recommendations
- [ ] **Action**: [KEEP/PRUNE/RE-ONBOARD]
- [ ] **Notes**:
"""
        audit_file.write_text(content)
        return audit_file

    def review_pr(self, pr_id: str, agent_id: str):
        """Run PR review SOP for an agent."""
        self.ace_dir.mkdir(parents=True, exist_ok=True)
        review_file = self.ace_dir / f"review_{pr_id}_{agent_id}.md"
        content = f"""# SOP: PR Review - {pr_id}
- **Reviewer**: {agent_id}
- **Date**: {datetime.now().isoformat()}

## 1. Strategy Alignment
- [ ] Does PR follow strategies defined in reviewer's playbook?
- [ ] Does the PR adhere to global rules in `_global.mdc`?

## 2. Decision Verification
- [ ] Does PR conflict with any recent ADRs in `.ace/decisions/`?

## 3. Learning Extraction
- [ ] Identify any new successful patterns: [str-NEW]
- [ ] Identify any new pitfalls or bugs: [mis-NEW]
- [ ] Identify any architectural choices that should be ADRs: [dec-NEW]

## 4. Conclusion
- [ ] **Status**: [PENDING/APPROVED/REQUEST_CHANGES]
- [ ] **Comments**:
"""
        review_file.write_text(content)

        # Notify agent of PR review task
        self.send_mail(
            to_agent=agent_id,
            from_agent="orchestrator",
            subject=f"PR REVIEW TASK: {pr_id}",
            body=(
                f"You have been assigned to review PR {pr_id}. "
                f"SOP: {review_file.name}"
            )
        )

        return review_file

    # --- Google Stitch Integration ---

    def ui_mockup(self, description: str, agent_id: str):
        """Generate a UI mockup using Google Stitch (simulated)."""
        # In a real scenario, this would call Google Stitch API
        # We simulate this by creating a prompt for the agent
        mockup_id = f"stitch_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        mockup_url = f"https://stitch.google.com/canvas/{mockup_id}"

        mockup_dir = self.ace_dir / "ui_mockups"
        mockup_dir.mkdir(parents=True, exist_ok=True)
        mockup_file = mockup_dir / f"{mockup_id}.md"

        # Use cursor-agent to generate the "mockup"
        prompt = (
            f"Design a UI mockup for: {description}. "
            "Output the design as a single TSX code block using "
            "Tailwind CSS. "
            "The output should be ONLY the code block."
        )

        # In a real implementation, we might use a specialized Stitch API
        # For now, we use the agent to simulate the generation
        agent_cmd = (
            "cursor-agent --print --model gemini-3-flash --force --trust "
            f'"{prompt}"'
        )

        print(f"[STITCH] Generating mockup for: {description}")

        # Check for STITCH_API_KEY to simulate real API call if present
        api_key = os.getenv("STITCH_API_KEY")
        if api_key:
            print("[STITCH] Using real API key (simulated)...")
            # Here we would make a real API call
            # For now, we still use the agent but mark it as "API-driven"
            ui_code = (
                "// Generated via Stitch API\n" +
                self._simulate_stitch_api(description)
            )
        else:
            result = subprocess.run(
                agent_cmd, shell=True, capture_output=True, text=True
            )
            # Extract the code block to ensure we have clean UI code
            code_match = re.search(
                r"```(?:tsx|jsx|html|javascript|typescript)?\n(.*?)\n```",
                result.stdout,
                re.DOTALL,
            )
            ui_code = code_match.group(1) if code_match else result.stdout

        content = (
            f"# UI Mockup: {description}\n"
            f"- **Agent**: {agent_id}\n"
            f"- **URL**: {mockup_url}\n"
            f"- **Status**: Generated\n"
            f"- **Timestamp**: {datetime.now().isoformat()}\n\n"
            f"## Design & Code\n"
            f"```tsx\n{ui_code}\n```\n"
        )
        mockup_file.write_text(content)

        # Extract components if it's a complex mockup
        if "export const" in ui_code:
            self._extract_stitch_components(mockup_id, ui_code)

        return mockup_url

    def _extract_stitch_components(self, mockup_id: str, code: str):
        """Extract individual components from Stitch code."""
        components_dir = self.ace_dir / "ui_mockups" / "components" / mockup_id
        components_dir.mkdir(parents=True, exist_ok=True)

        # Simple extraction of exported constants
        component_matches = re.finditer(
            r"export const (\w+) =.*?=>.*?;",
            code,
            re.DOTALL
        )
        for match in component_matches:
            name, content = match.group(1), match.group(0)
            (components_dir / f"{name}.tsx").write_text(content)

    def _simulate_stitch_api(self, description: str) -> str:
        """Simulate a real Stitch API call."""
        return (
            f"export const Mockup = () => "
            f"<div className='p-4'>Mockup for {description}</div>;"
        )

    def ui_sync(self, url: str):
        """Sync UI code from Google Stitch (simulated)."""
        # Extract mockup_id from URL
        mockup_id = url.split("/")[-1]
        mockup_file = self.ace_dir / "ui_mockups" / f"{mockup_id}.md"

        if not mockup_file.exists():
            return f"// Error: Mockup {mockup_id} not found."

        content = mockup_file.read_text()
        # Extract code block from the mockup file
        code_match = re.search(
            r"```(?:tsx|jsx|html|javascript|typescript)?\n(.*?)\n```",
            content,
            re.DOTALL,
        )
        if code_match:
            return code_match.group(1)

        return f"// Error: No code found in mockup {mockup_id}."

    def prune_agent_memory(self, agent_id: str, threshold: int = 0) -> int:
        agents_config = self.load_agents()
        agent = next(
            (a for a in agents_config.agents if a.id == agent_id), None
        )
        if not agent:
            return 0
        return self.prune_memory(agent, threshold)

    def prune_memory(self, agent: Agent, threshold: int = 0) -> int:
        playbook_path = self.base_path / agent.memory_file
        if not playbook_path.exists():
            return 0

        content = playbook_path.read_text()
        pattern = (
            r"<!-- \[(str|mis)-([^\]]+)\]\s+helpful=(\d+)\s+harmful=(\d+)"
            r"\s*::\s*(.*?) -->"
        )

        pruned_count = 0

        def prune_match(match):
            nonlocal pruned_count
            helpful = int(match.group(3))
            harmful = int(match.group(4))

            if harmful - helpful > threshold:
                pruned_count += 1
                return f"<!-- [PRUNED] {match.group(0)} -->"
            return match.group(0)

        new_content = re.sub(pattern, prune_match, content)
        if pruned_count > 0:
            playbook_path.write_text(new_content)
        return pruned_count
