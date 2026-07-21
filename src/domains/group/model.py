from __future__ import annotations

import enum
from datetime import datetime

import uuid6
from sqlalchemy import DateTime, Enum, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base


class GroupRole(str, enum.Enum):
    owner = "owner"
    member = "member"


class InviteStatus(str, enum.Enum):
    pending = "pending"
    accepted = "accepted"
    rejected = "rejected"
    cancelled = "cancelled"


class Group(Base):
    __tablename__ = "groups"

    id: Mapped[uuid6.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid6.uuid7
    )
    name: Mapped[str] = mapped_column(String(40), nullable=False)
    invite_code: Mapped[str] = mapped_column(String(8), unique=True, nullable=False)
    owner_id: Mapped[uuid6.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    members: Mapped[list[GroupMember]] = relationship(
        back_populates="group", cascade="all, delete-orphan"
    )
    invites: Mapped[list[GroupInvite]] = relationship(
        back_populates="group", cascade="all, delete-orphan"
    )


class GroupMember(Base):
    __tablename__ = "group_members"

    group_id: Mapped[uuid6.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("groups.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[uuid6.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
        unique=True,  # 유저당 1그룹
    )
    role: Mapped[GroupRole] = mapped_column(
        Enum(GroupRole, name="group_role", native_enum=False),
        nullable=False,
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    group: Mapped[Group] = relationship(back_populates="members")


class GroupInvite(Base):
    __tablename__ = "group_invites"

    id: Mapped[uuid6.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid6.uuid7
    )
    group_id: Mapped[uuid6.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("groups.id", ondelete="CASCADE"), index=True
    )
    inviter_id: Mapped[uuid6.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    invitee_id: Mapped[uuid6.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[InviteStatus] = mapped_column(
        Enum(InviteStatus, name="invite_status", native_enum=False),
        nullable=False,
        default=InviteStatus.pending,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    group: Mapped[Group] = relationship(back_populates="invites")
