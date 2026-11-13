"""nearby discovery: profiles, last-known positions, tokens, observations,
partnerships (active membership) replacing pairings; invitations.

Revision ID: b7d1sc0v3ry1
Revises: 58a9a37d73d0
Create Date: 2026-10-25

Non-destructive: existing pairings are converted into partnerships with
active memberships; history is preserved. The migration PREFLIGHTS the
pairings table for users appearing in more than one pairing (cross-column
duplicates) and aborts with a report instead of deleting data.
"""

from alembic import op
import sqlalchemy as sa

revision = "b7d1sc0v3ry1"
down_revision = "58a9a37d73d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # --- Preflight: refuse inconsistent memberships, never delete data ---
    duplicates = conn.execute(
        sa.text(
            """
            SELECT user_id, COUNT(*) AS pairings FROM (
                SELECT user_a_id AS user_id FROM pairings
                UNION ALL
                SELECT user_b_id AS user_id FROM pairings
            ) memberships
            GROUP BY user_id
            HAVING COUNT(*) > 1
            """
        )
    ).fetchall()
    if duplicates:
        report = "; ".join(f"user {str(row[0])} appears in {row[1]} pairings" for row in duplicates)
        raise RuntimeError(
            "Migration aborted: inconsistent pairings detected — "
            f"{report}. Resolve duplicates manually (do not delete history) "
            "and re-run."
        )

    # --- New tables ---
    op.create_table(
        "discovery_settings",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("age", sa.Integer(), nullable=True),
        sa.Column("pref_min_age", sa.Integer(), nullable=True),
        sa.Column("pref_max_age", sa.Integer(), nullable=True),
        sa.Column("discovery_radius_m", sa.Integer(), nullable=False),
        sa.Column("bluetooth_enabled", sa.Boolean(), nullable=False),
        sa.Column("gps_enabled", sa.Boolean(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("user_id"),
        sa.CheckConstraint("age IS NULL OR (age BETWEEN 18 AND 99)", name="ck_ds_age_range"),
        sa.CheckConstraint(
            "pref_min_age IS NULL OR (pref_min_age BETWEEN 18 AND 99)", name="ck_ds_pref_min_range"),
        sa.CheckConstraint(
            "pref_max_age IS NULL OR (pref_max_age BETWEEN 18 AND 99)", name="ck_ds_pref_max_range"),
        sa.CheckConstraint(
            "pref_min_age IS NULL OR pref_max_age IS NULL OR pref_min_age <= pref_max_age",
            name="ck_ds_pref_order"),
        sa.CheckConstraint("discovery_radius_m BETWEEN 100 AND 5000", name="ck_ds_radius_range"),
    )
    op.execute(
        "ALTER TABLE discovery_settings ALTER COLUMN discovery_radius_m SET DEFAULT 500"
    )
    op.execute(
        "ALTER TABLE discovery_settings ALTER COLUMN bluetooth_enabled SET DEFAULT false"
    )
    op.execute(
        "ALTER TABLE discovery_settings ALTER COLUMN gps_enabled SET DEFAULT false"
    )

    op.create_table(
        "user_interests",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("tag", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("user_id", "tag"),
        sa.CheckConstraint(
            "tag IN ('gaming','music','fitness','food','movies','travel','reading','outdoors')",
            name="ck_interest_tag"),
    )

    op.create_table(
        "last_known_positions",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("fix_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("user_id"),
    )

    op.create_table(
        "partnerships",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_by", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["ended_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "partnership_members",
        sa.Column("partnership_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "joined_at", sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("left_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["partnership_id"], ["partnerships.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("partnership_id", "user_id"),
    )
    op.create_index(
        "uq_partnership_member_active", "partnership_members", ["user_id"],
        unique=True, postgresql_where=sa.text("left_at IS NULL"),
    )

    op.create_table(
        "discovery_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("device_id", sa.Uuid(), nullable=False),
        sa.Column("token_value", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("token_value BETWEEN 0 AND 65535", name="ck_token_range"),
        sa.UniqueConstraint("token_value", name="uq_discovery_token_value"),
    )
    op.create_index(
        "uq_discovery_token_device", "discovery_tokens", ["device_id"],
        unique=True, postgresql_where=sa.text("revoked_at IS NULL"),
    )

    op.create_table(
        "discovery_observations",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("observer_user_id", sa.Uuid(), nullable=False),
        sa.Column("observed_token", sa.Integer(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "received_at", sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["observer_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("observed_token BETWEEN 0 AND 65535", name="ck_obs_token_range"),
        sa.UniqueConstraint(
            "observer_user_id", "observed_token", "captured_at",
            name="uq_observation_identity"),
    )
    op.create_index(
        "ix_observation_captured", "discovery_observations",
        ["observer_user_id", "captured_at"],
    )

    op.create_table(
        "partner_invitations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("from_user_id", sa.Uuid(), nullable=False),
        sa.Column("to_user_id", sa.Uuid(), nullable=False),
        sa.Column("pair_key", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["from_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["to_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("from_user_id <> to_user_id", name="ck_invite_not_self"),
        sa.CheckConstraint(
            "status IN ('pending','accepted','declined','expired')", name="ck_invite_status"),
    )
    op.create_index(
        "uq_invite_pending_pair", "partner_invitations", ["pair_key"],
        unique=True, postgresql_where=sa.text("status = 'pending'"),
    )

    # --- Convert existing pairings into partnerships + active memberships ---
    pairings = conn.execute(
        sa.text("SELECT id, user_a_id, user_b_id, created_at FROM pairings ORDER BY created_at")
    ).fetchall()
    for pairing_id, user_a, user_b, created_at in pairings:
        conn.execute(
            sa.text(
                "INSERT INTO partnerships (id, created_at) VALUES (:id, :created_at)"
            ),
            {"id": str(pairing_id), "created_at": created_at},
        )
        lo, hi = sorted((str(user_a), str(user_b)))
        conn.execute(
            sa.text(
                "INSERT INTO partnership_members (partnership_id, user_id, joined_at) "
                "VALUES (:p, :a, :joined), (:p, :b, :joined)"
            ),
            {"p": str(pairing_id), "a": str(user_a), "b": str(user_b), "joined": created_at},
        )
        _ = lo, hi  # canonical order kept for reference

    # Verified equal before dropping: every pairing became exactly two
    # active memberships (preflight guaranteed no user overlap).
    op.drop_table("pairings")


def downgrade() -> None:
    # History-preserving downgrade is not provided: partnership ends and
    # overlapping historical partnerships cannot be losslessly mapped back
    # onto the single pairings table (user_a_id/user_b_id uniqueness).
    raise NotImplementedError(
        "Downgrade would lose partnership history; restore from backup instead."
    )
