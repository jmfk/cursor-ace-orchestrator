import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict
from ace_lib.services.ace_service import ACEService


class SecurityAuditService:
    def __init__(self, ace_service: ACEService):
        self.ace_service = ace_service

    def run_automated_audit(self, agent_id: str) -> Dict:
        """Run automated security checks for an agent's owned modules (Phase 10.18)."""
        agents_config = self.ace_service.load_agents()
        agent = next((a for a in agents_config.agents if a.id == agent_id), None)
        if not agent:
            raise ValueError(f"Agent {agent_id} not found.")

        # Find owned modules
        ownership = self.ace_service.load_ownership()
        owned_paths = [
            path for path, mod in ownership.modules.items() if mod.agent_id == agent_id
        ]

        results = {
            "agent_id": agent_id,
            "timestamp": datetime.now().isoformat(),
            "checks": [],
            "summary": {"passed": 0, "failed": 0, "warnings": 0},
        }

        for path in owned_paths:
            full_path = self.ace_service.base_path / path
            if not full_path.exists():
                continue

            # 1. Secret scanning (simple regex for now)
            secret_check = self._check_secrets(full_path)
            results["checks"].append(secret_check)
            if secret_check["status"] == "failed":
                results["summary"]["failed"] += 1
            else:
                results["summary"]["passed"] += 1

            # 2. Dependency audit (if applicable)
            if (full_path / "package.json").exists():
                dep_check = self._audit_npm(full_path)
                results["checks"].append(dep_check)
                if dep_check["status"] == "failed":
                    results["summary"]["failed"] += 1
                elif dep_check["status"] == "warning":
                    results["summary"]["warnings"] += 1
                else:
                    results["summary"]["passed"] += 1
            elif (full_path / "requirements.txt").exists() or (
                full_path / "pyproject.toml"
            ).exists():
                dep_check = self._audit_pip(full_path)
                results["checks"].append(dep_check)
                if dep_check["status"] == "failed":
                    results["summary"]["failed"] += 1
                elif dep_check["status"] == "warning":
                    results["summary"]["warnings"] += 1
                else:
                    results["summary"]["passed"] += 1

        # Log results to agent's inbox if there are failures
        if results["summary"]["failed"] > 0:
            self.ace_service.send_mail(
                to_agent=agent_id,
                from_agent="orchestrator",
                subject="SECURITY ALERT: Automated Audit Failed",
                body=(
                    f"Automated security audit for your owned modules failed.\n\n"
                    f"Summary: {results['summary']['failed']} failures, "
                    f"{results['summary']['warnings']} warnings.\n\n"
                    f"Please review your modules and fix the identified issues."
                ),
            )

        return results

    def _check_secrets(self, path: Path) -> Dict:
        """Scan for potential secrets in a directory."""
        findings = []
        # 1. Secret scanning (simple regex for now)
        patterns = {
            "Generic API Key": (
                r"(?:key|api|token|secret|password|auth)[-_]?(?:key|api|token|secret|password|auth)?\s*[:=]\s*"
                r"['\"]([a-zA-Z0-9]{16,})['\"]"
            ),
            "Slack Token": r"xox[baprs]-([a-zA-Z0-9]{10,48})",
            "AWS Access Key": r"AKIA[0-9A-Z]{16}",
        }

        for root, _, files in os.walk(path):
            for file in files:
                if file.endswith(
                    (".py", ".js", ".ts", ".tsx", ".json", ".yaml", ".yml", ".env")
                ):
                    file_path = Path(root) / file
                    try:
                        content = file_path.read_text(encoding="utf-8")
                        for name, pattern in patterns.items():
                            matches = re.finditer(pattern, content, re.IGNORECASE)
                            for match in matches:
                                findings.append(
                                    {
                                        "file": str(
                                            file_path.relative_to(
                                                self.ace_service.base_path
                                            )
                                        ),
                                        "type": name,
                                        "line": content.count("\n", 0, match.start())
                                        + 1,
                                    }
                                )
                    except Exception:
                        continue

        return {
            "name": "Secret Scanning",
            "path": str(path.relative_to(self.ace_service.base_path)),
            "status": "failed" if findings else "passed",
            "findings": findings,
        }

    def _audit_npm(self, path: Path) -> Dict:
        """Run npm audit."""
        try:
            result = subprocess.run(
                ["npm", "audit", "--json"],
                cwd=path,
                capture_output=True,
                text=True,
                check=False,
            )
            import json

            data = json.loads(result.stdout)
            vulnerabilities = data.get("metadata", {}).get("vulnerabilities", {})
            total_vulnerabilities = sum(vulnerabilities.values())

            return {
                "name": "NPM Dependency Audit",
                "path": str(path.relative_to(self.ace_service.base_path)),
                "status": "failed" if total_vulnerabilities > 0 else "passed",
                "details": vulnerabilities,
            }
        except Exception:
            return {
                "name": "NPM Dependency Audit",
                "path": str(path.relative_to(self.ace_service.base_path)),
                "status": "warning",
                "error": "NPM audit failed.",
            }

    def _audit_pip(self, path: Path) -> Dict:
        """Run safety check for python dependencies."""
        try:
            # Check if safety is installed
            subprocess.run(["safety", "--version"], capture_output=True, check=True)
            result = subprocess.run(
                ["safety", "check", "--json"],
                cwd=path,
                capture_output=True,
                text=True,
                check=False,
            )
            import json

            data = json.loads(result.stdout)

            return {
                "name": "PIP Dependency Audit",
                "path": str(path.relative_to(self.ace_service.base_path)),
                "status": "failed" if data else "passed",
                "details": data,
            }
        except Exception:
            return {
                "name": "PIP Dependency Audit",
                "path": str(path.relative_to(self.ace_service.base_path)),
                "status": "warning",
                "error": "Safety check tool not found or failed. Run 'pip install safety'.",
            }
