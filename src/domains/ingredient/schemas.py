from datetime import date

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AddIngredientRequest(BaseModel):
    # 유통기한 안넣을 시 Default -> Today
    purchase_date: date = Field(default_factory=date.today)
    expiration_date: date | None = None
    ingredients: list[str]

    @field_validator("purchase_date", mode="before")
    @classmethod
    def set_today_if_null(cls, v):
        if v is None:
            return date.today()
        return v


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

    model_config = ConfigDict(from_attributes=True)


class GetIngredientResponse(BaseModel):
    id: int
    ingredient_name: str
    purchase_date: date
    expiration_date: date | None = None

    model_config = ConfigDict(from_attributes=True)
