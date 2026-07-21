"""add_shopping_group_scope

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-07-21 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("shopping_items", sa.Column("group_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_shopping_items_group_id_groups",
        "shopping_items",
        "groups",
        ["group_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        op.f("ix_shopping_items_group_id"),
        "shopping_items",
        ["group_id"],
        unique=False,
    )
    op.drop_constraint(
        "uq_shopping_items_user_name",
        "shopping_items",
        type_="unique",
    )
    op.create_index(
        "uq_shopping_items_personal_user_name",
        "shopping_items",
        ["user_id", "name"],
        unique=True,
        postgresql_where=sa.text("group_id IS NULL"),
    )
    op.create_index(
        "uq_shopping_items_group_name",
        "shopping_items",
        ["group_id", "name"],
        unique=True,
        postgresql_where=sa.text("group_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_shopping_items_group_name", table_name="shopping_items")
    op.drop_index(
        "uq_shopping_items_personal_user_name", table_name="shopping_items"
    )
    op.create_unique_constraint(
        "uq_shopping_items_user_name",
        "shopping_items",
        ["user_id", "name"],
    )
    op.drop_index(op.f("ix_shopping_items_group_id"), table_name="shopping_items")
    op.drop_constraint(
        "fk_shopping_items_group_id_groups",
        "shopping_items",
        type_="foreignkey",
    )
    op.drop_column("shopping_items", "group_id")
