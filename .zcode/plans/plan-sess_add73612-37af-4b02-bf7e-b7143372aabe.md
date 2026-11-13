# Catch Me v2: phone GPS, digital pet, landmark raids + co-op arcade — no heart-rate quest

## Context

The user is re-scoping the product (explicit instruction, overrides standing rules; affected docs get rewritten as part of this change):

1. **Phone GPS replaces the wearable ASD2501 GPS shield entirely** — all location (explore quest, discovery last-known, landmark raids) comes from phone fixes relayed with telemetry. The shield never achieved outdoor validation; phone GPS removes that risk.
2. **Digital pet** on each TinyScreen+ (ported from the bench-verified pet fork `D:\catch_me_pet`): levels up from quest XP, tamagotchi-style daily care via the 4 buttons granting small XP, synced to the phone app/server.
3. **Landmark raids**: Bluetooth proximity (existing heartbeat detection) + visiting a real landmark (phone GPS) unlocks a co-op raid boss — a simple space-invaders/bullet-hell game played **board-to-board over a direct BLE connection**, both players on their own TinyScreen+.
4. **The heart-rate quest (Keep Your Cool / `heart_challenge`) is REMOVED** from the product: no creation, no UI, no sensor. The AST1041 pulse sensor leaves the required stack (records keep carrying `hr_valid=false` honestly; record format unchanged). Historical `heart_challenge` sessions stay readable in the DB/web history. Quest set becomes **together, explore, raid**.
5. Deadline **28 Nov 2026**. Must-ship: phone GPS + pet. Stretch: raid game (gate-gated). Evolve the **main project**; the fork is the porting source only.

**Feasibility (from code exploration):** Pet — high confidence (hw-accelerated display primitives at 12 MHz SPI; 10 ms tick; ~25 KB RAM / ~210 KB flash free; the fork bench-verified species/moods/care/persistence/XP-leveling on this exact hardware). Game — feasible via dedicated board-to-board GATT connection: vendored STBLE implements `aci_gap_create_connection` + GATT client/notification APIs (needs an extern prototype; multi-role GAP init already runs); existing 20-byte CRC framing sustains ~80 packets/s vs a ~10 Hz game need. Phones drop during the fight (0x0C/0x82 gates make radio concurrency impossible) and auto-relink after. Bench-verify: unimplemented central path in `note_connect`/`HCI_Event_CB`, and display+BLE sharing SERCOM4 SPI under render load.

## Architecture decisions

- **XP stays server-owned** (unchanged spine). Pet levels from the **same `lifetime_xp`** (`level_for_xp`, `backend/app/schemas.py:15`); fork's evolutions (100/300 XP → teen/adult) map onto it. No second economy.
- **Pet split-brain by ownership**: cosmetic state (species, name, needs/mood decay) is **device-owned** in flash (fork's `pet_store` double-slot commit ported) so the pet lives on the wrist without the phone; XP/level is server-owned, pushed via a new `MSG_PET_STATE` relay (stale level shown honestly when offline).
- **Daily care**: care runs on-device (mood recovers immediately); events carry their date and relay phone→server when linked (queued offline, drained later). Server grants **+10 XP once per user per calendar day**, idempotency `care:{user}:{YYYY-MM-DD}` (reuses unique `PointTransaction.idempotency_key`, `models.py:330`).
- **Phone GPS**: phone keeps its last real fix; at relay time it stamps the record's `gps` object with `source:"phone"` and the **true fix age**, so all existing freshness rules (explore ≤10 s, discovery 30 s/900 s, clock ≤2 s) hold with zero server logic changes. New nullable `gps_source` column backfills `"wearable"`.
- **Heart-rate removal mechanics**: delete `heart_challenge` from the creation catalog + `QuestId` Literal for new sessions (legacy id stays recognized in serializers so old sessions keep rendering); remove its evaluation branch, interaction phases (`baseline/select_prompt/round/summary`), truth/dare catalog, tests, UI buttons, and firmware pulse init (`pulse_app` gated off; records stay `hr_valid=false`).
- **Raid quest** (`quest_id:"raid"`): server seeds a landmark catalog (geofence-freeze pattern, `sessions.py:188`); activation gate = both participants' phone fixes within 50 m of the landmark **and** mutual peer evidence live; the fight runs board-to-board; completion = **both** boards' outcome reports relayed as per-session idempotent commands (PIN-command pattern); award +100/+100 exactly once, server-verified. Together keeps its PIN flow unchanged.
- **Game netcode**: host-authoritative — board 1 (central) simulates boss/bullets, broadcasts state deltas; board 2 (peripheral) sends input. ~12-byte messages, 10 Hz. Game: boss (sinusoid, aimed slow bullets), 2 ships (LL/LR move, UR fire, 3 lives), boss 60 HP, shared win/lose screens.

## Implementation stages (to 28 Nov)

### Stage 0 — Docs rewrite (day 1; AGENTS.md governs later sessions)
Update `AGENTS.md` requirements (GPS rule reversal, heart-rate requirement dropped, new quest set + pet/game scope), `docs/PROJECT_SPEC.md` (lines 18/48 GPS clauses; quest table → together/explore/raid; pet + raid sections), `docs/QUEST_INTERACTION_PLAN.md` (together-only PIN spec; heart phases marked removed, history preserved), `docs/INTERFACES.md` (gps.source, new messages/endpoints, heart endpoints removed), `docs/DISCOVERY_PLAN.md`, `docs/TEST_PLAN.md`. Preserve: server-owned exactly-once awards, honest-invalid display, no fabricated GPS, fixture rules, legacy session readability.

### Stage 1 — Server (days 1–4)
- Heart removal: catalog/Literal/evaluation/interaction phases/tests/UI gone; legacy read path kept.
- Alembic migration: `telemetry_records.gps_source`; `pets` mirror table (species, name, last_care_date, care_streak); `quest_sessions` raid columns — pattern: `c4f7a91e2b10`.
- `schemas.py`: `GpsReading.source`; pet fields in `MeOut`; landmark catalog in seed.
- `routers/me.py`: `PUT /me/pet`, `POST /me/pet/care` (pattern: `location-sharing` PUT + purchases idempotency).
- `routers/sessions.py` + `services/evaluation.py`: raid activation gate + completion (both participants' idempotent outcome commands; evidence-window verification reusing `evidence.py` primitives).
- Tests: care daily cap, gps source pass-through, raid gate/completion/exactly-once, heart-creation rejected + legacy readable, migration backfill. Full suite on `catch_me_pg_test`.

### Stage 2 — Android (days 3–7)
- Remove Keep Your Cool button/flows; location source: `LocationManager` GPS (fine-location permission already declared).
- `QueueDb.kt RecordCodec` / `AppModel.enqueueTelemetry`: stamp phone fix + true fix age; strip wearable GPS (`AppModel.kt:663` comment updated).
- Pet: fields in `UiState`, pet card (species/name/level/mood/streak), care-event queue + sync, `MSG_PET_STATE` downlink.
- Raid button (3rd) + game-mode relays (pause link supervision during raid, relink after).
- `MainActivity.requestBlePermissions` extended for location-as-GPS.

### Stage 3 — Firmware pet port (days 5–10)
- Port from `D:\catch_me_pet\firmware\pet_app`: `pet_core.{h,cpp}` (needs/moods/care), `pet_store.{h,cpp}` (double-slot persistence — board1 W25Q slot / board2 internal rows, **separate slot from the telemetry queue**), pet rendering (procedural `draw_pet_sprite`, no assets).
- Integrate: `SCR_PET` in rotation, care modal owning all 4 buttons (PIN-entry pattern, `ui_app.cpp:74`), decay via the time anchor (`catch_me_app.ino:73`), `MSG_PET_STATE`/`MSG_CARE_EVENT` framing.
- Gate off GPS (`CM_GPS_ENABLED 0`) and pulse (`CM_PULSE_ENABLED 0`) inits; shields may stay stacked, unread.

### Stage 4 — Raid game, stretch (days 8–14)
- **Gate experiment first** (new `tools/drive_game_bench.py`, modeled on the fork's bench drivers): board A central-connects to B's deterministic bdaddr; pass = connection ≤10 s, sustained ≥2 min at 10 Hz ticks **while rendering**, zero watchdog resets, clean disconnect + phone relink. Add extern prototype for `aci_gap_create_connection`; implement the central branch in `note_connect`/`HCI_Event_CB`.
- Gate passes → `game_app.{h,cpp}` (10 ms tick, 10–20 FPS dirty-rect rendering), `RadioState::RAID` in the TDD scheduler, `MSG_GAME_*` over existing framing, raid flow + outcome reporting. Gate fails → phone-relay fallback (shared boss HP, async) or vertical-slice demo with honest status.

### Stage 5 — Integration + delivery (days 15–22)
Bench bilateral pet-sync + care + raid at a real landmark (phone GPS makes the outdoor walk trivial); extend `tools/test_feature_sweep.py` (pet care, gps source, raid, heart-creation-rejected); demo script + report per `DEMO_AND_REPORT.md`; freeze docs.

## Key files

- **Server**: `backend/app/{models,schemas}.py`, `routers/{telemetry,me,sessions,interactions}.py`, `services/{evaluation,interactions}.py`, `alembic/versions/` (new), `seed.py`, `backend/tests/`.
- **Android**: `app/src/main/java/com/catchme/app/data/{QueueDb,AppModel,Api}.kt`, `ble/Frame.kt` (new MSG ids), `MainActivity.kt`, `AndroidManifest.xml`.
- **Firmware**: `firmware/catch_me_app/{catch_me_app.ino, ui_app.*, ble_app.*, config.h, pulse_app.* (gated off)}` + ported `pet_core.*`/`pet_store.*` + new `game_app.*`.
- **Docs**: `AGENTS.md`, `docs/{PROJECT_SPEC,QUEST_INTERACTION_PLAN,INTERFACES,DISCOVERY_PLAN,TEST_PLAN}.md`.
- **Port source**: `D:\catch_me_pet\firmware\pet_app\{pet_core,pet_store}.cpp/.h`, pet UI blocks in its `ui_app.cpp`.

## Reuse (don't rewrite)

`level_for_xp` (schemas.py) · award path `evaluate_and_maybe_complete` (evaluation.py) · `command_start` idempotency (interactions.py) · `Idempotency-Key` purchase pattern (rewards.py) · geofence freeze (sessions.py:188) · `haversine_m`/window-coverage (evidence.py) · CRC framing + 20-byte chunks (ble_app.cpp:58) · TDD scheduler enum (ble_app.h:156) · button-modal pattern (ui_app.cpp:74) · STBLE GATT client APIs (bluenrg_gatt_aci.h) · fork's bench drivers and pet code.

## Verification

1. **Server**: full pytest suite green on `catch_me_pg_test` incl. new tests (heart creation rejected, legacy session still serializes); OpenAPI regenerated.
2. **Android**: `gradle assembleDebug`; bench: logcat shows `gps.source=phone` records accepted (200), pet card renders, care sync round-trip lands in `PointTransaction`.
3. **Firmware**: both DEVICE_ID builds; serial bench — pet survives reboot on both flash backends; `MSG_PET_STATE` round-trip visible server-side; GPS + pulse init absent from boot logs.
4. **Game gate**: `tools/drive_game_bench.py` pass criteria above, ×3 consecutive runs.
5. **End-to-end demo pass**: at a real landmark — proximity + location gate opens the raid, two players fight board-to-board, phones relink, server awards exactly once each; extended feature sweep all-green.
