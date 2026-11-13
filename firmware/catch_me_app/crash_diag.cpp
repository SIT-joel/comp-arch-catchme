#include "crash_diag.h"

#include <Arduino.h>
#include <string.h>

#include "watchdog_app.h"

// Same SerialUSB convention as the rest of the app files.
#define SerialLog SerialUSB

// PM->RCAUSE (reset cause) comes with <Arduino.h>, same as watchdog_app.cpp.

#define CD_MAGIC 0xCA7CB0A5ul
#define CD_COUNT 128
#define CD_TAIL 48  // entries dumped on a watchdog boot

__attribute__((section(".noinit"))) static uint32_t cd_magic;
__attribute__((section(".noinit"))) static uint32_t cd_stamp;
__attribute__((section(".noinit"))) static uint16_t cd_widx;
__attribute__((section(".noinit"))) static cdiag::Entry cd_ring[CD_COUNT];

namespace cdiag {

static void init_if_needed() {
  if (cd_magic == CD_MAGIC) return;
  cd_magic = CD_MAGIC;
  cd_stamp = millis();
  cd_widx = 0;
  memset(cd_ring, 0, sizeof(cd_ring));
}

void bc(uint8_t id, uint8_t a, uint16_t b) {
  init_if_needed();
  uint32_t now = millis();
  Entry* e = &cd_ring[cd_widx];
  e->dt = now - cd_stamp;
  e->id = id;
  e->a = a;
  e->b = b;
  cd_stamp = now;
  cd_widx = (uint16_t)((cd_widx + 1) % CD_COUNT);
}

void boot_dump() {
  const uint32_t r = PM->RCAUSE.reg;
  if (!(r & PM_RCAUSE_WDT)) return;  // only meaningful after a watchdog reset
  if (cd_magic != CD_MAGIC) {
    SerialLog.println("BCR: ring invalid (cold boot or pre-fix firmware)");
    return;
  }
  const uint32_t life = wdt::previous_life_ms();  SerialLog.print("BCR: watchdog at ~");
  SerialLog.print(life);
  SerialLog.println(" ms; last breadcrumbs (oldest -> newest):");
  uint16_t n = CD_TAIL;
  if (n > CD_COUNT) n = CD_COUNT;
  uint16_t idx = (uint16_t)((cd_widx + CD_COUNT - n) % CD_COUNT);
  for (uint16_t k = 0; k < n; ++k) {
    const Entry& e = cd_ring[idx];
    if (e.id != 0) {
      SerialLog.print("BCR -");
      SerialLog.print((long)(n - k));
      SerialLog.print(" id=0x");
      SerialLog.print(e.id, HEX);
      SerialLog.print(" a=0x");
      SerialLog.print(e.a, HEX);
      SerialLog.print(" b=0x");
      SerialLog.print(e.b, HEX);
      SerialLog.print(" dt=");
      SerialLog.println((unsigned long)e.dt);
    }
    idx = (uint16_t)((idx + 1) % CD_COUNT);
  }
  SerialLog.println("BCR tail done");
  cd_magic = 0;  // invalidate: don't re-dump on the next clean boot
}

}  // namespace cdiag

extern "C" void cdiag_bc(uint8_t id, uint8_t a, uint16_t b) {
  cdiag::bc(id, a, b);
}
