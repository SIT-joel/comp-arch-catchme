// Hardware watchdog: auto-recovery from whole-board freezes.
//
// Two freezes (26 Oct 02:22 and ~22:00) left the board dead until a manual
// USB replug — suspected trigger is blocking SerialUSB writes when the host
// stops reading, plus residual radio/flash interrupt hazards. The watchdog
// converts any such stall into a clean reboot; the phone auto-reconnects
// each TDD cycle and re-syncs state (mode, anchors) within one window.
//
// SAMD21 WDT, 16 s period, clocked at 1.024 kHz from the internal 32 kHz
// RC oscillator on generic-clock generator 3 (generators 0/1 are used by
// the Arduino core). Validated on hardware with a no-feed test build
// before use (see docs/PROGRESS.md).

#pragma once

#include <Arduino.h>

#define CM_WDT_PERIOD_S 16

namespace wdt {
// Configure and enable the watchdog. Call once at the END of setup() (the
// 60 s serial-attach wait must not be watched).
void begin();

// Feed. Call from loop() every iteration; every long blocking operation
// must stay well under CM_WDT_PERIOD_S.
void feed();

// Freeze forensics: reset-reason string (watchdog recoveries report the
// previous life's last known uptime from no-init RAM).
const char* boot_reason();

// Call from loop() every few seconds: records the liveness marker.
void note_alive(uint32_t now_ms);

// Previous life's last known uptime in ms (0 when unknown). Real values
// require the .noinit linker fix (see crash_diag.h, docs/PROGRESS.md).
uint32_t previous_life_ms();
}  // namespace wdt
