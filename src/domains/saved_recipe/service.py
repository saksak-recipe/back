from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from core.exception.codes import ErrorCode
from core.exception.exceptions import (
    BadRequestException,
    ConflictException,
    NotFoundException,
)
from domains.saved_recipe.model import SavedRecipe
from domains.saved_recipe.repository import SavedRecipeRepository
from domains.saved_recipe.schemas import (
    SaveRecipeRequest,
    SavedRecipeDetailResponse,
    SavedRecipeListItem,
    SavedRecipeStatusResponse,
)
from domains.user.model import User

if TYPE_CHECKING:
    from domains.recipe_detail.service import RecipeDetailService


def parse_mangae_source_id(source_id: str) -> tuple[str, str]:
    if "|" not in source_id:
        raise BadRequestException(
            detail="만개 레시피 source_id는 'board_name|author_name' 형식이어야 합니다."
        )
    board_name, author_name = source_id.split("|", 1)
    board_name = board_name.strip()
    author_name = author_name.strip()
    if not board_name or not author_name:
        raise BadRequestException(
            detail="만개 레시피 source_id의 board_name과 author_name은 비어 있을 수 없습니다."
        )
    return board_name, author_name


class SavedRecipeService:
    def __init__(
        self,
        user: User,
        repo: SavedRecipeRepository,
        recipe_detail_service: RecipeDetailService,
    ) -> None:
        self.user = user
        self.repo = repo
        self.recipe_detail_service = recipe_detail_service

    async def save(self, request: SaveRecipeRequest) -> SavedRecipeDetailResponse:
        parse_mangae_source_id(request.source_id)

        existing = await self.repo.find_by_source(
            self.user.id, request.source, request.source_id
        )
        if existing is not None:
            raise ConflictException(
                code=ErrorCode.CONFLICT,
                detail="이미 저장된 레시피입니다.",
            )

        board_name, author_name = parse_mangae_source_id(request.source_id)
        detail = await self.recipe_detail_service.get_detail(board_name, author_name)
        recipe_name = detail.recipe_name
        recipe_difficulty = None
        time_value = None
        snapshot = {
            "ingredients": [item.model_dump() for item in detail.ingredients],
            "steps": [item.model_dump() for item in detail.steps],
            "tips": list(detail.tips),
            "board_name": detail.board_name,
            "author_name": detail.author_name,
            "source_url": detail.source_url,
            "main_image_url": detail.main_image_url,
        }

        entity = SavedRecipe(
            user_id=self.user.id,
            source=request.source,
            source_id=request.source_id,
            recipe_name=recipe_name,
            recipe_difficulty=recipe_difficulty,
            time=time_value,
            snapshot=snapshot,
        )
        saved = await self.repo.add(entity)
        return SavedRecipeDetailResponse.model_validate(saved)

    async def list_saved(self) -> list[SavedRecipeListItem]:
        rows = await self.repo.list_by_user(self.user.id)
        return [SavedRecipeListItem.model_validate(row) for row in rows]

    async def get(self, recipe_id: uuid.UUID) -> SavedRecipeDetailResponse:
        row = await self.repo.get_by_id(recipe_id, self.user.id)
        if row is None:
            raise NotFoundException(detail="저장된 레시피를 찾을 수 없습니다.")
        return SavedRecipeDetailResponse.model_validate(row)

    async def delete(self, recipe_id: uuid.UUID) -> None:
        deleted = await self.repo.delete(recipe_id, self.user.id)
        if not deleted:
            raise NotFoundException(detail="저장된 레시피를 찾을 수 없습니다.")

    async def status(
        self, source: str, source_id: str
    ) -> SavedRecipeStatusResponse:
        if source != "mangae":
            raise BadRequestException(detail="source는 mangae 여야 합니다.")
        parse_mangae_source_id(source_id)
        row = await self.repo.find_by_source(self.user.id, source, source_id)
        if row is None:
            return SavedRecipeStatusResponse(saved=False, id=None)
        return SavedRecipeStatusResponse(saved=True, id=row.id)
