"""Test-Driven Development Gate.

Runs tests and checks coverage requirements.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .base import Gate, GateResult, GateStatus, CommandResult


class TDDGate(Gate):
    """TDD verification gate.

    Runs:
    - cargo test (unit and integration tests)
    - cargo llvm-cov (coverage measurement)
    - proptest/quickcheck (property-based tests)

    Enforces minimum coverage thresholds.
    """

    def __init__(
        self,
        project_dir: str | Path,
        *,
        fail_fast: bool = True,
        min_coverage: float = 80.0,
        run_property_tests: bool = True,
        run_doc_tests: bool = True,
        coverage_tool: str = "llvm-cov",  # llvm-cov or tarpaulin
    ):
        super().__init__("tdd", project_dir, fail_fast=fail_fast)
        self.min_coverage = min_coverage
        self.run_property_tests = run_property_tests
        self.run_doc_tests = run_doc_tests
        self.coverage_tool = coverage_tool

    async def run(self) -> GateResult:
        """Run all TDD checks."""
        started = datetime.now()
        results: list[CommandResult] = []
        details: dict[str, Any] = {
            "min_coverage_required": self.min_coverage,
        }

        # Run all tests first
        test_result = await self.run_command(
            "cargo-test",
            ["cargo", "test", "--all-features", "--no-fail-fast"],
            timeout=600,
        )
        results.append(test_result)
        details["test_output"] = self._parse_test_output(test_result.stdout + test_result.stderr)

        if self.fail_fast and not test_result.passed:
            return self._make_result(started, results, details)

        # Run doc tests separately
        if self.run_doc_tests:
            doctest_result = await self.run_command(
                "doc-tests",
                ["cargo", "test", "--doc"],
                timeout=300,
            )
            results.append(doctest_result)

            if self.fail_fast and not doctest_result.passed:
                return self._make_result(started, results, details)

        # Run coverage
        if self.coverage_tool == "llvm-cov":
            cov_result = await self._run_llvm_cov()
        else:
            cov_result = await self._run_tarpaulin()

        results.append(cov_result)
        details["coverage"] = self._parse_coverage_output(cov_result.stdout)

        # Check coverage threshold
        coverage_pct = details["coverage"].get("line_coverage", 0)
        if coverage_pct < self.min_coverage:
            cov_result.passed = False
            details["coverage_check"] = {
                "passed": False,
                "actual": coverage_pct,
                "required": self.min_coverage,
            }
        else:
            details["coverage_check"] = {
                "passed": True,
                "actual": coverage_pct,
                "required": self.min_coverage,
            }

        return self._make_result(started, results, details)

    async def _run_llvm_cov(self) -> CommandResult:
        """Run cargo-llvm-cov for coverage."""
        return await self.run_command(
            "coverage",
            ["cargo", "llvm-cov", "--all-features", "--json"],
            timeout=600,
        )

    async def _run_tarpaulin(self) -> CommandResult:
        """Run cargo-tarpaulin for coverage."""
        return await self.run_command(
            "coverage",
            ["cargo", "tarpaulin", "--all-features", "--out", "Json"],
            timeout=600,
        )

    def _make_result(
        self,
        started: datetime,
        results: list[CommandResult],
        details: dict[str, Any],
    ) -> GateResult:
        """Create a GateResult from command results."""
        all_passed = all(r.passed for r in results)

        coverage_info = details.get("coverage_check", {})
        if coverage_info.get("passed") is False:
            all_passed = False

        test_info = details.get("test_output", {})
        summary_parts = [
            f"Tests: {test_info.get('passed', 0)}/{test_info.get('total', 0)} passed",
        ]

        if "coverage" in details:
            summary_parts.append(f"Coverage: {details['coverage'].get('line_coverage', 0):.1f}%")

        return GateResult(
            gate_name=self.name,
            status=GateStatus.PASSED if all_passed else GateStatus.FAILED,
            exit_code=0 if all_passed else 1,
            command_results=results,
            started_at=started,
            completed_at=datetime.now(),
            summary=" | ".join(summary_parts),
            details=details,
        )

    def _parse_test_output(self, output: str) -> dict[str, Any]:
        """Parse cargo test output."""
        # Parse summary line like "test result: ok. 42 passed; 0 failed; 0 ignored"
        total = 0
        passed = 0
        failed = 0
        ignored = 0

        for line in output.split("\n"):
            if "test result:" in line:
                parts = line.split()
                for i, part in enumerate(parts):
                    if part == "passed;":
                        passed = int(parts[i-1])
                    elif part == "failed;":
                        failed = int(parts[i-1])
                    elif part == "ignored" or part == "ignored;":
                        ignored = int(parts[i-1])

        total = passed + failed + ignored

        return {
            "total": total,
            "passed": passed,
            "failed": failed,
            "ignored": ignored,
        }

    def _parse_coverage_output(self, output: str) -> dict[str, Any]:
        """Parse coverage output."""
        try:
            data = json.loads(output)
            # llvm-cov format
            if "data" in data:
                totals = data["data"][0].get("totals", {})
                lines = totals.get("lines", {})
                return {
                    "line_coverage": lines.get("percent", 0),
                    "lines_covered": lines.get("covered", 0),
                    "lines_total": lines.get("count", 0),
                }
            # tarpaulin format
            elif "coverage" in data:
                return {
                    "line_coverage": data.get("coverage", 0),
                }
        except json.JSONDecodeError:
            pass

        # Fallback: try to extract percentage from text
        import re
        match = re.search(r"(\d+\.?\d*)%", output)
        if match:
            return {"line_coverage": float(match.group(1))}

        return {"line_coverage": 0, "parse_error": True}
