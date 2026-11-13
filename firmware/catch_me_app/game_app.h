// v2 raid game: host-authoritative co-op boss fight over the direct
// board-to-board BLE connection (transport proven by the gate experiment).
//
// Board 1 (central) = HOST: simulates the boss (sinusoid drift + aimed slow
// bullets), both ships' movement and hit detection. Board 2 (peripheral) =
// CLIENT: renders the host state, sends its inputs.
//
// Wire format (matches docs/INTERFACES.md):
//   MSG_GAME_STATE (19) host -> client, ~10 Hz:
//     [ver=1][tick LE16][boss_x u8][boss_y u8][boss_hp u8][players 2x(u8 x,
//     u8 lives)][bullets n<=4 x(u8 x, u8 y)][flags u8 bit0=win bit1=lose]
//   MSG_GAME_INPUT (20) client -> host, ~10 Hz:
//     [ver=1][seq LE16][move i8 (-1/0/1)][fire u8]
//
// Buttons on both boards during RAID: UL left / UR right, LL fire, LR quit.
// The fight ends (win: boss hp 0; lose: both ships out of lives); the host
// reports the outcome through its phone once re-linked.

#pragma once

#include <Arduino.h>

#define GAME_ARENA_W 96
#define GAME_ARENA_H 64
#define GAME_BOSS_HP_DEMO 20
#define GAME_BOSS_HP_NORMAL 60
#define GAME_LIVES 3
#define GAME_BULLETS_MAX 4
#define GAME_TICK_MS 100

struct GamePlayer {
  uint8_t x = 48;
  int8_t lives = GAME_LIVES;
  uint8_t fire_cooldown = 0;
};

struct GameBullet {
  int8_t x = -1;
  int8_t y = 0;
  int8_t vy = 1;  // boss bullets fall
};

class GameApp {
 public:
  void begin(bool host);
  void tick();  // 10 ms cadence; steps at GAME_TICK_MS
  // Honest abort (module wedge / mid-fight radio loss): the fight did NOT
  // finish, so it can neither be won nor claimed; render shows the lost
  // state and the outcome is never relayed.
  void abort_lost() {
    finished_ = true;
    won_ = false;
    active_ = false;
  }

  bool active() const { return active_; }
  bool finished() const { return finished_; }
  bool won() const { return won_; }
  bool is_host() const { return host_; }

  // Host state (also rendered on the client from the wire mirror).
  uint8_t boss_x() const { return boss_x_; }
  uint8_t boss_y() const { return boss_y_; }
  uint8_t boss_hp() const { return boss_hp_; }
  uint8_t boss_hp_max() const { return boss_hp_max_; }
  const GamePlayer& player(uint8_t idx) const { return players_[idx & 1]; }
  uint8_t bullets(int8_t* bx, int8_t* by, uint8_t max) const;

  // Local ship control (host: ship 0 simulated; client: ship 1 on the host).
  void input_move(int8_t dir);
  void input_fire();

  // Client side: apply a received MSG_GAME_STATE payload.
  void apply_host_state(const uint8_t* p, uint16_t len);
  // Host side: apply a received MSG_GAME_INPUT payload (client's ship).
  void apply_client_input(const uint8_t* p, uint16_t len);

  // Host wire encode; returns length (0 = nothing to send).
  uint8_t encode_state(uint8_t* out, uint8_t cap);
  uint8_t encode_input(uint8_t* out, uint8_t cap);
  uint16_t tick_counter() const { return tick_; }

 private:
  void host_step();
  void spawn_bullet();
  bool host_;               // board 1 = host
  bool active_ = false;
  bool finished_ = false;
  bool won_ = false;
  uint16_t tick_ = 0;
  uint32_t last_step_ms_ = 0;
  uint8_t boss_x_ = 48;
  uint8_t boss_y_ = 12;
  int8_t boss_dir_ = 1;
  uint8_t boss_hp_ = GAME_BOSS_HP_DEMO;
  uint8_t boss_hp_max_ = GAME_BOSS_HP_DEMO;
  uint32_t last_spawn_ms_ = 0;
  GamePlayer players_[2];   // 0 = host ship, 1 = client ship
  GameBullet bullets_[GAME_BULLETS_MAX];
  int8_t pending_move_ = 0;
  bool pending_fire_ = false;
  uint16_t input_seq_ = 0;
};

extern GameApp g_game;
