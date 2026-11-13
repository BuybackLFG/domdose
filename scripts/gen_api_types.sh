#!/usr/bin/env bash
# Генерирует типы из OpenAPI текущего исходного кода, без запущенного сервера.
# Необязательный аргумент — путь к выходному файлу.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${1:-$ROOT/frontend/src/types/api.ts}"
UV="${UV_BIN:-uv}"

mkdir -p "$(dirname "$OUT")"
schema="$(mktemp)"
generated=""
trap 'rm -f "$schema" ${generated:+"$generated"}' EXIT
generated="$(mktemp "${OUT}.tmp.XXXXXX")"

(cd "$ROOT/backend" && "$UV" run --locked python -c \
  'import json; from app.main import app; print(json.dumps(app.openapi(), ensure_ascii=False))') >"$schema"

{
  echo "// Сгенерировано из OpenAPI backend — не править руками."
  echo "// Обновление: ./scripts/gen_api_types.sh"
  echo
  (cd "$ROOT/frontend" && npx --no-install openapi-typescript "$schema")
} >"$generated"
chmod 644 "$generated"
mv -f "$generated" "$OUT"

echo "готово: ${OUT#"$ROOT"/}"
