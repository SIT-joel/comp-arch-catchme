#include "w25q.h"

static const SPISettings W25Q_SPI(12000000, MSBFIRST, SPI_MODE0);

// The BlueNRG IRQ pin handler (STBLE HCI_Isr) performs full SPI reads in
// interrupt context on this same hardware SPI bus. If it fires while the
// W25Q's CS is low, the flash receives phantom clock edges / commands (seen
// on hardware as corrupted queue headers) and a corrupted IRQ read can spin
// the ISR forever (whole-board freeze). Every W25Q transaction therefore runs
// with interrupts disabled: frames are microseconds long (worst case a 256 B
// page program ~0.3 ms at 12 MHz), the BLE event pump polls via HCI_Process
// anyway, and the GPS tolerates an occasionally dropped 9600-baud character.
#define W25Q_BUS_XFER(body)     \
  noInterrupts();               \
  SPI.beginTransaction(W25Q_SPI); \
  body;                         \
  SPI.endTransaction();         \
  interrupts();

bool W25Q::begin(uint8_t cs_pin) {
  cs_ = cs_pin;
  pinMode(cs_, OUTPUT);
  digitalWrite(cs_, HIGH);
  SPI.begin();

  W25Q_BUS_XFER({
    digitalWrite(cs_, LOW);
    SPI.transfer(0x9F);  // JEDEC ID
    jedec_ = ((uint32_t)SPI.transfer(0) << 16) | ((uint32_t)SPI.transfer(0) << 8) | SPI.transfer(0);
    digitalWrite(cs_, HIGH);
  });

  // Require a sane manufacturer byte (0x00/0xFF means no chip on the bus).
  uint8_t man = (jedec_ >> 16) & 0xFF;
  return man != 0x00 && man != 0xFF;
}

bool W25Q::wait_ready(uint32_t timeout_ms) {
  uint32_t start = millis();
  do {
    uint8_t s;
    W25Q_BUS_XFER({
      digitalWrite(cs_, LOW);
      SPI.transfer(0x05);  // read status register 1
      s = SPI.transfer(0);
      digitalWrite(cs_, HIGH);
    });
    if (!(s & 0x01)) return true;  // WIP clear
  } while (millis() - start < timeout_ms);
  return false;
}

void W25Q::cmd(uint8_t c) {
  W25Q_BUS_XFER({
    digitalWrite(cs_, LOW);
    SPI.transfer(c);
    digitalWrite(cs_, HIGH);
  });
}

bool W25Q::erase_sector(uint32_t addr) {
  if (!wait_ready(200)) return false;
  cmd(0x06);  // write enable (separate CS frame)
  W25Q_BUS_XFER({
    digitalWrite(cs_, LOW);
    SPI.transfer(0x20);  // 4KB sector erase
    SPI.transfer((addr >> 16) & 0xFF);
    SPI.transfer((addr >> 8) & 0xFF);
    SPI.transfer(addr & 0xFF);
    digitalWrite(cs_, HIGH);
  });
  return wait_ready(500);
}

bool W25Q::read(uint32_t addr, uint8_t* out, uint16_t n) {
  if (!wait_ready(200)) return false;
  W25Q_BUS_XFER({
    digitalWrite(cs_, LOW);
    SPI.transfer(0x03);
    SPI.transfer((addr >> 16) & 0xFF);
    SPI.transfer((addr >> 8) & 0xFF);
    SPI.transfer(addr & 0xFF);
    for (uint16_t i = 0; i < n; i++) out[i] = SPI.transfer(0);
    digitalWrite(cs_, HIGH);
  });
  return true;
}

bool W25Q::write_page(uint32_t addr, const uint8_t* in, uint16_t n) {
  if (n == 0 || n > 256) return false;
  if (!wait_ready(200)) return false;
  cmd(0x06);  // write enable
  W25Q_BUS_XFER({
    digitalWrite(cs_, LOW);
    SPI.transfer(0x02);
    SPI.transfer((addr >> 16) & 0xFF);
    SPI.transfer((addr >> 8) & 0xFF);
    SPI.transfer(addr & 0xFF);
    for (uint16_t i = 0; i < n; i++) SPI.transfer(in[i]);
    digitalWrite(cs_, HIGH);
  });
  return wait_ready(50);
}

bool W25Q::write(uint32_t addr, const uint8_t* in, uint16_t n) {
  while (n > 0) {
    uint32_t page_off = addr & 0xFF;
    uint16_t chunk = (uint16_t)(256 - page_off);
    if (chunk > n) chunk = n;
    if (!write_page(addr, in, chunk)) return false;
    addr += chunk;
    in += chunk;
    n -= chunk;
  }
  return true;
}
