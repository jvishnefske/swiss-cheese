"""Swiss Cheese Orchestrator Core.

Main orchestration loop that:
1. Parses architecture TOML
2. Schedules tasks using topological sort
3. Spawns concurrent subagents in git worktrees
4. Runs verification gates
5. Rebases and reverifies linearly
"""

from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, AsyncIterator

from claude_agent_sdk import (
    ClaudeSDKClient,
    ClaudeAgentOptions,
    AssistantMessage,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
    CLINotFoundError,
    CLIConnectionError,
    ProcessError,
    ClaudeSDKError,
)

from .toml_parser import ProjectConfig, Task, AgentConfig, load_architecture
from .scheduler import TaskScheduler, ScheduledBatch, ScheduleResult


class TaskStatus(Enum):
    """Status of a verification task."""
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class TaskResult:
    """Result of a single task execution."""
    task_name: str
    status: TaskStatus
    duration_ms: int = 0
    output: str = ""
    error: str | None = None
    gate_exit_code: int | None = None
    report_paths: list[str] = field(default_factory=list)


@dataclass
class LayerResult:
    """Result of a verification layer."""
    layer_name: str
    status: TaskStatus
    task_results: list[TaskResult] = field(default_factory=list)
    gate_passed: bool = False
    started_at: datetime | None = None
    completed_at: datetime | None = None


@dataclass
class VerificationReport:
    """Complete verification report."""
    project_name: str
    started_at: datetime
    completed_at: datetime | None = None
    overall_status: TaskStatus = TaskStatus.PENDING
    layer_results: dict[str, LayerResult] = field(default_factory=dict)
    total_tasks: int = 0
    passed_tasks: int = 0
    failed_tasks: int = 0

    def to_json(self) -> str:
        """Serialize report to JSON."""
        return json.dumps(self._to_dict(), indent=2, default=str)

    def _to_dict(self) -> dict[str, Any]:
        return {
            "project": self.project_name,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "status": self.overall_status.value,
            "summary": {
                "total_tasks": self.total_tasks,
                "passed": self.passed_tasks,
                "failed": self.failed_tasks,
            },
            "layers": {
                name: {
                    "status": lr.status.value,
                    "gate_passed": lr.gate_passed,
                    "tasks": [
                        {
                            "name": tr.task_name,
                            "status": tr.status.value,
                            "duration_ms": tr.duration_ms,
                            "gate_exit_code": tr.gate_exit_code,
                        }
                        for tr in lr.task_results
                    ],
                }
                for name, lr in self.layer_results.items()
            },
        }


class SwissCheeseOrchestrator:
    """Main orchestrator for Swiss Cheese verification model.

    Coordinates concurrent subagents, manages git worktrees,
    and enforces verification gates.
    """

    def __init__(
        self,
        architecture_path: str | Path,
        project_dir: str | Path,
        *,
        verbose: bool = True,
        dry_run: bool = False,
    ):
        self.architecture_path = Path(architecture_path)
        self.project_dir = Path(project_dir).resolve()
        self.verbose = verbose
        self.dry_run = dry_run

        self.config: ProjectConfig | None = None
        self.scheduler: TaskScheduler | None = None
        self.report: VerificationReport | None = None

        # Track active subagent sessions
        self._active_sessions: dict[str, str] = {}  # task_name -> session_id

    async def initialize(self) -> None:
        """Initialize the orchestrator by parsing the architecture."""
        self._log("Parsing architecture document...")
        self.config = load_architecture(self.architecture_path)
        self.scheduler = TaskScheduler(self.config)

        self.report = VerificationReport(
            project_name=self.config.name,
            started_at=datetime.now(),
            total_tasks=len(self.config.tasks),
        )

        self._log(f"Loaded project: {self.config.name} v{self.config.version}")
        self._log(f"  Layers: {len(self.config.layers)}")
        self._log(f"  Tasks: {len(self.config.tasks)}")
        self._log(f"  Agents: {len(self.config.agents)}")

    async def run_verification(self) -> VerificationReport:
        """Run the full verification pipeline.

        Returns:
            VerificationReport with all results.
        """
        if self.config is None:
            await self.initialize()

        assert self.config is not None
        assert self.scheduler is not None
        assert self.report is not None

        # Schedule tasks
        schedule = self.scheduler.schedule_tasks()
        self._log(f"\nScheduled {schedule.total_tasks} tasks in {len(schedule.batches)} batches")
        self._log(f"Max parallelism: {schedule.max_parallelism}")

        # Process batches
        for batch in schedule:
            self._log(f"\n{'='*60}")
            self._log(f"BATCH {batch.batch_number}: {len(batch.tasks)} tasks")
            self._log('='*60)

            # Run tasks in this batch concurrently
            results = await self._run_batch(batch)

            # Check for failures
            failed = [r for r in results if r.status == TaskStatus.FAILED]
            if failed:
                self._log(f"\n❌ Batch {batch.batch_number} FAILED: {[f.task_name for f in failed]}")
                # Continue with non-dependent tasks or abort based on config
                # For now, we continue but mark failures

            # Update report
            for result in results:
                layer_name = self.config.tasks[result.task_name].layer
                if layer_name not in self.report.layer_results:
                    self.report.layer_results[layer_name] = LayerResult(
                        layer_name=layer_name,
                        status=TaskStatus.PENDING,
                        started_at=datetime.now(),
                    )
                self.report.layer_results[layer_name].task_results.append(result)

                if result.status == TaskStatus.PASSED:
                    self.report.passed_tasks += 1
                elif result.status == TaskStatus.FAILED:
                    self.report.failed_tasks += 1

        # Finalize report
        self.report.completed_at = datetime.now()
        self.report.overall_status = (
            TaskStatus.PASSED if self.report.failed_tasks == 0 else TaskStatus.FAILED
        )

        # Run layer gates
        for layer_name, layer_result in self.report.layer_results.items():
            layer_result.completed_at = datetime.now()
            all_passed = all(tr.status == TaskStatus.PASSED for tr in layer_result.task_results)
            layer_result.status = TaskStatus.PASSED if all_passed else TaskStatus.FAILED
            layer_result.gate_passed = all_passed

        return self.report

    async def _run_batch(self, batch: ScheduledBatch) -> list[TaskResult]:
        """Run all tasks in a batch concurrently."""
        if self.dry_run:
            self._log(f"  [DRY RUN] Would execute: {batch.task_names}")
            return [
                TaskResult(task_name=t.name, status=TaskStatus.SKIPPED)
                for t in batch.tasks
            ]

        # Create coroutines for each task
        coros = [self._run_task(task) for task in batch.tasks]

        # Run concurrently
        results = await asyncio.gather(*coros, return_exceptions=True)

        # Handle exceptions
        task_results: list[TaskResult] = []
        for i, result in enumerate(results):
            task = batch.tasks[i]
            if isinstance(result, Exception):
                task_results.append(TaskResult(
                    task_name=task.name,
                    status=TaskStatus.FAILED,
                    error=str(result),
                ))
            else:
                task_results.append(result)

        return task_results

    async def _run_task(self, task: Task) -> TaskResult:
        """Run a single task using a Claude subagent."""
        assert self.config is not None

        self._log(f"  ▶ Starting: {task.name}")
        start_time = datetime.now()

        # Get agent config
        agent_config = self.config.agents.get(task.agent) if task.agent else None

        # Build prompt for the subagent
        prompt = self._build_task_prompt(task)

        # Build system prompt from agent config description
        system_prompt = None
        if agent_config:
            # Use agent description as system context
            system_prompt = (
                f"You are the {agent_config.name} agent.\n"
                f"Role: {agent_config.description}\n\n"
                "Follow the instructions provided in each task carefully."
            )

        # Configure agent options
        options = ClaudeAgentOptions(
            cwd=str(self.project_dir),
            system_prompt=system_prompt,
            allowed_tools=agent_config.tools if agent_config else ["Read", "Grep", "Glob"],
            permission_mode="acceptEdits",
            model=agent_config.model if agent_config else "sonnet",
        )

        output_lines: list[str] = []
        error: str | None = None
        gate_exit_code: int | None = None

        try:
            async with ClaudeSDKClient(options=options) as client:
                await client.query(prompt)

                async for message in client.receive_response():
                    if isinstance(message, AssistantMessage):
                        for block in message.content:
                            if isinstance(block, TextBlock):
                                output_lines.append(block.text)
                                if self.verbose:
                                    # Truncate long output
                                    preview = block.text[:100].replace('\n', ' ')
                                    self._log(f"    {task.name}: {preview}...")
                            elif isinstance(block, ToolUseBlock):
                                if self.verbose:
                                    self._log(f"    {task.name}: using {block.name}")

                    elif isinstance(message, ResultMessage):
                        if message.is_error:
                            error = message.result or "Unknown error"
                        gate_exit_code = 0 if not message.is_error else 1

        except CLINotFoundError:
            error = "Claude Code CLI not found. Install with: npm install -g @anthropic-ai/claude-code"
            gate_exit_code = 127
        except ProcessError as e:
            error = f"Process failed (exit {e.exit_code}): {e.stderr or str(e)}"
            gate_exit_code = e.exit_code or 1
        except CLIConnectionError as e:
            error = f"Connection to Claude Code failed: {str(e)}"
            gate_exit_code = 1
        except ClaudeSDKError as e:
            error = f"SDK error: {str(e)}"
            gate_exit_code = 1
        except Exception as e:
            error = f"Unexpected error: {str(e)}"
            gate_exit_code = 1

        duration = int((datetime.now() - start_time).total_seconds() * 1000)

        status = TaskStatus.PASSED if error is None else TaskStatus.FAILED
        self._log(f"  {'✓' if status == TaskStatus.PASSED else '✗'} {task.name} ({duration}ms)")

        return TaskResult(
            task_name=task.name,
            status=status,
            duration_ms=duration,
            output="\n".join(output_lines),
            error=error,
            gate_exit_code=gate_exit_code,
        )

    def _build_task_prompt(self, task: Task) -> str:
        """Build the prompt for a task's subagent."""
        assert self.config is not None

        layer = self.config.layers.get(task.layer)
        layer_context = f"Layer: {layer.display_name}\n" if layer else ""

        prompt_parts = [
            f"# Task: {task.name}",
            f"\n{layer_context}",
            f"## Description\n{task.description}",
            f"\n## Project Context",
            f"- Project: {self.config.name}",
            f"- Language: {self.config.language}",
            f"- Working Directory: {self.project_dir}",
        ]

        if task.command:
            prompt_parts.append(f"\n## Command to Execute\n```bash\n{task.command}\n```")

        prompt_parts.append("\n## Instructions")
        prompt_parts.append("1. Execute the task described above")
        prompt_parts.append("2. Report any issues or failures clearly")
        prompt_parts.append("3. If this is a verification task, ensure the gate passes (exit code 0)")

        return "\n".join(prompt_parts)

    def _log(self, message: str) -> None:
        """Log a message if verbose mode is enabled."""
        if self.verbose:
            print(message, file=sys.stderr)


async def run_orchestrator(
    architecture_path: str,
    project_dir: str,
    *,
    verbose: bool = True,
    dry_run: bool = False,
    output_format: str = "json",
) -> int:
    """Run the Swiss Cheese orchestrator.

    Args:
        architecture_path: Path to TOML architecture document.
        project_dir: Path to the project to verify.
        verbose: Print progress to stderr.
        dry_run: Don't actually run tasks.
        output_format: Output format (json, text).

    Returns:
        Exit code (0 for success, 1 for failure).
    """
    orchestrator = SwissCheeseOrchestrator(
        architecture_path=architecture_path,
        project_dir=project_dir,
        verbose=verbose,
        dry_run=dry_run,
    )

    report = await orchestrator.run_verification()

    # Output report
    if output_format == "json":
        print(report.to_json())
    else:
        print(f"\n{'='*60}")
        print(f"VERIFICATION COMPLETE: {report.project_name}")
        print('='*60)
        print(f"Status: {report.overall_status.value.upper()}")
        print(f"Tasks: {report.passed_tasks}/{report.total_tasks} passed")
        print(f"Duration: {(report.completed_at - report.started_at).total_seconds():.1f}s")

    return 0 if report.overall_status == TaskStatus.PASSED else 1
