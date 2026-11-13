"""Загрузчик seed-данных. Пока каркас: читает JSON из `data/seed` и валидирует.

Реальную схему БД добавит задача про модель данных, тогда `run()` начнёт писать в базу.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

SEED_DIR = Path(__file__).resolve().parents[3] / "data" / "seed"


def load(name: str) -> list[dict[str, object]]:
    path = SEED_DIR / f"{name}.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise SystemExit(f"{path.name}: ожидался JSON-массив")
    return data


def run() -> dict[str, int]:
    counts: dict[str, int] = {}
    for path in sorted(SEED_DIR.glob("*.json")):
        counts[path.stem] = len(load(path.stem))
    return counts


def main() -> int:
    counts = run()
    if not counts:
        print(f"seed: каталог {SEED_DIR} пуст, загружать нечего")
        return 0
    for name, count in counts.items():
        print(f"seed: {name} — {count} записей")
    return 0


if __name__ == "__main__":
    sys.exit(main())
