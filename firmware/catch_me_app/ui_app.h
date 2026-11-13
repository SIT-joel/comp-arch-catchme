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
  // Phone-relayed quiz progress: active=0 leaves quiz mode. An idx CHANGE
  // (or quiz end) acknowledges the pending answer. Quiz completion
  // (active 1->0 with a quiz under way) fires the reward banner: the
  // lecturer must SEE the XP impact on the wearable itself.
  void note_quiz_state(uint8_t active, uint8_t idx, uint8_t total) {
    if (quiz_active_ && quiz_pending_ && (!active || idx != quiz_idx_)) {
      quiz_pending_ = false;  // the server accepted our answer
    }
    if (quiz_active_ && !active && quiz_total_ > 0) {
      flash_reward("QUIZ COMPLETE");
    }
    quiz_active_ = active != 0;
    quiz_idx_ = idx;
    quiz_total_ = total;
    quiz_sent_ = false;  // a new question (or quiz end) resets the pad
  }

  // Short (8 s) award banner overriding the current screen: title, the
  // exactly-once +100 points/+100 XP award, and the live server level
  // (shows "LEVEL UP" as soon as the pet sync delivers the new level).
  // Never overrides the raid fight or the PIN-evidence screen — those own
  // the display; the banner appears when they yield.
  void flash_reward(const char* title) {
    strncpy(reward_title_, title, sizeof(reward_title_) - 1);
    reward_title_[sizeof(reward_title_) - 1] = 0;
    reward_until_ms_ = millis() + 8000;
    reward_level_at_ = g_petcore.server_level();
  }

  // 10 ms tick: retransmit the pending answer until acknowledged.
  void tick_quiz() {
    if (!quiz_active_ || !quiz_pending_) return;
    const uint32_t now = millis();
    if (now - quiz_last_send_ms_ < 2000) return;
    quiz_last_send_ms_ = now;
    uint8_t ans[3] = {1, quiz_idx_, quiz_pending_choice_};
    if (g_ble.send_message(MSG_QUIZ_ANSWER, ans, sizeof(ans))) {
      quiz_sent_ = true;
      quiz_last_choice_ = quiz_pending_choice_;
    }
  }

 private:
  // The four cycled screens (UR/UL navigation). SCR_INTERACTION sits AFTER
  // SCREEN_COUNT: it is only entered by the interaction-phase takeover and
  // never by the cycle.
  enum Screen : uint8_t { SCR_PET = 0, SCR_CARE, SCR_DISC, SCR_GAME, SCREEN_COUNT, SCR_INTERACTION = SCREEN_COUNT, SCR_QUIZ };
  void render_pet();
  void render_care();
  void render_disc();
  void render_raid();
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
  uint32_t feed_flash_ms_ = 0;  // brief "fed!" / refusal feedback
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
  // Reward banner state (see flash_reward).
  char reward_title_[16] = {0};
  uint32_t reward_until_ms_ = 0;
  uint8_t reward_level_at_ = 0;

 public:
  bool wants_fast_render() const {
    return (screen_ == SCR_PET && game_view_) || g_game.active() ||
           g_ble.raid_active();
  }

 private:
};

extern UiApp g_ui;
