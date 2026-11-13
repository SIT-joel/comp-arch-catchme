// Pet core: needs decay, moods, care actions, bonding, server sync.
// Ported from the bench-verified pet fork; v2 adaptations:
//  - NO local economy: XP/level/points are server-owned. Feeding is free
//    (refused only when the pet is full); Snack Catch pays happiness only.
//  - Care actions emit MSG_PET_CARE_EVENT (date + nonce) via the pending
//    event mechanism; the phone claims the server's once-daily +10 XP and
//    ACKs with the shared MSG_INTERACTION_ACK nonce reply.
//  - The server pushes XP/level/stage via MSG_PET_STATE; the wearable
//    mirrors them (evolution flash on stage change) and marks the shown
//    level stale between syncs.

#pragma once

#include <Arduino.h>
#include "pet_store.h"

enum PetMood : uint8_t {
  PET_MOOD_HAPPY = 0,
  PET_MOOD_NEUTRAL,
  PET_MOOD_SAD,
  PET_MOOD_SICK,
  PET_MOOD_TIRED,
  PET_MOOD_SLEEPING,
};

// Pet events popped by the consumer (UI animations).
enum PetEvent : uint8_t { PEV_NONE = 0, PEV_EVOLVE };

// Species indices (0..2) chosen at bonding.
enum Species : uint8_t { SPECIES_SPARK = 0, SPECIES_FLUFF = 1, SPECIES_PIP = 2 };

class PetCore {
 public:
  void begin();
  void tick();  // 10 ms cadence

  uint8_t mood() const { return mood_; }
  bool bonded() const { return g_pet.state().species != 0xFF; }
  PetStage stage() const { return (PetStage)g_pet.state().server_stage; }
  const char* name() const { return g_pet.state().name; }
  // The displayed level comes from the server; stale until the next sync.
  uint8_t server_level() const { return server_level_; }
  bool server_synced() const { return server_synced_; }

  uint8_t anim_frame() const { return anim_; }  // toggles ~2 Hz
  bool hearts_visible() const;                  // stroke afterglow / partner here
  bool lonely() const;                          // alone too long

  // --- Bonding flow (PET screen drives; species then name) ---
  bool bonding_species_active() const { return !bonded() && !naming_; }
  bool naming_active() const { return naming_; }
  uint8_t bond_species() const { return bond_species_; }
  void bond_cycle_species();     // lower-right
  void bond_commit_species();    // upper-right confirm
  uint8_t naming_len() const { return name_len_; }
  const char* naming_buffer() const { return name_buf_; }
  uint8_t naming_cursor() const { return name_cursor_; }  // letter alphabet index
  void naming_next_letter();     // upper-right
  void naming_prev_letter();     // upper-left
  void naming_commit_char();     // lower-right
  void naming_backspace();       // lower-left (on empty name: finish)
  static char naming_letter_at(uint8_t idx);

  // --- Care (PET screen lower buttons) ---
  void wipe_for_rebond();        // bench: factory-reset to the bonding flow
  bool feed();                   // refused only when the pet is full
  const char* feed_refusal() const { return feed_refusal_; }
  void pet_stroke();             // hearts burst
  bool can_play() const;         // false while sick (the pet refuses)
  void note_activity();          // any button press resets the nap timer

  // --- Snack Catch mini-game (~10 Hz via wants_fast_render) ---
  bool game_active() const { return game_active_; }
  const char* game_start();      // NULL = started; else refusal message
  void game_move(int8_t dir);    // -1 left / +1 right (button edge)
  void game_quit();
  uint8_t game_caught() const { return game_caught_; }
  uint8_t game_missed() const { return game_missed_; }
  int8_t game_basket_x() const { return game_basket_x_; }
  uint8_t game_snacks(int8_t* sx, int8_t* sy, uint8_t max) const;
  bool award_flash() const { return millis() < award_flash_until_ms_; }
  bool evolve_flash() const { return millis() < evolve_flash_until_ms_; }

  uint8_t pop_event();           // PEV_NONE when nothing pending

  // --- v2 server/care plumbing ---
  // Called by the message router with the MSG_PET_STATE payload mirror.
  void note_server_pet(uint32_t xp, uint8_t level, uint8_t stage,
                       bool cared_today, const char* name);
  // Called by the sketch when the server relays a completion (celebration).
  void celebrate();
  // Anchor date for care events (YYYYMMDD); 0 = time not synced yet.
  void note_date_ymd(uint32_t ymd) { date_ymd_ = ymd; }
  // Pending care event for the UI retransmit loop (false = nothing pending).
  bool care_event_pending(uint32_t* ymd_out, uint64_t* nonce_out) const;
  void care_event_acked(uint64_t nonce);  // called on matching ACK

 private:
  void apply_decay(uint32_t dt_ms);
  void persist_soon() { persist_at_ms_ = 0; }  // commit on next tick
  void queue_care_event();                     // once per care day
  uint8_t compute_mood() const;
  void check_evolution();
  void game_step(uint32_t now);
  void game_finish();

  // Snack Catch state.
  bool game_active_ = false;
  uint8_t game_caught_ = 0;
  uint8_t game_missed_ = 0;
  int8_t game_basket_x_ = 42;
  uint32_t game_last_step_ms_ = 0;
  uint32_t game_next_spawn_ms_ = 0;
  int8_t snack_x_[3] = {-1, -1, -1};
  int8_t snack_y_[3] = {0, 0, 0};
  uint32_t award_flash_until_ms_ = 0;
  uint32_t evolve_flash_until_ms_ = 0;

  uint8_t mood_ = PET_MOOD_NEUTRAL;
  uint8_t anim_ = 0;
  uint32_t last_anim_ms_ = 0;
  uint32_t last_decay_ms_ = 0;
  uint32_t persist_at_ms_ = 0;
  uint32_t last_activity_ms_ = 0;
  uint32_t alone_since_ms_ = 0;  // while partner NOT right-here
  uint32_t stroke_until_ms_ = 0; // hearts afterglow
  uint8_t ev_evolve_pending_ = 0;
  PetStage last_stage_ = PET_BABY;

  // Care event outbox (one per care day; retried until the phone ACKs).
  bool care_pending_ = false;
  uint32_t care_ymd_ = 0;
  uint64_t care_nonce_ = 0;
  uint32_t care_last_send_ms_ = 0;

  // Server mirror.
  uint8_t server_level_ = 0;
  bool server_synced_ = false;

  // Date from the time anchor (YYYYMMDD; 0 = unsynced).
  uint32_t date_ymd_ = 0;

  // Bonding state.
  bool naming_ = false;
  uint8_t bond_species_ = SPECIES_SPARK;
  uint8_t name_cursor_ = 0;      // alphabet index of the current letter
  uint8_t name_len_ = 0;
  char name_buf_[9] = {0};
  const char* feed_refusal_ = "";
};

extern PetCore g_petcore;
