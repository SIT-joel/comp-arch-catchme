"""quest PIN stages and Keep Your Cool phase state

Revision ID: c4f7a91e2b10
Revises: b7d1sc0v3ry1
Create Date: 2026-10-30

Non-destructive: existing sessions receive a NULL interaction version and
retain their existing lifecycle/evaluation behavior.
"""

from alembic import op
import sqlalchemy as sa


revision = "c4f7a91e2b10"
down_revision = "b7d1sc0v3ry1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("quest_sessions", sa.Column("interaction_version", sa.SmallInteger(), nullable=True))

    op.create_table(
        "session_interactions",
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.SmallInteger(), nullable=False),
        sa.Column("phase", sa.String(length=24), nullable=False),
        sa.Column("phase_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("timing_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("evidence_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_evidence_ms", sa.Integer(), nullable=False),
        sa.Column("round_index", sa.SmallInteger(), nullable=False),
        sa.Column("active_user_id", sa.Uuid(), nullable=True),
        sa.Column("prompt_kind", sa.String(length=8), nullable=True),
        sa.Column("prompt_id", sa.String(length=32), nullable=True),
        sa.Column("results", sa.JSON(), nullable=False),
        sa.CheckConstraint("version >= 1", name="ck_session_interaction_version"),
        sa.CheckConstraint(
            "phase IN ('start_pin','timing','end_pin','baseline','select_prompt','round','summary')",
            name="ck_session_interaction_phase",
        ),
        sa.ForeignKeyConstraint(["active_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["session_id"], ["quest_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("session_id"),
    )
    op.create_table(
        "session_pins",
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("stage", sa.String(length=8), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("code_version", sa.Integer(), nullable=False),
        sa.Column("display_code", sa.String(length=4), nullable=False),
        sa.Column("failed_attempts", sa.Integer(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("stage IN ('start','end')", name="ck_session_pin_stage"),
        sa.CheckConstraint("code_version >= 1", name="ck_session_pin_version"),
        sa.CheckConstraint("failed_attempts >= 0 AND failed_attempts <= 5", name="ck_session_pin_attempts"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["session_id"], ["quest_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("session_id", "stage", "owner_user_id"),
    )
    op.create_table(
        "session_pin_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("display_code", sa.String(length=4), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["quest_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "display_code", name="uq_session_pin_history_code"),
    )
    op.create_index("ix_session_pin_history_session_id", "session_pin_history", ["session_id"])
    op.create_table(
        "session_interaction_commands",
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("command_id", sa.Uuid(), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("result_code", sa.String(length=32), nullable=True),
        sa.Column("result_message", sa.String(length=160), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["quest_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("session_id", "user_id", "command_id"),
    )


def downgrade() -> None:
    op.drop_table("session_interaction_commands")
    op.drop_index("ix_session_pin_history_session_id", table_name="session_pin_history")
    op.drop_table("session_pin_history")
    op.drop_table("session_pins")
    op.drop_table("session_interactions")
    op.drop_column("quest_sessions", "interaction_version")
