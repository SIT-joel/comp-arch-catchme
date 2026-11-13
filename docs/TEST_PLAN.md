# Verification plan

## Quest interaction validation (v2, 6 November)

Implemented backend coverage includes leading-zero and distinct-code generation, participant-only code exposure, per-code version refresh, stale/expired submission, five-attempt limits, no early together progress/rewards, end-code completion, and legacy-session scoring. **v2: the heart quest is removed** — creation must be rejected while legacy sessions keep serializing; the raid quest adds landmark-gate, both-reports-required completion, and exactly-once awards; pet care adds the daily +10 XP cap. The connected PostgreSQL integration suite is the result ledger in `PROGRESS.md`.

Web tests/build, Android debug APK compilation, and firmware compilation for DEVICE_ID 1 and 2 are software checks only. Physical acceptance remains pending:

- Flash both current firmware builds; confirm four-button digit entry and display on both TinyScreens.
- Relay a start exchange and fresh end exchange through the actual two wearables, both phones, and server. Confirm a network retry does not duplicate the command and that no phone autofills a PIN.
- Prioritize the Together proximity demo: verify direct Bluetooth presence gates 30 seconds of progress, start and end PINs are distinct, separation pauses evidence, and rewards wait for both end confirmations.
- Phone GPS: verify records carry `gps.source:"phone"` with true ages; explore scores on phone fixes; stale phone fixes fail freshness honestly.
- Pet: bonding/care on the wearable, persistence across reboot on both flash backends, `MSG_PET_STATE` sync round-trip, daily +10 XP cap enforced server-side, stale level marked on the wearable.
- **Board-to-board raid gate (`tools/drive_game_bench.py`)**: direct connection established ≤10 s, sustained ≥2 min at 10 Hz ticks while rendering, zero watchdog resets, clean disconnect + phone relink — ×3 consecutive runs. Only after this passes is the raid game physically accepted.
- Raid end-to-end at a real landmark: gate opens only with both phones in radius + mutual presence; fight runs board-to-board; both outcome reports required; exactly-once awards.
- Regress discovery, GPS freshness, explore scoring, balances, purchases, and historical sessions after migration.

This document remains an acceptance checklist, not a current test-results ledger. See `PROGRESS.md` for commands and actual results; do not infer physical acceptance from a successful build.

## Discovery extension acceptance

Use the complete cases in [DISCOVERY_PLAN.md](DISCOVERY_PLAN.md). Add unit tests with a controlled clock for fresh/last-known/expired GPS boundaries (30/31 and 900/901 seconds), actual fix age, invalid readings after valid fixes, out-of-order/replayed uploads, and restart persistence. Confirm both participants' ages and discovery opt-ins are checked.

Test direct BLE expiry (15/16 seconds), multiple provisioned IDs beyond 1–2, bounded buffers, duplicate GPS/BLE results, and expiry of only one source. Add migration and PostgreSQL concurrency tests for active partnership uniqueness across both pairing columns, invitation expiry/acceptance, and non-destructive termination.

Physically verify outdoor acquisition followed by indoor last-known labels, direct discovery on both boards using the existing scheduler, mutual pairing, and a completed quest. No cached discovery location or general discovery observation may grant quest progress. Run the existing backend/web/Android/firmware regression checks after implementation.

### Status after implementation (26 October 2026)

Software-level cases now automated in `backend/tests/integration/`
(`test_discovery.py`, `test_invitations_partnerships.py`; 72 tests total on
PostgreSQL, controlled clock via `app.clock`):

- [x] GPS boundaries 30/31 and 900/901 (fresh/last_known/expired; requester,
      other, both stale; ages surfaced; expiry notice)
- [x] Actual fix age honored (fix_time = captured_at − fix_age; delayed
      in-between fix cannot regress; newer fix wins; duplicates no-op)
- [x] Invalid reading after valid fix never erases; untrustworthy clock
      (>2 s) never updates; future fix rejected
- [x] BLE 15/16 s expiry; retransmission cannot revive presence; new
      physical reception can; 17-token upload (beyond ids 1–2); buffer
      dedup by token
- [x] Opt-in defaults off; either side opting out suppresses immediately;
      Bluetooth-only result labeled "Detected nearby" with no distance
- [x] Mutual age boundaries, invalid ranges rejected, no shared interest
      excluded, incomplete profile excluded, self excluded
- [x] Deterministic ordering (shared count desc, display name, user id);
      radius filtering unrounded; response distances rounded to 50 m
- [x] Combined sources union + dedup by user; GPS expiry leaves BLE result
- [x] Token provision/rotate; revoked token no longer maps
- [x] Invitation create/duplicate (either direction)/expire at 5 min/
      decline/double-respond; idempotent accept returns same partnership;
      concurrent opposite-side acceptances leave exactly one active
      membership (DB partial unique index)
- [x] End partnership cancels pending/active quest sessions first and
      preserves members/history; ended users return to discovery
- [x] Quest boundary: discovery observations + cached positions grant
      zero progress and zero awards
- [x] Migration: seeded pair preserved (verified on the live dev DB);
      preflight aborts on cross-column duplicate pairings with a report
      (verified on a scratch DB; no data deleted)

Still physical-only (unchecked): two-board discovery round-trip, radio
timing with payload alternation, TinyScreen rendering, outdoor→indoor
last-known demo, and the single-board re-flash regression of the existing
phone pipeline.

## Software tests

| Area | Cases | Expected result |
|---|---|---|
| Telemetry | Duplicate batch; out-of-order records; repeated same sequence across different boots | Exact duplicates count once; distinct boots remain distinct |
| Validation | Invalid coordinate range, malformed IDs, invalid BPM/status combination, oversize batch | Reject invalid payloads without partial commit |
| Authorization | Wrong user/device/session; unrelated user reading partner state/SSE | Access denied; no location or sensor leakage |
| Session lifecycle | One-sided invitation; double accept; cancel; accept completed session; parallel active sessions | Valid transitions only; one active shared quest per pair |
| Together | Consecutive peer samples at 9, 10, and 11 second gaps | <=10 second intervals count; 11 second gap does not |
| Peer evidence | Wrong peer, wrong token, duplicate heartbeat, one-sided evidence | Invalid evidence earns no time; intersect both users' evidence |
| Time | Delayed upload, uncertain anchor, reboot, millisecond timer wrap | Use trustworthy capture timeline; never fabricate continuity |
| GPS | 49/50/51 metre distance; 9/10/11 second age; missing fix; one partner outside | Configured boundary is inclusive; stale/invalid/outside intervals pause |
| Heart rate | No contact, warm-up, motion invalidity, >3 second report gap, only one valid participant | Graph gaps and paused progress; no interpolated success |
| Progress | Overlapping/replayed evidence; records arriving in reverse order | Same final progress without double-counting |
| Awards | Simultaneous evaluators/replayed completion | One 100-point/100-XP award per participant/session |
| Purchases | Insufficient funds, concurrent requests, repeated idempotency key, already-owned badge | No negative balance; no duplicate debit/ownership |
| Level | XP values 0, 99, 100, 200; purchase after level-up | Levels 1, 1, 2, 3; purchases do not reduce XP |
| SSE | Dropped connection/events | Reload snapshot, converge on canonical state |
| Demo mode | Normal vs demo durations | Prominent mode label and independent session evidence |

Use backend unit tests for interval math and integration tests against PostgreSQL for actual transaction/constraint behavior. A SQLite-only test does not establish PostgreSQL concurrency correctness. Web/Android tests should exercise meaningful state transitions, not mirror implementation details.

## BLE and persistence tests

- Fragment loss, duplication, reordering, oversized payload, timeout, protocol-version mismatch.
- Exact ACK processing with holes in a sequence range; never discard unacknowledged records.
- Lost server response after successful persistence; retry must remain idempotent.
- Phone restart with queued data; wearable restart during flash write.
- Flash full, corrupt/truncated final record, and acknowledged-sector reuse.
- Repeated completion state does not repeatedly trigger the buzzer.

## Physical test checklist

For each test record date, tester, device/board revisions, firmware commit, library versions, phone OS, procedure, raw observations, and pass/fail. Link logs/artifacts; do not paste secrets.

- [ ] TinyScreen+ display/buttons and programming work on both boards.
- [ ] Phone GPS fixes relay with true ages; no-fix/stale states are visible.
- [ ] Pet renders on both wearables; care works; state survives reboot on both flash backends.
- [ ] Both flash units survive write/read/reboot tests.
- [ ] Chosen buzzer ports pass pin/timer audit and do not disturb acquisition.
- [ ] Direct A/B heartbeat exchange identifies the partner and session.
- [ ] Phone links and peer detection coexist or alternate within scoring limits for 10 minutes.
- [ ] Actual separation stops verified presence; reconnect resumes without credit for the gap.
- [ ] Phone and web show actual latency/freshness while local display remains responsive.
- [ ] Full radio/display stack functions on battery, with measured runtime.
- [ ] Two-user together quest passes in normal mode at least once.
- [ ] Outdoor explore quest passes on phone GPS; leaving the geofence pauses it.
- [ ] Board-to-board raid gate passes ×3; a landmark raid completes with both outcome reports and exactly-once awards.
- [ ] Daily pet care pays +10 XP at most once per day; offline care syncs later under the same cap.
- [ ] Internet interruption stores data and later synchronizes once.
- [ ] Full demo earns a badge purchase and correct level without duplicate awards.

BLE reception is coarse presence evidence, not a precise distance sensor. Record the test environment and avoid claiming a calibrated range from a single RSSI reading.

## Handoff package verification

Before implementation: validate local Markdown links, check required files exist, parse the PowerShell script, and syntax-check Bash when Bash is available. Execute the non-mutating tool checker and record missing tools honestly. These checks do not pass any checklist item above.
