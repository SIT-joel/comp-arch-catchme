// Stage 0 probe: verify TinyScreen+ programming, display, buttons, and USB serial.
// Expected behavior:
//   - Display shows CATCH-ME, uptime seconds, and a live button bitmask line.
//   - SerialUSB prints one "screen_hello uptime_s=N buttons=0xX" line per second.
//   - Buttons: bit0=up? (see silk); any press must change the BTN value on screen and serial.
// Library: TinyScreen 1.1.0 (Arduino Library Manager, TinyCircuits).
#include <Wire.h>
#include <SPI.h>
#include <TinyScreen.h>

TinyScreen display0 = TinyScreen(TinyScreenPlus);

uint32_t started = 0;
uint32_t lastPrinted = (uint32_t)-1;

void setup() {
  SerialUSB.begin(115200);
  display0.begin();
  display0.setBrightness(8);
  display0.setFont(liberationSans_12ptFontInfo);
  started = millis();
}

void loop() {
  uint32_t up = (millis() - started) / 1000;
  uint8_t buttons = display0.getButtons();

  display0.clearScreen();
  display0.setCursor(0, 8);
  display0.fontColor(TS_8b_White, TS_8b_Black);
  display0.print("CATCH-ME");
  display0.setCursor(0, 24);
  display0.print("UP ");
  display0.print(up);
  display0.print('s');
  display0.setCursor(0, 40);
  display0.print("BTN 0x");
  display0.print(buttons, HEX);

  if (up != lastPrinted) {
    lastPrinted = up;
    SerialUSB.print("screen_hello uptime_s=");
    SerialUSB.print(up);
    SerialUSB.print(" buttons=0x");
    SerialUSB.println(buttons, HEX);
  }
  delay(100);
}
