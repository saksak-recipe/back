"""add_kakao_id_nullable_password

Revision ID: a1b2c3d4e5f6
Revises: f550a0b2a076
Create Date: 2026-07-21 01:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "f550a0b2a076"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "users",
        "password",
        existing_type=sa.String(length=128),
        nullable=True,
    )
    op.add_column(
        "users",
        sa.Column("kakao_id", sa.String(length=64), nullable=True),
    )
    op.create_unique_constraint("uq_users_kakao_id", "users", ["kakao_id"])


def downgrade() -> None:
    op.drop_constraint("uq_users_kakao_id", "users", type_="unique")
    op.drop_column("users", "kakao_id")
    op.alter_column(
        "users",
        "password",
        existing_type=sa.String(length=128),
        nullable=False,
    )
