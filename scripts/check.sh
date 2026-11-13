#!/usr/bin/env bash
# Единственная точка входа для локальных проверок.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

UV="${UV_BIN:-uv}"

step() { printf '\n== %s ==\n' "$1"; }

step "backend: uv sync"
(cd backend && "$UV" sync --locked --quiet)

step "backend: ruff format --check"
(cd backend && "$UV" run ruff format --check .)

step "backend: ruff check"
(cd backend && "$UV" run ruff check .)

step "backend: pyright"
(cd backend && "$UV" run pyright)

step "backend: pytest"
(cd backend && "$UV" run pytest -q)

step "frontend: build"
(cd frontend && npm run build --silent)

step "contract: типы из OpenAPI актуальны"
./scripts/check_api_types.sh

printf '\nВсе проверки зелёные.\n'
