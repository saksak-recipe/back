from __future__ import annotations

from datetime import datetime
from typing import Any

import uuid6
from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from core.database import Base


class SavedRecipe(Base):
    __tablename__ = "saved_recipes"

    id: Mapped[uuid6.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid6.uuid7
    )
    user_id: Mapped[uuid6.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    source_id: Mapped[str] = mapped_column(String(512), nullable=False)
    recipe_name: Mapped[str] = mapped_column(String(256), nullable=False)
    recipe_difficulty: Mapped[str | None] = mapped_column(String(64), nullable=True)
    time: Mapped[str | None] = mapped_column(String(64), nullable=True)
    snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship("User", back_populates="saved_recipes")

    __table_args__ = (
        UniqueConstraint(
            "user_id", "source", "source_id", name="uq_saved_recipes_user_source"
        ),
        Index("ix_saved_recipes_user_created", "user_id", created_at.desc()),
    )
