# ACE Development Guide

This document provides information for contributors and developers working on the ACE Orchestrator.

## 📂 Project Structure

- `ace.py`: The main CLI entry point (using Typer).
- `ace_lib/`: Core library containing logic and services.
  - `services/ace_service.py`: The central orchestrator logic.
  - `planner/`: Hierarchical task planning and decomposition.
  - `models/schemas.py`: Pydantic models for configuration, agents, and data.
  - `utils/`: Shared utilities (profiler, etc.).
- `rolf_loop.py`: The bootstrapping script for the ROLF cycle.
- `rolf.yaml`: Configuration for the ROLF loop.
- `analyze_commits.py`: Utility for evaluating git commits using LLMs.
- `Makefile`: Development commands for building, installing, and reporting.
- `.ace/`: (Created after `ace init`) Central database for agents, mail, and sessions.
- `.cursor/rules/`: (Created after `ace init`) Agent-specific "Playbooks" (long-term memory).

## 🧪 Running Tests

ACE uses `pytest` for testing.

```bash
# Run all tests
pytest

# Run tests with coverage
pytest --cov=ace_lib
```

## 🏗 Building Executables

ACE can be built into a self-contained executable using PyInstaller.

```bash
# Build 'ace' executable
make build-exe

# Install 'ace' binary to /usr/local/bin
make install-exe

# Build 'rolf' (the bootstrapping loop) executable
make build-rolf-exe
```

## 📈 Performance & Evaluation

### Commit Evaluation
ACE can evaluate recent git commits using LLMs to assign an "improvement score".

```bash
# Evaluate recent commits using heuristics
make eval

# Evaluate using LLM analysis
make eval-llm
```

### Generating Reports
Generate value reports to visualize project progress.

```bash
# Generate a markdown report with commit value graphs
make report

# Generate a comprehensive report (Time-series + Milestones + Commits)
make comprehensive
```

## 🤝 Contribution Guidelines

### 1. SOP-Driven Development
All major workflows (onboarding, reviews, consensus) follow Standard Operating Procedures. When implementing new features, ensure they align with the existing SOPs defined in `SPECS.md` and `WORKFLOW.md`.

### 2. Memory Persistence
Always consider how new features interact with the agent's long-term memory (`.mdc` files). Learnings should be extracted and persisted through the reflection loop.

### 3. Multi-Agent Consensus
If a change affects multiple subsystems, it must be resolved via the **Multi-Agent Consensus Protocol (MACP)**.

## 📝 Reflection Protocol
When finishing a task, provide a reflection on what was learned using the following format in your commit messages or documentation:
- `[str-XXX] helpful=X harmful=Y :: <strategy>`
- `[mis-XXX] helpful=X harmful=Y :: <pitfall>`
- `[dec-XXX] :: <decision>`
