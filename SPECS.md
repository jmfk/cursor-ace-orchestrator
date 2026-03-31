# ACE Spec Documents & Locations

This document outlines the structure and location of specification documents within the **Cursor ACE Orchestrator** ecosystem.

## 1. Project-Level Specs (`.ace/specs/`)

Each feature or module in a project has its own directory within the `.ace/specs/` folder. Specs follow the **Living Specs** architecture (Intent, Constraints, Implementation, Verification).

### Location: `.ace/specs/<feature-slug>/`

| File | Layer | Owner | Description |
|---|---|---|---|
| `intent.md` | **Intent** | Human | High-level goals, user stories, and success criteria. Stable. |
| `constraints.md` | **Constraints** | Human + Agent | Security, performance, and technical boundaries. Semi-stable. |
| `implementation.md` | **Implementation** | Agent | Technical approach, data models, and API contracts. Fluid/Disposable. |
| `verification.md` | **Verification** | Agent + Human | Acceptance criteria and test cases (e.g., Gherkin). Executable. |
| `meta.json` | **Metadata** | System | Tracks format used, outcome, and experiment IDs. |

---

## 2. Meta-Level Specs (`.ace-meta/`)

Used when ACE is working on itself (**Meta Mode**). These specs define the core orchestrator's behavior and cross-project learning logic.

### Location: `.ace-meta/`

| File/Directory | Description |
|---|---|
| `ownership.json` | Registry for ACE's own internal modules. |
| `experiments/` | Results and active trials for spec formats and prompt variants. |
| `cross-project/` | Aggregated, anonymized learnings from all managed projects. |
| `decisions/` | ADRs (Architectural Decision Records) for the ACE Orchestrator itself. |

---

## 3. Global Project Memory (`AGENTS.md`)

The root-level `AGENTS.md` acts as the primary entry point for all agents (Cursor, Claude Code, etc.) to understand the project's overall structure and standards.

### Location: `<repo-root>/AGENTS.md`

- **Project Overview**: Stack and purpose.
- **Role Registry**: Mapping of roles to `.mdc` playbooks.
- **Global Standards**: TDD, YAGNI, DRY, and coding conventions.
- **Recent Decisions**: Summary of the latest ADRs.

---

## 4. Agent Playbooks (`.cursor/rules/`)

Role-specific knowledge bases that act as the agent's "long-term memory" for a specific module.

### Location: `.cursor/rules/<role>.mdc`

- **Ownership**: Primary modules and dependencies.
- **Architectural Decisions**: Module-specific ADR summaries.
- **Strategies & Patterns**: `[str-XXX]` entries with helpful/harmful counters.
- **Known Pitfalls**: `[mis-XXX]` entries to avoid repeating mistakes.
