// Persistent pet cosmetic state, power-loss safe, on BOTH board shapes.
// Ported from the bench-verified pet fork (D:\catch_me_pet, 5 Nov) and
// adapted for the v2 product split:
//   - XP/level/points are SERVER-owned (User.lifetime_xp) and arrive via
//     MSG_PET_STATE; the wearable only MIRRORS them and never pays out.
//   - Care dates/streak live here (the server re-derives its own cap).
//
// Double-slot commit (identical to the fork): each commit erases + programs
// the slot indicated by (write_counter+1)&1 with the bumped counter. On boot
// the highest VALID (magic + version + CRC) counter wins; a commit lost to
// power loss falls back to the previous slot — one commit stale, never corrupt.
//
// Flash map (verified against this sketch's other users):
//   board 1 (W25Q shield): telemetry queue occupies 0x10000..0x1FA00
//     (2000 x 32 B records), pet slots at 0x20000/0x21000 are clear.
//   board 2 (no W25Q): internal telemetry queue owns 0x3E000..0x3FFFF
//     (CM_IQ_FLASH_ADDR, 31 rows + metadata). The pet store uses the two
//     256 B rows at 0x3D000/0x3D100 — the last row before the queue region,
//     far above the ~50 KB sketch (app region ends at 0x3E000).

#pragma once

#include <Arduino.h>
#include "config.h"
#include "w25q.h"

// Pet growth stage, mirrored from the server (pet_stage_for_xp): the
// wearable never derives stages from local XP in v2.
enum PetStage : uint8_t { PET_BABY = 0, PET_TEEN = 1, PET_ADULT = 2 };

struct PetState {
  uint8_t species;        // 0..2 chosen at bonding; 0xFF = not bonded yet
  char name[9];           // 8 chars + NUL; "" = unnamed
  uint8_t hunger;         // 0..100 (100 = full)
  uint8_t happiness;      // 0..100
  uint8_t energy;         // 0..100
  uint8_t flags;          // reserved
  uint32_t care_last_ymd; // YYYYMMDD of the last synced care day (0 = none)
  uint8_t care_streak;    // consecutive care days (mirror)
  uint32_t server_xp;     // mirror of User.lifetime_xp from MSG_PET_STATE
  uint8_t server_stage;   // mirror of the server evolution stage
  uint8_t reserved0;
  uint16_t reserved1;
};
static_assert(sizeof(PetState) == 32, "PetState must stay 32 bytes (fits one 64 B page)");

class PetStore {
 public:
  bool begin();          // probe backend, load latest valid state
  bool commit();         // persist current state; false on backend failure
  PetState& state() { return st_; }
  const PetState& state() const { return st_; }

  const char* backend_name() const {
    return backend_ == BACKEND_W25Q ? "w25q"
         : backend_ == BACKEND_NONE ? "ram" : "internal";
  }
  uint32_t write_counter() const { return write_counter_; }

 private:
  enum Backend : uint8_t { BACKEND_NONE = 0, BACKEND_W25Q, BACKEND_INTERNAL };
  bool load_external_slot(uint32_t addr, uint32_t* counter_out, PetState* out);
  bool load_internal_slot(uint32_t addr, uint32_t* counter_out, PetState* out);
  bool commit_external();
  bool commit_internal();

  W25Q w25q_;
  Backend backend_ = BACKEND_NONE;
  PetState st_{};
  uint32_t write_counter_ = 0;
};

extern PetStore g_pet;

// Record layout shared by both backends (header + PetState = 42 B, one page):
//   [0..1] magic LE (CM_PS_MAGIC)
//   [2]    version (CM_PS_VERSION)
//   [3]    reserved
//   [4..7] write_counter LE
//   [8..9] crc16 LE = fnv16 over the 32 payload bytes
//   [10..] PetState
#define CM_PS_MAGIC 0xA50B  // v2 layout (0xA50A was the fork's economy layout)
#define CM_PS_VERSION 2
#define CM_PS_HEADER 10
