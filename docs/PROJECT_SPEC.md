# Product specification

## Objective and audience

Demonstrate an embedded system for a computer architecture course by **28 November 2026**. Users discover compatible nearby profiles using wearable Bluetooth and phone GPS, mutually accept a partnership, and complete shared quests together. A digital pet on each TinyScreen+ levels up from quest XP and is cared for daily. Wearables collect direct peer evidence; Android phones provide internet transport **and GPS location**; the web application evaluates quests and manages rewards.

**v2 revision (6 November 2026, user-directed):** phone GPS replaces the wearable GPS shield entirely; the heart-rate quest is removed; the digital pet is added. **v2.1 (14 November 2026, user-directed):** the landmark raid quest is REMOVED — the board-to-board sustained link drops at 23-30 s (a hardware wall documented across every configuration since 12 Nov); raid creation is rejected and historical raid sessions stay readable. See `docs/QUEST_INTERACTION_PLAN.md` for quest interaction and `docs/DISCOVERY_PLAN.md` for discovery behavior.

## Scope

- Two complete TinyScreen+ devices and two Android phones; companion apps remain open during quests.
- Direct wearable-to-wearable Bluetooth presence, phone GPS location relayed with telemetry, flash buffering, and buzzer completion feedback. The wearable GPS shield and pulse sensor are not part of the product (v2) — they may remain stacked, unpowered/unread.
- A digital pet per user: species/name/needs live on the wearable in flash; XP/level is server-owned and synced through the phone; daily care grants +10 XP once per user per day.
- Linux Docker host for a React web application, FastAPI API, and PostgreSQL.
- Seeded accounts bound to devices, with editable age, interests, preferences, and display name, rule-based compatibility filtering, opt-in discovery, invitations, and partnership termination. Preserve existing seeded pairs until explicitly ended.
- Shared quest sessions require both users to accept. Partner location sharing remains separate from GPS discovery opt-in; discovery returns approximate distance and freshness rather than raw coordinates.
- No public registration, AI matching, swiping, chat, real-money shop, background/locked-phone guarantee, wearable Wi-Fi shield, Pi gateway, or runtime AI service.

## User flow

1. Each user signs in on the companion app and binds the assigned wearable, then bonds with and names their pet on the wearable.
2. Users edit profiles, enable discovery, and browse compatible users. Bluetooth indicates radio presence; phone GPS uses fresh fixes (<=30 seconds) or labeled last-known fixes (<=15 minutes). A partner invitation must be accepted before starting a shared quest.
3. The dashboard shows connection, points, XP/level, and pet status. One partner starts a quest; the other accepts the same session. Allow one active shared quest per pair.
4. Devices collect direct peer evidence; phones attach their real GPS fix to each relayed record. Phones upload records and relay server state and pet state to the screens.
5. The server updates progress and issues each user's award exactly once; daily pet care also earns +10 XP at most once per day.
6. Users spend points on profile badges in the web shop. Previously earned XP remains unchanged; the pet's level follows the same XP.

## Quest definitions

| Quest ID | Normal duration | Demo duration | Evidence |
|---|---:|---:|---|
| `together` | Existing 600-second configuration retained | 30 seconds | Mutual start PINs, direct peer presence on both devices, then new mutual end PINs before awards |
| `explore` | 120 seconds | 20 seconds | Direct peer presence plus both participants' valid phone-GPS fixes (relay timestamped, true fix age) inside a configured outdoor geofence |


- `heart_challenge` is **removed** (v2): creation is rejected, clients hide it, and no pulse sensor is required. Historical heart sessions remain readable in history views.
- Each successful session awards each participant **100 spendable points and 100 lifetime XP**.
- Level is `1 + floor(lifetime_xp / 100)`; the pet shares this level and evolves at 100 XP (teen) and 300 XP (adult).
- Daily pet care (feed/stroke on the wearable) grants **+10 XP, once per user per calendar day**, enforced server-side. Care works offline and syncs later; the cap is never exceeded.
- Seed three one-time cosmetic badge purchases: `first_spark` (50 points), `adventure_pair` (100), `heart_duo` (200). These have no monetary value.
- A repeat quest requires a new mutually accepted session. Completing or retrying one session cannot award it again.
- Demo mode must be prominent on all relevant screens and recorded in session data. Demo and standard progress do not merge.
- Default quest-start UI to demo mode for the course presentation. Together timing begins only after both start PINs; reaching its target waits for both end PINs before rewards. 

## Evidence and timing defaults

- Discovery freshness is separate from quest evidence. Keep a timestamped last-known position on the server; never use it to extend explore's 10-second GPS limit. Phone fixes carry their true age (`fix_age_ms` = fix time − record capture time); never clamp or fabricate ages.
- Evaluate contiguous evidence intervals using capture time, not HTTP arrival time.
- Peer-presence intervals require successive verified direct peer observations no more than **10 seconds apart**. Intersect the evidence reported by the two participants. A larger gap contributes no time and must not be bridged by interpolation.
- Overlapping intervals count once. Progress accumulates valid intervals until completion; invalid intervals pause rather than reset the session.
- Explore uses a **50-metre radius**, configured latitude/longitude, and fixes no older than **10 seconds at the evaluated time**. No default real-world destination is invented; the demo location must be configured before testing.
-- Cancellation closes the session without awarding incomplete progress. Completed sessions are immutable with respect to awards.
- Records without a trustworthy capture-time anchor may be retained for diagnostics but cannot award progress until their timeline is resolved.

## Screens

**Discovery extension:** Android/web gain profile/settings, merged nearby results with freshness/source labels, invitation inbox, and partnership controls. TinyScreen+ shows up to three compact discovery results when unpaired. See `DISCOVERY_PLAN.md` for exact labels and opt-out behavior.

**Pet:** the wearable shows the pet (species sprite, mood, needs), its synced level (marked stale when offline), and offers care via the four buttons; the phone app and web dashboard show species/name/level/mood/care streak and the daily-care state.

**Wearable:** pet screen; phone/peer status; active quest progress; approximate partner distance with freshness; battery status if reliable measurement is available. Prioritize readable text on the small display over maps.

**Android:** sign-in, wearable association, session accept/start/cancel, live readings, upload queue and last-success status, sharing toggle, pet card. Foreground operation only is required.

**Web:** paired dashboard, quests, points/level with pet status, badge shop, transaction history, explicit demo mode and stale-data states.

## Completion criteria

The discovery extension requires two physical users to acquire outdoor phone fixes, enter a building, see honest last-known labels, discover each other directly over Bluetooth, accept a partnership, and complete a quest. Discovery expiry must not be bypassed by queued uploads.

Full hardware acceptance requires both physical devices to complete all three quests through two Android phones and the real backend — with exactly-once awards. Invalid data pauses progress. Separation stops together-time. Retried uploads do not duplicate progress or rewards. An earned balance can purchase a badge without reducing XP; daily care never pays twice in one day. The full stack runs on batteries for a measured demonstration duration.

The product must not be declared hardware-complete until the BLE feasibility gates and physical tests in `TEST_PLAN.md` pass.
