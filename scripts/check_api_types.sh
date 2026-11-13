#!/usr/bin/env bash
# Проверяет, что frontend/src/types/api.ts совпадает с OpenAPI текущего кода.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMMITTED="$ROOT/frontend/src/types/api.ts"

tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT

"$ROOT/scripts/gen_api_types.sh" "$tmp" >/dev/null

if ! diff -u --label "закоммичено" --label "из OpenAPI" "$COMMITTED" "$tmp" >/dev/null; then
  echo "frontend/src/types/api.ts устарел. Запусти ./scripts/gen_api_types.sh и закоммить результат." >&2
  diff -u --label "закоммичено" --label "из OpenAPI" "$COMMITTED" "$tmp" >&2 || true
  exit 1
fi

echo "типы актуальны"
