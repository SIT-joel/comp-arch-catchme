"""Achievements: per-user unlocked achievement rows.

The catalog lives in code (app/services/achievements.py); rows are created
idempotently when each condition is first met.

Revision ID: c8e2a4b6d9f1
Revises: f7a2b3c94d51
"""

import sqlalchemy as sa
from alembic import op

revision = "c8e2a4b6d9f1"
down_revision = "f7a2b3c94d51"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_achievements",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("achievement_id", sa.String(length=40), nullable=False),
        sa.Column(
            "unlocked_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("user_id", "achievement_id", name="uq_achievement_once"),
    )
    op.create_index(
        "ix_user_achievements_user", "user_achievements", ["user_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_user_achievements_user", table_name="user_achievements")
    op.drop_table("user_achievements")
