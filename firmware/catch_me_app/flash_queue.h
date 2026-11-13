// Flash-backed queue of unsent telemetry records (ASD2202-R-F, SPIMemory).
//
// Layout from FLASH_QUEUE_BASE_ADDR:
//   [0..3]   magic 'CMQ1'
//   [4..7]   boot counter (u32 LE) — incremented once per boot; the boot id
//            string combines DEVICE_ID and this counter
//   [8..11]  head index (next record slot to write; u32 LE)
//   [12..15] acked index (all records before this are server-acknowledged; u32 LE)
//   [16..]   record slots, sizeof(TelemetryRecord) each
//
// Head/acked indices are written only after the record data they describe, so
// a power loss mid-write loses at most the newest record, never the queue.
// The ring is bounded by FLASH_QUEUE_MAX_RECORDS; when full, new records are
// REFUSED (queue-full surfaced to UI/STATUS), never silently dropped.

#pragma once

#include <Arduino.h>
#include "w25q.h"
#include "records.h"

class FlashQueue {
 public:
  bool begin();
  const char* boot_id() const { return boot_id_; }
  uint32_t boot_counter() const { return boot_counter_; }

  // Append one record. Returns false when the queue is full or write fails.
  bool push(const TelemetryRecord& rec);

  // Copy the oldest unacknowledged record at logical position
  // (acked + offset) into out. Returns false when none left.
  bool peek(uint16_t offset, TelemetryRecord* out);

  // Number of stored, unacknowledged records.
  uint16_t pending() const { return (uint16_t)(head_ - acked_); }
  bool full() const { return pending() >= FLASH_QUEUE_MAX_RECORDS; }

  // Advance the acknowledged watermark by n records (server-persisted).
  void acknowledge(uint16_t n);

  // Rebuild integrity after an unexpected write failure: drop tail record.
  void drop_newest();

 private:
  void write_header();
  void read_header();
  uint32_t slot_addr(uint32_t index) {
    return FLASH_QUEUE_BASE_ADDR + 16 + (index % FLASH_QUEUE_MAX_RECORDS) * sizeof(TelemetryRecord);
  }

  W25Q flash_;
  bool ok_ = false;
  uint32_t head_ = 0;
  uint32_t acked_ = 0;
  uint32_t boot_counter_ = 0;
  char boot_id_[16] = {0};
};

extern FlashQueue g_queue;
