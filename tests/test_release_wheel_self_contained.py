"""Release-wheel self-containment gate.

Regression for the 2026-07-17 packaging defect: pyproject shipped
``dopey.settlement``/``dopey.truth`` whose module-level imports resolved only
inside the laboratory tree, so the installed wheel raised
``ModuleNotFoundError``. The defect was masked during smoke testing by an
editable-install meta-path finder that silently backfilled missing modules
from a full repository clone.

This test is static (AST-based), hermetic, and needs no wheel build:

1. Every package named in ``[tool.setuptools.packages.find] include`` must
   exist on disk.
2. Every import that executes at import time in a shipped module must resolve
   to (a) another shipped package, (b) the standard library, or (c) a declared
   runtime dependency. Laboratory packages (``dopey_*`` top-levels and
   non-shipped ``dopey.*`` subpackages) are forbidden at import time.
"""
from __future__ import annotations

import ast
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Canonical import names for declared distribution names whose module name
# differs from the distribution name.
_DIST_TO_MODULE = {
    "exchange-calendars": "exchange_calendars",
}


def _packaging_config() -> tuple[list[str], set[str]]:
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    include = pyproject["tool"]["setuptools"]["packages"]["find"]["include"]
    deps = set()
    for spec in pyproject["project"]["dependencies"]:
        dist = spec.split("==")[0].split(">=")[0].split("<")[0].strip()
        deps.add(_DIST_TO_MODULE.get(dist, dist.replace("-", "_")))
    return include, deps


def _shipped_prefixes(include: list[str]) -> set[str]:
    """Dotted package prefixes covered by the include globs."""
    return {pattern.rstrip("*").rstrip(".") for pattern in include}


def _is_shipped(module: str, prefixes: set[str]) -> bool:
    if module in prefixes:
        return True
    # "dopey" alone ships only the top-level __init__, not every subpackage,
    # so a bare prefix match on "dopey" must not admit "dopey.memory".
    return any(
        module.startswith(prefix + ".")
        for prefix in prefixes
        if "." in prefix or prefix not in {"dopey"}
    )


def _import_time_imports(tree: ast.Module) -> list[ast.stmt]:
    """Import statements that execute when the module is imported.

    Function and async-function bodies are lazy; class bodies and every other
    top-level construct (including try/except fallbacks) execute at import
    time and therefore count.
    """
    found: list[ast.stmt] = []

    def walk(node: ast.AST) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if isinstance(child, (ast.Import, ast.ImportFrom)):
                found.append(child)
            walk(child)

    walk(tree)
    return found


def _shipped_python_files(include: list[str]) -> list[Path]:
    files: list[Path] = []
    for pattern in include:
        recursive = pattern.endswith("*")
        pkg_dir = REPO_ROOT / pattern.rstrip("*").rstrip(".").replace(".", "/")
        if not pkg_dir.is_dir():
            continue
        if recursive:
            files.extend(pkg_dir.rglob("*.py"))
        else:
            files.extend(pkg_dir.glob("*.py"))
    return sorted(set(files))


def test_included_packages_exist() -> None:
    include, _ = _packaging_config()
    missing = [
        pattern
        for pattern in include
        if not (REPO_ROOT / pattern.rstrip("*").rstrip(".").replace(".", "/")).is_dir()
    ]
    assert not missing, f"pyproject include names missing package dirs: {missing}"


def test_shipped_modules_have_no_laboratory_imports() -> None:
    include, declared_deps = _packaging_config()
    prefixes = _shipped_prefixes(include)
    stdlib = set(sys.stdlib_module_names)
    violations: list[str] = []

    for py_file in _shipped_python_files(include):
        rel = py_file.relative_to(REPO_ROOT)
        tree = ast.parse(py_file.read_text(encoding="utf-8"))
        for stmt in _import_time_imports(tree):
            if isinstance(stmt, ast.ImportFrom):
                if stmt.level:  # relative: stays inside a shipped package
                    continue
                modules = [stmt.module] if stmt.module else []
            else:
                modules = [alias.name for alias in stmt.names]
            for module in modules:
                top = module.split(".")[0]
                if top in stdlib or top in declared_deps:
                    continue
                if _is_shipped(module, prefixes):
                    continue
                violations.append(f"{rel}:{stmt.lineno} imports {module}")

    assert not violations, (
        "shipped modules import packages the release wheel does not contain "
        "(lazy imports inside function bodies are permitted; these run at "
        "import time):\n  " + "\n  ".join(violations)
    )
