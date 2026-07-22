from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from core.exception.exceptions import DatabaseException
from domains.ingredient_shelf_life.model import (
    IngredientShelfLife,
    IngredientShelfLifeLog,
)


class IngredientShelfLifeRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_names(
        self, names: list[str]
    ) -> dict[str, IngredientShelfLife]:
        if not names:
            return {}
        try:
            unique_names = list(dict.fromkeys(names))
            stmt = select(IngredientShelfLife).where(
                IngredientShelfLife.ingredient_name.in_(unique_names)
            )
            result = await self.session.execute(stmt)
            rows = list(result.scalars().all())
            return {row.ingredient_name: row for row in rows}
        except SQLAlchemyError as e:
            raise DatabaseException(
                detail="식재료 보관일수 조회 중 DB 오류가 발생했습니다."
            ) from e

    async def add_logs(self, logs: list[IngredientShelfLifeLog]) -> None:
        if not logs:
            return
        try:
            self.session.add_all(logs)
            await self.session.flush()
        except SQLAlchemyError as e:
            raise DatabaseException(
                detail="식재료 보관일수 로그 저장 중 DB 오류가 발생했습니다."
            ) from e
