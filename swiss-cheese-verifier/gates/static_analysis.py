"""Static Analysis Gate.

Runs Clippy, cargo-audit, cargo-deny, and unsafe audit for Rust projects.
Also supports clang-tidy for C++ with HICPP checks.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .base import Gate, GateResult, GateStatus, CommandResult


class StaticAnalysisGate(Gate):
    """Static analysis gate for Rust and C++ code.

    Runs:
    - cargo clippy (Rust lints)
    - cargo audit (security vulnerabilities)
    - cargo deny (license and advisory checks)
    - cargo geiger (unsafe audit)
    - clang-tidy (C++ HICPP checks, if configured)
    """

    def __init__(
        self,
        project_dir: str | Path,
        *,
        fail_fast: bool = True,
        run_clippy: bool = True,
        run_audit: bool = True,
        run_deny: bool = True,
        run_geiger: bool = True,
        clang_tidy_checks: list[str] | None = None,
        cpp_files: list[str] | None = None,
    ):
        super().__init__("static-analysis", project_dir, fail_fast=fail_fast)
        self.run_clippy = run_clippy
        self.run_audit = run_audit
        self.run_deny = run_deny
        self.run_geiger = run_geiger
        self.clang_tidy_checks = clang_tidy_checks or ["hicpp-*", "modernize-*"]
        self.cpp_files = cpp_files

    async def run(self) -> GateResult:
        """Run all static analysis checks."""
        started = datetime.now()
        results: list[CommandResult] = []
        details: dict[str, Any] = {}

        # Clippy
        if self.run_clippy:
            clippy_result = await self.run_command(
                "clippy",
                ["cargo", "clippy", "--all-targets", "--all-features",
                 "--message-format=json", "--", "-D", "warnings"],
                timeout=600,
            )
            results.append(clippy_result)
            details["clippy"] = self._parse_clippy_output(clippy_result.stdout)

            if self.fail_fast and not clippy_result.passed:
                return self._make_result(started, results, details)

        # Cargo audit
        if self.run_audit:
            audit_result = await self.run_command(
                "cargo-audit",
                ["cargo", "audit", "--json"],
                timeout=120,
            )
            results.append(audit_result)
            details["audit"] = self._parse_audit_output(audit_result.stdout)

            if self.fail_fast and not audit_result.passed:
                return self._make_result(started, results, details)

        # Cargo deny
        if self.run_deny:
            deny_result = await self.run_command(
                "cargo-deny",
                ["cargo", "deny", "check"],
                timeout=120,
            )
            results.append(deny_result)

            if self.fail_fast and not deny_result.passed:
                return self._make_result(started, results, details)

        # Cargo geiger (unsafe audit)
        if self.run_geiger:
            geiger_result = await self.run_command(
                "cargo-geiger",
                ["cargo", "geiger", "--all-features", "--output-format", "Json"],
                timeout=300,
            )
            results.append(geiger_result)
            details["unsafe_audit"] = self._parse_geiger_output(geiger_result.stdout)

            if self.fail_fast and not geiger_result.passed:
                return self._make_result(started, results, details)

        # Clang-tidy for C++ files (if configured)
        if self.cpp_files:
            checks = ",".join(self.clang_tidy_checks)
            for cpp_file in self.cpp_files:
                tidy_result = await self.run_command(
                    f"clang-tidy:{cpp_file}",
                    ["clang-tidy", f"-checks={checks}", cpp_file],
                    timeout=120,
                )
                results.append(tidy_result)

                if self.fail_fast and not tidy_result.passed:
                    return self._make_result(started, results, details)

        return self._make_result(started, results, details)

    def _make_result(
        self,
        started: datetime,
        results: list[CommandResult],
        details: dict[str, Any],
    ) -> GateResult:
        """Create a GateResult from command results."""
        all_passed = all(r.passed for r in results)
        failed_count = sum(1 for r in results if not r.passed)

        return GateResult(
            gate_name=self.name,
            status=GateStatus.PASSED if all_passed else GateStatus.FAILED,
            exit_code=0 if all_passed else 1,
            command_results=results,
            started_at=started,
            completed_at=datetime.now(),
            summary=f"{len(results) - failed_count}/{len(results)} checks passed",
            details=details,
        )

    def _parse_clippy_output(self, stdout: str) -> dict[str, Any]:
        """Parse Clippy JSON output."""
        warnings = []
        errors = []

        for line in stdout.strip().split("\n"):
            if not line:
                continue
            try:
                msg = json.loads(line)
                if msg.get("reason") == "compiler-message":
                    level = msg.get("message", {}).get("level", "")
                    if level == "warning":
                        warnings.append(msg["message"].get("message", ""))
                    elif level == "error":
                        errors.append(msg["message"].get("message", ""))
            except json.JSONDecodeError:
                continue

        return {
            "warnings": len(warnings),
            "errors": len(errors),
            "warning_messages": warnings[:10],  # Limit for readability
            "error_messages": errors[:10],
        }

    def _parse_audit_output(self, stdout: str) -> dict[str, Any]:
        """Parse cargo-audit JSON output."""
        try:
            data = json.loads(stdout)
            vulns = data.get("vulnerabilities", {})
            return {
                "vulnerabilities_found": vulns.get("count", 0),
                "advisories": [
                    {
                        "id": v.get("advisory", {}).get("id"),
                        "package": v.get("package", {}).get("name"),
                        "severity": v.get("advisory", {}).get("severity"),
                    }
                    for v in vulns.get("list", [])[:10]
                ],
            }
        except json.JSONDecodeError:
            return {"raw_output": stdout[:500]}

    def _parse_geiger_output(self, stdout: str) -> dict[str, Any]:
        """Parse cargo-geiger JSON output."""
        try:
            data = json.loads(stdout)
            return {
                "unsafe_usage": data.get("used", {}),
                "packages_scanned": len(data.get("packages", [])),
            }
        except json.JSONDecodeError:
            # Count unsafe blocks from text output
            unsafe_count = stdout.lower().count("unsafe")
            return {"approximate_unsafe_mentions": unsafe_count}
