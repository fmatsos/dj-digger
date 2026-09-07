"""Architecture checks for the core/application boundary."""

import ast
from pathlib import Path


def module_name_for_path(path: Path) -> str | None:
    """Return the import name represented by a source file under ``src``."""
    try:
        relative = path.relative_to(Path("src")).with_suffix("")
    except ValueError:
        return None
    parts = list(relative.parts)
    return ".".join(parts)


def imported_modules(tree: ast.AST, module_name: str | None = None) -> set[str]:
    """Collect static, relative, and literal dynamic imports from an AST."""
    modules: set[str] = set()
    importlib_aliases = {"importlib"}
    import_module_aliases = {"import_module"}

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "importlib":
                    importlib_aliases.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module == "importlib":
            for alias in node.names:
                if alias.name == "import_module":
                    import_module_aliases.add(alias.asname or alias.name)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module is None and node.level == 0:
                continue
            if node.level == 0:
                assert node.module is not None
                modules.add(node.module)
            elif module_name is not None:
                package = module_name.split(".")[:-1]
                package = package[: len(package) - node.level + 1]
                if node.module:
                    package.append(node.module)
                modules.add(".".join(package))
        elif isinstance(node, ast.Call):
            dynamic_name: str | None = None
            if isinstance(node.func, ast.Name):
                if node.func.id in import_module_aliases or node.func.id == "__import__":
                    dynamic_name = "dynamic"
            elif (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "import_module"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id in importlib_aliases
            ):
                dynamic_name = "dynamic"
            if dynamic_name and node.args:
                try:
                    imported = ast.literal_eval(node.args[0])
                except (ValueError, TypeError):
                    imported = None
                if isinstance(imported, str):
                    modules.add(imported)
    return modules


def test_imported_modules_resolves_relative_and_dynamic_imports() -> None:
    tree = ast.parse(
        "from .analysis import worker\n"
        "import importlib as loader\n"
        "loader.import_module('dj_digger.catalog.database')\n"
        "__import__('dj_digger.config')\n"
    )

    assert imported_modules(tree, "dj_digger.cli.app") >= {
        "dj_digger.cli.analysis",
        "dj_digger.catalog.database",
        "dj_digger.config",
    }


def test_core_never_imports_cli_or_presentation_libraries() -> None:
    forbidden = ("dj_digger.cli", "typer", "rich")
    for path in Path("src/dj_digger/core").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = imported_modules(tree, module_name_for_path(path))
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
            for module in imported_modules(tree, module_name_for_path(path)):
                if any(module == item or module.startswith(f"{item}.") for item in legacy):
                    violations.append(f"{path}: {module}")
    assert not violations, "legacy internal imports remain:\n" + "\n".join(sorted(violations))
