#!/usr/bin/env bash
# Генерирует frontend/src/types/api.ts из локального /openapi.json.
# Backend должен слушать 127.0.0.1:8000. Если он не поднят — скрипт поднимает его сам.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$ROOT/frontend/src/types/api.ts"
URL="${API_URL:-http://127.0.0.1:8000}"
UV="${UV_BIN:-uv}"

pid=""
cleanup() {
  if [[ -n "$pid" ]]; then kill "$pid" 2>/dev/null || true; fi
}
trap cleanup EXIT

if ! curl -sf --max-time 2 "$URL/health" >/dev/null 2>&1; then
  echo "backend не отвечает на $URL — поднимаю временный"
  (cd "$ROOT/backend" && "$UV" run uvicorn app.main:app --port 8000 --log-level warning) &
  pid=$!
  for _ in $(seq 1 50); do
    curl -sf --max-time 1 "$URL/health" >/dev/null 2>&1 && break
    sleep 0.2
  done
  curl -sf --max-time 2 "$URL/health" >/dev/null || {
    echo "не удалось дождаться backend на $URL" >&2
    exit 1
  }
fi

mkdir -p "$(dirname "$OUT")"
{
  echo "// Сгенерировано из $URL/openapi.json — не править руками."
  echo "// Обновление: ./scripts/gen_api_types.sh"
  echo
  (cd "$ROOT/frontend" && npx --no-install openapi-typescript "$URL/openapi.json")
} >"$OUT"

echo "готово: ${OUT#"$ROOT"/}"
