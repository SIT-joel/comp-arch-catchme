#include "pet_core.h"

#include "ble_app.h"
#include "config.h"

#define SerialLog SerialUSB

PetCore g_petcore;

// Alphabet for the name editor: A-Z, space, then '>' = DONE (binds the
// name). Without an explicit finish symbol there is no way to keep a typed
// name (backspace only deletes) — found while designing the bench harness.
static const char kAlphabet[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZ >";

// Local xorshift for snack spawn columns (game variety only, not security).
static uint32_t s_pet_prng = 1;
static uint32_t pet_prng_next() {
  s_pet_prng ^= s_pet_prng << 13;
  s_pet_prng ^= s_pet_prng >> 17;
  s_pet_prng ^= s_pet_prng << 5;
  return s_pet_prng;
}

// Seed helper: same SAMD serial words the framing uses, different mix.
static uint32_t samd_serial_hint_xorshift() {
  const uint32_t v = *(const uint32_t*)0x0080A00C ^ *(const uint32_t*)0x0080A040 ^
                     *(const uint32_t*)0x0080A044 ^ *(const uint32_t*)0x0080A048;
  uint32_t x = v ^ micros();
  x ^= x << 13;
  x ^= x >> 17;
  x ^= x << 5;
  return x;
}

void PetCore::begin() {
  s_pet_prng = samd_serial_hint_xorshift();
  if (s_pet_prng == 0) s_pet_prng = 0x9E3779B9;
  PetState& st = g_pet.state();
  last_stage_ = (PetStage)st.server_stage;
  server_level_ = (uint8_t)(1 + st.server_xp / 100);
  server_synced_ = st.server_xp != 0;
  mood_ = compute_mood();
  last_decay_ms_ = millis();
  persist_at_ms_ = millis() + CM_PET_PERSIST_MS;
  last_activity_ms_ = millis();
  alone_since_ms_ = millis();
  SerialLog.print("pet_core: species=");
  SerialLog.print(st.species == 0xFF ? -1 : (int)st.species);
  SerialLog.print(" name=");
  SerialLog.print(st.name[0] ? st.name : "(unnamed)");
  SerialLog.print(" stage=");
  SerialLog.println((uint8_t)last_stage_);
}

uint8_t PetCore::compute_mood() const {
  const PetState& st = g_pet.state();
  if (millis() - last_activity_ms_ >= CM_NAP_AFTER_MS && bonded()) return PET_MOOD_SLEEPING;
  if (st.hunger < 25 || st.happiness < 15) return PET_MOOD_SICK;
  if (st.happiness < 40) return PET_MOOD_SAD;
  if (st.energy < 20) return PET_MOOD_TIRED;
  if (st.hunger >= 70 && st.happiness >= 70) return PET_MOOD_HAPPY;
  return PET_MOOD_NEUTRAL;
}

void PetCore::apply_decay(uint32_t dt_ms) {
  PetState& st = g_pet.state();
  const bool napping = mood_ == PET_MOOD_SLEEPING;
  const bool together = g_ble.rssi_bucket() == BleApp::RSSI_HERE;
  // Fractional accumulators in ms; integer step when a full period passes.
  static uint32_t acc_hunger = 0, acc_happy = 0, acc_energy = 0;

  acc_hunger += dt_ms;
  acc_happy += dt_ms;
  acc_energy += dt_ms;

  if (acc_hunger >= CM_HUNGER_DECAY_MS) {
    acc_hunger -= CM_HUNGER_DECAY_MS;
    if (st.hunger > 0) st.hunger--;
  }
  const uint32_t happy_period = (together && !napping) ? CM_HAPPY_DECAY_TOGETHER_MS
                                                       : CM_HAPPY_DECAY_MS;
  // Napping halves the emotional decay by doubling the effective period.
  const uint32_t happy_eff = napping ? happy_period * 2 : happy_period;
  if (acc_happy >= happy_eff) {
    acc_happy -= happy_eff;
    if (st.happiness > 0) st.happiness--;
  }
  if (acc_energy >= CM_ENERGY_DECAY_MS) {
    acc_energy -= CM_ENERGY_DECAY_MS;
    if (st.energy > 0) st.energy--;
  }
}

void PetCore::tick() {
  const uint32_t now = millis();
  if (now - last_anim_ms_ >= 500) {
    last_anim_ms_ = now;
    anim_ ^= 1;
  }

  if (game_active_) {
    game_step(now);
  }

  apply_decay(now - last_decay_ms_);
  last_decay_ms_ = now;

  // Track "alone" for the lonely bubble and together-decay switching.
  if (g_ble.rssi_bucket() == BleApp::RSSI_HERE) {
    alone_since_ms_ = now;
  }

  const uint8_t new_mood = compute_mood();
  if (new_mood != mood_) {
    mood_ = new_mood;
    // Waking from a nap is an activity reset (any render interaction too).
    if (mood_ != PET_MOOD_SLEEPING) last_activity_ms_ = now;
  }

  check_evolution();

  // Periodic persistence; persist_soon() forces it on the next tick.
  if (persist_at_ms_ == 0) {
    persist_at_ms_ = now + CM_PET_PERSIST_MS;
    g_pet.commit();
  } else if (now >= persist_at_ms_) {
    persist_at_ms_ = now + CM_PET_PERSIST_MS;
    g_pet.commit();
  }

  // Retransmit an unacknowledged care event like interaction commands.
  if (care_pending_ && g_ble.phoneConnected() &&
      now - care_last_send_ms_ >= 1500) {
    // Wire format (matches AppModel.handlePetCareEvent):
    //   [0] ver, [1] kind, [2..11] date ASCII 'YYYY-MM-DD', [12..19] nonce LE64.
    uint8_t wire[20];
    memset(wire, 0, sizeof(wire));
    wire[0] = 1;
    wire[1] = 1;
    // YYYYMMDD -> 'YYYY-MM-DD'
    uint32_t v = care_ymd_;
    uint32_t y = v / 10000, m = (v / 100) % 100, d = v % 100;
    wire[2] = '0' + (y / 1000) % 10;
    wire[3] = '0' + (y / 100) % 10;
    wire[4] = '0' + (y / 10) % 10;
    wire[5] = '0' + y % 10;
    wire[6] = '-';
    wire[7] = '0' + (m / 10) % 10;
    wire[8] = '0' + m % 10;
    wire[9] = '-';
    wire[10] = '0' + (d / 10) % 10;
    wire[11] = '0' + d % 10;
    memcpy(wire + 12, &care_nonce_, 8);
    if (g_ble.send_message(MSG_PET_CARE_EVENT, wire, 20)) {
      care_last_send_ms_ = now;
    }
  }

  if (pop_event() == PEV_EVOLVE) {
    evolve_flash_until_ms_ = now + CM_EVOLVE_FLASH_MS;
  }
}

void PetCore::check_evolution() {
  const PetStage s = (PetStage)g_pet.state().server_stage;
  if (s != last_stage_) {
    last_stage_ = s;
    ev_evolve_pending_ = 1;
    persist_soon();
    SerialLog.print("pet_core: evolved to stage ");
    SerialLog.println((uint8_t)s);
  }
}

uint8_t PetCore::pop_event() {
  if (ev_evolve_pending_) {
    ev_evolve_pending_ = 0;
    return PEV_EVOLVE;
  }
  return PEV_NONE;
}

bool PetCore::hearts_visible() const {
  return millis() < stroke_until_ms_ || g_ble.rssi_bucket() == BleApp::RSSI_HERE;
}

bool PetCore::lonely() const {
  return bonded() && (millis() - alone_since_ms_ >= CM_LONELY_MS) &&
         g_pet.state().happiness < 40;
}

// --- Server sync (v2) ---

void PetCore::note_server_pet(uint32_t xp, uint8_t level, uint8_t stage,
                              bool cared_today, const char* name) {
  PetState& st = g_pet.state();
  st.server_xp = xp;
  st.server_stage = stage;
  server_level_ = level;
  server_synced_ = true;
  if (name[0] && strncmp(st.name, name, sizeof(st.name)) != 0) {
    // The server mirror is authoritative for the display name once set.
    strncpy(st.name, name, sizeof(st.name) - 1);
    st.name[sizeof(st.name) - 1] = 0;
    persist_soon();
  }
  (void)cared_today;  // the server cap is absolute; the wearable shows sync
  SerialLog.print("pet_core: server sync xp=");
  SerialLog.print(xp);
  SerialLog.print(" level=");
  SerialLog.println(level);
}

void PetCore::celebrate() {
  PetState& st = g_pet.state();
  st.happiness = (uint8_t)min(100, (int)st.happiness + CM_AWARD_HAPPY_BONUS);
  award_flash_until_ms_ = millis() + CM_AWARD_FLASH_MS;
  persist_soon();
  SerialLog.println("pet_core: celebrates the award");
}

// --- Care events (v2) ---

void PetCore::queue_care_event() {
  if (date_ymd_ == 0) {
    // Time not synced: care still improves the mood locally; the daily XP
    // claim happens once the anchor arrives (honest, no fabricated date).
    SerialLog.println("pet_core: care event deferred (no time anchor)");
    return;
  }
  if (care_pending_) return;                       // one in flight
  if (g_pet.state().care_last_ymd == date_ymd_) return;  // already claimed today
  care_pending_ = true;
  care_ymd_ = date_ymd_;
  care_nonce_ = ((uint64_t)millis() << 20) ^ (s_pet_prng *= 6364136223846793005ULL);
  care_last_send_ms_ = 0;
}

bool PetCore::care_event_pending(uint32_t* ymd_out, uint64_t* nonce_out) const {
  if (!care_pending_) return false;
  *ymd_out = care_ymd_;
  *nonce_out = care_nonce_;
  return true;
}

void PetCore::care_event_acked(uint64_t nonce) {
  if (!care_pending_ || care_nonce_ != nonce) return;  // stale ACK
  care_pending_ = false;
  PetState& st = g_pet.state();
  st.care_last_ymd = care_ymd_;
  persist_soon();
  SerialLog.print("pet_core: care event ACKed for ");
  SerialLog.println(care_ymd_);
}

// --- Bonding ---

void PetCore::bond_cycle_species() {
  bond_species_ = (bond_species_ + 1) % 3;
}

void PetCore::bond_commit_species() {
  naming_ = true;
  name_len_ = 0;
  name_cursor_ = 0;
  memset(name_buf_, 0, sizeof(name_buf_));
}

char PetCore::naming_letter_at(uint8_t idx) {
  return kAlphabet[idx % (sizeof(kAlphabet) - 1)];
}

void PetCore::naming_next_letter() { name_cursor_ = (name_cursor_ + 1) % (sizeof(kAlphabet) - 1); }
void PetCore::naming_prev_letter() {
  name_cursor_ = (name_cursor_ + (sizeof(kAlphabet) - 1) - 1) % (sizeof(kAlphabet) - 1);
}

void PetCore::naming_commit_char() {
  // '>' is the DONE symbol: bind species + current buffer and persist.
  if (naming_letter_at(name_cursor_) == '>') {
    PetState& st = g_pet.state();
    st.species = bond_species_;
    memset(st.name, 0, sizeof(st.name));
    strncpy(st.name, name_buf_, sizeof(st.name) - 1);
    st.hunger = 80;
    st.happiness = 80;
    st.energy = 80;
    naming_ = false;
    last_activity_ms_ = millis();
    alone_since_ms_ = millis();
    g_pet.commit();
    SerialLog.print("pet_core: bonded species=");
    SerialLog.print((int)st.species);
    SerialLog.print(" name=");
    SerialLog.println(st.name);
    return;
  }
  if (name_len_ >= 8) return;
  name_buf_[name_len_++] = naming_letter_at(name_cursor_);
  name_buf_[name_len_] = 0;
}

void PetCore::naming_backspace() {
  // Delete-only; binding happens via the '>' DONE symbol (commit_char).
  if (name_len_ > 0) {
    name_len_--;
    name_buf_[name_len_] = 0;
  }
}

// --- Care ---

void PetCore::wipe_for_rebond() {
  // Bench/demo reset: factory state (unbonded -> species chooser on next
  // render) with care flags cleared so the daily +10 can be showcased
  // immediately. Cosmetic identity only; server-owned XP is separate.
  PetState& st = g_pet.state();
  memset(&st, 0, sizeof(st));
  st.species = 0xFF;
  st.server_stage = (uint8_t)PET_BABY;
  care_pending_ = false;
  care_ymd_ = 0;
  care_last_send_ms_ = 0;
  server_level_ = 0;
  server_synced_ = false;
  naming_ = false;
  name_len_ = 0;
  name_buf_[0] = 0;
  game_active_ = false;
  last_stage_ = PET_BABY;
  persist_soon();
  SerialLog.println("pet_core: wiped for rebond (care guard cleared)");
}

bool PetCore::feed() {
  PetState& st = g_pet.state();
  if (st.hunger > 90) {
    feed_refusal_ = "not hungry";
    return false;
  }
  // v2: feeding is free (the fork's local snack economy is gone; the
  // server owns the currency and the daily-care XP cap).
  st.hunger = (uint8_t)min(100, (int)st.hunger + CM_FEED_AMOUNT);
  st.happiness = (uint8_t)min(100, (int)st.happiness + 2);
  feed_refusal_ = "";
  queue_care_event();
  persist_soon();
  SerialLog.println("pet_core: fed");
  return true;
}

void PetCore::pet_stroke() {
  PetState& st = g_pet.state();
  st.happiness = (uint8_t)min(100, (int)st.happiness + CM_STROKE_AMOUNT);
  stroke_until_ms_ = millis() + 2000;
  queue_care_event();
  persist_soon();
}

bool PetCore::can_play() const { return mood_ != PET_MOOD_SICK; }

// ---- Snack Catch ----

const char* PetCore::game_start() {
  if (game_active_) return NULL;
  if (!can_play()) return "too sick";
  PetState& st = g_pet.state();
  if (st.energy < CM_GAME_ENERGY_COST) return "too tired";
  st.energy -= CM_GAME_ENERGY_COST;
  game_active_ = true;
  game_caught_ = 0;
  game_missed_ = 0;
  game_basket_x_ = 42;
  for (uint8_t k = 0; k < 3; k++) {
    snack_x_[k] = -1;
    snack_y_[k] = 0;
  }
  game_last_step_ms_ = millis();
  game_next_spawn_ms_ = millis() + 400;
  persist_soon();
  note_activity();
  SerialLog.println("pet_core: snack catch round started");
  return NULL;
}

void PetCore::game_move(int8_t dir) {
  if (!game_active_) return;
  game_basket_x_ += dir * 6;
  if (game_basket_x_ < 2) game_basket_x_ = 2;
  if (game_basket_x_ > 86) game_basket_x_ = 86;
  note_activity();
}

void PetCore::game_quit() { game_finish(); }

uint8_t PetCore::game_snacks(int8_t* sx, int8_t* sy, uint8_t max) const {
  uint8_t n = 0;
  for (uint8_t k = 0; k < 3 && n < max; k++) {
    if (snack_x_[k] >= 0) {
      sx[n] = snack_x_[k];
      sy[n] = snack_y_[k];
      n++;
    }
  }
  return n;
}

void PetCore::game_step(uint32_t now) {
  if (now - game_last_step_ms_ < CM_GAME_STEP_MS) return;
  game_last_step_ms_ = now;

  // Spawning: keep up to 2 snacks falling.
  uint8_t falling = 0;
  for (uint8_t k = 0; k < 3; k++) {
    if (snack_x_[k] >= 0) falling++;
  }
  if (falling < 2 && now >= game_next_spawn_ms_) {
    for (uint8_t k = 0; k < 3; k++) {
      if (snack_x_[k] < 0) {
        snack_x_[k] = 4 + (int8_t)(pet_prng_next() % 84);
        snack_y_[k] = 0;
        break;
      }
    }
    game_next_spawn_ms_ = now + 900 - (uint32_t)min(500, (int)game_caught_ * 40);
  }

  // Falling + catch/miss. Basket: 12 px wide at y=52..55.
  const int bx0 = game_basket_x_ - 6;
  const int bx1 = game_basket_x_ + 6;
  for (uint8_t k = 0; k < 3; k++) {
    if (snack_x_[k] < 0) continue;
    snack_y_[k] += 1 + game_caught_ / 6;  // gentle difficulty ramp
    if (snack_y_[k] >= 48 && snack_y_[k] <= 55 && snack_x_[k] >= bx0 &&
        snack_x_[k] <= bx1) {
      snack_x_[k] = -1;
      game_caught_++;
    } else if (snack_y_[k] > 62) {
      snack_x_[k] = -1;
      game_missed_++;
    }
  }

  if (game_missed_ >= CM_GAME_MAX_MISSES) game_finish();
}

void PetCore::game_finish() {
  game_active_ = false;
  PetState& st = g_pet.state();
  // Happiness only (v2: no local currency — the server owns the economy).
  const int happy = min((int)game_caught_ * CM_GAME_HAPPY_PER_CATCH, (int)CM_GAME_HAPPY_CAP);
  st.happiness = (uint8_t)min(100, (int)st.happiness + happy);
  persist_soon();
  SerialLog.print("pet_core: snack catch finished caught=");
  SerialLog.print(game_caught_);
  SerialLog.print(" happy=");
  SerialLog.println(happy);
}

void PetCore::note_activity() { last_activity_ms_ = millis(); }
