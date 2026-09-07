"""Architecture checks for the core/application boundary."""

import ast
from pathlib import Path


def imported_modules(tree: ast.AST) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module)
    return modules


def test_core_never_imports_cli_or_presentation_libraries() -> None:
    forbidden = ("dj_digger.cli", "typer", "rich")
    for path in Path("src/dj_digger/core").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = imported_modules(tree)
        assert not any(
            name == item or name.startswith(f"{item}.") for item in forbidden for name in imports
        )
