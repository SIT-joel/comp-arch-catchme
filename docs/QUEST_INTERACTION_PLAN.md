# Quest interaction plan v2: together PINs, landmark raid; heart quest removed

Revision: 6 November 2026 (v2, user-directed). Extends the approved 30 October revision; the Together PIN specification below is unchanged and already implemented. **The heart-rate quest (`heart_challenge`) is removed from the product**: creation rejected, UI hidden, sensor dropped. Historical heart sessions stay readable.

## Demo defaults

- Together quest: **30 seconds of verified direct Bluetooth presence**, with mutual four-digit PIN exchange before timing and again before rewards (unchanged).
- Raid quest: a co-op boss fight at a real landmark. Demo mode shortens boss HP so a fight completes in roughly one minute; normal mode takes longer. Both boards must report the fight outcome before awards.
- Quest IDs: `together`, `explore`, `raid`. `heart_challenge` remains a known legacy ID for reading history only.
- Demo mode stays the default selection on quest-start screens, visibly labeled and stored per session.
- Successful sessions still award each participant 100 points and 100 XP exactly once.

## Together: exchange codes at start and finish (unchanged, implemented)

1. One partnered user creates a demo together quest and the other accepts through the existing session flow. Acceptance prepares the PIN stage; it must not start scoring yet.
2. Server generates a separate code for each participant. Wearable A displays A's code; wearable B displays B's code. Each person asks for and enters the OTHER person's code on their own TinyScreen+.
3. When both entries are server-confirmed, record `timing_started_at`, relay the new stage, and start accruing direct peer-presence evidence. Only evidence at/after that timestamp counts. Existing session-bound heartbeat and maximum-gap rules remain mandatory.
4. Once 30 seconds of valid overlapping evidence accumulate, freeze progress at target and enter the end-code stage. **Do not award points yet.**
5. Generate two NEW codes for that stage. Each user again enters their partner's code. Codes from the start stage must fail here.
6. When both end entries are confirmed, complete the quest and issue rewards transactionally, once.

### PIN lifecycle and device UI (unchanged, implemented)

- Four decimal digits, including leading zeros; secure server random. All four codes in a session differ.
- Codes are scoped to session, stage, and owner; only the requesting participant's display code is ever relayed to them.
- Five-minute validity; five failed submissions per entering user/stage/code version; refresh replaces only the caller's code and its confirmation.
- No codes in logs or broad SSE events. Route entries device → Android → authenticated API; a BLE send alone is not success; the phone never auto-fills codes.
- Retries carry command ID, session, stage, and code version. TinyScreen buttons in PIN mode: upper-right +1, upper-left −1, lower-right advance (submits on the last digit), lower-left back/exits entry without cancelling.

## Raid: landmark co-op boss fight (new)

### Start gate (server-verified)

1. A partnered pair creates a raid session for a seeded landmark (the session freezes the landmark's coordinates and radius, like explore's geofence).
2. Activation requires, for **both** participants: a valid phone-GPS fix within **50 m** of the landmark (fix age ≤ 30 s at evaluation) **and** live mutual direct peer presence (the existing ≤10 s heartbeat rule).
3. Phones relay "raid ready" to both wearables; the boards then enter the fight.

### The fight (device-to-device)

4. Both boards drop their phone links and open a **direct BLE connection** (board 1 central → board 2 peripheral, deterministic public addresses). The TDD scheduler is suspended for the fight's duration.
5. A simple host-authoritative space-invaders/bullet-hell game runs at ~10 ticks/s over the existing 20-byte CRC framing (new `MSG_GAME_*` types): board 1 simulates the boss (sinusoid movement, aimed slow bullets) and broadcasts state; board 2 sends inputs. Each player: move (LL/LR), fire (UR), 3 lives; boss HP shared (demo ~20, normal ~60).
6. Win = boss HP reaches 0. Lose = both players out of lives. Either way the fight ends, the connection closes, and both boards relink their phones.

### Completion (server-verified)

7. Each board reports its outcome (win/lose, fight duration, session id) through its phone as an idempotent command (the PIN-command pattern). The server completes the session only when **both** participants' reports arrive and the recorded evidence window overlapped the fight.
8. Awards (+100/+100) issue transactionally exactly once. A disconnect mid-fight aborts to the lobby honestly — no partial credit for an unfinished boss.

### Fallback

If the board-to-board connection gate fails on hardware, the raid falls back to a phone/server-relay variant (shared boss health bar, ~1 s round trip, same server verification) rather than weakening the evidence rules.

## Removed: Keep Your Cool

The `heart_challenge` quest (truth-or-dare with live pulse) is removed per the v2 decision. Do not create, display, or evaluate it. The pulse sensor is not initialized; telemetry honestly reports `hr_valid=false`. Historical sessions with this ID must keep serializing for history views.

## Tests and delivery order

1. Backend: together regressions unchanged; raid gate (landmark radius, fix age, mutual presence), outcome command idempotency, both-reports-required completion, exactly-once awards; heart-creation rejected (409/422) while legacy sessions still serialize; pet daily-care cap.
2. Android/firmware: raid lobby/ready relays; game-mode link suspension and relink; `MSG_GAME_*` framing; outcome reporting.
3. Board-to-board connection gate (`tools/drive_game_bench.py`): connect ≤10 s, sustained ≥2 min at 10 Hz while rendering, zero watchdog resets, clean disconnect + phone relink — ×3 consecutive runs.
4. Physical: a real landmark raid with two users, two phones, two boards; exactly-once awards; demo script update.
