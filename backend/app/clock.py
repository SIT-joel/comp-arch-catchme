"""Injectable clock.

Discovery freshness, observation expiry and invitation expiry are all
evaluated against a single clock seam so tests can pin time exactly at the
boundary seconds (30/31, 900/901, 15/16) with a controlled value instead
of sleeping or patching datetime everywhere.
"""

from datetime import datetime, timezone


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
