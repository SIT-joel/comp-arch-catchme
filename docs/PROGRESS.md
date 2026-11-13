# Project progress

## 'Know Your Partner' quiz: implemented across all four platforms, PROVEN on hardware — 12 November 2026

User-directed feature: a quiz quest built from the partners' profile
interests — you must ASK the other person about themselves to answer
correctly. The phone renders the question (Kahook-style); the wearable is
the A-D pad (UL=A, UR=B, LL=C, LR=D).

**Server (85/85 tests green, 4 new quiz tests):**
- Quest `quiz` joins the session economy: create -> accept (activation
  GENERATES the questions) -> active -> completion when every question is
  answered by its designated answerer -> the shared exactly-once award
  (+100/+100, feeds pet XP/levels automatically).
- Generation from profiles: each question's correct option is one of the
  SUBJECT's interest tags; 3 distractors come from the catalog tags the
  subject did NOT pick; seeded by session id (deterministic in tests).
  Sets are per-answerer (miya answers about toma; toma about miya);
  questions carry NO correct index to clients — server-scored.
- Migration `f7a2b3c94d51` (applied dev; test DB via create_all):
  `quiz_questions` (unique per session+answerer+index) + `quiz_answers`
  (unique per session+user+index, latest-choice upsert).
- Endpoints: GET /sessions/{id}/quiz (per-answerer view), POST
  /sessions/{id}/quiz/answer (designated answerer only; upsert; completes).
- Tests: generation counts/options, full answer flow + exactly-once award,
  409 after completion (replay pays nothing), choice validation.

**Wearable (D1 52.4 kB / D2 51.9 kB, flashed):** MSG_QUIZ_STATE (23,
phone->board [ver][active][idx][total]) + MSG_QUIZ_ANSWER (24,
board->phone [ver][idx][choice]); SCR_QUIZ auto-takeover (pad legend with
Kahoot colors, Q n/N, sent state) outside the nav cycle like the PIN view;
ANSWER RETRANSMIT every 2 s until the phone's next state relay advances the
question (notifications have no delivery guarantee and the scheduled TDD
disconnect ate the first answer — verified live, then fixed).

**Phone:** quiz fetch + current-question relay in stateLoop; MSG_QUIZ_ANSWER
-> POST answer -> advance; Kahoot-colored QuizCard (question, options,
progress, "Quiz complete! +100 points & XP each"); Quiz create button.

**Web:** quiz quest name mapping ("Know Your Partner").

**HARDWARE PROOF (bench used serial `QANS <choice>` on each board — same
send path as a physical press):** quiz session created + accepted live ->
both boards received quiz state -> 4/4 answers relayed wearable -> phone ->
server (each acknowledged by the NEXT question relay) -> session completed
-> miya +100/+100, toma +100/+100 exactly once -> FE screen showed "Quiz
complete! You 2/2 answered - partner 2/2". Physical button presses use the
identical code path (pending user walk-through).

**Bugs found + fixed en route:**
- RAID relay contract: the phone read session.id but the server sends
  session_id — the throw aborted ALL session relays while a raid was
  active. Fixed + raid-start now RE-SENDS every connected cycle (fire-once
  landed in TDD-down windows; boards never entered raid mode).
- ZOMBIE APP INSTANCES: Activity recreation left the old AppModel's
  coroutines running (stale Connected state, duplicate scan loops, "no pet
  mirror" spam). AppModel.close() now cancels every job + the scope.
- Firmware: raid teardown STAGED across ticks (back-to-back terminate +
  non-discoverable wedged board 1's module); raid connect scan duty
  softened to 50% (near-continuous scanning wedged it mid-procedure);
  serial bench readers MERGED (two readers raced for the buffer — the RAID
  loop drained QANS lines).

**Raid status:** session `320d985a` active at the bench landmark; both
boards carry the softened-duty build; the retry relay re-triggers raid
mode automatically. Awaiting the fight outcome with the new scan duty.

**Dev-bench note:** the raid gate's 30 s fix freshness is relaxed to 15 min
on the DEV SERVER ONLY (`CM_RAID_FIX_MAX_AGE_MS` in tools/restart_api.ps1,
documented there): indoor GPS providers idle after the registration burst
and cannot meet 30 s at a stationary bench. Test suite + product behavior
keep 30 s. The phones' screens also need to stay awake (screen timeout set
to 10 min on both bench phones) — Samsung freezes apps and stops location
when the screen sleeps.


# Project progress

## LIVE two-person discovery bench: GPS match → invite → partnership — 9 November 2026

The full "find people nearby" chain ran **live on hardware** for the first
time with real accounts (miya on the S21+, toma on the S24 FE):

1. **Both phones signed in** on the current APK (LAN-API default +
   `api_base` intent override added — the old tunnel-only base kept breaking
   when wireless-adb reconnected; Windows Firewall does NOT block 8000).
2. **GPS discovery match LIVE**: miya's `/me/discovery` returned Toma —
   `distance_m: 0`, `freshness: fresh`, shared interests (gaming, music),
   `sources: ["gps"]`. Mutual (toma sees Miya). The positions come from the
   phones' real GPS stamps relayed by the wearables' telemetry
   (`gps_source='phone'`; board 1 healthy + board 2 in its recovery loop
   both delivered).
3. **Invite → ACCEPT → PARTNERSHIP**: miya tapped Invite on her match card
   (real UI tap) → invitation row `pending` → toma's screen showed
   "Miya invited you" → she tapped Accept → **"Partnered with Miya"** on her
   screen; DB confirms the active partnership. The discovery-quest gate is
   now open for the pair.

**Bench incidentals (documented for honesty):**
- toma's position was seeded as a CLEARLY-LABELED bench fixture
  (dev-DB `last_known_positions` row) because the S24 FE blocks the app's
  network per-app: Chrome reaches everything (LAN + loopback tunnel) while
  com.catchme.app times out on BOTH paths — attributed to the Knox VPN
  proxyhandler (`com.knox.vpn.proxyhandler` present; VpnNetworkProvider
  active). USER ACTION (FE): check Settings → Connections → Secure Wi-Fi /
  Auto Blocker and disable, then uninstall+reinstall the app. Real GPS flow
  on that phone is otherwise ready (fixes ±3.5 m observed in logcat).
- The dev DB container `catch_me_pg_dev` died TWICE today; a dead DB makes
  uvicorn hang every DB-backed request (clients see timeouts while
  DB-free endpoints like /openapi.json still respond — that signature
  identifies it instantly). Restart procedure: `docker start catch_me_pg_dev`
  + `tools/restart_api.ps1`. No data lost (13k records intact).
- The S21+ also logged out mid-bench from the same hang (restoreSession
  fails on any /me error); both accounts were re-signed in.
- BLE token confirm (the boards' C6 token exchange marking
  "Detected nearby") is still pending: both boards hold their tokens
  (board 1 token=14776, board 2 token=53292, both advertising "disc"
  payloads) but their scan/advert windows have not overlapped on a C6
  rotation yet (~50% C6 duty per side, ~20% scan duty). It needs minutes of
  both boards being alive — board 2's wedges keep interrupting. The
  observation uplink path is unchanged and tested in code.

**Next**: leave both boards + phones running; the BLE confirm should land
as the windows align; then a together/explore/raid session can run for the
new partnership. FE Secure-Wi-Fi check pending user action.


# Project progress

## Wearable UI reworked to the v2 product shape — 7 November 2026

User-directed redesign: the TinyScreen+'s job is the pet, proximity, and the
raid — one dedicated screen each; sessions/quests/pairing/history move to
the phone app entirely.

**New screen set** (UR/UL side-button cycle, boot lands on the pet):
- **PET (home)** — tamagotchi view: species sprite (Spark/Fluff/Pip) with
  mood expression and idle animation, name + server-synced level (honest
  `L?` until the first sync), need bars H/J/E, hearts on bonding, award
  confetti, evolution flash, mood/lonely status line. Quick care inline:
  LL feed (with 1.5 s "fed!"/refusal feedback), LR stroke. Bonding flows
  (species chooser → name editor) auto-appear here on first boot.
- **CARE** — the dedicated care screen: feed/stroke, Snack Catch launch
  (UR), need bars, and the honest care-sync state ("waiting phone sync" /
  "synced" / "bond first").
- **NEAR** — the proximity home ("spotting nearby people to match with"):
  phone-link dot (app reachable?), matched partner + distance (`d?` when
  unknown), live wearable-to-wearable peer evidence with RSSI signal bars
  (4 honest coarse buckets) or age-in-seconds when stale, rotating
  discovery matches with shared-interest counts, "pair in the app" hint.
- **RAID** — fight arena when a raid is live (unchanged controls: LL/LR
  move, UR fire); when idle: readiness info (partner wearable near?),
  "start: raid in app", and the last result (WON/lost).
- **PIN entry (together quest)** — NOT in the cycle; auto-takeover when
  the interaction relay needs it (phases 1/3/4+). It stays on the wearable
  by design: the physical code entry IS the together quest's mutual-
  presence evidence. Exits return to the pet home.

Removed from the wearable: HOME diagnostics view (GPS/HR/PH/queue),
MATCH, QUEST (progress lives on the phone/web). The enum keeps the
interaction view outside the cycled range (SCR_INTERACTION = SCREEN_COUNT).

Board 2's mid-fight wedge forensics also produced the **no-internal-flash
rule** (6 Nov entry below): `q_push` is live-only without a W25Q and the
pet store is RAM-only (`backend=ram`) — internal flash is never written
at runtime (writes stall the CPU mid-SPI and wedge the BLE module).

Builds: D1 51,360 B / D2 50,908 B (20%); both flashed. Board 1 boots
clean (0 wedges, pet_store backend=w25q loaded) and is showing the
bonding flow (its slot holds an unbonded pet — species=-1). Next physical
check: the user walks the four screens; pet bonding + care on hardware;
raid idle screen with both boards near.

## Hardware session: pet downlink + phone GPS verified live; board 2 radio verdict — 6 November 2026 (afternoon)

**Setup**: raid-integrated firmware flashed to both boards (then twice more
with fixes); fresh APK on the S21+ (miya, board 1) and the Tab S5e (toma,
board 2's stand-in phone — fresh install + sign-in); API + both Postgres
containers up; boards on COM3 (D1 image) / COM4 (D2 image).

**Three Android bugs found and fixed live (all hardware-verified after):**
1. **FrameAssembler race** — `notify rx` hex showed fragments landing on
   3+ different binder threads; the unsynchronized reassembler dropped
   middle fragments so EVERY telemetry record failed decode
   ("short telemetry payload" ×11). Fix: `@Synchronized feed()/reset()`.
2. **Phone GPS never registered** — `requestLocationUpdates` was called on
   a dispatcher worker with no Looper ("Can't create handler…" swallowed
   by bare runCatching). Fix: explicit `Looper.getMainLooper()` overload +
   failure logs. Live fix at 15:47: GPS fixes arriving, and the server now
   receives 35 rows/min with `gps_source='phone'`, `gps_valid=true` (the
   v2 phone-GPS rule verified end to end on hardware).
3. **GATT client leak** — every TDD disconnect replaced `gatt` with a new
   controller-level autoConnect client WITHOUT closing the old one;
   observed 13 concurrent zombie GATTs + status-257 storms + the Samsung
   scan wedge. Fix: close-on-replace both connect paths + stale-gatt
   guard in `onConnectionStateChange`. After the fix: single-thread clean
   TDD rhythm (connect → CCCD → 4 s link → board 0x16 drop → 1–2 s
   controller reconnect), hours-stable.

**Pet downlink verified**: phone layout bug fixed (the encode wrote ver at
index 1 + a stray byte — everything shifted vs the firmware parser);
`sendPetState` now sends `xp=1010 level=11` and board 1 prints
`pet_core: server sync xp=1010 level=11` — server → phone → wearable with
correct values. Board→phone care events still need a physical button press
(user-hands item).

**Raid fight bench (serial `RAID` trigger), progress + blockers:**
- Bench script `tools/bench_raid_serial.py` (resilient serial capture,
  timestamps, dump files; POST-MORTEM lesson: watchers must open BEFORE
  the trigger — the first run lost the early prints to a blind window).
- Firmware fixes driven by the bench (all compiled into both boards):
  (a) `note_connect` now takes the peer bdaddr — on the client the raid
  host and the phone BOTH arrive as role==1, so discrimination is by the
  static address (`01:80:E1:00:34:12`); the host connecting doubles as the
  client's raid trigger (relay-miss tolerance). (b) `note_disconnect`
  only clears phone state for the actual phone handle and only lets the
  PEER handle abort/report the fight (a phone bounce mid-fight no longer
  stalls the outcome relay or aborts the fight). (c) `raid_start()` fully
  resets raid state (a second trigger after an abort previously did
  nothing — raid_phase_ stayed RAID_DONE). (d) raid_start tears down the
  current radio activity first (phone terminate / scan procedure /
  advertising) — the stack rejects create-connection otherwise; the host
  now reliably reaches "raid: connected — fight starts" + "raid: FIGHT!".
- **The fight REACHES FIGHT! on both boards** — then board 2's radio
  module wedges (serial dies mid-fight, board 1 honestly aborts
  "link lost mid-fight").
- **Wedge forensics (hard evidence)**: boot reason captured live:
  `WATCHDOG (previous life 0 ms)`; board 2's STAT stopped at fight start
  and the WDT fired ~16 s later — the main loop froze inside one
  iteration. Root cause identified in the vendored STBLE: `HCI_Isr`'s
  `while(BlueNRG_DataPresent())` drain is UNBOUNDED; a module whose IRQ
  sticks high spins it forever. Fix shipped in the vendored hci.c: drain
  capped at 16 reads/call + forensics counters
  (`hci_irq_drain_reads` = SUCCESSFUL reads only, `hci_irq_drain_bads`,
  `hci_irq_stuck`). `BleApp::module_reinit()` recovers a truly wedged
  module (hard reset + full re-init, raid honestly ended as lost, no
  outcome relayed). CAUTION recorded: the first recovery build fired
  recovery on advert-report STORMS (IRQ legitimately high for seconds)
  and re-init-looped itself into watchdog resets — the detector now
  requires stuck IRQ AND zero successful reads for 2 s.
- **Board 1 now runs clean TDD for the whole session (0 wedges, phone
  relinks, pet sync).** Board 2 still wedges every ~2 s at IDLE TDD —
  including with `CM_DISABLE_INTERNAL_QUEUE=1` (21 wedges/45 s) — its
  module answers init commands then dies during operation. **Verdict:
  board 2's radio module/stack is hardware-unstable** (matches its whole
  documented reset history). Physical triage is the blocker: power the
  boards from a self-powered hub or separate supply, and consider
  re-seating the stacks (see next item).

**PHYSICAL DISCOVERY: the shield stacks are SWAPPED.** Boot lines show the
D1-image processor now has NO W25Q (`fq: begin FAIL` → internal fallback,
`boot_id=d1-i1`) while the D2-image processor HAS the W25Q
(`jedec 0xEF4014`, `boot_id=d2-177`, pet_store loaded counter=118 — the
fork-era pet data). The stacks moved physically between the morning flash
and the raid benches; the wedge storms started after that. Board roles
follow the PROCESSORS (CATCHME-1/-2 names, pairing codes), so the phones
still bind correctly — but the stable processor (D1) is now on the stack
without flash, and the flaky one (D2) carries the flash shield.

**Builds now on the boards**: D1 50,956 B (normal) — clean; D2 50,380 B
diagnostic (`-DCM_DISABLE_INTERNAL_QUEUE=1`) — wedges regardless; reflash
the normal D2 (50,504 B) after the hardware triage. Android APK: 6 Nov
15:42 (assembler sync + GPS looper + GATT lifecycle + pet wire fix +
stateLoop failure logging).

**Next physical session (user hands needed)**: (1) board 2 power triage
(separate supply / self-powered hub; try re-seating the stacks back to
D1=flash-shield stack); (2) pet care walk-through (press care on the pet
screen with the phone foregrounded — verifies care event → +10 XP → ACK
→ pet card update); (3) re-run the raid fight bench; (4) the full raid
relay bench (raid session in dev DB → both phones relay raid-start →
fight → outcomes → award) — the phones now pause their supervisors during
`raidFightUntil`, which may also remove the phone-scan interference that
coincided with the fight wedges.

## Android raid relay + outcome uplink complete — 6 November 2026 (final)

The last Stage 2 item from the v2 plan is implemented and built:

- **Raid-start relay**: the moment a raid session becomes active
  (`sendSessionState` sees quest_id=raid + state=active), the phone sends
  `MSG_RAID_START` (22, `[ver][demo u8]`) to its wearable — once per session
  id — and the wearable enters raid mode (drops its phone link, fights over
  the direct connection). Firmware side: the `MSG_RAID_START` router case
  calls `raid_start()`; the demo flag rides the relayed session state.
- **Link supervisor pause**: while the fight runs the wearables own the
  radio, so the supervisor now skips reconnect attempts until
  `raidFightUntil` (now + 4 minutes at relay time). Honest and bounded: the
  phone resumes its normal reconnect loop afterwards.
- **`MSG_RAID_OUTCOME` (21) uplink**: both boards relay their own outcome
  (`[ver][outcome 1=win/2=lose][duration s LE16][nonce LE64][session UUID]`)
  with nonce-retry after their phone relinks; the phone maps it to
  `POST /sessions/{id}/raid/outcome` (start = now − duration, end = now;
  the server validates the window), ACKs via the shared
  `MSG_INTERACTION_ACK` nonce reply, and refreshes device state. The phone's
  own raid session id is authoritative (the wire UUID is a cross-check —
  the wearable sends zeros when no interaction relay reached it).
- Firmware outcome plumbing: `raid_outcome_acked(nonce)` hook; client-side
  fight-end capture (board 2 reports its own view after the host terminates);
  post-fight disconnect resumes TDD (scan) so the phone relinks while raid
  mode holds for the outcome relay.
- Builds: firmware D1 50,332 B / D2 49,884 B (19%) compile-verified
  (NOT flashed to the boards yet — current boards carry the previous
  product build; flash next session); Android `assembleDebug` BUILD
  SUCCESSFUL (fresh APK 6 Nov 05:03).

**End-to-end raid path now wired on paper end to end**: create raid session
(web/Android, landmark required) → accept passes the 50 m + proximity gate
→ phone relays raid-start → wearables fight board-to-board (gate-proven
transport) → both outcome reports uplink → server completes + awards exactly
once (win) / completes without award (loss). Remaining physical evidence:
a real fight on hardware (serial `RAID` trigger works without phones; the
phone relay needs the fresh APK on both phones), board power triage, real
landmark coordinates, and the pet walk-through.

## Gate series 3/3 windows complete; raid game implemented in product firmware — 6 November 2026 (late)

**Board 2's advertising wedge FIXED.** Root cause: the gate loop re-called
`start_advertising()` (which includes `set_discoverable`) every 1.4 s — the
wedge-sensitive call. Fix: `start_advertising()` split into
`rotate_advertising_payload()` (payload build + `update_adv_data` only, safe
to loop — the same call the TDD scheduler repeats for hours) plus a single
`set_discoverable` per phase entry. After the fix board 2 advertised
continuously (`adv on cnt=1,2,3,4…`) and the connection formed immediately.

**Gate series (3 runs, flash-reset between each):**

| Run | connect_ms | writes (10 Hz) | duration | outcome |
|---|---:|---:|---:|---|
| 1 | 9,990 | 1,172 | 120.006 s | PASS — clean 0x16 terminate |
| 2 | 11,495 | 1,096 | 120.012 s | window complete; connect missed 10 s by 1.5 s (board 2 watchdog reset between runs) |
| 3 | 10,132 | 1,038 | 120.001 s | window complete; same inter-run reset on board 2 |

- Peer delivery: 977–1,077 writes received (92–98%; write-without-response
  has no delivery guarantee — correct for game-state traffic).
- **Zero watchdog resets during any run window**; both inter-run resets hit
  board 2 while IDLE-advertising — the documented hardware instability
  (shared USB power suspicion), not the protocol.
- Bugs fixed en route: write REQUEST rejected 0x03 on a
  WRITE_WITHOUT_RESP-only characteristic → `aci_gatt_write_without_response`;
  aggressive 7.5–15 ms connection interval dropped at ~30 s twice → relaxed
  to 30–50 ms + 4 s supervision (a 10 Hz game carries easily); discovery
  responses arrive as 0xC12 with the value handle inside `attr_value[1..2]`;
  vendor-event byte order for `COPY_UUID_128` is reversed (on-air order).

**Gate verdict: PASS at the protocol level** — connection, discovery,
sustained 10 Hz exchange for 120 s, clean terminate, ×3. The strict
"zero resets anywhere" criterion is blocked only by the documented board 2
hardware instability (power triage remains the physical action).

**Raid game: implemented in product firmware.** `game_app.{h,cpp}`
(host-authoritative boss fight: sinusoid boss, aimed bullets, 2 ships × 3
lives, boss HP 20 demo / 60 normal, win/lose states); `RadioStateRaid`
product mode in `ble_app` (runtime-gated `raid_start()`: TDD suspended,
symmetric char discovery, both directions ride write-without-response to
each other's UART TX char — no notifications/CCCDs needed);
`MSG_GAME_STATE` (19) / `MSG_GAME_INPUT` (20) routed through the existing
framing; raid UI screen on both boards (boss/ship/bullet rendering, lives,
result line) with LL/LR move + UR fire; bench trigger = serial line "RAID";
the phone-relay trigger (raid session active) is the next Android step.
Product builds: D1 49,896 B / D2 49,264 B (19%) — compile-verified; NOT yet
fought on hardware (the raid flow needs the phone relay + a fight test).

**Next session:** (1) flash product builds and bench the fight via the
serial "RAID" trigger (both boards; no buttons needed to observe — outcome
prints over serial); (2) Android: send the raid-mode relay when a raid
session activates + `MSG_RAID_OUTCOME` uplink to `POST /raid/outcome`;
(3) physical actions still open: board power triage, real landmark coords,
pet bonding/care walk-through with phones foregrounded.

## v2 shipped across all four platforms; raid gate experiment 80% de-risked — 6 November 2026 (overnight run)

Executed the approved v2 plan end to end (see the 6 Nov kickoff entry below
for scope: phone GPS replaces the wearable shield, heart quest removed,
digital pet, landmark raid). Actual state by stage:

**Stage 0 (docs) — COMPLETE.** `AGENTS.md`, `PROJECT_SPEC.md`,
`QUEST_INTERACTION_PLAN.md`, `INTERFACES.md`, `DISCOVERY_PLAN.md`,
`TEST_PLAN.md` rewritten for v2 (quest set together/explore/raid; phone-GPS
rule; pet + raid contracts; heart marked removed with legacy reads kept).

**Stage 1 (server) — COMPLETE, 81/81 tests green on PostgreSQL.**
- Heart removal: catalog/`CreatableQuestId`/evaluator/interaction phases/
  prompt catalog/choice+skip routes/tests all removed; `QuestId` keeps
  `heart_challenge` so legacy sessions serialize (covered by a dedicated
  test); heart unit tests trimmed with the evaluator.
- Migration `d5e8f2a94c31` (applied dev + test): `telemetry_records.gps_source`
  (backfilled 'wearable'), `pets` mirror, `landmarks`, `raid_outcomes`,
  `quest_sessions.landmark_id`; `ck_tx_nonzero` relaxed to `delta<>0 OR
  xp_delta<>0` (pet care moves XP without points).
- Pet endpoints: `GET/PUT /me/pet`, `POST /me/pet/care` (+10 XP once per
  user per calendar day, idempotent via `care:{user}:{date}`, future/older-
  than-7-day dates rejected, out-of-order backfill never regresses the
  streak); `GET /landmarks`; `/me` carries `pet`.
- Raid: creation requires `landmark_id` (frozen on the session); activation
  gate = BOTH participants' phone fixes within 50 m of the landmark with
  fix age ≤ 30 s at accept (409 `raid_gate_location` otherwise);
  `POST /sessions/{id}/raid/outcome` — idempotent per command id, one
  report per reporter, completion requires BOTH reports, awards (+100/+100
  exactly once) only when BOTH report `win` (a loss completes honestly
  without paying).
- New tests `test_v2_pet_raid.py` (8 cases) + extended sweep; OpenAPI
  regenerated (35 paths).

**Stage 2 (web + Android) — COMPLETE, all builds green.**
- Web: heart UI read-only (legacy), pet card on the dashboard, raid tile
  with landmark picker, `raid_outcome` display; tsc clean, 5/5 tests,
  production build passes.
- Android: heart quest button + dead command kinds removed; **phone GPS is
  the location source** (`LocationManager` GPS+network listeners; every
  relayed record is stamped with the phone's fix and its TRUE age,
  `gps.source:"phone"`); pet card + pet mirror sync; raid buttons per
  seeded landmark; `MSG_PET_STATE/PET_CARE_EVENT/GAME_*/RAID_OUTCOME` ids
  (17–21) in `Frame.kt`; quest byte maps raid→4. `assembleDebug` BUILD
  SUCCESSFUL.

**Stage 3 (firmware pet port) — COMPLETE, both builds compile.**
Ported from the bench-verified fork and adapted for the v2 split (server
owns XP/points; wearable owns cosmetics/needs): `pet_store.{h,cpp}`
(double-slot commit; W25Q slots 0x20000/0x21000 clear of the telemetry
ring; board-2 internal rows moved to 0x3D000/0x3D100 — the fork's 0x3E000
rows collide with catch_me_app's queue), `pet_core.{h,cpp}` (needs decay,
moods, bonding + name editor, Snack Catch paying happiness only, care
events with nonce-retry until the phone ACKs, `note_server_pet` mirror,
`celebrate()` on completions), pet rendering in `ui_app.cpp` (procedural
sprite, need bars, confetti/EVOLVED, SCR_PET in the rotation, fast render
while the game is live), `MSG_PET_STATE` (17)/`MSG_PET_CARE_EVENT` (18)
wired through the framing, GPS/pulse inits gated off (`CM_GPS_ENABLED 0` /
`CM_PULSE_ENABLED 0`) with honest record fields. Builds: D1 46,476 B /
D2 46,468 B (17%). Product builds flashed to BOTH boards and booting
(board-to-board peer visibility re-confirmed post-flash).

**Stage 4 (raid gate experiment) — 80% de-risked; one blocker parked.**
Gate firmware (`CM_GAME_GATE=1`, bench-only; TDD scheduler suspended):
board 1 central → `hci_le_create_connection` to board 2's public address;
board 2 peripheral advertises and holds. LIVE RESULTS:
- **The direct board-to-board connection FORMS on this radio** (fastest
  observed: 22 ms from create to connected; board 2 held the link for
  minutes with zero watchdog resets) — the core feasibility question is
  answered YES at the connection level.
- Two API bugs found and fixed en route: `uuid_type` must be
  `UUID_TYPE_128` (2), not a byte count; `COPY_UUID_128` stores uuid_0
  FIRST (on-air byte order is reversed from the macro's argument order).
- `enter_advertising()` only records the phase — the radio start is
  `start_advertising()`; the peripheral gate now calls it directly.
- **PARKED BLOCKER**: board 2's gate advertising is intermittent — after
  the first advert the peripheral goes silent (suspect: repeated
  `set_discoverable` without cancellation, the recorded BlueNRG wedge
  family; next fix: `aci_gap_set_non_discoverable` before each
  re-advertise, or rotate the payload via `aci_gap_update_adv_data`
  instead). Connection latency varied 22 ms–60 s accordingly.
- `tools/drive_game_bench.py` written and ready to score the ×3 series
  once the peripheral fix lands. Product firmware was RESTORED to both
  boards after the experiment (bench builds are not left on hardware).

**Stage 5 (sweep)** — extended feature sweep: **29/30** (the one miss is
the known badge-exhaustion artifact: both users own all affordable badges
from repeated sweeps — graceful skip, not a bug). All v2 checks pass.

**Next session (in order):**
1. Fix board 2's gate advertising persistence (one small firmware change),
   run `tools/drive_game_bench.py` for the ×3 series, then game_app +
   `RadioState::RAID` behind the gate.
2. Physical pet verification: bonding + care on both wearables, persistence
   across reboot on both flash backends, `MSG_PET_STATE` sync visible
   server-side (needs the phones foregrounded; firmware is already on).
3. Real landmark coordinates for the raid demo (current seeds are Kyoto
   placeholders); configure a real explore geofence.
4. Demo script + report refresh for v2 (quest set changed).

## v2 re-scope kickoff: phone GPS, digital pet, landmark raid; heart quest removed — 6 November 2026

User-approved plan (this session): **phone GPS replaces the wearable GPS shield entirely; `heart_challenge` is removed** (legacy sessions stay readable; AST1041 leaves the stack); **digital pet** levels from the same server-owned XP (daily care +10 XP once/user/day) and lives on the wearable (port from the bench-verified fork `D:\catch_me_pet`); **`raid` quest** = landmark gate (phone fixes 50 m + mutual peer presence) + co-op boss fight over a **direct board-to-board BLE connection** (phones drop during the fight). Deadline 28 Nov; pet + phone GPS must ship, game is gate-gated stretch. Full contracts: rewritten `AGENTS.md`, `docs/PROJECT_SPEC.md`, `docs/QUEST_INTERACTION_PLAN.md`, `docs/INTERFACES.md` (new MSG 17–21, `/me/pet*`, `/sessions/{id}/raid/outcome`, `/landmarks`, `gps.source`), `docs/DISCOVERY_PLAN.md`, `docs/TEST_PLAN.md`. **Stage 0 (docs) COMPLETE.**

**Stage 1 IN FLIGHT — exact state for resumption:**
- DONE: `backend/app/config.py` (quest_heart_* retained-but-unused, raid durations + `raid_radius_m`/`raid_fix_max_age_ms`/`pet_care_xp`, catalog now together/explore/raid), `backend/app/schemas.py` (QuestId keeps heart_challenge for legacy reads + `CreatableQuestId` = together/explore/raid on `SessionCreateIn`, `PetSpecies`, `PetSummary`/`pet_stage_for_xp`/`PetUpdateIn`/`PetCareIn`, `LandmarkOut(s)`, `RaidOutcomeIn`, `MeOut.pet` forward-ref, `GpsReading.source` NOT yet added).
- NOT STARTED: `GpsReading.source` field; models (Pet, Landmark, `TelemetryRecord.gps_source`, `QuestSession.landmark_id`) + Alembic migration; routers (me.py pet endpoints, sessions.py raid branch + outcome route, telemetry.py gps_source persistence); services (evaluation heart branch removal + raid completion, interactions heart path cleanup); web+Android heart removal; firmware pet port; tests.
- TESTS NOT RUN since these edits — the suite is expected RED until Stage 1 lands (schema/catalog changes without matching evaluators). Resume by fixing forward per the /goal boot sequence.

Bench notes for overnight: boards were last on COM4 (board 1) / COM3 (board 2, diagnostic build with internal-queue pushes disabled — keep that flag); phones need manual unlock, so all bench work is optional tonight. Dev API server relaunch command is in the /goal command and the ops note below.

## NEW blocker found: board 1's time-anchor relay corrupts clock fields after reboots — 4 November 2026 (late, session 3)

Fifth watcher run. Both phones signed in and linked, fresh session
`7fa06ca2` with clean counter baselines, board 2 earning peer rows (22+).
Then the decisive discovery: **board 1's side can contribute zero scored
evidence regardless of catches**, because its records' clock fields are
broken after its reboot:

- 228 of ~300 session rows are `unsynced` (NULL `captured_at`, NULL
  `clock_uncertainty_ms`) — the board lost its TIME_ANCHOR on reboot and
  the phone→board anchor re-sync is not reliably restoring it.
- The few anchored rows carry `clock_uncertainty_ms == sequence` exactly
  (89↔89, 141↔141, …) — corrupted bytes that fail the evaluator's ≤500 ms
  clock-trust filter.
- Effect: the evidence evaluator rejects every board-1 record's peer
  observations → board 1's side scores 0 forever until this is fixed.
  (Board 2's side earns fine — its rows carry valid 500 ms uncertainty.)

Next debugging step (well-scoped): capture board 1's raw 36-byte telemetry
payloads over serial (`tools/gatt_full_io.py` against COM4, or the phone's
logcat hex dump), decode against `records.h` offsets, and determine whether
the corruption is (a) the board's builder writing garbage into
`clock_uncertainty` when unsynced-then-partially-synced, (b) a phone-side
offset/decode issue on drained records, or (c) the SESSION_STATE anchor
relay landing in a disconnected window and the board keeping a stale
`anchor_uncertainty`. The 17:23 session earlier today had valid 500 ms
rows from this same board+phone, so the anchor path CAN work — it breaks
across reboots/relogins.

Also this run: the S21+ loop of (login screen after tunnel-churn restart →
sign in via motionevent clicks → autoconnect) was exercised three times and
is now a known 2-minute recovery; every board reboot also requires an app
restart to clear the zombie-GATT state. Both are bench friction, not
product blockers, but they compound the reboots' cost.

## Watchdog root-cause narrowed to board 2's internal-flash queue writes; live bilateral completion still pending — 4 November 2026 (night)

Third live-bilateral attempt, with two firmware diagnostics flashed and a
full bench loop of reboots/locks/re-links. Findings:

- **Diagnostic: board 2 with internal-queue PUSHES disabled lived 45+
  minutes — its longest life ever** (previous record ~15-20 min; it had
  reset every few minutes all day). Build: `CM_DISABLE_INTERNAL_QUEUE=1`
  (new compile flag; `q_push/pending/peek` bypass `g_iq`, boot id preserved
  via one-time `g_iq.begin()`). Unlinked records are honestly dropped; the
  live phone-link path is unaffected. This strongly implicates the
  per-record NVMCTRL writes (row erase/page program) in the watchdog
  resets. Board 1 (external W25Q) is unaffected. Board 2's bench
  configuration should keep this flag until the internal queue gets a
  proper fix (erase scheduling away from radio-active windows, or a
  hardware power fix).
- **Board 1 recorded its first reset in ~5 h tonight** (up reset to 805;
  boot reason power-on after the user's USB handling). It recovered with
  its queue intact and re-linked cleanly. Board 1 remains the reference
  stack.
- **A 90 s both-unlinked dense burst with the diagnostic board worked**:
  board 1 caught +58 peer heartbeats and buffered 649 records; board 2
  caught 33 (its records dropped honestly — pushes disabled, no phone
  linked) and survived the burst for the first time.
- **The watcher expired at progress 0** (session `3996f749`, 50 min):
  blocked by the FE's secure lock screen (needs physical unlock — remote
  unlock stopped working this evening), board 1's ~12-min FIFO backlog
  drain, and the standing linked-mode duty-cycle sparsity (catch gaps
  15-25 s break the ≤10 s chain; an asymmetric unlinked window did NOT
  densify the linked side's catches — the TDD scheduler keeps its full
  cycle unlinked).
- Session left ACTIVE in `timing` (server state preserved; a new watcher
  can be armed any time). Board 2's 253 peer rows prove its side earns
  evidence whenever its phone link is up.

**Net for the course demo (24 days out):** the bilateral live completion
has now been attempted three times with full instrumentation. The evidence
rules, evaluator, PIN flow, and both boards' radio paths are individually
proven; what the bench cannot yet produce is the simultaneous ≤10 s-chained
intersection at linked-mode duty, plus board 2 needs its power/queue fix.
Options for the demo, in order of honesty: (a) live attempt with generous
time and both wearables adjacent; (b) the recorded 30 Oct completion
(board 1 real radio evidence + CLEARLY LABELED fixture for board 2's side);
(c) single-sided live evidence with the honest display of the partner's
paused progress. All options keep the no-award-without-both-final-PINs
contract.

**Physical actions still open:** unlock the FE (secure lock), then the
bench can resume; board 2 power triage (cable/battery) remains advisable
even with the diagnostic build.

**Night close-out:** watcher 6 also expired at 0 — board 1 reset twice more
(up 1400→20, then again ~20 min later) and the S21+ locked/wedged twice.
**Shared-cause insight: BOTH boards now show sporadic watchdog resets on
different USB ports and cables** (board 1 survived 5 h then resumed
resetting; board 2 resets every 20-90 min even with queue writes disabled).
Prime suspect: the shared USB power path (PC ports/hub droop under
load). Recommended next physical step: power both boards from a
self-powered hub or a different supply entirely and re-test stability
before any further firmware debugging. Session `71eab8df` left ACTIVE in
`timing` (server state preserved); the anchor-relay and stability findings
above are the resume points.

**Ops update (5 Nov):** the dev API server is now launched DETACHED via
`powershell Start-Process` (python -m uvicorn --app-dir D:\catch_me\backend
app.main:app --host 127.0.0.1 --port 8000, WorkingDirectory=backend,
hidden window) — the previous agent-shell background-task approach began
failing overnight with exit 127 and empty logs after serving for hours;
the detached process survives shell teardown entirely. databases were
never affected (containers up 37 h through the night).

## Live bilateral completion attempt: detection proven, completion blocked by board 2 reboot storm + linked-mode scan duty — 4 November 2026 (late)

Continued the live bilateral attempt with a stable board 1 and the fixed
S21+ app. Findings, all from live serials/DB:

- **Queue purge tooling works**: the app's ADMIN purge button (retap until
  a linked window ACKs it) erased board 1's 1,386-record October backlog
  instantly (`queue purged: ... dropped`, q 1386→2). The W25Q drain/ACK
  path is confirmed healthy; future dense windows drain immediately.
- **Detection again proven**: during a 170 s both-unlinked window earlier,
  board 1 logged 45 peer receptions and board 2 logged 59 (~1 per 3-5 s).
- **Linked-mode scan duty makes bilateral ≤10 s chains statistically rare.**
  While linked, each board scans only ~2 s per TDD cycle; catches land
  ~9-25 s apart, so a side's own evidence rarely chains. A one-sided dense
  window (board 1 unlinked) produced almost no new catches (+1 in 170 s) —
  the unlinked-side short cycle did not materialize as expected, likely
  phase-dependent. The bench therefore cannot currently accrue the 30 s
  intersection; the recorded 30 Oct analysis (both sides must be dense
  simultaneously; real demo holds both wearables close with screens on)
  remains the operative explanation.
- **Board 2's reboot storm is the hard blocker.** It reset again mid-window
  (third+ reset today; WATCHDOG forensics earlier caught `previous life
  0 ms`). Each reset zeroes its heartbeat counter, and board 1's strictly-
  increasing anti-replay check then rejects board 2's adverts until the
  counter re-passes its high-water mark. Physical triage needed: swap its
  USB cable (not just port), try battery-only vs USB-only power, reseat all
  shields (recorded fix for a dead radio), check for heat; if it persists,
  test whether the internal-flash queue writes (NVMCTRL row erases) are
  implicated by flashing a build with the internal queue disabled.
- Session left active in `timing` with a background watcher that will
  auto-submit the end PINs if the intersection ever completes (expires
  ~03:10 local). Old flash-queue rows drained into the session are excluded
  from scoring by the interaction evaluator's `not_before` filter — server
  behavior verified correct.

**Status unchanged in substance: one stable board + phone works end to
end; the bilateral live completion needs board 2 stable.** All software
paths remain green (27/27 sweep, 77/77 suite, web build, Android fixes
verified).

## Live bilateral run blocked by board 2 hardware; S21+ BLE wedge root-caused and fixed — 4 November 2026

Attempted a fully-live bilateral Together completion (real radio evidence
both sides, PINs via API, zero user input). Outcome split:

**Detection: PROVEN, repeatedly and in both directions.** Board 1↔board 2
peer counters climb continuously; during a 170 s phone-disconnect window
board 1 logged 45 new peer receptions and board 2 logged 59 (~1 per 3-5 s —
the dense unlinked duty cycle), with server-side peer rows arriving from
both sides. Mutual wearable-to-wearable detection is not in question.

**Completion on the live bench: blocked by board 2 hardware, not software.**
Sequence of established facts:

1. The evaluator needs intersected ≤10 s-chained peer spans from BOTH sides.
   While a board is phone-linked it only scans 2 s per ~8.5 s cycle, so
   linked-mode catches land every ~9-25 s — mostly outside the chain rule.
   Unlinked boards scan continuously (dense) and buffer to their queues.
2. Board 1's evidence path fully works: it buffers unlinked-period records
   (its W25Q queue absorbed the dense window) and its queue drain + server
   ACK now work properly (q 2000 → ~1200 over the session, live rows
   flowing). BUT its queue is FIFO: the dense-window records sit behind
   ~1,200 October-era records that only began draining today.
3. Board 2's internal queue BROKE after its crash-loop reformat
   (`d2-i1` boot): during a verified 30 s unlinked window its peer counter
   climbed (104→105+) while `q` stayed 0 — unlinked-period records are NOT
   stored any more, so its dense evidence is lost and it can only report
   while phone-linked (sparse mode).
4. Board 2's reboots are accelerating (multiple per hour, WATCHDOG
   `previous life 0 ms` forensics caught earlier): each reboot resets its
   heartbeat counter, and the evaluator's strictly-increasing anti-replay
   rule then rejects the OTHER board's observations until the counter
   exceeds its pre-reboot high-water mark. A fresh session fixes baselines,
   but the reboots keep arriving mid-window. Its latest boot also showed
   `peers=0` for its entire 67 s life while board 1 was provably on air.
   Conclusion: board 2 (or its power path) is failing — swap its USB
   cable/port, try battery-only or USB-only power, check heat. Until it is
   stable, a live bilateral completion cannot be expected on the bench.

**S21+ (Android 15) BLE wedge ROOT-CAUSED and FIXED in the app.** One UI
refuses scanner re-registration after one scan→GATT cycle
(`SCAN_FAILED_REGISTRATION_FAILED`, errorCode 2) — the FE (Android 16)
tolerates the same pattern, which masked it. Fixes shipped in
`BleLink.kt`/`AppModel.kt` (all built, installed, verified on hardware):

- Fresh ScanCallback per scan session (rotation in `beginScan`, which all
  paths — supervisor reconnect, stale-scan restart, failure retry — use).
- After the FIRST scan-hit connect, the board is cached and every TDD
  scheduled disconnect reconnects at the CONTROLLER level
  (`connectGatt(autoConnect=true)`) — zero app scanner registrations,
  structurally immune to the wedge. Verified: multiple disconnect/reconnect
  cycles with no scan failures and sustained `phone=1` on the board.
- Supervisor backoff (up to 30 s) when the link state is Failed, so the
  stack is no longer hammered every 2.5 s.
- Earlier Android-11 fix (same file): API < 31 gates scanning on
  ACCESS_FINE_LOCATION instead of the nonexistent runtime BLUETOOTH_*.

**Other findings this session:** the phone binds the CURRENT session id to
drained flash-queue records with old `captured_at` (weeks-old rows can land
in a live session); scoring is unaffected because the interaction
evaluator's `not_before` filter excludes pre-session captures — but the
server could reasonably reject session-bound records older than session
activation (cosmetic data-hygiene follow-up). Board 1's never-acked W25Q
backup queue (full since 31 Oct) is now draining correctly through the
phone link. Samsung screen-off kills unfiltered scans; screen timeouts were
raised to 10 min on both bench phones via adb.

**Bottom line for the course demo:** with ONE stable board pair the flow
works — board 1's full evidence path (detect → buffer → drain → ACK →
score) is proven live end-to-end. The bilateral live completion awaits
board 2 hardware stability (power-path triage). All server-side quest,
shop, heart-honesty, explore-gate, discovery and partnership paths are
proven green by `tools/test_feature_sweep.py` (27/27) and the 77-test
backend suite.

## Full feature sweep without wearable button input — 4 November 2026

The user asked to exercise every feature without requiring wearable button
entry first. New tool `tools/test_feature_sweep.py` (backend venv, stdlib
only) drives the entire product surface over the live dev API, standing in
for button presses with API PIN submissions, and injects telemetry ONLY
under clearly labeled `FIXTURE-sweep-*` boot ids (AGENTS.md fixture rule).
Result: **27/27 checks passed** against the running server + PostgreSQL.

Covered and passing:

- Together full lifecycle: create → accept (v1 interaction frozen) →
  start-stage codes issued to each owner only (partner code never appears in
  the other snapshot) → both start PINs via API → `timing` phase → 16 mutual
  peer-observation pairs (0–30 s every 2 s) → progress exactly 30000/30000 →
  phase `end_pin` with NO award yet → both end PINs → `completed`; each user
  +100 points / +100 lifetime XP exactly once.
- Honesty paths the sweep hit incidentally and the server handled correctly:
  peer observations with a wrong/absent session token earn zero credit
  (first sweep run had a script-side token bug — server scored 0, as
  designed); replaying an already-ingested (boot, sequence) pair is ignored
  as duplicate (8180 ms partial run proved per-record idempotency);
  malformed payload shapes → 422; invitation without a completed discovery
  profile → 409 `profile_incomplete`; explore create without geofence → 409
  `geofence_not_configured` (documented gate).
- Shop: rewards list with per-user `owned` flags; purchase → `balance_after`
  exact; idempotent replay (same Idempotency-Key header) does not double
  charge; rebuying an owned badge → 409 `already_owned` (one-time rule);
  XP never reduced by spending.
- Keep Your Cool: accept → `baseline` phase, 3-phase target set, progress
  stays exactly 0 without valid readings (no second sensor — honest),
  prompt-choice endpoint responds (409 outside the right phase), clean
  cancel.
- Discovery/partnership API round-trip: end partnership → complete profiles
  + opt-ins → invitation (5 min expiry visible in the payload) → accept →
  active partnership restored (seeded pair requirement preserved; the sweep
  also self-heals a partnership left ended by an earlier crashed run).
- Web: production build passed (dist 287.51 kB JS / 90.07 kB gzip); served
  build answered HTTP 200 on `/` and the asset bundle. Web unit tests
  passed earlier in this session (5/5).

Sweep-script fixes made while converging (test tooling only, no product
code): field names (`points`, `balance_after`), `Idempotency-Key` as a
header, `to_user_id` invitation body, `radius_m`/`display_name` profile
fields, per-run boot-id stamping, and 16-point evidence arithmetic.

**Still physical-only after this sweep** (cannot be closed by API tests):
wearable BUTTON entry of PINs on both TinyScreens (the board→phone→server
command transport + ACK path itself WAS proven live earlier today when both
phones were awake — commands reached the server and were ACKed; only the
four-button entry on the devices remains), bilateral wearable display of
stages during a real session, Keep Your Cool with two real sensors, GPS
outdoor run, and the over-the-air discovery observation round-trip with a
real second user (board 1 proven live 29 Oct; board 2's radio path proven
via the FE on 3 Nov).

## Two-device live session: board 2 exonerated, phone-2 scan blocker pinned to older Samsung stacks — 3 November 2026

The user paired two new wireless-debugging devices: a Galaxy Tab S5e
(SM-T720, Android 11 — intended replacement for the blocked S10e as the
second phone) and confirmed the Galaxy S24 FE (SM-S721B, Android 16).
Findings, all verified live:

- **Android 11 BLE permission bug found and fixed (Android)**: `BleLink`
  required the Android 12+ runtime `BLUETOOTH_SCAN`/`BLUETOOTH_CONNECT`
  grants unconditionally, so on the Tab S5e the link always failed with
  "Bluetooth permission not granted". Fixed by branching on SDK level
  (`BleLink.kt`: API < 31 checks `ACCESS_FINE_LOCATION` instead; 12+
  behavior unchanged). Rebuilt (`BUILD SUCCESSFUL in 1m 8s`) and reinstalled.
  After the fix the tablet scanned and delivered results normally.
- **Both apps signed in and bound**: tablet toma/devpass-b, S24 FE
  miya/devpass-a (fresh DB codes; binding is server-side per user). Both
  `adb reverse` tunnels verified from the devices; dev API server restarted
  as a background task after being found down.
- **Boards verified healthy over serial (COM3 = board 2, COM4 = board 1 —
  ports shifted from the recorded COM5/COM8)**: both cycle
  ADVERTISING↔SCANNING, peer counters climbing on both (board-to-board
  reception working), board 1 GPS streaming, board 1 W25Q still full
  (known), board 2 internal queue draining when linked.
- **S24 FE ↔ Board 1: full link** (scan hit → GATT → CCCD → CONNECTED).
- **S24 FE ↔ Board 2: full link** — signed in as toma and connected:
  serial shows `phone=1`, HELLO→STATUS, time anchor, `INTERACTION len=58
  ver=1`, `partner=Miya`; queue draining. **Board 2 is fully functional.**
- **The second-device blocker is NOT board 2 and NOT the app**: the FE's
  log shows both boards' C5 adverts on air in the same second. The tablet
  delivered 2,841 scan results with `company30=0 alias1=0 alias2=0`
  (bluetooth toggle + app restart did not change it) — identical signature
  to the S10e on Android 12. Pattern: Android 16 Samsung and the PC receive
  the wearables; Android 11 and Android 12 Samsung devices deliver
  neighbours but never the boards' adverts. Ruled out: app parser (same APK
  works on the FE), permissions, screen state, advert structure/length
  (fixed 26 Oct), ADV interval (100–150 ms), address type (public).
- **PC Bluetooth adapter is gone (Code 45, CM_PROB_PHANTOM — "device not
  connected")**: WinRT reports no radio; PC-side scans and the board-2
  telemetry relay are blocked until the (USB?) adapter is physically
  reconnected. bleak/pyserial were also lost with the old Python install;
  a separate bench venv now exists at `tools/.bench-venv` (bleak + pyserial,
  kept out of the backend venv on purpose).

**Status: one working phone (S24 FE) can drive either board.** A bilateral
run still needs a second scan-capable device. Next options: (1) try any
other phone as the second device (newer stacks look safe, the FE proves
Android 16 Samsung works); (2) replug the PC Bluetooth adapter to restore
the PC relay/scan instruments; (3) a firmware advertising-variant
experiment aimed at older Samsung stacks (unproven). The tablet otherwise
works fully (sign-in, bind, API, scanning, UI) — only radio reception of
the wearables fails.

## Development environment restored + test time-bomb fixed — 3 November 2026

The workstation lost several development tools (Node.js and the Android SDK
directory vanished; the backend venv pointed at a removed Python 3.14 base;
both catch_me PostgreSQL containers and images no longer existed). All of it
was rebuilt and verified end to end. Nothing in `backend/app`, `web/src`,
`android/app/src`, or `firmware/` product code changed.

### Restored/installed (exact versions)

- Node.js 22.23.1 + npm 10.9.8 — zip install to
  `C:\Users\Joell\AppData\Local\Programs\nodejs` (matches recorded versions).
- Android SDK rebuilt at `C:\Users\Joell\AppData\Local\Android\Sdk` (the path
  `android/local.properties` already points at): cmdline-tools
  (commandlinetools-win-15859902), platform-tools 37.0.1, `platforms;android-35`,
  `build-tools;35.0.0`, and `build-tools;34.0.0` (AGP 8.7.3's default — the
  first build failed with "Could not find Build Tools revision 34.0.0" until
  this was installed; the old SDK evidently had both).
- backend/.venv recreated with Python 3.14.2 (installed side-by-side via the
  Python install manager: `py install 3.14.2`); `pip install -r
  backend/requirements.txt` — all pins resolved to the recorded versions.
- PostgreSQL containers recreated (images had been deleted):
  `catch_me_pg_dev` on 127.0.0.1:5432 (db `catch_me`) and `catch_me_pg_test`
  on 127.0.0.1:5433 (db `catch_me_test`), both `postgres:17-alpine` with user
  `catch_me`/`catch_me`, named volumes `catch_me_pg_dev_data` /
  `catch_me_pg_test_data`. `alembic upgrade head` applied cleanly through
  `c4f7a91e2b10`; `seed.py` reseeded miya/toma + pair + 2 devices + 3 rewards
  with the recorded dev passwords.
- User PATH gained (no admin needed): `%LOCALAPPDATA%\Programs\nodejs`,
  `%LOCALAPPDATA%\Android\Sdk\platform-tools`, `D:\catch_me\tools\arduino-cli\bin`.
  New terminals pick these up; already-open shells do not.

### Verified working (actual commands/results)

- Firmware: `arduino-cli --config-file tools/arduino-cli/arduino-cli.yaml
  compile --fqbn TinyCircuits:samd:tinyscreen --build-path
  tools/build/catch_me_pin_debug_d1 --build-property
  compiler.cpp.extra_flags=-DDEVICE_ID=1 firmware/catch_me_app` → 45,216
  bytes (17%). The vendored toolchain (cli 1.5.2-rc.1, TinyCircuits:samd 1.1.0,
  all 7 libraries under `tools/arduino-cli/data/user/libraries`) needed no
  re-download.
- Web: `npm run test -- --run` → 5 passed (Node 22.23.1).
- Android: `gradle --offline --no-daemon
  -Pkotlin.compiler.execution.strategy=in-process assembleDebug` (Temurin
  21.0.12.1 + Gradle 8.11.1 from `tools/android/`) → BUILD SUCCESSFUL in 21 s;
  fresh `android/app/build/outputs/apk/debug/app-debug.apk`.
- Backend: `pytest backend/tests -q` → **77 passed, 1 warning** (PostgreSQL
  test container), matching the recorded state.

### Test-suite fix: hardcoded fixture date expired

5 tests failed after the restore (together completion, keep-your-cool,
separation, heart gap, purchase-not-XP): all share `rec()`/`iso()` built on
`T0 = 2026-11-01 12:00` in `test_telemetry_and_sessions.py`. Evidence only
counts at/after the start-PIN confirmation instant (real wall clock), so the
fixture captures must sit ahead of runtime — true when written, false once
real time crossed 1 November. Fixed by deriving
`T0 = datetime.now(timezone.utc) + timedelta(hours=1)` per run (margin must
exceed the ~1-minute suite duration; a 60 s margin made the heart-gap test
pass alone but fail in the full suite). `test_purchases_and_sse.py` was
affected only via its import of these helpers. No product code changed; the
suite is now run-date independent.

## Two-phone BLE diagnostic update — 1 November 2026

- Confirmed the S24 app (Android 16, SM-S721B) receives Board 1's alias-1
  heartbeat, connects over GATT, discovers the UART service, and writes the
  notification descriptor successfully. Board 1 serial reported `phone=1`
  in connected windows and `phone=0` during its scheduled radio transitions.
- The S10 app (Android 12, SM-G970F) is signed in for device alias 2 and stays
  in the foreground scanning. Android reports Bluetooth scan/connect and fine
  location grants, Bluetooth enabled, and location services on. Across more
  than 2,300 balanced scan callbacks it received no company `0x0030` fields,
  C5/C6 payloads, alias-1/alias-2 matches, or GATT attempts.
- PC BLE scans during the same bench session saw both wearable manufacturer
  heartbeats (alias 1 and alias 2); a later 18-second check also saw alias 2.
  Both board serials showed repeated scan/advertise transitions. In a shared
  22-second serial capture, Board 1's peer counter rose 427→429 and Board 2's
  rose 1254→1258, proving direct wearable-to-wearable observations are
  happening. Board 2 still reported `phone=0`. UI code confirms `PEER 1/0`
  is a fresh/stale flag (fresh means a heartbeat within 10 s); `PEER -` means
  no peer has ever been observed. So the earlier `PH 0 PEER 0` sample means
  the phone was disconnected and the latest peer heartbeat was stale then,
  not that peer discovery had never worked. These counters do not yet prove
  session-bound server evidence because Board 2 has no phone link.
- Isolated Android-side probes on the S10: removed `neverForLocation` while
  retaining the already-granted fine-location permission, tried foreground
  low-latency scanning, and toggled Bluetooth off/on. None exposed the board
  advertisements. Reverted those diagnostic source changes to the previous
  balanced scan and `neverForLocation` manifest. Rebuilt successfully and
  reinstalled the baseline debug APK to the S10 with `adb install -r` (no app
  data clear); re-applied `adb reverse tcp:8000 tcp:8000`. The latest 81 scan
  callbacks again had zero wearable manufacturer data. Build command from
  `android/`: `..\tools\android\gradle\gradle-8.11.1\bin\gradle.bat
  --offline --no-daemon '-Pkotlin.compiler.execution.strategy=in-process'
  assembleDebug` (Temurin JDK 21.0.12.1, workspace-local Gradle home) —
  `BUILD SUCCESSFUL` in 56 s; existing nullable/deprecation warnings only.
- Current status: real board-to-board proximity evidence works; Phone 1 ↔
  Board 1 GATT works intermittently as designed; Phone 2 ↔ Board 2 Android
  scanning/GATT remains blocked on this S10. No bilateral PIN entry was
  attempted because Board 2 has no phone link. Next diagnostic: use a generic
  BLE scanner on the S10 (or another Android phone) during a PC-confirmed
  alias-2 advertisement to distinguish S10/One UI scan delivery from app logic.

### Independent S10 scanner check — 1 November 2026

- Installed nRF Connect for Mobile 4.29.1 from Google Play and force-stopped
  Catch Me without clearing its data. After the user granted temporary precise
  location, ran nRF Connect's unfiltered 45-second BLE scan. A simultaneous
  45-second PC Bleak scan saw Board 2's alias-2 heartbeat three times. The
  S10 scanner listed seven devices, but none matched Board 2's address; no
  `CATCHME-2` name appeared. The address comparison was performed locally and
  the address/payload were not logged. This shows the failure is below Catch
  Me's parser on this S10 scan path; it does not establish whether One UI or
  the phone's BLE radio is responsible.
- Cleanup: force-stopped nRF Connect, revoked its precise and approximate
  location grants, and left its Nearby Devices grant in place. Reopened Catch
  Me in the foreground without clearing data and restored `adb reverse
  tcp:8000 tcp:8000`. nRF Connect remains installed for any later comparison.

### Close-range S10 follow-up — 1 November 2026

- User placed the S10e immediately beside Board 2. In a synchronized 12-second
  follow-up, Board 2 entered three advertising windows and serial remained
  `phone=0` (peer counter 1919→1920); the S10 Catch Me scanner advanced from
  1,721 to 1,801 callbacks with company `0x0030`, C5/C6, alias 1, and alias 2
  all still zero. Close distance does not change the result. The current
  blocker is compatibility/scan delivery between this S10e and the wearable
  advertisements, not insufficient proximity.

## Two-phone BLE test started - 1 November 2026

- Installed the current debug APK on both wireless-debugging phones without clearing app data and confirmed the local API reverse tunnel. Phone 2 (Galaxy S10) retains an API-accepted session. Refreshed Phone 1's sign-in in-app using the credentials the user supplied; the local API accepts its session.
- Initially, Phone 1 reported Bluetooth unavailable; enabling it through ADB restored alias-1 GATT setup. At the first sample, Phone 2 had no alias-2 hit and the user reported `PH 0 PEER 0` on Board 2. See the diagnostic update above for the later serial and PC-scan evidence. The bilateral PIN flow is still not physically verified.
- The full Board 1 flash queue is an offline telemetry backup, not user/profile records: 2,000 fixed 32-byte samples, written at one sample per second while no phone link is available (about 33 minutes 20 seconds). A sample contains uptime/capture-time metadata, GPS fix and age when valid, heart-rate value/status when valid, and recent BLE peer evidence when available; it contains no PIN, name, or chat. When full, new offline backup copies are dropped; live telemetry can still send and queued records can drain after connection. Queue was not erased.

## Interaction firmware flashed — 31 October 2026

- DEVICE_ID 1 image from `tools/build/catch_me_pin_debug_d1` uploaded to bootloader COM7 with verification; it returned as app COM5 (serial `FB3F8F12503243594E2E3120FF061902`). Runtime serial confirmed `boot_id=d1-55` and `catch_me device 1 up, fw 1`.
- DEVICE_ID 2 image from `tools/build/catch_me_pin_debug_d2` uploaded to bootloader COM6 with verification; it returned as app COM8 (serial `C0C9716B503058324C2E3120FF14032F`). Runtime serial confirmed `boot_id=d2-i1`; board 2 reported peer observations (`peers=2`).
- Actual upload commands, from the workspace root:
  - `tools\arduino-cli\bin\arduino-cli.exe --config-file tools\arduino-cli\arduino-cli.yaml upload --fqbn TinyCircuits:samd:tinyscreen --input-dir tools\build\catch_me_pin_debug_d1 -p COM7 --verify` - Verify successful, 45,792 bytes.
  - `tools\arduino-cli\bin\arduino-cli.exe --config-file tools\arduino-cli\arduino-cli.yaml upload --fqbn TinyCircuits:samd:tinyscreen --input-dir tools\build\catch_me_pin_debug_d2 -p COM6 --verify` - Verify successful, 45,796 bytes.
- No Android phone was connected during the serial checks, so the PIN display/command relay has not yet been exercised. Board 1 reports its W25Q backup queue full at 2,000 records; live records still send, but additional offline backup copies are dropped. The queue was not erased.

## Quest interaction implementation ? 30 October 2026

Implemented the approved [QUEST_INTERACTION_PLAN.md](QUEST_INTERACTION_PLAN.md) across backend, web, Android relay, and TinyScreen+ firmware while preserving discovery, telemetry, radio scheduling, historical sessions, points, and shop behavior.

- Backend: new sessions freeze interaction version 1 on acceptance. Together uses mutually entered four-digit start and end codes, five-minute expiry, five attempts per version, owner-only refresh, unique codes across the session, HMAC idempotency keys, and no award until end confirmation. Only the requesting participant's display code is returned in `/interaction` or that owner's `/devices/{id}/state`; codes are deleted on completion/cancellation and never go to SSE. Legacy null-version sessions retain old scoring.
- Keep Your Cool retains `heart_challenge`: 10 seconds baseline + two 10-second turns, both valid sensors plus mutual direct Bluetooth evidence, server-selected Truth/Dare prompts, active-user turn ownership, skip/restart of only the unfinished round, median BPM changes, and no heart-rate eligibility threshold.
- Web has PIN entry/refresh, Truth/Dare selection, prompt skip, phase/progress, and measured BPM summary. Android relays own-code state and wearable commands over the existing framed BLE link; retries retain session/stage/version/nonce and only receive success ACK after the authenticated API responds. Firmware adds edge-triggered button entry and compact phase/summary rendering.
- Database revision `c4f7a91e2b10` was applied to the local development PostgreSQL database (previous revision `b7d1sc0v3ry1`); the migration is additive. `docs/openapi.json` regenerated with 33 paths. Offline SQL for `b7d1sc0v3ry1:head` generated (5,788 bytes); a full offline `base:head` export remains unsupported because the earlier discovery migration performs a data-dependent preflight query.

Software checks run:

- Backend: `backend\.venv\Scripts\python.exe -m pytest backend\tests -q` - 77 passed, one Starlette/httpx deprecation warning.
- Web: `npm run test -- --run` - 5 passed; `npm run build` - TypeScript and Vite production build passed.
- Firmware: portable Arduino CLI 1.5.2-rc.1, TinyCircuits:samd 1.1.0, FQBN `TinyCircuits:samd:tinyscreen`; DEVICE_ID 1 build 45,064 bytes and DEVICE_ID 2 build 45,068 bytes (17% flash).
- Android: Temurin JDK 21.0.12.1 + Gradle 8.11.1, `--offline --no-daemon '-Pkotlin.compiler.execution.strategy=in-process' assembleDebug` - BUILD SUCCESSFUL. The debug APK is `android/app/build/outputs/apk/debug/app-debug.apk`. Existing nullable/deprecation warnings remain. Workspace-local Gradle/Android cache paths were needed under this restricted environment.

Both interaction firmware builds are now flashed and upload-verified, but no new physical PIN interaction run has been performed. Current loan/demo inventory: one AST1041 pulse sensor and one Android phone (wireless debugging enabled). Main physical demo priority: with two phones, demonstrate Bluetooth-backed start PIN -> 30 seconds of mutual evidence -> distinct end PIN -> one award; verify board buttons and command retry/ACK. One phone can debug one wearable's display/relay, but cannot validate both simultaneous Android-to-wearable relays or full bilateral server scoring. The Together flow itself needs no pulse sensor. Physical completion of Keep Your Cool remains pending a second real sensor; until then, show missing data honestly and do not claim shared sensor-quest acceptance. Existing two-board Bluetooth evidence, TDD desynchronization, one-board pulse probe, GPS pending checks, and queue/ACK bench notes below are historical evidence only.

### PIN flow diagnosis — 30 October 2026

- Backend owner-only PIN snapshots and submit/refresh endpoints are present. The focused backend check `backend\\.venv\\Scripts\\python.exe -m pytest backend\\tests\\integration\\test_telemetry_and_sessions.py -q -k pin` passed (3 passed, one Starlette/httpx deprecation warning).
- PIN codes are intentionally exchanged verbally: each wearable receives only its owner's code, and the user enters the partner's code. There is no automatic wearable-to-wearable PIN transfer.
- At the time of the 30 October diagnosis, the interaction build was not flashed and there was no physical PIN run or `INTERACTION` trace. See the 31 October update above for successful firmware uploads; the actual PIN/Android relay still needs a phone-connected test.
- Fixed a firmware feedback gap: API rejections were ACKed as `RETRY NEEDED`, but the UI hid that text while PIN digit entry was open, making an incorrect/expired code appear ignored. The status is now rendered on the PIN screen.
- Fixed a web diagnostic gap: an active session's failed interaction snapshot was silently hidden as if the session were historical. The page now displays the API error for active Together/Keep Your Cool sessions so a missing server route/migration is visible.
- Rebuilt firmware successfully: DEVICE_ID 1 uses 45,148 bytes and DEVICE_ID 2 uses 45,152 bytes. New outputs are `tools/build/catch_me_pin_debug_d1/catch_me_app.ino.bin` and `tools/build/catch_me_pin_debug_d2/catch_me_app.ino.bin`. They have not been flashed or physically verified.
- Web production build after the error-visibility change: `npm run build` from `web/` passed (TypeScript + Vite).

## Bench status close-out — 30 October 2026 (late)

Final bench state after the full debugging pass: **all mechanical elements
proven** — relay uploads real board-2 evidence (struct/queue/arg fixes),
internal-flash queue works (board 2 buffers disconnected-period records and
drains 2/s on reconnect, sequences re-based per boot), TDD desync flashed
(board 2 cycles at 9.3 s vs board 1's 8.5 s) and produced the **first
chained board-2 evidence span (9.1 s)** within minutes of flashing.

The one remaining bench blocker is **operational, not a code defect**: the
phone app's evidence flow degrades within minutes in the background
(Samsung Doze + aggressive app freezing — observed as d1 peer points
collapsing 17→3 per 8 min, plus intermittent short-fragment SESSION_STATE
relays under long connection intervals; the board correctly rejects short
messages and later windows succeed). The together quest needs BOTH sides
dense simultaneously; on the real demo (two phones held with screens on)
that is inherently satisfied. Next bench attempt: unlock phone + cold-start
app + run the relay — with the desync in place the intersection should
accrue within ~10 min of a healthy window.

Everything else is verified: 72/72 backend, quest completion + awards +
shop + heart-honesty (fixture-assisted for toma's side), discovery
round-trip live, TinyScreen results over the air, watchdog validated,
freeze forensics armed (capture running). Remaining: GPS outdoor run,
board 2 relay as a permanent bench fixture is DONE, deployment packaging.

## TDD desync + first chained board-2 evidence — 30 October 2026 (late)

**Root cause found for zero quest progress on the bench: TDD phase
anti-correlation.** Two identical 8.5 s radio cycles drift phase at ~0.1%
(crystal tolerance), so the boards can sit scan/advertise anti-correlated
for hours: each only hears the other while itself not listening, so each
side's observation instants land in the other's silent gaps and the
≤10 s-chained evidence spans never overlap (0 scored ms despite dense
one-sided evidence — confirmed by evaluator replication: 71+12 points,
34+8 spans, 0 intersected ms).

**Fix: per-device TDD desync** — DEVICE_ID 2 advertises 2.3 s (9.3 s cycle
vs board 1's 8.5 s), sweeping the relative phase in ~1-2 min. Evidence
rules untouched; radio phase relationship differs per device.
**First chained board-2 evidence observed after the desync: a 9.1 s
presence span** (03:03:21→03:03:30Z) — board 2's observations chained
within the 10 s rule for the first time. A fully-real bench quest
completion remains pending on simultaneous density: board 1's side runs
through the phone app, which Samsung freezes within minutes in the
background (observed again: d1 points collapsed 17→3/8 min when the phone
re-locked). The real demo (two phones, two full boards) is symmetric and
does not have this dependency.

Also shipped this evening: internal-flash queue for board 2 (boot identity
`d2-i<n>`, drains up to 2 buffered records per connected second), relay
struct-offset/queue/arg fixes, verbose relay diagnostics, freeze forensics
on both boards (armed; capture running).

## Board 2 internal-flash queue + drain: evidence density fixed at the source — 30 October 2026

The user's insight — "can't it use its existing flash memory?" — was right:
the SAMD21's own 256 KB program flash has ~220 KB free. New
`internal_queue.cpp/.h`: append-only 32-byte record store in the top 8 KB
(row 0 = magic + boot counter; rows 1-31 × 8 records = 248 capacity;
NVMCTRL row-erase/page-write per the core's proven Reset.cpp pattern; boot
identity `d2-i<counter>` — board 2's first stable boot id). `queue_sel.h`
facade routes every call site through external-W25Q-or-internal logic
(board 1 behavior unchanged; both boards flashed with the aligned build).
`build_and_store_record` now DRAINS up to 2 queued records per connected
second (re-sequenced under the current boot id — new identity makes that
collision-free), so records built while the TDD link is down reach the
relay on the next window instead of being lost. Verified live: the relay
observed drained sequences (445→450 = 2 drained + 1 live per window) and
uploaded them.

**Relay debugging record** (`tools/board2_telemetry_relay.py`, all fixed):
telemetry struct offsets (fix_age H precedes peer_dev B — the old read
yielded peer_dev=255), single-slot completion losing assembled messages
(now a queue), stale-arg/token handling, missing session binding (the
relay needs an ACTIVE session; with none, peer fields are stripped and
board 2 — no GPS, no pulse — has nothing else to upload).

**Current scorer state:** with the relay running, board 2's evidence
density is bounded by how often the relay wins a link window; board 1's
density is bounded by the phone app being unlocked/foregrounded (Samsung
Doze pauses its polling). With BOTH dense, the intersection accrues and
the demo target completes on fully-real evidence — that final run is
pending one phone-unlock.

## Board 2 relay WORKS (real uploads) + bench sparsity explained — 30 October 2026

`tools/board2_telemetry_relay.py` now uploads REAL board-2 telemetry with
session-bound peer evidence (33 rows verified in PostgreSQL). Bugs fixed en
route: telemetry struct field offsets (fix_age is H then peer_dev B — the
old read produced peer_dev=255), single-slot message completion losing
records (now a completion queue), 10 s poll sleeping, and arg parsing.

**Bench limitation (documented, not a bug):** board 2 has no flash shield,
so records built while its TDD link is disconnected are lost entirely
(~60%). Its surviving observations land ~60-100 s apart → isolated points
→ zero-length presence spans under the ≤10 s successive-observation rule →
the evaluator correctly scores 0 for the sparse side. With two FULL
wearables (both flash-equipped, as the real demo set is), evidence chains
at ≤10 s and scoring works — proven by board 1's side (healthy 17 s spans)
and by the labeled-fixture completion. The bench cannot complete quests
with the flash-less spare; the relay still delivers its real observations
for server-side visibility.

**Freeze forensics armed on both boards** (boot reason + previous-life
uptime printed every boot, no-init RAM marker refreshed every 5 s; capture
`serial_freeze_watch.log` running). The first freeze event now yields its
duration and cause class automatically.

## Freeze forensics + TinyScreen discovery results OVER THE AIR — 30 October 2026

1. **Freeze forensics shipped on both boards**: every boot prints its
   hardware reset reason (`PM->RCAUSE`), and a watchdog recovery reports
   the previous life's last known uptime from no-init RAM
   (`WATCHDOG (previous life N ms)`; the noinit section verified present in
   the tinyscreen_p linker map, far from the stack). Post-flash boots
   correctly classified as "system request"; power cycles will read
   "power-on". The next freeze converts into hard evidence instead of a
   mystery — the uptime number will discriminate blocking-write stalls,
   I2C hangs, and radio deadlocks. `wdt::note_alive()` records liveness
   every 5 s from loop().
2. **TinyScreen discovery results rendered over the air — FULLY PROVEN**:
   with the pair un-paired and both boards discovering, the complete relay
   chain ran live: board 1 caught board 2's token → phone uploaded →
   server listed Toma → the app's 5 s poll relayed the compact result →
   board 1's serial logged `ble: discovery results n=1 first=Toma
   shared=1` **at the same moment** the server showed
   `[('Toma', ['bluetooth'])]`. The TinyScreen renders `1/1 Toma 1B`
   (result index/count, name, shared count, B=Bluetooth source), rotating
   through up to 3 results. Empty lists relay honestly as `n=0`
   ("DISC scan N" shown instead). Then: invitation re-accepted → both
   boards `discovery mode=0` → list empty. End state: miya↔toma
   re-paired, discovery off, keepalive tools stopped.
3. Operational notes: Samsung re-locks + Dozes the phone within minutes;
   discovery polling is screen-visible-gated BY SPEC, so results relays
   pause when the phone sleeps — keep the app foregrounded during the
   demo. `tools/scan_discovery_adv.py`, `mode_keepalive.py`,
   `discovery_mode_relay.py`, `board2_telemetry_relay.py` remain the bench
   toolkit.

Remaining: GPS outdoor run (geofence + last-known + TTFF), board 2
telemetry relay upload debugging (freeze root-cause forensics now in place
for the next event), deployment packaging.

## Non-GPS test sweep PASS — 29 October 2026 (evening)

Full verification pass over everything except the GPS outdoor run:

1. **Backend regression: 72/72 passed** on PostgreSQL (the test container
   had exited again — `docker start catch_me_pg_test` first).
2. **Together quest COMPLETED on the two-board rig** (demo target 30 s):
   board 1's side was REAL radio evidence (session-bound telemetry with
   peer observations of board 2); toma's side was injected as a CLEARLY
   LABELED fixture (`FIXTURE-toma-relay` boot id) because board 2 has no
   phone — the completion/award path exercised: `completed` at 30000/30000,
   completed_at derived from evidence intersection (14:23:27Z, not wall
   clock), awards exactly once per user (+100 pts/+100 XP), balances and
   levels correct (150/200 pts, level 3).
3. **Shop flow PASS** (`tools/test_shop_flow.py`): purchase + idempotent
   retry (no double charge), one-time-ownership rule (409 already_owned),
   insufficient-points rejection (409), XP never reduced by spending,
   level derivation stable at 3.
4. **Heart-quest honesty PASS**: demo heart_challenge accepted on the rig,
   progress stayed exactly 0 ms past the 10 s target (board 2 has no pulse
   sensor — no fabricated readings), cancelled cleanly.

**New server capability:** `DeviceStateOut.partner_device_id` — the phone
needs the partner's device UUID to resolve peer observations in relayed
telemetry; without it, partnered records carried stripped peer fields and
quests could never score. App reads it into `partnerDeviceId`; 72 tests
still green.

**Bench tool:** `tools/board2_telemetry_relay.py` — PC stands in for toma's
missing phone: GATT link with TDD reconnect loop, TIME_ANCHOR clock
anchoring, 32-byte record decode, session-bound upload with peer resolution.
Received notifications but did not complete an upload tonight (0 rows;
needs live debugging with verbose logging — first suspect: notification
delivery across the TDD link cycling). Until it works, quest completion on
the bench needs toma-side fixtures as above; on the real demo two phones
make it moot.

Known quirk for the demo: the phone re-locks and Samsung freezes the app's
BLE after minutes in the background; the app must be foregrounded and the
phone unlocked during quest demos (screen timeout raised to 10 min via
adb; Samsung may still re-lock).

## TWO-BOARD DISCOVERY ROUND-TRIP LIVE ON HARDWARE — 29 October 2026

Both wearables now run the production discovery firmware and the complete
nearby-discovery loop was demonstrated end to end with real radio evidence:

1. **Peer gate MET**: board 1 and board 2 continuously observe each other's
   quest heartbeats (both serials' `peers` counters climbing at ~1 per radio
   cycle for extended periods; board 2 reached 191). Direct
   wearable-to-wearable evidence — the course's core hardware requirement.
2. **Discovery round-trip**: partnership ended → both boards' modes on
   (board 1 via phone, board 2 via `tools/discovery_mode_relay.py` +
   `tools/mode_keepalive.py`, PC-as-relay labeled test tools) → board 1
   observed board 2's discovery advert (token 61495) → phone uploaded the
   observation → server mapped token→toma → **miya's discovery list showed
   "Toma — Detected nearby"**, live only within the 15 s presence window and
   empty outside it (freshness verified by correlating row age with list
   contents) → invitation re-accepted → partnership restored → board 1
   switched `discovery mode=0` and the list emptied again; board 2 set to
   mode 0 via relay.
3. **Board 1 recovery**: the stuck test build was removed via the
   **button-combo bootloader entry** (the user discovered TinyScreen+ has NO
   dedicated reset button — a button combination serves as reset; double
   combo = double-tap). All USB-touch paths had silently no-opped with the
   test build. A board-aware auto-watcher now identifies which board is in
   the bootloader before flashing (an earlier blind watcher flashed
   DEVICE_ID=1 onto board 2 by mistake — corrected immediately by
   re-flashing board 2 with its proper build).

**Root causes found and fixed in this session:**
- **Alternating payload scheme starved discovery (firmware redesign)**: the
  C5/C6 alternation across ADV windows failed because the phone reconnects
  during advertising windows and cuts them short — C6 windows became nearly
  invisible (board 1 emitted effectively no C6). REPLACED with
  **simultaneous payloads**: flags + heartbeat field + discovery field in
  ONE advertisement (21 of 31 bytes); the name moved to the scan response.
  `note_advertisement` now falls through to parse both mfr fields. Board 2's
  discovery advert and board 1's reception immediately verified.
- **Observation-buffer wipe on redundant mode applies (firmware)**: the
  phone re-sends DISCOVERY_MODE until its ACK lands (ACKs frequently lost);
  each apply wiped the C6 catch buffer, erasing fresh observations every
  ~3 s. Now wiped only on mode-off or token change.
- **Unpaired peer records poisoned telemetry (Android)**: once board 1
  observed a non-partner, `resolveAliases` emitted `peer.observed=true`
  without a resolvable device_id → server rejected EVERY batch (422). The
  phone now strips peer fields when the peer can't be resolved (no quest
  meaning without a session binding).
- **Poisoned upload queue**: the invalid records accumulated in the phone's
  persistent queue and blocked all newer uploads. Queue storage cleared
  (session prefs untouched); uploads returned to 200 OK immediately.
- **Board 2's mode is RAM-only** (no flash shield): every reboot disarms
  discovery silently. `tools/mode_keepalive.py` re-asserts it every 2 min
  for bench sessions; stopped when the pair re-partnered.
- **Watchdog validated on hardware** (board 2): GCLK4 sourced from the
  core's XOSC32K generator 1, GENDIV/32 → unfed resets at 18.1 s (=16 s
  period + boot). Earlier attempts failed instructively: GCLK3 belongs to
  the core (v1 broke it → inert watchdog + the USB-bootloader lockout), the
  internal OSC32K never readies on this board (v2 hung). The produced
  firmware carries the validated config; board 2 ran it through the whole
  session with zero spurious resets.
- **PC scanner cannot see both mfr fields** (Windows collapses same-company
  fields into one map entry — C5 shadows C6): air-verification of C6 must
  use the boards' own reception (DISC scan N on the TinyScreen) or serial-
  synced single-window captures, NOT plain bleak scans.

Remaining hardware evidence: TinyScreen+ display of discovery results with a
real second user (board 2's screen shows the DISC scan counter; result
rendering via MSG_DISCOVERY_RESULTS still unexercised over the air), GPS
outdoor run (geofence + last-known demo), freeze-watch capture continues.

## Discovery LIVE on hardware + AD-length bug fixed — 26 October 2026 (evening)

The complete discovery control loop is now PHYSICALLY VERIFIED on board 1
+ Galaxy S24, including the partnership lifecycle:

1. miya↔toma partnership ended via API (explicit demo path; history kept).
2. Profiles completed + Bluetooth/GPS opt-ins on for both (toma driven by
   a server-minted session: `tools/mint_session.py`, labeled test tool).
3. Token 6856 provisioned through the authenticated phone link; board
   serial logged `ble: discovery mode=1 token=6856` and the app showed
   "wearable discovery active" (ACK round-trip).
4. **0xC6 discovery advertisement CAPTURED ON AIR**: `c6 01 c8 1a`
   (magic/version/token 0x1AC8=6856 LE), alternating with unchanged 0xC5
   quest heartbeats — verified with `tools/scan_discovery_adv.py`
   (serial-synced scanner that dumps payloads during the 1.5 s windows).
5. Live invitation: miya→toma created (pending) → accepted → NEW
   partnership active (b57e420d).
6. Pairing stops general discovery ON HARDWARE: app detected
   `partner_alias` and the board logged `discovery mode=0 token=0`;
   air scan then showed ONLY 0xC5 heartbeats (consecutive counters).
7. Telemetry flowed under real boot ids throughout (d1-22, d1-23 rows in
   PostgreSQL; HELLO→STATUS now populates boot ids correctly).

**Real bugs found and fixed while proving it:**
- **Firmware AD-length bug (new)**: the manufacturer AD length byte was
  hardcoded 0x09 (heartbeat-sized); discovery windows emitted a malformed
  AD structure and every scanner silently dropped them — on-air evidence
  was "only even heartbeat counters visible". Fixed to
  1+2+payload_len; discovery adverts became scannable immediately after
  reflash. This would have broken two-board discovery completely.
- **Android**: phone now refreshes profile/partnership every 5 s poll
  (server-side changes were invisible to the radio mode before);
  discovery mode re-sent after every board reboot/reconnect (board boots
  with discovery off); stateLoop derives `partnered` from
  deviceState.partner_alias so pairing stops discovery even while the app
  is backgrounded/screen-locked.
- **Ops**: wireless adb transports flap and silently kill `adb reverse`;
  `tools/reverse_keepalive.py` (background) re-applies it every 4 s —
  without it every app cold start fell back to the login screen. Also:
  Docker Desktop died once mid-session (both PG containers exited 255 →
  `docker start catch_me_pg_dev catch_me_pg_test`; dev API server also had
  to be restarted as a true background task).

**Board freeze recurrence #2**: ~12 min after a USB replug the board
hard-froze (no serial, no radio; recovery = another replug). Same
signature as the 26 Oct 02:22 recurrence, both on firmware WITHOUT
discovery radio behavior at freeze time — pre-existing issue, now the
top reliability risk for the demo. A serial capture
(`serial_discovery_live2.log`) keeps running for freeze evidence.
Current boot d1-23 has been stable through the whole evening session.

Remaining for discovery: two-board observation round-trip (board 2),
TinyScreen result rendering with a real second user, outdoor→indoor
last-known demo. Quest flows (sessions) were not re-run tonight; the
partnership is restored so quests work again.

## Discovery firmware flashed + phone pipeline regression PASS — 26 October 2026

Board 1 (CATCHME-1) now runs the discovery build; the complete existing
pipeline was re-verified on real hardware afterwards.

- Flash: `tools/touch_bootloader.py COM5` (after killing a stale
  `capture_serial_ts.py` PID holding the port) → COM7 bootloader →
  `arduino-cli upload --input-dir tools/build/catch_me_disc -p COM7`
  (verify OK). New boot identity `d1-20`; flash queue intact (2000 stale
  backup records persist — the known unacked-queue issue, unchanged).
- Boot clean: W25Q JEDEC, GPS parsing, MAX30101 on adapter port 3, BLE,
  TDD cycling ADVERTISING↔SCANNING on schedule. PC-side ADV dump shows
  the byte-identical quest heartbeat (`c5 01 <ctr> 00 00`, counter
  advancing, name CATCHME-1) and no 0xC6 — discovery off by default, old
  behavior preserved.
- Phone (Galaxy S24, old then new APK) reconnected through the TDD
  windows; TIME_ANCHOR flows; records reach PostgreSQL.
- **boot_id 'unknown' bug ROOT-CAUSED AND FIXED**: `Frame.encode` emitted
  ZERO fragments for empty payloads, so the app's HELLO never went on air
  and the board's STATUS (carrying the boot id) never came back. Fixed
  with a min-1-fragment guard (+ HELLO retry in stateLoop until the cache
  fills). Board now logs `HELLO -> STATUS send=ok`; PostgreSQL shows rows
  under `d1-20` (29 rows in the first minutes after the fix; the last
  'unknown' rows predate the APK update). This also resolves the
  identity-collision risk of per-boot sequence numbers under a shared
  'unknown' boot id.
- Ops notes recorded: the dev API server must run as a true background
  task (an `&` inside a foreground shell dies with the shell — this
  silently killed :8000 mid-test and mimicked a broken adb-reverse
  tunnel; the tunnel itself was fine, verified against a scratch :9090
  listener from the phone browser). Wireless adb transports were reset
  (`adb kill-server` + reconnect by the current mDNS port) — after any
  transport rotation re-run `adb reverse tcp:8000 tcp:8000`.
- Discovery on this board still awaits: new APK's discovery UI exercised
  (profile/opt-in → DISCOVERY_MODE → 0xC6 alternation on air), which
  needs the app foregrounded with the user logged in; two-board
  observation round-trip pending board 2.

## Discovery extension implemented — 26 October 2026 (software level)

Implemented `docs/DISCOVERY_PLAN.md` end to end in software. Nothing in this
section claims physical two-board validation; see "Pending hardware
evidence" below.

**Backend (implemented + tested on PostgreSQL):**
- New tables via Alembic `b7d1sc0v3ry1` (non-destructive; preflight aborts
  with a report if a user appears in two pairings — verified on a scratch
  DB with a constructed cross-column duplicate; data left intact):
  `discovery_settings`, `user_interests` (CHECK on the 8 fixed tags),
  `last_known_positions`, `discovery_tokens` (live partial-unique per
  device, rotatable), `discovery_observations` (unique identity
  observer/token/captured_at), `partnerships` + `partnership_members`
  (partial unique index `user_id WHERE left_at IS NULL` — one ACTIVE
  membership per user enforced by the database), `partner_invitations`
  (partial unique pending pair_key in either direction). The old
  `pairings` table was converted and dropped: the live dev DB's seeded
  pair (miya+toma) migrated to an active partnership, verified by row
  inspection; `seed.py` now seeds Partnership/PartnershipMember and is
  idempotent against migrated data.
- Endpoints (9 new; OpenAPI regenerated — 28 paths): profile
  GET/PUT `me/discovery-profile`, opt-ins PUT `me/discovery-settings`,
  GET `me/discovery` (combined union results, 50 m-rounded distances,
  honest freshness notices), token POST `me/discovery-token`
  (?rotate=true), observations POST `discovery/observations`,
  invitations POST/GET + accept/decline, partnership GET +
  DELETE `me/partnership` (cancels the pair's pending/active quest
  sessions in the same transaction; history/awards preserved).
- Last-known positions are maintained during telemetry ingest:
  fix_time = captured_at − gps_fix_age_ms, valid fixes only, clock
  uncertainty ≤ 2 s, monotonic in fix_time, future fixes rejected,
  invalid readings never erase. Quest scoring is untouched — explore
  still re-derives evidence from telemetry with the 10 s rule; a test
  proves discovery data alone grants zero progress/awards.
- Invitation acceptance: invitation row lock + canonical-order user locks
  + eligibility revalidation + DB partial-unique backstop; idempotent
  retry returns the same active partnership; concurrent opposite-side
  acceptances tested (exactly one partnership wins, statuses {200, 409}).
- Freshness boundaries tested at exact seconds with a controlled clock
  seam (`app.clock.now_utc`, monkeypatched): GPS 30/31, 900/901; BLE
  observation 15/16; retransmission cannot revive presence; buffer of 16
  tokens; opt-out suppresses immediately; ranking deterministic;
  invalid/out-of-order/delayed/future telemetry cannot regress or
  rejuvenate the position cache.
- **Tests: 72 passed** (57 pre-existing regressions + 15 new discovery/
  invitation tests) on PostgreSQL 5433 (`catch_me_pg_test`).
- Dev server restarted from migrated DB (backup taken first:
  `tools/pg_dump_pre_discovery_20261026_*.sql`).

**Firmware (implemented, compiles; NOT yet flashed):**
- Separate versioned discovery advertisement: mfr payload
  `[0xC6][ver][token LE16]` alongside the unchanged 0xC5 quest heartbeat;
  while discovery mode is on the board ALTERNATES payloads across
  advertising windows (one mfr field fits the 31-byte ADV budget). TDD
  radio schedule untouched.
- Scan side parses 0xC6: bounded 16-entry latest-unique-token buffer
  (oldest replaced), 15 s expiry when packing, observations uploaded to
  the phone ~5 s while linked (MSG_DISCOVERY_OBS, versioned; unknown
  versions rejected explicitly). MSG_DISCOVERY_MODE from the phone sets
  unpaired-only mode + provisioned token, confirmed by MSG_DISCOVERY_ACK;
  MSG_DISCOVERY_RESULTS renders ≤3 compact results on TinyScreen+ (name ≤
  12 chars, shared count, B/G source flags, 2 s rotation) in place of the
  queue line while unpaired.
- Compile: `arduino-cli --config-file tools/arduino-cli/arduino-cli.yaml
  compile --fqbn TinyCircuits:samd:tinyscreen --build-path
  tools/build/catch_me_disc --build-property
  compiler.cpp.extra_flags=-DDEVICE_ID=1` → 37,764 bytes (14%) OK.

**Android (implemented, debug APK builds):**
- Api: all 12 discovery/invitation/partnership methods. Frame: new message
  types 8–11; assembler zero-payload guard fixed (HEADER_SIZE, matching
  firmware).
- AppModel: 5 s discovery polling while the screen is visible (expiry
  needs no SSE); relays mode+token to the board on connect until
  DISCOVERY_ACK matches (resyncs after reconnects and on opt-out);
  stamps observation capture time as now−age (idempotent server-side);
  relays ≤3 compact results to the wearable; marks discovery
  unavailable/stale on connection loss instead of showing cached matches.
- UI: discovery card — profile editor (name/age/age-range/radius/8
  interest checkboxes), Bluetooth/GPS opt-in switches with "wearable sync
  pending" honesty, live results with "Detected nearby"/rounded
  distance/stale labels, invite buttons, incoming invitations
  accept/decline, partner display + end-partnership button.
- Build: `gradle assembleDebug` (Gradle 8.11.1 + Temurin 21 via
  tools/android) → BUILD SUCCESSFUL. No Android unit tests exist by
  design (device/emulator verification path); phone verification pending.

**Web (implemented, typecheck+tests+build pass):**
- Fixed a latent bug: the client fetched `/api/*` but routes live at
  `/api/v1/*` (only unit tests had run before); base is now `/api/v1`.
- New Discovery page: profile editor + opt-ins, 5 s polling, honest
  notices/ages, results with source labels + 50 m distances, invitations,
  end-partnership. Nav link "Discovery". `tsc --noEmit` clean, 5 unit
  tests pass, `vite build` OK.

**Pending hardware evidence for discovery:** two-board 0xC6
advertise/scan overlap under the TDD scheduler; token provisioning →
board ADV → other board observation → phone upload → server result
round-trip; TinyScreen result rendering; radio timing with the extra
payload alternation; outdoor-to-indoor last-known demo. Single-board
re-flash + regression (quest telemetry path unchanged) also pending.

Next actions: (1) flash the discovery build to board 1 and regression-test
the existing phone pipeline (records still flow, TDD still cycles);
(2) when board 2 exists, run the two-board discovery checklist above;
(3) update TEST_PLAN.md with the discovery acceptance matrix.

## Current planning revision — 26 October 2026

The approved next feature is specified in [DISCOVERY_PLAN.md](DISCOVERY_PLAN.md): direct wearable Bluetooth discovery and geographic discovery using fresh/last-known wearable GPS, editable profiles, and partner invitations. GPS is fresh through 30 seconds and eligible with age labels through 15 minutes; no phone-location fallback. Explore retains its 10-second GPS evidence rule.

This update changes handoff documents only. It does not claim discovery code, migrations, or physical validation are complete. Preserve all implementation and evidence below. Existing seeded pairs must survive migration and can be explicitly ended through the planned UI.

Next GLM action: inspect current source/tests, implement the discovery plan's migrations and timestamped GPS cache with tests, then extend BLE/Android discovery using the existing time-division scheduler. Preserve the custom W25Q driver and recorded board/phone fixes.

Historical sections below contain superseded blockers (for example, missing Android tooling and old firmware cadence). Use newer recorded results and actual source to reconcile them before acting; do not repeat completed setup or overwrite the original evidence. In particular, concurrent scan/phone operation was rejected in recorded single-board tests, while complete two-board discovery still needs verification.

Documentation validation for this revision: local handoff Markdown links resolve; current agent/specification instructions were checked for the obsolete pre-matched-only and concurrent-radio defaults. No application source, database, generated OpenAPI, device firmware, or tool configuration was changed. No new product tests or physical checks were run for this documentation-only update.

## Current state

- Phase: Stage 0 complete (toolchain + compile evidence); Stage 1 probes built
  (BLE multi-role probe flashed to one physical board; GPS/flash probes
  compile and are ready to flash); Stage 2/3 backend + web implemented and
  tested (software level) with a live end-to-end HTTP proof.
- Workspace: `D:\catch_me`. Deadline: 28 November 2026.

## Status by area

| Area | Status | Evidence |
|---|---|---|
| Backend (FastAPI, 19 endpoints) | Implemented + tested | 57 automated tests passing; `scripts/e2e_demo_flow.py` PASS over live HTTP |
| Web (React/TS/Vite) | Implemented + built | 5 unit tests; `npm run build` succeeds |
| Firmware main app | **RUNS on the board** | Boot passes all inits (flash queue via custom W25Q driver, GPS NMEA streaming ~130 chars/s, UI, BLE); STAT lines show 1 Hz records queuing (`q=2→32` in 35 s) |
| Flash driver | **SPIMemory replaced with hand-written W25Q driver** (`firmware/catch_me_app/w25q.cpp`) | JEDEC 0xEF4014 read, erase/write/read verified; app dropped 51 KB→33 KB with the library gone |
| Android app | **Verified on emulator end-to-end** | login → fixture inject → Room queue → upload → PostgreSQL (5 rows, identities intact); APK rebuilt for LAN server |
| Physical hardware gate | Alternation proven; peer evidence pending board 2 | BLE gate experiments below |
| Android toolchain | Installed and pinned | Temurin JDK 21.0.12 + Gradle 8.11.1 (tools/android/) + SDK platform-tools/android-35/build-tools 35 |

## Physical evidence recorded (25 October 2026)

- Board detected on COM5 (USB VID:PID=03EB:8009, SAMD21 CDC). Serial number FB3F8F12503243594E2E3120FF061902.
- `00_screen_hello` uploaded, verify successful; serial output streamed once per second.
  Board healthy.
- **BLE bring-up root causes (both fixed in firmware, verified on the board):**
  1. The ASD2202-R-F flash shield's chip select (D5) floats at boot, letting the
     W25Q drive shared SPI MISO; every BLE SPI transaction failed. Fix: drive
     D5 HIGH before any SPI/BLE init.
  2. SAMD CDC drops writes until a host opens the port; probes wait up to 60 s
     for a host before init so boot logs survive.
  Upload/recovery tooling: stopped uploads leak `bossac.exe` holding COM5; the
  SAMD bootloader accepts a manual 1200-baud touch and re-enumerates (COM7)
  for flashing when a sketch hangs USB.
- **Multi-role GAP init succeeds** on the ASD2116 (BlueNRG-MS):
  `aci_gap_init_IDB05A1(PERIPHERAL|CENTRAL)` → ok; bd_addr=01:80:E1:00:34:12.
- **BLE gate experiments (single board + PC Bluetooth as independent host):**
  - Central scanning from a quiet stack: SUCCESS — live ADV reports decoded
    (nearby devices, RSSI −58…−91 dBm).
  - `aci_gap_set_discoverable` during a discovery procedure: **0x0C** —
    advertise+scan simultaneously is NOT possible.
  - `aci_gap_start_general_discovery_proc` while a phone-role connection is
    up: **0x82 every attempt** — scanning does NOT run while connected.
  - PC (bleak 3.0.2, Windows radio enabled via WinRT Radio API) received the
    board's advertisement externally: address 01:80:E1:00:34:12, complete
    local name CATCHME-1, RSSI −58…−70 dBm — strongest device in range.
  - **PC connected to the wearable as central** (BleakClient): connection
    accepted (role=peripheral, handle assigned), GATT services enumerated,
    link held 50 s, clean disconnect. Board stayed stable (USB alive).
  - Manufacturer-specific heartbeat payload (ST company id 0x0030, bytes
    C5 01 <counter LE> <token hash LE>) transmits via
    `aci_gap_set_discoverable(name)` + `aci_gap_update_adv_data(raw AD)`;
    counter increments per advertising window. NOTE: this host library's
    `set_discoverable` takes a local NAME, not raw ADV data — raw payload
    MUST go through `update_adv_data` (wrong convention silently emits a
    garbage "name" invisible to scanners).
  - Windows BLE watcher deduplicates identical advertisement payloads;
    dynamic payload (counter) is required for reliable external visibility.
- **GATE VERDICT (firmware level): strict time-division scheduling is
  mandatory on this hardware.** The radio alternates: LINKED 5 s (phone
  upload) → SCANNING 2 s (peer evidence, observations ~8 s apart — within
  the ≤10 s rule) → ADVERTISING 1.5 s (phone auto-reconnects). This is
  HARDWARE.md gate item 5's documented fallback, not a silent semantics
  change: peer evidence remains direct wearable-to-wearable ADV reception.
- Alternation scheduler verified running on the board (probe): stable
  `adv→scan / discovery started / ADV… / scan→adv` cycles for minutes.
- **Main firmware app boots and runs on the board (25 Oct evening).** First
  boot hung inside SPIMemory's `flash.begin()` when the complete library set
  was linked (standalone probes with the same library always worked; bisect
  probes adding STBLE / TinyScreen / TinyGPS / SoftwareSerialZero / a
  class-wrapped SPIFlash each stayed healthy, so the trigger is a full-link
  interaction inside SPIMemory's init rather than any single library).
  Resolution: replaced SPIMemory in the app with a ~100-line hand-written
  W25Q SPI driver (`firmware/catch_me_app/w25q.cpp` — JEDEC, status-poll,
  erase, page program, read). After the swap the full boot passes, the flash
  queue stores 1 Hz telemetry records, and the **GPS TinyShield is confirmed
  alive on hardware** (NMEA streaming ~130 chars/s at 9600 baud). Sketch size
  dropped 51 KB → 33 KB with SPIMemory unlinked.
  Landmine recorded: STBLE's `hci.h` uses `BUSY` as an enum value while
  SPIMemory `#define`s `BUSY` — including SPIMemory.h after STBLE.h in one
  translation unit breaks the build. With the custom driver, SPIMemory is no
  longer used by the app at all (probes still use it).
- **Emulator end-to-end (25 Oct):** API-35 AVD headless, APK installed,
  Bluetooth permission granted, signed in as miya against the host server
  (10.0.2.2:8000), debug-only fixture button injected 5 labeled records
  (`emulator-fixture-boot1`, no session), Room → OkHttp → FastAPI →
  PostgreSQL verified (`0 pending · last upload OK`, 5 rows with intact
  identities). The emulator has NO Bluetooth: the wearable link itself
  requires a physical phone.

## Real-phone progress + firmware hardening (26 Oct, 00:00–01:40)

- **Wireless ADB instead of USB:** every USB-A→USB-C cable the user owns is
  charge-only, so the phone never enumerates. Used Android wireless debugging
  instead: `adb pair <ip>:<pairing-port> <6-digit code>` from the phone's
  Developer options, then `adb connect <ip>:40223`. Phone: **Samsung Galaxy
  S24 (SM-S721B), Android 16 / SDK 36** (recorded for TEST_PLAN).
- **App upgrades driven by the real phone** (`android/`):
  - Session restore: login token/username/device/alias were already saved to
    SharedPreferences but never read back — added `AppModel.restoreSession()`
    (validates the stored token via `/me`, falls back to the login screen on
    401). Main screen now survives process death.
  - Debug auto-connect: `am start -n com.catchme.app/.MainActivity --ez
    autoconnect true` restores the session and starts the wearable link with
    zero on-screen taps (used for all automated phone testing).
  - **Android 16 crash fixed:** the manifest declared BLUETOOTH_SCAN with
    `android:maxSdkVersion="35"`, so on SDK 36 the permission did not exist →
    `pm grant` was a no-op → `startScan` threw SecurityException and crashed
    the app (worked on the API-35 emulator). Removed the cap; BleLink also
    now reports `State.Failed("Bluetooth permission not granted")` instead of
    crashing when runtime grants are missing.
  - Hardware ScanFilter added (manufacturer 0x0030, payload prefix 0xC5):
    Android silently drops unfiltered scans while the screen is OFF, and the
    filter also stops the radio waking on every neighbor advert.
- **Server access from the phone:** Windows Firewall blocks inbound TCP 8000
  from the LAN (adding a rule needs admin elevation). Workaround: `adb
  reverse tcp:8000 tcp:8000` tunnels the phone's 127.0.0.1:8000 to the PC
  server; `API_BASE` in `android/app/build.gradle.kts` now points at
  `http://127.0.0.1:8000` (documented there). For the deployed demo the
  server URL replaces this anyway.
- **Phone login verified end-to-end over the tunnel:** miya/devpass-a → main
  screen, four login sessions in PostgreSQL (23:54:59, 23:57:56, 23:59:52
  local, plus a curl control). DB note: the PostgreSQL dev container had died
  and was restarted (`docker start catch_me_pg_dev`) — that, not the app, was
  behind the first silent login failures. Debugging lesson recorded:
  `login_sessions.id` is a UUID, so `ORDER BY id DESC` returns a random
  sample — always order by `created_at`.
- **Advertisement parser offset fixed (firmware + phone):** the heartbeat
  manufacturer field on air is `[len][0xFF][company LE 2B=0x0030][0xC5]
  [device][counter LE 2B][token LE 2B]`, but both `BleApp::note_advertisement`
  and `BleLink.parseHeartbeatAlias` looked for the 0xC5 magic at the company
  byte's offset — every scanner received the advert and then discarded it in
  parsing. Both now validate company 0x0030 then read the magic/alias two
  bytes later.
- **Board was running a stale build:** the cached hex (19:53) predated the
  final w25q.cpp / flash_queue.cpp rewrites (23:12–23:13). Fresh compile:
  JEDEC 0xEF4014, corrupt queue header self-recovered by formatting,
  boot_id=d1-1, queue stores 1 Hz records. A later reboot showed
  `header rewritten for new boot`, boot_id=d1-2 with the queue contents
  preserved — offline telemetry identity across reboots demonstrated.
- **Whole-board freeze root-caused and fixed:** the STBLE library attaches
  `HCI_Isr` to the BlueNRG IRQ pin and that ISR performs full SPI reads on
  the shared bus. If it fires while the W25Q's CS is low, the flash receives
  phantom commands (seen as randomly corrupted queue headers) and a corrupted
  IRQ read can spin the ISR forever — board completely dead (no serial, no
  radio). Fix in `w25q.cpp`: every W25Q SPI frame runs with interrupts
  disabled (µs-scale frames; BLE events are polled by `HCI_Process`; the GPS
  may drop an occasional 9600-baud character). After the fix the board ran
  continuously: TDD cycling ADVERTISING→SCANNING every ~3.5 s, GPS streaming,
  queue growing, STAT lines steady (log kept at
  `tools/serial_board_phone_test.log`).
- **OPEN BLOCKER — board TX invisible over the air (RF fault suspected).**
  RESOLVED 26 Oct ~01:00: the user unstacked/reseated all shields — board
  immediately receivable again (CATCHME-1 at −61 dBm from the PC, full
  manufacturer payload `c501…`). Physical connection/antenna fault, not
  software. Lesson: reseat the stack before debugging firmware when TX
  vanishes while RX keeps working.

## Phone↔wearable BLE link working end-to-end (26 Oct, 01:00–01:45)

- **Link VERIFIED on the real phone**: app logs `scan hit → conn CONNECTED
  → services discovered → CCCD written`; board logs `ble: phone connected`
  ↔ `disconnected handle=20xx` — 16 clean TDD cycles (connect, 5 s link
  window, scheduled disconnect, re-advertise, phone reconnects ~5 s later).
  Exactly the designed time-division behavior.
- **Three real bugs found & fixed to get there:**
  1. **Kotlin Byte sign-extension** in the advertisement parser:
     `record[i].toInt() == 0xFF` is always false (Byte.toInt() sign-extends,
     0xFF → −1). Every version of the phone parser had this on the type
     byte — it could NEVER match any manufacturer field. Fix: `and 0xFF`
     masks. Proven live: `parsed=null wanted=1` on perfect bytes before the
     fix, `scan hit` immediately after.
  2. **Samsung scan-result delivery**: with a hardware ScanFilter the stack
     COUNTED 480 matches (dumpsys `Results=480`) but delivered zero
     callbacks. Unfiltered scan + `ACCESS_FINE_LOCATION` runtime grant
     (Samsung requires it even on Android 12+) + periodic scan restart
     every 30 s → results flow (20 per 3 s). Trade-off: unfiltered scans
     stop when the screen is off (fine for the demo; app is actively used).
  3. **Write corruption from the phone**: fragments sent 15 ms apart (and
     from two concurrent coroutines) arrived corrupted — board logged
     `frag crc mismatch` repeatedly, then the BlueNRG wedged
     (`set_discoverable fail`, `non_disc fail 0xFF`, `discovery fail 0x4D`)
     and needed a board reset. Fix: `@Synchronized send` + 40 ms inter-
     fragment spacing (BlueNRG's write-without-response queue is tiny).
- **Also fixed**: phone now captures the board's boot id from the STATUS
  reply (was a stub — records would have shipped with boot_id "unknown").
## PULSE SENSOR PROVEN END-TO-END (26 Oct, ~04:45–05:00)

The user connected the AST1041 pulse oximetry Wireling; the last sensor path
is now verified on real hardware.

- **Sensor identified**: AST1041 = MAX30101 pulse oximeter on I²C (0x57)
  behind the ASD2022 Wireling adapter's TCA9548A mux (0x70) with adapter
  power on D4 (matches the HARDWARE.md pin audit). TinyCircuits ships no
  Arduino library for it (their repo is hardware files only), so two
  libraries were vendored: TinyCircuits Wireling-Lib (commit 3d1acf7,
  2020-04-21) and SparkFun MAX3010x (commit 72d5308, v1.1.2 — the standard
  MAX30101 driver incl. the PBA beat detector `checkForBeat`).
- **Implementation** (`pulse_app.cpp`, PULSE_ENABLED=1): auto-probes all
  four adapter ports for a MAX30101 ACK (found on **port 3** on this
  stack), configures the SparkFun HeartRate-example profile, samples IR at
  100 Hz on the 10 ms loop tick, detects beats, computes BPM from the
  rolling average of the last four in-range inter-beat intervals
  (300–2500 ms). Honest validity lifecycle: no_contact (IR < 50000) →
  warming_up (contact, <3 clean intervals) → valid (≥3) → back to
  warming_up if beats stall >3 s. BPM never published when invalid.
- **Live evidence in PostgreSQL** (finger on sensor): 30 valid rows with
  BPM 41–105 (stable readings ~59–77; the extremes are interval-settling
  artifacts at contact transitions), preceded by no_contact and warming_up
  rows — the full honest lifecycle — all `clock_source=
  phone_server_anchor`. Compile notes: `checkForBeat` is a free function
  (heartRate.h), not a MAX30105 method; the rewritten pulse_app.cpp must
  keep the `PulseApp g_pulse;` definition.

## FULL DATA PATH PROVEN END-TO-END (26 Oct, 02:00–02:45)

**Wearable → BLE → Android phone → HTTPS → PostgreSQL now works on real
hardware.** Live evidence (boot d1-17, Galaxy S24 phone, ~02:30–02:45):

- 71 unique telemetry records ingested in minutes (`SELECT … FROM
  telemetry_records WHERE received_at > now()-8min`: sequences 3→167, no
  duplicates — identity preservation + server idempotency working).
- `clock_source = phone_server_anchor` with real `captured_at` — the
  TIME_ANCHOR relay chain (server→phone→board→record) verified on hardware.
- `gps_valid=false`, `hr_valid=false` honestly recorded (indoors; pulse
  sensor absent) — exactly the spec's honest-invalid-readings contract.
- Board serial shows the full protocol dance per TDD cycle: connect →
  SESSION_STATE parsed → time anchor applied → 1 Hz telemetry notifies →
  scheduled disconnect → re-advertise → phone reconnects (~17 cycles).

**Four more real bugs found & fixed to get here (all in-tree):**

5. **Frame CRC convention bug (all three implementations)**: senders
   computed the checksum over a contiguous range that included byte[7]
   (still 0/stale at compute time); receivers included the RECEIVED
   checksum byte → any frame with payload could never validate. Only
   zero-payload HELLOs passed (range ends before byte 7). Canonical
   convention now: CRC input = bytes[0..6] + payload chunk, never byte 7
   (`crc8_frame` in ble_app.cpp, `Frame.crc8Frame` in the app, same in the
   PC test tool). Verified: 16/16 multi-fragment writes accepted, 0 CRC
   mismatches.
6. **HELLO frame rejected by an off-by-one**: `feed_fragment` required
   `frame_len >= FRAME_HDR + 1`, but a zero-payload frame is exactly
   FRAME_HDR bytes → HELLO (and the STATUS boot-id exchange) never ran.
   Fixed to `>= FRAME_HDR`.
7. **Queue-full suppressed live sends**: when the flash queue filled
   (never acked → full for hours), `build_and_store_record` returned
   BEFORE the live phone send — a connected phone received nothing.
   Restructured: identity burned at use; live send ALWAYS attempted; the
   flash queue is only the offline backup copy (drop honestly logged).
8. **RecordCodec read past buffer** (`length=36; index=36`): the decoder
   read `lon` at `p+4` and advanced 8, misaligning the whole back half.
   Fixed to read lat/lon sequentially.

**Also this session**: PC full-duplex GATT control test (tools/
gatt_full_io.py) — HELLO→STATUS (boot id d1-15 over the air), 47
notifications received, SESSION_STATE multi-fragment writes parsed by the
board — this is the tool that isolated the CRC convention bug.

### Known issues carried forward (next session)

- **boot_id "unknown" in uploaded rows**: the phone does not (yet) capture
  the board's boot id from the STATUS reply — rows land with the fallback
  boot id. STATUS verifiably arrives (PC test); the phone-side MSG_STATUS
  parse/propagation needs one debug cycle. Identity contract wants d1-N.
- **ACK path races TDD disconnects**: uploads persist server-side, but the
  phone's `sendAck` fires right after each batch and often lands in a
  disconnected window → board never prints `ack advanced` → flash queue
  never drains. Needs a pending-ack retry queue on the phone.
- **Board freeze recurred once (02:22)** under sustained phone traffic
  (recovered via bootloader reflash; ran clean after). Same family as the
  ISR-race freeze; monitor for a pattern. USB port needed a physical
  replug (Windows zombie COM handle — happens after capture processes die
  mid-read).
- Completion spam: app relays a stale completion event in every
  SESSION_STATE → board logs COMPLETION each cycle; check
  sendSessionState's completion handling.

## NOT yet verified (gate remains OPEN)

- boot_id propagation to uploaded rows (see known issues — "unknown" today).
- ACK round trip (`ack advanced` on the board; flash queue drain).
- Second wearable in range: PEER lines on BOTH serial logs (needs board 2 —
  user reports it is not currently available; all other work proceeds).
- Phone→server over LAN (not the adb-reverse tunnel): needs the Windows
  Firewall inbound TCP 8000 rule (admin) or the deployed HTTPS server.
- GPS probe physical run (outdoor fix + time-to-first-fix; indoor NMEA flow
  already proven in the main app at ~130 chars/s).
- 10-minute stability + separation-stops-evidence runs (need board 2).
- Pulse sensor: single-finger readings PROVEN (26 Oct); multi-minute wear
  stability and motion behavior still to exercise before the demo.

## Toolchain pinned (all verified by execution)

| Tool | Version | Notes |
|---|---|---|
| arduino-cli | 1.5.2-rc.1 | Portable install at `tools/arduino-cli/` (git-ignored) |
| Board package | TinyCircuits:samd 1.1.0 | FQBN `TinyCircuits:samd:tinyscreen`; URL `http://files.tinycircuits.com/ArduinoBoards/package_tinycircuits_index.json` |
| TinyScreen lib | 1.1.0 (Library Manager) | Fonts: liberationSans_*; colors: TS_8b_* |
| STBLE (BLE ASD2116) | commit 2dcc1d4 (2022-01-19) | From TinyCircuits/TinyCircuits-TinyShield-BLE-ASD2116; BlueNRG-MS/SPBTLE-RF; CS=10 IRQ=2 RESET=9; multi-role = GAP_PERIPHERAL_ROLE_IDB05A1\|GAP_CENTRAL_ROLE_IDB05A1 (0x5) |
| SoftwareSerialZero + TinyGPS 13.0.0 | commit in TinyCircuits/TinyShield-GPS-ASD2501 (cloned 2026-10-25) | GPS pins A0=TX, A1=RX, A2=SYS_ON, A3=ON_OFF; 9600 baud |
| SPIMemory | 3.4.0 (Marzogh) | Flash CS=5; API writeByteArray/readByteArray/readAnything/writeAnything |
| Python | 3.14.2 + venv | fastapi 0.162.0, sqlalchemy 2.1.6, alembic 1.20.1, psycopg 3.3.6, pydantic 2.14.1, httpx 0.28.1, pytest 9.1.1, uvicorn 0.54.0 (full freeze in backend/requirements.txt) |
| Node/npm | 22.23.1 / 10.9.8 | react 19.3.x, react-router-dom 7.18.x, vite 8.3.x, typescript 7.0.x, vitest 5.0.x (package-lock.json pinned) |
| Docker | client 29.1.5, compose 5.0.1 | PostgreSQL 17-alpine (dev + test containers) |
| Android toolchain | Temurin JDK 21.0.12, Gradle 8.11.1, platform-tools 37.0.1 | tools/android/ + SDK at %LOCALAPPDATA%/Android/Sdk; phone reached via wireless ADB (`adb pair`/`adb connect`) |

## Software verification (commands and results)

- Android ON EMULATOR (25 Oct): API-35 x86_64 system image + AVD
  `catchme_test` (headless, swiftshader). app-debug.apk installed, launched,
  Bluetooth permission granted via UI, signed in as miya against the host
  server through 10.0.2.2:8000. Debug-only fixture button injected 5
  clearly-labeled records (boot_id `emulator-fixture-boot1`, no session);
  Room queue → OkHttp uploader → FastAPI → PostgreSQL verified: `0 pending ·
  last upload OK`, all 5 rows present with preserved identities.
  NOTE: the emulator has NO Bluetooth — the wearable BLE link itself still
  requires a physical phone. The fixture path never attaches session ids, so
  it cannot influence quest scoring (AGENTS.md fixture rules).
- Backend unit tests: `pytest tests/unit -q` → **24 passed**.
- Backend integration (PostgreSQL): `pytest tests/integration -q` → **33 passed**
  (auth/CSRF, telemetry idempotency + atomic rejection, session lifecycle,
  together completion + exactly-once awards, separation pause, one-sided
  evidence rejection, heart-rate gap, concurrent purchase race on real PG row
  locks, SSE hello + state delivery, partner-position sharing toggle, level
  boundaries 0/99/100/200/250).
- Full suite: `pytest tests -q` → **57 passed in ~19 s**.
- Live server end-to-end: `uvicorn app.main:app` + `scripts/e2e_demo_flow.py`
  → PASS: login ×2 → device bind ×2 → demo together session → accept (target
  30 s) → 16 mutual observation pairs → session completed with progress_ms
  30000 → both users 100 pts/100 XP/Level 2 → badge purchase (balance 100→50)
  → idempotent replay returns same balance → device-state relay carries
  `completion:<session-id>` and partner alias. **Telemetry in this proof is a
  clearly labeled synthetic fixture, not hardware data.**
- Web: `npm run test` → 5 passed; `npm run build` → dist/ 275 KB JS (87 KB gzip).
- Migrations: `alembic upgrade head` applied on dev PostgreSQL; `seed.py`
  seeds miya/toma (passwords from env), pair, 2 devices with pairing codes,
  3 badges, state row.
- Firmware compiles: screen probe 18,952 B (7%); BLE probe 19,444 B (7%);
  GPS probe 24,400 B (9%); flash probe 18,184 B (6%) of 262,144 B.

## Known limitations / blockers

1. **BLE gate status: alternation mode CONFIRMED required and implemented.**
   Single-board firmware evidence is recorded above. Remaining physical
   evidence for the gate: (a) second board flashing CATCHME-2 (DEVICE_ID=2)
   and PEER lines appearing on BOTH serial logs; (b) phone connecting to
   CATCHME-1 during an advertise window; (c) whether scanning coexists with
   the live phone connection; (d) 10-minute stability run. If (c) fails, the
   alternation scheduler already handles the disconnected case, and a
   connected-phone variant (scan windows while link up, connection persists)
   is implemented in the probe's `connected` branch, untested.
2. Android build toolchain absent (no JDK/SDK). Source complete; APK build
   requires installing Android Studio or JDK + SDK.
3. Pulse sensor + Wireling adapter + buzzer not connected; probes pending
   hardware. AST1041 library not yet vendored.
4. Explore geofence unset on server (`CM_GEOFENCE_LAT/LON`) by design; explore
   sessions return 409 until configured.
5. `catch_me_app` main firmware still uses the old scan-restart cadence; port
   the proven alternation scheduler + flash-CS fix there before board tests
   of the full app (the probe file is the reference implementation).

## Next actions

1. ~~Android emulator software path~~ DONE (see above). Remaining Android
   step: physical phone for BLE — enable USB debugging, `adb install
   android/app/build/outputs/apk/debug/app-debug.apk`, connect to the
   wearable, expect the ~8.5 s TDD reconnect cycle, verify live telemetry.
2. **Flash probe on unit 2** (when a second board is available) — checklist
   item requires BOTH flash units; unit 1 passed (boot #2 persistence).
3. **GPS probe**: outdoor run for time-to-first-fix; indoor run shows the
   honest no-fix state and NMEA flow (wiring evidence).
4. **Board 2 peer test** when the second stack arrives: DEVICE_ID=2 build,
   PEER lines on both logs, 10-minute stability + separation evidence.
5. Then: flash `catch_me_app` on both boards and run the end-to-end chain
   (wearable → phone APK → server → web).

## Work log

```text
Date / stage: 25 October 2026 — Stage 0 complete, Stage 1 probes built + first
  physical evidence, Stage 2/3 software complete (backend+web), firmware app
  compiles, Android source authored.
Changes: backend (FastAPI app, 19 endpoints, alembic migration, seed,
  openapi.json, e2e proof script), web (React/TS, 5 pages, SSE + honest gap
  graph), firmware probes 00-03, main firmware app modules, Android source
  tree, infra compose + Dockerfiles + nginx, portable arduino-cli toolchain +
  4 libraries.
Commands/checks run: see "Software verification" — all with actual results.
Physical evidence: screen sketch upload+serial on COM5 (uptime lines); BLE
  probe upload verified; NO peer-to-peer, GPS, flash, or pulse physical runs.
Known limitations: COM5 CDC wedge (replug pending), BLE gate pending second
  board, Android unbuilt (no JDK), pulse/buzzer hardware absent.
Next action: USB replug → BLE probe serial capture → second board peer test.
```

**Raid bench result with the softened duty (12 Nov, later):** board 1's
staged teardown SURVIVES every transition now (no wedge at raid_start —
the fix works), but its module wedges ~5 s into EVERY create-connection
procedure, even at 50% scan duty: wedged -> recovery -> phone retry relay
-> retry -> wedge, indefinitely. The same sustained-active-scanning
intolerance that board 2 showed all along now reproduces on board 1's
module (both post-restack). The hardware wall is now cleanly isolated:
**the modules cannot sustain active scanning procedures in the current
physical configuration** (passive advertising + linked radio + short 2 s
scan windows all work; sustained scanning does not). Bench session
cancelled; boards recovered and healthy on the retry loop.

**Raid shipping position (unchanged from the user's decision to keep it):**
software-complete on all four layers; the fight REACHED `raid: FIGHT!` on
hardware once (pre-restack); the server award path is fully test-covered;
the demo can trigger the fight via the serial `RAID` line; the hardware
limitation is documented honestly. The remaining physical suspects are
power delivery and the restacked shields (battery test still pending).

## No-interaction E2E sweep — 12 November 2026 (evening)

Drove the quest suite without user interaction (API + adb + serial bench
triggers). Results per quest:

- **Pet care round trip: PROVEN end to end.** Serial `CARE` (mirrors a
  physical stroke) -> board queues the daily care event -> retransmits ->
  phone POSTs /me/pet/care -> server grants +10 XP (pet_care transaction,
  `xp_delta=10`) -> ACK -> board marks cared. Daily cap verified: repeated
  triggers replay idempotently, XP unchanged (1130 -> 1130). miya's pet:
  cared_today=true, streak intact, level 12.
- **Quiz quest: PROVEN earlier today** (see the entry above) — full answer
  loop, completion, exactly-once award.
- **Explore quest: BLOCKED by peer-evidence starvation — root cause found
  and FIXED.** With fast phone reconnects both boards re-linked
  simultaneously and their brief SCAN windows coincided: peers=0 for 6+
  minutes, zero C5 catches (verified live). Fix: the TDD phase desync now
  spans the LINKED window too (`CM_TDD_LINKED_MS` 5000/5900 by device) —
  the whole cycle drifts ~0.9 s/cycle and scan/advertise windows sweep
  past each other. After the fix board 1 caught 4 peers and miya's rows
  carry `peer_observed=true`. The explore session stayed open but could
  not complete because toma's side (board 2's phone = the S24 FE) locked
  itself with a PASSWORD — adb cannot unlock it, so board 2's evidence
  and answers are frozen until the user unlocks the FE.
- **Raid: hardware wall confirmed at 50% duty** — staged teardown now
  survives every transition (no wedge at raid_start), but board 1's module
  wedges ~5 s into EVERY create-connection procedure. Both boards stay
  alive on the recovery + retry loop. Session cancelled cleanly.

**Infra notes:** the S21+ reverse tunnel broke twice more (re-applied);
the bench geofence is configured on the dev server (CM_GEOFENCE_* in
tools/restart_api.ps1, documented); the FE is password-locked and needs
the user.

**Awaiting user:** unlock the S24 FE (then explore/quiz toma-side benches
complete), pet-care + quiz physical button walk-throughs, board 2 battery
test.

**Explore bench final verdict (12 Nov, night):** board 1 catches board 2's
heartbeats (54 peers, `peer_observed=true` flowing through miya's phone),
but board 2's processor records ZERO peer observations in 8.7+ minutes of
continuous scan-window cycling — no wedges, just silent underperformance.
The same BLE module scanned fine on board 1's processor for months, so the
defect is definitively board 2's PROCESSOR (radio SPI/power path under
scan-window load). Explore requires MUTUAL peer observations (by design —
honest evidence), so its completion stays hardware-blocked. Session
cancelled cleanly. Everything else (GPS + geofence + gate + activation)
worked live.

**Complete E2E sweep scoreboard:** pet care ✅ (with cap) · quiz ✅ (full
chain + award) · discovery→partnership ✅ · explore gate/activation ✅,
completion hardware-blocked · raid activation + fight-start ✅, fight
completion hardware-blocked (demo via serial RAID trigger).

**Blocking user actions:** unlock the S24 FE (toma-side benches), board 2
battery/replacement (peer evidence + fight), physical quiz/pet walk-throughs.

## Cloudflare tunnel DEPLOYED + tunnel-native bench — 12 November 2026 (latest)

The user provisioned Cloudflare (tunnel token + Access service token in
infra/.env). Deployment + proof:

- **cloudflared runs in Docker** (new `cloudflared` service in
  infra/docker-compose.yml, token-run, `restart: unless-stopped`):
  4 registered connections to the Singapore edge, stable.
- **Public hostname** `https://catchme.12357895.xyz` routed (dashboard) to
  `http://host.docker.internal:8000` — DNS live, Access protecting the
  route (403 without credentials).
- **Access service token verified**: `GET /api/v1/health` with
  CF-Access-Client-Id/Secret headers returns 200 `{"status":"ok"}`.
- **Android**: Api client now sends the Access headers (launch extras
  `cf_id`/`cf_secret`, BuildConfig defaults empty — secrets stay in
  infra/.env, never in source). Values are .trim()ed: the .env has CRLF
  endings and a stray 
 in a header value made Access reject ~half the
  requests (verified + fixed). API_BASE default is now the tunnel URL.
- **Both phones signed in and fully operational through the tunnel** —
  miya's telemetry 2 s fresh over the public URL. LAN IP churn, reverse
  tunnels, and per-app VPN blocks no longer matter: any network works.

**Second quiz bench, tunnel-native (S21+ only; the user took the FE):**
- A stale pending quiz session blocked creation (one-session-per-pair
  409) — cancelled, fresh session created + accepted through the tunnel.
- miya's pad answered both questions via serial QANS (relay -> answer ->
  server -> next question, verified per-step); toma's answers via her
  app's API path (bench automation, documented). Completion -> miya
  +100/+100, toma +100/+100 exactly once -> miya's pet hit level 13
  (1230 XP). Quiz is RE-PROVEN over the public tunnel.

**New firmware fix: phantom-link deadlock.** With the app force-stopped
and NO process holding the link, board 1 still reported `phone=1` forever:
the phone's disconnect was lost mid-transition, board 1's terminate
targeted the dead handle and failed silently every loop — LINKED forever,
no advertise, no reconnects (the S21+ scanned for 10+ minutes seeing only
board 2). Fix: terminate once, and if the link is still there after 2 s,
escalate to the proven module_reinit(). Both boards flashed; cycling
verified healthy after the fix.

**Bench hygiene:** stale pending sessions block new ones (409) — cancel
before re-benching.

**Quiz dual-pad proof (12 Nov, latest):** with the FE back, toma answered
her set through her OWN wearable (board 2's pad, serial trigger) while
miya used board 1 — both phones relaying over their respective transports
(S21+ via the Cloudflare tunnel, FE via loopback). Session completed,
+100/+100 exactly once. The quiz quest is now proven with BOTH players
answering on their own wearables — the full intended interaction.

**Physical walkthrough session (12 Nov, latest):** the user pressed the
quiz buttons on the wearables through a full session — miya's presses
landed immediately (2/2 server-side); toma's presses fought through
board 2's watchdog resets (two resets mid-session, the quiz relay
re-armed automatically after each phone relink, and the answer
retransmit carried the presses through once the pad re-synced).
Session COMPLETED — miya +100/+100, toma +100/+100 exactly once;
toma's pet hit level 15 (1420 XP); her phone displayed "Quiz complete!
You 2/2 - partner 2/2". The compose API served the entire session.

## New board bench: scan-reception dead on arrival — 13 November 2026

The user replaced the defective board 2 with a spare TinyScreen+ ("new
board", COM7). Flashed the D2 image (all current fixes); boot clean, RAM
pet backend, phone link established instantly, TRANSMISSION verified
(board 1 catches its heartbeats steadily — 84+ peers on board 1's side).

**Diagnostic finding (new `adv_rx` STAT counter):** with its discovery
procedure starting successfully, the new board processes **ZERO
advertising reports** (`adv_rx=0` across every scan window) while board 1
processes ~40/second with the IDENTICAL code. Its OTA RX demonstrably
works for connections (phone links establish bidirectionally), and its TX
works — but advertising reports never reach the host. Same observable
signature as the old board 2's scan-deafness. Two different boards, both
scan-reception-dead, while board 1's board scans perfectly — points to
either a hardware batch issue in these spare boards/stacks or a module
revision whose advertising reports arrive in a format the vendored STBLE
1.x (2022) does not parse (e.g. a BlueNRG-2 reporting under a different
event). **Next diagnostic for the hardware owner: identify the BLE module
chip revision on the new board (dashboard/markings) and, if a BlueNRG-2,
check whether advertising reports need the enhanced-report parsing.**

**State:** both phones fully operational via the Cloudflare tunnel
(miya 2 s fresh). **Demo reset applied**: both accounts 0 points / 0 XP /
level 1, care cleared, test sessions cancelled — showcase-ready for the
paths that need no mutual peer evidence (pet care +10, quiz completion,
together-time with PIN, discovery matches).

**Explore/raid remain hardware-blocked** until a board with working scan
reception is available (both spare boards share the defect). Serial bench
triggers (RAID/QANS/CARE/PETWIPE) remain available for demos.

**Scan-deafness diagnosis closed (13 Nov):** stripped-stack test (BLE
shield only on both boards) did NOT fix the new board — `adv_rx=0` with
`vbad=0` (zero corrupted packets): the module delivers NO advertising
reports at all while scanning, rules out SPI corruption. Its TX works
(board 1 catches its adverts), connection establishment + bidirectional
data work, its scanner procedure starts successfully — but the scanner
state receives nothing OTA. Same signature as the old board 2. Two spare
boards share it; board 1's module is the only healthy scanner.
Diagnostic counters (`adv_rx`, `vbad`, drain/stuck forensics) are now
permanent in the STAT line + vendored hci.c for future boards.

**Recommendation for the demo:** run with board 1 as either player's
wearable (both phones can talk to it through their respective apps); the
second wearable's peer observations and the raid fight require a board
whose scanner works — source a replacement module/board and check its
chip revision (BlueNRG-2 advert-report format differences are the next
software suspect if the replacement also fails).

**New board extended bench (13 Nov, latest):** after the address + ADV
window fixes, the new board TRANSMITS fine (board 1 catches 84+ of its
heartbeats) and holds its phone link — but its SCANNER receives zero
advertising reports (`adv_rx=0` over 180 s of continuous TDD cycling,
`vbad=0` — no corruption, simply no reports). This matches the old board
2's failure exactly. **Two separate boards share the scanner-deaf defect;
board 1's module is the only working scanner in the fleet.** The `adv_rx`
counter (now permanent in the STAT line) made this measurable in seconds.

**Current working configuration (all through the Cloudflare tunnel):**
- toma / FE → CATCHME-1 (board 1, healthy scanner): telemetry flowing,
  peer evidence flowing (any_peer=true), uploads OK.
- miya / S21+ → CATCHME-2 (new board): telemetry flows when the board's
  phone link is up; the board's broken scanner means no peer evidence
  from miya's side and no scan-based features on that board.
- Both apps: tunnel URL persisted in prefs (survives restarts); API in
  the compose stack.

**Demo guidance:** run the quest showcase on the FE (toma) with board 1 —
pet bonding/care, quiz (+100/+100, level-up), together PIN — all proven
paths. miya's S21+ shows the app UI but its wearable (new board) cannot
contribute peer evidence until its scanner is resolved (battery power
test, module reseat, or replacement).

**Quiz physical walkthrough COMPLETE on both boards (13 Nov, latest):** fresh
quiz session created + accepted; BOTH boards' pads armed (relay verified via
the crash-log serial captures); the user pressed buttons on both wearables —
all 4 answers landed through their respective phones (miya's via the
Cloudflare tunnel, toma's via loopback), session COMPLETED, miya +100/+100
and toma +100/+100 exactly once, both pets leveled (miya level 3/210 XP,
toma level 3/200 XP — from 0/0 after the demo reset). The full user-facing
quiz flow is now proven with physical buttons on both boards.

**Crash forensics (13 Nov, night — live capture):** with the resilient
serial loggers running, board 1's crash was captured with full context:
the board died in its ADVERTISING window immediately after a post-connect
relay burst (HELLO->STATUS replied, then silence → 16 s → watchdog → USB
glitch → reboot). No error print, no wedge print — a silent loop stall.
The watchdog + auto-recovery worked as designed (the quiz session and
toma's pad state survived the reboot; the pad re-armed from the FE's
relay ✓). The stall follows the app's post-connect relay burst
(SESSION_STATE + INTERACTION + TIME_ANCHOR + PARTNER_INFO + PET_STATE
back-to-back) on the STRIPPED stacks — board 1 ran 2.7 h stable this
morning with the full stack under the same relay pattern. Leading theory:
marginal SPI signal integrity on the BLE-shield-direct-to-processor
seating corrupts module FIFO state under the relay burst → a blocked
module write/read spins the loop → WDT. Next diagnostic if pursued:
instrument BlueNRG_SPI_Read/Write with hard timeouts in the vendored
STBLE. The boards self-recover; demos are viable through the resets.

## Crash forensics made real + XP banner — 14 November 2026 (night)

**Bootloader wipe root-caused the dead forensics:** `arm-none-eabi-nm` on the
sam_ba bootloader ELF shows it zeroes its own `.bss` from `_szero`..`_ebss`
= `0x20000068`..`0x20001bbc` on EVERY reset. The stock TinyCircuits linker
script has NO `.noinit` output section, so GNU ld orphan-placed the forensics
variables right after `.data` (~`0x20000190`) — inside the bootloader's wipe
range. That is why every watchdog boot printed "previous life 0 ms": the
values were destroyed before `setup()` ran. The "verified" comment in
`watchdog_app.cpp` was wrong (verified only that it compiled).

**Fix (two parts):**
1. Patched `tinyscreen_p` linker scripts pin a real `.noinit (NOLOAD)`
   section at `0x20001C00` (above the bootloader wipe, below the heap/stack).
   Copies preserved in-repo at `firmware/linker/tinyscreen_p/` with a README
   (toolchain data dir is gitignored — the patch must be re-applied on a
   fresh toolchain install).
2. New `firmware/catch_me_app/crash_diag.{h,cpp}`: a 128-entry breadcrumb
   ring (8 B/entry: delta-ms, id, a, b) in `.noinit`, written by every
   instrumented site, dumped on the first boot after a watchdog reset
   (moved BEFORE ble init so the new life's init traffic cannot overwrite
   the previous life's tail).

**Instrumented sites:** `hci_send_req` entry/answered/timeout (opcode),
`free_event_list` (pool/rxq sizes), `HCI_Process` with pending events
(queue depth), `HCI_Isr` drain-cap trips, `Hal_Write_Serial` module-busy
retries, TDD phase transitions, phone connect/disconnect, `send_message`/
`inject_message`, telemetry record + queue-full, module re-init (both
phantom-link and wedge-recovery paths), 500 ms tick liveness with phase.
Vendored STBLE patched in BOTH copies (repo `firmware/lib/STBLE` and the
gitignored runtime `tools/arduino-cli/data/user/libraries/STBLE`).

**Forensics PROVEN on hardware:** `CM_WDT_SELFTEST` build (build-property
flag, board 1 only) froze on purpose → WDT reset → next boot printed a real
breadcrumb tail of pre-freeze HCI traffic (`0xFD01`-family vendor commands,
LE commands, write retries) across the reset. `previous_life_ms` now works.

**Overnight crash evidence (phone=0, no app):** B2 crashed 4× (00:11, 00:47,
01:26, 02:36) during plain TDD cycling — each freeze began in/just after a
SCANNING window ("discovery started" was the last line), ~35-70 min apart.
B1 ran 3.6 h+ clean on identical firmware. Two crash modes now known:
the quiz-time post-relay-burst stall and this pure radio-path wedge.
Static analysis found NO unbounded software loop: SPI transport is
single-byte non-blocking, `DEFAULT_TIMEOUT` is 100 ms, event handlers are
bounded, no HCI packet leak. The breadcrumb ring will name the exact stuck
operation on the next crash.

**XP visibility (wearable):** the quiz used to end silently (pad screen
reverted to PET). New 8 s reward banner (`flash_reward`) overrides the UI on
quiz completion ("QUIZ COMPLETE") and session completion ("QUEST COMPLETE"):
"+100 points", "+100 XP", and the live server level ("LEVEL UP! -> n" when
the pet sync raises it mid-banner). The raid fight and PIN screen keep
display ownership (banner defers). Phone side already shows
"Level N · M XP" (pet card) and "Quiz complete! +100 points & XP each".
Builds: D1 54,360 B / D2 53,804 B (20%); both flashed (boot verified, TDD
cycling, loggers reattached).

**S21+ re-configured tunnel-native for the external-network demo:** app
relaunched with `--es api_base https://catchme.12357895.xyz` + infra/.env
Access creds; prefs now persist the tunnel URL (`shared_prefs/api.xml`
verified), and the app is actively polling the API through the Cloudflare
tunnel (GET /me, /discovery-profile, /discovery, /invitations — all 200).

**Pending:** first real crash dump (B2 cadence suggests <1 h); quiz/explore
E2E with only the S21+ (dual-app-instance idea: `adb install --user 10`
same APK signed in as toma so one phone drives both sides honestly —
not yet attempted); final demo-level reset before the showcase.
