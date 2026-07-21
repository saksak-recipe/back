from __future__ import annotations

import uuid6
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base

if TYPE_CHECKING:
    from domains.user.model import User


class ShoppingItem(Base):
    __tablename__ = "shopping_items"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid6.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    group_id: Mapped[uuid6.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("groups.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(45), nullable=False)
    is_checked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    user: Mapped["User"] = relationship("User", back_populates="shopping_items")

    __table_args__ = (
        Index(
            "uq_shopping_items_personal_user_name",
            "user_id",
            "name",
            unique=True,
            postgresql_where=text("group_id IS NULL"),
            sqlite_where=text("group_id IS NULL"),
        ),
        Index(
            "uq_shopping_items_group_name",
            "group_id",
            "name",
            unique=True,
            postgresql_where=text("group_id IS NOT NULL"),
            sqlite_where=text("group_id IS NOT NULL"),
        ),
    )
