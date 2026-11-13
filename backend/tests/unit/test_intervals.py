"""Unit tests for the pure interval/evidence mathematics.

These encode the numeric rules from docs/PROJECT_SPEC.md and the boundary
cases in docs/TEST_PLAN.md. No database involved.
"""

import uuid
from datetime import datetime, timedelta, timezone

from app.services import evidence

T0 = datetime(2026, 11, 1, 12, 0, 0, tzinfo=timezone.utc)
PEER_GAP = 10_000
MAX_UNCERTAINTY = 2_000
GPS_STALE = 10_000
# v2: heart_challenge removed (with HR_CARRY); its carry-window tests went with it.

DEVICE_A = uuid.uuid4()
DEVICE_B = uuid.uuid4()
TOKEN = "opaque-demo-session-token"


def at(seconds: float) -> datetime:
    return T0 + timedelta(milliseconds=seconds * 1000)


def record(
    seq: int,
    captured_at: datetime | None,
    *,
    clock_uncertainty: int | None = 500,
    peer_observed: bool = True,
    peer_device=DEVICE_B,
    peer_boot: str = "device-b-17",
    peer_heartbeat: int | None = None,
    peer_token: str | None = TOKEN,
    observation_age: int | None = 0,
    gps_valid: bool = False,
    gps_lat: float | None = None,
    gps_lon: float | None = None,
    fix_age: int | None = None,
    hr_valid: bool = False,
    bpm: int | None = None,
    hr_status: str | None = None,
) -> dict:
    return {
        "captured_at": captured_at,
        "clock_uncertainty_ms": clock_uncertainty,
        "gps_valid": gps_valid,
        "gps_lat": gps_lat,
        "gps_lon": gps_lon,
        "gps_fix_age_ms": fix_age,
        "hr_valid": hr_valid,
        "bpm": bpm,
        "hr_status": hr_status,
        "peer_observed": peer_observed,
        "peer_device_id": peer_device,
        "peer_boot_id": peer_boot,
        "peer_heartbeat_sequence": peer_heartbeat,
        "peer_session_token": peer_token,
        "peer_observation_age_ms": observation_age,
    }


# --- interval primitives ---


def test_merge_union_and_coalesce():
    merged = evidence.merge([(at(0), at(5)), (at(5), at(10)), (at(20), at(25))])
    assert merged == [(at(0), at(10)), (at(20), at(25))]


def test_intersect_basic():
    a = [(at(0), at(10)), (at(20), at(30))]
    b = [(at(5), at(25))]
    assert evidence.intersect(a, b) == [(at(5), at(10)), (at(20), at(25))]


def test_completion_instant_walks_merged_intervals():
    intervals = [(at(0), at(4)), (at(10), at(20))]
    instant = evidence.completion_instant(intervals, 10_000)
    assert instant == at(16)  # 4 s in first span, 6 s into second


def test_completion_instant_not_reached():
    assert evidence.completion_instant([(at(0), at(4))], 10_000) is None


# --- haversine boundary: 49/50/51 m from geofence center ---

GEOFENCE = (35.0000000, 135.0000000)


def offset_meters(lat: float, lon: float, meters: float) -> tuple[float, float]:
    """Move 'meters' north-east along latitude from the given point."""
    dlat = meters / 111_320.0
    return lat + dlat, lon


def test_haversine_boundary_49_50_51_metres():
    lat49, lon = offset_meters(*GEOFENCE, 49)
    lat50, _ = offset_meters(*GEOFENCE, 50)
    lat51, _ = offset_meters(*GEOFENCE, 51)
    center = GEOFENCE
    d49 = evidence.haversine_m(center[0], center[1], lat49, lon)
    d50 = evidence.haversine_m(center[0], center[1], lat50, lon)
    d51 = evidence.haversine_m(center[0], center[1], lat51, lon)
    assert d49 < 50
    assert d50 >= 49.9 and d50 <= 50.1  # configured boundary is inclusive
    assert d51 > 50


# --- together: 9/10/11 second gaps (TEST_PLAN 'Together' row) ---


def mutual_observations(gap_first: float, gap_second: float):
    """A observes B at 0, g1, g1+g2 (seconds); B observes A at the same times."""
    times = [0.0, gap_first, gap_first + gap_second]
    records_a = [record(i, at(t), peer_device=DEVICE_B, peer_heartbeat=i + 1) for i, t in enumerate(times)]
    records_b = [
        record(i, at(t), peer_device=DEVICE_A, peer_boot="device-a-42", peer_heartbeat=i + 1)
        for i, t in enumerate(times)
    ]
    return records_a, records_b


def together_ms(records_a, records_b):
    intervals = evidence.together_intervals(
        records_a, records_b,
        device_a=DEVICE_A, device_b=DEVICE_B, session_token=TOKEN,
        peer_gap_max_ms=PEER_GAP, clock_uncertainty_max_ms=MAX_UNCERTAINTY,
    )
    return evidence.total_ms(intervals)


def test_together_gap_9s_counts():
    a, b = mutual_observations(9, 9)
    assert together_ms(a, b) == 18_000


def test_together_gap_10s_counts_at_boundary():
    a, b = mutual_observations(10, 10)
    assert together_ms(a, b) == 20_000


def test_together_gap_11s_does_not_count():
    a, b = mutual_observations(11, 0)
    # Observations at 0 and 11 s: the gap contributes no time; final point is isolated.
    assert together_ms(a, b) == 0


def test_together_gap_splits_interval():
    a, b = mutual_observations(5, 15)  # spans [0,5] and nothing after gap
    assert together_ms(a, b) == 5_000


def test_one_sided_evidence_counts_nothing():
    a, _ = mutual_observations(2, 2)
    b = [record(i, at(t), peer_observed=False) for i, t in enumerate([0, 2, 4])]
    assert together_ms(a, b) == 0


def test_wrong_session_token_rejected():
    a, b = mutual_observations(2, 2)
    for r in a:
        r["peer_session_token"] = "other-token"
    assert together_ms(a, b) == 0


def test_wrong_peer_device_rejected():
    a, b = mutual_observations(2, 2)
    for r in a:
        r["peer_device_id"] = uuid.uuid4()
    assert together_ms(a, b) == 0


def test_duplicate_heartbeat_counters_are_not_new_evidence():
    # Same counter repeated: only the first observation counts.
    times = [0, 2, 4, 6, 8]
    a = [record(i, at(t), peer_heartbeat=1) for i, t in enumerate(times)]
    b = [
        record(i, at(t), peer_device=DEVICE_A, peer_boot="device-a-42", peer_heartbeat=i + 1)
        for i, t in enumerate(times)
    ]
    assert together_ms(a, b) == 0  # A's deduped view has one isolated point


def test_uncertain_clock_excluded():
    a, b = mutual_observations(2, 2)
    for r in a:
        r["clock_uncertainty_ms"] = 2_001
    assert together_ms(a, b) == 0


def test_missing_capture_time_excluded():
    a, b = mutual_observations(2, 2)
    for r in a:
        r["captured_at"] = None
    assert together_ms(a, b) == 0


def test_repeated_old_observation_is_not_new_evidence():
    # Telemetry repeats one old observation with growing age; it must not
    # become fresh evidence (observation time preserved, not capture time).
    a = [
        record(0, at(100), peer_heartbeat=7, observation_age=0),
        record(1, at(102), peer_heartbeat=7, observation_age=2_000),
        record(2, at(104), peer_heartbeat=7, observation_age=4_000),
    ]
    b = [
        record(i, at(t), peer_device=DEVICE_A, peer_boot="device-a-42", peer_heartbeat=i + 1)
        for i, t in enumerate([100, 102, 104])
    ]
    assert together_ms(a, b) == 0  # single deduped observation point: no span


# --- explore: GPS age and radius boundaries ---


def explore_ms(records_a, records_b):
    intervals = evidence.explore_intervals(
        records_a, records_b,
        device_a=DEVICE_A, device_b=DEVICE_B, session_token=TOKEN,
        peer_gap_max_ms=PEER_GAP, clock_uncertainty_max_ms=MAX_UNCERTAINTY,
        gps_stale_max_ms=GPS_STALE,
        geofence_lat=GEOFENCE[0], geofence_lon=GEOFENCE[1], geofence_radius_m=50,
    )
    return evidence.total_ms(intervals)


def inside_gps_record(seq, t, fix_age=0):
    lat, lon = offset_meters(*GEOFENCE, 20)
    return record(seq, at(t), gps_valid=True, gps_lat=lat, gps_lon=lon, fix_age=fix_age)


def test_explore_passes_with_valid_mutual_fixes():
    a = [record(i, at(t), peer_heartbeat=i + 1) | {"gps_valid": True, "gps_lat": offset_meters(*GEOFENCE, 20)[0], "gps_lon": offset_meters(*GEOFENCE, 20)[1], "gps_fix_age_ms": 0} for i, t in enumerate([0, 2, 4, 6])]
    b = [
        record(i, at(t), peer_device=DEVICE_A, peer_boot="device-a-42", peer_heartbeat=i + 1)
        | {"gps_valid": True, "gps_lat": offset_meters(*GEOFENCE, 10)[0], "gps_lon": offset_meters(*GEOFENCE, 10)[1], "gps_fix_age_ms": 0}
        for i, t in enumerate([0, 2, 4, 6])
    ]
    assert explore_ms(a, b) == 6_000


def test_explore_one_partner_outside_geofence_pauses():
    lat_in, lon_in = offset_meters(*GEOFENCE, 20)
    lat_out, lon_out = offset_meters(*GEOFENCE, 80)
    # Dense mutual peer observations 0..20 s. B's fixes are inside the fence
    # until t=4 and outside afterwards; A stays inside throughout.
    a = [
        record(i, at(t), peer_heartbeat=i + 1,
               gps_valid=True, gps_lat=lat_in, gps_lon=lon_in, fix_age=0)
        for i, t in enumerate([0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20])
    ]
    b = [
        record(i, at(t), peer_device=DEVICE_A, peer_boot="device-a-42", peer_heartbeat=i + 1,
                gps_valid=True,
                gps_lat=lat_in if t <= 4 else lat_out,
                gps_lon=lon_in if t <= 4 else lon_out,
                fix_age=0)
        for i, t in enumerate([0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20])
    ]
    # B's last inside fix is at t=4 and stays usable until it is 10 s old
    # ("no older than 10 seconds at the evaluated time"): coverage B = [0, 14].
    # Peer spans are [0, 20] on both sides; A is covered throughout.
    # Total = [0, 14] = 14 s, then progress pauses — B's outside fixes never
    # extend the in-fence coverage.
    assert explore_ms(a, b) == 14_000


def test_explore_stale_fix_expires_after_10s():
    # Single fresh fix pair at t=0 with fix_age 9s covers [fix, fix+10s]
    # but peer spans need successive observations anyway.
    lat, lon = offset_meters(*GEOFENCE, 20)
    a = [record(0, at(0), peer_heartbeat=1, gps_valid=True, gps_lat=lat, gps_lon=lon, fix_age=9_000)]
    b = [record(0, at(0), peer_device=DEVICE_A, peer_boot="a", peer_heartbeat=1,
                gps_valid=True, gps_lat=lat, gps_lon=lon, fix_age=9_000)]
    # Only one observation per side: no peer span -> no credit regardless of GPS.
    assert explore_ms(a, b) == 0


def test_explore_boundary_50m_is_inclusive():
    lat, lon = offset_meters(*GEOFENCE, 49.9)
    times = [0, 2, 4]
    a = [record(i, at(t), peer_heartbeat=i + 1, gps_valid=True, gps_lat=lat, gps_lon=lon, fix_age=0) for i, t in enumerate(times)]
    b = [record(i, at(t), peer_device=DEVICE_A, peer_boot="a", peer_heartbeat=i + 1,
                gps_valid=True, gps_lat=lat, gps_lon=lon, fix_age=0) for i, t in enumerate(times)]
    assert explore_ms(a, b) == 4_000
