from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.exception.exceptions import DatabaseException
from domains.group.model import Group, GroupInvite, GroupMember, InviteStatus


class GroupRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_membership(self, user_id: uuid.UUID) -> GroupMember | None:
        try:
            stmt = select(GroupMember).where(GroupMember.user_id == user_id)
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            raise DatabaseException(
                detail="그룹 멤버십 조회 중 DB 오류가 발생했습니다."
            ) from e

    async def get_group(self, group_id: uuid.UUID) -> Group | None:
        try:
            stmt = select(Group).where(Group.id == group_id)
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            raise DatabaseException(
                detail="그룹 조회 중 DB 오류가 발생했습니다."
            ) from e

    async def get_group_with_members(self, group_id: uuid.UUID) -> Group | None:
        try:
            stmt = (
                select(Group)
                .where(Group.id == group_id)
                .options(selectinload(Group.members))
            )
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            raise DatabaseException(
                detail="그룹 멤버 조회 중 DB 오류가 발생했습니다."
            ) from e

    async def get_by_invite_code(self, code: str) -> Group | None:
        try:
            stmt = select(Group).where(Group.invite_code == code)
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            raise DatabaseException(
                detail="초대 코드로 그룹 조회 중 DB 오류가 발생했습니다."
            ) from e

    async def add_group(self, group: Group) -> Group:
        try:
            self.session.add(group)
            await self.session.flush()
            return group
        except SQLAlchemyError as e:
            raise DatabaseException(
                detail="그룹 저장 중 DB 오류가 발생했습니다."
            ) from e

    async def add_member(self, member: GroupMember) -> GroupMember:
        try:
            self.session.add(member)
            await self.session.flush()
            return member
        except SQLAlchemyError as e:
            raise DatabaseException(
                detail="그룹 멤버 저장 중 DB 오류가 발생했습니다."
            ) from e

    async def delete_member(self, group_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        try:
            stmt = delete(GroupMember).where(
                GroupMember.group_id == group_id,
                GroupMember.user_id == user_id,
            )
            result = await self.session.execute(stmt)
            return result.rowcount > 0
        except SQLAlchemyError as e:
            raise DatabaseException(
                detail="그룹 멤버 삭제 중 DB 오류가 발생했습니다."
            ) from e

    async def delete_group(self, group: Group) -> None:
        try:
            await self.session.delete(group)
            await self.session.flush()
        except SQLAlchemyError as e:
            raise DatabaseException(
                detail="그룹 삭제 중 DB 오류가 발생했습니다."
            ) from e

    async def find_pending_invite(
        self, group_id: uuid.UUID, invitee_id: uuid.UUID
    ) -> GroupInvite | None:
        try:
            stmt = select(GroupInvite).where(
                GroupInvite.group_id == group_id,
                GroupInvite.invitee_id == invitee_id,
                GroupInvite.status == InviteStatus.pending,
            )
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            raise DatabaseException(
                detail="그룹 초대 조회 중 DB 오류가 발생했습니다."
            ) from e

    async def list_pending_for_invitee(
        self, invitee_id: uuid.UUID
    ) -> list[GroupInvite]:
        try:
            stmt = (
                select(GroupInvite)
                .where(
                    GroupInvite.invitee_id == invitee_id,
                    GroupInvite.status == InviteStatus.pending,
                )
                .order_by(GroupInvite.created_at.desc())
            )
            result = await self.session.execute(stmt)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            raise DatabaseException(
                detail="그룹 초대 목록 조회 중 DB 오류가 발생했습니다."
            ) from e

    async def get_invite(self, invite_id: uuid.UUID) -> GroupInvite | None:
        try:
            stmt = select(GroupInvite).where(GroupInvite.id == invite_id)
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            raise DatabaseException(
                detail="그룹 초대 조회 중 DB 오류가 발생했습니다."
            ) from e

    async def add_invite(self, invite: GroupInvite) -> GroupInvite:
        try:
            self.session.add(invite)
            await self.session.flush()
            return invite
        except SQLAlchemyError as e:
            raise DatabaseException(
                detail="그룹 초대 저장 중 DB 오류가 발생했습니다."
            ) from e
