# Catch Me Pets — standalone two-board firmware fork

## Context

The phone-relay architecture's last blocker is unsolved (Samsung Android 11/12 stacks never deliver the boards' adverts to the phone app; the PC BLE adapter is dead). The user pivoted to a **standalone Tamagotchi-style product**: two TinyScreen+ boards do everything device-to-device with **no phone, no server, no web app, no WiFi** (WiFi shield stays excluded). Main features:

1. **Matching via Bluetooth** (nearby discovery), 2. **Distance from BLE signal strength** (RSSI → honest coarse buckets), 3. **Detecting two users spending time together** (direct mutual BLE evidence), 4. **Interactive Tamagotchi pet** fed by rewards and direct care, 5. **Quests together**: PIN-gated together-time, visit-a-spot (hardcoded landmarks + the board's own GPS — GPS is satellite-only, needs no WiFi/server), heart-rate challenge (software-first; one real AST1041 exists).

Per user decisions: create the new project and **keep `D:\catch_me` completely untouched** (it remains the phone/server/web implementation). Pet stakes: **sad, never dies** — neglect makes the pet sad/sick and it refuses to play, but care always recovers it; no permanent loss. Never hardcode *user* positions (faked evidence); hardcoded *landmark* spots are fine. Labeled fixtures only for software tests, never the demo.

## New project layout — `D:\catch_me_pet`

- `firmware/pet_app/` — sketch `pet_app.ino` + modules forked from `catch_me_app`. `config.h`, `w25q`, `flash_queue`, `internal_queue`, `gps_app`, `pulse_app`, `watchdog_app` copy nearly verbatim (hardware fixes preserved: flash CS D5 pre-assert, GPS A0–A3, DEVICE_ID, per-board TDD windows).
- `tools/arduino-cli/arduino-cli.yaml` — **shares** the existing toolchain data dir at `D:\catch_me\tools\arduino-cli\data` (pinned core TinyCircuits:samd 1.1.0 + 7 libraries; no duplication). Builds → `D:\catch_me_pet\tools\build\`.
- `tools/` — copy bench scripts: `capture_serial_ts.py`, `touch_bootloader.py`, `rescue_flash.py`, `dump_serial.py`, `watch_ports.py`.
- `README.md` (build/flash/demo), `docs/PET_SPEC.md`, `docs/PROGRESS.md` (fork log), short `AGENTS.md`.

## Board-to-board protocol (advert-only, no connections, no phone)

Extend the proven C5 manufacturer payload from 6 to ~13 bytes (fits the 31-byte advert cap):
`[C5][device u8][counter LE16][token LE16][ack_counter LE16][state u8][code_hash LE16]`
- `ack_counter` = last-seen partner counter → each board locally computes **mutual presence** (I saw the partner ≤10 s ago AND their advert acks one of my counters from ≤10 s ago). Gaps pause evidence, never reset.
- `state` = session FSM phase (idle / proposing+nonce / awaiting-start-PIN / start-confirmed / timing / end-PIN / done).
- `code_hash` = fnv16 of my current stage's 4-digit code → my board validates what its user types against the partner's advertised hash. Codes still only travel verbally.
- Invite: inviter broadcasts a random 16-bit session nonce in `proposing` state; partner accepts from the Nearby screen; both bind `token = fnv16(nonce|device ids)`.
- RSSI proximity: moving average over observations → buckets (right-here / nearby / far), calibrated on the bench; displayed honestly, feeds pet mood; no fake meters from RSSI.
- Phone UART service, LINKED phase, and all MSG_* relay code **removed**; radio cycle is ADV(1.5/2.3 s)↔SCAN(2.0 s) only.

## Firmware modules

**Forked near-verbatim**: `config.h`, `w25q`, `flash_queue`, `internal_queue`, `gps_app`, `pulse_app`, `watchdog_app`.

- `pet_store.h/.cpp` — persistent state (magic/version/write-counter, points, lifetime_xp, owned-badge bitfield, pet: species/name/stats/stage, last-award session token). Two backends from day one: W25Q raw driver and SAMD21 internal flash (**board 2 has no W25Q**). Double-slot commit, highest-valid-counter wins (power-loss safe). Pet stats persisted on change + every ~5 min (wear-aware).
- `spots.h` — hardcoded landmark table (4–6 campus spots: name + lat_e6/lon_e6, values confirmed with the user before commit).
- `session_app.h/.cpp` — quest FSM ported from `docs/QUEST_INTERACTION_PLAN.md`: invite → start-PIN (hash-validated) → timing → end-PIN (new codes, start codes must fail) → award **100 points + 100 XP exactly once** per session token; level = 1+floor(xp/100). Demo durations default with visible DEMO marker; normal durations behind a build flag. Publishes events (start/complete/award) for pet reactions.
- **Together quest**: PIN-gated mutual evidence 30 s (demo) — the core "spending time together" feature. Quest availability is never gated by pet mood (grading safety); the pet cheers regardless.
- **Visit-a-spot quest**: menu lists hardcoded landmarks; both boards need fresh GPS fixes (≤10 s) within 50 m of the spot for 20 s (demo) by local haversine, plus mutual presence; honest "no fix" indoors.
- **Heart challenge**: 10 s baseline (both HR valid + mutual presence) → fixed truth/dare catalog drawn locally by the active user → two 10 s turns → median-BPM summary with signed delta. Missing/stale sensor (>3 s) pauses honestly; no BPM pass/fail. Board 2 shows "no sensor" until a second AST1041 exists.

### Pet system (the fun layer — `pet_ui` + logic in `pet_store`)

- **First-boot bonding**: choose 1 of 3 pixel-art species, name it (4-button letter picker reusing the PIN editor pattern).
- **Needs**: hunger/happiness/energy 0–100, decaying while powered (≈ hunger −1/10 min, happiness −1/15 min solo; partner in right-here range slows happiness decay; charging = pet sleeps, decay pauses). Mood = f(needs): happy bounce / neutral / sad slouch / sick / sleeping, 2-frame idle animations at a few Hz. Sad/sick pets refuse Play and look miserable — always recoverable, never dies (user decision).
- **Care interactions** on HOME: **Feed** (snack costs 5 points → daily sink for together-time rewards), **Pet** (hearts burst), **Play**.
- **Mini-game "Snack Catch"**: ~10 Hz render mode, snacks fall in 3 columns, left/right buttons move the basket, 3 misses ends the round. Big happiness boost, small point earn capped per 6 h uptime (supplements, never replaces, together-time rewards), costs energy.
- **Reactions**: hearts+bounce when partner's pet is right-here; lonely bubble when alone too long; cheer at quest start; dance + pixel confetti on quest award.
- **Evolution**: baby → teen (100 XP) → adult (300 XP) — visible reward moments tied to the existing level formula.
- **Badge shop screen**: 50/100/200 points, transactional single-device check; purchases never reduce XP.
- Buzzer stays `BUZZER_ENABLED 0` pending hardware audit; pet sounds activate if it's ever validated.

## Stages (each ends with both DEVICE_ID compiles + `docs/PROGRESS.md` update)

0. **Scaffold**: create `D:\catch_me_pet`, fork+rename sources, shared toolchain yaml, bench scripts, docs skeleton. Verify: compile d1+d2, record sizes.
1. **Radio fork**: strip phone transport, add ack/state/code_hash to C5, ADV↔SCAN-only scheduler. Verify: compile; bench serial shows cycle.
2. **Persistence**: `pet_store` both backends. Verify: compile; reboot-persistence on board 1 (W25Q) and board 2 (internal).
3. **Session FSM + together quest**: invite/accept, hash-validated PINs, 30 s mutual-evidence timing, end-PIN, award-once. Verify: compile; **two-board bench run** (user enters bootloader per board), serial captures via `capture_serial_ts.py`.
4. **Pet core**: species/name bonding, needs decay, Feed/Pet/Play, moods + idle animations, evolution. Verify: compile; bench interaction via serial captures.
5. **Fun layer + shop**: Snack Catch mini-game, proximity/quest reactions, badge shop screen. Verify: compile + bench.
6. **Spot quest + heart challenge**: landmark table, GPS haversine check, heart FSM with honest no-sensor. Verify: compile; GPS bench on board 1 (outdoor spot walk flagged as pending user evidence).
7. **Polish + demo script**: README walkthrough, final bench checklist, docs/memory handoff.

## Division of labor

I compile and stage everything; physical steps only the user can do: enter bootloader (button combo, no reset button) per board and hold boards for two-board bench runs. I run serial verification against COM ports when flashed. Board facts carried over: app PID `03EB:8009` / bootloader `03EB:8008`, board identity by USB serial number, killed `bossac.exe` caution, board-2 RAM-only caveat (pet store fixes this with internal-flash persistence).

## Verification (end-to-end)

1. `arduino-cli compile --fqbn TinyCircuits:samd:tinyscreen -DDEVICE_ID=1/2` every stage; sizes logged.
2. Two-board bench: full together quest (invite → start PINs → 30 s mutual evidence → end PINs → award once; points/level persist across reboot on both boards); pet care loop (feed/play/pet, mood transitions, sad→recovery); mini-game round; repeat-safe badge purchase; heart quest with one real sensor + honest no-sensor on the other; spot quest on bench with GPS fix, outdoor spot walk pending user evidence.
3. `docs/PROGRESS.md` records exact commands, results, and what remains physically unverified — compilation is never claimed as hardware validation.
