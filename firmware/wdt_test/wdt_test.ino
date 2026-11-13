// Watchdog configuration validation (docs/PROGRESS.md freeze mitigation).
// Enables the same WDT setup as watchdog_app.cpp and NEVER feeds it:
// expected behavior is a reboot roughly every 16 s, visible as repeated
// boot banners on serial. If the banner repeats — config is proven.

#include <Arduino.h>

void wdtBegin() {
  // v3: source the WDT from the core's running XOSC32K generator (GCLK1)
  // via unused generator 4 (GCLK3 belongs to the core; internal OSC32K
  // never becomes ready on this board).
  while (GCLK->STATUS.bit.SYNCBUSY) {}
  GCLK->GENDIV.reg = GCLK_GENDIV_ID(4) | GCLK_GENDIV_DIV(32);
  while (GCLK->STATUS.bit.SYNCBUSY) {}
  GCLK->GENCTRL.reg = GCLK_GENCTRL_ID(4) |
                      GCLK_GENCTRL_SRC(GCLK_GENCTRL_SRC_GCLKGEN1_Val) |
                      GCLK_GENCTRL_GENEN;
  while (GCLK->STATUS.bit.SYNCBUSY) {}
  GCLK->CLKCTRL.reg = GCLK_CLKCTRL_ID(GCLK_CLKCTRL_ID_WDT_Val) |
                      GCLK_CLKCTRL_GEN_GCLK4 | GCLK_CLKCTRL_CLKEN;
  while (WDT->STATUS.bit.SYNCBUSY) {}
  WDT->CTRL.bit.ENABLE = 0;
  while (WDT->STATUS.bit.SYNCBUSY) {}
  WDT->CONFIG.bit.PER = 0xB;  // 16 s @ 1.024 kHz
  WDT->CTRL.bit.WEN = 0;
  while (WDT->STATUS.bit.SYNCBUSY) {}
  WDT->CTRL.bit.ENABLE = 1;
  while (WDT->STATUS.bit.SYNCBUSY) {}
  WDT->CLEAR.reg = WDT_CLEAR_CLEAR_KEY;
}

void setup() {
  SerialUSB.begin(115200);
  for (uint32_t waited = 0; waited < 20000 && !SerialUSB; waited += 100) delay(100);
  SerialUSB.print("WDT TEST v3 boot millis=");
  SerialUSB.println(millis());
  wdtBegin();
  SerialUSB.println("WDT TEST v3: watchdog on, never fed");
}

uint32_t lastPrint = 0;

void loop() {
  if (millis() - lastPrint >= 2000) {
    lastPrint = millis();
    SerialUSB.print("alive t=");
    SerialUSB.println(millis() / 1000);
  }
  delay(100);
  // deliberately NO feed
}
