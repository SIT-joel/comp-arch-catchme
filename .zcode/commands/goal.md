---
description: Overnight autonomous driver — push the Catch Me v2 plan (phone GPS, pet, raid) as far as possible
---

# /goal — autonomous overnight run

You are running unattended with a generous budget. Push the **Catch Me v2** implementation as far as it can go tonight, honestly. Nobody will answer questions — park blockers, record them, and continue with independent work.

## Boot sequence (do this first, in order)

1. Read `AGENTS.md` (v2 mission: phone GPS replaces wearable GPS; heart quest removed; digital pet; landmark raid + co-op game), then the NEWEST entry of `docs/PROGRESS.md`, then `docs/QUEST_INTERACTION_PLAN.md`, `docs/INTERFACES.md`, `docs/PROJECT_SPEC.md`.
2. Reconcile in-flight state: the previous session may have stopped mid-edit. Run `backend\.venv\Scripts\python.exe -m pytest backend\tests -q` (needs `catch_me_pg_test` Docker container up — start it if down) and skim `git`-less diffs by reading the files listed in PROGRESS.md's last entry. Fix forward until the suite is green before adding anything.
3. Verify the environment quickly: Docker containers `catch_me_pg_dev`/`catch_me_pg_test` up; if the API server on :8000 is down, relaunch detached: `powershell -NoProfile -Command "Start-Process -FilePath 'D:\catch_me\backend\.venv\Scripts\python.exe' -ArgumentList '-m','uvicorn','--app-dir','D:\catch_me\backend','app.main:app','--host','127.0.0.1','--port','8000' -WorkingDirectory 'D:\catch_me\backend' -WindowStyle Hidden"`.

## Stage checklist (approved plan — work top-down, skip what PROGRESS.md already shows complete)

- **Stage 1 (server)**: heart-quest removal (creation rejected, legacy sessions still serialize); Alembic migration — `telemetry_records.gps_source`, `pets` mirror, `landmarks`, raid columns on `quest_sessions`; pet endpoints `GET/PUT /me/pet`, `POST /me/pet/care` (+10 XP once/user/day, idempotency `care:{user}:{date}`, reuse the purchase/award locking patterns); raid quest — catalog entry, landmark freeze at activation, gate = both participants' phone fixes within 50 m + mutual peer presence (reuse `latest_valid_gps` + evidence helpers), `POST /sessions/{id}/raid/outcome` completing only on BOTH participants' win reports, exactly-once +100/+100 awards. Add tests for every rule above; keep the whole suite green on the PG test container; regenerate `docs/openapi.json`.
- **Stage 2 (Android + web)**: remove Keep Your Cool UI everywhere; LocationManager GPS source + stamp real fixes (true fix age, `gps.source:"phone"`) into relayed records in `RecordCodec`/`enqueueTelemetry`; pet fields in `UiState` + pet card + care sync; raid quest button + `MSG_PET_STATE`/`MSG_PET_CARE_EVENT`/`MSG_RAID_OUTCOME` framing in `Frame.kt`; raise `quest_id` mapping for `raid`. Web: heart quest removal + pet card on the dashboard. Build: `gradle --offline --no-daemon -Pkotlin.compiler.execution.strategy=in-process assembleDebug` (JDK/Gradle via `tools/android/`), `npm run build` in `web/`.
- **Stage 3 (firmware)**: port `pet_core.{h,cpp}` + `pet_store.{h,cpp}` + pet rendering blocks from `D:\catch_me_pet\firmware\pet_app\` into `firmware/catch_me_app/` (dedicated flash slot, NOT the telemetry queue); `SCR_PET` screen + care buttons (PIN-modal ownership pattern); `MSG_PET_*` relay handling in `ble_app`; gate GPS + pulse inits off (`CM_GPS_ENABLED 0` / `CM_PULSE_ENABLED 0`); compile BOTH `DEVICE_ID`s via the pinned `tools/arduino-cli`.
- **Stage 4 (stretch)**: write `tools/drive_game_bench.py` (board-to-board connection gate; pass = connect ≤10 s, ≥2 min at 10 Hz while rendering, 0 watchdog resets, clean relink — ×3). If the boards are on COM3/COM4 you MAY flash and run it (autonomous, no button presses needed); otherwise leave it ready-to-run. Then `game_app.{h,cpp}` + `RadioState::RAID` + `MSG_GAME_*` behind the gate result.
- **Stage 5**: extend `tools/test_feature_sweep.py` (gps source, pet care cap, raid flow, heart-creation rejected) and run it against the dev server.

## Rules (non-negotiable)

- Awards/XP stay server-owned and exactly-once; never fabricate GPS ages or sensor data; fixtures stay clearly labeled; compilation ≠ hardware validation — record status honestly per stage in `docs/PROGRESS.md`.
- Never: delete historical sessions/awards, drop/migrate data destructively, clear app data on the phones, commit binaries, or claim a physical gate passed without serial/log evidence in hand.
- When a stage blocks, write the exact blocker + evidence into PROGRESS.md and move to the next independent item. Do not stop early while independent work remains.
- After each stage: append a PROGRESS.md entry (changes, exact commands + results, pending). At the end of the run: final PROGRESS.md summary with what shipped, what's verified at which level (implemented / software-tested / bench-verified), and the precise next physical actions for the user.

$ARGUMENTS
