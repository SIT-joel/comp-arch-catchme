// Internal-flash record queue for boards without the W25Q flash shield.
//
// The SAMD21's own program flash (256 KB) has ~220 KB free beyond this
// sketch; the top 8 KB are reserved as an append-only record store so a
// radio-only wearable stops losing telemetry built while its TDD link is
// disconnected (the root cause of its sparse evidence, 30 Oct).
//
// Layout at CM_IQ_FLASH_ADDR: row 0 = metadata (magic + boot counter),
// rows 1..CM_IQ_ROWS = 8 x 32-byte records each. Append-only; full is
// reported like the external queue. Wear: one row erased per 8 records
// (~10K cycle endurance → weeks of continuous 1 Hz bench use; fine).

#pragma once

#include <Arduino.h>
#include "records.h"

#define CM_IQ_FLASH_ADDR 0x0003E000UL
#define CM_IQ_META_ROW 0
#define CM_IQ_ROWS 31
#define CM_IQ_PER_ROW 8
#define CM_IQ_MAGIC 0x17C7F00Dul

class InternalQueue {
 public:
  bool begin();                       // init metadata, scan head
  const char* boot_id() const { return boot_id_; }
  bool push(const TelemetryRecord& rec);
  uint16_t pending() const { return pending_; }
  bool full() const { return full_; }
  bool peek(uint16_t offset, TelemetryRecord* out) const;
  void acknowledge(uint16_t n);

 private:
  static bool nvm_ready();
  static void nvm_erase_row(uint32_t addr);
  static void nvm_write_page(uint32_t addr, const uint32_t* data);
  uint32_t slot_addr(uint32_t slot) const {
    return CM_IQ_FLASH_ADDR + (1 + slot / CM_IQ_PER_ROW) * 256 +
           (slot % CM_IQ_PER_ROW) * 32;
  }

  char boot_id_[16] = {0};
  uint32_t head_ = 0;      // next slot to write
  uint32_t base_ = 0;      // oldest unacknowledged slot
  uint16_t pending_ = 0;
  bool full_ = false;
  bool ok_ = false;
};
