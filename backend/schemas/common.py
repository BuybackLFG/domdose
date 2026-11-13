"""Общие примитивы контракта: ссылки на источники и числовые ограничения.

Всё, что здесь объявлено, попадает в OpenAPI и в `frontend/src/types/api.ts`.
Меняет только техлид (см. `docs/api-contract.md`).
"""

from typing import Annotated

from pydantic import Field, StringConstraints

# Ссылка на открытый источник. Обычная строка с проверкой схемы, а не `HttpUrl`:
# `HttpUrl` нормализует значение (добавляет слэш), а seed-данные должны остаться
# байт-в-байт такими, какими пришли из источника, иначе ломается дедуп.
SourceUrl = Annotated[
    str,
    StringConstraints(pattern=r"^https?://\S+$", max_length=2048, strip_whitespace=True),
    Field(description="Ссылка на открытый источник (http/https)"),
]

# Оценка компоненты индекса: 0–100, больше — лучше.
Score = Annotated[float, Field(ge=0, le=100, description="Оценка 0–100, больше — лучше")]

# Вес компоненты в итоговом индексе: доля, сумма по пяти компонентам = 1.0.
Weight = Annotated[float, Field(gt=0, le=1, description="Доля в итоговом индексе")]

# Насколько данные полны: 0 — пусто, 1 — покрытие полное.
Factor = Annotated[float, Field(ge=0, le=1, description="Множитель покрытия источников, 0–1")]

# Серьёзность события: 1 — мелочь, 2 — заметно, 3 — критично.
Severity = Annotated[int, Field(ge=1, le=3, description="Серьёзность: 1 низкая, 3 критичная")]

# Уверенность извлечения: 1.0 у официальных источников.
Confidence = Annotated[float, Field(ge=0, le=1, description="Уверенность в событии, 0–1")]
