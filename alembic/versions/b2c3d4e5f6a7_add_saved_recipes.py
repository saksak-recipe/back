"""add_saved_recipes

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-07-21 01:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "saved_recipes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("source_id", sa.String(length=512), nullable=False),
        sa.Column("recipe_name", sa.String(length=256), nullable=False),
        sa.Column("recipe_difficulty", sa.String(length=64), nullable=True),
        sa.Column("time", sa.String(length=64), nullable=True),
        sa.Column(
            "snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "source", "source_id", name="uq_saved_recipes_user_source"
        ),
    )
    op.create_index(
        op.f("ix_saved_recipes_user_id"), "saved_recipes", ["user_id"], unique=False
    )
    op.create_index(
        "ix_saved_recipes_user_created",
        "saved_recipes",
        ["user_id", sa.literal_column("created_at DESC")],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_saved_recipes_user_created", table_name="saved_recipes")
    op.drop_index(op.f("ix_saved_recipes_user_id"), table_name="saved_recipes")
    op.drop_table("saved_recipes")
