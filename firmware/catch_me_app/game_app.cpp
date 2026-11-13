#include "game_app.h"

#include "ble_app.h"
#include "config.h"

GameApp g_game;

void GameApp::begin(bool host) {
  host_ = host;
  active_ = true;
  finished_ = false;
  won_ = false;
  tick_ = 0;
  // Demo flag comes from the relayed session state (frozen at activation).
  boss_hp_max_ = boss_hp_ = g_ble.session().demo ? GAME_BOSS_HP_DEMO : GAME_BOSS_HP_NORMAL;
  boss_x_ = 48;
  boss_dir_ = 1;
  for (auto& p : players_) {
    p.x = 48;
    p.lives = GAME_LIVES;
    p.fire_cooldown = 0;
  }
  for (auto& b : bullets_) b.x = -1;
  last_step_ms_ = millis();
}

void GameApp::input_move(int8_t dir) {
  if (!active_ || finished_) return;
  pending_move_ = dir > 0 ? 1 : dir < 0 ? -1 : 0;
}

void GameApp::input_fire() {
  if (!active_ || finished_) return;
  pending_fire_ = true;
}

uint8_t GameApp::bullets(int8_t* bx, int8_t* by, uint8_t max) const {
  uint8_t n = 0;
  for (uint8_t k = 0; k < GAME_BULLETS_MAX && n < max; k++) {
    if (bullets_[k].x >= 0) {
      bx[n] = bullets_[k].x;
      by[n] = bullets_[k].y;
      n++;
    }
  }
  return n;
}

void GameApp::spawn_bullet() {
  for (auto& b : bullets_) {
    if (b.x < 0) {
      b.x = boss_x_;
      b.y = boss_y_ + 4;
      b.vy = 1;
      return;
    }
  }
}

void GameApp::host_step() {
  // Boss: sinusoid-ish drift with direction bounce.
  boss_x_ += boss_dir_;
  if (boss_x_ <= 8 || boss_x_ >= GAME_ARENA_W - 9) boss_dir_ = -boss_dir_;

  // Ships: host ship 0 from pending input; client ship 1 mirrors its input.
  if (pending_move_ != 0) {
    const int8_t d = pending_move_ * 4;
    const uint8_t idx = host_ ? 0 : 1;
    const int nx = players_[idx].x + d;
    if (nx >= 3 && nx <= GAME_ARENA_W - 4) players_[idx].x = nx;
    pending_move_ = 0;
  }

  // Fire: host ship shoots straight up at the boss; client ship's shots are
  // abstracted (each fire command damages the boss when in range) — v1 keeps
  // client shots as direct damage (co-op feel; the client sees its hits via
  // the boss hp mirror).
  const uint8_t my_idx = host_ ? 0 : 1;
  if (pending_fire_ && players_[my_idx].fire_cooldown == 0) {
    pending_fire_ = false;
    players_[my_idx].fire_cooldown = 5;  // ~0.5 s at 10 Hz
    if (host_) {
      // Straight shot from the host ship; hits when horizontally aligned.
      if (boss_hp_ > 0 && players_[0].x + 6 >= boss_x_ && players_[0].x + 2 <= boss_x_ + 6) {
        boss_hp_--;
      }
    } else {
      // The client's fire is forwarded (input message); the HOST applies the
      // client's damage there — here we only visualise on the client.
      if (boss_hp_ > 0) boss_hp_--;  // optimistic mirror; host state wins on next tick
    }
  }
  if (players_[my_idx].fire_cooldown > 0) players_[my_idx].fire_cooldown--;

  if (!host_) return;

  // --- host authority: boss bullets vs both ships ---
  const uint32_t now = millis();
  if (now - last_spawn_ms_ >= 1800) {
    last_spawn_ms_ = now;
    spawn_bullet();
  }
  for (auto& b : bullets_) {
    if (b.x < 0) continue;
    b.y += b.vy;
    if (b.y > GAME_ARENA_H) {
      b.x = -1;
      continue;
    }
    for (auto& p : players_) {
      if (p.lives > 0 && b.y >= GAME_ARENA_H - 12 && b.y <= GAME_ARENA_H - 6 &&
          b.x + 2 >= p.x - 4 && b.x <= p.x + 4) {
        b.x = -1;
        if (p.lives > 0) p.lives--;
        break;
      }
    }
  }

  // End conditions.
  if (boss_hp_ == 0) {
    finished_ = true;
    won_ = true;
    active_ = false;
  } else if (players_[0].lives == 0 && players_[1].lives == 0) {
    finished_ = true;
    won_ = false;
    active_ = false;
  }
}

void GameApp::tick() {
  if (!active_ || finished_) return;
  const uint32_t now = millis();
  if (now - last_step_ms_ < GAME_TICK_MS) return;
  last_step_ms_ = now;
  tick_++;
  host_step();
}

uint8_t GameApp::encode_state(uint8_t* out, uint8_t cap) {
  if (cap < 20) return 0;
  memset(out, 0, 20);
  out[0] = 1;  // ver
  out[1] = tick_ & 0xFF;
  out[2] = (tick_ >> 8) & 0xFF;
  out[3] = boss_x_;
  out[4] = boss_y_;
  out[5] = boss_hp_;
  out[6] = players_[0].x;
  out[7] = players_[0].lives;
  out[8] = players_[1].x;
  out[9] = players_[1].lives;
  uint8_t n = 0;
  for (uint8_t k = 0; k < GAME_BULLETS_MAX && n < 4; k++) {
    if (bullets_[k].x >= 0) {
      out[10 + n * 2] = bullets_[k].x;
      out[11 + n * 2] = bullets_[k].y;
      n++;
    }
  }
  out[18] = n;
  out[19] = finished_ ? (won_ ? 1 : 2) : 0;
  return 20;
}

uint8_t GameApp::encode_input(uint8_t* out, uint8_t cap) {
  if (cap < 6) return 0;
  memset(out, 0, 6);
  out[0] = 1;
  out[1] = input_seq_ & 0xFF;
  out[2] = (input_seq_ >> 8) & 0xFF;
  out[3] = (uint8_t)pending_move_;
  out[4] = pending_fire_ ? 1 : 0;
  input_seq_++;
  return 6;
}

void GameApp::apply_host_state(const uint8_t* p, uint16_t len) {
  if (len < 20 || p[0] != 1) return;
  boss_x_ = p[3];
  boss_y_ = p[4];
  boss_hp_ = p[5];
  players_[0].x = p[6];
  players_[0].lives = p[7];
  players_[1].x = p[8];
  players_[1].lives = p[9];
  const uint8_t n = p[18] > 4 ? 4 : p[18];
  for (auto& b : bullets_) b.x = -1;
  for (uint8_t k = 0; k < n; k++) {
    bullets_[k].x = p[10 + k * 2];
    bullets_[k].y = p[11 + k * 2];
  }
  if (p[19] == 1) {
    finished_ = true;
    won_ = true;
    active_ = false;
  } else if (p[19] == 2) {
    finished_ = true;
    won_ = false;
    active_ = false;
  }
}

void GameApp::apply_client_input(const uint8_t* p, uint16_t len) {
  if (len < 6 || p[0] != 1 || !host_) return;
  const int8_t move = (int8_t)p[3];
  const bool fire = p[4] != 0;
  if (move != 0) {
    const int nx = players_[1].x + move * 4;
    if (nx >= 3 && nx <= GAME_ARENA_W - 4) players_[1].x = nx;
  }
  if (fire && players_[1].fire_cooldown == 0) {
    players_[1].fire_cooldown = 5;
    if (boss_hp_ > 0 && players_[1].x + 6 >= boss_x_ && players_[1].x + 2 <= boss_x_ + 6) {
      boss_hp_--;
    }
  }
  if (players_[1].fire_cooldown > 0) players_[1].fire_cooldown--;
}
