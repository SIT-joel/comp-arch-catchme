# Implementation stages

Deadline: **28 November 2026**. These are target dates, not completed milestones. Preserve hardware verification status if dates slip.

## Latest quest task (30 October)

Implement [QUEST_INTERACTION_PLAN.md](QUEST_INTERACTION_PLAN.md): server phase gates/migrations and tests first, then Android/BLE commands and TinyScreen+ button input, then physical validation. Together defaults to a 30-second demo and needs mutual four-digit PIN exchange before timing and again before awards. Keep Your Cool replaces the generic heart quest presentation with a 10-second baseline and two 10-second truth-or-dare turns. Preserve quest IDs, historical sessions, existing discovery work, and all unrelated hardware results. This documentation revision does not implement those features or resolve the separate queue/ACK findings.

## Current extension: discovery (26 October)

The application already has implementation and recorded hardware work. The stages below are the original baseline, not instructions to restart. For the next work, follow [DISCOVERY_PLAN.md](DISCOVERY_PLAN.md):

1. Reconcile current source and recent progress; preserve existing toolchain and hardware fixes.
2. Add profile/settings migrations, durable timestamped GPS caching, compatibility filtering, and backend tests.
3. Extend wearable discovery and Android transport using the implemented time-division scheduler.
4. Add discovery UI, invitations, transactional active memberships, and partnership termination without resetting existing data.
5. Run regressions and physical outdoor-to-indoor discovery, pairing, and quest demonstration by 22 November.

Last-known GPS is for discovery only: fresh <=30 seconds, usable with age labels through 15 minutes, expired afterward. Do not alter explore's 10-second threshold or substitute phone location. Finish with documentation/rehearsal on 23–27 November.

## Stage 0 — Environment and inventory

- Read the handoff, inspect the workspace, run the tool checks, and record missing prerequisites.
- Count parts, record both device revisions/battery capacities, and confirm two Android phone OS versions.
- Create source folders, reproducible dependency manifests, and a consistent local development setup.
- Audit pins, buses, timers, and library support from manufacturer examples.

Exit evidence: documented inventory, actual tool versions, exact build target, and a minimal sketch that compiles. A successful upload/display check requires hardware evidence separately.

## Stage 1 — Hardware and Bluetooth gate, target 1 November

- Implement standalone screen, GPS, pulse, flash, and buzzer probes.
- Implement direct A/B heartbeat probe and minimal Android telemetry client.
- Baseline experiment completed: recorded hardware results require scheduled alternation. Preserve that implementation and complete remaining two-board timing/peer checks.
- Exercise separation/reconnection and record observed cadence, local BPM refresh, phone delay, and failure behavior for at least 10 minutes.
- Complete remaining-stack pin audit before combining peripherals.

Exit evidence: physical logs and observations satisfy `HARDWARE.md`. If blocked, state the exact unsupported behavior. Continue independent software with labeled fixtures, but do not mark this gate passed or silently change proximity semantics.

## Stage 2 — End-to-end telemetry, target 8 November

- Firmware: acquisition state machines, local display, bounded record format, recoverable flash queue.
- Android: login/provisioning, connection lifecycle, message reassembly, persistent queue, HTTPS uploads, server ACK relay.
- Backend: migrations, authentication, ownership, idempotent ingestion, server time, current device state.
- Freeze tested BLE framing and transport cadence in `INTERFACES.md` after hardware results.

Exit evidence: a real sample reaches persistent server storage, retry produces no duplicate, and a server state response returns to the device. Add automated tests using the same logical contract.

## Stage 3 — Product slice, target 15 November

- Implement session invitation/acceptance/cancellation, three quest evaluators, demo mode, and progress.
- Implement per-user awards and XP/level calculation in transactions.
- Add the three-badge catalog, purchase idempotency, and transaction history.
- Build web dashboard, live graph, shop, and invalid/stale states.
- Relay completion event and partner summary through Android to the wearable.

Exit evidence: tests cover boundaries, retries, authorization, and purchase races. All intended controls operate against the backend rather than UI-only mock state.

## Stage 4 — Integrated validation, target 22 November

- Test outdoors with both devices/phones, real GPS, stationary pulse readings, and the full stack.
- Test network outage, reboot, delayed upload, duplicate records, lost contact, and partner separation.
- Measure battery runtime and BLE/upload latency.
- Deploy Compose on the Linux host with HTTPS and actual configured demo location.

Exit evidence: completed physical checklist and reproducible build/deploy instructions. Do not claim background-phone behavior, exact ranging, or robust anti-cheating beyond what was tested.

## Stage 5 — Demonstration and report, 23–27 November

- Freeze features, fix defects, rehearse the shortened demo, and retain a standard-duration test result.
- Prepare architecture diagrams, evidence screenshots/logs, and the report outline in `DEMO_AND_REPORT.md`.
- Produce firmware artifacts/instructions and Android debug APK, plus database backup/restore instructions.
- Record final known limitations and exact start-up procedure.

## Handoff at every stage

Update `PROGRESS.md` with files changed, actual checks/results, remaining physical checks, blockers, and next action. Keep contract changes synchronized across firmware, Android, API schemas, fixtures, and documentation.
