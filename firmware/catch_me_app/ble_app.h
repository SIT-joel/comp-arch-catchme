// BLE application layer: multi-role BlueNRG-MS operation.
//
// Two logically separate services share one radio (docs/INTERFACES.md):
//  1. Peer presence — advertised manufacturer data carrying the heartbeat;
//     the central-role scan observes the partner's advertisements. Each
//     accepted observation is a direct wearable-to-wearable evidence point.
//  2. Phone transport — Nordic-style UART service (the STBLE example's
//     service) carrying framed messages both ways (TELEMETRY up; ACK,
//     TIME_ANCHOR, SESSION_STATE, COMPLETION down).
//
// The radio schedule is deliberately conservative: while the phone link is
// connected, the discovery procedure is restarted only from the main loop's
// 8 s tick (the phone connection owns most radio time); peer observations
// still accumulate whenever advertisements land. Concurrency behavior is a
// hardware-gate question — see docs/PROGRESS.md; this module records what it
// observes rather than assuming a cadence.

#pragma once

#include <Arduino.h>
#include "config.h"

// Framed message types (phone <-> wearable).
#define MSG_HELLO 1
#define MSG_TIME_ANCHOR 2
#define MSG_SESSION_STATE 3
#define MSG_PEER_HEARTBEAT 4
#define MSG_TELEMETRY 5
#define MSG_ACK 6
#define MSG_STATUS 7
// Nearby discovery (docs/DISCOVERY_PLAN.md) — versioned payloads, separate
// from session-bound quest transport. Unknown payload versions are
// rejected explicitly (logged), never misdecoded.
#define MSG_DISCOVERY_MODE 8   // phone -> wearable: [ver u8][mode u8][token LE16]
#define MSG_DISCOVERY_OBS 9    // wearable -> phone: [ver u8][n u8][n*(token LE16 + age_ms LE16)]
#define MSG_DISCOVERY_RESULTS 10  // phone -> wearable: compact display results
#define MSG_DISCOVERY_ACK 11   // wearable -> phone: mode change confirmed [ver u8][mode u8]
#define MSG_QUEUE_PURGE 12     // phone -> wearable: drop undelivered BACKUP queue [ver]['P']['G']
#define MSG_PARTNER_INFO 13    // phone -> wearable: [ver][nameLen][name<=12][dist LE16][flags bit0=dist valid]
#define MSG_INTERACTION_STATE 14  // phone -> wearable: compact phase + this user's code
#define MSG_INTERACTION_COMMAND 15 // wearable -> phone: idempotent user action
#define MSG_INTERACTION_ACK 16     // phone -> wearable: server accepted/rejected command
#define MSG_PET_STATE 17           // phone -> wearable: [ver][xp LE32][level u8][stage u8][cared u8][nameLen][name<=8]
#define MSG_PET_CARE_EVENT 18      // wearable -> phone: [ver][kind][date ASCII 10][nonce LE64]
#define MSG_GAME_STATE 19          // v2 raid: board1 -> board2 fight state (direct connection)
#define MSG_GAME_INPUT 20          // v2 raid: board2 -> board1 input
#define MSG_RAID_OUTCOME 21        // wearable -> phone: raid fight report
#define MSG_RAID_START 22          // phone -> w
#define MSG_QUIZ_STATE 23          // phone -> wearable: quiz progress [ver][active][idx][total]
#define MSG_QUIZ_ANSWER 24         // wearable -> phone: A-D press [ver][idx][choice]

struct PeerObservation {
  uint8_t device;         // peer DEVICE_ID
  uint16_t heartbeat;     // peer counter
  uint16_t token_hash;
  int8_t rssi;
  uint32_t at_ms;         // millis when observed
  bool fresh;             // seen within CM_PEER_RECENT_MS
};

// One relayed discovery result (bounded text for the small display).
struct DiscoveryResult {
  uint8_t shared_count;   // shared interest count
  uint8_t flags;          // bit0 = bluetooth source, bit1 = gps source
  char name[13];          // display name, NUL-terminated, <= 12 chars
};

struct SessionStateMsg {
  uint8_t active;         // 0 none, 1 active session
  uint8_t quest;          // 1 together, 2 explore, 3 heart
  uint8_t demo;
  uint32_t progress_ms;
  uint32_t target_ms;
  uint8_t partner_alias;
  uint16_t token_hash;    // active session token hash (binds peer evidence)
  char completion[24];    // completion event id ("" when none)
};

struct InteractionStateMsg {
  uint8_t phase;  // 0 none, 1 start PIN, 2 timing, 3 end PIN, 4 baseline, 5 choose, 6 round, 7 summary
  uint8_t stage;  // 1 start, 2 end
  char own_code[5];
  uint16_t own_code_version;
  uint16_t partner_code_version;
  bool own_confirmed;
  bool partner_confirmed;
  uint8_t round_index;
  bool active_user;
  uint8_t prompt_kind;  // 1 truth, 2 dare
  char prompt[25];
  uint8_t session_id[16];
};

class BleApp {
 public:
  bool begin();
  // Module-wedge recovery: hard-reset the BlueNRG and run the full init
  // again (same path as begin). Any raid state ends honestly (the fight is
  // lost, no outcome relayed); the phone relinks via normal TDD.
  void module_reinit();
  void tick();  // call at least every ~10 ms

  bool phoneConnected() const { return phone_connected_; }
  uint32_t adverts_received() const { return adverts_rx_; }

  // Latest peer observation state (updated by scan events).
  const PeerObservation& last_peer() const { return peer_; }
  uint32_t peer_count() const { return peer_count_; }
  // v2 pet: coarse partner proximity from the latest peer advert.
  // Buckets match the fork: >=-55 here, >=-75 nearby, else far.
  enum RssiBucket : uint8_t { RSSI_FAR = 0, RSSI_NEARBY = 1, RSSI_HERE = 2 };
  RssiBucket rssi_bucket() const {
    if (!peer_.fresh || peer_.rssi == 0) return RSSI_FAR;
    if (peer_.rssi >= -55) return RSSI_HERE;
    if (peer_.rssi >= -75) return RSSI_NEARBY;
    return RSSI_FAR;
  }

  // Active session token hash — set from SESSION_STATE messages; included in
  // advertised heartbeats so the partner's evidence binds to the session.
  void set_session_token_hash(uint16_t h) { session_token_hash_ = h; }
  uint16_t session_token_hash() const { return session_token_hash_; }

  // Send one framed message; payload is copied. Returns false when not
  // connected or the radio rejects the write.
  bool send_message(uint8_t type, const uint8_t* payload, uint16_t len);

  // Received messages are surfaced here (one at a time, non-blocking).
  bool poll_message(uint8_t* type, uint8_t* payload, uint16_t* len, uint16_t max_len);

  const SessionStateMsg& session() const { return session_; }
  const InteractionStateMsg& interaction() const { return interaction_; }
  const char* last_completion() const { return completion_; }

  // --- Nearby discovery (unpaired mode; never quest evidence) ---
  // General discovery runs only while enabled AND unpaired; pairing stops
  // it in favor of partner communication/quests (phone relays mode=0).
  bool discovery_on() const { return discovery_mode_ != 0; }
  uint16_t discovery_token() const { return discovery_token_; }
  bool discovery_synced() const { return discovery_synced_; }

  // Apply a mode change from the phone; true when the payload version was
  // accepted (unknown versions are rejected and logged, never applied).
  bool apply_discovery_mode(const uint8_t* payload, uint16_t len);
  bool apply_discovery_results(const uint8_t* payload, uint16_t len);

  // Pack observations newer than CM_DISC_OBS_MAX_MS into payload (max 10
  // entries per message); returns payload length, 0 when nothing to send.
  // Retained entries are NOT cleared: the phone stamps captured_at from
  // the reported age, so a retransmit yields the same server identity
  // (idempotent) while a new physical reception changes at_ms.
  uint8_t build_discovery_obs(uint8_t* payload, uint8_t max_len);
  uint8_t discovery_fresh_count() const;

  const DiscoveryResult* discovery_results() const { return disc_results_; }
  uint8_t discovery_results_count() const { return disc_results_count_; }

  // Matched-partner display data (relayed by the phone).
  const char* partner_name() const { return partner_name_; }
  uint16_t partner_dist_m() const { return partner_dist_m_; }
  bool partner_dist_valid() const { return partner_dist_valid_; }

  // Sessions state is updated by SESSION_STATE messages from the phone.
  void apply_session_message(const uint8_t* payload, uint16_t len);
  void apply_interaction_message(const uint8_t* payload, uint16_t len);

  // Called from the HCI event callback (bridging C callback to instance).
  // bdaddr = the peer's address (LSB-first, as in the connection-complete
  // event); needed to tell the RAID peer from the phone on the client.
  void note_connect(uint16_t handle, uint8_t role, const uint8_t* bdaddr);
  void note_disconnect(uint16_t handle, uint8_t reason = 0);
  // v2 raid mode (product): suspend the TDD scheduler, run the fight over a
  // direct connection, then resume. Triggered by the phone relay (raid
  // session active) or the bench serial command. existing_peer_handle: the
  // host's already-live link (relay-miss tolerance entry on the client).
  void raid_start(bool demo_hp, uint16_t existing_peer_handle = 0);
  // Boss HP selection for the live fight (the raid-start's demo byte; the
  // practice raid always passes true). Also rides the peer-advert raid flag
  // (1 normal / 2 demo) so the auto-armed host matches the client.
  bool raid_demo_hp() const { return raid_demo_hp_; }
  bool raid_active() const { return raid_mode_; }
  void raid_note_connected(uint16_t handle, uint8_t role);
  void raid_note_disc_resp(uint16_t attr_handle);
  void raid_note_proc_complete();
  void raid_note_disconnected(uint16_t handle);
  void raid_tick();
  void raid_outcome_acked(uint64_t nonce) {
    if (raid_outcome_pending_ && raid_outcome_nonce_ == nonce) {
      raid_outcome_ack_ = true;
    }
  }
  void note_advertisement(uint8_t* data, uint8_t len, int8_t rssi);
  void inject_message(uint8_t type, const uint8_t* payload, uint16_t len);
  void note_discovery_complete() { discovery_running_ = 0; }

 private:
  // Strict time-division radio scheduler (hardware-verified: this stack
  // rejects advertise+scan with 0x0C and scan-while-connected with 0x82,
  // so the radio alternates; the phone reconnects during ADVERTISING windows).
  enum class RadioState : uint8_t { LINKED, SCANNING, ADVERTISING };
  // v2 raid: dedicated radio mode — the phone link drops, board 1 (central)
  // connects to board 2, both exchange game traffic via write-without-
  // response to each other's UART TX characteristic (gate-proven transport).
  enum class RadioStateRaid : uint8_t { RAID_IDLE, RAID_CONNECTING, RAID_DISCOVERING, RAID_FIGHTING, RAID_REPORT, RAID_DONE };
#if CM_GAME_GATE
  // --- v2 raid gate experiment (bench builds only) ---
  // Everything here is PUBLIC: the HCI C callback (outside the class) and
  // the sketch call into it.
  enum class GatePhase : uint8_t { GATE_IDLE, GATE_CONNECTING, GATE_DISCOVERING, GATE_WRITING, GATE_DONE };
  GatePhase gate_phase_ = GatePhase::GATE_IDLE;
  uint16_t gate_conn_handle_ = 0;
  uint16_t gate_peer_tx_handle_ = 0;
  uint32_t gate_started_ms_ = 0;
  uint32_t gate_connected_ms_ = 0;
  uint32_t gate_last_write_ms_ = 0;
  uint32_t gate_writes_ = 0;
  uint32_t gate_retry_ms_ = 0;
  bool gate_advertising_started_ = false;  // initial state lies: force real entry

 public:
  uint32_t gate_rx_writes_ = 0;  // written from the HCI callback
  bool gate_diag_ecodes_ = true;  // print vendor event codes during discovery
  void gate_start();
  void gate_note_connected(uint16_t handle, uint8_t role);
  void gate_note_disc_resp(uint16_t attr_handle);
  void gate_note_proc_complete();
  void gate_note_disconnected();
  void gate_tick();
  uint32_t gate_writes() const { return gate_writes_; }
  uint32_t gate_rx_writes() const { return gate_rx_writes_; }
  uint32_t gate_connect_ms() const { return gate_connected_ms_; }
  uint32_t gate_started_ms() const { return gate_started_ms_; }
  const char* gate_phase_name() const;
#endif

  void start_advertising();
  void rotate_advertising_payload();
  void restart_discovery();
  void enter_scanning();
  void enter_advertising();

  bool phone_connected_ = false;
  volatile bool need_advertise_ = true;
  uint32_t last_discovery_ms_ = 0;
  uint16_t conn_handle_ = 0;
  RadioState radio_state_ = RadioState::ADVERTISING;
  // v2 raid state (runtime-gated; zero effect until raid_start()).
  bool raid_mode_ = false;
  bool raid_demo_hp_ = false;  // raid-start's demo byte: 20 HP vs 60 HP boss
  bool raid_adv_started_ = false;
  uint8_t raid_teardown_stage_ = 0;
  bool link_terminate_sent_ = false;
  uint32_t link_terminate_at_ms_ = 0;
  RadioStateRaid raid_phase_ = RadioStateRaid::RAID_IDLE;
  uint16_t raid_conn_handle_ = 0;
  uint16_t raid_peer_tx_handle_ = 0;
  uint32_t adverts_rx_ = 0;  // raw advertising reports seen while scanning
  uint32_t raid_started_ms_ = 0;
  uint32_t raid_connected_ms_ = 0;
  uint32_t raid_last_tx_ms_ = 0;
  uint32_t raid_retry_ms_ = 0;
  bool raid_outcome_sent_ = false;
  bool raid_outcome_pending_ = false;
  uint64_t raid_outcome_nonce_ = 0;
  bool raid_outcome_ack_ = false;
  uint8_t raid_outcome_value_ = 0;   // 1 win, 2 lose
  uint16_t raid_duration_s_ = 0;
  uint32_t raid_last_outcome_ms_ = 0;
  uint8_t raid_session_uuid_[16] = {0};
  uint32_t state_started_ms_ = 0;
  volatile uint8_t discovery_running_ = 0;

  PeerObservation peer_{};
  uint32_t peer_count_ = 0;
  uint16_t heartbeat_counter_ = 0;
  uint16_t session_token_hash_ = 0;

  // Simple inbound frame buffer for reassembled phone messages.
  uint8_t in_buf_[64];
  uint16_t in_len_ = 0;
  uint8_t in_type_ = 0;
  bool message_ready_ = false;

  SessionStateMsg session_{};
  InteractionStateMsg interaction_{};
  char completion_[24] = {0};

  // Discovery state (docs/DISCOVERY_PLAN.md). discovery_synced_ shows the
  // last mode change was confirmed end-to-end; false + disconnected means
  // the display should indicate pending synchronization.
  uint8_t discovery_mode_ = 0;
  uint16_t discovery_token_ = 0;
  bool discovery_synced_ = true;
  bool adv_alternate_ = false;  // alternate heartbeat/discovery payloads

  struct DiscObs {
    uint16_t token;
    uint32_t at_ms;
  };
  DiscObs disc_obs_[CM_DISC_BUFFER];
  uint8_t disc_obs_count_ = 0;

  DiscoveryResult disc_results_[CM_DISC_RESULTS_MAX];
  uint8_t disc_results_count_ = 0;

  char partner_name_[13] = {0};      // matched partner display name ("" = none)
  uint16_t partner_dist_m_ = 0;
  bool partner_dist_valid_ = false;

  void note_discovery_token(uint16_t token, uint32_t now);
};

extern BleApp g_ble;

// Build the 6-byte peer heartbeat manufacturer payload into out (>= 6 bytes).
void build_peer_adv(uint8_t* out, uint8_t device_id, uint16_t counter, uint16_t token_hash);

// 16-bit FNV-1a hash used for token fingerprints (not security, just binding).
uint16_t fnv16(const uint8_t* data, uint16_t len);
uint16_t fnv16_str(const char* s);
