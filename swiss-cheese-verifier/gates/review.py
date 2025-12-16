"""Code Review Gate.

Independent code review using Claude for fresh-eyes analysis.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from claude_agent_sdk import query, ClaudeAgentOptions, AssistantMessage, TextBlock, ResultMessage

from .base import Gate, GateResult, GateStatus, CommandResult


class ReviewGate(Gate):
    """Independent code review gate using Claude.

    Performs:
    - Security review
    - Code quality assessment
    - Architecture compliance check
    - Documentation completeness
    """

    def __init__(
        self,
        project_dir: str | Path,
        *,
        fail_fast: bool = True,
        review_security: bool = True,
        review_quality: bool = True,
        review_architecture: bool = True,
        review_docs: bool = True,
        model: str = "opus",
        severity_threshold: str = "high",  # low, medium, high, critical
    ):
        super().__init__("review", project_dir, fail_fast=fail_fast)
        self.review_security = review_security
        self.review_quality = review_quality
        self.review_architecture = review_architecture
        self.review_docs = review_docs
        self.model = model
        self.severity_threshold = severity_threshold

    async def run(self) -> GateResult:
        """Run code review gate."""
        started = datetime.now()
        results: list[CommandResult] = []
        details: dict[str, Any] = {
            "reviews": {},
        }

        # Security review
        if self.review_security:
            sec_result = await self._run_review(
                "security",
                self._get_security_prompt(),
            )
            results.append(sec_result)
            details["reviews"]["security"] = self._parse_review_response(sec_result.stdout)

            if self.fail_fast and not sec_result.passed:
                return self._make_result(started, results, details)

        # Quality review
        if self.review_quality:
            quality_result = await self._run_review(
                "quality",
                self._get_quality_prompt(),
            )
            results.append(quality_result)
            details["reviews"]["quality"] = self._parse_review_response(quality_result.stdout)

            if self.fail_fast and not quality_result.passed:
                return self._make_result(started, results, details)

        # Architecture review
        if self.review_architecture:
            arch_result = await self._run_review(
                "architecture",
                self._get_architecture_prompt(),
            )
            results.append(arch_result)
            details["reviews"]["architecture"] = self._parse_review_response(arch_result.stdout)

        # Documentation review
        if self.review_docs:
            docs_result = await self._run_review(
                "documentation",
                self._get_docs_prompt(),
            )
            results.append(docs_result)
            details["reviews"]["documentation"] = self._parse_review_response(docs_result.stdout)

        return self._make_result(started, results, details)

    async def _run_review(self, review_name: str, prompt: str) -> CommandResult:
        """Run a single review using Claude."""
        start = datetime.now()
        output_lines: list[str] = []
        passed = True
        error = ""

        try:
            options = ClaudeAgentOptions(
                cwd=str(self.project_dir),
                allowed_tools=["Read", "Grep", "Glob"],
                permission_mode="bypassPermissions",
                model=self.model,
            )

            async for message in query(prompt=prompt, options=options):
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            output_lines.append(block.text)

                elif isinstance(message, ResultMessage):
                    if message.is_error:
                        passed = False
                        error = message.result or "Review failed"

        except Exception as e:
            passed = False
            error = str(e)

        duration = int((datetime.now() - start).total_seconds() * 1000)
        output = "\n".join(output_lines)

        # Check for blocking issues in the review
        if passed and self._has_blocking_issues(output):
            passed = False

        return CommandResult(
            name=review_name,
            command=f"claude-review:{review_name}",
            exit_code=0 if passed else 1,
            stdout=output,
            stderr=error,
            duration_ms=duration,
            passed=passed,
        )

    def _has_blocking_issues(self, review_output: str) -> bool:
        """Check if review output contains blocking issues."""
        severity_levels = ["low", "medium", "high", "critical"]
        threshold_idx = severity_levels.index(self.severity_threshold)

        blocking_keywords = severity_levels[threshold_idx:]

        lower_output = review_output.lower()
        for keyword in blocking_keywords:
            # Look for severity markers like "CRITICAL:" or "[HIGH]"
            if f"{keyword}:" in lower_output or f"[{keyword}]" in lower_output:
                return True

        return False

    def _parse_review_response(self, output: str) -> dict[str, Any]:
        """Parse review response into structured data."""
        # Try to extract JSON if present
        try:
            # Look for JSON block
            if "```json" in output:
                start = output.index("```json") + 7
                end = output.index("```", start)
                return json.loads(output[start:end])
        except (ValueError, json.JSONDecodeError):
            pass

        # Fallback: return summary
        lines = output.strip().split("\n")
        return {
            "summary": lines[0] if lines else "",
            "full_response": output[:2000],  # Truncate for storage
        }

    def _get_security_prompt(self) -> str:
        """Get the security review prompt."""
        return """You are performing a security review of this Rust project.

Analyze the codebase for:
1. Memory safety issues (despite Rust's guarantees, check unsafe blocks)
2. Input validation and sanitization
3. Authentication/authorization flaws
4. Cryptographic issues (weak algorithms, hardcoded secrets)
5. Dependency vulnerabilities
6. Race conditions in concurrent code
7. Information disclosure risks

For each issue found, classify severity as: [LOW], [MEDIUM], [HIGH], or [CRITICAL]

Start by reading the project structure, then analyze key files.
Output your findings in a structured format with severity classifications.

If you find any HIGH or CRITICAL issues, they MUST be addressed before release.
"""

    def _get_quality_prompt(self) -> str:
        """Get the code quality review prompt."""
        return """You are performing a code quality review of this Rust project.

Analyze the codebase for:
1. Code clarity and readability
2. Proper error handling (Result/Option usage)
3. Appropriate use of Rust idioms
4. Function/module organization
5. Dead code or unused dependencies
6. Proper documentation of public APIs
7. Test coverage adequacy

For each issue found, classify severity as: [LOW], [MEDIUM], [HIGH], or [CRITICAL]

Start by reading the project structure, then analyze key modules.
Provide specific, actionable recommendations.
"""

    def _get_architecture_prompt(self) -> str:
        """Get the architecture review prompt."""
        return """You are performing an architecture review of this Rust project.

Analyze the codebase for:
1. Module boundaries and separation of concerns
2. Dependency direction (no circular dependencies)
3. Proper abstraction layers
4. Ownership and borrowing patterns
5. Error propagation strategy
6. Configuration management
7. Scalability considerations

For each issue found, classify severity as: [LOW], [MEDIUM], [HIGH], or [CRITICAL]

Start by understanding the overall structure, then drill into key components.
Focus on architectural decisions that could impact maintainability and evolution.
"""

    def _get_docs_prompt(self) -> str:
        """Get the documentation review prompt."""
        return """You are reviewing documentation completeness for this Rust project.

Check for:
1. README with setup instructions
2. API documentation (rustdoc comments on public items)
3. Architecture decision records (if applicable)
4. Examples and usage guides
5. CHANGELOG maintenance
6. Contributing guidelines
7. License information

For each issue found, classify severity as: [LOW], [MEDIUM], [HIGH], or [CRITICAL]

Missing documentation for critical code paths should be marked HIGH severity.
"""

    def _make_result(
        self,
        started: datetime,
        results: list[CommandResult],
        details: dict[str, Any],
    ) -> GateResult:
        """Create a GateResult from command results."""
        all_passed = all(r.passed for r in results)
        failed_reviews = [r.name for r in results if not r.passed]

        if failed_reviews:
            summary = f"Reviews failed: {', '.join(failed_reviews)}"
        else:
            summary = f"All {len(results)} reviews passed"

        return GateResult(
            gate_name=self.name,
            status=GateStatus.PASSED if all_passed else GateStatus.FAILED,
            exit_code=0 if all_passed else 1,
            command_results=results,
            started_at=started,
            completed_at=datetime.now(),
            summary=summary,
            details=details,
        )
