// Bounded telemetry record. Fixed layout so the phone can decode it into the
// server JSON contract (docs/INTERFACES.md) without any string handling here.

#pragma once

#include <Arduino.h>
#include "config.h"

// Heart-rate status values (mirror server contract).
#define HR_STATUS_VALID 0
#define HR_STATUS_WARMING_UP 1
#define HR_STATUS_NO_CONTACT 2
#define HR_STATUS_INVALID_SIGNAL 3

// Record flags (bit positions).
#define RF_GPS_VALID 0
#define RF_HR_VALID 1
#define RF_PEER_OBSERVED 2

#pragma pack(push, 1)
struct TelemetryRecord {
  uint32_t uptime_ms;
  uint32_t captured_epoch;   // unix seconds; 0 = unsynced (phone anchors later)
  uint16_t clock_uncertainty;  // ms; 0xFFFF = unknown
  uint8_t flags;              // RF_* bits
  uint8_t bpm;                // 0 when invalid
  uint8_t hr_status;          // HR_STATUS_*
  int32_t lat_e6;             // degrees * 1e6; 0x7FFFFFFF = n/a
  int32_t lon_e6;
  uint16_t gps_fix_age_ms;    // 0xFFFF = n/a
  uint8_t peer_device;        // observed peer DEVICE_ID; 0 = none
  uint16_t peer_heartbeat;    // peer's advertised counter
  uint16_t peer_obs_age_ms;   // age of that observation at capture time
  uint16_t peer_token_hash;   // advertised token hash
  uint8_t reserved[2];        // pad to 32 bytes; future use
};                            // 32 bytes
#pragma pack(pop)

static_assert(sizeof(TelemetryRecord) == 32, "record layout must stay fixed");

// Boot identity: "d<DEVICE_ID>-<counter from flash>" is produced by FlashQueue;
// kept as a plain char buffer because it lives in records and log lines.
extern char g_boot_id[16];

extern uint32_t g_record_sequence;  // monotonic within this boot
