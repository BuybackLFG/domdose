"""Дом: паспорт из открытых данных и краткая карточка для поиска."""

from datetime import date as Date
from datetime import datetime

from pydantic import BaseModel, Field

from schemas.common import Score, SourceUrl


class House(BaseModel):
    """Паспорт дома. Поля 1:1 совпадают с `data/seed/houses.json` (задача D2).

    Неизвестное значение — `null`, а не 0 и не догадка: индекс и UI обязаны
    отличать «нет данных» от «данные плохие».
    """

    id: str = Field(min_length=1, max_length=100, description="Стабильный slug, не меняется")
    address: str = Field(min_length=1, max_length=300)
    district: str = Field(min_length=1, max_length=100)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    year: int | None = Field(default=None, ge=1800, le=2100, description="Год постройки")
    floors: int | None = Field(default=None, ge=1, le=100)
    material: str | None = Field(default=None, max_length=100)
    wear_pct: int | None = Field(default=None, ge=0, le=100, description="Износ по ГИС ЖКХ, %")
    uk: str | None = Field(default=None, max_length=200, description="Управляющая компания")
    avariy: bool = Field(description="Аварийный дом по реестру")
    caprepair: bool = Field(description="В плане капремонта")
    developer: str | None = Field(default=None, max_length=200)
    source_urls: list[SourceUrl] = Field(min_length=1, description="Хотя бы один источник")
    retrieved_at: datetime = Field(description="Когда данные получены, ISO 8601")


class ComponentBrief(BaseModel):
    """Короткая проекция компоненты индекса для списка в поиске."""

    key: str = Field(description="Машинный ключ компоненты")
    label: str = Field(description="Название для человека")
    score: Score


class HouseSummary(BaseModel):
    """Элемент списка `GET /api/houses?q=` (задача B1).

    `index` и `components` приходят `null`/пустыми, пока индекс не посчитан:
    поиск не должен падать из-за отсутствия скоринга.
    """

    id: str
    address: str
    district: str
    index: Score | None = Field(default=None, description="Итоговый индекс, если посчитан")
    components: list[ComponentBrief] = Field(default_factory=list)


class HouseList(BaseModel):
    """Ответ поиска. Обёртка вместо голого массива: место для пагинации и счётчика."""

    items: list[HouseSummary]
    total: int = Field(ge=0)
    query: str = Field(description="Что реально искали, после нормализации")
    retrieved_at: Date | None = Field(default=None, description="Дата заморозки seed")
