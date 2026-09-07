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


def test_source_tests_and_scripts_do_not_import_legacy_internal_paths() -> None:
    legacy = {
        "dj_digger.application",
        "dj_digger.analysis",
        "dj_digger.artifacts",
        "dj_digger.background",
        "dj_digger.catalog",
        "dj_digger.config",
        "dj_digger.curation",
        "dj_digger.duplicates",
        "dj_digger.exports",
        "dj_digger.logging",
        "dj_digger.mcp_server",
        "dj_digger.metadata",
        "dj_digger.progress",
        "dj_digger.resources",
        "dj_digger.rich_progress",
        "dj_digger.scanning",
        "dj_digger.set_copy",
        "dj_digger.terminal",
    }
    roots = (Path("src"), Path("tests"), Path("scripts"))
    violations: list[str] = []
    for root in roots:
        for path in root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for module in imported_modules(tree):
                if any(module == item or module.startswith(f"{item}.") for item in legacy):
                    violations.append(f"{path}: {module}")
    assert not violations, "legacy internal imports remain:\n" + "\n".join(sorted(violations))
