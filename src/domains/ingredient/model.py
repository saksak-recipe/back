from __future__ import annotations

import uuid6

from datetime import date, datetime

from sqlalchemy import BigInteger, ForeignKey, String, Date, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base

class Ingredient(Base):
    __tablename__ = "ingredients"

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

    ingredient_name: Mapped[str] = mapped_column(String(45))
    expiration_date: Mapped[date | None] = mapped_column(Date)
    purchase_date: Mapped[date] = mapped_column(
        Date, server_default=func.current_date()
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    user: Mapped["User"] = relationship(
        "User",
        back_populates="ingredients"
    )
