from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SaveRecipeRequest(BaseModel):
    source: Literal["mangae"]
    source_id: str = Field(min_length=1)


class SavedRecipeListItem(BaseModel):
    id: UUID
    source: str
    source_id: str
    recipe_name: str
    recipe_difficulty: str | None = None
    time: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SavedRecipeDetailResponse(BaseModel):
    id: UUID
    source: str
    source_id: str
    recipe_name: str
    recipe_difficulty: str | None = None
    time: str | None = None
    snapshot: dict[str, Any]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SavedRecipeStatusResponse(BaseModel):
    saved: bool
    id: UUID | None = None
