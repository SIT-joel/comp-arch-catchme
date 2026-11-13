#include "watchdog_app.h"

// Freeze forensics: no-init RAM survives watchdog/system resets (verified:
// .noinit is placed by the tinyscreen_p linker script, far from the stack).
// The board records its last known uptime every few seconds; on any boot
// the reset reason + previous life are printed, converting a mystery freeze
// into hard evidence (watchdog stall vs power cycle).
__attribute__((__section__(".noinit"))) static uint32_t noinit_magic;
__attribute__((__section__(".noinit"))) static uint32_t noinit_last_ms;
#define NOINIT_MAGIC 0xCA7F00Dul

namespace wdt {

void begin() {
  // Clock derivation, per the core's startup.c reality on this board:
  // - GCLK1 = XOSC32K (32.768 kHz crystal) — configured and running as the
  //   DFLL48M reference; do not touch it, source from it.
  // - GCLK3 = OSC8M/8 (1 MHz) — OWNED BY THE CORE; reconfiguring it broke
  //   it (v1: dead source, inert watchdog).
  // - Internal OSC32K never reports ready on this board (v2 hung in its
  //   enable loop).
  // So: unused generator 4, source GCLKGEN1, GENDIV 32 -> 1.024 kHz WDT.
  while (GCLK->STATUS.bit.SYNCBUSY) {}
  GCLK->GENDIV.reg = GCLK_GENDIV_ID(4) | GCLK_GENDIV_DIV(32);
  while (GCLK->STATUS.bit.SYNCBUSY) {}
  GCLK->GENCTRL.reg = GCLK_GENCTRL_ID(4) |
                      GCLK_GENCTRL_SRC(GCLK_GENCTRL_SRC_GCLKGEN1_Val) |
                      GCLK_GENCTRL_GENEN;
  while (GCLK->STATUS.bit.SYNCBUSY) {}
  GCLK->CLKCTRL.reg = GCLK_CLKCTRL_ID(GCLK_CLKCTRL_ID_WDT_Val) |
                      GCLK_CLKCTRL_GEN_GCLK4 | GCLK_CLKCTRL_CLKEN;

  // WDT: disable before reconfiguring; PER 0xB = 16 s @ 1.024 kHz.
  while (WDT->STATUS.bit.SYNCBUSY) {}
  WDT->CTRL.bit.ENABLE = 0;
  while (WDT->STATUS.bit.SYNCBUSY) {}
  WDT->CONFIG.bit.PER = 0xB;
  WDT->CTRL.bit.WEN = 0;   // no closed window
  WDT->CTRL.bit.ALWAYSON = 0;
  while (WDT->STATUS.bit.SYNCBUSY) {}
  WDT->CTRL.bit.ENABLE = 1;
  while (WDT->STATUS.bit.SYNCBUSY) {}
  feed();
}

void feed() {
  WDT->CLEAR.reg = WDT_CLEAR_CLEAR_KEY;  // 0xA5
}

const char* boot_reason() {
  static char reason[48];
  const uint32_t r = PM->RCAUSE.reg;
  if (r & PM_RCAUSE_WDT) {
    snprintf(reason, sizeof(reason), "WATCHDOG (previous life %lu ms)",
             noinit_magic == NOINIT_MAGIC ? (unsigned long)noinit_last_ms : 0ul);
  } else if (r & PM_RCAUSE_POR) {
    snprintf(reason, sizeof(reason), "power-on");
  } else if (r & PM_RCAUSE_EXT) {
    snprintf(reason, sizeof(reason), "external reset (combo/bootloader)");
  } else if (r & PM_RCAUSE_SYST) {
    snprintf(reason, sizeof(reason), "system request");
  } else {
    snprintf(reason, sizeof(reason), "other (RCAUSE=0x%02lx)", (unsigned long)r);
  }
  return reason;
}

void note_alive(uint32_t now_ms) {
  noinit_magic = NOINIT_MAGIC;
  noinit_last_ms = now_ms;
}

}  // namespace wdt
