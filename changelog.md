# Changelog

## [2026-04-01] - RALPH Loop Iteration 10

### Added
- **Phase 5: API & Future Readiness**
  - FastAPI Architecture: Refactored core logic into a service layer to support a FastAPI backend.
  - CLI-to-API Bridge: Ensured all CLI commands call the underlying service layer.

## [2026-04-01] - RALPH Loop Iteration 9

### Added
- **Phase 5: API & Future Readiness**
  - FastAPI Architecture: Refactored core logic into a service layer to support a FastAPI backend.
  - CLI-to-API Bridge: Ensured all CLI commands call the underlying service layer.

## [2026-04-01] - RALPH Loop Iteration 9

### Added
- **Phase 5: API & Future Readiness**
  - Documentation: Finalized `README.md` and CLI `--help` documentation for all commands.

## [2026-04-01] - RALPH Loop Iteration 8

### Added
- **Phase 5: API & Future Readiness**
  - Documentation: Finalized `README.md` and CLI `--help` documentation for all commands.

## [2026-04-01] - RALPH Loop Iteration 7

### Added
- **Phase 4: RALPH Loop & Multi-Agent Coordination (M4)**
  - Google Stitch Integration: Implemented `ace ui mockup` and `ace ui sync` to interface with Google Labs design tools.

## [2026-04-01] - RALPH Loop Iteration 6

### Added
- **Phase 5: API & Future Readiness**
  - Documentation: Finalized `README.md` and CLI `--help` documentation for all commands.

## [2026-04-01] - RALPH Loop Iteration 5

### Added
- **Phase 4: RALPH Loop & Multi-Agent Coordination (M4)**
  - SOP Engine: Implemented Standard Operating Procedures for `onboarding`, `audit`, and `pr-review`.

## [2026-04-01] - RALPH Loop Iteration 4

### Added
- **Phase 4: RALPH Loop & Multi-Agent Coordination (M4)**
  - Agent Mail System: Implemented the internal messaging system in `.ace/mail/` with `inbox/` and `sent/` per agent.
  - Consensus Protocol: Implemented the debate logic where agents exchange proposals via Mail, mediated by an LLM-referee.

## [2026-04-01] - RALPH Loop Iteration 3

### Added
- **Phase 4: RALPH Loop & Multi-Agent Coordination (M4)**
  - RALPH Loop Engine: Implemented `ace loop` for iterative execution including Context Refresh, Execute, Verify (Tests), and Reflect.

## [2026-04-01] - RALPH Loop Iteration 2

### Added
- **Phase 2: Write-back Pipeline (M2)**
  - Reflection Engine: Extracts learnings from agent output using structured patterns.
  - Delta Update Parser: Parses `[str-XXX]`, `[mis-XXX]`, and `[dec-XXX]` updates from reflection output.
  - Playbook Updater: Safely updates `.mdc` files with new learnings while preserving structure.
  - Helpful/Harmful Counters: Logic to track and update strategy effectiveness.

## [2026-04-01] - RALPH Loop Iteration 1

### Added
- **Phase 1: Context Builder & Executor (M1)**
  - `ace build-context`: Composes context slice including global rules, agent playbooks, recent ADRs, and task framing.
  - `ace run`: Executor wrapper for agent commands (e.g., `cursor-agent`, `claude-code`) with automatic context injection.
  - Session Logging: Every `ace run` execution is now logged to `.ace/sessions/` in Markdown format.
  - Token Mode Configuration: `ace config tokens --mode [low|medium|high]` to control context depth.
  - Session Continuity: Logic to inject the most recent relevant session log into the Context Builder.
  - Task Type Framing: Structured prompt prefixes for `implement`, `review`, `debug`, `refactor`, and `plan`.

### Changed
- Updated `plan.md` to reflect completed Phase 1 tasks.
- Moved `Session Continuity` from Phase 3 to Phase 1 as it was implemented as part of the core context builder logic.
