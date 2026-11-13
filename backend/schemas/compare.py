"""Сравнение двух домов — ответ `GET /api/compare?ids=a,b` (задача F5)."""

from pydantic import BaseModel, Field, model_validator

from schemas.dossier import Dossier


class CompareResponse(BaseModel):
    """Два дома бок о бок и честный вывод, где каждый слабее.

    Контракт запрещает «победителя без объяснения»: `summary` обязателен, а
    `weaker_house_id` указывает на дом с более слабым местом, а не на проигравшего.
    """

    houses: list[Dossier] = Field(min_length=2, max_length=2)
    weaker_house_id: str = Field(
        description="id дома, у которого есть заметное слабое место в сравнении"
    )
    summary: str = Field(
        min_length=1,
        max_length=2000,
        description="Человеческое объяснение сравнения: что лучше, что хуже и почему",
    )

    @model_validator(mode="after")
    def _weaker_house_is_present_and_distinct(self) -> "CompareResponse":
        ids = [dossier.house.id for dossier in self.houses]
        if len(set(ids)) != 2:
            raise ValueError("сравнивать нужно два разных дома")
        if self.weaker_house_id not in ids:
            raise ValueError("weaker_house_id должен указывать на один из сравниваемых домов")
        return self
