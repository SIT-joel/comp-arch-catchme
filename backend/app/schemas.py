"""Pydantic request/response models aligned with docs/INTERFACES.md."""

import math
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Full set readable by serializers — heart_challenge stays known so legacy
# sessions keep rendering (v2 removed it from creation, see CreatableQuestId).
QuestId = Literal["together", "explore", "heart_challenge", "raid", "quiz"]
CreatableQuestId = Literal["together", "explore", "raid", "quiz"]
PetSpecies = Literal["spark", "fluff", "pip"]
HeartRateStatus = Literal["valid", "warming_up", "no_contact", "invalid_signal"]
ClockSource = Literal["phone_server_anchor", "unsynced", "device_rtc"]


def level_for_xp(lifetime_xp: int) -> int:
    """Level rule from docs/PROJECT_SPEC.md: 1 + floor(lifetime_xp / 100)."""
    return 1 + lifetime_xp // 100


class ErrorBody(BaseModel):
    code: str
    message: str
    fields: list[str] | None = None


class ErrorEnvelope(BaseModel):
    error: ErrorBody


# --- Auth / user ---


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class UserSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    display_name: str
    points: int
    lifetime_xp: int
    level: int


def user_summary(user) -> UserSummary:
    return UserSummary(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        points=user.points_balance,
        lifetime_xp=user.lifetime_xp,
        level=level_for_xp(user.lifetime_xp),
    )


class LoginOut(BaseModel):
    user: UserSummary
    token: str
    csrf_token: str
    expires_at: datetime


class DeviceSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    firmware_alias: int
    claimed_at: datetime | None = None


class PartnerSummary(BaseModel):
    id: uuid.UUID
    display_name: str
    level: int
    location_sharing: bool


class MeOut(BaseModel):
    user: UserSummary
    partner: PartnerSummary | None = None
    device: DeviceSummary | None = None
    pet: "PetSummary | None" = None


# --- Pet (v2) ---


class PetSummary(BaseModel):
    """Server mirror of the wearable-owned pet. XP/level are authoritative
    here; species/name/needs live on the wearable and are mirrored."""

    species: PetSpecies | None = None
    name: str | None = None
    level: int
    lifetime_xp: int
    evolution_stage: int  # 1 baby, 2 teen (>=100 XP), 3 adult (>=300 XP)
    care_streak: int = 0
    cared_today: bool = False
    last_care_date: str | None = None  # YYYY-MM-DD


def pet_stage_for_xp(lifetime_xp: int) -> int:
    """Fork-compatible evolution thresholds (pet_store.pet_stage)."""
    if lifetime_xp >= 300:
        return 3
    if lifetime_xp >= 100:
        return 2
    return 1


class PetUpdateIn(BaseModel):
    species: PetSpecies
    name: str = Field(min_length=1, max_length=8, pattern=r"^[A-Za-z0-9 ]+$")


class PetCareIn(BaseModel):
    # The wearable performs care locally; this claims the day's XP grant.
    # Idempotency is server-derived (care:{user}:{date}), not client-supplied.
    date: str = Field(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")


# --- Landmarks / raid (v2) ---


class LandmarkOut(BaseModel):
    id: str
    name: str
    latitude: float
    longitude: float
    radius_m: float


class LandmarksOut(BaseModel):
    landmarks: list[LandmarkOut]


class RaidOutcomeIn(BaseModel):
    outcome: Literal["win", "lose"]
    fight_started_at: datetime
    fight_ended_at: datetime
    command_id: uuid.UUID


class BindIn(BaseModel):
    pairing_code: str = Field(min_length=4, max_length=128)


class BindOut(BaseModel):
    device: DeviceSummary


class LocationSharingIn(BaseModel):
    enabled: bool


# --- Discovery profiles / settings / results (docs/DISCOVERY_PLAN.md) ---

InterestTag = Literal[
    "gaming", "music", "fitness", "food", "movies", "travel", "reading", "outdoors"
]


class DiscoveryProfileIn(BaseModel):
    display_name: str = Field(min_length=1, max_length=64)
    age: int = Field(ge=18, le=99)
    pref_min_age: int = Field(ge=18, le=99)
    pref_max_age: int = Field(ge=18, le=99)
    interests: list[InterestTag] = Field(min_length=1, max_length=8)
    radius_m: int = Field(ge=100, le=5000)

    @model_validator(mode="after")
    def check_age_order(self) -> "DiscoveryProfileIn":
        if self.pref_min_age > self.pref_max_age:
            raise ValueError("pref_min_age must be <= pref_max_age")
        if len(set(self.interests)) != len(self.interests):
            raise ValueError("interests must not contain duplicates")
        return self


class DiscoverySettingsIn(BaseModel):
    """Separate opt-in switches; both off by default, independent of profile."""

    bluetooth_enabled: bool
    gps_enabled: bool


class DiscoveryProfileOut(BaseModel):
    display_name: str
    age: int | None = None
    pref_min_age: int | None = None
    pref_max_age: int | None = None
    interests: list[str]
    radius_m: int
    bluetooth_enabled: bool
    gps_enabled: bool
    complete: bool


class DiscoveryTokenOut(BaseModel):
    token_value: int = Field(ge=0, le=65535)
    device_id: uuid.UUID


class ObservationIn(BaseModel):
    token: int = Field(ge=0, le=65535)
    captured_at: datetime


class ObservationBatchIn(BaseModel):
    schema_version: Literal[1]
    observations: list[ObservationIn] = Field(min_length=1)

    @model_validator(mode="after")
    def check_limit(self) -> "ObservationBatchIn":
        from app.config import get_settings

        limit = get_settings().telemetry_batch_limit
        if len(self.observations) > limit:
            raise ValueError(f"batch exceeds limit of {limit} observations")
        identities = {(o.token, o.captured_at) for o in self.observations}
        if len(identities) != len(self.observations):
            raise ValueError("duplicate (token, captured_at) inside batch")
        return self


class ObservationAckOut(BaseModel):
    accepted: int
    duplicates: int


class NoticeOut(BaseModel):
    code: str
    message: str
    age_seconds: int | None = None


class BluetoothSourceOut(BaseModel):
    label: str
    observed_at: datetime


class GpsSourceOut(BaseModel):
    distance_m: int
    freshness: Literal["fresh", "last_known"]
    my_age_seconds: int | None = None
    their_age_seconds: int | None = None
    labels: list[str]


class DiscoveryResultOut(BaseModel):
    user_id: uuid.UUID
    display_name: str
    shared_interests: list[str]
    shared_count: int
    sources: list[Literal["bluetooth", "gps"]]
    bluetooth: BluetoothSourceOut | None = None
    gps: GpsSourceOut | None = None


class DiscoveryOut(BaseModel):
    generated_at: datetime
    position_state: Literal["fresh", "last_known", "expired", "missing"]
    notices: list[NoticeOut]
    results: list[DiscoveryResultOut]


# --- Invitations / partnership ---


class InvitationCreateIn(BaseModel):
    to_user_id: uuid.UUID


class InvitationOut(BaseModel):
    id: uuid.UUID
    from_user_id: uuid.UUID
    from_name: str
    to_user_id: uuid.UUID
    to_name: str
    status: str
    created_at: datetime
    expires_at: datetime
    responded_at: datetime | None = None


class InvitationsOut(BaseModel):
    incoming: list[InvitationOut]
    outgoing: list[InvitationOut]


class PartnershipOut(BaseModel):
    id: uuid.UUID
    since: datetime
    ended_at: datetime | None = None
    ended_by: uuid.UUID | None = None
    partner: PartnerSummary | None = None


# --- Quests / sessions ---


class QuestOut(BaseModel):
    quest_id: QuestId
    name: str
    description: str
    evidence: str
    normal_duration_ms: int
    demo_duration_ms: int
    geofence_configured: bool


class QuestsOut(BaseModel):
    quests: list[QuestOut]


class SessionCreateIn(BaseModel):
    quest_id: CreatableQuestId
    demo: bool = True
    # Raid only: which seeded landmark to freeze for this session.
    landmark_id: str | None = Field(default=None, max_length=32)


class ParticipantOut(BaseModel):
    user_id: uuid.UUID
    display_name: str
    accepted: bool


class SessionOut(BaseModel):
    id: uuid.UUID
    quest_id: QuestId
    demo: bool
    state: Literal["pending", "active", "completed", "cancelled"]
    created_by: uuid.UUID
    created_at: datetime
    activated_at: datetime | None = None
    completed_at: datetime | None = None
    cancelled_at: datetime | None = None
    target_ms: int | None = None
    progress_ms: int
    participants: list[ParticipantOut]
    # Opaque session token; visible to participants only, set once active.
    # Firmware embeds it in peer heartbeats so evidence binds to this session.
    token: str | None = None
    geofence: dict | None = None
    # v2 raid: the frozen landmark and this caller's outcome report (if any).
    landmark: dict | None = None
    raid_outcome: Literal["win", "lose"] | None = None


class QuizQuestionOut(BaseModel):
    """One question as the answerer sees it: no correct index (server-scored)."""

    index: int
    text: str
    options: list[str]
    answered: bool
    choice: int | None = None


class QuizStateOut(BaseModel):
    completed: bool
    my_total: int
    my_answered: int
    partner_total: int
    partner_answered: int
    questions: list[QuizQuestionOut]


class QuizAnswerIn(BaseModel):
    question_index: int
    choice: int


class SessionsOut(BaseModel):
    sessions: list[SessionOut]


class InteractionSnapshot(BaseModel):
    session_id: uuid.UUID
    quest_id: QuestId
    version: int
    phase: str
    phase_started_at: datetime | None = None
    timing_started_at: datetime | None = None
    progress_ms: int
    target_ms: int
    completed_evidence_ms: int
    stage: Literal["start", "end"] | None = None
    own_code: str | None = None
    own_code_version: int | None = None
    own_code_expires_at: datetime | None = None
    own_code_confirmed_by_partner: bool = False
    partner_code_version: int | None = None
    partner_code_expires_at: datetime | None = None
    partner_code_confirmed_by_me: bool = False
    round_index: int = 0
    active_user_id: uuid.UUID | None = None
    prompt_kind: Literal["truth", "dare"] | None = None
    prompt_id: str | None = None
    prompt: str | None = None
    results: dict = Field(default_factory=dict)


class PinSubmitIn(BaseModel):
    stage: Literal["start", "end"]
    pin: str = Field(pattern=r"^[0-9]{4}$")
    code_version: int = Field(ge=1)
    command_id: uuid.UUID


class PinRefreshIn(BaseModel):
    stage: Literal["start", "end"]
    command_id: uuid.UUID


class InteractionChoiceIn(BaseModel):
    choice: Literal["truth", "dare"]
    command_id: uuid.UUID


class InteractionSkipIn(BaseModel):
    command_id: uuid.UUID


# --- Telemetry ---


class ClockInfo(BaseModel):
    source: ClockSource
    uncertainty_ms: int | None = Field(default=None, ge=0)


GpsSource = Literal["wearable", "phone"]


class GpsReading(BaseModel):
    valid: bool = False
    latitude: float | None = Field(default=None, ge=-90.0, le=90.0)
    longitude: float | None = Field(default=None, ge=-180.0, le=180.0)
    fix_age_ms: int | None = Field(default=None, ge=0)
    # v2: "phone" fixes are relayed by the companion app with their true age;
    # "wearable" is the legacy/default source.
    source: GpsSource = "wearable"

    @model_validator(mode="after")
    def check_consistency(self) -> "GpsReading":
        if self.valid and (self.latitude is None or self.longitude is None):
            raise ValueError("gps.valid=true requires latitude and longitude")
        if not self.valid and (self.latitude is not None or self.longitude is not None):
            raise ValueError("coordinates only allowed when gps.valid=true")
        if self.latitude is not None and math.isnan(self.latitude):
            raise ValueError("latitude must not be NaN")
        return self


class HeartRateReading(BaseModel):
    valid: bool = False
    bpm: int | None = Field(default=None, ge=20, le=255)
    status: HeartRateStatus | None = None

    @model_validator(mode="after")
    def check_consistency(self) -> "HeartRateReading":
        if self.valid:
            if self.bpm is None or self.status != "valid":
                raise ValueError("heart_rate.valid=true requires bpm and status='valid'")
        else:
            if self.bpm is not None:
                raise ValueError("bpm only allowed when heart_rate.valid=true")
            if self.status is None:
                raise ValueError("heart_rate.status is required when invalid")
        return self


class PeerObservation(BaseModel):
    observed: bool = False
    device_id: uuid.UUID | None = None
    boot_id: str | None = Field(default=None, max_length=64)
    heartbeat_sequence: int | None = Field(default=None, ge=0)
    session_token: str | None = Field(default=None, max_length=64)
    observation_age_ms: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def check_consistency(self) -> "PeerObservation":
        if self.observed:
            missing = [
                name
                for name, value in {
                    "device_id": self.device_id,
                    "boot_id": self.boot_id,
                    "heartbeat_sequence": self.heartbeat_sequence,
                    "session_token": self.session_token,
                    "observation_age_ms": self.observation_age_ms,
                }.items()
                if value is None
            ]
            if missing:
                raise ValueError(f"peer.observed=true requires {', '.join(missing)}")
        elif any(
            v is not None
            for v in (
                self.device_id,
                self.boot_id,
                self.heartbeat_sequence,
                self.session_token,
                self.observation_age_ms,
            )
        ):
            raise ValueError("peer fields only allowed when peer.observed=true")
        return self


class TelemetryRecordIn(BaseModel):
    boot_id: str = Field(min_length=1, max_length=64)
    sequence: int = Field(ge=0)
    session_id: uuid.UUID | None = None
    uptime_ms: int = Field(ge=0)
    captured_at: datetime | None = None
    clock: ClockInfo
    gps: GpsReading = Field(default_factory=GpsReading)
    heart_rate: HeartRateReading = Field(default_factory=HeartRateReading)
    peer: PeerObservation = Field(default_factory=PeerObservation)

    @field_validator("boot_id")
    @classmethod
    def strip_boot_id(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("boot_id must not be blank")
        return v


class TelemetryBatchIn(BaseModel):
    schema_version: Literal[1]
    device_id: uuid.UUID
    records: list[TelemetryRecordIn] = Field(min_length=1)

    @model_validator(mode="after")
    def check_limit(self) -> "TelemetryBatchIn":
        from app.config import get_settings

        limit = get_settings().telemetry_batch_limit
        if len(self.records) > limit:
            raise ValueError(f"batch exceeds limit of {limit} records")
        identities = {(r.boot_id, r.sequence) for r in self.records}
        if len(identities) != len(self.records):
            raise ValueError("duplicate (boot_id, sequence) inside batch")
        return self


class AcceptedIdentity(BaseModel):
    boot_id: str
    sequence: int


class TelemetryAckOut(BaseModel):
    server_time: datetime
    accepted: list[AcceptedIdentity]
    duplicates: list[AcceptedIdentity]
    state_version: int


class ServerTimeOut(BaseModel):
    server_time: datetime
    unix_ms: int


# --- Rewards / purchases / transactions ---


class RewardOut(BaseModel):
    id: str
    name: str
    description: str
    price: int
    owned: bool


class RewardsOut(BaseModel):
    points: int
    rewards: list[RewardOut]


class PurchaseIn(BaseModel):
    reward_id: str


class PurchaseOut(BaseModel):
    reward_id: str
    price: int
    balance_after: int
    owned: bool


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    delta: int
    xp_delta: int
    balance_after: int
    session_id: uuid.UUID | None = None
    reward_id: str | None = None
    created_at: datetime


class TransactionsOut(BaseModel):
    transactions: list[TransactionOut]


# --- Device state relay / SSE ---


class PartnerPosition(BaseModel):
    latitude: float
    longitude: float
    captured_at: datetime | None = None
    age_ms: int | None = None
    sharing_enabled: bool


class SessionBrief(BaseModel):
    session_id: uuid.UUID
    quest_id: QuestId
    demo: bool
    state: str
    token: str | None
    target_ms: int | None
    progress_ms: int
    interaction: InteractionSnapshot | None = None


class CompletionEvent(BaseModel):
    completion_event_id: str
    session_id: uuid.UUID
    interaction: InteractionSnapshot | None = None


class DeviceStateOut(BaseModel):
    state_version: int
    session: SessionBrief | None = None
    partner_alias: int | None = None
    # Partner's device UUID so the phone can resolve peer observations in
    # relayed telemetry (needed whenever the pair is partnered).
    partner_device_id: uuid.UUID | None = None
    partner_position: PartnerPosition | None = None
    partner_distance_m: float | None = None
    completion: CompletionEvent | None = None
    server_time: datetime
