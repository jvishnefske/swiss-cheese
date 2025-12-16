"""Tests for the task scheduler with topological sorting.

These tests verify dependency resolution and batch scheduling without
requiring any external API calls.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from graphlib import CycleError


def _load_module_directly(module_name: str, file_path: Path):
    """Load a module directly from file, bypassing package __init__.py."""
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


# Load modules directly to avoid importing orchestrator/__init__.py
# which requires claude_agent_sdk
_base_path = Path(__file__).parent.parent / "orchestrator"

_toml_parser = _load_module_directly(
    "orchestrator.toml_parser",
    _base_path / "toml_parser.py"
)
_scheduler = _load_module_directly(
    "orchestrator.scheduler",
    _base_path / "scheduler.py"
)

ProjectConfig = _toml_parser.ProjectConfig
Layer = _toml_parser.Layer
Task = _toml_parser.Task
WorktreeConfig = _toml_parser.WorktreeConfig

TaskScheduler = _scheduler.TaskScheduler
ScheduledBatch = _scheduler.ScheduledBatch
ScheduleResult = _scheduler.ScheduleResult


def make_config(
    tasks: dict[str, Task] | None = None,
    layers: dict[str, Layer] | None = None,
) -> ProjectConfig:
    """Create a minimal ProjectConfig for testing."""
    return ProjectConfig(
        name="test",
        version="1.0",
        language="rust",
        description="Test project",
        layers=layers or {},
        tasks=tasks or {},
        agents={},
        gates={},
        worktree=WorktreeConfig(),
    )


def make_task(name: str, layer: str = "default", depends_on: list[str] | None = None) -> Task:
    """Create a task for testing."""
    return Task(
        name=name,
        layer=layer,
        description=f"Task {name}",
        depends_on=depends_on or [],
    )


def make_layer(name: str, order: int = 1, depends_on: list[str] | None = None) -> Layer:
    """Create a layer for testing."""
    return Layer(
        name=name,
        display_name=name.title(),
        description=f"Layer {name}",
        order=order,
        depends_on=depends_on or [],
    )


class TestScheduledBatch:
    """Tests for ScheduledBatch data class."""

    def test_task_names_property(self):
        """task_names should return list of task names."""
        tasks = [make_task("a"), make_task("b"), make_task("c")]
        batch = ScheduledBatch(batch_number=0, tasks=tasks)

        assert batch.task_names == ["a", "b", "c"]

    def test_repr(self):
        """repr should show batch number and task names."""
        tasks = [make_task("task1"), make_task("task2")]
        batch = ScheduledBatch(batch_number=2, tasks=tasks)

        assert "Batch 2" in repr(batch)
        assert "task1" in repr(batch)
        assert "task2" in repr(batch)

    def test_layer_when_all_same(self):
        """layer should be set when all tasks share a layer."""
        tasks = [make_task("a", layer="L1"), make_task("b", layer="L1")]
        batch = ScheduledBatch(batch_number=0, tasks=tasks, layer="L1")

        assert batch.layer == "L1"


class TestScheduleResult:
    """Tests for ScheduleResult data class."""

    def test_iteration(self):
        """ScheduleResult should be iterable over batches."""
        batches = [
            ScheduledBatch(batch_number=0, tasks=[make_task("a")]),
            ScheduledBatch(batch_number=1, tasks=[make_task("b")]),
        ]
        result = ScheduleResult(batches=batches, total_tasks=2, max_parallelism=1)

        collected = list(result)
        assert len(collected) == 2
        assert collected[0].batch_number == 0
        assert collected[1].batch_number == 1


class TestTaskSchedulerBasic:
    """Basic tests for TaskScheduler."""

    def test_empty_tasks(self):
        """Scheduling empty task list should return empty result."""
        config = make_config(tasks={})
        scheduler = TaskScheduler(config)
        result = scheduler.schedule_tasks()

        assert result.total_tasks == 0
        assert result.batches == []
        assert result.max_parallelism == 0

    def test_single_task(self):
        """Single task should be scheduled in one batch."""
        tasks = {"task1": make_task("task1")}
        config = make_config(tasks=tasks)
        scheduler = TaskScheduler(config)
        result = scheduler.schedule_tasks()

        assert result.total_tasks == 1
        assert len(result.batches) == 1
        assert result.batches[0].task_names == ["task1"]
        assert result.max_parallelism == 1

    def test_independent_tasks_parallel(self):
        """Independent tasks should be scheduled in same batch."""
        tasks = {
            "a": make_task("a"),
            "b": make_task("b"),
            "c": make_task("c"),
        }
        config = make_config(tasks=tasks)
        scheduler = TaskScheduler(config)
        result = scheduler.schedule_tasks()

        assert result.total_tasks == 3
        assert len(result.batches) == 1
        assert set(result.batches[0].task_names) == {"a", "b", "c"}
        assert result.max_parallelism == 3


class TestTaskSchedulerDependencies:
    """Tests for dependency resolution."""

    def test_linear_dependency_chain(self):
        """Linear dependencies should produce sequential batches."""
        tasks = {
            "a": make_task("a"),
            "b": make_task("b", depends_on=["a"]),
            "c": make_task("c", depends_on=["b"]),
        }
        config = make_config(tasks=tasks)
        scheduler = TaskScheduler(config)
        result = scheduler.schedule_tasks()

        assert result.total_tasks == 3
        assert len(result.batches) == 3
        assert result.batches[0].task_names == ["a"]
        assert result.batches[1].task_names == ["b"]
        assert result.batches[2].task_names == ["c"]
        assert result.max_parallelism == 1

    def test_diamond_dependency(self):
        """Diamond pattern should parallelize middle tasks."""
        #     a
        #    / \
        #   b   c
        #    \ /
        #     d
        tasks = {
            "a": make_task("a"),
            "b": make_task("b", depends_on=["a"]),
            "c": make_task("c", depends_on=["a"]),
            "d": make_task("d", depends_on=["b", "c"]),
        }
        config = make_config(tasks=tasks)
        scheduler = TaskScheduler(config)
        result = scheduler.schedule_tasks()

        assert result.total_tasks == 4
        assert len(result.batches) == 3
        assert result.batches[0].task_names == ["a"]
        assert set(result.batches[1].task_names) == {"b", "c"}
        assert result.batches[2].task_names == ["d"]
        assert result.max_parallelism == 2

    def test_multiple_roots(self):
        """Multiple independent roots should run in parallel."""
        tasks = {
            "root1": make_task("root1"),
            "root2": make_task("root2"),
            "child1": make_task("child1", depends_on=["root1"]),
            "child2": make_task("child2", depends_on=["root2"]),
        }
        config = make_config(tasks=tasks)
        scheduler = TaskScheduler(config)
        result = scheduler.schedule_tasks()

        assert result.total_tasks == 4
        # First batch has both roots
        assert set(result.batches[0].task_names) == {"root1", "root2"}
        # Second batch has both children
        assert set(result.batches[1].task_names) == {"child1", "child2"}

    def test_cycle_detection(self):
        """Circular dependencies should raise CycleError."""
        tasks = {
            "a": make_task("a", depends_on=["c"]),
            "b": make_task("b", depends_on=["a"]),
            "c": make_task("c", depends_on=["b"]),
        }
        config = make_config(tasks=tasks)
        scheduler = TaskScheduler(config)

        with pytest.raises(CycleError):
            scheduler.schedule_tasks()

    def test_self_dependency_cycle(self):
        """Self-referential dependency should raise CycleError."""
        tasks = {
            "a": make_task("a", depends_on=["a"]),
        }
        config = make_config(tasks=tasks)
        scheduler = TaskScheduler(config)

        with pytest.raises(CycleError):
            scheduler.schedule_tasks()


class TestTaskSchedulerFiltering:
    """Tests for task filtering."""

    def test_filter_subset(self):
        """Filtering should only schedule specified tasks."""
        tasks = {
            "a": make_task("a"),
            "b": make_task("b"),
            "c": make_task("c"),
        }
        config = make_config(tasks=tasks)
        scheduler = TaskScheduler(config)
        result = scheduler.schedule_tasks(task_filter=["a", "c"])

        assert result.total_tasks == 2
        task_names = [name for batch in result.batches for name in batch.task_names]
        assert set(task_names) == {"a", "c"}

    def test_filter_with_dependencies(self):
        """Filtered tasks should respect internal dependencies."""
        tasks = {
            "a": make_task("a"),
            "b": make_task("b", depends_on=["a"]),
            "c": make_task("c", depends_on=["a"]),
        }
        config = make_config(tasks=tasks)
        scheduler = TaskScheduler(config)
        result = scheduler.schedule_tasks(task_filter=["a", "b"])

        assert result.total_tasks == 2
        assert result.batches[0].task_names == ["a"]
        assert result.batches[1].task_names == ["b"]

    def test_filter_ignores_external_dependencies(self):
        """Dependencies on non-filtered tasks should be ignored."""
        tasks = {
            "a": make_task("a"),
            "b": make_task("b", depends_on=["a"]),
        }
        config = make_config(tasks=tasks)
        scheduler = TaskScheduler(config)
        # Only schedule b, without a - dependency should be ignored
        result = scheduler.schedule_tasks(task_filter=["b"])

        assert result.total_tasks == 1
        assert result.batches[0].task_names == ["b"]

    def test_filter_nonexistent_tasks(self):
        """Filtering with nonexistent task names should ignore them."""
        tasks = {
            "a": make_task("a"),
        }
        config = make_config(tasks=tasks)
        scheduler = TaskScheduler(config)
        result = scheduler.schedule_tasks(task_filter=["a", "nonexistent"])

        assert result.total_tasks == 1
        assert result.batches[0].task_names == ["a"]


class TestTaskSchedulerLayers:
    """Tests for layer scheduling."""

    def test_schedule_empty_layers(self):
        """Scheduling empty layers should return empty result."""
        config = make_config(layers={})
        scheduler = TaskScheduler(config)
        result = scheduler.schedule_layers()

        assert result.total_tasks == 0
        assert result.batches == []

    def test_schedule_independent_layers(self):
        """Independent layers should be scheduled in parallel."""
        layers = {
            "L1": make_layer("L1", order=1),
            "L2": make_layer("L2", order=2),
        }
        config = make_config(layers=layers)
        scheduler = TaskScheduler(config)
        result = scheduler.schedule_layers()

        assert result.total_tasks == 2
        assert len(result.batches) == 1
        assert result.max_parallelism == 2

    def test_schedule_dependent_layers(self):
        """Dependent layers should be scheduled sequentially."""
        layers = {
            "L1": make_layer("L1", order=1),
            "L2": make_layer("L2", order=2, depends_on=["L1"]),
            "L3": make_layer("L3", order=3, depends_on=["L2"]),
        }
        config = make_config(layers=layers)
        scheduler = TaskScheduler(config)
        result = scheduler.schedule_layers()

        assert result.total_tasks == 3
        assert len(result.batches) == 3
        assert "layer:L1" in result.batches[0].task_names
        assert "layer:L2" in result.batches[1].task_names
        assert "layer:L3" in result.batches[2].task_names


class TestTaskSchedulerCommonLayer:
    """Tests for common layer detection."""

    def test_common_layer_same(self):
        """Tasks in same layer should have common layer."""
        tasks = {
            "a": make_task("a", layer="L1"),
            "b": make_task("b", layer="L1"),
        }
        config = make_config(tasks=tasks)
        scheduler = TaskScheduler(config)
        result = scheduler.schedule_tasks()

        assert result.batches[0].layer == "L1"

    def test_common_layer_different(self):
        """Tasks in different layers should have None common layer."""
        tasks = {
            "a": make_task("a", layer="L1"),
            "b": make_task("b", layer="L2"),
        }
        config = make_config(tasks=tasks)
        scheduler = TaskScheduler(config)
        result = scheduler.schedule_tasks()

        assert result.batches[0].layer is None


class TestGetTaskOrder:
    """Tests for get_task_order method."""

    def test_get_task_order_simple(self):
        """get_task_order should return topologically sorted list."""
        tasks = {
            "a": make_task("a"),
            "b": make_task("b", depends_on=["a"]),
            "c": make_task("c", depends_on=["b"]),
        }
        config = make_config(tasks=tasks)
        scheduler = TaskScheduler(config)
        order = scheduler.get_task_order()

        assert order.index("a") < order.index("b")
        assert order.index("b") < order.index("c")

    def test_get_task_order_parallel(self):
        """get_task_order should include all tasks even if parallel."""
        tasks = {
            "a": make_task("a"),
            "b": make_task("b"),
            "c": make_task("c"),
        }
        config = make_config(tasks=tasks)
        scheduler = TaskScheduler(config)
        order = scheduler.get_task_order()

        assert set(order) == {"a", "b", "c"}
