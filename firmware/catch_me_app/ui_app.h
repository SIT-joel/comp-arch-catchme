// TinyScreen+ UI (v2 product shape): the wearable's three jobs are the pet,
// proximity, and the raid — one screen each, navigated with the two upper
// side buttons (upper-left = previous, upper-right = next):
//   PET  (home) — tamagotchi view: sprite, mood, needs, level (server-synced)
//   CARE        — feed / stroke / Snack Catch + care-sync status
//   NEAR        — Bluetooth proximity: partner, live peer evidence, matches
//   RAID        — the co-op fight (auto-taken-over when a raid starts)
// Sessions, quests, pairing, and history live on the phone app. The only
// non-navigable view is the together-quest PIN entry (auto-takeover): it is
// the quest's wearable-native mutual-presence evidence, so it stays.
// Honest states everywhere: invalid readings show their reason, unknown
// distances show "?" rather than a fabricated number.

#pragma once

#include <Arduino.h>
#include <TinyScreen.h>

#include "ble_app.h"
#include "game_app.h"
#include "gps_app.h"
#include "pet_core.h"
#include "pet_store.h"
#include "pulse_app.h"

class UiApp {
 public:
  void begin();
  void tick();   // poll buttons; call every loop iteration (~10 ms)
  void render(); // redraws the current screen; call ~1 Hz
  void apply_interaction_ack(const uint8_t* payload, uint16_t len);
  // Bench trigger (serial "QANS <choice>"): sends the A-D press for the
  // current question exactly as a button press would. Returns whether the
  // message went out (false: quiz inactive, already sent, or link down).
  bool bench_quiz_answer(uint8_t choice) {
    if (!quiz_active_ || quiz_sent_) return false;
    uint8_t ans[3] = {1, quiz_idx_, choice};
    if (g_ble.send_message(MSG_QUIZ_ANSWER, ans, sizeof(ans))) {
      quiz_sent_ = true;
      quiz_last_choice_ = choice;
      quiz_pending_ = true;  // retransmit until the phone's next state relay
      quiz_pending_choice_ = choice;
      quiz_last_send_ms_ = millis();
      return true;
    }
    return false;
  }

  // Bench trigger (serial "PIN 1234"): submits the four-digit PIN exactly as
  // the physical pad would (digits + the final lower-right press). Only
  // accepted while the interaction is in a PIN-entry phase (1 start / 3 end).
  bool bench_pin_entry(const char* digits) {
    const InteractionStateMsg& it = g_ble.interaction();
    if (it.phase != 1 && it.phase != 3) return false;
    for (uint8_t k = 0; k < 4; ++k) {
      if (digits[k] < '0' || digits[k] > '9') return false;
      pin_digits_[k] = (uint8_t)(digits[k] - '0');
    }
    pin_digit_ = 3;
    pin_edit_ = true;
    send_interaction_command(1, it.stage, it.partner_code_version, digits);
    return true;
  }
  // Phone-relayed quiz progress: active=0 leaves quiz mode. An idx CHANGE
  // (or quiz end) acknowledges the pending answer. Quiz completion
  // (active 1->0 with a quiz under way) fires the reward banner: the
  // lecturer must SEE the XP impact on the wearable itself.
  void note_quiz_state(uint8_t active, uint8_t idx, uint8_t total) {
    const bool was_active = quiz_active_;
    const uint8_t prev_idx = quiz_idx_;
    if (quiz_active_ && quiz_pending_ && (!active || idx != quiz_idx_)) {
      quiz_pending_ = false;  // the server accepted our answer
    }
    if (quiz_active_ && !active && quiz_total_ > 0) {
      flash_reward("QUIZ DONE!");
    }
    quiz_active_ = active != 0;
    quiz_idx_ = idx;
    quiz_total_ = total;
    if (!quiz_active_ || !was_active || idx != prev_idx) {
      quiz_sent_ = false;  // only reset the pad on new question or quiz start/end
    }
  }

  // Dedicated Quest Complete screen (15 s, or dismiss earlier via any button):
  // title, the exactly-once +100 pts / +100 XP award, and server level.
  void flash_reward(const char* title) {
    strncpy(reward_title_, title, sizeof(reward_title_) - 1);
    reward_title_[sizeof(reward_title_) - 1] = 0;
    reward_until_ms_ = millis() + 15000UL;
    reward_level_at_ = g_petcore.server_level();
    screen_ = SCR_PET;
    SerialUSB.print("ui: reward banner: ");
    SerialUSB.println(reward_title_);
  }

  // 10 ms tick: retransmit the pending answer until acknowledged.
  void tick_quiz() {
    if (!quiz_active_ || !quiz_pending_) return;
    if (!g_ble.phoneReady()) {
      quiz_last_send_ms_ = 0;
      return;
    }
    const uint32_t now = millis();
    if (quiz_last_send_ms_ == 0 || now - quiz_last_send_ms_ >= 2000) {
      uint8_t ans[3] = {1, quiz_idx_, quiz_pending_choice_};
      if (g_ble.send_message(MSG_QUIZ_ANSWER, ans, sizeof(ans))) {
        quiz_last_send_ms_ = now;
        quiz_sent_ = true;
        quiz_last_choice_ = quiz_pending_choice_;
      }
    }
  }

 private:
  // The four cycled screens (UR/UL navigation). SCR_INTERACTION sits AFTER
  // SCREEN_COUNT: it is only entered by the interaction-phase takeover and
  // never by the cycle.
  enum Screen : uint8_t { SCR_PET = 0, SCR_CARE, SCR_DISC, SCR_GPS, SCREEN_COUNT, SCR_INTERACTION = SCREEN_COUNT, SCR_QUIZ };
  // (SCR_GAME removed 14 Nov: the raid quest was cut — the board-to-board
  // sustained link drops at 23-30 s, a hardware wall documented across every
  // configuration since 12 Nov. The quest set is together, explore, quiz.)
  void render_pet();
  void render_care();
  void render_disc();
  void render_gps();
  // (render_raid removed 14 Nov with the raid quest.)
  void render_game();
  void render_interaction();
  void render_quiz();
  void send_interaction_command(uint8_t kind, uint8_t stage, uint16_t code_version,
                                const char* value = nullptr);

  TinyScreen display_{TinyScreenPlus};
  Screen screen_ = SCR_PET;
  uint8_t last_buttons_ = 0;
  uint8_t last_phase_ = 0;
  bool pin_edit_ = false;
  uint8_t pin_digits_[4] = {0, 0, 0, 0};
  uint8_t pin_digit_ = 0;
  uint8_t command_counter_ = 0;
  uint8_t pending_command_[40] = {0};
  uint8_t pending_command_len_ = 0;
  uint64_t pending_nonce_ = 0;
  uint32_t last_command_send_ms_ = 0;
  char interaction_status_[20] = {0};
  bool game_view_ = false;  // v2: Snack Catch view on the pet/care screens
  uint32_t feed_flash_ms_ = 0;  // feed treat/chomp animation start
  uint32_t pet_anim_ms_ = 0;    // stroke love/hearts animation start
  uint32_t catch_fx_ms_ = 0;    // Snack Catch burst start
  uint8_t catch_fx_x_ = 48;     // Snack Catch burst horizontal center
  uint32_t miss_fx_ms_ = 0;     // Snack Catch miss flash start
  uint32_t game_finish_ms_ = 0; // Snack Catch celebration start
  uint8_t last_game_caught_ = 0;
  uint8_t last_game_missed_ = 0;
  bool was_game_active_ = false;
  bool feed_anim_active() const {
    return feed_flash_ms_ != 0 && millis() - feed_flash_ms_ < 1800UL;
  }
  bool pet_anim_active() const {
    return pet_anim_ms_ != 0 && millis() - pet_anim_ms_ < 2000UL;
  }
  bool game_finish_anim_active() const {
    return game_finish_ms_ != 0 && millis() - game_finish_ms_ < 2200UL;
  }
  // Game-start refusal ("too tired" / "too sick") shown on CARE for 2.5 s.
  const char* game_refusal_ = "";
  uint32_t game_refusal_ms_ = 0;
  // v2 quiz (phone-driven; the wearable is the A-D pad like a Kahoot
  // controller): state arrives via MSG_QUIZ_STATE, answers leave via
  // MSG_QUIZ_ANSWER. Auto-takeover while active, like the PIN screen.
  bool quiz_active_ = false;
  uint8_t quiz_idx_ = 0;
  uint8_t quiz_total_ = 0;
  bool quiz_sent_ = false;      // an answer for the CURRENT question was sent
  uint8_t quiz_last_choice_ = 0;
  // Retransmit: notifications have no delivery guarantee and the scheduled
  // TDD disconnect can eat the answer — resend every 2 s until the phone's
  // next MSG_QUIZ_STATE advances the question (the care-event pattern).
  bool quiz_pending_ = false;
  uint8_t quiz_pending_choice_ = 0;
  uint32_t quiz_last_send_ms_ = 0;
  bool explore_dismissed_ = false;
  uint32_t quest_active_since_ms_ = 0;
  bool interaction_screen_active() const {
    const uint8_t ph = g_ble.interaction().phase;
    return ph >= 1 && ph <= 3;
  }
  bool quest_bt_out_of_range() const {
    const SessionStateMsg& s = g_ble.session();
    if (!s.active || quest_active_since_ms_ == 0) return false;
    if (s.quest == 5) return false;
    if (millis() - quest_active_since_ms_ < 25000UL) return false;
    if (g_ble.phoneLinkLost(25000UL)) return true;
    const PeerObservation& p = g_ble.last_peer();
    return (p.device == 0 || (millis() - p.at_ms) > 28000UL);
  }
  // Reward banner state (see flash_reward).
  char reward_title_[16] = {0};
  uint32_t reward_until_ms_ = 0;
  uint8_t reward_level_at_ = 0;

 public:
  bool wants_fast_render() const {
    return (screen_ == SCR_PET || screen_ == SCR_CARE) &&
           (game_view_ || g_petcore.game_active() || feed_anim_active() ||
            pet_anim_active() || game_finish_anim_active());
  }
  bool wants_timer_refresh() const {
    const SessionStateMsg& s = g_ble.session();
    if (!s.active || !s.timer_running) return false;
    return (screen_ == SCR_INTERACTION && g_ble.interaction().phase == 2) ||
           (screen_ == SCR_GPS && s.quest == 2);
  }

 private:
};

extern UiApp g_ui;
