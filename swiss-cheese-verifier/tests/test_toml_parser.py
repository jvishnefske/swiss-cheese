"""Tests for the TOML architecture parser.

These tests verify parsing of TOML configuration files without
requiring any external API calls.
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

import pytest


def _load_module_directly(module_name: str, file_path: Path):
    """Load a module directly from file, bypassing package __init__.py."""
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


# Load toml_parser directly to avoid importing orchestrator/__init__.py
# which requires claude_agent_sdk
_toml_parser = _load_module_directly(
    "orchestrator.toml_parser",
    Path(__file__).parent.parent / "orchestrator" / "toml_parser.py"
)

ArchitectureParser = _toml_parser.ArchitectureParser
ProjectConfig = _toml_parser.ProjectConfig
Layer = _toml_parser.Layer
Task = _toml_parser.Task
AgentConfig = _toml_parser.AgentConfig
GateConfig = _toml_parser.GateConfig
GateCommand = _toml_parser.GateCommand
WorktreeConfig = _toml_parser.WorktreeConfig
load_architecture = _toml_parser.load_architecture


@pytest.fixture
def minimal_toml_content():
    """Minimal valid TOML content."""
    return """
[project]
name = "test-project"
version = "0.1.0"
language = "rust"
description = "A test project"
"""


@pytest.fixture
def full_toml_content():
    """Full TOML content with all sections."""
    return """
[project]
name = "full-test-project"
version = "1.0.0"
language = "rust"
description = "A complete test project"

[project.toolchain]
rust = "1.75.0"
edition = "2021"

[layers.layer1]
name = "First Layer"
description = "The first verification layer"
order = 1
gate = "gates/layer1.sh"
reports = ["json", "html"]

[layers.layer2]
name = "Second Layer"
description = "The second verification layer"
order = 2
depends_on = ["layer1"]
optional = true

[tasks.task1]
layer = "layer1"
description = "First task"
agent = "test-agent"

[tasks.task2]
layer = "layer1"
description = "Second task"
depends_on = ["task1"]
command = "cargo test"

[tasks.task3]
layer = "layer2"
description = "Third task"
depends_on = ["task2"]
optional = true

[agents.test-agent]
description = "A test agent"
model = "opus"
tools = ["Read", "Write", "Bash"]

[gates.layer1]
commands = [
    { name = "test", cmd = "cargo test", output = "json" },
    { name = "clippy", cmd = "cargo clippy", output = "text" },
]
fail_fast = false
min_coverage = 80

[worktree]
base_path = ".custom-worktrees"
branch_prefix = "test-prefix"
cleanup_on_success = false
rebase_strategy = "merge"
"""


@pytest.fixture
def minimal_toml_file(minimal_toml_content):
    """Create a temporary minimal TOML file."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as f:
        f.write(minimal_toml_content)
        return Path(f.name)


@pytest.fixture
def full_toml_file(full_toml_content):
    """Create a temporary full TOML file."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as f:
        f.write(full_toml_content)
        return Path(f.name)


class TestArchitectureParserMinimal:
    """Tests for minimal TOML parsing."""

    def test_parse_minimal_project(self, minimal_toml_file):
        """Parse a minimal TOML file with only project section."""
        parser = ArchitectureParser(minimal_toml_file)
        config = parser.parse()

        assert config.name == "test-project"
        assert config.version == "0.1.0"
        assert config.language == "rust"
        assert config.description == "A test project"

    def test_parse_minimal_has_empty_collections(self, minimal_toml_file):
        """Minimal config should have empty dicts for optional sections."""
        parser = ArchitectureParser(minimal_toml_file)
        config = parser.parse()

        assert config.layers == {}
        assert config.tasks == {}
        assert config.agents == {}
        assert config.gates == {}
        assert config.toolchain == {}

    def test_parse_minimal_has_default_worktree(self, minimal_toml_file):
        """Minimal config should have default worktree settings."""
        parser = ArchitectureParser(minimal_toml_file)
        config = parser.parse()

        assert config.worktree.base_path == ".worktrees"
        assert config.worktree.branch_prefix == "swiss-cheese"
        assert config.worktree.cleanup_on_success is True
        assert config.worktree.rebase_strategy == "linear"


class TestArchitectureParserFull:
    """Tests for full TOML parsing."""

    def test_parse_project_section(self, full_toml_file):
        """Parse project section from full TOML."""
        config = load_architecture(full_toml_file)

        assert config.name == "full-test-project"
        assert config.version == "1.0.0"
        assert config.language == "rust"
        assert config.toolchain["rust"] == "1.75.0"
        assert config.toolchain["edition"] == "2021"

    def test_parse_layers(self, full_toml_file):
        """Parse layer definitions."""
        config = load_architecture(full_toml_file)

        assert len(config.layers) == 2
        assert "layer1" in config.layers
        assert "layer2" in config.layers

        layer1 = config.layers["layer1"]
        assert layer1.name == "layer1"
        assert layer1.display_name == "First Layer"
        assert layer1.description == "The first verification layer"
        assert layer1.order == 1
        assert layer1.gate == "gates/layer1.sh"
        assert layer1.reports == ["json", "html"]
        assert layer1.depends_on == []
        assert layer1.optional is False

        layer2 = config.layers["layer2"]
        assert layer2.depends_on == ["layer1"]
        assert layer2.optional is True

    def test_parse_tasks(self, full_toml_file):
        """Parse task definitions."""
        config = load_architecture(full_toml_file)

        assert len(config.tasks) == 3

        task1 = config.tasks["task1"]
        assert task1.name == "task1"
        assert task1.layer == "layer1"
        assert task1.description == "First task"
        assert task1.agent == "test-agent"
        assert task1.depends_on == []
        assert task1.command is None
        assert task1.optional is False

        task2 = config.tasks["task2"]
        assert task2.depends_on == ["task1"]
        assert task2.command == "cargo test"

        task3 = config.tasks["task3"]
        assert task3.optional is True

    def test_parse_agents(self, full_toml_file):
        """Parse agent definitions."""
        config = load_architecture(full_toml_file)

        assert len(config.agents) == 1
        agent = config.agents["test-agent"]

        assert agent.name == "test-agent"
        assert agent.description == "A test agent"
        assert agent.model == "opus"
        assert agent.tools == ["Read", "Write", "Bash"]

    def test_parse_gates(self, full_toml_file):
        """Parse gate configurations."""
        config = load_architecture(full_toml_file)

        assert len(config.gates) == 1
        gate = config.gates["layer1"]

        assert len(gate.commands) == 2
        assert gate.fail_fast is False
        assert gate.min_coverage == 80

        cmd1 = gate.commands[0]
        assert cmd1.name == "test"
        assert cmd1.cmd == "cargo test"
        assert cmd1.output == "json"

        cmd2 = gate.commands[1]
        assert cmd2.name == "clippy"
        assert cmd2.output == "text"

    def test_parse_worktree(self, full_toml_file):
        """Parse worktree configuration."""
        config = load_architecture(full_toml_file)

        assert config.worktree.base_path == ".custom-worktrees"
        assert config.worktree.branch_prefix == "test-prefix"
        assert config.worktree.cleanup_on_success is False
        assert config.worktree.rebase_strategy == "merge"


class TestProjectConfigMethods:
    """Tests for ProjectConfig helper methods."""

    def test_get_layer_tasks(self, full_toml_file):
        """Test filtering tasks by layer."""
        config = load_architecture(full_toml_file)

        layer1_tasks = config.get_layer_tasks("layer1")
        assert len(layer1_tasks) == 2
        assert all(t.layer == "layer1" for t in layer1_tasks)

        layer2_tasks = config.get_layer_tasks("layer2")
        assert len(layer2_tasks) == 1
        assert layer2_tasks[0].name == "task3"

    def test_get_layer_tasks_empty(self, full_toml_file):
        """Test filtering tasks for non-existent layer."""
        config = load_architecture(full_toml_file)

        tasks = config.get_layer_tasks("nonexistent")
        assert tasks == []


class TestParserEdgeCases:
    """Tests for edge cases and error handling."""

    def test_parse_missing_file(self):
        """Parsing non-existent file should raise FileNotFoundError."""
        parser = ArchitectureParser("/nonexistent/path.toml")
        with pytest.raises(FileNotFoundError):
            parser.parse()

    def test_parse_invalid_toml(self):
        """Parsing invalid TOML should raise an error."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as f:
            f.write("this is not valid toml [[[")
            path = Path(f.name)

        parser = ArchitectureParser(path)
        with pytest.raises(Exception):  # tomllib.TOMLDecodeError
            parser.parse()

    def test_parse_missing_required_project_fields(self):
        """Missing required project fields should raise KeyError."""
        content = """
[project]
name = "test"
# missing version and language
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as f:
            f.write(content)
            path = Path(f.name)

        parser = ArchitectureParser(path)
        with pytest.raises(KeyError):
            parser.parse()

    def test_agent_default_values(self):
        """Agents should have default values for optional fields."""
        content = """
[project]
name = "test"
version = "1.0"
language = "rust"

[agents.minimal-agent]
# Only implicit fields, all optional
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as f:
            f.write(content)
            path = Path(f.name)

        config = load_architecture(path)
        agent = config.agents["minimal-agent"]

        assert agent.name == "minimal-agent"
        assert agent.description == ""
        assert agent.model == "sonnet"
        assert agent.tools == []

    def test_gate_command_default_output(self):
        """Gate commands should default to text output."""
        content = """
[project]
name = "test"
version = "1.0"
language = "rust"

[gates.test-gate]
commands = [
    { name = "simple", cmd = "echo hello" }
]
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as f:
            f.write(content)
            path = Path(f.name)

        config = load_architecture(path)
        cmd = config.gates["test-gate"].commands[0]

        assert cmd.output == "text"


class TestLoadArchitectureConvenience:
    """Tests for the load_architecture convenience function."""

    def test_load_architecture_returns_project_config(self, minimal_toml_file):
        """load_architecture should return a ProjectConfig instance."""
        config = load_architecture(minimal_toml_file)
        assert isinstance(config, ProjectConfig)

    def test_load_architecture_with_path_string(self, minimal_toml_file):
        """load_architecture should accept string paths."""
        config = load_architecture(str(minimal_toml_file))
        assert config.name == "test-project"

    def test_load_architecture_with_path_object(self, minimal_toml_file):
        """load_architecture should accept Path objects."""
        config = load_architecture(minimal_toml_file)
        assert config.name == "test-project"
