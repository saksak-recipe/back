from __future__ import annotations

import uuid

import uuid6
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from core.exception.exceptions import DatabaseException
from domains.notification.model import Notification


class NotificationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_if_absent(
        self, notification: Notification
    ) -> Notification | None:
        try:
            notification.id = notification.id or uuid6.uuid7()
            if notification.is_read is None:
                notification.is_read = False
            dialect_name = self.session.get_bind().dialect.name
            insert = sqlite_insert if dialect_name == "sqlite" else postgresql_insert
            stmt = (
                insert(Notification)
                .values(
                    id=notification.id,
                    user_id=notification.user_id,
                    type=notification.type,
                    title=notification.title,
                    body=notification.body,
                    reference_key=notification.reference_key,
                    payload=notification.payload,
                    is_read=notification.is_read,
                )
                .on_conflict_do_nothing(
                    index_elements=["user_id", "reference_key"],
                )
                .returning(Notification)
            )
            result = await self.session.execute(stmt)
            row = result.scalar_one_or_none()
            return row
        except SQLAlchemyError as e:
            raise DatabaseException(
                detail="알림 저장 중 DB 오류가 발생했습니다."
            ) from e

    async def list_by_user(self, user_id: uuid.UUID) -> list[Notification]:
        try:
            stmt = (
                select(Notification)
                .where(Notification.user_id == user_id)
                .order_by(Notification.created_at.desc())
            )
            result = await self.session.execute(stmt)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            raise DatabaseException(
                detail="알림 목록 조회 중 DB 오류가 발생했습니다."
            ) from e

    async def count_unread(self, user_id: uuid.UUID) -> int:
        try:
            stmt = select(func.count()).select_from(Notification).where(
                Notification.user_id == user_id,
                Notification.is_read.is_(False),
            )
            result = await self.session.execute(stmt)
            return int(result.scalar_one())
        except SQLAlchemyError as e:
            raise DatabaseException(
                detail="미읽음 알림 수 조회 중 DB 오류가 발생했습니다."
            ) from e

    async def get_by_id_for_user(
        self, notification_id: uuid.UUID, user_id: uuid.UUID
    ) -> Notification | None:
        try:
            stmt = select(Notification).where(
                Notification.id == notification_id,
                Notification.user_id == user_id,
            )
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            raise DatabaseException(
                detail="알림 조회 중 DB 오류가 발생했습니다."
            ) from e

    async def mark_read(self, notification: Notification) -> Notification:
        try:
            notification.is_read = True
            await self.session.flush()
            return notification
        except SQLAlchemyError as e:
            raise DatabaseException(
                detail="알림 읽음 처리 중 DB 오류가 발생했습니다."
            ) from e

    async def mark_all_read(self, user_id: uuid.UUID) -> int:
        try:
            stmt = (
                update(Notification)
                .where(
                    Notification.user_id == user_id,
                    Notification.is_read.is_(False),
                )
                .values(is_read=True)
            )
            result = await self.session.execute(stmt)
            await self.session.flush()
            return int(result.rowcount or 0)
        except SQLAlchemyError as e:
            raise DatabaseException(
                detail="알림 전체 읽음 처리 중 DB 오류가 발생했습니다."
            ) from e

    async def delete(self, notification: Notification) -> None:
        try:
            await self.session.delete(notification)
            await self.session.flush()
        except SQLAlchemyError as e:
            raise DatabaseException(
                detail="알림 삭제 중 DB 오류가 발생했습니다."
            ) from e
