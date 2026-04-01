import os
import re
import subprocess
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

    def create_agent(self, id: str, name: str, role: str, email: Optional[str] = None) -> Agent:
        config = self.load_agents()
        if any(a.id == id for a in config.agents):
            raise ValueError(f"Agent with ID {id} already exists.")

        if not email:
            email = f"{id}@ace.local"

        memory_file = f".cursor/rules/{role}.mdc"
        new_agent = Agent(id=id, name=name, role=role, email=email, memory_file=memory_file)
        config.agents.append(new_agent)
        self.save_agents(config)
        return new_agent

    # --- Context & Execution ---

    def get_task_framing(self, task_type: TaskType, module: str) -> str:
        framing = {
            TaskType.IMPLEMENT: (
                f"You are implementing new functionality in {module}. Follow the playbook strategies. "
                "Write back new learnings in the write-back section."
            ),
            TaskType.REVIEW: (
                f"You are reviewing code in {module}. Identify deviations from playbook strategies. "
                "Add any new pitfalls to the write-back section."
            ),
            TaskType.DEBUG: (
                f"You are debugging an issue in {module}. If the root cause reveals a new pattern, "
                "document it as [mis-XXX] in write-back."
            ),
            TaskType.REFACTOR: (
                f"You are refactoring code in {module}. Ensure that the refactoring adheres to the "
                "architectural decisions and strategies in the playbook."
            ),
            TaskType.PLAN: (
                f"You are planning a task in {module}. Outline the steps and consider the impact on "
                "existing strategies and decisions."
            ),
        }
        return framing.get(task_type, "")

    def build_context(
        self, path: Optional[str] = None, task_type: TaskType = TaskType.IMPLEMENT, agent_id: Optional[str] = None
    ) -> Tuple[str, Optional[str]]:
        context_parts = []

        # 1. Global rules
        global_rules_file = self.cursor_rules_dir / "_global.mdc"
        if global_rules_file.exists():
            context_parts.append(f"### GLOBAL RULES\n{global_rules_file.read_text()}")

        # 2. Resolve agent and playbook
        resolved_agent_id = agent_id
        if not resolved_agent_id and path:
            resolved_agent_id = self.resolve_owner(path)

        if resolved_agent_id:
            agents_config = self.load_agents()
            agent = next((a for a in agents_config.agents if a.id == resolved_agent_id), None)
            if agent:
                playbook_path = self.base_path / agent.memory_file
                if not playbook_path.exists():
                    playbook_path = self.cursor_rules_dir / f"{agent.role}.mdc"

                if playbook_path.exists():
                    context_parts.append(f"### AGENT PLAYBOOK ({agent.role})\n{playbook_path.read_text()}")

        # 3. Recent decisions (ADRs)
        if self.decisions_dir.exists():
            decisions = sorted(list(self.decisions_dir.glob("*.md")), key=lambda x: x.stat().st_mtime, reverse=True)[:3]
            if decisions:
                context_parts.append("### RECENT DECISIONS")
                for d in decisions:
                    context_parts.append(f"#### {d.name}\n{d.read_text()}")

        # 4. Session continuity
        config = self.load_config()
        if self.sessions_dir.exists():
            session_files = sorted(list(self.sessions_dir.glob("*.md")), key=lambda x: x.stat().st_mtime, reverse=True)
            num_sessions = {TokenMode.LOW: 1, TokenMode.MEDIUM: 3, TokenMode.HIGH: 5}.get(config.token_mode, 1)
            recent_sessions = session_files[:num_sessions]
            if recent_sessions:
                context_parts.append("### RECENT SESSIONS")
                for s in recent_sessions:
                    context_parts.append(f"#### Session: {s.name}\n{s.read_text()}")

        # 5. Task framing
        module_name = path if path else "the project"
        framing = self.get_task_framing(task_type, module_name)
        context_parts.append(f"### TASK FRAMING\n{framing}")

        return "\n\n".join(context_parts), resolved_agent_id

    # --- Reflection Engine ---

    def list_sessions(self) -> List[Dict]:
        if not self.sessions_dir.exists():
            return []
        session_files = sorted(list(self.sessions_dir.glob("*.md")), key=lambda x: x.stat().st_mtime, reverse=True)
        sessions = []
        for s in session_files:
            content = s.read_text()
            # Extract basic metadata from markdown
            command_match = re.search(r"- \*\*Command\*\*: `(.*?)`", content)
            agent_match = re.search(r"- \*\*Agent ID\*\*: `(.*?)`", content)
            sessions.append({
                "id": s.stem.replace("session_", ""),
                "command": command_match.group(1) if command_match else "unknown",
                "agent_id": agent_match.group(1) if agent_match else "unknown",
                "timestamp": datetime.fromtimestamp(s.stat().st_mtime).isoformat()
            })
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
            "You are an ACE Reflection Engine. Your task is to analyze the output of a coding agent session "
            "and extract structured learnings.\n\n"
            "Look for:\n"
            "1. **Strategies [str-XXX]**: Successful patterns, helpful libraries, or effective approaches.\n"
            "2. **Pitfalls [mis-XXX]**: Bugs encountered, harmful patterns, or things to avoid.\n"
            "3. **Decisions [dec-XXX]**: Architectural choices made during the task.\n\n"
            "Format your output EXACTLY as follows:\n"
            "[str-NEW] helpful=1 harmful=0 :: <description of the strategy>\n"
            "[mis-NEW] helpful=0 harmful=1 :: <description of the pitfall>\n"
            "[dec-NEW] :: <description of the decision>\n\n"
            "Only include items that are clearly supported by the session output. If no new learnings are found, "
            'return "No new learnings."\n\n'
            f"Session Output:\n{session_output}\n"
        )
        try:
            message = client.messages.create(
                model="claude-3-5-sonnet-20241022", max_tokens=1024, messages=[{"role": "user", "content": prompt}]
            )
            if isinstance(message.content, list):
                return "".join([block.text for block in message.content if hasattr(block, "text")])
            return str(message.content)
        except Exception as e:
            return f"Error during reflection: {e}"

    def parse_reflection_output(self, reflection_text: str) -> List[Dict]:
        updates = []
        pattern = r"\[(str|mis|dec)-([^\]]+)\](?:\s+helpful=(\d+)\s+harmful=(\d+))?\s*::\s*(.*)"
        for line in reflection_text.splitlines():
            match = re.search(pattern, line)
            if match:
                updates.append(
                    {
                        "type": match.group(1),
                        "id": match.group(2),
                        "helpful": int(match.group(3)) if match.group(3) else 0,
                        "harmful": int(match.group(4)) if match.group(4) else 0,
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
            existing_pattern = (
                rf"<!-- \[{update_type}-{update_id}\](?:\s+helpful=(\d+)\s+harmful=(\d+))?\s*::\s*(.*?) -->"
            )
            match = re.search(existing_pattern, content)

            if match:
                old_h, old_m = int(match.group(1) or 0), int(match.group(2) or 0)
                new_h, new_m = old_h + update["helpful"], old_m + update["harmful"]
                new_line = f"<!-- [{update_type}-{update_id}]"
                if update_type != "dec":
                    new_line += f" helpful={new_h} harmful={new_m}"
                new_line += f" :: {update['description']} -->"
                content = content.replace(match.group(0), new_line)
            else:
                if update_id == "NEW":
                    existing_ids = re.findall(rf"\[{update_type}-(\d+)\]", content)
                    next_id = max([int(i) for i in existing_ids] + [0]) + 1
                    update_id = f"{next_id:03d}"

                update_str = f"[{update_type}-{update_id}]"
                if update_type != "dec":
                    update_str += f" helpful={update['helpful']} harmful={update['harmful']}"
                new_line = f"<!-- {update_str} :: {update['description']} -->"

                section_map = {
                    "str": "## Strategier & patterns",
                    "mis": "## Kända fallgropar",
                    "dec": "## Arkitekturella beslut",
                }
                header = section_map.get(update_type)
                if header and header in content:
                    parts = content.split(header)
                    content = parts[0] + header + "\n" + new_line + parts[1]
                else:
                    content += f"\n\n{header}\n{new_line}"

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
            context_match = re.search(r"## Context\n(.*?)\n\n## Decision", content, re.DOTALL)
            decision_match = re.search(r"## Decision\n(.*?)\n\n## Consequences", content, re.DOTALL)
            consequences_match = re.search(r"## Consequences\n(.*)", content, re.DOTALL)

            decisions.append(Decision(
                id=adr_path.stem,
                title=title_match.group(1) if title_match else adr_path.name,
                status=status_match.group(1) if status_match else "unknown",
                created_at=date_match.group(1) if date_match else datetime.now().isoformat(),
                agent_id=agent_match.group(1) if agent_match else None,
                context=context_match.group(1).strip() if context_match else "",
                decision=decision_match.group(1).strip() if decision_match else "",
                consequences=consequences_match.group(1).strip() if consequences_match else ""
            ))
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
                int(re.search(r"ADR-(\d+)", f.name).group(1)) for f in existing_adrs if re.search(r"ADR-(\d+)", f.name)
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
        content = (
            f"# {adr_id}: {title}\n"
            f"- **Status**: {status}\n"
            f"- **Date**: {new_decision.created_at}\n"
            f"- **Agent**: {agent_id or 'User'}\n\n"
            f"## Context\n{context}\n\n"
            f"## Decision\n{decision}\n\n"
            f"## Consequences\n{consequences}\n"
        )
        adr_file.write_text(content)
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

    def send_mail(self, to_agent: str, from_agent: str, subject: str, body: str) -> MailMessage:
        agent_mail_dir = self.mail_dir / to_agent
        agent_mail_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        msg_id = f"{timestamp}_{from_agent}"
        msg = MailMessage(id=msg_id, **{"from": from_agent, "to": to_agent}, subject=subject, body=body)

        with open(agent_mail_dir / f"{msg_id}.yaml", "w") as f:
            yaml.dump(msg.model_dump(by_alias=True), f)
        return msg

    # --- RALPH Loop Engine ---

    def run_loop(
        self,
        prompt: str,
        test_cmd: str,
        max_iterations: int = 10,
        path: Optional[str] = None,
        agent_id: Optional[str] = None,
    ):
        """Iteratively run: Context Refresh -> Execute -> Verify -> Reflect -> Repeat."""
        iteration = 0
        success = False
        
        while iteration < max_iterations:
            iteration += 1
            print(f"\n[RALPH] Iteration {iteration}/{max_iterations}")
            
            # 1. Context Refresh & Build
            context, resolved_agent_id = self.build_context(path=path, task_type=TaskType.IMPLEMENT, agent_id=agent_id)
            
            # 2. Execute (Mocking cursor-agent call for now, as it's a CLI tool)
            # In a real scenario, this would call 'ace run' or similar logic
            print(f"[RALPH] Executing task: {prompt[:50]}...")
            
            # 3. Verify (Run tests)
            print(f"[RALPH] Verifying with: {test_cmd}")
            result = subprocess.run(test_cmd, shell=True, capture_output=True, text=True)
            
            if result.returncode == 0:
                print("[RALPH] ✅ Verification successful!")
                success = True
                break
            else:
                print(f"[RALPH] ❌ Verification failed (Exit code: {result.returncode})")
                # 4. Reflect (In a real scenario, we'd pass the error to the agent)
                # For now, we'll just log it and continue
            
        return success, iteration

    # --- SOP Engine ---

    def onboard_agent(self, agent_id: str):
        """Run onboarding SOP for an agent."""
        agents_config = self.load_agents()
        agent = next((a for a in agents_config.agents if a.id == agent_id), None)
        if not agent:
            raise ValueError(f"Agent {agent_id} not found.")

        onboarding_file = self.ace_dir / f"onboarding_{agent_id}.md"
        content = f"""# Onboarding: {agent.name} ({agent.id})
- **Role**: {agent.role}
- **Responsibilities**: {', '.join(agent.responsibilities) if agent.responsibilities else 'None'}
- **Memory File**: {agent.memory_file}
- **Status**: {agent.status}

## Subsystem Status
- [ ] Review existing codebase in {', '.join(agent.responsibilities) if agent.responsibilities else 'None'}
- [ ] Identify technical debts
- [ ] Propose initial strategies

## Handover Notes
No handover notes available.
"""
        onboarding_file.write_text(content)
        return onboarding_file

    def review_pr(self, pr_id: str, agent_id: str):
        """Run PR review SOP for an agent."""
        # Mocking PR review logic
        review_file = self.ace_dir / f"review_{pr_id}_{agent_id}.md"
        content = f"""# PR Review: {pr_id}
- **Reviewer**: {agent_id}
- **Date**: {datetime.now().isoformat()}

## Findings
- [ ] Check for deviations from playbook strategies
- [ ] Identify new pitfalls
- [ ] Verify architectural decisions

## Conclusion
Pending review.
"""
        review_file.write_text(content)
        return review_file

    # --- Google Stitch Integration ---

    def ui_mockup(self, description: str, agent_id: str):
        """Generate a UI mockup (Mocked for now)."""
        # In a real scenario, this would call Google Stitch API
        mockup_id = f"stitch_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        mockup_url = f"https://stitch.google.com/canvas/{mockup_id}"
        return mockup_url

    def ui_sync(self, url: str):
        """Sync UI code from Google Stitch (Mocked for now)."""
        # In a real scenario, this would fetch code from the URL
        return f"// Synced from {url}\nexport const Component = () => <div>Synced Component</div>;"

    def prune_agent_memory(self, agent_id: str, threshold: int = 0) -> int:
        agents_config = self.load_agents()
        agent = next((a for a in agents_config.agents if a.id == agent_id), None)
        if not agent:
            return 0
        return self.prune_memory(agent, threshold)

    def prune_memory(self, agent: Agent, threshold: int = 0) -> int:
        playbook_path = self.base_path / agent.memory_file
        if not playbook_path.exists():
            return 0

        content = playbook_path.read_text()
        pattern = r"<!-- \[(str|mis)-([^\]]+)\]\s+helpful=(\d+)\s+harmful=(\d+)\s*::\s*(.*?) -->"

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
