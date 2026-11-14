# GLM 5.3 implementation instructions

## Mission

Implement the course prototype described in `docs/PROJECT_SPEC.md` by 28 November 2026. Start with `GLM_START_HERE.md` and `docs/PROGRESS.md`. The repository already contains firmware, Android, backend, and web implementation; preserve that work and recorded hardware results.

The current extension is the **v2 product revision (6 November 2026, user-directed)**:

1. **Phone GPS replaces the wearable ASD2501 GPS entirely.** Phones stamp their real fix (with true fix age) into telemetry at relay time; all existing freshness rules keep applying. This reverses the previous "no phone GPS" rule by explicit user decision.
2. **Digital pet** on each TinyScreen+ (ported from the bench-verified fork `D:\catch_me_pet`): levels from the same server-owned quest XP, tamagotchi daily care via buttons granting +10 XP once per user per day, synced through the phone.
3. **The landmark raid quest is REMOVED** (`raid`, 14 Nov user decision): the board-to-board sustained link drops at 23-30 s — a hardware wall documented across every configuration since 12 Nov (the gate experiment, the session fights, and the practice fights all hit it). Raid creation is rejected as an unknown quest; historical raid sessions stay readable. The board-to-board fight remains a documented hardware finding, not a product feature.
4. **The heart-rate quest is REMOVED** (`heart_challenge`): no creation, no UI, no sensor. The AST1041 pulse sensor leaves the required stack; records keep carrying `hr_valid=false` honestly. Historical heart sessions stay readable. Quest set: `together`, `explore`, `quiz`.

See `docs/PROJECT_SPEC.md` (v2 sections), `docs/QUEST_INTERACTION_PLAN.md` (together PIN spec), and `docs/INTERFACES.md` (new contracts). Earlier extensions (discovery, PIN exchange) remain in force except where v2 changes them above.

You are the implementation agent. Build and verify the product in this workspace, rather than stopping at another proposal. GLM 5.3 is the development assistant only; do not add an LLM API dependency to the product. This file does not select a model: the user selects GLM 5.3 in their coding agent.

## Current Wi-Fi assumption

Treat the ASD2123 Wi-Fi TinyShield as unavailable for this implementation. Exclude it from the active stack, firmware dependencies, and required tests. Do not spend implementation time troubleshooting it unless the user explicitly reopens that task.

This is a scope assumption, not a confirmed diagnosis that the board is broken or unusable. The user has physically stacked the boards; combined Wi-Fi/Bluetooth/GPS operation has not been demonstrated. Physical stacking alone is not functional verification. Do not claim otherwise or require the user to return the board.

The data path is:

```text
Wearable A <--- direct BLE peer messages ---> Wearable B
    | BLE                                      | BLE
Android phone A                           Android phone B
    | HTTPS over phone internet                | HTTPS over phone internet
    +---------------- server ------------------+
                         |
                       web app
```

The phones may use mobile data or their own Wi-Fi. Excluding the wearable Wi-Fi shield does not prohibit phone Wi-Fi. The Raspberry Pi is not required.

## Read before implementation

1. `docs/PROGRESS.md`: actual completion state, tools, and pending evidence.
2. `docs/PROJECT_SPEC.md`: product behavior and acceptance criteria.
3. `docs/HARDWARE.md`: inventory, revisions, pin audit, and BLE feasibility gate.
4. `docs/ARCHITECTURE.md` and `docs/INTERFACES.md`: component boundaries and contracts.
5. `docs/IMPLEMENTATION_PLAN.md`, `docs/TEST_PLAN.md`, and `docs/TOOLS_AND_SETUP.md`: execution order and checks.

Latest explicit user instructions take priority over older project documentation. Update affected documents when an agreed requirement changes.

## Requirements that must not silently change

- Two TinyScreen+ devices, two Android phones with the app open, Linux Docker server.
- Direct Bluetooth evidence exchanged between the two wearable devices.
- Location comes from **phone GPS fixes relayed with telemetry** (v2 rule; the wearable ASD2501 GPS is no longer part of the product). Fixes carry their true age; never fabricate or clamp ages. All freshness limits (explore 10 s, discovery 30 s/900 s) still apply.
- The heart-rate quest is removed; no pulse sensor in the required stack. Records honestly report `hr_valid=false`. Historical sessions remain readable.
- No soldering, board modifications, wearable Wi-Fi, or Pi gateway.
- Three quests (`together`, `explore`, `quiz`), server-owned points/XP, cosmetic reward shop, seeded editable accounts, nearby discovery, and mutually accepted partnerships. Preserve existing seeded partnerships until users explicitly end them.
- Pet XP is the same server-owned `lifetime_xp`; awards stay exactly-once per session; daily care grants at most +10 XP per user per calendar day. The wearable may own cosmetic pet state (species/name/needs) in flash, never the economy.
- Show freshness/age honestly everywhere; never use cached discovery coordinates as explore evidence.

## Work method

1. Inspect the workspace and current progress before editing. Preserve existing user work.
2. Work in the stages in `docs/IMPLEMENTATION_PLAN.md`. Keep modules independently testable.
3. Resolve discoverable questions through repository inspection and primary manufacturer documentation before asking the user.
4. Pin actual working dependencies and record exact board packages, tool versions, and build commands. Do not invent library calls or claim a dependency exists without checking.
5. Maintain `docs/PROGRESS.md` after each meaningful stage: changes, checks with results, pending hardware evidence, blockers, next action.
6. Distinguish planned, implemented, software-tested, and physically verified status. Compilation is not hardware validation.
7. Use clearly labeled fixtures to advance independent software work while hardware is unavailable. Never turn those fixtures into production fallback readings.
8. Ask the user only for non-discoverable constraints or decisions that materially change the agreed scope. Report an unsatisfied hardware gate rather than silently using phone-assisted proximity.
9. Do not introduce automatic package installation, destructive reset scripts, secrets in source, or paid runtime AI services.
10. Run relevant tests and document exact outcomes. Do not leave placeholder buttons or fake balances presented as finished features.

## Engineering defaults

- Arduino C++ firmware; native Android Kotlin/Jetpack Compose; React/TypeScript web; FastAPI/Python; PostgreSQL; Docker Compose.
- Inspect existing source and hardware results first; extend the working implementation instead of recreating completed probes or scaffolds.
- Generate backend OpenAPI from the implemented routes and keep contracts/examples aligned with `docs/INTERFACES.md`.
- Use database constraints and transactions for idempotent ingestion, awards, and purchases.
- Keep capture time separate from receive time. Never count network downtime or missing peer observations as together-time.
- Validate credentials and device ownership at the server. Keep exact locations and raw sensor evidence private to authorized users.
- Use fixtures and test accounts without personal data. Separate demo mode visibly from standard sessions.

## Hardware scope and first milestone

Each wearable uses TinyScreen+ ASM2022, ASD2116 BLE (existing board Rev1), ASD2202-R-F flash, ASD2022 Wireling adapter, and a battery. The ASD2501 GPS shield and AST1041 pulse sensor are **no longer part of the product** (v2: phone GPS; heart quest removed) — they may remain physically stacked but the firmware must not depend on them. A buzzer remains optional after its model/port are confirmed. TinyScreen+ is already the processor; do not require an additional TinyDuino.

Preserve the implemented radio scheduler: recorded experiments require time-division between scanning and phone connections. (The raid game's dedicated board-to-board radio mode was removed with the raid quest on 14 Nov; the gate experiment's finding — sustained board-to-board links drop at 23-30 s — is documented in docs/PROGRESS.md.)

- Do not assume the BLE module's advertised master/slave capability proves the host library supports the needed concurrent connections.
- Use the established scheduled alternation for quest/discovery traffic.
- Missing peer evidence must pause credit. Never substitute phone connectivity or server co-location for direct wearable evidence.
- (The board-to-board gate DID fail: sustained links drop at 23-30 s. The raid quest was removed on 14 Nov by user decision rather than weakening evidence rules.)
- When physical access is needed, provide the exact sketch/build, wiring prerequisites, test steps, and serial output/observations required from the user.

## Product checklist

- Follow `docs/DISCOVERY_PLAN.md` for compatibility filtering, opt-in settings, source deduplication, timestamped location cache, and invitation/partnership behavior.
- Three shared quests: PIN-gated together-time, outdoor geofence visit (phone GPS), and the Know-Your-Partner quiz.
- Both users accept a session. Communication gaps pause progress.
- Award each user 100 points and 100 lifetime XP exactly once per completed session.
- Level is `1 + floor(lifetime_xp / 100)`; the pet's level and evolution stages derive from the same XP. Spending points never reduces XP.
- Daily pet care grants +10 XP at most once per user per calendar day (server-enforced); care works offline and syncs later, but never more than the cap.
- Three cosmetic badges priced at 50, 100, and 200 points; transactional purchases cannot overspend.
- Use durations, freshness limits, and evidence rules from `docs/PROJECT_SPEC.md`; show demo mode explicitly.
- Preserve offline telemetry identity across retries and acknowledge only server-persisted records.
- Display invalid or stale readings honestly. Phone GPS fixes carry their true age; never present a stale fix as fresh.

## Session handoff

After each meaningful milestone, record what changed, commands actually run, their results, physical checks still pending, and the next concrete action in `docs/PROGRESS.md`. End each work session with a concise status and precise user action only if needed. Do not repeatedly ask permission for ordinary implementation already authorized by the project brief.

## Delivery

Provide reproducible build/run instructions, migrations and seed command, debug APK, firmware upload instructions, test results, physical verification notes, and demo script. Do not commit generated binaries unless explicitly requested; document where to find them.
