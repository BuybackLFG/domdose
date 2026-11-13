"""Состав Python-образов api и scoring равен графу импортов их точки входа.

Замыкание абсолютных импортов проектных пакетов от модуля CMD сравнивается
с проектными .py, которые COPY-инструкции Dockerfile кладут в образ с учётом
.dockerignore. Лишний модуль в образе — второй путь к зоне, которой сервис
не владеет; недостающий — отказ при запуске контейнера.
"""

import ast
import json
import os
import posixpath
from pathlib import Path

import pytest

from test_compose import (
    DOCKERFILES,
    DOCKERIGNORE_PATH,
    ROOT,
    dockerfile_instructions,
    dockerignore_excludes,
    dockerignore_pattern,
    read_required,
)

ENTRYPOINTS = {"api": "api.main", "scoring": "api.scoring_main"}


def project_packages():
    """Корневые пакеты репозитория: каталоги с __init__.py."""
    return frozenset(
        path.parent.name
        for path in ROOT.glob("*/__init__.py")
        if path.parent.name not in {"tests", "frontend"}
    )


def module_file(module):
    """Файл модуля относительно корня или None, если такого модуля нет."""
    base = Path(*module.split("."))
    for candidate in (base.with_suffix(".py"), base / "__init__.py"):
        if (ROOT / candidate).is_file():
            return candidate.as_posix()
    return None


def imported_modules(path, module, packages):
    """Проектные модули, которые импортирует файл, включая подмодули from."""
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"), filename=path)
    package = module if path.endswith("__init__.py") else module.rpartition(".")[0]
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                parts = package.split(".")
                anchor = ".".join(parts[: len(parts) - node.level + 1])
                base = f"{anchor}.{node.module}" if node.module else anchor
            else:
                base = node.module or ""
            found.add(base)
            found.update(f"{base}.{alias.name}" for alias in node.names)
    return {name for name in found if name.split(".")[0] in packages}


def import_closure(entrypoint):
    """Файлы замыкания: модули и __init__.py всех родительских пакетов."""
    packages = project_packages()
    pending, seen, files = [entrypoint], set(), set()
    while pending:
        module = pending.pop()
        if module in seen:
            continue
        seen.add(module)
        parts = module.split(".")
        pending.extend(".".join(parts[:depth]) for depth in range(1, len(parts)))
        path = module_file(module)
        if path is None:
            continue
        files.add(path)
        pending.extend(imported_modules(path, module, packages))
    return files


GLOB_CHARS = "*?["


def walk_files(directory, ignore):
    """Файлы каталога контекста; исключённые каталоги без исключений-! пропускаются."""
    negations = [
        line.strip()[1:].strip().lstrip("/")
        for line in ignore.splitlines()
        if line.strip().startswith("!")
    ]
    files = []
    for current, dirnames, filenames in os.walk(ROOT / directory):
        base = Path(current).relative_to(ROOT).as_posix()
        prefix = "" if base == "." else base + "/"
        dirnames[:] = [
            name
            for name in dirnames
            if not dockerignore_excludes(ignore, prefix + name)
            or any(
                pattern.startswith(prefix + name + "/")
                or any(char in pattern for char in GLOB_CHARS)
                for pattern in negations
            )
        ]
        files.extend(prefix + name for name in filenames)
    return files


def context_files(pattern, ignore):
    """Файлы контекста, которые может выбрать источник COPY, после .dockerignore."""
    head = []
    for part in pattern.split("/"):
        if any(char in part for char in GLOB_CHARS):
            break
        head.append(part)
    base = "/".join(head) or "."
    path = ROOT / base
    if path.is_file():
        candidates = [base]
    elif path.is_dir():
        candidates = walk_files(base, ignore)
    else:
        candidates = []
    return [item for item in candidates if not dockerignore_excludes(ignore, item)]


def copy_arguments(arguments):
    """Источники и назначение COPY без флагов; JSON-форма поддерживается."""
    if arguments.lstrip().startswith("["):
        tokens = json.loads(arguments)
    else:
        tokens = arguments.split()
    tokens = [token for token in tokens if not token.startswith("--")]
    return tokens[:-1], tokens[-1]


def copied_files(dockerfile):
    """Пути в образе относительно WORKDIR CMD -> исходный путь контекста."""
    instructions = dockerfile_instructions(read_required(dockerfile))
    ignore = read_required(DOCKERIGNORE_PATH)
    workdir, placed = "/", {}
    for keyword, arguments in instructions:
        if keyword == "FROM":
            workdir, placed = "/", {}
        elif keyword == "WORKDIR":
            workdir = posixpath.normpath(posixpath.join(workdir, arguments.strip()))
        elif keyword in ("COPY", "ADD"):
            assert "--from" not in arguments, f"multi-stage COPY: {arguments}"
            sources, destination = copy_arguments(arguments)
            target = posixpath.join(workdir, destination)
            for source in sources:
                pattern = posixpath.normpath(source).lstrip("/")
                for relative in sorted(context_files(pattern, ignore)):
                    image_path = placed_path(relative, pattern, target, sources)
                    if image_path is not None:
                        placed[posixpath.normpath(image_path)] = relative
    return {
        posixpath.relpath(path, workdir) if path.startswith(workdir + "/") else path: src
        for path, src in placed.items()
    }


def placed_path(relative, pattern, target, sources):
    """Путь файла контекста в образе для источника COPY или None."""
    if pattern == ".":
        return posixpath.join(target, relative)
    directory = pattern.rstrip("/")
    has_glob = any(char in pattern for char in GLOB_CHARS)
    if relative.startswith(directory + "/") and not has_glob:
        return posixpath.join(target, relative[len(directory) + 1 :])
    if glob_matches(pattern, relative):
        if target.endswith("/") or len(sources) > 1:
            return posixpath.join(target, posixpath.basename(relative))
        return target
    for parent in ancestors(relative):
        if has_glob and glob_matches(pattern, parent):
            return posixpath.join(target, relative[len(parent) + 1 :])
    return None


def glob_matches(pattern, relative):
    """Шаблон источника COPY: * и ? не пересекают /, как filepath.Match."""
    return dockerignore_pattern(pattern).fullmatch(relative) is not None


def ancestors(relative):
    parts = relative.split("/")
    return ["/".join(parts[:depth]) for depth in range(1, len(parts))]


def image_python_modules(service):
    return {
        path for path in copied_files(DOCKERFILES[service]) if path.endswith(".py")
    }


@pytest.mark.parametrize("service", list(ENTRYPOINTS))
def test_cmd_runs_the_declared_entrypoint(service):
    instructions = dockerfile_instructions(read_required(DOCKERFILES[service]))
    commands = [arguments for keyword, arguments in instructions if keyword == "CMD"]

    assert commands, f"{service}: no CMD"
    assert f"{ENTRYPOINTS[service]}:app" in commands[-1]


@pytest.mark.parametrize("service", list(ENTRYPOINTS))
def test_image_contains_every_module_of_import_closure(service):
    closure = import_closure(ENTRYPOINTS[service])
    in_image = image_python_modules(service)

    missing = sorted(closure - in_image)
    assert module_file(ENTRYPOINTS[service]) in closure
    assert missing == [], f"{service}: modules missing in image: {missing}"


@pytest.mark.parametrize("service", list(ENTRYPOINTS))
def test_image_contains_no_python_outside_import_closure(service):
    closure = import_closure(ENTRYPOINTS[service])
    in_image = image_python_modules(service)

    extra = sorted(in_image - closure)
    assert extra == [], f"{service}: modules outside closure: {extra}"


@pytest.mark.parametrize(
    ("service", "forbidden"),
    [
        pytest.param("api", "api/scoring_main.py", id="api-without-scoring-door"),
        pytest.param("api", "utility_rating/scoring.py", id="api-without-formula"),
        pytest.param("scoring", "api/main.py", id="scoring-without-public-app"),
        pytest.param("scoring", "api/routes.py", id="scoring-without-routes"),
        pytest.param(
            "scoring", "sources/legacy_dataset.py", id="scoring-without-legacy"
        ),
        pytest.param(
            "scoring", "sources/utility_rating_json.py", id="scoring-without-json"
        ),
        pytest.param("scoring", "dossier/service.py", id="scoring-without-dossier"),
    ],
)
def test_known_foreign_modules_stay_out_of_image(service, forbidden):
    assert forbidden not in import_closure(ENTRYPOINTS[service])
    assert forbidden not in image_python_modules(service)


def test_closure_follows_package_init_and_from_submodules():
    closure = import_closure("api.scoring_main")

    # from utility_rating.dataset import ... исполняет utility_rating/__init__.py,
    # а он тянет utility_rating.scoring и utility_rating.metrics.
    assert {
        "api/__init__.py",
        "utility_rating/__init__.py",
        "utility_rating/dataset.py",
        "utility_rating/scoring.py",
        "utility_rating/metrics.py",
        "contract/__init__.py",
    } <= closure


@pytest.mark.parametrize(
    ("instruction", "files", "expected"),
    [
        (
            "COPY api ./api",
            {"api/__init__.py", "api/main.py"},
            {"api/__init__.py", "api/main.py"},
        ),
        (
            "COPY api/__init__.py api/main.py ./api/",
            {"api/__init__.py", "api/main.py", "api/scoring_main.py"},
            {"api/__init__.py", "api/main.py"},
        ),
        (
            "COPY --chown=app:app core/*.py ./core/",
            {"core/__init__.py", "core/logging.py", "core/sub/x.py"},
            {"core/__init__.py", "core/logging.py"},
        ),
        (
            "COPY api/main.py ./api/entry.py",
            {"api/main.py"},
            {"api/entry.py"},
        ),
        (
            '["api/main.py", "./api/"]',
            {"api/main.py"},
            {"api/main.py"},
        ),
    ],
)
def test_copy_evaluator_places_files_like_docker(instruction, files, expected):
    if instruction.startswith("["):
        sources, destination = copy_arguments(instruction)
    else:
        sources, destination = copy_arguments(instruction.partition(" ")[2])
    target = posixpath.join("/app", destination)
    placed = set()
    for source in sources:
        pattern = posixpath.normpath(source).lstrip("/")
        for relative in files:
            image_path = placed_path(relative, pattern, target, sources)
            if image_path is not None:
                placed.add(posixpath.relpath(posixpath.normpath(image_path), "/app"))

    assert placed == expected
