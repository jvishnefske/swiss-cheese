"""Base Gate Classes.

Defines the abstract gate interface and result types.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET


class GateStatus(Enum):
    """Status of a gate execution."""
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass
class CommandResult:
    """Result of a single command execution."""
    name: str
    command: str
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    passed: bool


@dataclass
class GateResult:
    """Result of a gate execution."""
    gate_name: str
    status: GateStatus
    exit_code: int
    command_results: list[CommandResult] = field(default_factory=list)
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime | None = None
    summary: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        """Serialize to JSON."""
        return json.dumps({
            "gate": self.gate_name,
            "status": self.status.value,
            "exit_code": self.exit_code,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "summary": self.summary,
            "commands": [
                {
                    "name": c.name,
                    "command": c.command,
                    "exit_code": c.exit_code,
                    "passed": c.passed,
                    "duration_ms": c.duration_ms,
                }
                for c in self.command_results
            ],
            "details": self.details,
        }, indent=2)

    def to_xml(self) -> str:
        """Serialize to XML (JUnit-compatible format)."""
        testsuite = ET.Element("testsuite", {
            "name": self.gate_name,
            "tests": str(len(self.command_results)),
            "failures": str(sum(1 for c in self.command_results if not c.passed)),
            "time": str((self.completed_at - self.started_at).total_seconds() if self.completed_at else 0),
        })

        for cmd in self.command_results:
            testcase = ET.SubElement(testsuite, "testcase", {
                "name": cmd.name,
                "time": str(cmd.duration_ms / 1000),
            })
            if not cmd.passed:
                failure = ET.SubElement(testcase, "failure", {"message": f"Exit code: {cmd.exit_code}"})
                failure.text = cmd.stderr or cmd.stdout

        return ET.tostring(testsuite, encoding="unicode")

    def to_html(self) -> str:
        """Generate HTML report."""
        status_color = {
            GateStatus.PASSED: "#28a745",
            GateStatus.FAILED: "#dc3545",
            GateStatus.SKIPPED: "#6c757d",
            GateStatus.ERROR: "#fd7e14",
        }.get(self.status, "#6c757d")

        commands_html = ""
        for cmd in self.command_results:
            cmd_color = "#28a745" if cmd.passed else "#dc3545"
            commands_html += f"""
            <div style="margin: 10px 0; padding: 10px; border-left: 3px solid {cmd_color}; background: #f8f9fa;">
                <strong>{cmd.name}</strong> - {'✓ Passed' if cmd.passed else '✗ Failed'} ({cmd.duration_ms}ms)
                <pre style="margin-top: 5px; font-size: 12px; overflow-x: auto;">{cmd.command}</pre>
            </div>
            """

        return f"""
<!DOCTYPE html>
<html>
<head>
    <title>Gate Report: {self.gate_name}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 40px; }}
        .status {{ color: white; padding: 5px 15px; border-radius: 4px; display: inline-block; }}
        pre {{ background: #2d2d2d; color: #f8f8f2; padding: 15px; border-radius: 4px; overflow-x: auto; }}
    </style>
</head>
<body>
    <h1>Gate Report: {self.gate_name}</h1>
    <p><span class="status" style="background: {status_color};">{self.status.value.upper()}</span></p>
    <p><strong>Summary:</strong> {self.summary}</p>
    <p><strong>Exit Code:</strong> {self.exit_code}</p>
    <h2>Commands</h2>
    {commands_html}
</body>
</html>
        """


class Gate(ABC):
    """Abstract base class for verification gates."""

    def __init__(
        self,
        name: str,
        project_dir: str | Path,
        *,
        fail_fast: bool = True,
    ):
        self.name = name
        self.project_dir = Path(project_dir).resolve()
        self.fail_fast = fail_fast

    @abstractmethod
    async def run(self) -> GateResult:
        """Run the gate verification.

        Returns:
            GateResult with status and details.
        """

    async def run_command(
        self,
        name: str,
        command: str | list[str],
        *,
        timeout: int = 300,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        """Run a shell command and capture results.

        Args:
            name: Human-readable name for this command.
            command: Command to run (string or list).
            timeout: Timeout in seconds.
            env: Additional environment variables.

        Returns:
            CommandResult with exit code and output.
        """
        start = datetime.now()

        if isinstance(command, str):
            cmd_list = command.split()
        else:
            cmd_list = command

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd_list,
                cwd=self.project_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )

            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout,
            )

            exit_code = proc.returncode or 0
            stdout_str = stdout.decode() if stdout else ""
            stderr_str = stderr.decode() if stderr else ""

        except asyncio.TimeoutError:
            exit_code = 124  # Standard timeout exit code
            stdout_str = ""
            stderr_str = f"Command timed out after {timeout}s"

        except Exception as e:
            exit_code = 1
            stdout_str = ""
            stderr_str = str(e)

        duration = int((datetime.now() - start).total_seconds() * 1000)

        return CommandResult(
            name=name,
            command=" ".join(cmd_list),
            exit_code=exit_code,
            stdout=stdout_str,
            stderr=stderr_str,
            duration_ms=duration,
            passed=exit_code == 0,
        )


class GateRunner:
    """Runs multiple gates and collects results."""

    def __init__(self, project_dir: str | Path):
        self.project_dir = Path(project_dir).resolve()
        self._gates: list[Gate] = []

    def add_gate(self, gate: Gate) -> None:
        """Add a gate to run."""
        self._gates.append(gate)

    async def run_all(
        self,
        *,
        fail_fast: bool = False,
        output_dir: str | Path | None = None,
    ) -> list[GateResult]:
        """Run all gates.

        Args:
            fail_fast: Stop on first failure.
            output_dir: Directory to write reports.

        Returns:
            List of GateResults.
        """
        results: list[GateResult] = []
        output_path = Path(output_dir) if output_dir else None

        for gate in self._gates:
            result = await gate.run()
            results.append(result)

            # Write reports if output dir specified
            if output_path:
                output_path.mkdir(parents=True, exist_ok=True)
                (output_path / f"{gate.name}.json").write_text(result.to_json())
                (output_path / f"{gate.name}.xml").write_text(result.to_xml())
                (output_path / f"{gate.name}.html").write_text(result.to_html())

            if fail_fast and result.status == GateStatus.FAILED:
                break

        return results
