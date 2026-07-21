from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from domains.ingredient.schemas import GetIngredientResponse


def _validate_group_name(v: str) -> str:
    name = v.strip()
    if not name:
        raise ValueError("그룹 이름은 비어 있을 수 없습니다.")
    if len(name) > 40:
        raise ValueError("그룹 이름은 40자 이하여야 합니다.")
    return name


class CreateGroupRequest(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        return _validate_group_name(v)


class UpdateGroupRequest(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        return _validate_group_name(v)


class GroupMemberResponse(BaseModel):
    user_id: UUID
    nickname: str
    role: str


class GroupResponse(BaseModel):
    id: UUID
    name: str
    invite_code: str
    owner_id: UUID
    members: list[GroupMemberResponse]
    created_at: datetime


class InviteByNicknameRequest(BaseModel):
    nickname: str


class JoinByCodeRequest(BaseModel):
    invite_code: str


class GroupInviteResponse(BaseModel):
    id: UUID
    group_id: UUID
    group_name: str
    inviter_nickname: str
    status: str
    created_at: datetime


class MergeRequest(BaseModel):
    mode: Literal["copy", "move"]
    ingredients: list[int] = Field(default_factory=list)
    shopping_items: list[int] = Field(default_factory=list)


class MergeResponse(BaseModel):
    created_ingredients: list[GetIngredientResponse] = Field(default_factory=list)
    created_shopping_items: list[Any] = Field(default_factory=list)
    skipped_ingredient_ids: list[int] = Field(default_factory=list)
    skipped_shopping_item_ids: list[int] = Field(default_factory=list)
    deleted_ingredient_ids: list[int] = Field(default_factory=list)
    deleted_shopping_item_ids: list[int] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)
