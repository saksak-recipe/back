import uuid
from datetime import datetime

from sqlalchemy import select, func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio.session import AsyncSession

from core.exception.exceptions import DatabaseException
from domains.user.model import User


class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def _get_one(self, *args) -> User | None:
        """조건에 맞는 엔티티 조회"""
        try:
            stmt = select(User).where(*args)
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            raise DatabaseException(
                detail="사용자 조회 중 DB 오류가 발생했습니다."
            ) from e

    async def get_user_by_id(self, user_id: uuid.UUID) -> User | None:
        """고유ID 정보로 조회"""
        return await self._get_one(User.id == user_id)

    async def get_user_by_email(self, email: str) -> User | None:
        """이메일 정보로 조회"""
        return await self._get_one(User.email == email)

    async def get_user_by_nickname(self, nickname: str) -> User | None:
        """닉네임(대소문자 무시)으로 조회"""
        return await self._get_one(func.lower(User.nickname) == nickname.lower())

    async def get_user_by_kakao_id(self, kakao_id: str) -> User | None:
        """카카오 회원번호로 조회"""
        return await self._get_one(User.kakao_id == kakao_id)

    async def add_user(self, user: User):
        self.session.add(user)
        await self.session.flush()
        return user

    async def save(self, user: User) -> User:
        try:
            self.session.add(user)
            await self.session.flush()
            return user
        except SQLAlchemyError as e:
            raise DatabaseException(
                detail="사용자 저장 중 DB 오류가 발생했습니다."
            ) from e

    async def delete_user(self, user: User) -> None:
        try:
            await self.session.delete(user)
            await self.session.flush()
        except SQLAlchemyError as e:
            raise DatabaseException(
                detail="사용자 삭제 중 DB 오류가 발생했습니다."
            ) from e

    async def list_withdrawn_before(self, cutoff: datetime) -> list[User]:
        try:
            stmt = select(User).where(
                User.deleted_at.is_not(None),
                User.deleted_at < cutoff,
            )
            result = await self.session.execute(stmt)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            raise DatabaseException(
                detail="탈퇴 사용자 조회 중 DB 오류가 발생했습니다."
            ) from e
