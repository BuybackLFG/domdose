"""Регрессии для генерации и проверки типов API без запущенного сервера."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def scripts_repo(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    for name in ("gen_api_types.sh", "check_api_types.sh"):
        shutil.copy2(ROOT / "scripts" / name, scripts / name)
    (tmp_path / "backend").mkdir()
    (tmp_path / "backend" / "schema.json").write_text("current schema\n")
    (tmp_path / "frontend" / "src" / "types").mkdir(parents=True)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    commands = {
        "uv": "#!/bin/sh\ncat schema.json\n",
        "npx": '#!/bin/sh\nif [ "${FAIL_NPX:-}" = 1 ]; then exit 1; fi\ncat "$3"\n',
        "curl": (
            '#!/bin/sh\n[ "${CURL_OK:-}" = 1 ] && exit 0\n'
            'echo "unexpected server request" >&2\nexit 1\n'
        ),
    }
    for name, contents in commands.items():
        path = bin_dir / name
        path.write_text(contents)
        path.chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "UV_BIN": str(bin_dir / "uv"),
    }
    return tmp_path, env


def run_script(repo: Path, env: dict[str, str], script: str) -> subprocess.CompletedProcess[str]:
    if os.name == "nt":
        # Windows cannot execute shell scripts directly; convert paths inside Git Bash.
        return subprocess.run(
            [
                "bash",
                "-c",
                'bin=$(cygpath -u "$1"); export PATH="$bin:$PATH" UV_BIN="$bin/uv"; '
                'exec bash "$(cygpath -u "$2")"',
                "test-script",
                str(repo / "bin"),
                str(repo / "scripts" / script),
            ],
            cwd=repo,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    return subprocess.run(
        [str(repo / "scripts" / script)], cwd=repo, env=env, capture_output=True, text=True
    )


@pytest.mark.parametrize("script", ["check_api_types.sh", "gen_api_types.sh"])
def test_generation_failure_preserves_existing_types(
    scripts_repo: tuple[Path, dict[str, str]], script: str
) -> None:
    repo, env = scripts_repo
    types = repo / "frontend" / "src" / "types" / "api.ts"
    types.write_text("existing content\n")

    result = run_script(repo, {**env, "FAIL_NPX": "1", "CURL_OK": "1"}, script)

    assert result.returncode != 0
    assert types.read_text() == "existing content\n"


def test_check_compares_current_schema_without_a_server(
    scripts_repo: tuple[Path, dict[str, str]],
) -> None:
    repo, env = scripts_repo
    types = repo / "frontend" / "src" / "types" / "api.ts"
    generated = run_script(repo, env, "gen_api_types.sh")
    assert generated.returncode == 0, generated.stderr
    assert "current schema" in types.read_text()
    original = types.read_bytes()

    assert run_script(repo, env, "check_api_types.sh").returncode == 0
    (repo / "backend" / "schema.json").write_text("changed schema\n")
    result = run_script(repo, env, "check_api_types.sh")
    assert result.returncode != 0
    assert "устарел" in result.stderr
    assert types.read_bytes() == original
