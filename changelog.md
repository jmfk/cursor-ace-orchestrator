# Changelog

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
