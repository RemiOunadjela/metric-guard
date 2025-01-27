"""Dependency graph for metric definitions."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable

from metric_guard.registry.metric import MetricDefinition


class CyclicDependencyError(Exception):
    """Raised when the metric dependency graph contains a cycle."""


class DependencyGraph:
    """DAG of metric dependencies with topological ordering.

    Used to determine safe validation order -- downstream metrics should
    only be validated after their upstream dependencies pass.
    """

    def __init__(self, metrics: Iterable[MetricDefinition]) -> None:
        self._metrics: dict[str, MetricDefinition] = {}
        self._edges: dict[str, set[str]] = {}  # parent -> children
        self._reverse: dict[str, set[str]] = {}  # child -> parents

        for m in metrics:
            self._metrics[m.name] = m
            self._edges.setdefault(m.name, set())
            self._reverse.setdefault(m.name, set())

        for m in self._metrics.values():
            for dep in m.depends_on:
                if dep in self._metrics:
                    self._edges[dep].add(m.name)
                    self._reverse[m.name].add(dep)

    @property
    def metric_names(self) -> list[str]:
        return list(self._metrics.keys())

    def upstream(self, name: str) -> set[str]:
        """All transitive upstream dependencies of a metric."""
        visited: set[str] = set()
        queue = deque(self._reverse.get(name, set()))
        while queue:
            current = queue.popleft()
            if current not in visited:
                visited.add(current)
                queue.extend(self._reverse.get(current, set()) - visited)
        return visited

    def downstream(self, name: str) -> set[str]:
        """All transitive downstream dependents of a metric."""
        visited: set[str] = set()
        queue = deque(self._edges.get(name, set()))
        while queue:
            current = queue.popleft()
            if current not in visited:
                visited.add(current)
                queue.extend(self._edges.get(current, set()) - visited)
        return visited

    def topological_order(self) -> list[str]:
        """Return metrics in dependency-safe validation order.

        Raises CyclicDependencyError if the graph has cycles.
        """
        in_degree = {name: len(parents) for name, parents in self._reverse.items()}
        queue = deque(name for name, deg in in_degree.items() if deg == 0)
        result: list[str] = []

        while queue:
            node = queue.popleft()
            result.append(node)
            for child in self._edges.get(node, set()):
                in_degree[child] -= 1
                if in_degree[child] == 0:
                    queue.append(child)

        if len(result) != len(self._metrics):
            missing = set(self._metrics.keys()) - set(result)
            raise CyclicDependencyError(
                f"Cyclic dependency detected involving: {', '.join(sorted(missing))}"
            )

        return result

    def get_metric(self, name: str) -> MetricDefinition:
        return self._metrics[name]
