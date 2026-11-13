#include "flash_queue.h"

#include <SPI.h>

FlashQueue g_queue;

static const uint32_t QUEUE_MAGIC = 0x314D4D43;  // "CMM1"

bool FlashQueue::begin() {
  SerialUSB.println("fq: flash.begin");
  if (!flash_.begin(FLASH_CS)) { SerialUSB.println("fq: begin FAIL"); return false; }
  SerialUSB.print("fq: jedec 0x");
  SerialUSB.println(flash_.jedec_id(), HEX);

  uint8_t raw[4];
  if (!flash_.read(FLASH_QUEUE_BASE_ADDR, raw, 4)) { SerialUSB.println("fq: read FAIL"); return false; }
  uint32_t magic = raw[0] | ((uint32_t)raw[1] << 8) | ((uint32_t)raw[2] << 16) | ((uint32_t)raw[3] << 24);
  if (magic != QUEUE_MAGIC) {
    // First run (or corrupted header): reinitialize the queue area.
    SerialUSB.println("fq: erase 4 sectors");
    for (uint8_t s = 0; s < 4; s++) {
      if (!flash_.erase_sector(FLASH_QUEUE_BASE_ADDR + 0x1000UL * s)) {
        SerialUSB.println("fq: erase FAIL");
        return false;
      }
    }
    SerialUSB.println("fq: write header");
    boot_counter_ = 1;
    head_ = 0;
    acked_ = 0;
    write_header();
    SerialUSB.println("fq: header written");
  } else {
    read_header();
    boot_counter_ += 1;
    write_header();  // new boot id; queue contents remain valid
    SerialUSB.println("fq: header rewritten for new boot");
  }
  snprintf(boot_id_, sizeof(boot_id_), "d%d-%lu", DEVICE_ID, (unsigned long)boot_counter_);
  ok_ = true;
  return true;
}

void FlashQueue::read_header() {
  uint8_t buf[12];
  flash_.read(FLASH_QUEUE_BASE_ADDR + 4, buf, 12);
  boot_counter_ = (uint32_t)buf[0] | ((uint32_t)buf[1] << 8) | ((uint32_t)buf[2] << 16) | ((uint32_t)buf[3] << 24);
  head_ = (uint32_t)buf[4] | ((uint32_t)buf[5] << 8) | ((uint32_t)buf[6] << 16) | ((uint32_t)buf[7] << 24);
  acked_ = (uint32_t)buf[8] | ((uint32_t)buf[9] << 8) | ((uint32_t)buf[10] << 16) | ((uint32_t)buf[11] << 24);
  if (acked_ > head_) acked_ = head_;  // integrity guard
}

void FlashQueue::write_header() {
  uint8_t buf[16];
  uint32_t vals[4] = {QUEUE_MAGIC, boot_counter_, head_, acked_};
  for (uint8_t f = 0; f < 4; f++) {
    buf[f * 4] = vals[f] & 0xFF;
    buf[f * 4 + 1] = (vals[f] >> 8) & 0xFF;
    buf[f * 4 + 2] = (vals[f] >> 16) & 0xFF;
    buf[f * 4 + 3] = (vals[f] >> 24) & 0xFF;
  }
  flash_.erase_sector(FLASH_QUEUE_BASE_ADDR);
  flash_.write(FLASH_QUEUE_BASE_ADDR, buf, 16);
}

bool FlashQueue::push(const TelemetryRecord& rec) {
  if (!ok_ || full()) return false;
  uint32_t addr = slot_addr(head_);
  // Erase the sector when we wrap to its first slot (records are 32 B; each
  // 4 KB sector holds 128 slots).
  if (head_ % 128 == 0) {
    if (!flash_.erase_sector(addr & ~(uint32_t)0xFFF)) return false;
  }
  if (!flash_.write(addr, (const uint8_t*)&rec, sizeof(rec))) {
    return false;
  }
  head_ += 1;
  // Persist head AFTER the record data (crash-ordered write).
  write_header();
  return true;
}

bool FlashQueue::peek(uint16_t offset, TelemetryRecord* out) {
  if (!ok_ || offset >= pending()) return false;
  uint32_t index = acked_ + offset;
  return flash_.read(slot_addr(index), (uint8_t*)out, sizeof(TelemetryRecord));
}

void FlashQueue::acknowledge(uint16_t n) {
  if (!ok_ || n == 0) return;
  uint32_t target = acked_ + n;
  if (target > head_) target = head_;
  // Acked slots become reusable: erased lazily when the write wraps around.
  acked_ = target;
  write_header();
}

void FlashQueue::drop_newest() {
  if (!ok_ || head_ > acked_) {
    head_ -= 1;
    write_header();
  }
}
