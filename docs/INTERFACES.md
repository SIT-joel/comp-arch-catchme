# Initial interface contract

## Quest interaction v1 (implemented; v2 quest set)

The approved behavior is in [QUEST_INTERACTION_PLAN.md](QUEST_INTERACTION_PLAN.md). New together sessions activated after both users accept get `interaction_version=1`; legacy rows with a null version retain the previous evaluator. **v2: `heart_challenge` is removed** — creation is rejected, the choice/skip routes below are withdrawn, and legacy heart sessions keep serializing read-only. **v2.1 (14 Nov): `raid` is removed** — creation is rejected as an unknown quest; legacy raid sessions (and the outcome route) keep serializing read-only.

Participant routes:

| Method and path | Behavior |
|---|---|
| `GET /api/v1/sessions/{id}/interaction` | Authoritative phase snapshot. Includes only the caller's display PIN, never the partner's. |
| `POST /api/v1/sessions/{id}/interaction/pin/submit` | Body: `stage` (`start`/`end`), `pin` (four ASCII digits), `code_version`, `command_id`. |
| `POST /api/v1/sessions/{id}/interaction/pin/refresh` | Body: `stage`, `command_id`. Replaces only the caller's code and invalidates its prior confirmation. |
| `POST /api/v1/sessions/{id}/raid/outcome` | Body: `outcome` (`win`/`lose`), `fight_started_at`, `fight_ended_at`, `command_id`. Completion requires both participants' reports (idempotent per command id). |

All mutation commands are participant-authorized and idempotent by command ID. PINs are securely random four-digit strings (leading zeros preserved), expire after five minutes, have five failed attempts per entering user and code version, and are unique within a session across both exchanges and refreshes. Only the code owner can refresh it. Codes are removed when the session completes or is cancelled; PINs are a cooperative game step, never authentication or proximity evidence. Command hashes are HMACs scoped by the session token; raw PINs are not logged or broadcast over SSE.

New together sessions enter `start_pin`, then `timing`, then `end_pin`. Presence evidence is filtered to observations captured after `timing_started_at`; progress caps at target while the final exchange is pending. Rewards issue only after both end entries. Demo defaults are visibly enabled in the clients; demo together is 30 s, and its normal target remains 600 s.

(Raid sessions: historical only — the quest was removed 14 Nov; the outcome route stays for legacy read paths.)

## Pet (v2)

| Method and path | Behavior |
|---|---|
| `GET /api/v1/me/pet` | Pet mirror: species, name, level (derived from `lifetime_xp`), care streak, today's care state |
| `PUT /api/v1/me/pet` | Body: `species` (`spark`/`fluff`/`pip`), `name` (≤8 chars). Mirrors the wearable's bonding choice; cosmetic only |
| `POST /api/v1/me/pet/care` | Body: `date` (`YYYY-MM-DD`), `command_id`. Grants **+10 XP at most once per user per calendar day**; idempotent by `care:{user}:{date}`. Offline days sync later; the cap still applies |

Pet cosmetic state (species/name/needs/mood) is authoritative on the wearable's flash; the server mirrors it for web/phone display. XP/level is server-owned and pushed to the wearable via `MSG_PET_STATE`; the wearable marks its shown level stale until the next sync.

### Interaction BLE v1 messages

These messages are separate from telemetry, discovery, and peer heartbeat fields. The phone sends only the current wearer's code to that wearer's wearable. BLE receipt is not API success: the board retries the same nonce until the Android relay acknowledges the authenticated server result.

| Type | Direction | Payload |
|---|---|---|
| `MSG_INTERACTION_STATE` (14) | phone → wearable | 58 bytes: `[ver=1][phase][reserved][stage][own code ASCII[4]][own code version LE16][partner code version LE16][own-confirmed u8][partner-confirmed-by-me u8][round u8][active-user u8][prompt-kind u8][prompt-len<=24][prompt ASCII[24]][session UUID raw 16 bytes]`. Phase: 0 none, 1 start PIN, 2 timing, 3 end PIN. Stage: 0 none, 1 start, 2 end. |
| `MSG_INTERACTION_COMMAND` (15) | wearable → phone | `[ver=1][kind][stage][target code version LE16][nonce LE64][session UUID raw 16][value-len][value<=4 ASCII]`. Kind: 1 PIN submit, 2 refresh own PIN. |
| `MSG_INTERACTION_ACK` (16) | phone → wearable | `[ver=1][nonce LE64][server-result u8]`; 1 = server accepted/idempotently confirmed, 0 = server rejected. |
| `MSG_PET_STATE` (17) | phone → wearable | `[ver=1][xp LE32][level u8][stage u8][care-today u8][name-len u8][name ASCII ≤8]` — server-owned economy view; the wearable marks its displayed level stale between syncs. |
| `MSG_PET_CARE_EVENT` (18) | wearable → phone | `[ver=1][care-kind u8][date ASCII 10 (YYYY-MM-DD)][nonce LE64]`; the phone maps it to `POST /me/pet/care` and ACKs like an interaction command. |
| `MSG_GAME_STATE` (19) | board 1 → board 2 (direct connection) | `[ver=1][tick LE16][boss x/y u8][boss hp u8][bullets n ≤6 ×(x,y)][players 2 ×(x,lives)][flags u8]` at ~10 Hz during the raid fight. |
| `MSG_GAME_INPUT` (20) | board 2 → board 1 (direct connection) | `[ver=1][tick LE16][move i8][fire u8]` at ~10 Hz. |
| `MSG_RAID_OUTCOME` (21) | wearable → phone | `[ver=1][outcome u8][duration s LE16][nonce LE64][session UUID raw 16]`; relays to `POST /sessions/{id}/raid/outcome`. |

The session UUID and nonce identify a retry; Android maps them to the authenticated API command UUID. Firmware button edges are debounced; while PIN entry is active, upper-right increments a digit, upper-left decrements, lower-right advances/submits, and lower-left returns/exits entry without cancelling. Pet care buttons: LL feed, LR stroke (on the pet screen). Game buttons: LL/LR move, UR fire, UL pause/quit.

## Discovery extension (implemented; regenerate OpenAPI after changes)

Behavior per [DISCOVERY_PLAN.md](DISCOVERY_PLAN.md). Implemented paths (see
`docs/openapi.json`, generated from the live routes):

| Method and path | Purpose |
|---|---|
| `GET /api/v1/me/discovery-profile` | Profile snapshot + opt-ins + completeness |
| `PUT /api/v1/me/discovery-profile` | Edit display name, age (18–99), `pref_min_age`/`pref_max_age` (18–99, min ≤ max), `interests` (≥1 of the 8 fixed tags), `radius_m` (100–5000) |
| `PUT /api/v1/me/discovery-settings` | Separate `bluetooth_enabled` / `gps_enabled` opt-ins (both default off) |
| `GET /api/v1/me/discovery` | Combined results; clients poll every 5 s while their screen is open |
| `POST /api/v1/me/discovery-token` | Provision/rotate the bound wearable's 16-bit opaque token (`?rotate=true` invalidates the old value) |
| `POST /api/v1/discovery/observations` | Phone upload of direct wearable scan observations (idempotent) |
| `POST /api/v1/invitations` | Invite an eligible unpaired user (`to_user_id`) |
| `GET /api/v1/invitations` | Pending inbox/outbox (lazy 5-minute expiry) |
| `POST /api/v1/invitations/{id}/accept` | Transactional, idempotent partnership acceptance |
| `POST /api/v1/invitations/{id}/decline` | Recipient declines |
| `GET /api/v1/me/partnership` | Active partnership or 404 when unpaired |
| `DELETE /api/v1/me/partnership` | End partnership; cancels the pair's pending/active quest sessions first, preserves all history/awards |

Fixed interest catalog: `gaming`, `music`, `fitness`, `food`, `movies`,
`travel`, `reading`, `outdoors` (DB CHECK on `user_interests.tag`).

Rules encoded server-side: mutual age-preference inclusion, ≥1 shared
interest, complete profiles only, self/partnered users excluded, per-method
opt-in required for BOTH users, requester's radius filters (unrounded),
ranking by shared-count desc then display name then user id. GPS states:
`fresh` ≤ 30 s, `last_known` ≤ 900 s (both inclusive boundaries),
`expired` beyond; `missing` before the first trustworthy fix. Distances in
responses are rounded to the nearest 50 m; raw coordinates never leave the
server in discovery results. Honesty notices: "Near your last GPS
location", "Based on their last GPS location", "GPS location expired—go
outdoors to refresh.", "Waiting for GPS fix." (v2: fixes come from the
phone, relayed with telemetry.)

Observation identity is `(observer_user, token, captured_at)`: a
retransmitted observation is a no-op; only a new physical reception (new
capture time) refreshes presence. Presence window is 15 s from the
original capture time, evaluated at query time. The phone stamps
`captured_at = receive_time - age_ms` from the wearable's report, which
makes retries naturally idempotent.

Last-known positions are durable rows updated during telemetry ingest:
`fix_time = captured_at - gps_fix_age_ms`, only for valid fixes with clock
uncertainty ≤ 2 s, monotonic in `fix_time` (older/repeated/delayed records
never replace or refresh; invalid readings never erase; future fixes
beyond the uncertainty tolerance rejected). Age is recomputed at read
time; discovery expiry never deletes telemetry or the cached position.
Quest scoring NEVER reads this cache — explore still requires fresh ≤10 s
fixes derived from telemetry rows.

### Discovery BLE messages (firmware ↔ phone)

Versioned payloads (first byte = discovery payload version, currently 1;
unknown versions are rejected explicitly and never misdecoded). The quest
heartbeat advertisement (0xC5, device ids 1–2, session token hash) is
UNCHANGED and remains the only quest evidence path.

| Type | Direction | Payload |
|---|---|---|
| `MSG_DISCOVERY_MODE` (8) | phone → wearable | `[ver][mode u8][token LE16]`; mode 1 only while unpaired and opted in; confirmed by ACK |
| `MSG_DISCOVERY_ACK` (11) | wearable → phone | `[ver][applied mode u8]` |
| `MSG_DISCOVERY_OBS` (9) | wearable → phone | `[ver][n ≤ 10][n × (token LE16, age_ms LE16)]`; sent ~5 s while linked; entries older than 15 s are not sent |
| `MSG_DISCOVERY_RESULTS` (10) | phone → wearable | `[ver][n ≤ 3][n × (shared u8, flags u8 (bit0 BLE, bit1 GPS), len u8, name ≤ 12 ASCII)]` |

On-air discovery advertisement (manufacturer field, same 0x0030 company
framing as the heartbeat): `[0xC6][version][token LE16]` — no names, ages,
or interests. While discovery mode is on, the wearable ALTERNATES between
the 0xC5 heartbeat and the 0xC6 discovery payload across advertising
windows; the TDD radio schedule itself is unchanged. Scan side: a bounded
buffer keeps the 16 latest unique observed tokens (oldest replaced when
full). Discovery observations are never session heartbeat evidence and
never grant points.

## Identity, time, and units

- Server entity/session IDs: UUID strings. Firmware may use provisioned compact numeric aliases mapped to those IDs.
- `boot_id`: unique across device restarts; implement using a wear-conscious persisted boot counter combined with device identity, or a verified random-ID source. Do not assume Arduino `random()` is unique.
- `sequence`: monotonic unsigned integer within a boot. Never change it when retrying a record.
- UTC timestamps: RFC3339 strings with timezone. Device uptime: integer milliseconds, extended across timer rollover.
- Coordinates: decimal degrees; radius/distance: metres; heart rate: BPM; durations: milliseconds internally.
- Use null for unavailable numeric values. Zero is a value, not a generic missing marker.
- Invalid fields must carry validity/status. Never trust client-submitted progress, points, XP, or completion flags.

## Telemetry batch

`POST /api/v1/telemetry/batches`, authenticated as the device owner's user. Initial limit: 100 records per batch. Reject malformed batches atomically with a useful error; duplicate valid records are successful no-ops.

Example shape (illustrative values, not actual hardware readings):

```json
{
  "schema_version": 1,
  "device_id": "11111111-1111-4111-8111-111111111111",
  "records": [
    {
      "boot_id": "device-a-42",
      "sequence": 1,
      "session_id": "22222222-2222-4222-8222-222222222222",
      "uptime_ms": 12000,
      "captured_at": "2026-11-01T02:00:12Z",
      "clock": {"source": "phone_server_anchor", "uncertainty_ms": 500},
      "gps": {"valid": true, "latitude": 35.0123, "longitude": 135.4567, "fix_age_ms": 1200, "source": "phone"},
      "heart_rate": {"valid": false, "bpm": null, "status": "no_contact"},
      "peer": {
        "observed": true,
        "device_id": "33333333-3333-4333-8333-333333333333",
        "boot_id": "device-b-17",
        "heartbeat_sequence": 6,
        "session_token": "opaque-demo-session-token",
        "observation_age_ms": 0
      }
    }
  ]
}
```

`heart_rate.status`: `valid`, `warming_up`, `no_contact`, or `invalid_signal`. **v2: the pulse sensor is not part of the product** — firmware reports `valid:false` honestly and the field is retained for contract stability.

**v2 GPS source rule:** `gps.source` is `"phone"` or `"wearable"` (default `"wearable"` for history). Phones attach their last real GPS fix at relay time with the **true** `fix_age_ms` (fix time − record capture time). Ages must never be clamped or fabricated; stale phone fixes are relayed as-is and fail freshness rules honestly. All existing evidence/freshness rules apply unchanged to phone fixes.

Peer evidence represents a directly received wearable message. Store only new observations, or preserve their original age; repeated telemetry about one old observation must not become new evidence. Match peer ID/session token and reject stale or repeated heartbeat counters for progress.

Acknowledgement shape:

```json
{
  "server_time": "2026-11-01T02:00:13Z",
  "accepted": [{"boot_id": "device-a-42", "sequence": 1}],
  "duplicates": [],
  "state_version": 7
}
```

Acknowledge exact record identities, not merely the largest observed sequence. The phone may relay compact contiguous acknowledgement ranges only when all included records are confirmed. Server persistence must finish before acknowledgement.

## Time reconciliation

- Phone estimates server clock offset using a timestamped request/response and records uncertainty. Device stores the corresponding uptime anchor.
- A record can have `captured_at: null` and `clock.source: "unsynced"`. Keep it pending for evaluation.
- Allow anchoring earlier records from the same boot only when the continuous uptime history is trustworthy. Never bridge an unknown reboot interval.
- Default maximum clock uncertainty for quest scoring: 2 seconds. Larger uncertainty pauses scoring for those records.
- Preserve original capture metadata when retrying. Clock corrections must be explicit and auditable, not silent timestamp replacement.
- Backend adds `received_at`; queued records are evaluated at capture time, not as fresh live readings.

## Endpoint inventory

| Method and path | Purpose |
|---|---|
| `GET /api/v1/health` | Service health without secrets |
| `GET /api/v1/time` | UTC synchronization response |
| `POST /api/v1/auth/login` | Login to seeded account |
| `POST /api/v1/auth/logout` | Revoke current login session |
| `GET /api/v1/me` | User, paired partner summary, points, XP, level |
| `POST /api/v1/devices/bind` | Bind preprovisioned device using one-time pairing credential |
| `GET /api/v1/devices/{id}/state` | Authorized session/partner summary for phone-to-device relay |
| `PUT /api/v1/me/location-sharing` | Enable/disable sharing within the pair |
| `GET /api/v1/quests` | Quest catalog and configured normal/demo durations |
| `POST /api/v1/sessions` | Create pending quest session with quest ID and demo flag |
| `POST /api/v1/sessions/{id}/accept` | Other paired user accepts; activate once both consent |
| `POST /api/v1/sessions/{id}/cancel` | Participant cancels an incomplete session |
| `GET /api/v1/sessions/{id}` | Canonical state, evidence status, progress, completion |
| `GET /api/v1/sessions/{id}/interaction` | Participant-only v1 interaction snapshot |
| `POST /api/v1/sessions/{id}/interaction/pin/submit` | Enter the partner's current stage code |
| `POST /api/v1/sessions/{id}/interaction/pin/refresh` | Refresh the caller's own code |
| `POST /api/v1/sessions/{id}/raid/outcome` | Report this board's raid fight outcome (both required to complete) |
| `GET /api/v1/me/pet` | Pet mirror (species/name/level/streak/today's care) |
| `PUT /api/v1/me/pet` | Update the pet mirror (species, name) |
| `POST /api/v1/me/pet/care` | Daily care claim: +10 XP once per user per calendar day |
| `GET /api/v1/landmarks` | Seeded landmark catalog (name, coordinates, radius) |
| `POST /api/v1/telemetry/batches` | Idempotent ingestion |
| `GET /api/v1/events` | Authenticated SSE state-change notifications |
| `GET /api/v1/rewards` | Catalog and ownership |
| `POST /api/v1/purchases` | Transactional purchase with `Idempotency-Key` |
| `GET /api/v1/transactions` | Current user's point/XP history |

Session states: `pending`, `active`, `completed`, `cancelled`. Reject invalid transitions with 409. Errors use `{ "error": { "code": "...", "message": "..." } }`; validation responses may additionally identify fields. Use 401 for unauthenticated, 403 for forbidden, 404 for missing resources, 409 for conflicts, and 422 for invalid input.

## Device state and BLE messages

Phone-to-device state contains state version, session ID/token, quest ID, mode, progress/target, partner alias, partner position with capture time and sharing status, and completion event ID. The active participant's interaction snapshot is relayed in a separate bounded message; completion events carry the heart-quest summary but no PINs. It must fit bounded firmware buffers.

Logical BLE message types:

- `HELLO`: device/protocol identity and capabilities.
- `TIME_ANCHOR`: server UTC, uncertainty, device uptime association.
- `SESSION_STATE`: current authoritative quest/partner state.
- `PEER_HEARTBEAT`: direct device identity, boot ID, session token, counter.
- `TELEMETRY`: queued capture record(s).
- `ACK`: server-persisted record identities/ranges.
- `STATUS`: sensor/queue/connection state.

Do not assume a large negotiated MTU. Implement bounded fragmentation and reassembly with version, message ID, fragment index/count, payload length, timeout, and integrity checking. Test dropped, duplicate, and reordered fragments. Do not send JSON blindly through a 20-byte example UART characteristic. Keep phone transport characteristics logically separate from the peer heartbeat service.

## Completion events

Use a stable completion ID derived from the awarded session. The phone relays it to the wearable. The device remembers delivered completion IDs sufficiently to avoid replaying a buzzer on every state poll. Buzzer notification failure must not undo a committed award.

## Live updates

SSE events contain a state version and affected session/user identifiers, or an authorized compact snapshot. On disconnect, reconnect and reload canonical state. Do not require uninterrupted SSE delivery for correctness. Mobile uploads and web display must remain independently recoverable.
