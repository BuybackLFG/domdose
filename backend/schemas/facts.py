"""Факт о доме, ссылка на источник и дисклеймер."""

from datetime import date as Date
from enum import StrEnum

from pydantic import BaseModel, Field

from schemas.common import Confidence, SourceUrl


class FactType(StrEnum):
    """Категория факта. Совпадает по смыслу с компонентами индекса."""

    building = "building"
    communications = "communications"
    nature = "nature"
    transport = "transport"
    safety = "safety"
    legal = "legal"


class Fact(BaseModel):
    """Утверждение о доме, которое можно проверить по ссылке.

    У каждого факта обязателен `source_url` — это требование эпика B, без него
    досье превращается в непроверяемые утверждения.
    """

    id: str = Field(min_length=1, max_length=200)
    type: FactType
    label: str = Field(min_length=1, max_length=200, description="Короткая подпись факта")
    value: str = Field(min_length=1, max_length=500, description="Значение как текст")
    source_url: SourceUrl
    retrieved_at: Date
    confidence: Confidence = 1.0


class Source(BaseModel):
    """Источник в подвале досье: реестр, на котором построены факты."""

    name: str = Field(min_length=1, max_length=200)
    url: SourceUrl
    retrieved_at: Date


DISCLAIMER = "аналитика по открытым данным, не гарантия"
"""Дисклеймер дословно. Менять только вместе с тестом `test_schemas.py`."""
