"""TOML Architecture Parser.

Parses software design documents in TOML format.
Uses tomllib (Python 3.11+) or tomli (Python 3.9+) as fallback.
Extracts layers, tasks, dependencies, and gate configurations.
"""

from __future__ import annotations

import sys

# Python 3.11+ has tomllib in stdlib, otherwise use tomli
if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib
    except ImportError:
        raise ImportError(
            "Python < 3.11 requires the 'tomli' package. "
            "Install with: pip install tomli"
        )
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class GateCommand:
    """A single gate command configuration."""
    name: str
    cmd: str
    output: str = "text"  # json, xml, text


@dataclass
class GateConfig:
    """Gate configuration for a verification layer."""
    commands: list[GateCommand] = field(default_factory=list)
    fail_fast: bool = True
    min_coverage: int | None = None


@dataclass
class AgentConfig:
    """Subagent configuration."""
    name: str
    description: str
    model: str = "sonnet"
    tools: list[str] = field(default_factory=list)


@dataclass
class Task:
    """A verification task with dependencies."""
    name: str
    layer: str
    description: str
    depends_on: list[str] = field(default_factory=list)
    agent: str | None = None
    command: str | None = None
    optional: bool = False


@dataclass
class Layer:
    """A verification layer (Swiss Cheese slice)."""
    name: str
    display_name: str
    description: str
    order: int
    depends_on: list[str] = field(default_factory=list)
    gate: str | None = None
    reports: list[str] = field(default_factory=list)
    optional: bool = False


@dataclass
class WorktreeConfig:
    """Git worktree configuration."""
    base_path: str = ".worktrees"
    branch_prefix: str = "swiss-cheese"
    cleanup_on_success: bool = True
    rebase_strategy: str = "linear"


@dataclass
class ProjectConfig:
    """Complete project configuration parsed from TOML."""
    name: str
    version: str
    language: str
    description: str
    layers: dict[str, Layer]
    tasks: dict[str, Task]
    agents: dict[str, AgentConfig]
    gates: dict[str, GateConfig]
    worktree: WorktreeConfig
    toolchain: dict[str, Any] = field(default_factory=dict)
    additional_languages: dict[str, Any] = field(default_factory=dict)

    def get_layer_tasks(self, layer_name: str) -> list[Task]:
        """Get all tasks belonging to a specific layer."""
        return [t for t in self.tasks.values() if t.layer == layer_name]


class ArchitectureParser:
    """Parses TOML architecture documents into ProjectConfig."""

    def __init__(self, toml_path: str | Path):
        self.toml_path = Path(toml_path)
        self._raw: dict[str, Any] = {}

    def parse(self) -> ProjectConfig:
        """Parse the TOML file and return a ProjectConfig."""
        with open(self.toml_path, "rb") as f:
            self._raw = tomllib.load(f)

        return ProjectConfig(
            name=self._raw["project"]["name"],
            version=self._raw["project"]["version"],
            language=self._raw["project"]["language"],
            description=self._raw["project"].get("description", ""),
            toolchain=self._raw["project"].get("toolchain", {}),
            additional_languages=self._raw["project"].get("additional_languages", {}),
            layers=self._parse_layers(),
            tasks=self._parse_tasks(),
            agents=self._parse_agents(),
            gates=self._parse_gates(),
            worktree=self._parse_worktree(),
        )

    def _parse_layers(self) -> dict[str, Layer]:
        """Parse layer definitions."""
        layers = {}
        raw_layers = self._raw.get("layers", {})

        for layer_id, layer_data in raw_layers.items():
            layers[layer_id] = Layer(
                name=layer_id,
                display_name=layer_data.get("name", layer_id),
                description=layer_data.get("description", ""),
                order=layer_data.get("order", 0),
                depends_on=layer_data.get("depends_on", []),
                gate=layer_data.get("gate"),
                reports=layer_data.get("reports", []),
                optional=layer_data.get("optional", False),
            )

        return layers

    def _parse_tasks(self) -> dict[str, Task]:
        """Parse task definitions."""
        tasks = {}
        raw_tasks = self._raw.get("tasks", {})

        for task_id, task_data in raw_tasks.items():
            tasks[task_id] = Task(
                name=task_id,
                layer=task_data["layer"],
                description=task_data.get("description", ""),
                depends_on=task_data.get("depends_on", []),
                agent=task_data.get("agent"),
                command=task_data.get("command"),
                optional=task_data.get("optional", False),
            )

        return tasks

    def _parse_agents(self) -> dict[str, AgentConfig]:
        """Parse agent definitions."""
        agents = {}
        raw_agents = self._raw.get("agents", {})

        for agent_id, agent_data in raw_agents.items():
            agents[agent_id] = AgentConfig(
                name=agent_id,
                description=agent_data.get("description", ""),
                model=agent_data.get("model", "sonnet"),
                tools=agent_data.get("tools", []),
            )

        return agents

    def _parse_gates(self) -> dict[str, GateConfig]:
        """Parse gate configurations."""
        gates = {}
        raw_gates = self._raw.get("gates", {})

        for gate_id, gate_data in raw_gates.items():
            if not isinstance(gate_data, dict):
                continue

            commands = []
            for cmd_data in gate_data.get("commands", []):
                commands.append(GateCommand(
                    name=cmd_data["name"],
                    cmd=cmd_data["cmd"],
                    output=cmd_data.get("output", "text"),
                ))

            gates[gate_id] = GateConfig(
                commands=commands,
                fail_fast=gate_data.get("fail_fast", True),
                min_coverage=gate_data.get("min_coverage"),
            )

        return gates

    def _parse_worktree(self) -> WorktreeConfig:
        """Parse worktree configuration."""
        raw_wt = self._raw.get("worktree", {})
        return WorktreeConfig(
            base_path=raw_wt.get("base_path", ".worktrees"),
            branch_prefix=raw_wt.get("branch_prefix", "swiss-cheese"),
            cleanup_on_success=raw_wt.get("cleanup_on_success", True),
            rebase_strategy=raw_wt.get("rebase_strategy", "linear"),
        )


def load_architecture(toml_path: str | Path) -> ProjectConfig:
    """Convenience function to load and parse an architecture document."""
    parser = ArchitectureParser(toml_path)
    return parser.parse()
