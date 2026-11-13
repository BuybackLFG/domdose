#!/usr/bin/env bash
# Проверяет, что frontend/src/types/api.ts совпадает с локальным OpenAPI.
# Используется в scripts/check.sh и в CI (после активации).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMMITTED="$ROOT/frontend/src/types/api.ts"

tmp="$(mktemp)"
backup="$(mktemp)"
trap 'rm -f "$tmp" "$backup"' EXIT

cp "$COMMITTED" "$backup"
"$ROOT/scripts/gen_api_types.sh" >/dev/null
cp "$COMMITTED" "$tmp"
cp "$backup" "$COMMITTED"

if ! diff -u --label "закоммичено" --label "из OpenAPI" "$tmp" "$COMMITTED" >/dev/null; then
  echo "frontend/src/types/api.ts устарел. Запусти ./scripts/gen_api_types.sh и закоммить результат." >&2
  diff -u --label "закоммичено" --label "из OpenAPI" "$tmp" "$COMMITTED" >&2 || true
  exit 1
fi

echo "типы актуальны"
