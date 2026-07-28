from datetime import date
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

IngredientStatus = Literal["expired", "soon", "ok", "unknown"]


class AddIngredientRequest(BaseModel):
    # 유통기한 안넣을 시 Default -> Today
    purchase_date: date = Field(default_factory=date.today)
    expiration_date: date | None = None
    ingredients: list[str] = Field(min_length=1)

    @field_validator("purchase_date", mode="before")
    @classmethod
    def set_today_if_null(cls, v):
        if v is None:
            return date.today()
        return v

    @field_validator("ingredients")
    @classmethod
    def validate_ingredients(cls, names: list[str]) -> list[str]:
        cleaned: list[str] = []
        for raw in names:
            name = raw.strip()
            if not name:
                raise ValueError("식재료 이름은 비어 있을 수 없습니다.")
            if len(name) > 45:
                raise ValueError("식재료 이름은 45자 이하여야 합니다.")
            cleaned.append(name)
        return cleaned

    @model_validator(mode="after")
    def clear_shared_expiration_for_batch(self) -> Self:
        # 다건 추가는 재료별 유통기한을 받을 수 없어 공유 값을 무시한다.
        if len(self.ingredients) > 1 and self.expiration_date is not None:
            self.expiration_date = None
        return self


class UpdateIngredientRequest(BaseModel):
    ingredient_name: str | None = None
    purchase_date: date | None = None
    expiration_date: date | None = None

    @field_validator("ingredient_name")
    @classmethod
    def validate_ingredient_name(cls, v: str | None) -> str | None:
        if v is None:
            return v
        name = v.strip()
        if not name:
            raise ValueError("식재료 이름은 비어 있을 수 없습니다.")
        if len(name) > 45:
            raise ValueError("식재료 이름은 45자 이하여야 합니다.")
        return name


class AddIngredientResponse(BaseModel):
    id: int
    ingredient_name: str
    purchase_date: date
    expiration_date: date | None = None
    status: IngredientStatus

    model_config = ConfigDict(from_attributes=True)


class GetIngredientResponse(BaseModel):
    id: int
    ingredient_name: str
    purchase_date: date
    expiration_date: date | None = None
    status: IngredientStatus

    model_config = ConfigDict(from_attributes=True)
