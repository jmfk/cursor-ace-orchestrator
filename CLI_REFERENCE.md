# ACE CLI Reference

The `ace` command-line interface provides tools for managing agents, memory, and autonomous development loops.

## 🛠 Core Commands

### `ace init`
Initialize the `.ace/` and `.ace-local/` directories and set up credentials.
- Creates: `agents.yaml`, `config.yaml`, `ownership.yaml`.
- Prompts for: `GOOGLE_API_KEY`, `CURSOR_API_KEY`.

### `ace loop`
Run the **ROLF Cycle** (Reasoning, Action, Learning, Progress, Halt) for a specific prompt.
- **Arguments**: `PROMPT` (The task to solve).
- **Options**:
  - `--test`, `-t`: Command to run tests (e.g., `pytest`).
  - `--max`, `-m`: Maximum number of iterations (default: 10).
  - `--path`, `-p`: Target file or module path.
  - `--agent`, `-a`: Explicit agent ID to use.
  - `--git-commit`, `-g`: Automatically commit on success.
  - `--max-spend`: Maximum spend in USD (default: 20.0).

### `ace run`
Execute a single command with ACE context injected.
- **Arguments**: `COMMAND` (The command to run).
- **Options**: Same as `ace loop`.

### `ace token-stats`
Report token usage and cost per agent/session.
- **Options**:
  - `--agent`, `-a`: Filter by agent ID.

---

## 🤖 Agent Management (`ace agent`)

### `ace agent create`
Register a new agent.
- **Options**: `--name`, `--role`, `--id`, `--email`, `--resp`.

### `ace agent list`
List all registered agents.

### `ace agent onboard`
Run the onboarding SOP for an agent.

### `ace agent review`
Run a PR review SOP for an agent.

### `ace agent audit`
Run a performance/memory audit for an agent.

---

## 🧠 Memory Management (`ace memory`)

### `ace memory index`
Index an agent's playbook into vectorized memory.

### `ace memory search`
Search vectorized memory for relevant strategies or pitfalls.

### `ace memory synthesize`
Synthesize shared memories from individual agent experiences.

### `ace memory prune`
Archive or remove "harmful" strategies based on helpfulness/harmfulness scores.

---

## 🤝 Consensus & Coordination (`ace macp`)

### `ace macp propose`
Create a new Multi-Agent Consensus Protocol (MACP) proposal.

### `ace macp list`
List all active and completed MACP proposals.

### `ace macp show`
Show details of a specific proposal, including votes and consensus summary.

### `ace debate`
Initiate a multi-turn debate between agents on a proposal.

---

## 📜 Living Specs (`ace spec`)

### `ace spec create`
Create a new Living Spec (Living documentation of intent and constraints).

### `ace spec list` / `ace spec show`
Manage and view Living Specs.

---

## 🖥 UI Integration (`ace ui`)

### `ace ui mockup`
Generate a UI mockup using Google Stitch.

### `ace ui sync`
Sync UI code from a Google Stitch Canvas.

---

## ⚙️ Meta Commands (`ace meta`)

### `ace meta self-audit`
ACE performs a comprehensive self-audit of its own codebase and memory.

### `ace meta cross-project-export` / `ace meta cross-project-import`
Share learnings across different projects.
