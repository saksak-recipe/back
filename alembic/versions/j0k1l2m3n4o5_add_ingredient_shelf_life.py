"""add_ingredient_shelf_life

Revision ID: j0k1l2m3n4o5
Revises: i9j0k1l2m3n4
Create Date: 2026-07-22

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "j0k1l2m3n4o5"
down_revision: Union[str, Sequence[str], None] = "i9j0k1l2m3n4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ingredient_shelf_lives",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("ingredient_name", sa.String(length=45), nullable=False),
        sa.Column("shelf_life_days", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "ingredient_name",
            name="uq_ingredient_shelf_lives_ingredient_name",
        ),
    )
    op.create_table(
        "ingredient_shelf_life_logs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("log_type", sa.String(length=32), nullable=False),
        sa.Column("ingredient_name", sa.String(length=45), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("purchase_date", sa.Date(), nullable=True),
        sa.Column("user_expiration_date", sa.Date(), nullable=True),
        sa.Column("user_shelf_life_days", sa.Integer(), nullable=True),
        sa.Column("master_shelf_life_days", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_ingredient_shelf_life_logs_user_id"),
        "ingredient_shelf_life_logs",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_ingredient_shelf_life_logs_log_type_ingredient_name",
        "ingredient_shelf_life_logs",
        ["log_type", "ingredient_name"],
        unique=False,
    )
    op.create_index(
        "ix_ingredient_shelf_life_logs_ingredient_name",
        "ingredient_shelf_life_logs",
        ["ingredient_name"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ingredient_shelf_life_logs_ingredient_name",
        table_name="ingredient_shelf_life_logs",
    )
    op.drop_index(
        "ix_ingredient_shelf_life_logs_log_type_ingredient_name",
        table_name="ingredient_shelf_life_logs",
    )
    op.drop_index(
        op.f("ix_ingredient_shelf_life_logs_user_id"),
        table_name="ingredient_shelf_life_logs",
    )
    op.drop_table("ingredient_shelf_life_logs")
    op.drop_table("ingredient_shelf_lives")
