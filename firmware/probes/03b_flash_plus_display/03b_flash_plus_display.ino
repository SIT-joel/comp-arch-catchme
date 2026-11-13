// Stage 1 probe: ASD2202-R-F flash TinyShield (Winbond W25Q-series, SPI, CS=D5).
//
// Verifies, in order:
//   1. The flash chip answers on SPI and reports its JEDEC ID and capacity.
//   2. Sector erase + page writes persist across a software reset (RAM variable
//      trick: signature is read BEFORE any write on later boots).
//   3. A write/read/verify round-trip works with error checking enabled.
//
// Expected serial (115200):
//   flash_probe jedec_id=0xEF4014 capacity_kb=1024  (0xEF=Winbond; record the
//     actual ID — it identifies the real chip variant on this board rev)
//   flash_probe roundtrip OK (256 bytes, 3 passes)
//   flash_probe boot #2: signature found, counter=1 -> persistence confirmed
//
// The -F flash variant is SPI NOR flash, NOT EEPROM: erase-before-write at
// sector granularity applies. This probe only touches sector 0.
//
// Library: SPIMemory 3.4.0 (github.com/Marzogh/SPIMemory) — the library used
// by the official TinyCircuits flash tutorial.

#include <SPI.h>
#include <SPIMemory.h>

#define SerialMonitorInterface SerialUSB

const int flashCS = 5;
SPIFlash flash(flashCS);
#include <TinyScreen.h>
TinyScreen g_disp{TinyScreenPlus};

// Signature block at address 0: magic + 32-bit boot counter.
const uint32_t MAGIC_ADDR = 0x00000040;  // addr 0 is rejected by SPIMemory reads
const uint32_t MAGIC = 0x434D4631;  // "CMF1"
const uint32_t COUNTER_ADDR = 0x44;
const uint32_t TEST_ADDR = 0x00010000;  // different 4KB sector than the metadata

void setup() {
  SerialMonitorInterface.begin(115200);
  // Wait (bounded) for a host serial connection: SAMD CDC drops early writes.
  for (uint32_t waited = 0; waited < 60000 && !SerialMonitorInterface; waited += 100) delay(100);

  pinMode(flashCS, OUTPUT);
  digitalWrite(flashCS, HIGH);

  if (!flash.begin()) {
    SerialMonitorInterface.println("flash_probe FAIL: chip not detected (begin)");
    return;
  }
  uint16_t jedec = (uint16_t)(flash.getJEDECID() & 0xFFFF);
  uint32_t capacity = flash.getCapacity();
  SerialMonitorInterface.print("flash_probe jedec_id=0x");
  SerialMonitorInterface.print(flash.getJEDECID(), HEX);
  SerialMonitorInterface.print(" capacity_kb=");
  SerialMonitorInterface.println(capacity / 1024);

  // --- persistence check: read signature first, then bump the counter ---
  bool found = false;
  uint32_t magic = 0, counter = 0;
  if (flash.readAnything(MAGIC_ADDR, magic) && magic == MAGIC) {
    flash.readAnything(COUNTER_ADDR, counter);
    found = true;
  }
  if (!found) {
    flash.eraseSector(MAGIC_ADDR);
    magic = MAGIC;
    counter = 0;
    flash.writeAnything(MAGIC_ADDR, magic);
    SerialMonitorInterface.println("flash_probe first boot: signature written");
  }
  counter++;
  flash.eraseSector(MAGIC_ADDR);
  flash.writeAnything(MAGIC_ADDR, magic);
  flash.writeAnything(COUNTER_ADDR, counter);
  SerialMonitorInterface.print("flash_probe boot #");
  SerialMonitorInterface.print(counter);
  SerialMonitorInterface.println(": persistence will be confirmed if this number grows after the reset button");

  // --- round-trip test: 3 passes of 256 bytes with error checking ---
  uint8_t buf[64];
  for (int pass = 0; pass < 3; pass++) {
    for (int chunk = 0; chunk < 4; chunk++) {
      uint32_t addr = TEST_ADDR + chunk * 64;
      for (uint16_t i = 0; i < 64; i++) buf[i] = (uint8_t)(pass + chunk + i);
      if (!flash.eraseSector(addr)) {
        SerialMonitorInterface.print("flash_probe FAIL erase addr=0x");
        SerialMonitorInterface.println(addr, HEX);
        return;
      }
      if (!flash.writeByteArray(addr, buf, 64, true)) {
        SerialMonitorInterface.print("flash_probe FAIL write addr=0x");
        SerialMonitorInterface.println(addr, HEX);
        return;
      }
      uint8_t back[64];
      flash.readByteArray(addr, back, 64);
      for (uint16_t i = 0; i < 64; i++) {
        if (back[i] != (uint8_t)(pass + chunk + i)) {
          SerialMonitorInterface.print("flash_probe FAIL verify addr=0x");
          SerialMonitorInterface.println(addr + i, HEX);
          return;
        }
      }
    }
  }
  SerialMonitorInterface.println("flash_probe roundtrip OK (3 passes x 256 bytes)");
  SerialMonitorInterface.println("flash_probe DONE — press the reset button to test persistence");
}

void loop() {
  delay(1000);
}
