from datetime import datetime

import uuid6  # 추후 인덱싱 고려했을 때, uuid와 다르게 uuid6 라이브러리를 사용했을 경우, 생성된 시간 정보가 앞에 들어감. 물론 여기서 uuid6를 배정하진 않음

from sqlalchemy import String, DateTime, func, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base

class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid6.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid6.uuid7
    )
    email: Mapped[str] = mapped_column(String(128), unique=True)
    password: Mapped[str | None] = mapped_column(String(128), nullable=True)
    kakao_id: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    nickname: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    ingredients: Mapped[list["Ingredient"]] = relationship(
        "Ingredient",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    saved_recipes: Mapped[list["SavedRecipe"]] = relationship(
        "SavedRecipe",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    shopping_items: Mapped[list["ShoppingItem"]] = relationship(
        "ShoppingItem",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        # 닉네임 대소문자 중복 닉네임 방지
        Index("ix_user_nickname_lower", func.lower(nickname), unique=True),
        # 생성일 기준 정렬을 위한 일반 인덱스 설정
        Index("ix_user_created_at", created_at.desc()),
    )
