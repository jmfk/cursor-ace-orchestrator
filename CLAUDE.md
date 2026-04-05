# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

ACE (Automated Coding Environment Orchestrator) is a Python-based multi-agent orchestration system that implements the **ROLF Cycle** (Reasoning, Action, Learning, Progress, Halt) to autonomously manage complex development tasks. Agents have long-term memory, can coordinate via consensus protocols, and improve through reflection.

## Commands

```bash
make install        # Install in editable mode (pip install -e .)
make test           # Run all tests (pytest tests/)
make rolf           # Run bootstrap ROLF loop (python3 rolf_loop.py)
make eval           # Evaluate commits using heuristics
make eval-llm       # Evaluate commits using LLM
make report         # Generate markdown report

pytest tests/test_specific.py  # Run a single test file
pytest --cov=ace_lib           # Run with coverage
```

After install, the CLI entry points are:
```bash
ace loop "task description" --test "pytest tests/test_x.py" --max 10
ace init            # Initialize .ace/ directories
ace agent create    # Register agents
ace own <path> --agent <id>   # Assign module ownership
ace memory index    # Index playbooks into vector DB
ace debate          # Multi-agent consensus
sqe                 # System Quality Evaluator
```

## Architecture

### Core Execution Path

```
ace.py (Typer CLI)
  └─→ ACEService (ace_lib/services/ace_service.py)   ← central orchestrator
        ├─→ Context Builder     — assembles prompts with memory + SOP
        ├─→ Executor            — runs agents (cursor-agent or LLM)
        ├─→ ReflectionEngine (reflection.py) — extracts learnings post-run
        ├─→ HierarchicalPlanner (ace_lib/planner/) — task decomposition
        ├─→ SOP Engine (ace_lib/sop/) — standard operating procedures
        ├─→ ChromaDB vector store — indexed playbook memory
        └─→ Token Manager — cost tracking
```

### State & Memory

ACE uses two `.ace/` directories:
- `.ace/` — git-tracked metadata: `agents.yaml`, `ownership.yaml`, `sessions/`, `decisions/`, `mail/`, `specs/`, `planner_memory.jsonl`
- `.ace-local/` — git-ignored local session state

Long-term memory lives in `.cursor/rules/*.mdc` files (Markdown + Comments format). Shared cross-agent learnings are in `.ace/shared-learnings.mdc`. The reflection engine tags learnings as `[str-XXX]` (strategies), `[mis-XXX]` (pitfalls), or `[dec-XXX]` (decisions).

### Key Subsystems

**Planning** (`ace_lib/planner/`): `HierarchicalPlanner` decomposes tasks into a `PlanTree`. `GeminiClient` wraps Google Gemini for planning LLM calls. `ContextCurator` trims context to fit token budgets. `DiffGate` validates plan-to-code transitions.

**Agent Coordination**: Agents own modules via longest-prefix matching in `ownership.yaml`. `AgentMail` (`.ace/mail/`) handles async inter-agent messaging. The MACP debate mechanism (`ace debate`) uses an LLM referee for consensus.

**SQE** (`sqe/`): An independent validation loop — `PRDAnalyzer` decomposes requirements, `CodeExaminer` checks implementation, `TestBuilder` generates tests, `Reporting` produces HTML/Markdown output.

**FastAPI backend** (`ace_api/main.py`): Web interface with Jinja2 templates; secondary to the CLI.

**Google Stitch** (`ace_lib/stitch/`): UI mockup generation and visual verification.

### Data Models

`ace_lib/models/schemas.py` defines the core Pydantic models: `Config`, `Agent`, `Decision`, and related types. `rolf.yaml` configures the ROLF loop (model, budget, retry thresholds).

## Key Files to Read First

- `ARCHITECTURE.md` — detailed system design and data flow diagrams
- `WORKFLOW.md` — end-to-end ROLF workflow walkthrough
- `CLI_REFERENCE.md` — full CLI command reference
- `ace_lib/services/ace_service.py` — the heart of orchestration logic
- `rolf.yaml` — runtime configuration

## Development Status

Phase 11 (Advanced Autonomy / Deep LLM Integration) is in progress. Phase 12 is pending. Phases 1–10 are complete. See `plan.md` for the full roadmap.
