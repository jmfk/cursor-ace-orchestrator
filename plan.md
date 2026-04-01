# Cursor ACE Orchestrator Implementation Plan

This plan outlines the step-by-step implementation of the Cursor ACE Orchestrator, a Python-based CLI tool designed to provide long-term memory and coordination for coding agents.

## Phase 1: Core Infrastructure (Completed)
- [x] **1.1 Environment Setup**: Initialize Python project with `poetry` or `pip` + `venv`. Install dependencies: `typer`, `ruamel.yaml`, `pydantic`, `rich`, `anthropic`, `fastapi`, `uvicorn`.
- [x] **1.2 Core Directory Structure**: Implement `ace init` to create `.ace/` (agents.yaml, ownership.yaml, mail/, sessions/, decisions/, specs/) and `.ace-local/`.
- [x] **1.3 TDD Infrastructure**: Set up `pytest` and create comprehensive unit tests for Registry, Path matching, and SOP logic.
- [x] **1.4 Agent Registry**: Implement `ace agent create` and `ace agent list` to manage `agents.yaml`.
- [x] **1.5 Ownership Registry**: Implement `ace own` and `ace who` logic using longest-prefix matching for file paths.
- [x] **1.6 MDC Templates**: Create base `.cursor/rules/*.mdc` templates with the required sections (Ownership, Decisions, Strategies, Pitfalls).

## Phase 2: Context & Execution (Completed)
- [x] **2.1 Context Builder Logic**: Implement `ace build-context` to compose the context slice (global rules + role playbook + recent ADRs + task framing + session continuity).
- [x] **2.2 Task Type Framing**: Define structured prompt prefixes for `implement`, `review`, `debug`, `refactor`, and `plan`.
- [x] **2.3 Executor Wrapper**: Implement `ace run` to wrap `cursor-agent`. Capture output, exit codes, and log to sessions.
- [x] **2.4 Session Logging**: Implement automatic logging of every `ace run` execution to `.ace/sessions/` in Markdown format.
- [x] **2.5 Token Mode Configuration**: Implement `ace config tokens --mode [low|medium|high]` to control context depth.
- [x] **2.6 Session Continuity**: Implement logic to inject the most recent relevant session logs into the Context Builder based on Token Mode.

## Phase 3: Memory & Reflection (Completed)
- [x] **3.1 Reflection Engine**: Implement the LLM reflection prompt (using Claude) to extract learnings (`[str-XXX]`, `[mis-XXX]`, `[dec-XXX]`) from agent output.
- [x] **3.2 Delta Update Parser**: Create logic to parse structured reflection output and handle ID assignment for new entries.
- [x] **3.3 Playbook Updater**: Implement safe, incremental updates to `.mdc` files that preserve existing structure and frontmatter.
- [x] **3.4 Helpful/Harmful Counters**: Implement logic to increment/decrement strategy counters based on task success/failure in RALPH loop.
- [x] **3.5 ADR Management**: Implement `ace decision add` and `ace decision list` to manage Architectural Decision Records in `.ace/decisions/`.
- [x] **3.6 Memory Pruning**: Implement `ace memory prune` to archive or remove "harmful" strategies (harmful - helpful > threshold).
- [x] **3.7 Global Memory Sync**: Implement `ace memory sync` to keep `AGENTS.md` in sync with the Agent Registry and recent Decisions.

## Phase 4: RALPH Loop & Coordination (Completed)
- [x] **4.1 RALPH Loop Engine**: Implement `ace loop` to iteratively run: Context Refresh -> Execute -> Verify (Tests) -> Reflect -> Update Playbook -> Repeat.
- [x] **4.2 Agent Mail System**: Implement the internal messaging system in `.ace/mail/` with `inbox/` and `sent/` per agent using YAML storage.
- [x] **4.3 Consensus Protocol**: Implement `ace debate` where agents exchange perspectives via Mail, mediated by an LLM-referee with escalation support.
- [x] **4.4 SOP Engine**: Implement Standard Operating Procedures for `onboarding`, `audit`, `pr-review`, and `security-audit`.
- [x] **4.5 Google Stitch Integration**: Implement `ace ui mockup` and `ace ui sync` to interface with Google Labs design tools (API + Agent fallback).

## Phase 5: Service & API (Completed)
- [x] **5.1 FastAPI Architecture**: Refactor core logic into `ACEService` to support both CLI and FastAPI backend.
- [x] **5.2 CLI-to-API Bridge**: Implement `api_call` in CLI to prefer FastAPI backend if available, with local fallback.
- [x] **5.3 FastAPI Backend Implementation**: Create `ace_api/main.py` with endpoints for all core ACE functionalities.
- [x] **5.4 Documentation**: Finalize CLI `--help` and ensure all commands are correctly mapped to service/API.

## Phase 6: Advanced Features & Refinement (Completed)
- [x] **6.1 Living Specs Implementation**: Implement `ace spec` commands to manage feature-specific specification layers (Intent, Constraints, Implementation, Verification).
- [x] **6.2 Cross-Project Learning**: Implement `ace meta cross-project-export/import` to share anonymized learnings between projects.
- [x] **6.3 Meta Mode Enhancements**: Implement `ace meta self-audit` for ACE to audit its own codebase and memory.
- [x] **6.4 Token Consumption Monitoring**: Implement `ace token-stats` to track and report token usage and costs per agent/session.
- [x] **6.5 Multi-Turn Debate**: Support multi-turn debate logic in `ace debate` with LLM mediation and consensus reporting.
- [x] **6.6 Security Audit SOP**: Implement `ace agent security-audit` to perform security checks on agent-owned modules.
- [x] **6.7 Agentic Feedback Loop**: Automate success/failure flagging in RALPH loop based on test-output, connecting write-back to CI/CD.

## Phase 7: Future Directions (In Progress)
- [x] **7.1 Vectorized Memory**: Replace flat `.mdc` with embedding-based search for large playbooks using a vector database.
- [ ] **7.2 IDE Extension Integration**: Build a native Cursor/VSCode extension to provide a GUI for ACE Orchestrator.
- [ ] **7.3 Advanced Multi-Agent Consensus**: Support more complex debate formats, voting mechanisms, and human-in-the-loop escalation UI.
- [ ] **7.4 Performance Optimization**: Profile and optimize core logic for extremely large codebases and high-frequency agent calls.
- [ ] **7.5 Security Hardening**: Conduct a formal security audit and implement sandboxing for agent execution.
- [ ] **7.6 Multi-Agent Consensus Debate**: Implement explicit consensus logic where multiple agents must "sign off" on a change before it's finalized.
- [ ] **7.7 Shared "Coffee Break" Context**: Implement a shared `.ace/shared-learnings.mdc` for cross-pollination of general architectural patterns.
- [ ] **7.8 Token Consumption Modes (L/M/H)**: Refine the impact of Token Modes on debate depth and context composition.
- [ ] **7.9 Google Stitch Visual Verification**: Implement E2E tests (Playwright) to validate that implemented code matches Stitch mockups.
