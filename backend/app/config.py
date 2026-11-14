"""Application settings loaded from environment variables (CM_ prefix)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CM_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://catch_me:catch_me@127.0.0.1:5432/catch_me"

    # Auth/session
    session_ttl_hours: int = 24 * 7
    cookie_secure: bool = False  # must be True behind HTTPS in deployment

    # Quest durations (milliseconds); defaults from docs/PROJECT_SPEC.md
    quest_together_normal_ms: int = 600_000
    quest_together_demo_ms: int = 30_000
    quest_explore_normal_ms: int = 120_000
    quest_explore_demo_ms: int = 20_000
    # v2: heart_challenge removed. quest_heart_* settings retained only so
    # old env files keep loading; they are unused.
    quest_heart_normal_ms: int = 30_000
    quest_heart_demo_ms: int = 30_000
    # Raid: estimated fight duration for display; completion is outcome-driven.
    quest_raid_normal_ms: int = 180_000
    quest_raid_demo_ms: int = 60_000

    # Explore geofence: no default real-world destination is invented.
    geofence_lat: float | None = None
    geofence_lon: float | None = None
    geofence_radius_m: float = 50.0

    # Raid landmark gate (v2): both participants' phone fixes within this
    # radius of the session's landmark, fixes no older than this at check.
    raid_radius_m: float = 50.0
    raid_fix_max_age_ms: int = 30_000

    # Pet daily care (v2): +10 XP at most once per user per calendar day.
    pet_care_xp: int = 10

    # Evidence rules from docs/PROJECT_SPEC.md
    peer_gap_max_ms: int = 10_000
    gps_stale_max_ms: int = 10_000
    heart_rate_carry_max_ms: int = 3_000
    clock_uncertainty_max_ms: int = 2_000

    telemetry_batch_limit: int = 100

    # --- Nearby discovery (docs/DISCOVERY_PLAN.md) ---
    # GPS last-known classification (evaluated on actual fix time):
    # 0..fresh inclusive = fresh; fresh..expiry inclusive = last_known;
    # beyond expiry = expired (no geographic results).
    discovery_fresh_seconds: int = 30
    discovery_expiry_seconds: int = 900
    # A BLE observation contributes presence for this long after its
    # original capture time; delayed retransmissions cannot revive it.
    discovery_ble_observation_seconds: int = 15
    # Partner invitation validity window.
    invitation_expiry_seconds: int = 300
    # Radius default; accepted range is enforced by DB constraints (100-5000).
    discovery_radius_default_m: int = 500

    def quest_catalog(self) -> list[dict]:
        return [
            {
                "quest_id": "together",
                "name": "Together Time",
                "description": "Stay within direct Bluetooth range of each other.",
                "evidence": "direct peer presence on both devices",
                "normal_duration_ms": self.quest_together_normal_ms,
                "demo_duration_ms": self.quest_together_demo_ms,
            },
            {
                "quest_id": "explore",
                "name": "Outdoor Visit",
                "description": "Stay close to each other inside the configured outdoor geofence.",
                "evidence": "direct peer presence plus both valid wearable GPS fixes inside the geofence",
                "normal_duration_ms": self.quest_explore_normal_ms,
                "demo_duration_ms": self.quest_explore_demo_ms,
            },
            {
                "quest_id": "quiz",
                "name": "Know Your Partner",
                "description": "Answer multiple-choice questions about your partner's profile - ask them to learn the answers, then pick on your wearable.",
                "evidence": "every quiz question answered by its designated answerer through the authenticated phone",
                "normal_duration_ms": self.quest_raid_normal_ms,
                "demo_duration_ms": self.quest_raid_demo_ms,
            },
        ]
        # (The "raid" quest was removed 14 Nov by user decision: the
        # board-to-board sustained link drops at 23-30 s — a hardware wall
        # documented across every configuration since 12 Nov. Legacy raid
        # sessions stay readable; raid creation is rejected as an unknown
        # quest. The demo focus is proximity, quests, leveling.)

    def quest_config(self, quest_id: str) -> dict | None:
        return next((q for q in self.quest_catalog() if q["quest_id"] == quest_id), None)

    def geofence_configured(self) -> bool:
        return self.geofence_lat is not None and self.geofence_lon is not None


@lru_cache
def get_settings() -> Settings:
    return Settings()
