#include "ui_app.h"

#include "config.h"
#include "queue_sel.h"

#include <string.h>

// Draw helpers shared by the pet and raid renders (defined below; the CARE
// and NEAR screens reuse the row/ellipse primitives).
static void fill_row(TinyScreen& d, int x0, int x1, int y, uint8_t color);
static void fill_ellipse(TinyScreen& d, int cx, int cy, int rx, int ry, uint8_t color);

UiApp g_ui;

void UiApp::begin() {
  display_.begin();
  display_.setBrightness(8);
  display_.setFont(liberationSans_10ptFontInfo);
}

void UiApp::tick() {
  uint8_t buttons = display_.getButtons();
  uint8_t pressed = buttons & ~last_buttons_;  // edge only
  last_buttons_ = buttons;
  const InteractionStateMsg& interaction = g_ble.interaction();
  if (interaction.phase != last_phase_) {
    last_phase_ = interaction.phase;
    if (g_ble.raid_active() && screen_ != SCR_GAME) {
      screen_ = SCR_GAME;  // the fight takes over the display
    }
    if (interaction.phase == 1 || interaction.phase == 3) {
      screen_ = SCR_INTERACTION;
      pin_edit_ = true;
      memset(pin_digits_, 0, sizeof(pin_digits_));
      pin_digit_ = 0;
      interaction_status_[0] = 0;
    } else if (interaction.phase >= 4) {
      screen_ = SCR_INTERACTION;
      pin_edit_ = false;
    }
  }

  // v2 quiz: auto-takeover while the phone's quiz is active (the wearable
  // is the A-D answer pad; the question text lives on the phone screen).
  if (quiz_active_ && screen_ != SCR_QUIZ) {
    screen_ = SCR_QUIZ;
    quiz_sent_ = false;
  } else if (!quiz_active_ && screen_ == SCR_QUIZ) {
    screen_ = SCR_PET;  // quiz done or cancelled: back to the pet
  }

  // Retransmit the exact same command ID/payload until Android confirms the
  // server response. A reconnect therefore cannot create duplicate actions.
  if (pending_command_len_ && g_ble.phoneConnected() &&
      millis() - last_command_send_ms_ >= 1500) {
    if (g_ble.send_message(MSG_INTERACTION_COMMAND, pending_command_, pending_command_len_)) {
      last_command_send_ms_ = millis();
    }
  }

  if (screen_ == SCR_INTERACTION &&
      (interaction.phase == 1 || interaction.phase == 3)) {
    const uint8_t stage = interaction.stage;
    if (pin_edit_) {
      if (pressed & TSButtonUpperRight) pin_digits_[pin_digit_] = (pin_digits_[pin_digit_] + 1) % 10;
      if (pressed & TSButtonUpperLeft) pin_digits_[pin_digit_] = (pin_digits_[pin_digit_] + 9) % 10;
      if (pressed & TSButtonLowerRight) {
        if (pin_digit_ < 3) {
          ++pin_digit_;
        } else {
          char entry[5] = {char('0' + pin_digits_[0]), char('0' + pin_digits_[1]),
                           char('0' + pin_digits_[2]), char('0' + pin_digits_[3]), 0};
          send_interaction_command(1, stage, interaction.partner_code_version, entry);
        }
      }
      if (pressed & TSButtonLowerLeft) {
        if (pin_digit_ > 0) --pin_digit_;
        else pin_edit_ = false;  // leave entry only; do not cancel the quest
      }
    } else {
      if (pressed & TSButtonUpperRight) {
        pin_edit_ = true;
        pin_digit_ = 0;
      }
      if ((pressed & TSButtonLowerRight) && interaction.own_code_version) {
        send_interaction_command(2, stage, interaction.own_code_version, nullptr);
      }
      if (pressed & TSButtonUpperLeft) screen_ = SCR_PET;
      if (pressed & TSButtonLowerLeft) screen_ = SCR_PET;
    }
    return;  // PIN entry owns all four buttons; global navigation is paused.
  }

  if (screen_ == SCR_INTERACTION && interaction.phase >= 4) {
    if (pressed & TSButtonUpperRight) screen_ = SCR_PET;
    if (pressed & TSButtonUpperLeft) screen_ = SCR_PET;
    return;
  }
  // v2 quiz pad: UL=A, UR=B, LL=C, LR=D — one press per question; the
  // phone relays the next question via MSG_QUIZ_STATE (which clears sent).
  if (screen_ == SCR_QUIZ && quiz_active_) {
    if (!quiz_sent_) {
      uint8_t choice = 0xFF;
      if (pressed & TSButtonUpperLeft) choice = 0;
      else if (pressed & TSButtonUpperRight) choice = 1;
      else if (pressed & TSButtonLowerLeft) choice = 2;
      else if (pressed & TSButtonLowerRight) choice = 3;
      if (choice != 0xFF) {
        uint8_t ans[3] = {1, quiz_idx_, choice};
        if (g_ble.send_message(MSG_QUIZ_ANSWER, ans, sizeof(ans))) {
          quiz_sent_ = true;
          quiz_last_choice_ = choice;
          quiz_pending_ = true;  // retransmit until the phone acknowledges
          quiz_pending_choice_ = choice;
          quiz_last_send_ms_ = millis();
        }
      }
    }
    return;  // the pad owns all four buttons
  }

  // v2 raid screen: fight controls (LL left, LR right, UR fire; UL parked —
  // no navigation away mid-fight).
  if (screen_ == SCR_GAME && g_ble.raid_active()) {
    if (pressed & TSButtonLowerLeft) g_game.input_move(-1);
    if (pressed & TSButtonLowerRight) g_game.input_move(1);
    if (pressed & TSButtonUpperRight) g_game.input_fire();
    return;
  }

  // Snack Catch mini-game view (launched from PET or CARE): owns the lower
  // buttons; UL exits.
  if ((screen_ == SCR_PET || screen_ == SCR_CARE) &&
      (g_petcore.game_active() || game_view_)) {
    if (pressed & TSButtonLowerLeft) g_petcore.game_move(-1);
    if (pressed & TSButtonLowerRight) g_petcore.game_move(1);
    if (pressed & TSButtonUpperLeft) {
      if (g_petcore.game_active()) g_petcore.game_quit();
      game_view_ = false;
    }
    return;
  }

  // v2 pet home: bonding flows own the buttons first; then quick care.
  if (screen_ == SCR_PET) {
    if (g_petcore.bonding_species_active()) {
      if (pressed & TSButtonLowerRight) g_petcore.bond_cycle_species();
      if (pressed & TSButtonUpperRight) g_petcore.bond_commit_species();
      return;
    }
    if (g_petcore.naming_active()) {
      if (pressed & TSButtonUpperRight) g_petcore.naming_next_letter();
      if (pressed & TSButtonUpperLeft) g_petcore.naming_prev_letter();
      if (pressed & TSButtonLowerRight) g_petcore.naming_commit_char();
      if (pressed & TSButtonLowerLeft) g_petcore.naming_backspace();
      return;
    }
    if (pressed & TSButtonLowerLeft) {
      if (g_petcore.feed()) feed_flash_ms_ = millis();
    }
    if (pressed & TSButtonLowerRight) g_petcore.pet_stroke();
    // UL/UR fall through to global navigation below.
  }

  // v2 care screen: full care actions; UL/UR navigate.
  if (screen_ == SCR_CARE) {
    if (pressed & TSButtonLowerLeft) {
      if (g_petcore.feed()) feed_flash_ms_ = millis();
    }
    if (pressed & TSButtonLowerRight) g_petcore.pet_stroke();
    if (pressed & TSButtonUpperRight) {
      if (g_petcore.game_start() == nullptr) game_view_ = true;
    }
    // UL falls through to global navigation below.
  }

  if (pressed & TSButtonUpperRight) {
    screen_ = static_cast<Screen>((screen_ + 1) % SCREEN_COUNT);
  }
  if (pressed & TSButtonUpperLeft) {
    game_view_ = false;
    screen_ = static_cast<Screen>((screen_ + SCREEN_COUNT - 1) % SCREEN_COUNT);
  }
}

void UiApp::send_interaction_command(uint8_t kind, uint8_t stage, uint16_t code_version,
                                    const char* value) {
  // A completed entry REPLACES any still-pending command: when the previous
  // attempt was submitted while the phones were offline, its rejection ACK
  // (ok=0) can be lost with the link, leaving the board retransmitting an
  // expired command forever and silently dropping every new entry. The nonce
  // changes here, so apply_interaction_ack's stale-ACK check keeps an ACK for
  // the replaced command from clearing this one.
  const InteractionStateMsg& interaction = g_ble.interaction();
  uint8_t value_len = value ? 4 : 0;
  memset(pending_command_, 0, sizeof(pending_command_));
  pending_command_[0] = 1;
  pending_command_[1] = kind;
  pending_command_[2] = stage;
  pending_command_[3] = code_version & 0xFF;
  pending_command_[4] = (code_version >> 8) & 0xFF;
  uint32_t uptime = millis();
  uint16_t sequence = ++command_counter_;
  memcpy(pending_command_ + 5, &uptime, 4);
  memcpy(pending_command_ + 9, &sequence, 2);
  pending_command_[11] = DEVICE_ID;
  pending_command_[12] = g_ble.session().token_hash & 0xFF;
  memcpy(pending_command_ + 13, interaction.session_id, 16);
  pending_command_[29] = value_len;
  if (value_len) memcpy(pending_command_ + 30, value, value_len);
  pending_command_len_ = 30 + value_len;
  memcpy(&pending_nonce_, pending_command_ + 5, 8);
  strcpy(interaction_status_, "CHECKING");
  last_command_send_ms_ = 0;
  if (g_ble.phoneConnected() &&
      g_ble.send_message(MSG_INTERACTION_COMMAND, pending_command_, pending_command_len_)) {
    last_command_send_ms_ = millis();
  }
}

void UiApp::apply_interaction_ack(const uint8_t* payload, uint16_t len) {
  if (len < 10 || payload[0] != 1 || !pending_command_len_) return;
  if (memcmp(payload + 1, &pending_nonce_, 8) != 0) return;  // stale ACK
  pending_command_len_ = 0;
  strcpy(interaction_status_, payload[9] ? "SENT" : "RETRY NEEDED");
}

void UiApp::render() {
  display_.clearScreen();
  // Reward banner (8 s) overrides ordinary screens: the quest's XP impact
  // must be visible on the wearable itself, not only in the phone app. The
  // raid fight and PIN-evidence screens keep ownership of the display.
  const bool fight_owning = g_game.active() || g_ble.raid_active();
  if (reward_until_ms_ != 0 && millis() < reward_until_ms_ && !fight_owning &&
      screen_ != SCR_INTERACTION) {
    display_.setFont(liberationSans_10ptFontInfo);
    display_.setCursor(0, 0);
    display_.fontColor(TS_8b_Green, TS_8b_Black);
    display_.print(reward_title_);
    display_.setFont(liberationSans_8ptFontInfo);
    display_.setCursor(0, 20);
    display_.fontColor(TS_8b_White, TS_8b_Black);
    display_.print("+100 points");
    display_.setCursor(0, 32);
    display_.print("+100 XP");
    const uint8_t lvl = g_petcore.server_level();
    display_.setCursor(0, 44);
    if (reward_level_at_ != 0 && lvl > reward_level_at_) {
      display_.fontColor(TS_8b_Yellow, TS_8b_Black);
      display_.print("LEVEL UP! -> ");
      display_.print(lvl);
    } else if (lvl != 0) {
      display_.fontColor(TS_8b_Gray, TS_8b_Black);
      display_.print("LEVEL ");
      display_.print(lvl);
    } else {
      display_.fontColor(TS_8b_Gray, TS_8b_Black);
      display_.print("syncing level...");
    }
    return;
  }
  if (reward_until_ms_ != 0 && millis() >= reward_until_ms_) {
    reward_until_ms_ = 0;  // banner spent; normal screens resume
  }
  display_.setFont(liberationSans_10ptFontInfo);
  display_.fontColor(TS_8b_White, TS_8b_Black);
  switch (screen_) {
    case SCR_PET: render_pet(); break;
    case SCR_CARE: render_care(); break;
    case SCR_DISC: render_disc(); break;
    case SCR_GAME: render_raid(); break;
    case SCR_QUIZ: render_quiz(); break;
    case SCR_INTERACTION: render_interaction(); break;
    default: render_pet(); break;
  }
  // Screen indicator on the last row: name + position. The tamagotchi home
  // stays clean (its own status line occupies the footer); interaction
  // renders its own footer.
  if (screen_ != SCR_INTERACTION && screen_ != SCR_PET && screen_ != SCR_QUIZ) {
    static const char* kNames[SCREEN_COUNT] = {"PET", "CARE", "NEAR", "RAID"};
    display_.setFont(liberationSans_8ptFontInfo);
    display_.fontColor(TS_8b_Gray, TS_8b_Black);
    display_.setCursor(0, 58);
    display_.print("< ");
    display_.print(kNames[screen_]);
    display_.print(" ");
    display_.print(screen_ + 1);
    display_.print("/");
    display_.print(SCREEN_COUNT);
  }
}

// v2 CARE screen: the pet's care actions in one place (the tamagotchi home
// keeps quick feed/stroke; this screen adds Snack Catch and the honest
// care-sync state).
void UiApp::render_care() {
  const PetState& st = g_pet.state();

  display_.setFont(liberationSans_10ptFontInfo);
  display_.setCursor(0, 0);
  display_.fontColor(TS_8b_Gray, TS_8b_Black);
  display_.print("CARE");

  display_.setFont(liberationSans_8ptFontInfo);
  display_.setCursor(0, 14);
  display_.fontColor(TS_8b_White, TS_8b_Black);
  display_.print("LL feed  LR pet");
  display_.setCursor(0, 24);
  display_.fontColor(TS_8b_Yellow, TS_8b_Black);
  display_.print("UR play Snack Catch");

  // Need bars: H(hunger) J(joy) E(energy).
  const uint8_t bw = 26;
  struct Bar { const char* label; uint8_t value; };
  const Bar bars[3] = {{"H", st.hunger}, {"J", st.happiness}, {"E", st.energy}};
  for (uint8_t k = 0; k < 3; k++) {
    const uint8_t x = 2 + k * 32;
    const uint8_t y = 38;
    display_.setCursor(x, y - 2);
    display_.fontColor(TS_8b_Gray, TS_8b_Black);
    display_.print(bars[k].label);
    display_.drawRect(x + 8, y, bw, 4, 0, TS_8b_Gray);
    const uint8_t fill = (uint8_t)((bw - 2) * bars[k].value / 100);
    if (fill) {
      const uint8_t col = bars[k].value >= 40 ? TS_8b_Green
                          : bars[k].value >= 20 ? TS_8b_Yellow : TS_8b_Red;
      fill_row(display_, x + 9, x + 8 + fill, y + 1, col);
      fill_row(display_, x + 9, x + 8 + fill, y + 2, col);
    }
  }

  // Honest care-sync state: the wearable queues the care event; the phone
  // claims the server's once-daily +10 XP and ACKs.
  display_.setCursor(0, 48);
  uint32_t ymd = 0;
  uint64_t nonce = 0;
  if (g_petcore.care_event_pending(&ymd, &nonce)) {
    display_.fontColor(TS_8b_Yellow, TS_8b_Black);
    display_.print("care: waiting phone sync");
  } else if (!g_petcore.bonded()) {
    display_.fontColor(TS_8b_Gray, TS_8b_Black);
    display_.print("bond first (PET)");
  } else {
    display_.fontColor(TS_8b_Green, TS_8b_Black);
    display_.print("care: synced");
  }

  if (g_petcore.feed_refusal()[0]) {
    display_.setCursor(0, 14);
    display_.fontColor(TS_8b_Yellow, TS_8b_Black);
    display_.print(g_petcore.feed_refusal());
  } else if (millis() - feed_flash_ms_ < 1500) {
    display_.setCursor(0, 14);
    display_.fontColor(TS_8b_Green, TS_8b_Black);
    display_.print("fed!");
  }
}

// v2 NEAR screen: the proximity home — this is where "who is around me"
// lives. Partner first (the matched person), then the live wearable-to-
// wearable peer evidence, then discovery matches; everything honest.
void UiApp::render_disc() {
  display_.setFont(liberationSans_10ptFontInfo);
  display_.setCursor(0, 0);
  display_.fontColor(TS_8b_Gray, TS_8b_Black);
  display_.print("NEAR");

  // Phone link dot: matching happens in the app.
  display_.setFont(liberationSans_8ptFontInfo);
  display_.setCursor(76, 2);
  if (g_ble.phoneConnected()) {
    display_.fontColor(TS_8b_Green, TS_8b_Black);
    display_.print("app");
  } else {
    display_.fontColor(TS_8b_Red, TS_8b_Black);
    display_.print("app?");
  }

  // 1) Matched partner + distance (or the honest "none yet").
  display_.setCursor(0, 14);
  const char* name = g_ble.partner_name();
  if (name[0]) {
    display_.fontColor(TS_8b_White, TS_8b_Black);
    display_.print(name);
    if (g_ble.partner_dist_valid()) {
      display_.fontColor(TS_8b_Green, TS_8b_Black);
      display_.print(" ");
      display_.print(g_ble.partner_dist_m());
      display_.print("m");
    } else {
      display_.fontColor(TS_8b_Yellow, TS_8b_Black);
      display_.print(" d?");
    }
  } else {
    display_.fontColor(TS_8b_Gray, TS_8b_Black);
    display_.print("no match yet");
  }

  // 2) Live peer evidence (the other wearable's heartbeat adverts).
  const PeerObservation& peer = g_ble.last_peer();
  display_.setCursor(0, 26);
  if (peer.device != 0) {
    if (peer.fresh) {
      display_.fontColor(TS_8b_Green, TS_8b_Black);
      display_.print("WEARABLE NEAR #");
      display_.println(peer.device);
      // Signal bars from RSSI (honest coarse buckets, never a fake meter).
      const uint8_t bars = peer.rssi >= -60 ? 4
                           : peer.rssi >= -75 ? 3
                           : peer.rssi >= -90 ? 2 : 1;
      for (uint8_t k = 0; k < 4; k++) {
        const uint8_t bx = 2 + k * 6;
        const uint8_t bh = 3 + k * 2;
        if (k < bars) {
          display_.drawRect(bx, (uint8_t)(40 - bh), 3, bh, 0, TS_8b_Green);
          fill_row(display_, bx, bx + 1, 39, TS_8b_Green);
        } else {
          display_.drawRect(bx, (uint8_t)(40 - bh), 3, bh, 0, TS_8b_DarkGreen);
        }
      }
    } else {
      const uint32_t age_s = (millis() - peer.at_ms) / 1000;
      display_.fontColor(TS_8b_Yellow, TS_8b_Black);
      display_.print("wearable ");
      display_.print(age_s);
      display_.print("s ago");
    }
  } else {
    display_.fontColor(TS_8b_Gray, TS_8b_Black);
    display_.print("no wearable seen");
  }

  // 3) Discovery matches (rotates every ~2 s so each entry is readable).
  display_.setCursor(0, 44);
  const uint8_t count = g_ble.discovery_results_count();
  if (count > 0) {
    const uint8_t index = (millis() / 2000) % count;
    const DiscoveryResult& r = g_ble.discovery_results()[index];
    display_.fontColor(TS_8b_White, TS_8b_Black);
    display_.print(index + 1);
    display_.print("/");
    display_.print(count);
    display_.print(" ");
    display_.print(r.name);
    display_.print(" shr");
    display_.print(r.shared_count);
  } else {
    display_.fontColor(TS_8b_Gray, TS_8b_Black);
    display_.print("scanning...");
  }

  display_.setCursor(0, 52);
  display_.fontColor(TS_8b_Gray, TS_8b_Black);
  if (name[0]) {
    display_.print("quests in the app");
  } else {
    display_.print("pair in the app");
  }
}

void UiApp::render_interaction() {
  const InteractionStateMsg& interaction = g_ble.interaction();
  display_.setFont(liberationSans_8ptFontInfo);
  display_.fontColor(TS_8b_Gray, TS_8b_Black);
  display_.setCursor(0, 0);
  if (interaction.phase == 1 || interaction.phase == 3) {
    display_.print(interaction.stage == 1 ? "START CODE" : "FINISH CODE");
    display_.setCursor(0, 10);
    display_.fontColor(TS_8b_White, TS_8b_Black);
    display_.print("Your code: ");
    display_.print(interaction.own_code[0] ? interaction.own_code : "----");
    display_.setCursor(0, 20);
    display_.fontColor(TS_8b_Gray, TS_8b_Black);
    display_.print("Partner: ");
    display_.print(interaction.own_confirmed ? "entered yours" : "waiting");
    if (pin_edit_) {
      char entered[] = {' ', char('0' + pin_digits_[0]), ' ', char('0' + pin_digits_[1]),
                        ' ', char('0' + pin_digits_[2]), ' ', char('0' + pin_digits_[3]), 0};
      display_.setCursor(0, 31);
      display_.fontColor(TS_8b_White, TS_8b_Black);
      display_.print("Enter: ");
      display_.print(entered);
      display_.setCursor(0, 41);
      for (uint8_t i = 0; i < pin_digit_; ++i) display_.print("  ");
      display_.print("^");
      display_.fontColor(TS_8b_Gray, TS_8b_Black);
      display_.setCursor(0, 50);
      display_.print("UR + UL - LR next");
      display_.setCursor(0, 58);
      // Surface the server ACK while entry mode stays open; otherwise an
      // incorrect/expired PIN looks like the button did nothing.
      display_.print(interaction_status_[0] ? interaction_status_ : "LL back");
    } else {
      display_.setCursor(0, 33);
      display_.print(interaction.partner_confirmed ? "You entered partner's code" : "Enter partner's code");
      display_.setCursor(0, 45);
      display_.print("UR edit  LR refresh");
      display_.setCursor(0, 56);
      display_.print(interaction_status_[0] ? interaction_status_ : "LL back");
    }
    return;
  }

  if (interaction.phase == 2) {
    display_.print("TOGETHER TIME");
    display_.setCursor(0, 18);
    display_.fontColor(TS_8b_Green, TS_8b_Black);
    display_.print("Codes confirmed");
    display_.setCursor(0, 32);
    display_.fontColor(TS_8b_White, TS_8b_Black);
    display_.print("Verified BT time");
    display_.setCursor(0, 45);
    display_.print(g_ble.session().progress_ms / 1000);
    display_.print(" / ");
    display_.print(g_ble.session().target_ms / 1000);
    display_.print(" sec");
    return;
  }
  if (interaction.phase == 4) {
    display_.print("KEEP YOUR COOL");
    display_.setCursor(0, 18);
    display_.fontColor(TS_8b_White, TS_8b_Black);
    display_.print("Baseline: both fingers");
    display_.setCursor(0, 32);
    display_.print("HR + peer must be valid");
    display_.setCursor(0, 46);
    display_.fontColor(TS_8b_Yellow, TS_8b_Black);
    display_.print("Gaps pause progress");
    return;
  }
  if (interaction.phase == 5) {
    display_.print("CHOOSE A PROMPT");
    display_.setCursor(0, 18);
    display_.fontColor(TS_8b_White, TS_8b_Black);
    display_.print(interaction.active_user ? "Your turn" : "Partner's turn");
    display_.setCursor(0, 34);
    display_.print("UL Truth");
    display_.print("  UR Dare");
    display_.setCursor(0, 49);
    display_.fontColor(TS_8b_Gray, TS_8b_Black);
    display_.print("Both users stay still");
    return;
  }
  if (interaction.phase == 6) {
    display_.print(interaction.prompt_kind == 1 ? "TRUTH" : "DARE");
    display_.print(" ");
    display_.print(interaction.round_index);
    display_.print("/2");
    display_.setCursor(0, 14);
    display_.fontColor(TS_8b_White, TS_8b_Black);
    char line[15] = {0};
    strncpy(line, interaction.prompt, 14);
    display_.print(line);
    display_.setCursor(0, 25);
    display_.print(interaction.prompt + strlen(line));
    display_.setCursor(0, 40);
    display_.fontColor(TS_8b_Gray, TS_8b_Black);
    display_.print("Keep fingers still");
    display_.setCursor(0, 52);
    display_.print(interaction.active_user ? "LL skip  LR next" : "Partner's turn");
    return;
  }
  if (interaction.phase == 7) {
    display_.print("KEEP YOUR COOL");
    display_.setCursor(0, 20);
    display_.fontColor(TS_8b_Green, TS_8b_Black);
    display_.print("Complete!");
    display_.setCursor(0, 33);
    display_.fontColor(TS_8b_White, TS_8b_Black);
    display_.print("+100 points / XP");
    char line[15] = {0};
    strncpy(line, interaction.prompt, 14);
    display_.setCursor(0, 44);
    display_.fontColor(TS_8b_Gray, TS_8b_Black);
    display_.print(line);
    display_.setCursor(0, 54);
    display_.print(interaction.prompt + strlen(line));
    return;
  }
  display_.print("No interaction");
}

// ---- v2 pet rendering (ported from the bench-verified pet fork) ----

static void fill_row(TinyScreen& d, int x0, int x1, int y, uint8_t color) {
  if (x1 < x0) return;
  d.drawLine((uint8_t)x0, (uint8_t)y, (uint8_t)x1, (uint8_t)y, color);
}

// Filled ellipse via integer row half-widths (no FPU on SAMD21).
static void fill_ellipse(TinyScreen& d, int cx, int cy, int rx, int ry, uint8_t color) {
  for (int dy = -ry; dy <= ry; dy++) {
    int t = ((ry * ry - dy * dy) << 8) / (ry * ry);  // 0..256
    int hw = (rx * t) >> 8;
    fill_row(d, cx - hw, cx + hw, cy + dy, color);
  }
}

static void draw_heart(TinyScreen& d, int x, int y) {
  d.drawPixel(x + 1, y + 0, TS_8b_Red);
  d.drawPixel(x + 3, y + 0, TS_8b_Red);
  d.drawPixel(x + 0, y + 1, TS_8b_Red);
  d.drawPixel(x + 2, y + 1, TS_8b_Red);
  d.drawPixel(x + 4, y + 1, TS_8b_Red);
  d.drawPixel(x + 1, y + 2, TS_8b_Red);
  d.drawPixel(x + 3, y + 2, TS_8b_Red);
  d.drawPixel(x + 2, y + 3, TS_8b_Red);
}

static void draw_pet_sprite(TinyScreen& d, uint8_t species, uint8_t mood, uint8_t frame,
                            int cx, int cy) {
  const uint8_t body = species == SPECIES_SPARK  ? TS_8b_Yellow
                       : species == SPECIES_FLUFF ? TS_8b_White
                                                  : TS_8b_Blue;
  int dy = (mood == PET_MOOD_HAPPY && frame) ? 1 : 0;
  if (mood == PET_MOOD_SLEEPING) dy = 1;

  if (species == SPECIES_FLUFF) {  // bunny: two long ears
    fill_row(d, cx - 6, cx - 5, cy - 12 + dy, body);
    fill_row(d, cx - 6, cx - 5, cy - 11 + dy, body);
    fill_row(d, cx + 4, cx + 5, cy - 12 + dy, body);
    fill_row(d, cx + 4, cx + 5, cy - 11 + dy, body);
  } else if (species == SPECIES_PIP) {  // cat: triangle ears
    d.drawPixel(cx - 6, cy - 10 + dy, body);
    d.drawPixel(cx - 5, cy - 11 + dy, body);
    fill_row(d, cx - 6, cx - 4, cy - 10 + dy, body);
    d.drawPixel(cx + 6, cy - 10 + dy, body);
    d.drawPixel(cx + 5, cy - 11 + dy, body);
    fill_row(d, cx + 4, cx + 6, cy - 10 + dy, body);
  } else {  // Spark: antenna with a flame tip
    d.drawLine(cx, cy - 9 + dy, cx, cy - 12 + dy, TS_8b_Gray);
    d.drawPixel(cx, cy - 13 + dy, frame ? TS_8b_Red : TS_8b_Yellow);
  }

  fill_ellipse(d, cx, cy + dy, 10, 8, body);

  const uint8_t ink = TS_8b_Black;
  const int fy = cy + dy;
  if (mood == PET_MOOD_SLEEPING) {
    fill_row(d, cx - 5, cx - 3, fy - 2, ink);  // closed eyes
    fill_row(d, cx + 3, cx + 5, fy - 2, ink);
    fill_row(d, cx - 1, cx + 1, fy + 2, ink);  // small mouth
  } else {
    d.drawPixel(cx - 4, fy - 3, ink);
    d.drawPixel(cx - 4, fy - 2, ink);
    d.drawPixel(cx + 4, fy - 3, ink);
    d.drawPixel(cx + 4, fy - 2, ink);
    if (mood == PET_MOOD_HAPPY) {
      d.drawPixel(cx - 2, fy + 2, ink);
      d.drawPixel(cx - 1, fy + 3, ink);
      d.drawPixel(cx, fy + 3, ink);
      d.drawPixel(cx + 1, fy + 3, ink);
      d.drawPixel(cx + 2, fy + 2, ink);
    } else if (mood == PET_MOOD_SAD || mood == PET_MOOD_SICK) {
      d.drawPixel(cx - 2, fy + 3, ink);
      d.drawPixel(cx - 1, fy + 2, ink);
      d.drawPixel(cx, fy + 2, ink);
      d.drawPixel(cx + 1, fy + 2, ink);
      d.drawPixel(cx + 2, fy + 3, ink);
    } else if (mood == PET_MOOD_TIRED) {
      fill_row(d, cx - 2, cx + 2, fy + 2, ink);
    } else {
      fill_row(d, cx - 1, cx + 1, fy + 2, ink);
    }
  }
}

void UiApp::render_game() {
  if (g_petcore.game_active()) {
    display_.setFont(liberationSans_8ptFontInfo);
    display_.setCursor(0, 0);
    display_.fontColor(TS_8b_White, TS_8b_Black);
    display_.print("C:");
    display_.print(g_petcore.game_caught());
    display_.print(" M:");
    display_.print(g_petcore.game_missed());
    display_.print("/");
    display_.print(CM_GAME_MAX_MISSES);

    int8_t sx[3], sy[3];
    const uint8_t n = g_petcore.game_snacks(sx, sy, 3);
    for (uint8_t k = 0; k < n; k++) {
      display_.drawRect((uint8_t)sx[k] - 1, (uint8_t)sy[k] + 4, 3, 3, 1, TS_8b_Yellow);
    }
    const uint8_t bx = (uint8_t)g_petcore.game_basket_x();
    display_.drawRect(bx - 6, 52, 13, 4, 1, TS_8b_Brown);
    display_.drawRect(bx - 6, 52, 13, 1, 1, TS_8b_DarkBrown);
    return;
  }

  display_.setFont(liberationSans_10ptFontInfo);
  display_.setCursor(0, 12);
  display_.fontColor(TS_8b_White, TS_8b_Black);
  display_.print("Snack Catch");
  display_.setCursor(0, 28);
  display_.setFont(liberationSans_8ptFontInfo);
  display_.fontColor(TS_8b_Gray, TS_8b_Black);
  display_.print("LL/LR: move basket");
  display_.setCursor(0, 40);
  display_.fontColor(TS_8b_Yellow, TS_8b_Black);
  display_.print("UL: back to pet");
}

void UiApp::render_pet() {
  const PetState& st = g_pet.state();

  // --- Species chooser (first boot) ---
  if (g_petcore.bonding_species_active()) {
    display_.setFont(liberationSans_10ptFontInfo);
    display_.setCursor(0, 0);
    display_.fontColor(TS_8b_Gray, TS_8b_Black);
    display_.print("Choose pet");
    const uint8_t sp = g_petcore.bond_species();
    draw_pet_sprite(display_, sp, PET_MOOD_HAPPY, g_petcore.anim_frame(), 48, 30);
    display_.setCursor(0, 44);
    display_.fontColor(TS_8b_White, TS_8b_Black);
    display_.print(sp == SPECIES_SPARK ? "Spark" : sp == SPECIES_FLUFF ? "Fluff" : "Pip");
    display_.setFont(liberationSans_8ptFontInfo);
    display_.setCursor(50, 44);
    display_.fontColor(TS_8b_Gray, TS_8b_Black);
    display_.print("LR next");
    display_.setCursor(0, 54);
    display_.fontColor(TS_8b_Yellow, TS_8b_Black);
    display_.print("UR: yes!");
    return;
  }

  // --- Name editor (bonding step 2) ---
  if (g_petcore.naming_active()) {
    display_.setFont(liberationSans_8ptFontInfo);
    display_.setCursor(0, 0);
    display_.fontColor(TS_8b_Gray, TS_8b_Black);
    display_.print("Name your pet");
    display_.setCursor(0, 14);
    display_.setFont(liberationSans_10ptFontInfo);
    display_.fontColor(TS_8b_White, TS_8b_Black);
    display_.print(g_petcore.naming_len() > 0 ? g_petcore.naming_buffer() : "(name)");
    char cur = PetCore::naming_letter_at(g_petcore.naming_cursor());
    display_.setCursor(0, 28);
    display_.fontColor(TS_8b_Yellow, TS_8b_Black);
    if (cur == '>') {
      display_.print("DONE -> LR");
    } else {
      display_.print("Letter: ");
      display_.print(cur);
    }
    display_.setCursor(0, 44);
    display_.setFont(liberationSans_8ptFontInfo);
    display_.fontColor(TS_8b_Gray, TS_8b_Black);
    display_.print("UR+ UL- LR keep");
    display_.setCursor(0, 54);
    display_.print("LL del; > = finish");
    return;
  }

  // --- Snack Catch (pet mini-game) ---
  if (g_petcore.game_active() || game_view_) {
    render_game();
    return;
  }

  // --- Bonded pet view ---
  display_.setFont(liberationSans_8ptFontInfo);
  display_.setCursor(0, 0);
  display_.fontColor(TS_8b_White, TS_8b_Black);
  display_.print(st.name[0] ? st.name : "pet");
  if (g_petcore.server_synced()) {
    display_.print(" L");
    display_.print(g_petcore.server_level());
  } else {
    display_.print(" L?");  // honest: level unknown until the first sync
  }
  const PetStage stage = g_petcore.stage();
  display_.setFont(liberationSans_8ptFontInfo);
  display_.fontColor(TS_8b_Gray, TS_8b_Black);
  display_.print(stage == PET_ADULT ? " adult" : stage == PET_TEEN ? " teen" : " baby");

  const uint8_t mood = g_petcore.mood();
  const int cy = 26;
  draw_pet_sprite(display_, st.species, mood, g_petcore.anim_frame(), 48, cy);

  if (g_petcore.hearts_visible()) {
    const int hy = cy - 14 - (g_petcore.anim_frame() ? 1 : 0);
    draw_heart(display_, 30, hy);
    draw_heart(display_, 46, hy - 2);
    draw_heart(display_, 62, hy);
  }

  // Need bars: H(hunger) J(joy) E(energy).
  const uint8_t bw = 26;
  struct Bar { const char* label; uint8_t value; };
  const Bar bars[3] = {{"H", st.hunger}, {"J", st.happiness}, {"E", st.energy}};
  for (uint8_t k = 0; k < 3; k++) {
    const uint8_t x = 2 + k * 32;
    const uint8_t y = 42;
    display_.setFont(liberationSans_8ptFontInfo);
    display_.setCursor(x, y - 2);
    display_.fontColor(TS_8b_Gray, TS_8b_Black);
    display_.print(bars[k].label);
    display_.drawRect(x + 8, y, bw, 4, 0, TS_8b_Gray);
    const uint8_t fill = (uint8_t)((bw - 2) * bars[k].value / 100);
    if (fill) {
      const uint8_t col = bars[k].value >= 40 ? TS_8b_Green
                          : bars[k].value >= 20 ? TS_8b_Yellow : TS_8b_Red;
      fill_row(display_, x + 9, x + 8 + fill, y + 1, col);
      fill_row(display_, x + 9, x + 8 + fill, y + 2, col);
    }
  }

  // Celebrations: confetti after an award, "evolved!" on growth.
  if (g_petcore.award_flash()) {
    const uint8_t f = g_petcore.anim_frame();
    for (uint8_t k = 0; k < 8; k++) {
      const uint8_t px = (k * 13 + (f ? 5 : 0)) % 94 + 1;
      const uint8_t py = 6 + ((k * 7 + (f ? 3 : 0)) % 50);
      display_.drawPixel(px, py, k % 3 == 0 ? TS_8b_Yellow : k % 3 == 1 ? TS_8b_Green : TS_8b_Red);
    }
  } else if (g_petcore.evolve_flash()) {
    display_.setCursor(56, 12);
    display_.fontColor(TS_8b_Yellow, TS_8b_Black);
    display_.print("EVOLVED!");
  }

  // Mood / status line (brief feed feedback overrides it for 1.5 s).
  display_.setCursor(0, 52);
  if (millis() - feed_flash_ms_ < 1500) {
    display_.fontColor(TS_8b_Green, TS_8b_Black);
    display_.print("fed!");
    return;
  }
  if (g_petcore.lonely()) {
    display_.fontColor(TS_8b_Red, TS_8b_Black);
    display_.print("lonely... bring a friend");
  } else {
    switch (mood) {
      case PET_MOOD_HAPPY: display_.fontColor(TS_8b_Green, TS_8b_Black); display_.print("happy!"); break;
      case PET_MOOD_SAD: display_.fontColor(TS_8b_Yellow, TS_8b_Black); display_.print("sad"); break;
      case PET_MOOD_SICK: display_.fontColor(TS_8b_Red, TS_8b_Black); display_.print("sick - feed me"); break;
      case PET_MOOD_TIRED: display_.fontColor(TS_8b_Yellow, TS_8b_Black); display_.print("tired"); break;
      case PET_MOOD_SLEEPING: display_.fontColor(TS_8b_Gray, TS_8b_Black); display_.print("zzz"); break;
      default: display_.fontColor(TS_8b_White, TS_8b_Black); display_.print("ok"); break;
    }
    if (g_petcore.feed_refusal()[0]) {
      display_.fontColor(TS_8b_Yellow, TS_8b_Black);
      display_.print(" ");
      display_.print(g_petcore.feed_refusal());
    }
  }
}

// ---- v2 quiz pad rendering: question progress + A-D legend ----

void UiApp::render_quiz() {
  display_.setFont(liberationSans_10ptFontInfo);
  display_.setCursor(0, 0);
  display_.fontColor(TS_8b_White, TS_8b_Black);
  display_.print("QUIZ ");
  display_.print(quiz_total_ ? (quiz_idx_ + 1) : 0);
  display_.print("/");
  display_.print(quiz_total_);

  display_.setFont(liberationSans_8ptFontInfo);
  display_.setCursor(0, 18);
  display_.fontColor(TS_8b_Gray, TS_8b_Black);
  display_.print("question on the phone");

  // Kahoot-style pad legend, one letter per button.
  display_.setCursor(0, 30);
  display_.fontColor(TS_8b_Red, TS_8b_Black);
  display_.print("UL=A");
  display_.setCursor(52, 30);
  display_.fontColor(TS_8b_Blue, TS_8b_Black);
  display_.print("UR=B");
  display_.setCursor(0, 42);
  display_.fontColor(TS_8b_Yellow, TS_8b_Black);
  display_.print("LL=C");
  display_.setCursor(52, 42);
  display_.fontColor(TS_8b_Green, TS_8b_Black);
  display_.print("LR=D");

  display_.setCursor(0, 54);
  if (quiz_sent_) {
    display_.fontColor(TS_8b_Green, TS_8b_Black);
    display_.print("sent: ");
    display_.print((char)('A' + quiz_last_choice_));
    display_.print(" - waiting...");
  } else {
    display_.fontColor(TS_8b_White, TS_8b_Black);
    display_.print("press your answer");
  }
}

// ---- v2 raid fight rendering (both boards; state mirrors the host) ----

void UiApp::render_raid() {
  // Idle: raid info — the fight starts from the phone (landmark raid quest);
  // this screen shows readiness honestly and the last result.
  if (!g_ble.raid_active() && !g_game.active()) {
    display_.setFont(liberationSans_10ptFontInfo);
    display_.setCursor(0, 0);
    display_.fontColor(TS_8b_Gray, TS_8b_Black);
    display_.print("RAID");

    display_.setFont(liberationSans_8ptFontInfo);
    display_.setCursor(0, 16);
    const PeerObservation& peer = g_ble.last_peer();
    if (peer.device != 0 && peer.fresh) {
      display_.fontColor(TS_8b_Green, TS_8b_Black);
      display_.print("partner wearable near");
    } else {
      display_.fontColor(TS_8b_Gray, TS_8b_Black);
      display_.print("need partner wearable");
    }
    display_.setCursor(0, 28);
    display_.fontColor(TS_8b_White, TS_8b_Black);
    display_.print("start: raid in app");
    display_.setCursor(0, 40);
    if (g_game.finished()) {
      display_.fontColor(g_game.won() ? TS_8b_Green : TS_8b_Red, TS_8b_Black);
      display_.print(g_game.won() ? "last: WON" : "last: lost");
    } else {
      display_.fontColor(TS_8b_Gray, TS_8b_Black);
      display_.print("co-op boss, board vs board");
    }
    display_.setCursor(0, 50);
    display_.fontColor(TS_8b_Gray, TS_8b_Black);
    display_.print("LL< >LR  UR fire");
    return;
  }

  display_.setFont(liberationSans_8ptFontInfo);
  display_.setCursor(0, 0);
  display_.fontColor(TS_8b_White, TS_8b_Black);
  display_.print("BOSS ");
  display_.print(g_game.boss_hp());
  display_.print("/");
  display_.print(g_game.boss_hp_max());

  // Boss body.
  fill_ellipse(display_, g_game.boss_x(), g_game.boss_y(), 7, 4, TS_8b_Red);
  display_.drawPixel(g_game.boss_x(), g_game.boss_y() + 4, TS_8b_Yellow);

  // Bullets.
  int8_t bx[4], by[4];
  const uint8_t n = g_game.bullets(bx, by, 4);
  for (uint8_t k = 0; k < n; k++) {
    display_.drawRect((uint8_t)bx[k], (uint8_t)by[k], 2, 3, 1, TS_8b_Yellow);
  }

  // Ships: you = green bottom, partner = blue (both boards render both).
  const GamePlayer& p0 = g_game.player(0);
  const GamePlayer& p1 = g_game.player(1);
  if (p0.lives > 0) {
    display_.drawRect(p0.x - 3, GAME_ARENA_H - 10, 7, 4, 1, TS_8b_Green);
  }
  if (p1.lives > 0) {
    display_.drawRect(p1.x - 3, GAME_ARENA_H - 5, 7, 3, 1, TS_8b_Blue);
  }

  // Lives + result line.
  display_.setCursor(56, 0);
  display_.fontColor(TS_8b_Gray, TS_8b_Black);
  display_.print("x");
  display_.print(g_game.player(DEVICE_ID == 1 ? 0 : 1).lives);
  display_.setCursor(0, 54);
  if (g_game.finished()) {
    display_.fontColor(g_game.won() ? TS_8b_Green : TS_8b_Red, TS_8b_Black);
    display_.print(g_game.won() ? "RAID WON!" : "raid lost");
  } else {
    display_.fontColor(TS_8b_Gray, TS_8b_Black);
    display_.print("LL< >LR move  UR fire");
  }
}
