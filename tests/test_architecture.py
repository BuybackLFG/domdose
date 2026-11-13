import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def imports(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            yield node.module


def contract_violations(tree):
    bad = []
    forbidden = {
        "core",
        "fastapi",
        "os",
        "dotenv",
        "pydantic_settings",
        "io",
        "pathlib",
        "socket",
        "requests",
        "httpx",
    }
    # pathlib/resources are permitted for reading the packaged schema, but not datasets.
    forbidden.remove("pathlib")
    for module in imports(tree):
        if module.split(".")[0] in forbidden:
            bad.append(module)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            call = node.func
            if isinstance(call, ast.Name) and call.id in {"open", "eval", "exec", "__import__"}:
                bad.append(call.id)
            if isinstance(call, ast.Attribute) and call.attr in {
                "getenv",
                "environ",
                "write_text",
                "write_bytes",
                "mkdir",
                "unlink",
            }:
                bad.append(call.attr)
        if isinstance(node, ast.Attribute) and node.attr == "environ":
            bad.append("environ")
    return bad


@pytest.mark.parametrize("package", ["core", "contract"])
def test_layer_import_boundaries(package):
    files = sorted((ROOT / package).glob("**/*.py"))
    assert files, f"Required package {package} is absent"
    for file in files:
        tree = ast.parse(file.read_text(encoding="utf-8-sig"), filename=str(file))
        if package == "contract":
            assert not contract_violations(tree), (file, contract_violations(tree))
        else:
            assert not any(
                name.split(".")[0] in {"contract", "fastapi"} for name in imports(tree)
            ), file


def test_logging_setup_never_at_module_level():
    file = ROOT / "core" / "logging.py"
    assert file.exists()
    tree = ast.parse(file.read_text(encoding="utf-8-sig"))
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        for item in ast.walk(node):
            if isinstance(item, ast.Call):
                name = (
                    item.func.id
                    if isinstance(item.func, ast.Name)
                    else getattr(item.func, "attr", "")
                )
                assert name not in {
                    "setup_logging",
                    "basicConfig",
                    "FileHandler",
                    "StreamHandler",
                    "Settings",
                    "get_settings",
                }
    for item in ast.walk(tree):
        if isinstance(item, ast.Call) and isinstance(item.func, ast.Attribute):
            assert item.func.attr not in {"basicConfig", "setLogRecordFactory"}


@pytest.mark.parametrize(
    "source",
    [
        "from core.config import Settings",
        "import fastapi",
        "import os; x=os.environ.get('X')",
        "from os import getenv; x=getenv('X')",
        "x=open('dataset.json')",
        "import requests",
    ],
)
def test_architecture_probe_catches_test_only_mutants(source):
    assert contract_violations(ast.parse(source))
