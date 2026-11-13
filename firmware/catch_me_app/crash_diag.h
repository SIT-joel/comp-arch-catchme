// Crash forensics: a breadcrumb ring in no-init RAM that survives watchdog
// resets, converting a silent 16 s stall into an exact operation trace.
//
// Why this needed the linker script fix (14 Nov): the sam_ba bootloader runs
// on every reset and zeroes its own .bss range 0x20000068..0x20001bbc, which
// previously swallowed orphan-placed .noinit vars ("previous life 0 ms" on
// every watchdog boot). The tinyscreen_p linker script now pins .noinit at
// 0x20001C00 (NOLOAD). Reproducing a build therefore requires that local
// linker script edit — see docs/PROGRESS.md.
//
// Writes are plain RAM stores (a few hundred ns) — safe to sprinkle into the
// HCI library and hot app paths without perturbing radio timing.

#pragma once

#include <stdint.h>

namespace cdiag {

// One ring entry: delta-ms to the PREVIOUS breadcrumb plus the event.
struct Entry {
  uint32_t dt;
  uint8_t id;
  uint8_t a;
  uint16_t b;
};

// Record a breadcrumb. Safe from any context that can read RAM (no serial,
// no locks); not ISR-reentrancy-guarded, but each caller site is either
// main-loop or single-ISR exclusive, and worst case is one torn entry.
void bc(uint8_t id, uint8_t a, uint16_t b);

// Call once from setup() after the serial attach wait: after a watchdog
// reset, prints the previous life's breadcrumb tail (oldest to newest),
// the last known uptime, and the HCI corruption counters. Invalidates the
// ring afterwards so clean boots don't re-dump stale traces.
void boot_dump();

// Breadcrumb ids (hex, kept distinctive for log reading).
enum : uint8_t {
  B_TICK = 0x01,       // a = phase code (0 LINKED / 1 SCAN / 2 ADV)
  B_STAT = 0x02,       // STAT line written
  B_SCAN = 0x10,       // enter_scanning
  B_ADV = 0x11,        // enter_advertising
  B_PHONE_UP = 0x12,   // a = role, b = conn handle
  B_DISC = 0x13,       // a = handle lo, b = reason
  B_REQ = 0x20,        // hci_send_req entry,    b = opcode
  B_REQ_OK = 0x21,     // hci_send_req answered, b = opcode
  B_REQ_FAIL = 0x22,   // hci_send_req timeout,  b = opcode
  B_PROC = 0x30,       // HCI_Process with events pending, a = rxq depth
  B_ISR_CAP = 0x31,    // HCI_Isr drain cap tripped, a = reads done
  B_FREELIST = 0x32,   // free_event_list, a = pool size, b = rxq size
  B_SEND = 0x40,       // send_message, a = msg type, b = payload len
  B_MSG = 0x41,        // received message, a = msg type, b = payload len
  B_RECORD = 0x50,     // telemetry record built
  B_QFULL = 0x51,      // internal queue full (backups dropped)
  B_REINIT = 0x60,     // module_reinit (phantom link / stuck module)
  B_WRETRY = 0x70,     // Hal_Write_Serial retry, a = ret, b = bytes left
};

}  // namespace cdiag

// C-facing hook for the STBLE library (hci.c compiles as C).
extern "C" void cdiag_bc(uint8_t id, uint8_t a, uint16_t b);
