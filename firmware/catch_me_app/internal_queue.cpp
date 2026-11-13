#include "internal_queue.h"
#include "config.h"

// NVM register procedure mirrors the core's own Reset.cpp erase (proven on
// this silicon). ADDR is a 16-bit word address → byte address >> 1. Erase
// stalls the core ~2.5 ms per row (well under the 16 s watchdog window);
// feed the watchdog before batch operations.

#define NVM_MEMORY ((volatile uint16_t*)0x000000)
bool InternalQueue::nvm_ready() { return NVMCTRL->INTFLAG.bit.READY; }

void InternalQueue::nvm_erase_row(uint32_t addr) {
  while (!nvm_ready()) {}
  NVMCTRL->STATUS.reg |= NVMCTRL_STATUS_MASK;
  NVMCTRL->ADDR.reg = addr >> 1;
  NVMCTRL->CTRLA.reg = NVMCTRL_CTRLA_CMD_ER | NVMCTRL_CTRLA_CMDEX_KEY;
  while (!nvm_ready()) {}
}

void InternalQueue::nvm_write_page(uint32_t addr, const uint32_t* data) {  // 64 bytes
  while (!nvm_ready()) {}
  NVMCTRL->STATUS.reg |= NVMCTRL_STATUS_MASK;
  NVMCTRL->ADDR.reg = addr >> 1;
  NVMCTRL->CTRLA.reg = NVMCTRL_CTRLA_CMD_PBC | NVMCTRL_CTRLA_CMDEX_KEY;
  while (!nvm_ready()) {}
  uint32_t* dst = (uint32_t*)addr;
  for (uint8_t i = 0; i < 16; i++) dst[i] = data[i];
  NVMCTRL->CTRLA.reg = NVMCTRL_CTRLA_CMD_WP | NVMCTRL_CTRLA_CMDEX_KEY;
  while (!nvm_ready()) {}
}


bool InternalQueue::begin() {
  const uint32_t meta = CM_IQ_FLASH_ADDR;
  const uint32_t* meta_w = (const uint32_t*)meta;
  uint32_t counter = 1;
  if (meta_w[0] == CM_IQ_MAGIC) {
    counter = meta_w[1] + 1;  // new boot identity
    nvm_erase_row(meta);
  } else {
    nvm_erase_row(meta);
  }
  uint32_t page[16] = {CM_IQ_MAGIC, counter};
  nvm_write_page(meta, page);
  snprintf(boot_id_, sizeof(boot_id_), "d%d-i%lu", DEVICE_ID,
           (unsigned long)counter);

  // Scan for the first erased slot (append position).
  head_ = 0;
  const TelemetryRecord* recs = (const TelemetryRecord*)(CM_IQ_FLASH_ADDR + 256);
  while (head_ < (uint32_t)(CM_IQ_ROWS * CM_IQ_PER_ROW) &&
         recs[head_].uptime_ms != 0xFFFFFFFFul) {
    head_++;
  }
  // Acknowledgements are RAM-only: everything stored counts as pending
  // after a boot; the server dedupes by (boot_id, sequence).
  pending_ = head_;
  full_ = head_ >= (uint32_t)(CM_IQ_ROWS * CM_IQ_PER_ROW);
  ok_ = true;
  return true;
}

bool InternalQueue::push(const TelemetryRecord& rec) {
  if (full_ || !ok_) return false;
  if (head_ > 0 && head_ % CM_IQ_PER_ROW == 0) {
    nvm_erase_row(slot_addr(head_));  // fresh row for the next 8 records
  }
  uint32_t addr = slot_addr(head_);
  const uint32_t* src = (const uint32_t*)&rec;
  // Records share 64-byte pages: rebuild the full page (existing half +
  // new slot) because the page buffer is cleared before writing.
  uint32_t page_addr = addr & ~0x3Ful;
  uint32_t page[16];
  const uint32_t* existing = (const uint32_t*)page_addr;
  for (uint8_t i = 0; i < 16; i++) page[i] = existing[i];
  uint8_t off = (addr - page_addr) / 4;
  for (uint8_t i = 0; i < 8; i++) page[off + i] = src[i];
  nvm_write_page(page_addr, page);

  head_++;
  pending_++;
  if (head_ >= (uint32_t)(CM_IQ_ROWS * CM_IQ_PER_ROW)) full_ = true;
  return true;
}

bool InternalQueue::peek(uint16_t offset, TelemetryRecord* out) const {
  if (offset >= pending_) return false;
  uint32_t slot = base_ + offset;
  if (slot >= head_) return false;
  memcpy(out, (const void*)slot_addr(slot), sizeof(TelemetryRecord));
  return out->uptime_ms != 0xFFFFFFFFul;
}

void InternalQueue::acknowledge(uint16_t n) {
  if (n > pending_) n = pending_;
  base_ += n;
  pending_ -= n;
}
