"""Executable layering rules: dependencies point inwards, and no import cycles."""

import ast
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src" / "dj_digger"


def _module_name(path: Path) -> str:
    relative = path.relative_to(SOURCE_ROOT.parent).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _imported_modules(path: Path) -> Iterator[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.module


def _internal_imports() -> dict[str, set[str]]:
    graph: dict[str, set[str]] = {}
    for path in sorted(SOURCE_ROOT.rglob("*.py")):
        module = _module_name(path)
        graph[module] = {name for name in _imported_modules(path) if name.startswith("dj_digger.")}
    return graph


def test_the_domain_never_depends_on_the_application_layer() -> None:
    """Ports belong to the domain; a use case may depend on them, never the reverse."""
    offenders = {
        module: sorted(
            target for target in targets if target.startswith("dj_digger.core.application")
        )
        for module, targets in _internal_imports().items()
        if module.startswith("dj_digger.core.")
        and not module.startswith("dj_digger.core.application")
        and any(target.startswith("dj_digger.core.application") for target in targets)
    }

    assert offenders == {}


#: Inbound adapters translate an external protocol into domain calls. They may
#: depend on the domain; the domain must never depend on them.
INBOUND_ADAPTERS = ("dj_digger.core.mcp_server",)


def test_the_domain_never_depends_on_an_inbound_adapter() -> None:
    """A lazy import that survives the cycle still points the wrong way."""
    offenders = {
        module: sorted(target for target in targets if target.startswith(INBOUND_ADAPTERS))
        for module, targets in _internal_imports().items()
        if module.startswith("dj_digger.core.")
        and not module.startswith(INBOUND_ADAPTERS)
        and not module.startswith("dj_digger.core.application")
        and any(target.startswith(INBOUND_ADAPTERS) for target in targets)
    }

    assert offenders == {}


def test_the_core_never_depends_on_the_cli() -> None:
    offenders = {
        module: sorted(target for target in targets if target.startswith("dj_digger.cli"))
        for module, targets in _internal_imports().items()
        if module.startswith("dj_digger.core")
        and any(target.startswith("dj_digger.cli") for target in targets)
    }

    assert offenders == {}


def _cycles(graph: dict[str, set[str]]) -> list[list[str]]:
    """Return every import cycle, resolving targets to the modules that exist."""
    known = set(graph)

    def resolve(target: str) -> str | None:
        while target and target not in known:
            target, _, _ = target.rpartition(".")
        return target or None

    edges = {
        module: {
            resolved
            for target in targets
            if (resolved := resolve(target)) is not None and resolved != module
        }
        for module, targets in graph.items()
    }
    found: list[list[str]] = []
    state: dict[str, int] = {}
    stack: list[str] = []

    def visit(module: str) -> None:
        state[module] = 1
        stack.append(module)
        for target in sorted(edges.get(module, ())):
            if state.get(target, 0) == 0:
                visit(target)
            elif state[target] == 1:
                found.append(stack[stack.index(target) :] + [target])
        stack.pop()
        state[module] = 2

    for module in sorted(edges):
        if state.get(module, 0) == 0:
            visit(module)
    return found


def test_the_package_has_no_import_cycles() -> None:
    """A cycle only works by accident of import order; it is a latent failure."""
    previous_limit = sys.getrecursionlimit()
    sys.setrecursionlimit(max(previous_limit, 5_000))
    try:
        cycles = _cycles(_internal_imports())
    finally:
        sys.setrecursionlimit(previous_limit)

    assert cycles == []


@pytest.mark.parametrize(
    "module", ["dj_digger.core.progress", "dj_digger.core.analysis", "dj_digger.core.catalog"]
)
def test_domain_packages_import_without_the_application_layer(module: str) -> None:
    """Each domain package must be importable on its own."""
    import importlib

    assert importlib.import_module(module) is not None
