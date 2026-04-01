# Cursor ACE Orchestrator Workflow

This document describes the end-to-end workflow for the **Cursor ACE Orchestrator**, from initialization to the automated write-back loop.

## 1. Initialization (`ace init`)
The workflow begins by preparing the repository for agent orchestration.
- Creates the `.ace/` directory for tracked metadata.
- Creates the `.ace-local/` directory for local session state (git-ignored).
- Generates a default `AGENTS.md` in the root if it doesn't exist.
- Sets up the `agents.yaml` registry and `ownership.yaml`.

## 2. Defining Agents & Ownership (`ace agent create` / `ace own`)
Before running tasks, agents are defined and code modules are mapped to them.
- **Create Agent**: `ace agent create --name Aegis --role auth`
- **Assign Ownership**: `ace own src/auth --agent <agent-id>`
- **Registry Update**: The orchestrator updates `.ace/agents.yaml` and `.ace/ownership.yaml`.
- **Playbook Creation**: A corresponding `.cursor/rules/<role>.mdc` is created using a template if it doesn't exist.

## 3. Execution Loop (`ace run` & `ace loop`)
The core loop consists of four distinct phases, with an optional iterative wrapper.

### Phase A: Context Building
When a user runs `ace run "task"` or `ace loop "task"`, the orchestrator:
1. **Resolves Agent**: Finds the owner of the target file(s) via longest-prefix match in `ownership.yaml`.
2. **Gathers Memory**: 
   - Reads global rules (`_global.mdc`).
   - Reads the agent-specific playbook (`<role>.mdc`).
   - Fetches recent decisions (ADRs) from `.ace/decisions/`.
   - Retrieves state from the last session in `.ace/sessions/`.
   - Injects shared learnings from `.ace/shared-learnings.mdc`.
3. **Composes Prompt**: Wraps the user task with a "Task Frame" (e.g., `implement`, `debug`, `review`) and the gathered context.
4. **Token Management**: Applies context pruning based on the selected Token Mode (Low, Medium, High).

### Phase B: Execution (RALPH Cycle)
- **Execute**: The orchestrator invokes the `cursor-agent` in headless mode.
- **Verify (TDD)**: If running via `ace loop`, the orchestrator executes the specified test command (e.g., `npm test`).
- **Analyze**: If tests fail, a reflection prompt analyzes the failure to update the memory for the next iteration.
- **Coordinate (SOP-driven)**: If multiple agents are involved, they follow the **Consensus SOP** via **Agent Mail**.
- **UI/UX Mockup**: If the task involves UI, the agent uses **Google Stitch** to generate mockups and extract code before implementation.
- **Review**: Other agents may perform a **PR Review SOP** on the changes if the Token Mode is set to Medium or High.

### Phase C: Reflection (Write-back)
Once the task is completed (or max iterations reached):
1. **Reflection Prompt**: The orchestrator sends the agent's output and test results to a reflection model.
2. **Extraction**: The model identifies:
   - **Strategies** (`[str-XXX]`) that worked or failed (updating `helpful`/`harmful` counters).
   - **Pitfalls** (`[mis-XXX]`) encountered.
   - **Decisions** (`[dec-XXX]`) for ADRs.
3. **Delta Update**: A JSON delta is generated for the playbook.
4. **Audit (Optional)**: If Token Mode is High, a **Subsystem Health SOP** is triggered to check for DRY/YAGNI violations.

### Phase D: Persistence & Best Practices
- **Playbook Update**: The `.cursor/rules/<role>.mdc` is updated incrementally.
- **Session Logging**: Detailed logs are stored in `.ace/sessions/`.
- **Principles Enforcement**:
  - **TDD**: No code without a failing test first.
  - **YAGNI**: Implement only what is needed to pass the current test.
  - **DRY**: Shared utilities are extracted if used in >1 place.

## 4. Memory Management (`ace memory`)
Over time, the orchestrator maintains the playbooks:
- **Pruning**: `ace memory prune` removes strategies where `harmful` counts significantly outweigh `helpful` counts.
- **History**: `ace memory history` allows the user to browse past session logs.

---

## Summary Diagram

```mermaid
graph TD
    A[User: ace run/loop] --> B[Context Builder]
    B --> C[Resolve Agent & Memory]
    C --> D[Execute cursor-agent]
    D --> E{Tests Pass?}
    E -- No (ace loop) --> F[Analyze Failure]
    F --> G[Update Memory]
    G --> D
    E -- Yes --> H[Reflection Model]
    H --> I[Extract Delta]
    I --> J[Update .mdc Playbook]
    I --> K[Log Session .md]
    J --> L[End Task]
    K --> L
```
