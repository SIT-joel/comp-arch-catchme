# GLM 5.3 implementation plan: nearby discovery

Approved scope revision: 26 October 2026. Deadline: 28 November 2026.
Status: implemented in software; physical acceptance is partial and remains pending. See `PROGRESS.md` for executed checks and the specific outstanding hardware evidence.

## Extend the existing application

Preserve the existing firmware, Android, backend, web, migrations, tests, and physical results. Read the newest entries in `PROGRESS.md` before acting; older entries contain superseded toolchain and firmware limitations. Do not restart from a scaffold or overwrite historical evidence.

The wearable Wi-Fi shield remains unavailable by assumption. **v2 (6 November): Android phones provide internet transport AND geographic location** — phone GPS fixes are relayed with telemetry (`gps.source:"phone"`, true fix age) and feed both discovery and explore. The wearable GPS shield is no longer part of the product. The heart-rate quest is removed; quest set is `together`, `explore`, `raid`. Points, XP, pet, and the badge shop are preserved.

## Profiles and eligibility

- Keep seeded accounts and no public registration. Add editable display name, age (18–99), interest tags, preferred minimum/maximum age (18–99, minimum <= maximum), and discovery radius.
- Seed interest choices: gaming, music, fitness, food, movies, travel, reading, and outdoors. Users may select any subset; no shared tag means no match.
- Require both users' age preferences to include the other's age and at least one shared interest. Exclude self, incomplete profiles, and partnered users.
- Rank by shared-interest count descending, then display name and user ID for deterministic ties.
- Bluetooth and GPS discovery have separate opt-in switches, both off initially. A result from a method requires that method enabled for both users.
- GPS radius defaults to 500 metres; accept 100–5,000 metres. Filter using the requesting user's radius; the other user's radius controls their own list.
- Refresh Android/web discovery every five seconds while its screen is open. This polling is necessary for expiry even when no new SSE event arrives.

## Phone GPS and last-known location (v2)

Only valid fixes with trustworthy capture time can update the server's durable last-known position. v2: fixes come from the phone, stamped into telemetry at relay time with `source:"phone"` and the true fix age. Derive actual fix time as `captured_at - gps_fix_age_ms`; never use upload receipt time as fix time and never clamp ages.

| Age of actual fix | Discovery state | Behavior |
|---|---|---|
| 0–30 seconds inclusive | `fresh` | Geographic results allowed |
| >30 seconds through 900 seconds inclusive | `last_known` | Geographic results allowed with stale-location labels |
| >900 seconds | `expired` | No results contributed by this position |
| No trustworthy valid fix | `missing` | Bluetooth-only discovery |

- Require both users' positions to be fresh or last-known for a GPS result. Compare the stored coordinates; this is not proof of either user's current position indoors.
- If the requesting user's fix is stale, show **“Near your last GPS location”** and its age. If only the other user's fix is stale, show **“Based on their last GPS location”** and its age. If both are stale, show both ages.
- Distances are approximate. Discovery responses return distance rounded to the nearest 50 metres and never raw coordinates. Filtering uses the unrounded distance.
- When the requesting user's position expires, show **“GPS location expired—go outdoors to refresh.”** Before the first fix, show **“Waiting for GPS fix.”** Bluetooth can still contribute results.
- Invalid/no-fix readings must not erase the last valid position. Older, repeated, or delayed records must not replace a newer fix or refresh its timestamp. A delayed new fix is still classified using its original age.
- Reject future/unknown-time fixes for discovery until the timeline is resolved. Use the existing trustworthy-clock rule (maximum 2 seconds uncertainty); do not infer freshness from connection status.
- Persist the last-known fix through server restarts and recompute its age at read time. Discovery expiry does not require deleting historical telemetry.
- The firmware currently caps GPS age in a 16-bit field. Do not represent 15 minutes by merely increasing its stale threshold. Cache fixes received while valid on the server; do not change the current GPS validity rule to label old coordinates valid.
- Configurable defaults: fresh limit 30 seconds and expiry 900 seconds. Tests must use a controlled clock.

## Bluetooth discovery and radio scheduling

- Use direct wearable scan observations; phone scanning is not a substitute. Phones relay observations and filtered results.
- Preserve the implemented time-division radio scheduler. Recorded single-board experiments rejected scanning while phone-connected and simultaneous advertising/scanning. Do not restart concurrent-mode exploration as the default approach.
- Extend the current device-ID 1–2 restriction into discovery of provisioned users with opaque identifiers, using a bounded observation buffer of 16 latest unique identifiers; replace the oldest when full.
- Use a separate versioned discovery advertisement/message from session-bound quest heartbeats. No names, ages, or interests in advertisements. Keep the existing manufacturer payload framing/library conventions that were verified on hardware.
- Provision a random opaque discovery token per device through the authenticated phone link. Map it server-side; invalidate it on device unbinding/reassignment. This classroom token is not a claim of unlinkability or anti-spoofing security.
- Each observation includes its original capture time and identity for idempotent upload. Expire it after 15 seconds; delayed uploads cannot revive old presence. A new physical reception can refresh discovery presence, but a retransmitted observation cannot.
- General discovery operates only while unpaired. On pairing, stop general discovery and prioritize partner communication/quests. Confirm firmware receipt of mode changes and display pending synchronization if the device is disconnected.
- Stop discovery advertising/scanning when opted out on the next phone link; the server must immediately suppress the user regardless of device connectivity.
- Bluetooth-only results say **“Detected nearby”** with distance null. Do not claim exact distance or same-room presence.
- Validate two-board discovery and radio timing physically; single-board alternation success does not prove both boards' scan/advertise windows overlap suitably.

## Combined results and connectivity

Union eligible Bluetooth and GPS candidates by user ID; show one result with one or both source flags. Losing one source must not hide a still-eligible result from the other source. Expiry and opt-out are evaluated on every query.

Display full lists on Android/web and up to three compact results on TinyScreen+. Relay display names, shared-interest summary, source labels, location age/freshness, and rounded distance only. Use bounded text lengths on the wearable.

Server connectivity is required for current profile filtering and invitations. On connection loss, clearly mark discovery unavailable/stale instead of continuing to present cached profiles as current matches. Local GPS and pulse acquisition may continue normally.

## Invitations and partnership lifecycle

- Users may invite a currently eligible discovery result. Revalidate compatibility and eligibility on creation; reject self, already-partnered users, and duplicate pending invitations for the same pair.
- Invitations expire five minutes after creation. The recipient may accept or decline. Acceptance requires an unexpired pending invitation, both users still eligible by profile/opt-in rules, and both unpaired. Do not require uninterrupted radio/GPS presence between invitation creation and acceptance.
- Acceptance is transactional and idempotent. Lock both users in canonical order and enforce one active partnership per user in the database, not only application checks.
- Replace reliance on separate `user_a_id` and `user_b_id` uniqueness constraints with an active membership relation whose `user_id` is unique across all partnerships. Preserve partnership history with an end timestamp.
- Either user may end a partnership only when neither a pending nor active quest remains for it; cancel those sessions first. Remove active memberships and notify both users. Preserve historical participants, awards, balances, transactions, and purchases.
- Partner invitation acceptance is separate from quest-session acceptance.
- Preserve existing seeded partnerships during migration. Provide an explicit end-partnership UI for demonstrating discovery; never wipe or silently unpair existing users.
- Migration must preflight existing memberships for cross-column duplicates and abort with a useful report if inconsistent. Do not delete data to make the migration pass.

## Quest boundary

Retain all current quest evidence thresholds, durations, awards, levels, and shop behavior. **Explore still requires fixes no older than 10 seconds.** The 15-minute discovery cache must never enter quest scoring. Discovery observations must never become session heartbeat evidence or grant points.

## Implementation order

1. Reconcile current source with progress records. Preserve working toolchain, W25Q driver, radio scheduler, and existing tests.
2. Add non-destructive migrations, editable profiles/settings, durable last-known positions, and backend filtering tests.
3. Extend discovery advertisements/scans and Android framing/upload while preserving quest transport. Version changed messages; reject unknown versions explicitly rather than misdecoding them.
4. Add discovery lists, TinyScreen+ summaries, invitations, active partnership constraints, and partnership termination.
5. Run regression suites and real outdoor-to-indoor tests. Finish integration by 22 November; keep 23–27 November for fixes, report, and rehearsal.

Independent backend/web work may use labeled fixtures while hardware is unavailable. Keep fixtures separate from genuine hardware evidence and awards.

## Acceptance tests

- Mutual age boundaries, invalid ranges, shared/no interests, self exclusion, opt-in per method, radius bounds, and deterministic ordering.
- GPS at 30/31 and 900/901 seconds; stale fix on either/both users; missing GPS; invalid reading after valid fix; restart with cached position.
- Original fix time accounts for reported fix age; duplicate/out-of-order/delayed telemetry cannot rejuvenate or regress the cache; future/unsynced records are excluded.
- BLE at 15/16 seconds; retransmission vs new reception; multiple IDs including beyond 1–2; buffer capacity; mixed source deduplication; GPS expiry leaves valid BLE result.
- Opt-out hides profiles immediately and radio settings synchronize later without showing opted-out users.
- Invitation expiry, decline, duplicate request, concurrent acceptances involving the same user on opposite pairing sides, migration preserving old pairs/history, and termination blocked by unfinished quests.
- Full regression suite: no discovery data grants quest credit, cached locations cannot satisfy explore, no duplicate points or purchases.
- Physical demo: outdoor fixes, enter classroom, last-known labels with increasing age, direct BLE discovery, accept partnership, complete a quest. Record actual latency and two-device scan/advertise behavior.

## Handoff requirements

OpenAPI is generated from implemented routes. Regenerate it when those routes change. Update progress with executed commands/results and physical evidence. Do not treat software completion as physical acceptance.
