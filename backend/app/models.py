"""SQLAlchemy ORM models. See docs/ARCHITECTURE.md 'Persistence'."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    SmallInteger,
    String,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    display_name: Mapped[str] = mapped_column(String(64), nullable=False)
    points_balance: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lifetime_xp: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    location_sharing: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Partnership(Base):
    """A partnership between two users (docs/DISCOVERY_PLAN.md).

    Active memberships live in partnership_members with a partial unique
    index on user_id (one active partnership per user, enforced by the
    database). History is preserved: ending sets ended_at / left_at and
    never deletes rows. Replaced the earlier pairings table (user_a_id /
    user_b_id column-pair uniqueness) during migration.
    """

    __tablename__ = "partnerships"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class PartnershipMember(Base):
    __tablename__ = "partnership_members"
    __table_args__ = (
        # One ACTIVE membership per user across all partnerships (partial
        # unique index); historical memberships keep their rows with left_at.
        Index(
            "uq_partnership_member_active",
            "user_id",
            postgresql_where=text("left_at IS NULL"),
            sqlite_where=text("left_at IS NULL"),
        ),
    )

    partnership_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("partnerships.id"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    # Compact numeric alias provisioned to firmware; unique across devices.
    firmware_alias: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    # One-time pairing credential (hashed). Null once claimed.
    pairing_code_hash: Mapped[str | None] = mapped_column(String(256), nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LoginSession(Base):
    __tablename__ = "login_sessions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    csrf_token: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class QuestSession(Base):
    __tablename__ = "quest_sessions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    quest_id: Mapped[str] = mapped_column(String(32), nullable=False)
    demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    # Target frozen at activation so later config edits cannot move the goalpost.
    target_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # NULL denotes a pre-interaction/legacy session. New together and heart
    # sessions are frozen to the current interaction state machine at accept.
    interaction_version: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    session_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    geofence_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    geofence_lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    geofence_radius_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    # v2 raid: the landmark this session froze at creation (raid only).
    landmark_id: Mapped[str | None] = mapped_column(
        ForeignKey("landmarks.id"), nullable=True
    )
    progress_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "state IN ('pending','active','completed','cancelled')", name="ck_sessions_state"
        ),
    )


class SessionInteraction(Base):
    """Server-owned phase state for versioned quest interactions."""

    __tablename__ = "session_interactions"

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("quest_sessions.id", ondelete="CASCADE"), primary_key=True
    )
    version: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    phase: Mapped[str] = mapped_column(String(24), nullable=False)
    phase_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    timing_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    evidence_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_evidence_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    round_index: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    active_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    prompt_kind: Mapped[str | None] = mapped_column(String(8), nullable=True)
    prompt_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    results: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    __table_args__ = (
        CheckConstraint("version >= 1", name="ck_session_interaction_version"),
        CheckConstraint(
            "phase IN ('start_pin','timing','end_pin','baseline','select_prompt','round','summary')",
            name="ck_session_interaction_phase",
        ),
    )


class SessionPin(Base):
    """Short-lived participant-owned display code for a PIN stage.

    `display_code` is visible only through participant-scoped snapshots and is
    deleted when the session completes/cancels. Failed entry attempts count
    against the code being entered, which gives each user five tries per code
    version without affecting the partner's code.
    """

    __tablename__ = "session_pins"

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("quest_sessions.id", ondelete="CASCADE"), primary_key=True
    )
    stage: Mapped[str] = mapped_column(String(8), primary_key=True)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    code_version: Mapped[int] = mapped_column(Integer, nullable=False)
    display_code: Mapped[str] = mapped_column(String(4), nullable=False)
    failed_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint("stage IN ('start','end')", name="ck_session_pin_stage"),
        CheckConstraint("code_version >= 1", name="ck_session_pin_version"),
        CheckConstraint("failed_attempts >= 0 AND failed_attempts <= 5", name="ck_session_pin_attempts"),
    )


class SessionPinHistory(Base):
    """Codes already issued in this active session, enforcing distinctness."""

    __tablename__ = "session_pin_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("quest_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    display_code: Mapped[str] = mapped_column(String(4), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (UniqueConstraint("session_id", "display_code", name="uq_session_pin_history_code"),)


class SessionInteractionCommand(Base):
    """Idempotency key for phone/wearable interaction commands."""

    __tablename__ = "session_interaction_commands"

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("quest_sessions.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    command_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    result_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    result_message: Mapped[str | None] = mapped_column(String(160), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SessionParticipant(Base):
    __tablename__ = "session_participants"

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("quest_sessions.id"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TelemetryRecord(Base):
    __tablename__ = "telemetry_records"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    device_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("devices.id"), nullable=False)
    boot_id: Mapped[str] = mapped_column(String(64), nullable=False)
    sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("quest_sessions.id"), nullable=True
    )
    uptime_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    clock_source: Mapped[str] = mapped_column(String(32), nullable=False)
    clock_uncertainty_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gps_valid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    gps_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    gps_lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    gps_fix_age_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # v2: where the fix came from — "phone" (relayed by the companion app) or
    # "wearable" (legacy ASD2501 shield). Nullable for pre-v2 history.
    gps_source: Mapped[str | None] = mapped_column(String(16), nullable=True)
    hr_valid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    bpm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hr_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    peer_observed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    peer_device_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    peer_boot_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    peer_heartbeat_sequence: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    peer_session_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    peer_observation_age_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("device_id", "boot_id", "sequence", name="uq_telemetry_identity"),
        Index("ix_telemetry_session", "session_id", "device_id", "captured_at"),
    )


class QuestAward(Base):
    __tablename__ = "quest_awards"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("quest_sessions.id"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    points: Mapped[int] = mapped_column(Integer, nullable=False)
    xp: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("session_id", "user_id", name="uq_award_once"),)


class Reward(Base):
    __tablename__ = "rewards"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(String(256), nullable=False)
    price: Mapped[int] = mapped_column(Integer, nullable=False)


class OwnedReward(Base):
    __tablename__ = "owned_rewards"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), primary_key=True
    )
    reward_id: Mapped[str] = mapped_column(ForeignKey("rewards.id"), primary_key=True)
    acquired_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PointTransaction(Base):
    __tablename__ = "point_transactions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    delta: Mapped[int] = mapped_column(Integer, nullable=False)
    xp_delta: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    balance_after: Mapped[int] = mapped_column(Integer, nullable=False)
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("quest_sessions.id"), nullable=True
    )
    reward_id: Mapped[str | None] = mapped_column(ForeignKey("rewards.id"), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_purchase_idempotency"),
        # v2: pet care moves XP without points, so either currency counts.
        CheckConstraint("delta <> 0 OR xp_delta <> 0", name="ck_tx_nonzero"),
    )


class AppState(Base):
    """Single-row table holding the global state version for SSE clients."""

    __tablename__ = "app_state"

    key: Mapped[str] = mapped_column(String(32), primary_key=True)
    value: Mapped[int] = mapped_column(BigInteger, nullable=False)


# --- Nearby discovery (docs/DISCOVERY_PLAN.md) ---

# Fixed interest catalog; user_interests.tag is constrained to these values.
INTEREST_TAGS = (
    "gaming",
    "music",
    "fitness",
    "food",
    "movies",
    "travel",
    "reading",
    "outdoors",
)


class DiscoverySetting(Base):
    """Editable discovery profile fields + per-method opt-in switches.

    A profile is COMPLETE when age, pref_min_age and pref_max_age are set and
    the user has chosen at least one interest tag. Incomplete profiles are
    excluded from discovery on both sides. Opt-ins default to off.
    """

    __tablename__ = "discovery_settings"
    __table_args__ = (
        CheckConstraint("age IS NULL OR (age BETWEEN 18 AND 99)", name="ck_ds_age_range"),
        CheckConstraint(
            "pref_min_age IS NULL OR (pref_min_age BETWEEN 18 AND 99)",
            name="ck_ds_pref_min_range",
        ),
        CheckConstraint(
            "pref_max_age IS NULL OR (pref_max_age BETWEEN 18 AND 99)",
            name="ck_ds_pref_max_range",
        ),
        CheckConstraint(
            "pref_min_age IS NULL OR pref_max_age IS NULL OR pref_min_age <= pref_max_age",
            name="ck_ds_pref_order",
        ),
        CheckConstraint(
            "discovery_radius_m BETWEEN 100 AND 5000", name="ck_ds_radius_range"
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), primary_key=True
    )
    age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pref_min_age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pref_max_age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    discovery_radius_m: Mapped[int] = mapped_column(Integer, nullable=False, default=500)
    bluetooth_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    gps_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class UserInterest(Base):
    __tablename__ = "user_interests"
    __table_args__ = (
        CheckConstraint(
            "tag IN ('gaming','music','fitness','food','movies','travel','reading','outdoors')",
            name="ck_interest_tag",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    tag: Mapped[str] = mapped_column(String(32), primary_key=True)


class QuizQuestion(Base):
    """One 'Know Your Partner' quiz question generated at session activation.

    The ANSWERER answers questions about the SUBJECT (their partner): the
    correct option is one of the subject's interest tags; distractors come
    from the same catalog. The correct index never leaves the server.
    """

    __tablename__ = "quiz_questions"
    __table_args__ = (
        UniqueConstraint(
            "session_id", "answerer_user_id", "question_index",
            name="uq_quiz_question_per_answerer",
        ),
        CheckConstraint("correct_index BETWEEN 0 AND 3", name="ck_quiz_correct_range"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("quest_sessions.id", ondelete="CASCADE"), nullable=False
    )
    answerer_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    subject_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    question_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(String(200), nullable=False)
    options: Mapped[list] = mapped_column(JSON, nullable=False)  # exactly 4 strings
    correct_index: Mapped[int] = mapped_column(SmallInteger, nullable=False)


class QuizAnswer(Base):
    """The answerer's choice for one question (latest wins). Server-scored."""

    __tablename__ = "quiz_answers"
    __table_args__ = (
        UniqueConstraint("session_id", "user_id", "question_index", name="uq_quiz_answer"),
        CheckConstraint("choice BETWEEN 0 AND 3", name="ck_quiz_choice_range"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("quest_sessions.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    question_index: Mapped[int] = mapped_column(Integer, nullable=False)
    choice: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    answered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class LastKnownPosition(Base):
    """Durable last-known wearable GPS position per user.

    Updated only by trustworthy valid fixes during telemetry ingest
    (fix_time = captured_at - gps_fix_age_ms). Age is recomputed at read
    time; discovery expiry never deletes the row. Invalid or no-fix records
    never erase a stored position.
    """

    __tablename__ = "last_known_positions"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    fix_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DiscoveryToken(Base):
    """Opaque 16-bit token advertised by a wearable for nearby discovery.

    Provisioned through the authenticated phone link and mapped to the
    device's owning user server-side. Rotating the token (or unbinding the
    device) invalidates the old value. Classroom-grade identifier only —
    not a claim of unlinkability or anti-spoofing security.
    """

    __tablename__ = "discovery_tokens"
    __table_args__ = (
        CheckConstraint("token_value BETWEEN 0 AND 65535", name="ck_token_range"),
        # At most one live token per device.
        Index(
            "uq_discovery_token_device",
            "device_id",
            postgresql_where=text("revoked_at IS NULL"),
            sqlite_where=text("revoked_at IS NULL"),
        ),
        UniqueConstraint("token_value", name="uq_discovery_token_value"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    device_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("devices.id"), nullable=False)
    token_value: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DiscoveryObservation(Base):
    """One direct wearable scan observation uploaded by the owner's phone.

    captured_at is the ORIGINAL observation time (board reception time,
    stamped by the phone from its anchored clock minus the reported age).
    Identity (observer, token, captured_at) makes uploads idempotent:
    retransmitting the same observation cannot refresh presence; only a new
    physical reception (new captured_at) can. Discovery presence is derived
    at query time from rows no older than the BLE expiry window.
    """

    __tablename__ = "discovery_observations"
    __table_args__ = (
        UniqueConstraint(
            "observer_user_id", "observed_token", "captured_at",
            name="uq_observation_identity",
        ),
        CheckConstraint("observed_token BETWEEN 0 AND 65535", name="ck_obs_token_range"),
        Index("ix_observation_captured", "observer_user_id", "captured_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    observer_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    observed_token: Mapped[int] = mapped_column(Integer, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PartnerInvitation(Base):
    """Partner invitation between two users (docs/DISCOVERY_PLAN.md).

    Pair invitations are separate from quest-session acceptance. A pending
    invitation expires 5 minutes after creation (lazy transition). pair_key
    is the canonical "min_uuid:max_uuid" of the two users so the database
    can enforce at most one pending invitation per pair in either direction.
    """

    __tablename__ = "partner_invitations"
    __table_args__ = (
        CheckConstraint("from_user_id <> to_user_id", name="ck_invite_not_self"),
        CheckConstraint(
            "status IN ('pending','accepted','declined','expired')",
            name="ck_invite_status",
        ),
        Index(
            "uq_invite_pending_pair",
            "pair_key",
            postgresql_where=text("status = 'pending'"),
            sqlite_where=text("status = 'pending'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    from_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    to_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    pair_key: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# --- v2: pet, landmarks, raid ---


class Landmark(Base):
    """Seeded raid destination. Coordinates are real-world places chosen for
    the demo; the raid gate freezes the session's landmark at creation."""

    __tablename__ = "landmarks"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    radius_m: Mapped[float] = mapped_column(Float, nullable=False, default=50.0)


class Pet(Base):
    """Server mirror of each user's wearable-owned pet. Cosmetic state
    (species/name) is set by the wearable bonding flow and mirrored here for
    web/phone display; XP/level remain owned by the User row."""

    __tablename__ = "pets"
    __table_args__ = (
        CheckConstraint(
            "species IN ('spark','fluff','pip')", name="ck_pets_species"
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    species: Mapped[str | None] = mapped_column(String(8), nullable=True)
    name: Mapped[str | None] = mapped_column(String(8), nullable=True)
    last_care_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    care_streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class RaidOutcome(Base):
    """One board's verified fight report. The raid completes only when both
    participants have reported; awards require both to report 'win'."""

    __tablename__ = "raid_outcomes"
    __table_args__ = (
        UniqueConstraint("session_id", "user_id", name="uq_raid_outcome_reporter"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("quest_sessions.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    command_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    outcome: Mapped[str] = mapped_column(String(8), nullable=False)
    fight_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fight_ended_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
