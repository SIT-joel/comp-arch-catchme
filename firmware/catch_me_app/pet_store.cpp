#include "pet_store.h"

#include "ble_app.h"  // fnv16

#define SerialLog SerialUSB

// Slot addresses (see pet_store.h for the flash-map justification).
#define CM_PS_W25Q_SLOT_A 0x00020000UL
#define CM_PS_W25Q_SLOT_B (CM_PS_W25Q_SLOT_A + 0x1000UL)
// Internal: two 256 B rows at 0x3D000/0x3D100 — clear of the telemetry
// queue region (0x3E000+) and far above the sketch image.
#define CM_PS_INT_SLOT_A 0x0003D000UL
#define CM_PS_INT_SLOT_B 0x0003D100UL

PetStore g_pet;

// ---- record packing ---------------------------------------------------------

static void pack_record(uint8_t* out /*>= CM_PS_HEADER + 32*/, const PetState& st,
                        uint32_t counter) {
  memset(out, 0, CM_PS_HEADER + sizeof(PetState));
  out[0] = CM_PS_MAGIC & 0xFF;
  out[1] = (CM_PS_MAGIC >> 8) & 0xFF;
  out[2] = CM_PS_VERSION;
  out[3] = 0;
  memcpy(out + 4, &counter, 4);
  uint16_t crc = fnv16((const uint8_t*)&st, sizeof(PetState));
  memcpy(out + 8, &crc, 2);
  memcpy(out + CM_PS_HEADER, &st, sizeof(PetState));
}

static bool unpack_record(const uint8_t* in, uint16_t len, uint32_t* counter_out,
                          PetState* out) {
  if (len < CM_PS_HEADER + sizeof(PetState)) return false;
  const uint16_t magic = in[0] | ((uint16_t)in[1] << 8);
  if (magic != CM_PS_MAGIC || in[2] != CM_PS_VERSION) return false;
  uint32_t counter;
  memcpy(&counter, in + 4, 4);
  uint16_t crc;
  memcpy(&crc, in + 8, 2);
  const uint16_t expect = fnv16(in + CM_PS_HEADER, sizeof(PetState));
  if (crc != expect) return false;
  memcpy(out, in + CM_PS_HEADER, sizeof(PetState));
  *counter_out = counter;
  return true;
}

// ---- internal NVM primitives (mirrors internal_queue.cpp; proven on this
// silicon: ADDR is a 16-bit word address, erase stalls the core ~2.5 ms) ----

#define NVM_MEMORY ((volatile uint16_t*)0x000000)
static bool nvm_ready() { return NVMCTRL->INTFLAG.bit.READY; }

static void nvm_erase_row(uint32_t addr) {
  while (!nvm_ready()) {}
  NVMCTRL->STATUS.reg |= NVMCTRL_STATUS_MASK;
  NVMCTRL->ADDR.reg = addr >> 1;
  NVMCTRL->CTRLA.reg = NVMCTRL_CTRLA_CMD_ER | NVMCTRL_CTRLA_CMDEX_KEY;
  while (!nvm_ready()) {}
}

static void nvm_write_page(uint32_t addr, const uint32_t* data) {  // 64 bytes
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

// ---- PetStore ---------------------------------------------------------------

bool PetStore::begin() {
  uint32_t counters[2] = {0, 0};
  PetState candidates[2];
  bool valid[2] = {false, false};

  if (w25q_.begin(FLASH_CS)) {
    backend_ = BACKEND_W25Q;
    valid[0] = load_external_slot(CM_PS_W25Q_SLOT_A, &counters[0], &candidates[0]);
    valid[1] = load_external_slot(CM_PS_W25Q_SLOT_B, &counters[1], &candidates[1]);
  } else {
    // v2 hardware finding: internal-flash writes stall the CPU mid-SPI and
    // wedge the BLE module (verified on both boards). Without a W25Q the
    // pet lives in RAM only — cosmetic state resets each boot (honest);
    // XP/level stay server-owned and are unaffected.
    backend_ = BACKEND_NONE;
    SerialLog.println("pet_store: no W25Q - RAM-only (pet resets on reboot; "
                      "XP stays server-owned)");
  }

  bool loaded = false;
  for (uint8_t k = 0; k < 2; k++) {
    if (valid[k] && (!loaded || counters[k] > write_counter_)) {
      st_ = candidates[k];
      write_counter_ = counters[k];
      loaded = true;
    }
  }
  if (!loaded) {
    // Fresh device (or both slots damaged): DEFAULT pet, bonded and named —
    // the user asked for demo-ready defaults so a reflash never requires
    // re-entering species/name (13 Nov). The name/species stay server-
    // mirrored afterwards (MSG_PET_STATE / pet PUT override cosmetic
    // identity); care_last_ymd stays 0 so the first care press grants XP.
#if DEVICE_ID == 1
    const uint8_t def_species = 0;          // spark
    const char* def_name = "Sweep";
#else
    const uint8_t def_species = 1;          // fluff
    const char* def_name = "Pixel";
#endif
    memset(&st_, 0, sizeof(st_));
    st_.species = def_species;
    strncpy(st_.name, def_name, sizeof(st_.name) - 1);
    st_.name[sizeof(st_.name) - 1] = 0;
    st_.hunger = 80;
    st_.happiness = 80;
    st_.energy = 80;
    st_.server_stage = 0;
    write_counter_ = 0;
  }
  SerialLog.print("pet_store: backend=");
  SerialLog.print(backend_name());
  SerialLog.print(" counter=");
  SerialLog.print(write_counter_);
  SerialLog.print(" loaded=");
  SerialLog.println(loaded ? 1 : 0);
  return backend_ != BACKEND_NONE;
}

bool PetStore::load_external_slot(uint32_t addr, uint32_t* counter_out,
                                  PetState* out) {
  uint8_t buf[CM_PS_HEADER + sizeof(PetState)];
  if (!w25q_.read(addr, buf, sizeof(buf))) return false;
  return unpack_record(buf, sizeof(buf), counter_out, out);
}

bool PetStore::load_internal_slot(uint32_t addr, uint32_t* counter_out,
                                  PetState* out) {
  const uint8_t* flash = (const uint8_t*)addr;
  return unpack_record(flash, CM_PS_HEADER + sizeof(PetState), counter_out, out);
}

bool PetStore::commit() {
  if (backend_ != BACKEND_W25Q) {
    // RAM-only backend: nothing to write (internal flash is off-limits).
    return false;
  }
  const bool ok = commit_external();
  if (ok) {
    write_counter_++;
  } else {
    SerialLog.println("pet_store: COMMIT FAILED (state kept in RAM)");
  }
  return ok;
}

bool PetStore::commit_external() {
  const uint32_t target = ((write_counter_ + 1) & 1) ? CM_PS_W25Q_SLOT_A
                                                     : CM_PS_W25Q_SLOT_B;
  if (!w25q_.erase_sector(target)) return false;
  uint8_t buf[CM_PS_HEADER + sizeof(PetState)];
  pack_record(buf, st_, write_counter_ + 1);
  return w25q_.write(target, buf, sizeof(buf));
}

bool PetStore::commit_internal() {
  // Each slot owns one 256 B row; the 42-byte record fits a single 64 B page.
  const uint32_t target = ((write_counter_ + 1) & 1) ? CM_PS_INT_SLOT_A : CM_PS_INT_SLOT_B;
  uint8_t buf[64];
  memset(buf, 0, sizeof(buf));
  pack_record(buf, st_, write_counter_ + 1);
  nvm_erase_row(target);
  uint32_t page[16];
  memcpy(page, buf, sizeof(buf));
  nvm_write_page(target, page);
  return true;
}
