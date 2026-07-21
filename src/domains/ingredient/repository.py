import uuid

from sqlalchemy import select, delete
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from core.exception.exceptions import DatabaseException
from domains.ingredient.model import Ingredient


class IngredientRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add_ingredient(self, ingredients: list[Ingredient]) -> list[Ingredient]:
        try:
            self.session.add_all(ingredients)
            await self.session.flush()
            return ingredients
        except SQLAlchemyError as e:
            raise DatabaseException(
                detail="식재료 저장 중 DB 오류가 발생했습니다."
            ) from e

    async def get_ingredients(self, user_id: uuid.UUID) -> list[Ingredient]:
        try:
            stmt = (
                select(Ingredient)
                .where(
                    Ingredient.user_id == user_id,
                    Ingredient.group_id.is_(None),
                )
                .order_by(Ingredient.created_at.desc())
            )
            result = await self.session.execute(stmt)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            raise DatabaseException(
                detail="식재료 목록 조회 중 DB 오류가 발생했습니다."
            ) from e

    async def get_by_id(
        self, ingredient_id: int, user_id: uuid.UUID
    ) -> Ingredient | None:
        try:
            stmt = select(Ingredient).where(
                Ingredient.id == ingredient_id,
                Ingredient.user_id == user_id,
                Ingredient.group_id.is_(None),
            )
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            raise DatabaseException(
                detail="식재료 조회 중 DB 오류가 발생했습니다."
            ) from e

    async def delete_ingredient(self, ingredient_id: int, user_id: uuid.UUID) -> bool:
        try:
            stmt = delete(Ingredient).where(
                Ingredient.id == ingredient_id,
                Ingredient.user_id == user_id,
                Ingredient.group_id.is_(None),
            )
            result = await self.session.execute(stmt)
            return result.rowcount > 0
        except SQLAlchemyError as e:
            raise DatabaseException(
                detail="식재료 삭제 중 DB 오류가 발생했습니다."
            ) from e

    async def delete_all_ingredients(self, user_id: uuid.UUID) -> bool:
        try:
            stmt = delete(Ingredient).where(
                Ingredient.user_id == user_id,
                Ingredient.group_id.is_(None),
            )
            result = await self.session.execute(stmt)
            await self.session.flush()
            return result.rowcount > 0
        except SQLAlchemyError as e:
            raise DatabaseException(
                detail="식재료 일괄 삭제 중 DB 오류가 발생했습니다."
            ) from e

    async def list_by_group(self, group_id: uuid.UUID) -> list[Ingredient]:
        try:
            stmt = (
                select(Ingredient)
                .where(Ingredient.group_id == group_id)
                .order_by(Ingredient.created_at.desc())
            )
            result = await self.session.execute(stmt)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            raise DatabaseException(
                detail="그룹 식재료 목록 조회 중 DB 오류가 발생했습니다."
            ) from e

    async def get_by_id_in_group(
        self, ingredient_id: int, group_id: uuid.UUID
    ) -> Ingredient | None:
        try:
            stmt = select(Ingredient).where(
                Ingredient.id == ingredient_id,
                Ingredient.group_id == group_id,
            )
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            raise DatabaseException(
                detail="그룹 식재료 조회 중 DB 오류가 발생했습니다."
            ) from e

    async def find_name_in_group(
        self, group_id: uuid.UUID, name: str
    ) -> Ingredient | None:
        try:
            stmt = select(Ingredient).where(
                Ingredient.group_id == group_id,
                Ingredient.ingredient_name == name,
            )
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            raise DatabaseException(
                detail="그룹 식재료 조회 중 DB 오류가 발생했습니다."
            ) from e

    async def delete_in_group(self, ingredient_id: int, group_id: uuid.UUID) -> bool:
        try:
            stmt = delete(Ingredient).where(
                Ingredient.id == ingredient_id,
                Ingredient.group_id == group_id,
            )
            result = await self.session.execute(stmt)
            return result.rowcount > 0
        except SQLAlchemyError as e:
            raise DatabaseException(
                detail="그룹 식재료 삭제 중 DB 오류가 발생했습니다."
            ) from e

    async def delete_all_in_group(self, group_id: uuid.UUID) -> int:
        try:
            stmt = delete(Ingredient).where(Ingredient.group_id == group_id)
            result = await self.session.execute(stmt)
            await self.session.flush()
            return result.rowcount
        except SQLAlchemyError as e:
            raise DatabaseException(
                detail="그룹 식재료 일괄 삭제 중 DB 오류가 발생했습니다."
            ) from e
