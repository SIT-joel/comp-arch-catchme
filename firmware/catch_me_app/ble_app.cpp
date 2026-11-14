#include "ble_app.h"
#include "crash_diag.h"
#include "game_app.h"

// TEMP DIAGNOSTIC: peripheral-only radio (no central role, no TDD cycling
// while linked). Isolates whether multi-role init breaks notifications.
#define CM_DIAG_PERIPHERAL_ONLY 0
#define CM_DIAG_TRACE 0

#include <SPI.h>
#include <STBLE.h>

#include "records.h"

#define SerialLog SerialUSB

#ifndef BLE_DEBUG
#define BLE_DEBUG true
#endif

BleApp g_ble;

// ---------------- Nordic-style UART service (from STBLE example) ------------

#define COPY_UUID_128(uuid_struct, uuid_15, uuid_14, uuid_13, uuid_12, uuid_11, uuid_10, uuid_9, uuid_8, uuid_7, uuid_6, uuid_5, uuid_4, uuid_3, uuid_2, uuid_1, uuid_0) \
  do {\
    uuid_struct[0] = uuid_0; uuid_struct[1] = uuid_1; uuid_struct[2] = uuid_2; uuid_struct[3] = uuid_3; \
    uuid_struct[4] = uuid_4; uuid_struct[5] = uuid_5; uuid_struct[6] = uuid_6; uuid_struct[7] = uuid_7; \
    uuid_struct[8] = uuid_8; uuid_struct[9] = uuid_9; uuid_struct[10] = uuid_10; uuid_struct[11] = uuid_11; \
    uuid_struct[12] = uuid_12; uuid_struct[13] = uuid_13; uuid_struct[14] = uuid_14; uuid_struct[15] = uuid_15; \
  } while (0)

#define COPY_UART_SERVICE_UUID(uuid_struct) COPY_UUID_128(uuid_struct, 0x6E, 0x40, 0x00, 0x01, 0xB5, 0xA3, 0xF3, 0x93, 0xE0, 0xA9, 0xE5, 0x0E, 0x24, 0xDC, 0xCA, 0x9E)
#define COPY_UART_TX_CHAR_UUID(uuid_struct) COPY_UUID_128(uuid_struct, 0x6E, 0x40, 0x00, 0x02, 0xB5, 0xA3, 0xF3, 0x93, 0xE0, 0xA9, 0xE5, 0x0E, 0x24, 0xDC, 0xCA, 0x9E)
#define COPY_UART_RX_CHAR_UUID(uuid_struct) COPY_UUID_128(uuid_struct, 0x6E, 0x40, 0x00, 0x03, 0xB5, 0xA3, 0xF3, 0x93, 0xE0, 0xA9, 0xE5, 0x0E, 0x24, 0xDC, 0xCA, 0x9E)

static uint16_t uart_serv_handle, uart_tx_char_handle, uart_rx_char_handle;

static int add_uart_service() {
  tBleStatus ret;
  uint8_t uuid[16];

  COPY_UART_SERVICE_UUID(uuid);
  ret = aci_gatt_add_serv(UUID_TYPE_128, uuid, PRIMARY_SERVICE, 7, &uart_serv_handle);
  if (ret != BLE_STATUS_SUCCESS) return ret;

  COPY_UART_TX_CHAR_UUID(uuid);  // phone writes here
  ret = aci_gatt_add_char(uart_serv_handle, UUID_TYPE_128, uuid, 20,
                          CHAR_PROP_WRITE_WITHOUT_RESP, ATTR_PERMISSION_NONE,
                          GATT_NOTIFY_ATTRIBUTE_WRITE, 16, 1, &uart_tx_char_handle);
  if (ret != BLE_STATUS_SUCCESS) return ret;

  COPY_UART_RX_CHAR_UUID(uuid);  // device notifies here
  ret = aci_gatt_add_char(uart_serv_handle, UUID_TYPE_128, uuid, 20,
                          CHAR_PROP_NOTIFY, ATTR_PERMISSION_NONE, 0, 16, 1,
                          &uart_rx_char_handle);
  return ret;
}

// ---------------- framing ----------------------------------------------------
//
// Fragment (fits one 20-byte notification):
//   [0]=0xA5 [1]=version [2]=type [3]=msgId [4]=fragIdx [5]=fragCount
//   [6]=payloadLenThisFragment [7]=crc8(bytes 0..6 + payload)
//   [8..]=payload chunk (<= 12 bytes)
// Full message = ordered fragments; receiver reassembles by msgId.

#define FRAME_MAGIC 0xA5
#define FRAME_PROTO_VER 1
#define FRAME_HDR 8
#define FRAME_PAYLOAD_MAX 12

static uint8_t crc8_init(const uint8_t* d, uint8_t n, uint8_t crc) {
  for (uint8_t i = 0; i < n; i++) {
    crc ^= d[i];
    for (uint8_t b = 0; b < 8; b++) crc = (crc & 0x80) ? (uint8_t)((crc << 1) ^ 0x07) : (uint8_t)(crc << 1);
  }
  return crc;
}

static uint8_t crc8(const uint8_t* d, uint8_t n) { return crc8_init(d, n, 0x00); }

// Frame checksum input is bytes [0..6] followed by the payload chunk — the
// CRC byte at [7] itself is never part of the input (all senders compute it
// before writing [7]; including it on receive would never validate).
static uint8_t crc8_frame(const uint8_t* frame, uint8_t chunk) {
  uint8_t crc = crc8_init(frame, FRAME_HDR - 1, 0x00);
  return crc8_init(frame + FRAME_HDR, chunk, crc);
}

uint16_t fnv16(const uint8_t* data, uint16_t len) {
  uint32_t h = 2166136261u;
  for (uint16_t i = 0; i < len; i++) {
    h ^= data[i];
    h *= 16777619u;
  }
  return (uint16_t)(h ^ (h >> 16));
}

uint16_t fnv16_str(const char* s) { return fnv16((const uint8_t*)s, (uint16_t)strlen(s)); }

void build_peer_adv(uint8_t* out, uint8_t device_id, uint16_t counter, uint16_t token_hash) {
  out[0] = CM_PEER_MAGIC;
  out[1] = device_id;
  out[2] = (uint8_t)(counter & 0xFF);
  out[3] = (uint8_t)(counter >> 8);
  out[4] = (uint8_t)(token_hash & 0xFF);
  out[5] = (uint8_t)(token_hash >> 8);
}

// Discovery advertisement: [0xC6][version][token LE16]. No PII; opaque id
// provisioned through the authenticated phone link.
void build_discovery_adv(uint8_t* out, uint16_t token) {
  out[0] = CM_DISC_MAGIC;
  out[1] = CM_DISC_VERSION;
  out[2] = (uint8_t)(token & 0xFF);
  out[3] = (uint8_t)(token >> 8);
}

// Inbound reassembly state (used by feed_fragment and disconnect paths).
static uint8_t rx_msg_buf[64];
static uint16_t rx_msg_len = 0;
static uint8_t rx_msg_frags_left = 0;

// ---------------- BleApp ------------------------------------------------------

bool BleApp::begin() {
  int ret;
  // Hold the flash shield's CS (D5) high before any SPI traffic: a floating
  // flash CS lets the W25Q drive shared MISO and breaks BLE transactions
  // (root-caused on the real board, see firmware/probes/01b_ble_spi_diag).
  pinMode(5, OUTPUT);
  digitalWrite(5, HIGH);

  HCI_Init();
  BNRG_SPI_Init();
  BlueNRG_RST();

#ifdef CM_DIAG_BDADDR_LSB
  // Wedge-triage diagnostic: advertise under a different static address so
  // armed controller-level reconnects (targeting the normal address) can
  // never reach this board. Decouples "assaulted by pending reconnects"
  // from "module is hardware-unstable".
  uint8_t bdaddr[] = {0x12, 0x34, 0x00, 0xE1, 0x80, CM_DIAG_BDADDR_LSB};
#else
  // Address scheme: the last byte's bit pattern MATTERS on this module —
  // 0x02 (the original D2 address) made the module scan-DEAF (zero adv
  // reports while scanning, verified by A/B flash + adv_rx counter, 13 Nov).
  // 0x01 and 0x03 both scan fine. Board 1 keeps 01; board 2 uses 03.
  // RAID PEER ADDRESSES reference these — keep ble_app.cpp in sync:
  //   board 1 = 01:80:E1:00:34:12, board 2 = 03:80:E1:00:34:12.
#if DEVICE_ID == 2
  uint8_t bdaddr[] = {0x12, 0x34, 0x00, 0xE1, 0x80, 0x03};
#else
  uint8_t bdaddr[] = {0x12, 0x34, 0x00, 0xE1, 0x80, 0x01};
#endif
#endif
  ret = aci_hal_write_config_data(CONFIG_DATA_PUBADDR_OFFSET, CONFIG_DATA_PUBADDR_LEN, bdaddr);
  if (ret) return false;
  ret = aci_gatt_init();
  if (ret) return false;

  uint16_t service_handle, dev_name_char_handle, appearance_char_handle;
#if CM_DIAG_PERIPHERAL_ONLY
  ret = aci_gap_init_IDB05A1(GAP_PERIPHERAL_ROLE_IDB05A1,
                             0, 0x10, &service_handle, &dev_name_char_handle,
                             &appearance_char_handle);
#else
  ret = aci_gap_init_IDB05A1(GAP_PERIPHERAL_ROLE_IDB05A1 | GAP_CENTRAL_ROLE_IDB05A1,
                             0, 0x10, &service_handle, &dev_name_char_handle,
                             &appearance_char_handle);
#endif
  if (ret) return false;

  char name[12];
  snprintf(name, sizeof(name), "CATCHME-%d", DEVICE_ID);
  aci_gatt_update_char_value(service_handle, dev_name_char_handle, 0,
                             strlen(name), (uint8_t*)name);

  ret = add_uart_service();
  if (ret != BLE_STATUS_SUCCESS) return false;

  aci_hal_set_tx_power_level(1, 3);
  hci_le_set_scan_resp_data(0, NULL);
  return true;
}

void BleApp::rotate_advertising_payload() {
  heartbeat_counter_++;  // rotating payload: required for scanner visibility
  // Payload rotation ONLY (no set_discoverable): safe to call in a tight
  // loop — this is the same call the TDD scheduler repeats every cycle.
  // ONE manufacturer field per advertisement, payload alternating per
  // advertising window while discovery is on: the quest heartbeat (C5) or
  // the discovery token (C6). A dual-field advert (both mfr fields at once)
  // was tried and REJECTED by Android 12 stacks — the G970F delivered
  // neither board (30 Oct); single-field adverts deliver on all tested
  // phones. The heartbeats keep full pairing duty; discovery rides the
  // alternating windows.
  bool discovery_window = discovery_mode_ && discovery_token_ != 0 &&
                          ((heartbeat_counter_ & 1) != 0);
  uint8_t advData[31];
  uint8_t i = 0;
  advData[i++] = 0x02; advData[i++] = 0x01; advData[i++] = 0x06;
  advData[i++] = (uint8_t)(1 + 2 + (discovery_window ? CM_DISC_ADV_LEN : CM_PEER_ADV_LEN));
  advData[i++] = 0xFF;
  advData[i++] = 0x30; advData[i++] = 0x00;  // ST company id (LE)
  if (discovery_window) {
    build_discovery_adv(advData + i, discovery_token_);
    i += CM_DISC_ADV_LEN;
  } else {
    build_peer_adv(advData + i, DEVICE_ID, heartbeat_counter_, session_token_hash_);
    i += CM_PEER_ADV_LEN;
  }
  tBleStatus ret = aci_gap_update_adv_data(i, advData);
  if (ret != BLE_STATUS_SUCCESS) {
    SerialLog.print("ble: update_adv_data fail 0x");
    SerialLog.println(ret, HEX);
  } else {
    SerialLog.print("ble: adv on cnt=");
    SerialLog.print(heartbeat_counter_);
    SerialLog.println(discovery_window ? " disc" : "");
  }
}

void BleApp::start_advertising() {
  // Library convention (verified on hardware): aci_gap_set_discoverable takes
  // a LOCAL NAME and builds the AD itself; the payload then goes through
  // aci_gap_update_adv_data in standard [len][type][data] format (rotate_-
  // advertising_payload). set_discoverable is the wedge-sensitive call —
  // call it once per phase entry, never in a loop (gate lesson, 6 Nov).
  char name[12];
  snprintf(name, sizeof(name), "CATCHME-%d", DEVICE_ID);
  uint8_t nameLen = strlen(name);
  // Name in the scan response (space budget); active scanners still see it.
  uint8_t nameAd[11];
  nameAd[0] = (uint8_t)(1 + nameLen);
  nameAd[1] = AD_TYPE_COMPLETE_LOCAL_NAME;
  memcpy(nameAd + 2, name, nameLen);
  hci_le_set_scan_resp_data((uint8_t)(1 + nameLen), nameAd);
  tBleStatus ret = aci_gap_set_discoverable(
      ADV_IND, (CM_ADV_INTERVAL_MIN_MS * 1000) / 625, (CM_ADV_INTERVAL_MAX_MS * 1000) / 625,
      PUBLIC_ADDR, NO_WHITE_LIST_USE, 0, NULL, 0, NULL, 0, 0);
  if (ret != BLE_STATUS_SUCCESS) {
    SerialLog.print("ble: set_discoverable fail 0x");
    SerialLog.println(ret, HEX);
    return;
  }
  rotate_advertising_payload();
}

void BleApp::restart_discovery() {
  tBleStatus ret = aci_gap_start_general_discovery_proc(CM_SCAN_INTERVAL, CM_SCAN_WINDOW,
                                                        PUBLIC_ADDR, 0);
  if (ret != BLE_STATUS_SUCCESS) {
    SerialLog.print("ble: discovery fail 0x");
    SerialLog.println(ret, HEX);
  } else {
    discovery_running_ = 1;
    SerialLog.println("ble: discovery started");
  }
  last_discovery_ms_ = millis();
}

void BleApp::note_advertisement(uint8_t* data, uint8_t len, int8_t rssi) {
  adverts_rx_++;
  int i = 0;
  while (i + 1 < len) {
    uint8_t field_len = data[i];
    if (field_len == 0 || i + 1 + field_len > len) break;
    // Manufacturer field layout: [len][0xFF][company LE 2B][payload...]
    // — the company id precedes our magic in both message families.
    if (data[i + 1] == 0xFF && data[i + 2] == 0x30 && data[i + 3] == 0x00) {
      if (field_len >= 2 + 1 + CM_PEER_ADV_LEN && data[i + 4] == CM_PEER_MAGIC) {
        // Session-bound quest heartbeat (device ids 1-2 only; this IS
        // quest evidence and keeps its original restriction).
        uint8_t device = data[i + 5];
        uint16_t counter = data[i + 6] | ((uint16_t)data[i + 7] << 8);
        uint16_t token_hash = data[i + 8] | ((uint16_t)data[i + 9] << 8);
        if (device != DEVICE_ID && device >= 1 && device <= 2) {
          uint32_t now = millis();
          // Dedupe: the same counter is not new evidence (docs/INTERFACES.md).
          if (!(peer_.device == device && peer_.heartbeat == counter)) {
            peer_.device = device;
            peer_.heartbeat = counter;
            peer_.token_hash = token_hash;
            peer_.rssi = rssi;
            peer_.at_ms = now;
            peer_.fresh = true;
            peer_count_++;
          } else {
            peer_.at_ms = now;  // same heartbeat still observed; refresh age
            peer_.rssi = rssi;
          }
        }
        // fall through: the same advertisement also carries the discovery
        // field when discovery mode is on — parse it too.
      }
      if (field_len >= 2 + 1 + CM_DISC_ADV_LEN && data[i + 4] == CM_DISC_MAGIC) {
        // Versioned discovery advertisement: [0xC6][ver][token LE16].
        // Unknown versions are ignored (never misdecoded); discovery
        // observations are collected only while discovery mode is on.
        if (data[i + 5] == CM_DISC_VERSION && discovery_mode_) {
          uint16_t token = data[i + 6] | ((uint16_t)data[i + 7] << 8);
          if (token != 0 && token != discovery_token_) {
            note_discovery_token(token, millis());
          }
        }
        return;
      }
    }
    i += 1 + field_len;
  }
}

void BleApp::note_discovery_token(uint16_t token, uint32_t now) {
  for (uint8_t k = 0; k < disc_obs_count_; k++) {
    if (disc_obs_[k].token == token) {
      disc_obs_[k].at_ms = now;  // new physical reception refreshes presence
      return;
    }
  }
  if (disc_obs_count_ < CM_DISC_BUFFER) {
    disc_obs_[disc_obs_count_].token = token;
    disc_obs_[disc_obs_count_].at_ms = now;
    disc_obs_count_++;
  } else {
    // Bounded: replace the oldest entry when full (docs/DISCOVERY_PLAN.md).
    uint8_t oldest = 0;
    for (uint8_t k = 1; k < CM_DISC_BUFFER; k++) {
      if (disc_obs_[k].at_ms < disc_obs_[oldest].at_ms) oldest = k;
    }
    disc_obs_[oldest].token = token;
    disc_obs_[oldest].at_ms = now;
  }
}

uint8_t BleApp::discovery_fresh_count() const {
  uint32_t now = millis();
  uint8_t n = 0;
  for (uint8_t k = 0; k < disc_obs_count_; k++) {
    if (now - disc_obs_[k].at_ms <= CM_DISC_OBS_MAX_MS) n++;
  }
  return n;
}

uint8_t BleApp::build_discovery_obs(uint8_t* payload, uint8_t max_len) {
  // [ver u8][n u8] then n * ([token LE16][age_ms LE16]); at most 10 entries.
  uint32_t now = millis();
  uint8_t n = 0;
  uint8_t out = 2;
  if (max_len < 2) return 0;
  payload[0] = CM_DISC_VERSION;
  for (uint8_t k = 0; k < disc_obs_count_ && n < 10; k++) {
    uint32_t age = now - disc_obs_[k].at_ms;
    if (age > CM_DISC_OBS_MAX_MS) continue;  // expired: cannot revive
    if (out + 4 > max_len) break;
    payload[out++] = (uint8_t)(disc_obs_[k].token & 0xFF);
    payload[out++] = (uint8_t)(disc_obs_[k].token >> 8);
    payload[out++] = (uint8_t)(age & 0xFF);
    payload[out++] = (uint8_t)((age >> 8) & 0xFF);
    n++;
  }
  payload[1] = n;
  return n ? out : 0;
}

bool BleApp::apply_discovery_mode(const uint8_t* p, uint16_t len) {
  // [ver u8][mode u8][token LE16]; unknown version rejected explicitly.
  if (len < 4) {
    SerialLog.println("ble: short DISCOVERY_MODE");
    return false;
  }
  if (p[0] != CM_DISC_VERSION) {
    SerialLog.print("ble: DISCOVERY_MODE unknown version ");
    SerialLog.println(p[0]);
    return false;
  }
  uint8_t new_mode = p[1] ? 1 : 0;
  uint16_t new_token = p[2] | ((uint16_t)p[3] << 8);
  // The phone re-sends the mode until its ACK lands, so redundant applies
  // are NORMAL — wiping the observation buffer here erased fresh C6 catches
  // every ~3 s (root cause of missing discovery uploads, 29 Oct). Wipe only
  // on a real transition: mode off, or a different provisioned token.
  if (new_mode == 0 || new_token != discovery_token_) {
    disc_obs_count_ = 0;
  }
  discovery_mode_ = new_mode;
  discovery_token_ = new_token;
  discovery_synced_ = true;
  SerialLog.print("ble: discovery mode=");
  SerialLog.print(discovery_mode_);
  SerialLog.print(" token=");
  SerialLog.println(discovery_token_);
  return true;
}

bool BleApp::apply_discovery_results(const uint8_t* p, uint16_t len) {
  // [ver u8][n u8 (<=3)] then n * ([shared u8][flags u8][len u8][name...]).
  if (len < 2) return false;
  if (p[0] != CM_DISC_VERSION) {
    SerialLog.print("ble: DISCOVERY_RESULTS unknown version ");
    SerialLog.println(p[0]);
    return false;
  }
  uint8_t n = p[1];
  if (n > CM_DISC_RESULTS_MAX) return false;
  uint16_t off = 2;
  for (uint8_t k = 0; k < n; k++) {
    if (off + 3 > len) return false;
    uint8_t shared = p[off++];
    uint8_t flags = p[off++];
    uint8_t name_len = p[off++];
    if (name_len > 12 || off + name_len > len) return false;
    disc_results_[k].shared_count = shared;
    disc_results_[k].flags = flags;
    memcpy(disc_results_[k].name, p + off, name_len);
    disc_results_[k].name[name_len] = 0;
    off += name_len;
  }
  disc_results_count_ = n;
  SerialLog.print("ble: discovery results n=");
  SerialLog.print(n);
  if (n > 0) {
    SerialLog.print(" first=");
    SerialLog.print(disc_results_[0].name);
    SerialLog.print(" shared=");
    SerialLog.println(disc_results_[0].shared_count);
  } else {
    SerialLog.println();
  }
  return true;
}

void BleApp::note_connect(uint16_t handle, uint8_t role, const uint8_t* bdaddr) {
#if DEVICE_ID != 1
  // On the CLIENT, both the phone AND the raid host arrive as role==1 (we
  // are peripheral in both cases) — discriminate by the static peer address
  // (board 1 = 01:80:E1:00:34:12, LSB-first bytes below). This also gives
  // relay-miss tolerance: the host connecting IS the raid trigger for us.
  static const uint8_t kRaidPeerAddr[6] = {0x12, 0x34, 0x00, 0xE1, 0x80, 0x01};
  if (role == 1 && bdaddr && memcmp(bdaddr, kRaidPeerAddr, 6) == 0) {
    if (!raid_mode_) raid_start(session_.demo, handle);
    else raid_conn_handle_ = handle;
    raid_note_connected(handle, role);
    return;
  }
#endif
  if (role == 1) {  // we are peripheral: the phone connected
    phone_connected_ = true;
    conn_handle_ = handle;
    radio_state_ = RadioState::LINKED;
    state_started_ms_ = millis();
    cdiag::bc(cdiag::B_PHONE_UP, role, handle);
    link_terminate_sent_ = false;  // fresh link: re-arm the drop timer
    SerialLog.println("ble: phone connected");
#if CM_GAME_GATE
  } else {
    // Gate experiment: WE are the central connecting to the peer board.
    g_ble.gate_note_connected(handle, role);
  }
#else
  } else if (raid_mode_) {
    // v2 raid: WE are the central connecting to the peer board.
    raid_note_connected(handle, role);
  } else {
    SerialLog.println("ble: central connection (unexpected in this design)");
  }
#endif
}

void BleApp::note_disconnect(uint16_t handle, uint8_t reason) {
  cdiag::bc(cdiag::B_DISC, (uint8_t)(handle & 0xFF), reason);
  SerialLog.print("ble: disconnected handle=");
  SerialLog.print(handle);
  SerialLog.print(" reason=0x");
  SerialLog.println(reason, HEX);
#if CM_GAME_GATE
  g_ble.gate_note_disconnected();
#endif
  // Only the RAID PEER's disconnect affects the fight; a phone bounce
  // mid-fight must not abort it (the phone is not needed until the
  // outcome relay after the fight).
  if (raid_mode_ && handle == raid_conn_handle_) raid_note_disconnected(handle);
  // Only the actual phone link's disconnect clears the phone state — in
  // raid mode the PEER terminate used to wrongly clear phone_connected_,
  // stalling the outcome relay until the phone's next reconnect.
  if (handle == conn_handle_) {
    phone_connected_ = false;
    conn_handle_ = 0;
  }
  rx_msg_frags_left = 0;
  rx_msg_len = 0;
  if (radio_state_ == RadioState::LINKED && !raid_mode_) {
    enter_scanning();  // scheduled TDD disconnect: evidence window next
  }
}

void BleApp::enter_scanning() {
  radio_state_ = RadioState::SCANNING;
  state_started_ms_ = millis();
  discovery_running_ = 0;
  cdiag::bc(cdiag::B_SCAN, 0, 0);
  SerialLog.println("ble: -> SCANNING");
}

void BleApp::enter_advertising() {
  radio_state_ = RadioState::ADVERTISING;
  state_started_ms_ = millis();
  cdiag::bc(cdiag::B_ADV, 0, 0);
  SerialLog.println("ble: -> ADVERTISING");
}

void BleApp::inject_message(uint8_t type, const uint8_t* payload, uint16_t len) {
  cdiag::bc(cdiag::B_MSG, type, len);
  if (type == MSG_SESSION_STATE) {
    apply_session_message(payload, len);
    return;
  }
  if (type == MSG_INTERACTION_STATE) {
    // Diagnostics: why did the 58-byte interaction relay fail this time?
    SerialLog.print("ble: INTERACTION len=");
    SerialLog.print(len);
    SerialLog.print(" ver=");
    SerialLog.println(len >= 1 ? payload[0] : -1);
  }
  if (type == MSG_PARTNER_INFO) {
    // [ver][nameLen][name<=12][dist LE16][flags bit0=dist valid]
    if (len < 3 || payload[0] != CM_DISC_VERSION) {
      SerialLog.println("ble: bad PARTNER_INFO");
      return;
    }
    uint8_t name_len = payload[1];
    if (name_len > 12 || len < (uint16_t)(2 + name_len + 3)) {
      SerialLog.println("ble: bad PARTNER_INFO len");
      return;
    }
    memcpy(partner_name_, payload + 2, name_len);
    partner_name_[name_len] = 0;
    partner_dist_m_ = payload[2 + name_len] | ((uint16_t)payload[3 + name_len] << 8);
    partner_dist_valid_ = payload[4 + name_len] & 0x01;
    SerialLog.print("ble: partner=");
    SerialLog.print(partner_name_);
    SerialLog.print(" dist=");
    SerialLog.println(partner_dist_valid_ ? (long)partner_dist_m_ : -1L);
    return;
  }
  if (type == MSG_INTERACTION_STATE) {
    apply_interaction_message(payload, len);
    return;
  }
  if (type == MSG_DISCOVERY_MODE) {
    if (apply_discovery_mode(payload, len)) {
      // Confirm receipt end-to-end: [ver u8][mode u8].
      uint8_t ack[2] = {CM_DISC_VERSION, discovery_mode_};
      send_message(MSG_DISCOVERY_ACK, ack, sizeof(ack));
    }
    return;
  }
  if (type == MSG_DISCOVERY_RESULTS) {
    apply_discovery_results(payload, len);
    return;
  }
  if (len <= sizeof(in_buf_)) {
    memcpy(in_buf_, payload, len);
    in_len_ = len;
    in_type_ = type;
    message_ready_ = true;
  }
}

void BleApp::apply_interaction_message(const uint8_t* p, uint16_t len) {
  // Version 1 compact layout is documented in docs/INTERFACES.md.
  if (len < 58 || p[0] != 1) {
    SerialLog.println("ble: bad INTERACTION_STATE");
    return;
  }
  interaction_.phase = p[1];
  interaction_.stage = p[3];
  memcpy(interaction_.own_code, p + 4, 4);
  interaction_.own_code[4] = 0;
  interaction_.own_code_version = p[8] | ((uint16_t)p[9] << 8);
  interaction_.partner_code_version = p[10] | ((uint16_t)p[11] << 8);
  interaction_.own_confirmed = p[12] != 0;
  interaction_.partner_confirmed = p[13] != 0;
  interaction_.round_index = p[14];
  interaction_.active_user = p[15] != 0;
  interaction_.prompt_kind = p[16];
  uint8_t prompt_len = p[17] > 24 ? 24 : p[17];
  memcpy(interaction_.prompt, p + 18, prompt_len);
  interaction_.prompt[prompt_len] = 0;
  memcpy(interaction_.session_id, p + 42, 16);
}

void BleApp::apply_session_message(const uint8_t* p, uint16_t len) {
  // Layout: active u8, quest u8, demo u8, progress u32, target u32,
  // partner_alias u8, token_hash u16, completion char[24].
  if (len < 17 + 24) {
    SerialLog.println("ble: short SESSION_STATE");
    return;
  }
  session_.active = p[0];
  session_.quest = p[1];
  session_.demo = p[2];
  memcpy(&session_.progress_ms, p + 3, 4);
  memcpy(&session_.target_ms, p + 7, 4);
  session_.partner_alias = p[11];
  session_.token_hash = p[12] | ((uint16_t)p[13] << 8);
  uint8_t fresh_completion = p[14];
  memcpy(completion_, p + 17, 23);
  completion_[23] = 0;
  // Bind advertised heartbeats to the active session token.
  set_session_token_hash(session_.active ? session_.token_hash : 0);
  SerialLog.print("ble: session active=");
  SerialLog.print(session_.active);
  SerialLog.print(" completion_flag=");
  SerialLog.println(fresh_completion);
}

bool BleApp::send_message(uint8_t type, const uint8_t* payload, uint16_t len) {
  cdiag::bc(cdiag::B_SEND, type, len);
  if (!phone_connected_) return false;
  uint8_t frag_count = (uint8_t)((len + FRAME_PAYLOAD_MAX - 1) / FRAME_PAYLOAD_MAX);
  if (frag_count == 0) frag_count = 1;
  if (frag_count > 15) return false;  // bounded messages only
  static uint8_t msg_id = 0;
  msg_id++;

  uint8_t frame[20];
  for (uint8_t frag = 0; frag < frag_count; frag++) {
    uint16_t off = (uint16_t)frag * FRAME_PAYLOAD_MAX;
    uint8_t chunk = (uint8_t)(len - off > FRAME_PAYLOAD_MAX ? FRAME_PAYLOAD_MAX : len - off);
    frame[0] = FRAME_MAGIC;
    frame[1] = FRAME_PROTO_VER;
    frame[2] = type;
    frame[3] = msg_id;
    frame[4] = frag;
    frame[5] = frag_count;
    frame[6] = chunk;
    memcpy(frame + FRAME_HDR, payload + off, chunk);
    frame[7] = crc8_frame(frame, chunk);
    tBleStatus ret = aci_gatt_update_char_value(uart_serv_handle, uart_rx_char_handle,
                                                0, (uint8_t)(FRAME_HDR + chunk), frame);
    if (ret != BLE_STATUS_SUCCESS) {
      SerialLog.print("ble: notify fail 0x");
      SerialLog.println(ret, HEX);
      return false;
    }
    delay(12);  // give the radio room between notifications
  }
  return true;
}

// Inbound reassembly (single message at a time — sufficient at 1 Hz cadence)
// lives near the top with feed_fragment; see rx_msg_* above.

void BleApp::module_reinit() {
  cdiag::bc(cdiag::B_REINIT, 0, 0);
  // The module is gone (IRQ stuck): every radio state is void. End any
  // raid honestly — the fight is LOST, never fabricated as anything else,
  // and no outcome is relayed (the boards' phones only relay outcomes the
  // boards actually reported; a wedged module reports none).
  link_terminate_sent_ = false;
  raid_mode_ = false;
  raid_phase_ = RadioStateRaid::RAID_DONE;
  raid_conn_handle_ = 0;
  raid_peer_tx_handle_ = 0;
  raid_outcome_pending_ = false;
  phone_connected_ = false;
  conn_handle_ = 0;
  radio_state_ = RadioState::SCANNING;
  state_started_ms_ = millis();
  peer_.device = 0;
  g_game.abort_lost();
  if (!begin()) {
    SerialLog.println("ble: module re-init FAILED (radio down this boot)");
  } else {
    SerialLog.println("ble: module re-init OK; TDD resumes");
  }
}

void BleApp::tick() {
  HCI_Process();
  // Module-wedge recovery: a wedged module holds its IRQ high AND every
  // read fails (garbage). A busy-but-healthy module ALSO holds IRQ high for
  // seconds at a time (advert-report storms during scanning read as valid
  // packets) — the first recovery build false-fired on exactly that and
  // re-init-looped itself into watchdog resets (verified live). So fire only
  // when the IRQ is stuck continuously AND no read succeeds for 2 s.
  static uint32_t wedge_ms_start = 0;
  static uint32_t wedge_last_reads = 0;
  const uint32_t now_ms = millis();
  const bool healthy_reads =
      hci_irq_drain_reads != wedge_last_reads || !hci_irq_stuck;
  if (healthy_reads) {
    wedge_ms_start = 0;
    wedge_last_reads = hci_irq_drain_reads;
  } else if (!wedge_ms_start) {
    wedge_ms_start = now_ms;
  }
  if (wedge_ms_start && now_ms - wedge_ms_start >= 2000) {
    SerialLog.println("ble: module wedged (IRQ stuck, no valid reads 2s); hard reset + re-init");
    wedge_ms_start = 0;
    cdiag::bc(cdiag::B_REINIT, 1, 0);  // a=1: wedge-recovery path
    module_reinit();
    return;
  }
  { /* throttled liveness breadcrumb with the TDD phase (500 ms) */
    static uint32_t last_bc_tick_ms = 0;
    if (now_ms - last_bc_tick_ms >= 500) {
      last_bc_tick_ms = now_ms;
      cdiag::bc(cdiag::B_TICK, (uint8_t)radio_state_, 0);
    }
  }
  { /* Deaf-module recovery (14 Nov): the receiver can die WITHOUT any wedge
     * signature — adv_rx frozen, connections/TX alive, IRQ quiet — observed
     * after the raid teardown attempts (board 2: 8+ min with zero adverts,
     * every GATT notification lost). The wedge detector (IRQ stuck + no
     * reads) never fires for this state. If adverts stopped advancing across
     * three consecutive 10 s checks AFTER the module had been receiving,
     * hard-reset the module once per episode (a lone board whose peer left
     * gets exactly one harmless re-init, not a loop). */
    static uint32_t last_deaf_check_ms = 0;
    static uint32_t deaf_check_adv_rx = 0;
    static uint8_t deaf_checks = 0;
    static bool deaf_reinit_done = false;
    if (now_ms - last_deaf_check_ms >= 10000UL && !raid_mode_) {
      // raid_mode_ exempt: the raid CLIENT intentionally stops scanning
      // (adv_rx frozen while advertising for the host — not a deaf module).
      if (last_deaf_check_ms != 0) {
        if (adverts_rx_ != deaf_check_adv_rx) {
          deaf_check_adv_rx = adverts_rx_;
          deaf_checks = 0;
          deaf_reinit_done = false;
        } else if (adverts_rx_ > 0 && !deaf_reinit_done) {
          if (++deaf_checks >= 3) {
            SerialLog.println("ble: module deaf (no adverts 30s+); hard reset + re-init");
            deaf_checks = 0;
            deaf_reinit_done = true;
            cdiag::bc(cdiag::B_REINIT, 2, 0);  // a=2: deaf-recovery path
            module_reinit();
            return;
          }
        }
      }
      last_deaf_check_ms = now_ms;
    }
  }
  { /* Event-deaf recovery (14 Nov, third failure mode): the module accepts
     * the phone's connection and even scans, but delivers NO HCI events —
     * every GATT write from the phone is silently lost (board 2: the
     * practice raid-start never arrived while adverts kept flowing). A
     * linked phone ALWAYS generates events (its writes arrive ~1-2 s apart),
     * so: phone connected AND the HCI read counter frozen for 15 s = the
     * event path is dead. Hard-reset once per episode. */
    static uint32_t evt_check_ms = 0;
    static uint32_t evt_check_reads = 0;
    static bool evt_reinit_done = false;
    if (now_ms - evt_check_ms >= 15000UL) {
      if (evt_check_ms != 0 && phone_connected_) {
        if (hci_irq_drain_reads == evt_check_reads) {
          if (!evt_reinit_done) {
            SerialLog.println("ble: module event-deaf (phone linked, no HCI reads 15s); re-init");
            evt_reinit_done = true;
            cdiag::bc(cdiag::B_REINIT, 3, 0);  // a=3: event-deaf path
            module_reinit();
            return;
          }
        } else {
          evt_reinit_done = false;
        }
      }
      evt_check_reads = hci_irq_drain_reads;
      evt_check_ms = now_ms;
    }
  }
#if CM_GAME_GATE
  gate_tick();
  return;  // the gate owns the radio; the TDD scheduler is suspended
#endif
  if (raid_mode_) {
    raid_tick();
    return;  // the raid owns the radio; the TDD scheduler is suspended
  }
  uint32_t now = millis();
  if (peer_.device != 0) {
    peer_.fresh = (now - peer_.at_ms) <= CM_PEER_RECENT_MS;
  }

  if (need_advertise_) {
    need_advertise_ = false;
    enter_advertising();
    start_advertising();
    return;
  }

#if CM_DIAG_PERIPHERAL_ONLY
  // Static radio for the notify diagnostic: advertise until connected, then
  // hold the link (no cycling, no discovery procedures).
  if (radio_state_ == RadioState::ADVERTISING && !phone_connected_ &&
      now - state_started_ms_ >= 10000) {
    // Re-advertise periodically so scanners can find us (adv data refresh).
    start_advertising();
    state_started_ms_ = now;
  }
  return;
#endif

  switch (radio_state_) {
    case RadioState::LINKED:
      // Connection held; scanning is rejected while linked (0x82, verified on
      // hardware). After the link window, drop the link so peer evidence can
      // resume; the phone reconnects during the next ADVERTISING window.
      // PHANTOM-LINK deadlock (verified live 12 Nov): when the phone's drop
      // is lost mid-transition the terminate targets a dead handle and fails
      // silently every loop — LINKED forever, no advertise, no reconnects.
      // Terminate once, then escalate to a full module re-init.
#if !CM_DIAG_PERIPHERAL_ONLY
      if (now - state_started_ms_ >= CM_TDD_LINKED_MS) {
        if (!link_terminate_sent_) {
          aci_gap_terminate(conn_handle_, 0x13);  // 0x13 = remote user terminated
          link_terminate_sent_ = true;
          link_terminate_at_ms_ = now;
        } else if (now - link_terminate_at_ms_ >= 2000) {
          SerialLog.println("ble: phantom link (terminate ignored); re-init");
          module_reinit();
          return;
        }
      }
#endif
      break;
    case RadioState::SCANNING:
      if (!discovery_running_ || now - state_started_ms_ >= CM_TDD_SCAN_MS) {
        aci_gap_terminate_gap_procedure(GAP_GENERAL_DISCOVERY_PROC);
        discovery_running_ = 0;
        enter_advertising();
        start_advertising();
      }
      break;
    case RadioState::ADVERTISING:
      if (now - state_started_ms_ >= CM_TDD_ADV_MS) {
        tBleStatus r = aci_gap_set_non_discoverable();
        if (r != BLE_STATUS_SUCCESS) {
          SerialLog.print("ble: non_disc fail 0x");
          SerialLog.println(r, HEX);
        }
        enter_scanning();
        restart_discovery();
      }
      break;
  }
}

bool BleApp::poll_message(uint8_t* type, uint8_t* payload, uint16_t* len, uint16_t max_len) {
  if (!message_ready_) return false;
  uint16_t n = in_len_ < max_len ? in_len_ : max_len;
  memcpy(payload, in_buf_, n);
  *type = in_type_;
  *len = n;
  message_ready_ = false;
  in_len_ = 0;
  return true;
}

// Feed raw fragment bytes (from GATT writes) into the reassembler.
static void feed_fragment(const uint8_t* frame, uint8_t frame_len) {
  // Zero-payload frames (HELLO) are exactly FRAME_HDR bytes — valid.
  if (frame_len < FRAME_HDR) return;
  if (frame[0] != FRAME_MAGIC || frame[1] != FRAME_PROTO_VER) return;
  uint8_t chunk = frame[6];
  if (frame_len < FRAME_HDR + chunk) return;
  uint8_t expect_crc = crc8_frame(frame, chunk);
  if (expect_crc != frame[7]) {
    SerialLog.println("ble: frag crc mismatch");
    rx_msg_frags_left = 0;
    rx_msg_len = 0;
    return;
  }
  if (frame[4] == 0) {  // first fragment resets the buffer
    rx_msg_len = 0;
    rx_msg_frags_left = frame[5];
  }
  if (rx_msg_len + chunk > sizeof(rx_msg_buf)) {
    rx_msg_frags_left = 0;
    return;
  }
  memcpy(rx_msg_buf + rx_msg_len, frame + FRAME_HDR, chunk);
  rx_msg_len += chunk;
  if (rx_msg_frags_left > 0) rx_msg_frags_left--;
  if (rx_msg_frags_left == 0) {
    g_ble.inject_message(frame[2], rx_msg_buf, rx_msg_len);
  }
}

// Called by feed_fragment with a complete message (bridges into the app).

// ---------------- HCI event callback -----------------------------------------

extern "C" void HCI_Event_CB(void* pckt) {
  hci_uart_pckt* hci_pckt = (hci_uart_pckt*)pckt;
  hci_event_pckt* event_pckt = (hci_event_pckt*)hci_pckt->data;
  if (hci_pckt->type != HCI_EVENT_PKT) return;

  switch (event_pckt->evt) {
    case EVT_DISCONN_COMPLETE: {
      evt_disconn_complete* evt = (evt_disconn_complete*)event_pckt->data;
      g_ble.note_disconnect(evt->handle, evt->reason);
      break;
    }
    case EVT_LE_META_EVENT: {
      evt_le_meta_event* evt = (evt_le_meta_event*)event_pckt->data;
      switch (evt->subevent) {
        case EVT_LE_CONN_COMPLETE: {
          evt_le_connection_complete* cc = (evt_le_connection_complete*)evt->data;
          g_ble.note_connect(cc->handle, cc->role, cc->peer_bdaddr);
          break;
        }
        case EVT_LE_ADVERTISING_REPORT: {
          le_advertising_info* pr = (le_advertising_info*)(evt->data + 1);
          int8_t rssi = (int8_t)pr->data_RSSI[pr->data_length];
          g_ble.note_advertisement(pr->data_RSSI, pr->data_length, rssi);
          break;
        }
      }
      break;
    }
    case EVT_VENDOR: {
      evt_blue_aci* blue_evt = (evt_blue_aci*)event_pckt->data;
#if CM_GAME_GATE
      if (g_ble.gate_diag_ecodes_) {
        SerialLog.print("GATE: vendor ecode=0x");
        SerialLog.println(blue_evt->ecode, HEX);
      }
      if (blue_evt->ecode == EVT_BLUE_GATT_DISC_READ_CHAR_BY_UUID_RESP) {
        // aci_gatt_disc_charac_by_uuid responses actually arrive HERE in this
        // stack version. attr_value = [props][value-handle LE16][uuid...];
        // the VALUE handle (char handle + 1) is what accepts writes.
        evt_gatt_disc_read_char_by_uuid_resp* evt =
            (evt_gatt_disc_read_char_by_uuid_resp*)blue_evt->data;
        if (evt->event_data_length >= 3) {
          uint16_t value_handle = evt->attr_value[1] | (evt->attr_value[2] << 8);
          SerialLog.print("GATE: disc resp decl=");
          SerialLog.print(evt->attr_handle);
          SerialLog.print(" parsed_value=");
          SerialLog.println(value_handle);
          g_ble.gate_note_disc_resp(value_handle);
        }
      } else if (blue_evt->ecode == EVT_BLUE_ATT_FIND_INFORMATION_RESP) {
        // aci_gatt_disc_charac_by_uuid responses arrive here: format=2 pairs
        // of [2-byte handle][16-byte UUID]. Match the peer's UART TX char.
        evt_att_find_information_resp* evt =
            (evt_att_find_information_resp*)blue_evt->data;
        // On-air (reversed) order — must match the request.
        static const uint8_t kTxUuid[16] = {0x9E, 0xCA, 0xDC, 0x24, 0x0E, 0xE5,
                                            0xA9, 0xE0, 0x93, 0xF3, 0xA3, 0xB5,
                                            0x02, 0x00, 0x40, 0x6E};
        if (evt->format == 2) {
          const uint8_t* p = evt->handle_uuid_pair;
          const uint8_t* end = (const uint8_t*)blue_evt->data + 3 + evt->event_data_length;
          while (p + 18 <= end) {
            uint16_t handle = p[0] | (p[1] << 8);
            if (memcmp(p + 2, kTxUuid, 16) == 0) {
              g_ble.gate_note_disc_resp(handle);
            }
            p += 18;
          }
        }
      } else if (blue_evt->ecode == EVT_BLUE_GATT_ERROR_RESP) {
        evt_gatt_error_resp* er = (evt_gatt_error_resp*)blue_evt->data;
        SerialLog.print("GATE: gatt error resp handle=");
        SerialLog.print(er->conn_handle);
        SerialLog.print(" attr=");
        SerialLog.print(er->attr_handle);
        SerialLog.print(" err=0x");
        SerialLog.println(er->error_code, HEX);
      } else if (blue_evt->ecode == EVT_BLUE_GATT_PROCEDURE_COMPLETE) {
        evt_gatt_procedure_complete* pc = (evt_gatt_procedure_complete*)blue_evt->data;
        SerialLog.print("GATE: proc complete, error=0x");
        SerialLog.println(pc->error_code, HEX);
        g_ble.gate_note_proc_complete();
      }
#endif
#if !CM_GAME_GATE
      // v2 raid (product): discovery responses route to the raid handlers.
      if (blue_evt->ecode == EVT_BLUE_GATT_DISC_READ_CHAR_BY_UUID_RESP) {
        evt_gatt_disc_read_char_by_uuid_resp* evt =
            (evt_gatt_disc_read_char_by_uuid_resp*)blue_evt->data;
        if (g_ble.raid_active() && evt->event_data_length >= 3) {
          uint16_t value_handle = evt->attr_value[1] | (evt->attr_value[2] << 8);
          g_ble.raid_note_disc_resp(value_handle);
        }
      } else if (blue_evt->ecode == EVT_BLUE_GATT_PROCEDURE_COMPLETE) {
        g_ble.raid_note_proc_complete();
      }
#endif
      if (blue_evt->ecode == EVT_BLUE_GATT_ATTRIBUTE_MODIFIED) {
        evt_gatt_attr_modified_IDB05A1* evt = (evt_gatt_attr_modified_IDB05A1*)blue_evt->data;
#if CM_GAME_GATE
        if (evt->attr_handle == uart_tx_char_handle + 1) {
          g_ble.gate_rx_writes_++;  // gate build: count peer writes (public field)
        }
#endif
        if (evt->attr_handle == uart_tx_char_handle + 1) {
          feed_fragment(evt->att_data, evt->data_length);
        }
      } else if (blue_evt->ecode == 0x407) {
        // EVT_BLUE_GAP_PROCEDURE_COMPLETE: the discovery window ended on its
        // own; the TDD scheduler starts the next window.
        g_ble.note_discovery_complete();
      }
      break;
    }
  }
}

// ---------------- v2 raid gate experiment (bench builds only) ----------------

#if CM_GAME_GATE

const char* BleApp::gate_phase_name() const {
  switch (gate_phase_) {
    case GatePhase::GATE_IDLE: return "idle";
    case GatePhase::GATE_CONNECTING: return "connecting";
    case GatePhase::GATE_DISCOVERING: return "discovering";
    case GatePhase::GATE_WRITING: return "writing";
    case GatePhase::GATE_DONE: return "done";
  }
  return "?";
}

void BleApp::gate_start() {
  gate_started_ms_ = millis();
  SerialLog.println("GATE: armed (suspends TDD; central connects in 5 s)");
  SerialLog.print("GATE: my writable attr (uart_tx_char_handle+1)=");
  SerialLog.println(uart_tx_char_handle + 1);
}

void BleApp::gate_tick() {
  const uint32_t now = millis();
#if DEVICE_ID == 1
  // Central: connect -> discover peer TX char -> write 10 Hz for 120 s.
  switch (gate_phase_) {
    case GatePhase::GATE_IDLE:
      if (gate_started_ms_ == 0) gate_started_ms_ = now;
      if (now - gate_started_ms_ >= 5000 && now >= gate_retry_ms_) {
        tBDAddr peer;  // uint8_t[6], LSB first (link_layer.h)
        peer[0] = 0x12; peer[1] = 0x34; peer[2] = 0x00;
        peer[3] = 0xE1; peer[4] = 0x80; peer[5] = 0x02;
                // Relaxed parameters: 30-50 ms interval, 4 s supervision. The game
        // needs ~10 Hz; a 30-50 ms interval carries that easily and survives
        // SPI contention with the display (aggressive 7.5-15 ms dropped at
        // ~30 s twice).
        // Scan duty softened 40/40 -> 96/30 units (50%): near-continuous scanning
// wedged board 1's module mid-procedure (verified live 12 Nov). ~2x slower
// to connect, sustainable for the module; the peer advertises continuously.
if (hci_le_create_connection(0x60, 0x30, 0, 0, peer, 0, 24, 40, 0, 400, 0, 0) == 0) {
          gate_phase_ = GatePhase::GATE_CONNECTING;
          SerialLog.println("GATE: create_connection sent");
        } else {
          SerialLog.println("GATE: create_connection rejected");
        }
        gate_retry_ms_ = now + 2000;
      }
      break;
    case GatePhase::GATE_CONNECTING:
      break;  // LE connection complete event advances us
    case GatePhase::GATE_DISCOVERING:
      break;  // 0x0C12 response + procedure complete advance us
    case GatePhase::GATE_WRITING:
      if (gate_peer_tx_handle_ && now - gate_last_write_ms_ >= 100) {
        uint8_t payload[12] = {1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0};
        memcpy(payload + 1, &gate_writes_, 4);
        // The peer's UART char permits WRITE_WITHOUT_RESPONSE only — a
        // write REQUEST is rejected 0x03 (observed 6 Nov).
        if (aci_gatt_write_without_response(gate_conn_handle_, gate_peer_tx_handle_, 12, payload) == 0) {
          gate_writes_++;
        }
        gate_last_write_ms_ = now;
      }
      if (gate_connected_ms_ && now - gate_connected_ms_ >= 120000UL) {
        SerialLog.print("GATE: writing window complete writes=");
        SerialLog.println(gate_writes_);
        aci_gap_terminate(gate_conn_handle_, 0x13);
        gate_phase_ = GatePhase::GATE_DONE;
        SerialLog.print("GATE: RESULT connect_ms=");
        SerialLog.print(gate_connected_ms_);
        SerialLog.print(" writes=");
        SerialLog.print(gate_writes_);
        SerialLog.print(" duration_ms=");
        SerialLog.println(now - gate_connected_ms_);
      }
      break;
    case GatePhase::GATE_DONE:
      break;
  }
#else
  // Peripheral: keep advertising until the central takes us; then hold.
  // NOTE: radio_state_ boots claiming ADVERTISING without any real start,
  // so the first entry is forced explicitly.
  if (!phone_connected_) {
    // set_discoverable is the wedge-sensitive call (6 Nov gate lesson):
    // call it ONCE at gate start, then rotate ONLY the payload — the same
    // update_adv_data loop the TDD scheduler survives for hours.
    if (!gate_advertising_started_) {
      enter_advertising();
      start_advertising();
      gate_advertising_started_ = true;
      gate_last_write_ms_ = now;
      SerialLog.println("GATE: peripheral advertising on (single set_discoverable)");
    } else if (now - gate_last_write_ms_ >= 1400) {
      rotate_advertising_payload();
      gate_last_write_ms_ = now;
    }
  } else {
    static uint32_t last_rx_print = 0;
    if (now - last_rx_print >= 10000) {
      last_rx_print = now;
      SerialLog.print("GATE: peripheral rx_writes=");
      SerialLog.println(gate_rx_writes_);
    }
  }
#endif
}

void BleApp::gate_note_connected(uint16_t handle, uint8_t role) {
  gate_conn_handle_ = handle;
  gate_connected_ms_ = millis();
  if (role == 0) {
    // Central: discover the peer's UART TX characteristic (128-bit UUID).
    gate_phase_ = GatePhase::GATE_DISCOVERING;
    // On-air (reversed) order — COPY_UUID_128 stores uuid_0 first.
    uint8_t uuid[16] = {0x9E, 0xCA, 0xDC, 0x24, 0x0E, 0xE5, 0xA9, 0xE0,
                        0x93, 0xF3, 0xA3, 0xB5, 0x02, 0x00, 0x40, 0x6E};
    tBleStatus st = aci_gatt_disc_charac_by_uuid(handle, 1, 0xFFFF, UUID_TYPE_128, uuid);
    SerialLog.print("GATE: connected (central), disc=");
    SerialLog.println(st);
  } else {
    SerialLog.println("GATE: connected (peripheral) - holding for writes");
  }
}

void BleApp::gate_note_disc_resp(uint16_t attr_handle) {
  gate_peer_tx_handle_ = attr_handle;
  SerialLog.print("GATE: peer tx char handle=");
  SerialLog.println(attr_handle);
}

void BleApp::gate_note_proc_complete() {
  if (gate_phase_ == GatePhase::GATE_DISCOVERING) {
    if (gate_peer_tx_handle_) {
      gate_phase_ = GatePhase::GATE_WRITING;
      SerialLog.println("GATE: discovery complete, writing at 10 Hz");
    } else {
      SerialLog.println("GATE: discovery finished WITHOUT the tx char");
      gate_phase_ = GatePhase::GATE_DONE;
    }
  }
}

void BleApp::gate_note_disconnected() {
  if (gate_phase_ == GatePhase::GATE_WRITING) {
    SerialLog.println("GATE: disconnected mid-window (unexpected)");
    gate_phase_ = GatePhase::GATE_DONE;
  }
#if DEVICE_ID != 1
  // Peripheral: after a disconnect the stack usually stops advertising —
  // one full restart (set_discoverable once) puts us back on air.
  gate_advertising_started_ = false;
#endif
}
#endif  // CM_GAME_GATE

// ---------------- v2 raid mode (product; runtime-gated) ----------------
//
// Transport: both sides WRITE to each other's UART TX characteristic
// (write-without-response — proven by the gate experiment). The host's game
// state reaches the client as framed MSG_GAME_STATE through the peer's
// normal fragment path, and the client's inputs arrive as MSG_GAME_INPUT.
// No notifications/CCCDs needed.

void BleApp::raid_start(bool demo_hp, uint16_t existing_peer_handle) {
  // RAID REMOVED 14 Nov (user decision): the board-to-board sustained link
  // drops at 23-30 s — a hardware wall documented across every configuration
  // since 12 Nov. Every arm path (the phone relay, the practice button, the
  // bench trigger, the flag auto-arm) dead-ends here. The quest set is
  // together, explore, quiz; the raid state/implementation below stays
  // compiled but is unreachable.
  (void)demo_hp;
  (void)existing_peer_handle;
}

void BleApp::raid_tick() {
  const uint32_t now = millis();
#if DEVICE_ID == 1
  // Host (central): connect -> discover peer TX char -> exchange game traffic.
  switch (raid_phase_) {
    case RadioStateRaid::RAID_IDLE:
      // Staged teardown — one radio operation per tick, then the connect.
      if (raid_teardown_stage_ == 0) {
        if (conn_handle_) {
          aci_gap_terminate(conn_handle_, 0x16);
          conn_handle_ = 0;
          phone_connected_ = false;
          SerialLog.println("raid: phone link dropped for the fight");
        }
        raid_teardown_stage_ = 1;
        break;
      }
      if (raid_teardown_stage_ == 1) {
        if (radio_state_ == RadioState::SCANNING) {
          aci_gap_terminate_gap_procedure(GAP_GENERAL_DISCOVERY_PROC);
          discovery_running_ = 0;
        } else if (radio_state_ == RadioState::ADVERTISING) {
          aci_gap_set_non_discoverable();
        }
        raid_teardown_stage_ = 2;
        break;
      }
      // Client-side advertising entry (teardown complete).
#if DEVICE_ID != 1
      if (!raid_conn_handle_ && !raid_adv_started_) {
        enter_advertising();
        start_advertising();
        raid_adv_started_ = true;
      }
      // Client timeout: the host times out and exits after 60 s; without
      // this the client waits in raid mode FOREVER (radio frozen, no TDD,
      // no phone relink — observed live 14 Nov when the host's phone was
      // locked). Exit honestly; the phones re-relay raid-start on the next
      // relink and the whole gate retries.
      if (now - raid_started_ms_ > 90000UL) {
        SerialLog.println("raid: no host connected; resuming TDD");
        raid_mode_ = false;
        raid_phase_ = RadioStateRaid::RAID_DONE;
      }
#else
      if (now >= raid_retry_ms_) {
        tBDAddr peer;  // uint8_t[6], LSB first — board 2 = 03:80:E1:00:34:12
        peer[0] = 0x12; peer[1] = 0x34; peer[2] = 0x00;
        peer[3] = 0xE1; peer[4] = 0x80; peer[5] = 0x03;
        // Scan duty softened 40/40 -> 96/30 units (50%): near-continuous scanning
// wedged board 1's module mid-procedure (verified live 12 Nov). ~2x slower
// to connect, sustainable for the module; the peer advertises continuously.
if (hci_le_create_connection(0x60, 0x30, 0, 0, peer, 0, 24, 40, 0, 400, 0, 0) == 0) {
          raid_phase_ = RadioStateRaid::RAID_CONNECTING;
          SerialLog.println("raid: connecting to peer");
        } else {
          SerialLog.println("raid: create_connection rejected; retrying");
        }
        raid_retry_ms_ = now + 2000;
      }
#endif
      break;
    case RadioStateRaid::RAID_CONNECTING:
      if (now - raid_started_ms_ > 60000UL) {
        SerialLog.println("raid: connect timeout; resuming TDD");
        raid_mode_ = false;
      }
      break;
    case RadioStateRaid::RAID_DISCOVERING:
      break;
    case RadioStateRaid::RAID_FIGHTING:
      if (raid_peer_tx_handle_ && now - raid_last_tx_ms_ >= GAME_TICK_MS) {
        uint8_t payload[20];
        const uint8_t n = g_game.encode_state(payload, sizeof(payload));
        aci_gatt_write_without_response(raid_conn_handle_, raid_peer_tx_handle_, n, payload);
        raid_last_tx_ms_ = now;
        if (g_game.finished()) {
          SerialLog.print("raid: fight over, won=");
          SerialLog.println(g_game.won() ? 1 : 0);
          raid_outcome_value_ = g_game.won() ? 1 : 2;
          raid_duration_s_ = (uint16_t)((now - raid_connected_ms_) / 1000);
          raid_outcome_nonce_ = ((uint64_t)now << 20) ^ 0x5A1D5A1D5A1D5A1DULL;
          raid_outcome_pending_ = true;
          raid_outcome_ack_ = false;
          memcpy(raid_session_uuid_, g_ble.interaction().session_id, 16);
          raid_phase_ = RadioStateRaid::RAID_REPORT;
          aci_gap_terminate(raid_conn_handle_, 0x13);
        }
      }
      break;
    case RadioStateRaid::RAID_REPORT:
      // The phone relinks via the normal TDD path; the outcome relays with
      // nonce-retry until the phone ACKs (same pattern as interaction
      // commands). Wire: [ver][outcome u8][duration s LE16][nonce LE64]
      //                     [session UUID raw 16].
      if (phone_connected_ && !raid_outcome_ack_) {
        if (now - raid_last_outcome_ms_ >= 1500) {
          uint8_t wire[26];
          memset(wire, 0, sizeof(wire));
          wire[0] = 1;
          wire[1] = raid_outcome_value_;
          wire[2] = raid_duration_s_ & 0xFF;
          wire[3] = (raid_duration_s_ >> 8) & 0xFF;
          memcpy(wire + 4, &raid_outcome_nonce_, 8);
          memcpy(wire + 12, raid_session_uuid_, 16);
          if (g_ble.send_message(MSG_RAID_OUTCOME, wire, sizeof(wire))) {
            raid_last_outcome_ms_ = now;
          }
        }
      } else if (raid_outcome_ack_ && !raid_outcome_sent_) {
        raid_outcome_sent_ = true;
        SerialLog.println("raid: outcome ACKed by the phone");
      }
      break;
    case RadioStateRaid::RAID_DONE:
      break;
  }
#else
  // Client (peripheral): advertise until taken; hold while connected.
  // Keyed on the raid peer link (NOT phone_connected_): the peer connection
  // may be the trigger itself (relay-miss tolerance), and phone_connected_
  // then only tracks the relink for the outcome relay. IDLE-only: after the
  // fight (REPORT) TDD resumes for the phone relink instead.
  if (!raid_conn_handle_ && raid_phase_ == RadioStateRaid::RAID_IDLE) {
    if (!raid_adv_started_) {
      enter_advertising();
      start_advertising();
      raid_adv_started_ = true;
    } else if (now - raid_last_tx_ms_ >= 1400) {
      rotate_advertising_payload();
      raid_last_tx_ms_ = now;
    }
  } else if (raid_phase_ == RadioStateRaid::RAID_FIGHTING && raid_peer_tx_handle_ &&
             now - raid_last_tx_ms_ >= GAME_TICK_MS) {
    uint8_t payload[6];
    const uint8_t n = g_game.encode_input(payload, sizeof(payload));
    aci_gatt_write_without_response(raid_conn_handle_, raid_peer_tx_handle_, n, payload);
    raid_last_tx_ms_ = now;
    if (g_game.finished()) {
      SerialLog.print("raid: fight over (client view), won=");
      SerialLog.println(g_game.won() ? 1 : 0);
      raid_outcome_value_ = g_game.won() ? 1 : 2;
      raid_duration_s_ = (uint16_t)((now - raid_connected_ms_) / 1000);
      raid_outcome_nonce_ = ((uint64_t)now << 20) ^ 0x5A1D5A1D5A1D5A1EULL;
      raid_outcome_pending_ = true;
      raid_outcome_ack_ = false;
      memcpy(raid_session_uuid_, g_ble.interaction().session_id, 16);
      raid_phase_ = RadioStateRaid::RAID_REPORT;
      aci_gap_terminate(raid_conn_handle_, 0x13);
    }
  } else if (raid_phase_ == RadioStateRaid::RAID_REPORT) {
    // Client: identical outcome relay to its own phone.
    if (phone_connected_ && raid_outcome_pending_ && !raid_outcome_ack_ &&
        now - raid_last_outcome_ms_ >= 1500) {
      uint8_t wire[26];
      memset(wire, 0, sizeof(wire));
      wire[0] = 1;
      wire[1] = raid_outcome_value_;
      wire[2] = raid_duration_s_ & 0xFF;
      wire[3] = (raid_duration_s_ >> 8) & 0xFF;
      memcpy(wire + 4, &raid_outcome_nonce_, 8);
      memcpy(wire + 12, raid_session_uuid_, 16);
      if (g_ble.send_message(MSG_RAID_OUTCOME, wire, sizeof(wire))) {
        raid_last_outcome_ms_ = now;
      }
    } else if (raid_outcome_ack_ && !raid_outcome_sent_) {
      raid_outcome_sent_ = true;
      SerialLog.println("raid: outcome ACKed by the phone");
    }
  }
#endif
}

void BleApp::raid_note_connected(uint16_t handle, uint8_t role) {
  raid_conn_handle_ = handle;
  raid_connected_ms_ = millis();
  radio_state_ = RadioState::LINKED;
  state_started_ms_ = millis();
  SerialLog.println("raid: connected — fight starts");
  // BOTH roles discover the peer's UART TX char (symmetric write transport).
  raid_phase_ = RadioStateRaid::RAID_DISCOVERING;
  uint8_t uuid[16] = {0x9E, 0xCA, 0xDC, 0x24, 0x0E, 0xE5, 0xA9, 0xE0,
                      0x93, 0xF3, 0xA3, 0xB5, 0x02, 0x00, 0x40, 0x6E};
  aci_gatt_disc_charac_by_uuid(handle, 1, 0xFFFF, UUID_TYPE_128, uuid);
}

void BleApp::raid_note_disc_resp(uint16_t attr_handle) {
  raid_peer_tx_handle_ = attr_handle;
  SerialLog.print("raid: peer tx char value handle=");
  SerialLog.println(attr_handle);
}

void BleApp::raid_note_proc_complete() {
  if (raid_phase_ == RadioStateRaid::RAID_DISCOVERING) {
    if (raid_peer_tx_handle_) {
      raid_phase_ = RadioStateRaid::RAID_FIGHTING;
      raid_last_tx_ms_ = 0;
      g_game.begin(DEVICE_ID == 1);
      SerialLog.println("raid: FIGHT!");
    } else {
      SerialLog.println("raid: discovery found nothing; resuming TDD");
      raid_mode_ = false;
    }
  }
}

void BleApp::raid_note_disconnected(uint16_t handle) {
  (void)handle;  // caller already verified handle == raid_conn_handle_
  raid_conn_handle_ = 0;
  raid_peer_tx_handle_ = 0;
  if (raid_phase_ == RadioStateRaid::RAID_FIGHTING) {
    SerialLog.println("raid: link lost mid-fight (aborting honestly)");
    raid_phase_ = RadioStateRaid::RAID_DONE;
    raid_mode_ = false;
    return;
  }
  // Post-fight disconnect (the host's terminate): hold raid mode so the
  // outcome relays once the phone relinks; TDD resumes for the relink.
  if (raid_phase_ == RadioStateRaid::RAID_REPORT) {
    enter_scanning();  // resume TDD so the phone can find us
  }
}
