# System architecture

## Planned quest interaction layer (30 October)

Extend existing server-authoritative sessions with the phase machine in [QUEST_INTERACTION_PLAN.md](QUEST_INTERACTION_PLAN.md). Together accumulates 30 demo seconds only after both wearable start-code entries and awards only after both end-code entries. Keep Your Cool uses baseline/selection/round phases with valid sensor/proximity evidence. Keep the existing telemetry evaluator but gate its progress and award transitions by phase.

Firmware owns four-button input/rendering, Android relays idempotent commands, and the server validates codes, choices, phases, evidence timing, and final rewards. A BLE transmission alone never confirms an action. Protect current data with additive migration/versioned legacy behavior. This is planned work, not a statement that the interaction layer already exists.

## Discovery extension (planned, 26 October)

Implement [DISCOVERY_PLAN.md](DISCOVERY_PLAN.md) on top of the existing application. Add profile/settings, a durable last-known wearable GPS fix per device, recent direct BLE observations, and partner invitations. The server merges compatible candidates while Android relays observations and results. Phone location is prohibited.

Cache actual GPS fix time, not upload receipt time. Preserve the newest trustworthy fix through invalid readings/restarts; fresh <=30 seconds, last-known <=900 seconds, expired afterward. Discovery reads this cache; the quest evaluator continues reading its original fresh sensor evidence.

Extend the established time-division BLE scheduler and bounded buffers for multi-user discovery while unpaired. Do not restart concurrent-radio experimentation by default. Add active partnership memberships with unique user IDs across both pairing sides; preserve historical pairs and existing seeded memberships during migration.

Profiles and invitations appear in Android/web; TinyScreen+ receives up to three compact results. Poll discovery every five seconds while visible to expire results even without new SSE events. See the discovery plan for opt-in, data exposure, and freshness rules.

## Data flow

```text
Wearable A <-- direct BLE peer evidence --> Wearable B
    | BLE telemetry/control                    | BLE telemetry/control
Android A                                  Android B
    | HTTPS                                    | HTTPS
    +---------------- FastAPI -----------------+
                         |
                     PostgreSQL
                         |
                React web app via API/SSE
```

The diagram shows logical links. Recorded experiments require scheduled scan/phone windows on the current hardware; preserve the implemented time-division scheduler. Complete two-device timing and stability verification remains necessary.

## Wearable firmware

Use Arduino C++ with small modules for board configuration, GPS parsing, pulse acquisition, peer protocol, phone transport, flash queue, display, and buzzer. Keep the main loop responsive using state machines and elapsed-time scheduling. Do not block acquisition while waiting for a connection or fix.

- Sample raw pulse data at the manufacturer algorithm's required cadence. Publish computed BPM/validity approximately once per second; do not reduce the acquisition rate to the telemetry rate.
- Parse GPS continuously and use available fixes, typically at the board's configured update cadence.
- Target a direct peer heartbeat every 2 seconds when links permit; the acceptance ceiling is 10 seconds between countable observations.
- Target local BPM display refresh once per second when a valid estimate is available. Phone/web updates are best effort, with measured freshness shown.
- Use compact bounded records and buffers; avoid unbounded strings or storing whole sessions in RAM.
- Use SPI transactions for shared external devices and confirm the display driver's interaction with buses/timers.
- Store unsent records in flash and erase/reuse only acknowledged storage. Report queue-full state and suspend evidence collection that cannot be retained rather than pretending it was saved.
- Reconstruct the queue after reboot using integrity checks. Only remove records after a server acknowledgement is relayed through the phone.

## Android companion

Native Kotlin, Jetpack Compose, Android BLE APIs, HTTPS API client, and a persistent local upload queue. Use Room for queue storage. Choose supported SDK/build versions after inspecting the target phones, and record the tested OS versions.

- Each phone owns one wearable connection and one user account.
- Request applicable Bluetooth runtime permissions for the OS version. The initial demo keeps the app open; locked-screen continuity is out of scope.
- Reconnect after expected firmware radio scheduling transitions and distinguish these from long outages.
- Reassemble BLE messages, persist before uploading, and retransmit without generating new record identities.
- Relay server-confirmed acknowledgements, session metadata, and partner state back to the wearable.
- Obtain a server UTC time anchor and send it to the device; report uncertainty and loss of time synchronization.
- Record capture time and receive time separately. Delayed upload must not fabricate a continuous interval.
- Do not use Android GPS as a silent substitute for the wearable GPS.

## Backend

FastAPI with typed request/response models, SQLAlchemy, Alembic migrations, and PostgreSQL. Use opaque server-side login sessions: Android sends a bearer token, while web/SSE uses a Secure, HttpOnly, SameSite cookie backed by the same session store. Protect cookie-authenticated state-changing routes against CSRF. Do not place authentication tokens in event-stream URLs.

The backend handles device ownership, paired-session lifecycle, idempotent telemetry ingestion, evidence aggregation, points/XP, badge purchases, and fresh partner summaries. Keep these as separate modules with unit/integration tests. Quest completion must lock or atomically update the session and create unique per-user award transactions.

Use one API worker initially so in-memory SSE notification fan-out remains straightforward. PostgreSQL is the source of truth; reconnecting clients fetch a fresh state snapshot. Multiple-worker pub/sub is unnecessary for two users.

## Web

React/TypeScript with Vite. Pages: login, dashboard, quest session/live graph, shop, and transaction history. Use the backend contract rather than duplicating quest rules in JavaScript. Show invalid/stale states and a prominent demo banner. Store no device secrets or privileged logic in the browser.

Serve the static web build and `/api` through the same reverse-proxy origin. Use SSE for progress; on reconnect reload the canonical snapshot. A graph gap means missing data, not zero BPM.

## Persistence

Minimum entities: users, devices, pairings, login sessions, shared quest sessions, session participants, telemetry records, per-user quest awards, point transactions, reward catalog, and owned rewards.

- Unique telemetry key: `(device_id, boot_id, sequence)`.
- Unique award key: `(session_id, user_id)`.
- Unique reward ownership: `(user_id, reward_id)` for the one-time cosmetic catalog.
- Purchase idempotency key scoped to user; concurrent requests must never allow negative balances.
- Keep lifetime XP separate from the spendable points ledger.
- Access control applies to every API path, including live events and partner coordinates.

## Deployment and source layout

Create `firmware/`, `android/`, `backend/`, `web/`, and `infra/` when implementation starts. Keep shared protocol examples under `docs/` or a dedicated schema directory. Check in lockfiles, migrations, the Gradle wrapper, and sample environment configuration with placeholders.

Docker Compose runs PostgreSQL, the API, and the static-web/reverse-proxy service. Persist database data in a named volume. Use HTTPS for phone traffic. Domain, TLS provisioning, reachable server URL, and actual demo destination remain user-environment inputs; do not invent them.

Seed two users and their pair without hardcoded real passwords. Seed the three badges. The deployment guide must explain migrations, seed configuration, startup, health checks, backups, and restoring the database. Do not expose PostgreSQL publicly.

## Evidence boundary

This is a cooperative classroom prototype, not a tamper-resistant anti-cheating system. Session tokens, counters, ownership checks, and duplicate suppression prevent common mistakes; they do not prove that a determined user cannot fabricate firmware data. Describe that limit in the report rather than claiming cryptographic proximity proof.
