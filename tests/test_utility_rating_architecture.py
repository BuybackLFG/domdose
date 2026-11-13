import ast
from pathlib import Path

import pytest

PACKAGE = Path(__file__).parent.parent / "backend" / "utility_rating"
FORBIDDEN_IMPORTS = {
    "fastapi",
    "httpx",
    "pathlib",
    "psycopg",
    "random",
    "requests",
    "socket",
    "sqlalchemy",
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
