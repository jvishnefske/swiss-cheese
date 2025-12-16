"""Task Scheduler with Topological Sorting.

Uses Python's built-in graphlib.TopologicalSorter for dependency resolution.
Produces batches of tasks that can be executed concurrently.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from graphlib import TopologicalSorter, CycleError
from typing import Iterator

from .toml_parser import ProjectConfig, Task, Layer


@dataclass
class ScheduledBatch:
    """A batch of tasks that can be executed concurrently."""
    batch_number: int
    tasks: list[Task]
    layer: str | None = None  # If all tasks are from same layer

    @property
    def task_names(self) -> list[str]:
        return [t.name for t in self.tasks]

    def __repr__(self) -> str:
        return f"Batch {self.batch_number}: {self.task_names}"


@dataclass
class ScheduleResult:
    """Result of scheduling tasks."""
    batches: list[ScheduledBatch]
    total_tasks: int
    max_parallelism: int  # Maximum concurrent tasks in any batch

    def __iter__(self) -> Iterator[ScheduledBatch]:
        return iter(self.batches)


class TaskScheduler:
    """Schedules tasks using topological sorting.

    Produces batches of tasks that can run concurrently, respecting dependencies.
    """

    def __init__(self, config: ProjectConfig):
        self.config = config
        self._sorter: TopologicalSorter[str] | None = None

    def schedule_tasks(self, task_filter: list[str] | None = None) -> ScheduleResult:
        """Schedule all tasks (or filtered subset) into concurrent batches.

        Args:
            task_filter: Optional list of task names to include. If None, all tasks.

        Returns:
            ScheduleResult with batches of concurrent tasks.

        Raises:
            CycleError: If there's a dependency cycle.
        """
        tasks_to_schedule = self._get_tasks(task_filter)

        # Build dependency graph
        graph: dict[str, set[str]] = {}
        for task in tasks_to_schedule.values():
            # Filter dependencies to only include tasks we're scheduling
            deps = {d for d in task.depends_on if d in tasks_to_schedule}
            graph[task.name] = deps

        # Create topological sorter
        self._sorter = TopologicalSorter(graph)

        try:
            self._sorter.prepare()
        except CycleError as e:
            raise CycleError(f"Dependency cycle detected in tasks: {e}")

        # Extract batches (groups that can run concurrently)
        batches: list[ScheduledBatch] = []
        batch_num = 0
        max_parallelism = 0

        while self._sorter.is_active():
            ready = list(self._sorter.get_ready())
            if not ready:
                break

            batch_tasks = [tasks_to_schedule[name] for name in ready]
            batches.append(ScheduledBatch(
                batch_number=batch_num,
                tasks=batch_tasks,
                layer=self._common_layer(batch_tasks),
            ))

            max_parallelism = max(max_parallelism, len(ready))
            batch_num += 1

            # Mark all as done for next iteration
            for name in ready:
                self._sorter.done(name)

        return ScheduleResult(
            batches=batches,
            total_tasks=len(tasks_to_schedule),
            max_parallelism=max_parallelism,
        )

    def schedule_layers(self) -> ScheduleResult:
        """Schedule layers (not tasks) into concurrent batches.

        Useful for high-level orchestration of verification phases.
        """
        layers = self.config.layers

        # Build dependency graph for layers
        graph: dict[str, set[str]] = {}
        for layer in layers.values():
            deps = {d for d in layer.depends_on if d in layers}
            graph[layer.name] = deps

        sorter: TopologicalSorter[str] = TopologicalSorter(graph)
        sorter.prepare()

        batches: list[ScheduledBatch] = []
        batch_num = 0
        max_parallelism = 0

        while sorter.is_active():
            ready = list(sorter.get_ready())
            if not ready:
                break

            # Create pseudo-tasks for layers
            layer_tasks = [
                Task(
                    name=f"layer:{name}",
                    layer=name,
                    description=layers[name].description,
                    depends_on=layers[name].depends_on,
                )
                for name in ready
            ]

            batches.append(ScheduledBatch(
                batch_number=batch_num,
                tasks=layer_tasks,
            ))

            max_parallelism = max(max_parallelism, len(ready))
            batch_num += 1

            for name in ready:
                sorter.done(name)

        return ScheduleResult(
            batches=batches,
            total_tasks=len(layers),
            max_parallelism=max_parallelism,
        )

    def get_task_order(self) -> list[str]:
        """Get a flat topologically-sorted list of all task names."""
        tasks = self.config.tasks

        graph: dict[str, set[str]] = {}
        for task in tasks.values():
            deps = {d for d in task.depends_on if d in tasks}
            graph[task.name] = deps

        sorter: TopologicalSorter[str] = TopologicalSorter(graph)
        return list(sorter.static_order())

    def _get_tasks(self, task_filter: list[str] | None) -> dict[str, Task]:
        """Get tasks to schedule, optionally filtered."""
        if task_filter is None:
            return self.config.tasks.copy()
        return {name: self.config.tasks[name] for name in task_filter if name in self.config.tasks}

    def _common_layer(self, tasks: list[Task]) -> str | None:
        """Return common layer if all tasks share one, else None."""
        layers = {t.layer for t in tasks}
        return layers.pop() if len(layers) == 1 else None


def print_schedule(schedule: ScheduleResult) -> None:
    """Pretty-print a schedule for debugging."""
    print(f"\n{'='*60}")
    print(f"SCHEDULE: {schedule.total_tasks} tasks in {len(schedule.batches)} batches")
    print(f"Max parallelism: {schedule.max_parallelism}")
    print('='*60)

    for batch in schedule:
        layer_info = f" [{batch.layer}]" if batch.layer else ""
        print(f"\nBatch {batch.batch_number}{layer_info}:")
        for task in batch.tasks:
            deps = f" <- {task.depends_on}" if task.depends_on else ""
            print(f"  • {task.name}: {task.description[:50]}{deps}")

    print()
