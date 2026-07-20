from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from core.exception.exceptions import DatabaseException
from domains.saved_recipe.model import SavedRecipe


class SavedRecipeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, recipe: SavedRecipe) -> SavedRecipe:
        try:
            self.session.add(recipe)
            await self.session.flush()
            return recipe
        except SQLAlchemyError as e:
            raise DatabaseException(
                detail="레시피 저장 중 DB 오류가 발생했습니다."
            ) from e

    async def list_by_user(self, user_id: uuid.UUID) -> list[SavedRecipe]:
        try:
            stmt = (
                select(SavedRecipe)
                .where(SavedRecipe.user_id == user_id)
                .order_by(SavedRecipe.created_at.desc())
            )
            result = await self.session.execute(stmt)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            raise DatabaseException(
                detail="저장 레시피 목록 조회 중 DB 오류가 발생했습니다."
            ) from e

    async def get_by_id(
        self, recipe_id: uuid.UUID, user_id: uuid.UUID
    ) -> SavedRecipe | None:
        try:
            stmt = select(SavedRecipe).where(
                SavedRecipe.id == recipe_id,
                SavedRecipe.user_id == user_id,
            )
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            raise DatabaseException(
                detail="저장 레시피 조회 중 DB 오류가 발생했습니다."
            ) from e

    async def find_by_source(
        self, user_id: uuid.UUID, source: str, source_id: str
    ) -> SavedRecipe | None:
        try:
            stmt = select(SavedRecipe).where(
                SavedRecipe.user_id == user_id,
                SavedRecipe.source == source,
                SavedRecipe.source_id == source_id,
            )
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            raise DatabaseException(
                detail="저장 레시피 조회 중 DB 오류가 발생했습니다."
            ) from e

    async def delete(self, recipe_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        try:
            stmt = delete(SavedRecipe).where(
                SavedRecipe.id == recipe_id,
                SavedRecipe.user_id == user_id,
            )
            result = await self.session.execute(stmt)
            return result.rowcount > 0
        except SQLAlchemyError as e:
            raise DatabaseException(
                detail="저장 레시피 삭제 중 DB 오류가 발생했습니다."
            ) from e
