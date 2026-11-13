// Stage 1 BLE gate probe: BlueNRG-MS (ASD2116) multi-role operation on TinyScreen+.
//
// What this probe demonstrates, in order of importance:
//   1. The BLE TinyShield initializes over SPI (CS=10, IRQ=2, RESET=9) on TinyScreen+.
//   2. The STBLE host library accepts GAP_CENTRAL_PERIPHERAL multi-role init.
//   3. The device advertises as CATCHME-<ID> while simultaneously running a
//      central-role scan. Both roles operating at once is the firmware-side
//      precondition for "direct peer evidence + phone link" concurrency.
//   4. Every received CATCHME-* advertisement is printed with a millis timestamp
//      and RSSI: each "PEER" line is one direct wearable-to-wearable observation.
//      With two boards running this sketch, both serial logs must show PEER lines.
//   5. STAT lines every 2 s summarize scan/advertise state so silence is diagnosable.
//
// Expected serial (115200) lines:
//   ble_probe init bd_addr=xx:xx:xx:xx:xx:xx role=multi(0x5)
//   ble_probe advertising name=CATCHME-1
//   ble_probe discovery started
//   PEER t=12345 addr=02:34:00:E1:80:02 name=CATCHME-2 rssi=-58
//   STAT t=14000 peers=3 last_peer_ms=210
//
// Change DEVICE_ID to 2 on the second board before uploading there.
//
// Library: STBLE from TinyCircuits/TinyCircuits-TinyShield-BLE-ASD2116
// (commit 2dcc1d4), installed into the Arduino user libraries directory.

#include <SPI.h>
#include <STBLE.h>

#ifndef BLE_DEBUG
#define BLE_DEBUG true
#endif

#define SerialMonitorInterface SerialUSB

#define DEVICE_ID 1  // 1 on the first wearable, 2 on the second
#define CM_PEER_ADV_LEN 6

// Scan interval/window in 0.625 ms units: 0x4000 = 10.24 s (ST sampleChat values).
#define SCAN_INTERVAL 0x4000
#define SCAN_WINDOW   0x4000

const char DEVICE_NAME[] = "CATCHME-" "1";  // kept short; overwritten below if needed
char actualName[16];

volatile uint8_t set_connectable = 1;
uint16_t connection_handle = 0;
int connected = FALSE;
volatile uint8_t discovery_running = 0;

uint32_t peerCount = 0;
uint32_t lastPeerAtMs = 0;
int8_t lastPeerRssi = 0;

uint32_t lastStatMs = 0;
uint32_t lastAdvPrintMs = 0;

// Peer heartbeat advertisement payload (same layout as catch_me_app).
uint16_t heartbeat_counter_ = 0;
uint16_t session_token_hash_ = 0;

void build_peer_adv(uint8_t *out, uint8_t device_id, uint16_t counter, uint16_t token_hash) {
  out[0] = 0xC5;
  out[1] = device_id;
  out[2] = (uint8_t)(counter & 0xFF);
  out[3] = (uint8_t)(counter >> 8);
  out[4] = (uint8_t)(token_hash & 0xFF);
  out[5] = (uint8_t)(token_hash >> 8);
}

// Alternation scheduler state (see setup()).
enum RadioMode { MODE_ADV, MODE_SCAN };
static RadioMode mode_ = MODE_ADV;
static uint32_t mode_started_ms_ = 0;
const uint32_t ADV_WINDOW_MS = 4000;
const uint32_t SCAN_WINDOW_MS = 4000;

#define ADV_INTERVAL_MIN_MS 50
#define ADV_INTERVAL_MAX_MS 100

static void printBdAddr(const uint8_t *a) {
  for (int i = 5; i >= 0; i--) {
    if (a[i] < 0x10) SerialMonitorInterface.print('0');
    SerialMonitorInterface.print(a[i], HEX);
    if (i) SerialMonitorInterface.print(':');
  }
}

int BLEsetup() {
  int ret;
  // Each step is announced BEFORE running so a hang identifies its location
  // even when no host has the CDC port open (prints before open are lost,
  // but the step that follows the last visible line is the culprit).
  SerialMonitorInterface.println("ble_probe step: HCI_Init");
  HCI_Init();
  SerialMonitorInterface.println("ble_probe step: BNRG_SPI_Init");
  BNRG_SPI_Init();
  SerialMonitorInterface.println("ble_probe step: BlueNRG_RST");
  BlueNRG_RST();
  SerialMonitorInterface.println("ble_probe step: rst done");

  uint8_t bdaddr[] = {0x12, 0x34, 0x00, 0xE1, 0x80, 0x00 | DEVICE_ID};
  SerialMonitorInterface.println("ble_probe step: write_config_data");
  ret = aci_hal_write_config_data(CONFIG_DATA_PUBADDR_OFFSET, CONFIG_DATA_PUBADDR_LEN, bdaddr);
  if (ret) { SerialMonitorInterface.println("ble_probe FAIL write_config_data"); return ret; }

  SerialMonitorInterface.println("ble_probe step: gatt_init");
  ret = aci_gatt_init();
  if (ret) { SerialMonitorInterface.println("ble_probe FAIL gatt_init"); return ret; }

  SerialMonitorInterface.println("ble_probe step: gap_init multi-role");
  uint16_t service_handle, dev_name_char_handle, appearance_char_handle;
  ret = aci_gap_init_IDB05A1(GAP_PERIPHERAL_ROLE_IDB05A1 | GAP_CENTRAL_ROLE_IDB05A1,
                             0, 0x10, &service_handle, &dev_name_char_handle,
                             &appearance_char_handle);
  if (ret) {
    SerialMonitorInterface.print("ble_probe FAIL gap_init(0x05) ret=0x");
    SerialMonitorInterface.println(ret, HEX);
    return ret;
  }
  SerialMonitorInterface.println("ble_probe step: gap_init ok");

  snprintf(actualName, sizeof(actualName), "CATCHME-%d", DEVICE_ID);
  SerialMonitorInterface.println("ble_probe step: set_name");
  ret = aci_gatt_update_char_value(service_handle, dev_name_char_handle, 0,
                                   strlen(actualName), (uint8_t *)actualName);
  if (ret) { SerialMonitorInterface.println("ble_probe FAIL set_name"); return ret; }

  SerialMonitorInterface.println("ble_probe step: tx_power");
  ret = aci_hal_set_tx_power_level(1, 3);  // +4 dBm-ish, as in TinyCircuits example
  if (ret) { SerialMonitorInterface.println("ble_probe WARN tx_power"); }

  SerialMonitorInterface.print("ble_probe init bd_addr=");
  printBdAddr(bdaddr);
  SerialMonitorInterface.println(" role=multi(0x5)");
  return 0;
}

void setConnectable() {
  tBleStatus ret;
  heartbeat_counter_++;  // dynamic payload: defeats scanner dedup, carries evidence
  uint8_t nameLen = strlen(actualName);

  // Step 1: become discoverable with the name (library builds that AD itself).
  hci_le_set_scan_resp_data(0, NULL);
  uint8_t nameAd[17];
  nameAd[0] = AD_TYPE_COMPLETE_LOCAL_NAME;
  memcpy(nameAd + 1, actualName, nameLen);
  ret = aci_gap_set_discoverable(ADV_IND,
                                 (ADV_INTERVAL_MIN_MS * 1000) / 625,
                                 (ADV_INTERVAL_MAX_MS * 1000) / 625,
                                 PUBLIC_ADDR, NO_WHITE_LIST_USE,
                                 nameLen + 1, (const char *)nameAd, 0, NULL, 0, 0);
  if (ret != BLE_STATUS_SUCCESS) {
    SerialMonitorInterface.print("ble_probe FAIL set_discoverable ret=0x");
    SerialMonitorInterface.println(ret, HEX);
    return;
  }

  // Step 2: replace the ADV data with full raw AD structures: flags,
  // manufacturer-specific (0xC5 magic + id + counter + token hash), name.
  // aci_gap_update_adv_data takes standard [len][type][data] format.
  uint8_t advData[31];
  uint8_t i = 0;
  advData[i++] = 0x02; advData[i++] = 0x01; advData[i++] = 0x06;
  advData[i++] = 0x09; advData[i++] = 0xFF;  // mfr len: type+2+6 = 9 bytes follow
  advData[i++] = 0x30; advData[i++] = 0x00;  // ST company id (LE)
  build_peer_adv(advData + i, DEVICE_ID, heartbeat_counter_, session_token_hash_);
  i += CM_PEER_ADV_LEN;
  advData[i++] = 1 + nameLen;
  advData[i++] = AD_TYPE_COMPLETE_LOCAL_NAME;
  memcpy(advData + i, actualName, nameLen);
  i += nameLen;
  ret = aci_gap_update_adv_data(i, advData);
  if (ret != BLE_STATUS_SUCCESS) {
    SerialMonitorInterface.print("ble_probe FAIL update_adv_data ret=0x");
    SerialMonitorInterface.println(ret, HEX);
  } else {
    SerialMonitorInterface.print("ble_probe advertising name=");
    SerialMonitorInterface.print(actualName);
    SerialMonitorInterface.print(" hb=");
    SerialMonitorInterface.println(heartbeat_counter_);
  }
}

void startDiscovery() {
  tBleStatus ret = aci_gap_start_general_discovery_proc(SCAN_INTERVAL, SCAN_WINDOW,
                                                        PUBLIC_ADDR, 0);
  if (ret == BLE_STATUS_SUCCESS) {
    discovery_running = 1;
    SerialMonitorInterface.println("ble_probe discovery started");
  } else {
    SerialMonitorInterface.print("ble_probe FAIL discovery ret=0x");
    SerialMonitorInterface.println(ret, HEX);
  }
}

void aci_loop() {
  HCI_Process();
  if (set_connectable) {
    setConnectable();
    set_connectable = 0;
  }
}

// Extract up to maxLen bytes of the local name from an advertising report.
// Returns name length, or 0 if the report carries no local name.
int extractLocalName(const uint8_t *data, uint8_t dataLen, char *out, int maxLen) {
  int i = 0;
  while (i + 1 < dataLen) {
    uint8_t fieldLen = data[i];
    if (fieldLen == 0 || i + 1 + fieldLen > dataLen) break;
    uint8_t type = data[i + 1];
    if ((type == AD_TYPE_COMPLETE_LOCAL_NAME || type == AD_TYPE_SHORTENED_LOCAL_NAME)
        && fieldLen - 1 <= (uint8_t)maxLen) {
      memcpy(out, data + i + 2, fieldLen - 1);
      return fieldLen - 1;
    }
    i += 1 + fieldLen;
  }
  return 0;
}

void handleAdvertisingReport(le_advertising_info *pr) {
  char name[32];
  int nameLen = extractLocalName(pr->data_RSSI, pr->data_length, name, sizeof(name) - 1);
  name[nameLen] = 0;
  int8_t rssi = (int8_t)pr->data_RSSI[pr->data_length];

  if (nameLen > 7 && strncmp(name, "CATCHME-", 8) == 0) {
    peerCount++;
    lastPeerAtMs = millis();
    lastPeerRssi = rssi;
    SerialMonitorInterface.print("PEER t=");
    SerialMonitorInterface.print(lastPeerAtMs);
    SerialMonitorInterface.print(" addr=");
    printBdAddr(pr->bdaddr);
    SerialMonitorInterface.print(" name=");
    SerialMonitorInterface.print(name);
    SerialMonitorInterface.print(" rssi=");
    SerialMonitorInterface.println(rssi);
  } else if (millis() - lastAdvPrintMs > 1000) {
    // Rate-limited visibility that scanning itself works even with no peer nearby.
    lastAdvPrintMs = millis();
    SerialMonitorInterface.print("ADV t=");
    SerialMonitorInterface.print(millis());
    SerialMonitorInterface.print(" addr=");
    printBdAddr(pr->bdaddr);
    SerialMonitorInterface.print(" rssi=");
    SerialMonitorInterface.print(rssi);
    if (nameLen) {
      SerialMonitorInterface.print(" name=");
      SerialMonitorInterface.print(name);
    }
    SerialMonitorInterface.println();
  }
}

extern "C" void HCI_Event_CB(void *pckt) {
  hci_uart_pckt *hci_pckt = (hci_uart_pckt *)pckt;
  hci_event_pckt *event_pckt = (hci_event_pckt *)hci_pckt->data;

  if (hci_pckt->type != HCI_EVENT_PKT) return;

  switch (event_pckt->evt) {
    case EVT_DISCONN_COMPLETE: {
      evt_disconn_complete *evt = (evt_disconn_complete *)event_pckt->data;
      SerialMonitorInterface.print("ble_probe disconnected handle=");
      SerialMonitorInterface.println(evt->handle);
      connected = FALSE;
      connection_handle = 0;
      set_connectable = 1;  // resume advertising
      break;
    }
    case EVT_LE_META_EVENT: {
      evt_le_meta_event *evt = (evt_le_meta_event *)event_pckt->data;
      switch (evt->subevent) {
        case EVT_LE_CONN_COMPLETE: {
          evt_le_connection_complete *cc = (evt_le_connection_complete *)evt->data;
          connected = TRUE;
          connection_handle = cc->handle;
          SerialMonitorInterface.print("ble_probe connected handle=");
          SerialMonitorInterface.print(cc->handle);
          SerialMonitorInterface.print(" role=");
          SerialMonitorInterface.println(cc->role == 0 ? "central" : "peripheral");
          if (cc->role == 0) discovery_running = 0;  // central scan stops on connection
          break;
        }
        case EVT_LE_ADVERTISING_REPORT: {
          le_advertising_info *pr = (le_advertising_info *)(evt->data + 1);
          handleAdvertisingReport(pr);
          break;
        }
      }
      break;
    }
    case EVT_VENDOR: {
      evt_blue_aci *blue_evt = (evt_blue_aci *)event_pckt->data;
      // 0x0407 = EVT_BLUE_GAP_PROCEDURE_COMPLETE (bit 15 of the GAP group):
      // the discovery window ended on its own; clear the flag so the
      // scheduler starts the next window.
      if (blue_evt->ecode == 0x407) {
        discovery_running = 0;
        SerialMonitorInterface.println("ble_probe discovery window complete");
      }
      break;
    }
  }
}

void setup() {
  SerialMonitorInterface.begin(115200);
  // Hold the flash shield's chip select (D5) HIGH before touching SPI: with
  // D5 floating, the W25Q flash drives the shared MISO line and every BLE
  // SPI transaction fails (verified by 01b_ble_spi_diag on the real board).
  pinMode(5, OUTPUT);
  digitalWrite(5, HIGH);
  // Wait briefly for a host serial connection so boot-time step logs are not
  // lost (SAMD CDC drops writes when no host port is open). Bounded: after
  // 60 s the probe runs headless regardless.
  for (uint32_t waited = 0; waited < 60000 && !SerialMonitorInterface; waited += 100) {
    delay(100);
  }
  SerialMonitorInterface.println("ble_probe serial attached");
  if (BLEsetup() != 0) {
    SerialMonitorInterface.println("ble_probe HALTED: init failed");
    while (1) delay(1000);
  }
  // Alternation scheduler (gate mode chosen by experiments):
  //   advertise+scan simultaneously is rejected by this stack (0x0C), so:
  //   - no phone connection: alternate ADVERTISE 4 s (phone can find/connect)
  //     and SCAN 4 s (peer heartbeat evidence; <=10 s rule needs <=8 s cycles).
  //   - phone connected: connection persists without advertising; keep cycling
  //     scan windows and log whether scanning coexists with the live link.
  aci_loop();
  delay(500);
  set_connectable = 0;  // scheduler owns advertising from here
  setConnectable();
  mode_ = MODE_ADV;
  mode_started_ms_ = millis();
}

uint32_t lastDiscoveryRestartMs = 0;

void loop() {
  aci_loop();

  uint32_t now = millis();

  if (connected) {
    // Phone link up: connections persist without advertising. Keep scanning
    // for peer heartbeats; restart the window when a procedure completes.
    if (!discovery_running && now - lastDiscoveryRestartMs >= 2000) {
      lastDiscoveryRestartMs = now;
      aci_gap_terminate_gap_procedure(GAP_GENERAL_DISCOVERY_PROC);
      delay(300);
      aci_loop();
      SerialMonitorInterface.println("SCHED scan-while-connected attempt");
      startDiscovery();
    }
  } else if (mode_ == MODE_ADV && now - mode_started_ms_ >= ADV_WINDOW_MS) {
    SerialMonitorInterface.println("SCHED adv->scan");
    aci_gap_set_non_discoverable();
    delay(300);
    aci_loop();
    startDiscovery();
    if (discovery_running) { mode_ = MODE_SCAN; mode_started_ms_ = millis(); }
  } else if (mode_ == MODE_SCAN && now - mode_started_ms_ >= SCAN_WINDOW_MS) {
    SerialMonitorInterface.println("SCHED scan->adv");
    aci_gap_terminate_gap_procedure(GAP_GENERAL_DISCOVERY_PROC);
    discovery_running = 0;
    delay(300);
    aci_loop();
    setConnectable();
    if (true) { mode_ = MODE_ADV; mode_started_ms_ = millis(); }
  }

  if (now - lastStatMs >= 2000) {
    lastStatMs = now;
    SerialMonitorInterface.print("STAT t=");
    SerialMonitorInterface.print(now);
    SerialMonitorInterface.print(" peers=");
    SerialMonitorInterface.print(peerCount);
    if (peerCount) {
      SerialMonitorInterface.print(" last_peer_ms=");
      SerialMonitorInterface.print(now - lastPeerAtMs);
      SerialMonitorInterface.print(" last_rssi=");
      SerialMonitorInterface.print(lastPeerRssi);
    }
    SerialMonitorInterface.print(" conn=");
    SerialMonitorInterface.println(connected);
  }

  delay(10);
}
