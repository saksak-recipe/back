import uuid

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from core.exception.exceptions import DatabaseException
from domains.shopping.model import ShoppingItem


class ShoppingRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add_items(self, items: list[ShoppingItem]) -> list[ShoppingItem]:
        if not items:
            return []

        try:
            dialect_name = self.session.get_bind().dialect.name
            insert = sqlite_insert if dialect_name == "sqlite" else postgresql_insert
            stmt = (
                insert(ShoppingItem)
                .values(
                    [
                        {
                            "user_id": item.user_id,
                            "name": item.name,
                            "is_checked": item.is_checked,
                        }
                        for item in items
                    ]
                )
                .on_conflict_do_nothing(index_elements=["user_id", "name"])
                .returning(ShoppingItem)
            )
            result = await self.session.execute(stmt)
            saved_by_key = {
                (item.user_id, item.name): item for item in result.scalars().all()
            }
            return [
                saved_by_key.pop((item.user_id, item.name))
                for item in items
                if (item.user_id, item.name) in saved_by_key
            ]
        except SQLAlchemyError as e:
            raise DatabaseException(
                detail="장보기 항목 저장 중 DB 오류가 발생했습니다."
            ) from e

    async def list_by_user(self, user_id: uuid.UUID) -> list[ShoppingItem]:
        try:
            stmt = (
                select(ShoppingItem)
                .where(ShoppingItem.user_id == user_id)
                .order_by(ShoppingItem.created_at.asc())
            )
            result = await self.session.execute(stmt)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            raise DatabaseException(
                detail="장보기 목록 조회 중 DB 오류가 발생했습니다."
            ) from e

    async def get_existing_names(
        self, user_id: uuid.UUID, names: list[str]
    ) -> set[str]:
        try:
            stmt = select(ShoppingItem.name).where(
                ShoppingItem.user_id == user_id,
                ShoppingItem.name.in_(names),
            )
            result = await self.session.execute(stmt)
            return set(result.scalars().all())
        except SQLAlchemyError as e:
            raise DatabaseException(
                detail="기존 장보기 항목 조회 중 DB 오류가 발생했습니다."
            ) from e

    async def get_by_id(
        self, item_id: int, user_id: uuid.UUID
    ) -> ShoppingItem | None:
        try:
            stmt = select(ShoppingItem).where(
                ShoppingItem.id == item_id,
                ShoppingItem.user_id == user_id,
            )
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            raise DatabaseException(
                detail="장보기 항목 조회 중 DB 오류가 발생했습니다."
            ) from e

    async def delete_item(self, item_id: int, user_id: uuid.UUID) -> bool:
        try:
            stmt = delete(ShoppingItem).where(
                ShoppingItem.id == item_id,
                ShoppingItem.user_id == user_id,
            )
            result = await self.session.execute(stmt)
            return result.rowcount > 0
        except SQLAlchemyError as e:
            raise DatabaseException(
                detail="장보기 항목 삭제 중 DB 오류가 발생했습니다."
            ) from e

    async def delete_all(self, user_id: uuid.UUID) -> bool:
        try:
            stmt = delete(ShoppingItem).where(ShoppingItem.user_id == user_id)
            result = await self.session.execute(stmt)
            await self.session.flush()
            return result.rowcount > 0
        except SQLAlchemyError as e:
            raise DatabaseException(
                detail="장보기 항목 일괄 삭제 중 DB 오류가 발생했습니다."
            ) from e
