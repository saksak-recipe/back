from __future__ import annotations

from datetime import date, datetime

import uuid6
from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class IngredientShelfLife(Base):
    __tablename__ = "ingredient_shelf_lives"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ingredient_name: Mapped[str] = mapped_column(String(45), nullable=False)
    shelf_life_days: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "ingredient_name",
            name="uq_ingredient_shelf_lives_ingredient_name",
        ),
    )


class IngredientShelfLifeLog(Base):
    __tablename__ = "ingredient_shelf_life_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    log_type: Mapped[str] = mapped_column(String(32), nullable=False)
    ingredient_name: Mapped[str] = mapped_column(String(45), nullable=False)
    user_id: Mapped[uuid6.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    purchase_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    user_expiration_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    user_shelf_life_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    master_shelf_life_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index(
            "ix_ingredient_shelf_life_logs_log_type_ingredient_name",
            "log_type",
            "ingredient_name",
        ),
        Index(
            "ix_ingredient_shelf_life_logs_ingredient_name",
            "ingredient_name",
        ),
    )
