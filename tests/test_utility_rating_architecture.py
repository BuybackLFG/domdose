import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
PACKAGE = ROOT / "utility_rating"
FORBIDDEN_IMPORTS = {
    "aiohttp",
    "asyncio",
    "fastapi",
    "glob",
    "http",
    "httpx",
    "io",
    "os",
    "pathlib",
    "psycopg",
    "random",
    "requests",
    "secrets",
    "shutil",
    "socket",
    "sqlalchemy",
    "sqlite3",
    "starlette",
    "subprocess",
    "tempfile",
    "time",
    "urllib",
    "uuid",
    "uvicorn",
}
FORBIDDEN_CALLS = {"open", "now", "utcnow", "today"}


def module_sources() -> list[tuple[Path, ast.Module]]:
    sources = [
        (path, ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
        for path in PACKAGE.glob("*.py")
    ]
    assert sources
    return sources


@pytest.mark.parametrize(("path", "tree"), module_sources())
def test_scoring_package_has_no_io_or_relative_imports(
    path: Path, tree: ast.Module
) -> None:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots = {alias.name.split(".")[0] for alias in node.names}
            assert not roots & FORBIDDEN_IMPORTS, path
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, path
            assert (node.module or "").split(".")[0] not in FORBIDDEN_IMPORTS, path
        elif isinstance(node, ast.Call):
            assert not (
                isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_CALLS
            ), path
            assert not (
                isinstance(node.func, ast.Attribute)
                and node.func.attr in FORBIDDEN_CALLS
            ), path


PROJECT_ROOTS = {"api", "contract", "core", "dossier", "sources", "tests", "utility_rating"}
SCORING_ENTRYPOINT = ROOT / "api" / "scoring_main.py"
# Целевая граница Compose (AGENTS.md, раздел 5); свой пакет разрешён всем.
TARGET_ALLOWED = {
    "core": {"core"},
    "contract": {"contract"},
    "utility_rating": {"contract", "utility_rating"},
    "sources": {"contract", "core", "sources"},
    "dossier": {"contract", "core", "dossier", "sources"},
    "api": {"api", "contract", "core", "dossier"},
}
SCORING_ENTRYPOINT_ALLOWED = {"contract", "core", "sources", "utility_rating"}


def production_modules() -> list[tuple[str, Path]]:
    modules = [
        (zone, path)
        for zone in TARGET_ALLOWED
        for path in sorted((ROOT / zone).rglob("*.py"))
    ]
    assert modules
    return modules


def project_imports(tree: ast.Module) -> tuple[set[str], set[str]]:
    """Модули проекта файла и те же имена с импортируемыми атрибутами.

    Второе множество ловит форму from api import scoring_main.
    """
    modules: set[str] = set()
    targets: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules.add(node.module)
            targets.update(f"{node.module}.{alias.name}" for alias in node.names)
    modules = {name for name in modules if name.split(".")[0] in PROJECT_ROOTS}
    return modules, modules | targets


@pytest.mark.parametrize(
    ("zone", "path"),
    production_modules(),
    ids=lambda value: value.relative_to(ROOT).as_posix()
    if isinstance(value, Path)
    else value,
)
def test_production_imports_follow_compose_target_boundary(
    zone: str, path: Path
) -> None:
    """Ловит обратные и поперечные зависимости зон и формулу вне scoring."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    relative = [
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.level
    ]
    assert relative == [], path
    modules, targets = project_imports(tree)
    if path == SCORING_ENTRYPOINT:
        allowed = SCORING_ENTRYPOINT_ALLOWED
    else:
        allowed = TARGET_ALLOWED[zone]
    forbidden = sorted(name for name in modules if name.split(".")[0] not in allowed)
    if zone == "api" and path != SCORING_ENTRYPOINT:
        forbidden += sorted(
            name
            for name in targets
            if name == "api.scoring_main" or name.startswith("api.scoring_main.")
        )
    assert forbidden == [], (
        f"{path.relative_to(ROOT).as_posix()} ({zone}) imports {forbidden}"
    )
