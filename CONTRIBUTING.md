# ACE Contribution Guidelines

Thank you for your interest in contributing to the Cursor ACE Orchestrator! This project aims to provide long-term memory and coordination for coding agents.

## Core Principles
- **TDD (Test-Driven Development)**: All new features and bug fixes must include tests.
- **DRY (Don't Repeat Yourself)**: Extract common patterns into shared utilities.
- **YAGNI (You Ain't Gonna Need It)**: Focus on current requirements; avoid over-engineering.
- **Agentic Experience (AX)**: Consider how your changes impact the effectiveness and memory of the agents.

## Development Workflow
1. **Fork and Clone**: Create a fork of the repository and clone it locally.
2. **Environment Setup**:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
3. **Create a Branch**: Use descriptive branch names (e.g., `feat/new-sop`, `fix/registry-bug`).
4. **Implement and Test**:
   - Write your tests in the `tests/` directory.
   - Run tests using `pytest`.
   - Ensure all tests pass before submitting.
5. **Linting and Formatting**: We use `ruff` for linting and formatting.
6. **Submit a PR**: Provide a clear description of your changes and link to any relevant issues.

## Project Structure
- `ace.py`: The main CLI entry point.
- `ace_api/`: FastAPI backend implementation.
- `ace_lib/`: Core logic and services.
- `tests/`: Unit and integration tests.
- `.ace/`: Metadata (agents, ownership, mail, sessions, decisions, specs).
- `.cursor/rules/`: Agent playbooks (.mdc files).

## Contribution Areas
- **SOPs**: Improving or adding new Standard Operating Procedures in `ace_lib/sop/`.
- **Memory Logic**: Enhancing reflection, pruning, or vectorized memory search.
- **Integrations**: Improving Google Stitch or other external tool integrations.
- **CLI/API**: Adding new commands or refining existing ones.

## Write-back Protocol
When contributing code that modifies agent behavior, please include a reflection in your PR description:
- `[str-XXX] helpful=X harmful=Y :: <strategy>`
- `[mis-XXX] helpful=X harmful=Y :: <pitfall>`
- `[dec-XXX] :: <decision>`

## License
By contributing, you agree that your contributions will be licensed under the project's license.
