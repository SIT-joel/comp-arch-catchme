// Minimal Winbond W25Q SPI NOR driver for the telemetry queue.
//
// Replaces SPIMemory, whose begin() hung inside the full app build on this
// board (hangs in chip detection only when the complete library set is
// linked; standalone probes always worked). The chip itself is proven: the
// flash probe read JEDEC 0xEF4014 and passed roundtrip + persistence tests
// with plain SPI commands, which is all this driver uses.
//
// Commands (W25Q datasheet): 0x9F JEDEC ID, 0x05 read status (WIP bit 0),
// 0x06 write enable, 0x20 erase 4KB sector, 0x02 page program (<=256 B,
// never crossing a page), 0x03 read data.

#pragma once

#include <Arduino.h>
#include <SPI.h>

class W25Q {
 public:
  bool begin(uint8_t cs_pin);
  uint32_t jedec_id() const { return jedec_; }

  bool erase_sector(uint32_t addr);                 // 4 KB
  bool read(uint32_t addr, uint8_t* out, uint16_t n);
  bool write_page(uint32_t addr, const uint8_t* in, uint16_t n);  // <=256 B, page-aligned start
  bool write(uint32_t addr, const uint8_t* in, uint16_t n);       // handles page crossings

 private:
  void cmd(uint8_t c);
  bool wait_ready(uint32_t timeout_ms);
  uint8_t cs_ = 5;
  uint32_t jedec_ = 0;
};
