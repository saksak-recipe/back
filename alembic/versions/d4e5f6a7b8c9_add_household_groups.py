"""add_household_groups

Revision ID: d4e5f6a7b8c9
Revises: b2c3d4e5f6a7
Create Date: 2026-07-21 15:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "groups",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=40), nullable=False),
        sa.Column("invite_code", sa.String(length=8), nullable=False),
        sa.Column("owner_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("invite_code"),
    )
    op.create_table(
        "group_members",
        sa.Column("group_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column(
            "role",
            sa.Enum("owner", "member", name="group_role", native_enum=False),
            nullable=False,
        ),
        sa.Column(
            "joined_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("group_id", "user_id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_table(
        "group_invites",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("group_id", sa.UUID(), nullable=False),
        sa.Column("inviter_id", sa.UUID(), nullable=False),
        sa.Column("invitee_id", sa.UUID(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "accepted",
                "rejected",
                "cancelled",
                name="invite_status",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["inviter_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["invitee_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_group_invites_group_id"), "group_invites", ["group_id"], unique=False
    )
    op.create_index(
        op.f("ix_group_invites_invitee_id"),
        "group_invites",
        ["invitee_id"],
        unique=False,
    )

    op.add_column("ingredients", sa.Column("group_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_ingredients_group_id_groups",
        "ingredients",
        "groups",
        ["group_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        op.f("ix_ingredients_group_id"), "ingredients", ["group_id"], unique=False
    )
    op.create_index(
        "uq_ingredients_group_name",
        "ingredients",
        ["group_id", "ingredient_name"],
        unique=True,
        postgresql_where=sa.text("group_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_ingredients_group_name", table_name="ingredients")
    op.drop_index(op.f("ix_ingredients_group_id"), table_name="ingredients")
    op.drop_constraint(
        "fk_ingredients_group_id_groups", "ingredients", type_="foreignkey"
    )
    op.drop_column("ingredients", "group_id")

    op.drop_index(op.f("ix_group_invites_invitee_id"), table_name="group_invites")
    op.drop_index(op.f("ix_group_invites_group_id"), table_name="group_invites")
    op.drop_table("group_invites")
    op.drop_table("group_members")
    op.drop_table("groups")
