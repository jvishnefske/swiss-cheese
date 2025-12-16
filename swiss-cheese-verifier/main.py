#!/usr/bin/env python3
"""Swiss Cheese Verifier - Production Rust Verification.

A NASA Swiss Cheese Model implementation for multi-layer verification
of production Rust code using Claude AI subagents.

Usage:
    python main.py verify --architecture arch.toml --project ./my-rust-project
    python main.py gate --gate static-analysis --project ./my-rust-project
    python main.py schedule --architecture arch.toml
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from orchestrator import SwissCheeseOrchestrator, ArchitectureParser, TaskScheduler
from orchestrator.scheduler import print_schedule
from gates import StaticAnalysisGate, TDDGate, ReviewGate, GateRunner
from reports import ReportGenerator, ReportFormat


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser."""
    parser = argparse.ArgumentParser(
        prog="swiss-cheese",
        description="Swiss Cheese Model verification for production Rust code",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run full verification pipeline
  python main.py verify -a architecture/example_project.toml -p ./my-project

  # Run a specific gate
  python main.py gate -g static-analysis -p ./my-project

  # Show task schedule without executing
  python main.py schedule -a architecture/example_project.toml

  # Generate reports only
  python main.py report -a architecture/example_project.toml -o ./reports
        """,
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # verify command
    verify_parser = subparsers.add_parser(
        "verify",
        help="Run full verification pipeline",
    )
    verify_parser.add_argument(
        "-a", "--architecture",
        type=Path,
        required=True,
        help="Path to TOML architecture document",
    )
    verify_parser.add_argument(
        "-p", "--project",
        type=Path,
        required=True,
        help="Path to project directory",
    )
    verify_parser.add_argument(
        "-o", "--output",
        type=Path,
        help="Output directory for reports",
    )
    verify_parser.add_argument(
        "--format",
        choices=["json", "text", "html"],
        default="json",
        help="Output format (default: json)",
    )
    verify_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be executed without running",
    )
    verify_parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose output",
    )

    # gate command
    gate_parser = subparsers.add_parser(
        "gate",
        help="Run a specific verification gate",
    )
    gate_parser.add_argument(
        "-g", "--gate",
        required=True,
        choices=["static-analysis", "tdd", "review"],
        help="Gate to run",
    )
    gate_parser.add_argument(
        "-p", "--project",
        type=Path,
        required=True,
        help="Path to project directory",
    )
    gate_parser.add_argument(
        "-o", "--output",
        type=Path,
        help="Output directory for reports",
    )
    gate_parser.add_argument(
        "--format",
        choices=["json", "xml", "html", "all"],
        default="json",
        help="Report format (default: json)",
    )

    # schedule command
    schedule_parser = subparsers.add_parser(
        "schedule",
        help="Show task schedule from architecture document",
    )
    schedule_parser.add_argument(
        "-a", "--architecture",
        type=Path,
        required=True,
        help="Path to TOML architecture document",
    )
    schedule_parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )
    schedule_parser.add_argument(
        "--tasks-only",
        action="store_true",
        help="Show task order only (flat list)",
    )

    # parse command - just parse and validate TOML
    parse_parser = subparsers.add_parser(
        "parse",
        help="Parse and validate architecture document",
    )
    parse_parser.add_argument(
        "-a", "--architecture",
        type=Path,
        required=True,
        help="Path to TOML architecture document",
    )
    parse_parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )

    return parser


async def cmd_verify(args: argparse.Namespace) -> int:
    """Run the full verification pipeline."""
    orchestrator = SwissCheeseOrchestrator(
        architecture_path=args.architecture,
        project_dir=args.project,
        verbose=args.verbose,
        dry_run=args.dry_run,
    )

    report = await orchestrator.run_verification()

    # Generate reports
    if args.output:
        generator = ReportGenerator(args.output)
        formats = [ReportFormat.JSON, ReportFormat.XML, ReportFormat.HTML]
        outputs = generator.generate(report, formats)
        print(f"Reports written to: {args.output}", file=sys.stderr)
        for fmt, path in outputs.items():
            print(f"  {fmt.value}: {path}", file=sys.stderr)

    # Output to stdout
    if args.format == "json":
        print(report.to_json())
    elif args.format == "html":
        generator = ReportGenerator(Path("."))
        print(generator._to_html(report))
    else:
        print(f"\nVerification {'PASSED' if report.overall_status.value == 'passed' else 'FAILED'}")
        print(f"Tasks: {report.passed_tasks}/{report.total_tasks} passed")

    return 0 if report.overall_status.value == "passed" else 1


async def cmd_gate(args: argparse.Namespace) -> int:
    """Run a specific verification gate."""
    project_dir = args.project.resolve()

    # Create the appropriate gate
    if args.gate == "static-analysis":
        gate = StaticAnalysisGate(project_dir)
    elif args.gate == "tdd":
        gate = TDDGate(project_dir)
    elif args.gate == "review":
        gate = ReviewGate(project_dir)
    else:
        print(f"Unknown gate: {args.gate}", file=sys.stderr)
        return 1

    result = await gate.run()

    # Output reports
    if args.output:
        args.output.mkdir(parents=True, exist_ok=True)

        if args.format in ("json", "all"):
            (args.output / f"{args.gate}.json").write_text(result.to_json())
        if args.format in ("xml", "all"):
            (args.output / f"{args.gate}.xml").write_text(result.to_xml())
        if args.format in ("html", "all"):
            (args.output / f"{args.gate}.html").write_text(result.to_html())

        print(f"Reports written to: {args.output}", file=sys.stderr)

    # Output to stdout
    if args.format == "json":
        print(result.to_json())
    elif args.format == "xml":
        print(result.to_xml())
    elif args.format == "html":
        print(result.to_html())
    else:
        print(result.to_json())

    return result.exit_code


def cmd_schedule(args: argparse.Namespace) -> int:
    """Show the task schedule."""
    parser = ArchitectureParser(args.architecture)
    config = parser.parse()
    scheduler = TaskScheduler(config)

    if args.tasks_only:
        # Flat topologically-sorted list
        order = scheduler.get_task_order()
        if args.format == "json":
            print(json.dumps(order, indent=2))
        else:
            print("Task order (topologically sorted):")
            for i, task in enumerate(order, 1):
                print(f"  {i}. {task}")
        return 0

    # Full schedule with batches
    schedule = scheduler.schedule_tasks()

    if args.format == "json":
        output = {
            "total_tasks": schedule.total_tasks,
            "max_parallelism": schedule.max_parallelism,
            "batches": [
                {
                    "batch_number": batch.batch_number,
                    "layer": batch.layer,
                    "tasks": [
                        {
                            "name": task.name,
                            "description": task.description,
                            "depends_on": task.depends_on,
                        }
                        for task in batch.tasks
                    ],
                }
                for batch in schedule
            ],
        }
        print(json.dumps(output, indent=2))
    else:
        print_schedule(schedule)

    return 0


def cmd_parse(args: argparse.Namespace) -> int:
    """Parse and validate the architecture document."""
    try:
        parser = ArchitectureParser(args.architecture)
        config = parser.parse()
    except Exception as e:
        print(f"Error parsing architecture: {e}", file=sys.stderr)
        return 1

    if args.format == "json":
        output = {
            "project": {
                "name": config.name,
                "version": config.version,
                "language": config.language,
                "description": config.description,
            },
            "layers": {
                name: {
                    "display_name": layer.display_name,
                    "order": layer.order,
                    "depends_on": layer.depends_on,
                    "optional": layer.optional,
                }
                for name, layer in config.layers.items()
            },
            "tasks": {
                name: {
                    "layer": task.layer,
                    "depends_on": task.depends_on,
                    "agent": task.agent,
                }
                for name, task in config.tasks.items()
            },
            "agents": list(config.agents.keys()),
        }
        print(json.dumps(output, indent=2))
    else:
        print(f"Project: {config.name} v{config.version}")
        print(f"Language: {config.language}")
        print(f"Description: {config.description}")
        print(f"\nLayers ({len(config.layers)}):")
        for name, layer in sorted(config.layers.items(), key=lambda x: x[1].order):
            deps = f" <- {layer.depends_on}" if layer.depends_on else ""
            opt = " (optional)" if layer.optional else ""
            print(f"  {layer.order}. {name}: {layer.display_name}{deps}{opt}")
        print(f"\nTasks ({len(config.tasks)}):")
        for name, task in config.tasks.items():
            deps = f" <- {task.depends_on}" if task.depends_on else ""
            print(f"  • {name} [{task.layer}]{deps}")
        print(f"\nAgents ({len(config.agents)}):")
        for name, agent in config.agents.items():
            print(f"  • {name}: {agent.description[:50]}...")

    return 0


def main() -> int:
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args()

    if args.command == "verify":
        return asyncio.run(cmd_verify(args))
    elif args.command == "gate":
        return asyncio.run(cmd_gate(args))
    elif args.command == "schedule":
        return cmd_schedule(args)
    elif args.command == "parse":
        return cmd_parse(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
