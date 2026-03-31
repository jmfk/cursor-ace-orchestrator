# Architecture: Cursor ACE Orchestrator

This document describes the high-level architecture, component interactions, and design principles of the **Cursor ACE Orchestrator**.

## 1. Architectural Overview

ACE Orchestrator is designed as a modular, event-driven orchestration layer that sits on top of coding agents (like `cursor-agent`). It follows a **Multi-Agent System (MAS)** pattern where responsibility is distributed across specialized "Mini-Team Agents".

### Core Design Principles
- **Contextual Specialization**: Agents only see the context relevant to their assigned subsystem.
- **Memory Persistence**: Long-term memory is stored in `.mdc` files and updated via a reflection loop.
- **SOP-Driven**: All major workflows (onboarding, reviews, consensus) follow Standard Operating Procedures.
- **Iterative Problem Solving**: Uses the **RALPH Cycle** (Reasoning, Action, Learning, Progress, Halt) to solve tasks.

---

## 2. System Components

### 2.1 Orchestration Layer (Python)
The core engine, built in Python, managing the lifecycle of tasks and agents.
- **CLI / API Wrapper**: Entry point for user commands or web requests (FastAPI).
- **Context Builder**: Composes the prompt-slice for each agent call.
- **Executor**: Runs the headless coding agent.
- **Token Manager**: Controls context depth and feature availability based on L/M/H modes.

### 2.2 Agent Registry & Ownership
- **Agents YAML (`.ace/agents.yaml`)**: Central database of agent identities, roles, and emails.
- **Ownership YAML (`.ace/ownership.yaml`)**: Mapping of file paths/modules to specific agent IDs.

### 2.3 Memory & Communication
- **Playbooks (`.cursor/rules/*.mdc`)**: Agent-specific long-term memory.
- **Agent Mail (`.ace/mail/`)**: Asynchronous, threaded messaging system for agent coordination.
- **Shared Learnings (`.ace/shared-learnings.mdc`)**: Global context for cross-pollination of patterns.

### 2.4 UI/UX Orchestration
- **Google Stitch**: Integrated via API/CLI to generate mockups and extract UI code (Tailwind/Flutter).

---

## 3. Data Flow (The RALPH Loop)

```mermaid
sequence_diagram
    participant U as User
    |participant O as Orchestrator
    participant C as Context Builder
    participant E as Executor (Agent)
    participant V as Verification (Tests)
    participant R as Reflection (LLM)

    U->>O: ace run/loop "task"
    O->>C: Build context (Memory + SOP + Token Mode)
    C-->>O: Injected Prompt
    loop RALPH Cycle
        O->>E: Execute task
        E-->>O: Code Changes
        O->>V: Run Tests / Lint
        V-->>O: Pass/Fail
        alt Fail
            O->>R: Analyze Failure
            R-->>O: Update Memory (.mdc)
        else Pass
            O->>R: Final Reflection
            R-->>O: Extract Delta-updates
            O->>O: Update Playbook & Changelog
        end
    end
    O->>U: Task Completed
```

---

## 4. Multi-Agent Consensus Protocol

When a task affects multiple subsystems:
1. **Conflict Detection**: Orchestrator identifies multiple owners.
2. **Debate**: Involved agents exchange proposals via **Agent Mail**.
3. **Referee**: A neutral `arch-agent` or LLM-referee evaluates the thread.
4. **Resolution**: If consensus is reached, the task proceeds. Otherwise, it escalates to the user.

---

## 5. Token Management Strategy

| Mode | Context Pruning | Asynchronous Features |
|---|---|---|
| **Low** | Strict (last 2 sessions) | None (Single agent only) |
| **Medium** | Moderate (last 5 sessions) | Basic Mail & Subscriptions |
| **High** | Full (All relevant memory) | Full Debate, QA Audits, Stitch Sync |

---

## 7. Development Lifecycle: From Bootstrap to Self-Hosting

The development of ACE Orchestrator follows a two-phase evolution:

### Phase 1: Bootstrapping (Temporary RALPH Loop)
Initially, a standalone Python script (`ralph_loop.py`) is used to orchestrate `cursor-agent` in headless mode. This script implements a simplified RALPH cycle to build the core components of ACE (CLI, Registry, Context Builder).
- **Status**: Active.
- **Outcome**: A functional `ace` CLI that can run its own loops.

### Phase 2: Self-Hosting (The ACE Loop)
Once the core system is stable, `ralph_loop.py` will be manually removed. The system will then use its own `ace loop` command to implement further features, SOPs, and optimizations.
- **Status**: Target.
- **Mechanism**: ACE uses its own internal logic, Agent Mail, and Consensus protocols to evolve itself.
