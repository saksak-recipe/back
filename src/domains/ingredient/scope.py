from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import StrEnum

from core.exception.codes import ErrorCode
from core.exception.exceptions import NotFoundException
from domains.group.repository import GroupRepository
from domains.ingredient.model import Ingredient
from domains.ingredient.repository import IngredientRepository
from domains.user.model import User


class RecipeScope(StrEnum):
    personal = "personal"
    group = "group"


@dataclass(frozen=True)
class ScopedIngredients:
    ingredients: list[Ingredient]
    scope: RecipeScope
    cache_owner_id: uuid.UUID


class IngredientScopeLoader:
    def __init__(
        self,
        user: User,
        ingredient_repo: IngredientRepository,
        group_repo: GroupRepository,
    ) -> None:
        self.user = user
        self.ingredient_repo = ingredient_repo
        self.group_repo = group_repo

    async def load(self, scope: RecipeScope) -> ScopedIngredients:
        if scope is RecipeScope.personal:
            ingredients = await self.ingredient_repo.get_ingredients(self.user.id)
            return ScopedIngredients(
                ingredients=ingredients,
                scope=RecipeScope.personal,
                cache_owner_id=self.user.id,
            )

        membership = await self.group_repo.get_membership(self.user.id)
        if membership is None:
            raise NotFoundException(
                code=ErrorCode.GROUP_NOT_FOUND,
                detail="가입된 그룹을 찾을 수 없습니다.",
            )

        ingredients = await self.ingredient_repo.list_by_group(membership.group_id)
        return ScopedIngredients(
            ingredients=ingredients,
            scope=RecipeScope.group,
            cache_owner_id=membership.group_id,
        )
