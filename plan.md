# Cursor ACE Orchestrator Implementation Plan

This plan outlines the step-by-step implementation of the Cursor ACE Orchestrator, a Python-based CLI tool designed to provide long-term memory and coordination for coding agents.

## Phase 1: Core Infrastructure (Completed)
- [x] **1.1 Environment Setup**: Initialize Python project with `poetry` or `pip` + `venv`. Install dependencies: `typer`, `ruamel.yaml`, `pydantic`, `rich`, `anthropic`.
- [x] **1.2 Core Directory Structure**: Implement `ace init` to create `.ace/` (agents.yaml, ownership.yaml, mail/, sessions/, decisions/) and `.ace-local/`.
- [x] **1.3 TDD Infrastructure**: Set up `pytest` and create initial unit tests for Registry and Path matching logic.
- [x] **1.4 Agent Registry**: Implement `ace agent create` and `ace agent list` to manage `agents.yaml`.
- [x] **1.5 Ownership Registry**: Implement `ace own` and `ace who` logic using longest-prefix matching for file paths.
- [x] **1.6 MDC Templates**: Create base `.cursor/rules/*.mdc` templates with the required sections (Ownership, Decisions, Strategies, Pitfalls).

## Phase 2: Context & Execution (Completed)
- [x] **2.1 Context Builder Logic**: Implement `ace build-context` to compose the context slice (global rules + role playbook + recent ADRs + task framing).
- [x] **2.2 Task Type Framing**: Define structured prompt prefixes for `implement`, `review`, `debug`, `refactor`, and `plan`.
- [x] **2.3 Executor Wrapper**: Implement `ace run` to wrap `cursor-agent` (or `claude-code`). Capture output and exit codes.
- [x] **2.4 Session Logging**: Implement automatic logging of every `ace run` execution to `.ace/sessions/` in Markdown format.
- [x] **2.5 Token Mode Configuration**: Implement `ace config tokens --mode [low|medium|high]` to control context depth.
- [x] **2.6 Session Continuity**: Implement logic to inject the most recent relevant session log into the Context Builder.

## Phase 3: Memory & Reflection (Completed)
- [x] **3.1 Reflection Engine**: Implement the LLM reflection prompt (using Claude) to extract learnings from agent output.
- [x] **3.2 Delta Update Parser**: Create logic to parse structured reflection output into `[str-XXX]`, `[mis-XXX]`, and `[dec-XXX]` updates.
- [x] **3.3 Playbook Updater**: Implement safe, incremental updates to `.mdc` files that preserve existing structure and frontmatter.
- [x] **3.4 Helpful/Harmful Counters**: Implement logic to increment/decrement strategy counters based on task success/failure.
- [x] **3.5 ADR Management**: Implement `ace decision add` and `ace decision list` to manage Architectural Decision Records in `.ace/decisions/`.
- [x] **3.6 Memory Pruning**: Implement `ace memory prune` to archive or remove "harmful" strategies (harmful > helpful).
- [x] **3.7 Global Memory Sync**: Implement logic to keep `AGENTS.md` in sync with the Agent Registry and recent Decisions.

## Phase 4: RALPH Loop & Coordination (Completed)
- [x] **4.1 RALPH Loop Engine**: Implement `ace loop` to iteratively run: Context Refresh -> Execute -> Verify (Tests) -> Reflect -> Repeat.
- [x] **4.2 Agent Mail System**: Implement the internal messaging system in `.ace/mail/` with `inbox/` and `sent/` per agent.
- [x] **4.3 Consensus Protocol**: Implement the debate logic where agents exchange proposals via Mail, mediated by an LLM-referee.
- [x] **4.4 SOP Engine**: Implement Standard Operating Procedures for `onboarding`, `audit`, and `pr-review`.
- [x] **4.5 Google Stitch Integration**: Implement `ace ui mockup` and `ace ui sync` to interface with Google Labs design tools.

## Phase 5: Service & API (Completed)
- [x] **5.1 FastAPI Architecture**: Refactor core logic into a service layer to support a FastAPI backend for future Web/IDE integration.
- [x] **5.2 CLI-to-API Bridge**: Ensure all CLI commands call the underlying service layer.
- [x] **5.3 FastAPI Backend Implementation**: Create the actual FastAPI app and endpoints.
- [x] **5.4 Documentation**: Finalize `README.md` and CLI `--help` documentation for all commands.

## Phase 6: Refinement & Missing Features (In Progress)
- [x] **6.1 Memory Write-back Verification**: Added tests to verify that `update_playbook` correctly handles various markdown structures and edge cases.
- [x] **6.2 RALPH Loop Reflection Integration**: Ensure the loop correctly uses reflection to update memory between iterations.
- [x] **6.3 Native ace loop**: Integrate the RALPH loop logic directly into 'ace.py' as a native command.
- [x] **6.4 SOP Logic**: Implement formal instructions/SOPs for agent onboarding and PR reviews.
- [x] **6.5 Google Stitch Integration**: Connect the CLI stubs to actual API or code extraction logic.
- [ ] **6.6 Advanced Consensus**: Implement multi-turn debate logic (currently 1-turn mediation).
- [ ] **6.7 Test Coverage Expansion**: Increase test coverage for `ACEService` and API endpoints beyond basic tests.
- [ ] **6.8 Production Readiness**: Add logging, error handling middleware for FastAPI, and deployment scripts.

