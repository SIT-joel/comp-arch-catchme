// Catch Me wearable firmware — compile-time configuration.
// Device identity: for the prototype the device id is set at compile time
// (1 = Wearable A / alias 1, 2 = Wearable B / alias 2), matching the server's
// seeded firmware_alias. Flash-provisioned identity can replace this later.

#pragma once

#define FIRMWARE_VERSION 1

#ifndef DEVICE_ID
#define DEVICE_ID 1
#endif

// --- BLE (ASD2116 BlueNRG-MS; pins fixed by board: CS=10, IRQ=2, RESET=9) ---
#define CM_ADV_INTERVAL_MIN_MS 100
#define CM_ADV_INTERVAL_MAX_MS 150
#define CM_SCAN_INTERVAL 0x0400  // 0.625ms units
#define CM_SCAN_WINDOW 0x0400
#define CM_SCAN_RESTART_MS 8000

// Peer heartbeat advertised in the manufacturer-specific field:
// bytes: [0]=0xC5 magic, [1]=DEVICE_ID, [2..3]=heartbeat counter LE,
// [4..5]=session token hash LE (fnv1a-16 of the active token; 0 when none).
#define CM_PEER_MAGIC 0xC5
#define CM_PEER_ADV_LEN 6

// Nearby discovery advertisement (docs/DISCOVERY_PLAN.md): separate,
// versioned message — NOT session evidence. Bytes: [0]=0xC6 magic,
// [1]=discovery payload version, [2..3]=opaque discovery token LE
// (provisioned through the authenticated phone link; server-side mapped).
// No names, ages, or interests travel in advertisements.
#define CM_DISC_MAGIC 0xC6
#define CM_DISC_VERSION 1
#define CM_DISC_ADV_LEN 4

// A discovery observation contributes presence for at most this long after
// its physical reception (docs/DISCOVERY_PLAN.md: 15 s rule).
#define CM_DISC_OBS_MAX_MS 15000
// Bounded buffer of latest unique observed discovery tokens.
#define CM_DISC_BUFFER 16
// Compact discovery results relayed phone -> wearable for the display.
#define CM_DISC_RESULTS_MAX 3

// Evidence rule ceiling: an observation older than this is not "recent".
#define CM_PEER_RECENT_MS 10000

// --- GPS (ASD2501) ---
#define GPS_RXPin A1
#define GPS_TXPin A0
#define GPS_ONOFFPin A3
#define GPS_SYSONPin A2
#define GPS_FIX_STALE_MS 10000

// --- Flash (ASD2202-R-F) ---
#define FLASH_CS 5
#define FLASH_QUEUE_BASE_ADDR 0x00010000UL  // keep sector 0 for metadata
#define FLASH_QUEUE_MAX_RECORDS 2000        // bounded ring, ~2000 records

// --- Wireling pulse sensor (AST1041, MAX30101 over the ASD2022 adapter) ---
// The adapter mux (TCA9548A at 0x70) selects the Wireling port; the sensor
// answers at I2C address 0x57. When disabled, records carry heart_rate
// .valid=false / status=no_contact (honest absence, never a fabricated BPM).
#ifndef PULSE_ENABLED
#define PULSE_ENABLED 1
#endif
#ifndef CM_PULSE_I2C_ADDR
#define CM_PULSE_I2C_ADDR 0x57
#endif

// --- Buzzer (AST1035) — model/port pending physical audit ---
#ifndef BUZZER_ENABLED
#define BUZZER_ENABLED 0
#endif
#ifndef BUZZER_PIN
#define BUZZER_PIN 4  // candidate; must be audited against Wireling D4 power use
#endif

// --- Record cadence ---
#define CM_RECORD_PERIOD_MS 1000        // one telemetry record per second
#define CM_UI_REFRESH_MS 1000           // local display refresh
#define CM_LOCAL_HR_REFRESH_MS 1000

// --- Strict time-division radio windows (hardware-verified necessity) ---
// This BlueNRG-MS host stack rejects advertise+scan (0x0C) and
// scan-while-connected (0x82), so the radio alternates. Cycle: 5 s phone
// link (upload), 2 s peer scan (evidence ~8 s apart, within the 10 s rule),
// 1.5 s advertising (phone auto-reconnects).
//
// DEVICE 2 runs a deliberately DIFFERENT cycle (2.3 s advertising): two
// identical 8.5 s TDD cycles phase-drift very slowly (crystal tolerance
// ~0.1%), so the boards can sit scan/advertise anti-correlated for hours —
// each hearing the other only while itself not listening — starving the
// evidence intersection (observed 30 Oct: 0 scored ms despite dense
// one-sided evidence). A 9.3 s cycle sweeps the relative phase in ~1-2 min,
// keeping observation chains within the 10 s rule. Evidence rules are
// unchanged; only the radio phase relationship differs.
// Phase desync needs to span the LINKED window too: with fast phone
// reconnects both boards re-link simultaneously and their brief SCAN
// windows coincided (verified live 12 Nov — peers=0 for 6+ minutes, zero
// C5 catches). A device-dependent LINKED duration makes the whole cycle
// drift (~0.9 s/cycle), so the scan/advertise windows sweep past each
// other within a couple of minutes regardless of reconnect timing.
#if DEVICE_ID == 2
#define CM_TDD_LINKED_MS 5900
#define CM_TDD_SCAN_MS 2000
#define CM_TDD_ADV_MS 1500  // 2300 broke the module's next scan reception (13 Nov bisect)
#else
#define CM_TDD_LINKED_MS 5000
#define CM_TDD_SCAN_MS 2000
#define CM_TDD_ADV_MS 1500
#endif

// --- v2 raid gate experiment ---
// Board-to-board connection gate (docs/QUEST_INTERACTION_PLAN.md stage 4):
// gate builds (CM_GAME_GATE=1, bench only) suspend the TDD scheduler after
// boot, connect the two boards directly (board 1 central -> board 2),
// discover the peer UART TX characteristic, write a 12-byte payload at
// 10 Hz for 120 s while rendering, then terminate and report. Never set in
// product builds.
#ifndef CM_GAME_GATE
#define CM_GAME_GATE 0
#endif

// --- v2 product scope flags ---
// Phone GPS replaced the wearable shield; the heart quest (and its pulse
// sensor) was removed. Shields may remain stacked; firmware must not depend
// on them. Records report honest no-fix / no_contact when disabled.
#ifndef CM_GPS_ENABLED
#define CM_GPS_ENABLED 0
#endif
#ifndef CM_PULSE_ENABLED
#define CM_PULSE_ENABLED 0
#endif

// --- Pet (v2; rates from the bench-verified fork's docs/PET_SPEC.md) ---
#define CM_HUNGER_DECAY_MS 600000UL           // -1 hunger per 10 min
#define CM_HAPPY_DECAY_MS 900000UL            // -1 happiness per 15 min alone
#define CM_HAPPY_DECAY_TOGETHER_MS 2700000UL  // -1 per 45 min with partner here
#define CM_ENERGY_DECAY_MS 1800000UL          // -1 energy per 30 min awake
#define CM_PET_PERSIST_MS 300000UL            // persist needs every 5 min
#define CM_NAP_AFTER_MS 600000UL              // 10 min idle -> nap (decay halves)
#define CM_LONELY_MS 1800000UL                // 30 min alone -> lonely bubble
#define CM_FEED_AMOUNT 25                     // hunger restored per snack
#define CM_STROKE_AMOUNT 5                    // happiness per stroke
#define CM_AWARD_HAPPY_BONUS 10               // happiness on quest award

// --- Snack Catch mini-game (pet care; happiness only in v2) ---
#define CM_GAME_STEP_MS 100UL                 // ~10 Hz step
#define CM_GAME_ENERGY_COST 10
#define CM_GAME_MAX_MISSES 3
#define CM_GAME_HAPPY_PER_CATCH 3
#define CM_GAME_HAPPY_CAP 15
#define CM_AWARD_FLASH_MS 5000UL
#define CM_EVOLVE_FLASH_MS 4000UL
