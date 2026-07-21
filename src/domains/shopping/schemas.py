from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AddShoppingItemsRequest(BaseModel):
    names: list[str] = Field(min_length=1)

    @field_validator("names")
    @classmethod
    def validate_names(cls, names: list[str]) -> list[str]:
        cleaned: list[str] = []
        for raw in names:
            name = raw.strip()
            if not name:
                raise ValueError("식재료 이름은 비어 있을 수 없습니다.")
            if len(name) > 45:
                raise ValueError("식재료 이름은 45자 이하여야 합니다.")
            cleaned.append(name)
        return cleaned


class UpdateShoppingItemRequest(BaseModel):
    is_checked: bool


class ShoppingItemResponse(BaseModel):
    id: int
    name: str
    is_checked: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
