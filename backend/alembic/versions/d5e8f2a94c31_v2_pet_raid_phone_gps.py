"""v2: pet mirror, landmarks/raid, phone GPS source; heart quest dropped

Revision ID: d5e8f2a94c31
Revises: c4f7a91e2b10
Create Date: 2026-11-06

Non-destructive: additive columns/tables only. Historical telemetry gets
gps_source='wearable' (the only source that existed before v2). Existing
quest sessions are untouched; heart_challenge rows remain for history.
"""

from alembic import op
import sqlalchemy as sa


revision = "d5e8f2a94c31"
down_revision = "c4f7a91e2b10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # v2 pet care grants XP without points; every transaction must still move
    # SOMETHING, so the nonzero check now covers either currency.
    op.drop_constraint("ck_tx_nonzero", "point_transactions", type_="check")
    op.create_check_constraint(
        "ck_tx_nonzero",
        "point_transactions",
        "delta <> 0 OR xp_delta <> 0",
    )

    op.add_column(
        "telemetry_records",
        sa.Column("gps_source", sa.String(length=16), nullable=True),
    )
    # Backfill: every pre-v2 fix came from the wearable shield.
    op.execute("UPDATE telemetry_records SET gps_source = 'wearable' WHERE gps_valid = true")

    op.create_table(
        "landmarks",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("radius_m", sa.Float(), nullable=False),
    )

    op.add_column(
        "quest_sessions",
        sa.Column(
            "landmark_id",
            sa.String(length=32),
            sa.ForeignKey("landmarks.id"),
            nullable=True,
        ),
    )

    op.create_table(
        "pets",
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("species", sa.String(length=8), nullable=True),
        sa.Column("name", sa.String(length=8), nullable=True),
        sa.Column("last_care_date", sa.String(length=10), nullable=True),
        sa.Column("care_streak", sa.Integer(), nullable=False, server_default="0"),
        sa.CheckConstraint("species IN ('spark','fluff','pip')", name="ck_pets_species"),
    )

    op.create_table(
        "raid_outcomes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("session_id", sa.Uuid(), sa.ForeignKey("quest_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("command_id", sa.Uuid(), nullable=False),
        sa.Column("outcome", sa.String(length=8), nullable=False),
        sa.Column("fight_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fight_ended_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("session_id", "user_id", name="uq_raid_outcome_reporter"),
    )


def downgrade() -> None:
    op.drop_table("raid_outcomes")
    op.drop_table("pets")
    op.drop_column("quest_sessions", "landmark_id")
    op.drop_table("landmarks")
    op.drop_column("telemetry_records", "gps_source")
    op.drop_constraint("ck_tx_nonzero", "point_transactions", type_="check")
    op.create_check_constraint(
        "ck_tx_nonzero", "point_transactions", "delta <> 0"
    )
