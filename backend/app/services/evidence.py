"""Pure evidence-interval mathematics for quest scoring.

Rules implemented here come directly from docs/PROJECT_SPEC.md:

- Intervals are evaluated on capture time, never HTTP arrival time.
- Peer presence needs successive verified direct peer observations at most
  10 s apart; gaps are never bridged by interpolation.
- The two participants' evidence is intersected: both must have observed
  each other for a moment to count.
- Overlapping intervals count once (union before summing).
- Explore: both GPS fixes valid and inside the geofence (inclusive radius),
  and no fix older than 10 s at the evaluated time.
- Heart challenge: valid BPM/contact from both devices, a valid report is
  carried at most 3 s.
- Records with excessive clock uncertainty (> 2 s) or no capture time never
  score; they are retained as diagnostics only.

All functions are pure and timezone-safe: inputs must be timezone-aware
datetimes in a consistent zone (UTC expected).
"""

import math
from dataclasses import dataclass
from datetime import datetime, timedelta

Interval = tuple[datetime, datetime]

EARTH_RADIUS_M = 6_371_008.8


# --- Interval primitives ---


def merge(intervals: list[Interval]) -> list[Interval]:
    """Union: sorted, non-overlapping, touching intervals coalesced."""
    cleaned = sorted((s, e) for s, e in intervals if e > s)
    out: list[Interval] = []
    for start, end in cleaned:
        if out and start <= out[-1][1]:
            if end > out[-1][1]:
                out[-1] = (out[-1][0], end)
        else:
            out.append((start, end))
    return out


def intersect(a: list[Interval], b: list[Interval]) -> list[Interval]:
    """Intersection of two merged interval lists."""
    out: list[Interval] = []
    i = j = 0
    while i < len(a) and j < len(b):
        start = max(a[i][0], b[j][0])
        end = min(a[i][1], b[j][1])
        if start < end:
            out.append((start, end))
        if a[i][1] <= b[j][1]:
            i += 1
        else:
            j += 1
    return out


def total_ms(intervals: list[Interval]) -> int:
    return sum(int((e - s).total_seconds() * 1000) for s, e in intervals)


def gap_intervals(points: list[datetime], max_gap_ms: int) -> list[Interval]:
    """Presence spans built from successive points whose gap is at most
    max_gap_ms. Each counted span is [t_i, t_{i+1}]; a larger gap splits the
    timeline and contributes no time (never bridged by interpolation).
    Isolated points produce zero-measure intervals."""
    pts = sorted(points)
    max_gap = timedelta(milliseconds=max_gap_ms)
    out: list[Interval] = []
    for p in pts:
        if out and p - out[-1][1] <= max_gap:
            out[-1] = (out[-1][0], p)
        else:
            out.append((p, p))
    return out


def window_coverage(points: list[datetime], window_ms: int) -> list[Interval]:
    """Each point covers [t, t + window_ms]; union of all windows."""
    w = timedelta(milliseconds=window_ms)
    return merge([(p, p + w) for p in points])


def completion_instant(intervals: list[Interval], target_ms: int) -> datetime | None:
    """Earliest instant at which cumulative merged duration reaches target_ms."""
    accumulated_ms = 0
    for start, end in merge(intervals):
        accumulated_ms += int((end - start).total_seconds() * 1000)
        if accumulated_ms >= target_ms:
            overrun = accumulated_ms - target_ms
            return end - timedelta(milliseconds=overrun)
    return None


# --- Distance ---


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


# --- Per-participant record views ---


@dataclass(frozen=True)
class PeerObservationPoint:
    """One verified direct observation of the partner, on the observer's clock."""

    observed_at: datetime  # capture time minus observation age
    peer_boot_id: str
    heartbeat_sequence: int


@dataclass(frozen=True)
class GpsPoint:
    fix_time: datetime  # capture time minus fix age
    latitude: float
    longitude: float


def peer_observation_points(
    records: list[dict],
    expected_peer_device_id,
    session_token: str,
    clock_uncertainty_max_ms: int,
    not_before: datetime | None = None,
) -> list[PeerObservationPoint]:
    """Filter a participant's records down to verified peer observations.

    - Record must carry a capture time and acceptable clock uncertainty.
    - The observed device must be the expected partner and carry the active
      session token (evidence binds to the session).
    - Repeated or stale heartbeat counters are rejected: strictly increasing
      per peer boot, evaluated in capture order.
    """
    eligible: list[PeerObservationPoint] = []
    for r in records:
        captured_at = r["captured_at"]
        uncertainty = r["clock_uncertainty_ms"]
        if captured_at is None:
            continue
        if uncertainty is None or uncertainty > clock_uncertainty_max_ms:
            continue
        if not r["peer_observed"]:
            continue
        if r["peer_device_id"] != expected_peer_device_id:
            continue
        if r["peer_session_token"] != session_token:
            continue
        age = r["peer_observation_age_ms"] or 0
        observed_at = captured_at - timedelta(milliseconds=age)
        if not_before is not None and observed_at < not_before:
            continue
        eligible.append(
            PeerObservationPoint(
                observed_at=observed_at,
                peer_boot_id=r["peer_boot_id"] or "",
                heartbeat_sequence=r["peer_heartbeat_sequence"] or 0,
            )
        )

    eligible.sort(key=lambda p: (p.observed_at, p.heartbeat_sequence))

    last_by_boot: dict[str, int] = {}
    result: list[PeerObservationPoint] = []
    for point in eligible:
        if point.peer_boot_id in last_by_boot and point.heartbeat_sequence <= last_by_boot[point.peer_boot_id]:
            continue  # repeated/stale counter: not new evidence
        last_by_boot[point.peer_boot_id] = point.heartbeat_sequence
        result.append(point)
    return result


def gps_points(
    records: list[dict],
    clock_uncertainty_max_ms: int,
) -> list[GpsPoint]:
    out: list[GpsPoint] = []
    for r in records:
        if not r["gps_valid"]:
            continue
        captured_at = r["captured_at"]
        uncertainty = r["clock_uncertainty_ms"]
        if captured_at is None:
            continue
        if uncertainty is None or uncertainty > clock_uncertainty_max_ms:
            continue
        age = r["gps_fix_age_ms"] or 0
        out.append(
            GpsPoint(
                fix_time=captured_at - timedelta(milliseconds=age),
                latitude=r["gps_lat"],
                longitude=r["gps_lon"],
            )
        )
    return out


# --- Quest evaluators ---
# v2: the heart_challenge evaluator (heart_rate_points/HeartRatePoint/
# heart_challenge_intervals) was removed with the quest. window_coverage
# remains a generic interval helper.


def peer_presence_intervals(
    records_a: list[dict],
    records_b: list[dict],
    device_a,
    device_b,
    session_token: str,
    peer_gap_max_ms: int,
    clock_uncertainty_max_ms: int,
    not_before: datetime | None = None,
) -> list[Interval]:
    """Both participants' views of direct presence, intersected.

    records_a are captured by user A's device; each must report observing
    device B (and vice versa) for a moment to count. Each side's presence
    spans follow the <=10 s successive-observation rule; the awarded time is
    the intersection of the two sides' spans.
    """
    points_a = peer_observation_points(records_a, device_b, session_token, clock_uncertainty_max_ms, not_before)
    points_b = peer_observation_points(records_b, device_a, session_token, clock_uncertainty_max_ms, not_before)

    spans_a = gap_intervals([p.observed_at for p in points_a], peer_gap_max_ms)
    spans_b = gap_intervals([p.observed_at for p in points_b], peer_gap_max_ms)
    return intersect(spans_a, spans_b)


def together_intervals(
    records_a: list[dict],
    records_b: list[dict],
    *,
    device_a,
    device_b,
    session_token: str,
    peer_gap_max_ms: int,
    clock_uncertainty_max_ms: int,
    not_before: datetime | None = None,
) -> list[Interval]:
    return peer_presence_intervals(
        records_a, records_b, device_a, device_b, session_token,
        peer_gap_max_ms, clock_uncertainty_max_ms, not_before,
    )


def explore_intervals(
    records_a: list[dict],
    records_b: list[dict],
    *,
    device_a,
    device_b,
    session_token: str,
    peer_gap_max_ms: int,
    clock_uncertainty_max_ms: int,
    gps_stale_max_ms: int,
    geofence_lat: float,
    geofence_lon: float,
    geofence_radius_m: float,
) -> list[Interval]:
    peer = peer_presence_intervals(
        records_a, records_b, device_a, device_b, session_token,
        peer_gap_max_ms, clock_uncertainty_max_ms,
    )
    coverage_a = merge(
        [
            (p.fix_time, p.fix_time + timedelta(milliseconds=gps_stale_max_ms))
            for p in gps_points(records_a, clock_uncertainty_max_ms)
            if haversine_m(p.latitude, p.longitude, geofence_lat, geofence_lon)
            <= geofence_radius_m
        ]
    )
    coverage_b = merge(
        [
            (p.fix_time, p.fix_time + timedelta(milliseconds=gps_stale_max_ms))
            for p in gps_points(records_b, clock_uncertainty_max_ms)
            if haversine_m(p.latitude, p.longitude, geofence_lat, geofence_lon)
            <= geofence_radius_m
        ]
    )
    both = intersect(coverage_a, coverage_b)
    return intersect(peer, both)

