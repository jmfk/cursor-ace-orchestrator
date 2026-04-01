from datetime import datetime
from typing import List

def generate_onboarding_sop(agent_id: str, name: str, role: str, responsibilities: List[str], memory_file: str, status: str) -> str:
    """Generate a formal onboarding SOP for an agent (PRD-01 / Phase 9.5)."""
    resp_str = ", ".join(responsibilities) if responsibilities else "None"
    return f"""# SOP: Agent Onboarding - {name} ({agent_id})
- **Role**: {role}
- **Responsibilities**: {resp_str}
- **Memory File**: {memory_file}
- **Status**: {status}
- **Date**: {datetime.now().isoformat()}

## 1. Context Acquisition
- [ ] **Registry**: Read `AGENTS.md` to understand the current agent landscape.
- [ ] **Decisions**: Read `.ace/decisions/*.md` for recent architectural decisions.
- [ ] **Global Standards**: Read `.cursor/rules/_global.mdc` for project-wide standards.
- [ ] **Ownership**: Review `ownership.yaml` for assigned modules.

## 2. Role-Specific Setup
- [ ] **Playbook**: Create/Verify `{memory_file}` exists.
- [ ] **Structure**: Ensure the playbook contains sections for "Strategier & patterns",
      "Kända fallgropar", and "Arkitekturella beslut".

## 3. Initial Task
- [ ] **Audit**: Review existing codebase in assigned modules: {resp_str}
- [ ] **Debt**: Identify initial technical debts and document as `[mis-NEW]` in playbook.
- [ ] **Strategy**: Propose first strategy improvement as `[str-NEW]`.

## 4. Handover & Verification
- [ ] **Communication**: Send a "Ready" message to the orchestrator via `ace mail-send`.
- [ ] **Consensus**: Participate in the next `ace debate` to demonstrate alignment.

## 5. Standard Operating Procedures (SOPs)
- [ ] **Onboarding**: Follow `ace agent onboard` to initialize role-specific playbooks.
- [ ] **PR Review**: Use `ace agent review` for systematic code reviews.
- [ ] **Audit**: Participate in regular `ace agent audit` sessions.
- [ ] **Security**: Conduct `ace agent security-audit` on owned modules.
"""

def generate_pr_review_sop(pr_id: str, agent_id: str) -> str:
    """Generate a formal PR review SOP for an agent (PRD-01 / Phase 9.5)."""
    return f"""# SOP: PR Review - {pr_id}
- **Reviewer**: {agent_id}
- **Date**: {datetime.now().isoformat()}

## 1. Strategy Alignment
- [ ] **Core Principles**: Does the PR follow TypeScript Strict Mode and TDD?
- [ ] **DRY/YAGNI**: Is the code concise and reusable without over-engineering?
- [ ] **Playbook Matching**: Does the PR follow strategies defined in reviewer's playbook?
- [ ] **Global Rules**: Does the PR adhere to global rules in `_global.mdc`?

## 2. Decision Verification
- [ ] **ADR Compliance**: Does PR conflict with any recent ADRs in `.ace/decisions/`?
- [ ] **Ownership**: Is the code being modified by the correct agent (check `ownership.yaml`)?

## 3. Learning Extraction
- [ ] **New Strategies**: Identify any new successful patterns: `[str-NEW] helpful=1 harmful=0 :: <desc>`
- [ ] **New Pitfalls**: Identify any new pitfalls or bugs: `[mis-NEW] helpful=0 harmful=1 :: <desc>`
- [ ] **New Decisions**: Identify any architectural choices that should be ADRs: `[dec-NEW] :: <desc>`

## 4. Conclusion
- [ ] **Status**: [PENDING/APPROVED/REQUEST_CHANGES]
- [ ] **Comments**:
"""

def generate_audit_sop(agent_id: str, name: str) -> str:
    """Generate a formal audit SOP for an agent (PRD-01 / Phase 9.5)."""
    return f"""# SOP: Agent Audit - {name} ({agent_id})
- **Auditor**: Orchestrator
- **Date**: {datetime.now().isoformat()}

## 1. Playbook Quality
- [ ] **Completeness**: Does the playbook have all required sections?
- [ ] **Utility**: Are the strategies actionable and relevant?
- [ ] **Pruning**: Has the playbook been pruned of stale or harmful entries?

## 2. Performance & Alignment
- [ ] **Success Rate**: Review recent session logs for success/failure ratio.
- [ ] **Decision Alignment**: Does the agent's work align with recent ADRs?
- [ ] **Communication**: Is the agent using the mail system and MACP correctly?

## 3. Knowledge Extraction
- [ ] **New Learnings**: Are new strategies being identified and documented?
- [ ] **Shared Knowledge**: Is the agent contributing to shared-learnings?

## 4. Conclusion
- [ ] **Status**: [PASSED/REQUIRES_IMPROVEMENT/RE-ONBOARDING]
- [ ] **Notes**:
"""
