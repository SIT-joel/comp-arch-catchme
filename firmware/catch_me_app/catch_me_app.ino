// Catch Me wearable firmware — main application.
//
// State machine at a 10 ms tick; nothing blocks waiting on a connection or a
// GPS fix (docs/ARCHITECTURE.md 'Wearable firmware'):
//   - GPS parsed continuously; pulse acquisition independent of radio.
//   - Peer observations arrive from BLE scan events (advertising heartbeats).
//   - One telemetry record per second: appended to the flash queue and, when
//     the phone is connected, sent framed over the UART service.
//   - ACK messages advance the flash queue watermark; records are only
//     removed after the server persisted them (relayed by the phone).
//   - SESSION_STATE updates the local display + advertised token binding.
//   - Completion events buzz once (buzzer pending hardware audit).
//
// Build: arduino-cli compile --fqbn TinyCircuits:samd:tinyscreen
//        --build-property "compiler.cpp.extra_flags=-DDEVICE_ID=1"  (or 2)

#include "ble_app.h"
#include "config.h"
#include "crash_diag.h"
#include "flash_queue.h"
#include "game_app.h"
#include "gps_app.h"
#include "internal_queue.h"
#include "pet_core.h"
#include "pet_store.h"
#include "pulse_app.h"
#include "queue_sel.h"
#include "records.h"
#include "ui_app.h"
#include "watchdog_app.h"

#define SerialLog SerialUSB

// Bounded-SPI timeout counter (arduino_bluenrg_ble.cpp): each increment is
// a wedged-SERCOM byte transfer that USED to hang the loop until the WDT
// fired — now it fails fast and the module-wedge detector re-inits.
extern volatile uint32_t spi_xfer_timeouts;

char g_boot_id[16] = "d?-0";
uint32_t g_record_sequence = 0;

InternalQueue g_iq;   // used when the W25Q shield is absent
static bool external_flash_ok = false;

#ifndef CM_DISABLE_INTERNAL_QUEUE
#define CM_DISABLE_INTERNAL_QUEUE 0  // watchdog-triage flag (diagnostic builds)
#endif

bool q_external() { return external_flash_ok; }
// v2 hardware finding (wedge forensics, 6 Nov): internal-flash writes stall
// the CPU mid-SPI and corrupt the BLE module's transaction — IRQ-stuck
// wedges on BOTH boards, reproduced in every configuration. The flash queue
// is only an offline backup ("the live send IS the record"), so without a
// W25Q shield we run LIVE-ONLY and drop backups honestly; internal flash is
// never written again. (g_iq stays for the boot id/counter, written once at
// boot before the radio exists.)
bool q_push(const TelemetryRecord& rec) {
  return external_flash_ok ? g_queue.push(rec) : false;
}
extern volatile uint32_t hci_verify_bads;

uint16_t q_pending() {
  return external_flash_ok ? g_queue.pending() : 0;
}
bool q_full() {
  return external_flash_ok ? g_queue.full() : true;
}
bool q_peek(uint16_t offset, TelemetryRecord* out) {
  if (external_flash_ok) return g_queue.peek(offset, out);
  (void)offset; (void)out; return false;
}
void q_acknowledge(uint16_t n) {
  if (external_flash_ok) g_queue.acknowledge(n);
}

// Time anchor: phone relays server time (MSG_TIME_ANCHOR: u32 epoch, u16
// uncertainty). Until then records carry captured_epoch=0 (unsynced) and the
// phone anchors them later from uptime history.
static uint32_t anchor_epoch = 0;
static uint32_t anchor_at_ms = 0;
static uint16_t anchor_uncertainty = 0xFFFF;

static uint32_t last_record_ms = 0;
static uint32_t last_ui_ms = 0;
static uint32_t last_status_ms = 0;
static uint32_t last_disc_obs_ms = 0;

// Completion de-dup: remember the last buzzed completion id.
static char last_buzzed_completion[24] = {0};

void handle_time_anchor(const uint8_t* p, uint16_t len) {
  if (len < 6) return;
  memcpy(&anchor_epoch, p, 4);
  memcpy(&anchor_uncertainty, p + 4, 2);
  anchor_at_ms = millis();
  SerialLog.print("time anchor epoch=");
  SerialLog.print(anchor_epoch);
  SerialLog.print(" unc=");
  SerialLog.println(anchor_uncertainty);
}

void handle_ack(const uint8_t* p, uint16_t len) {
  // ACK payload: u8 count, then count * u32 sequences acknowledged by the
  // SERVER (phone relays exactly; contiguous prefix only per contract).
  if (len < 1) return;
  uint8_t count = p[0];
  if (count > 16 || len < (uint16_t)(1 + count * 4)) return;
  // The phone sends the contiguous prefix length; verify against the queue.
  uint16_t acked = 0;
  TelemetryRecord rec;
  for (uint16_t i = 0; i < q_pending() && acked < count; i++) {
    if (!q_peek(i, &rec)) break;
    uint32_t seq;
    memcpy(&seq, p + 1 + acked * 4, 4);
    if (seq == g_record_sequence - q_pending() + i) {
      acked++;
    } else {
      break;  // hole in the range: never discard unacknowledged records
    }
  }
  if (acked > 0) {
    q_acknowledge(acked);
    SerialLog.print("ack advanced by ");
    SerialLog.println(acked);
  }
}

void buzz_completion() {
#if BUZZER_ENABLED
  // Two short beeps; buzzer port/timer interaction pending physical audit.
  tone(BUZZER_PIN, 2600, 120);
  delay(160);
  tone(BUZZER_PIN, 3200, 120);
#else
  SerialLog.println("COMPLETION (buzzer disabled)");
#endif
}

void build_and_store_record() {
  TelemetryRecord rec;
  memset(&rec, 0, sizeof(rec));

  uint32_t now = millis();
  rec.uptime_ms = now;
  if (anchor_epoch != 0) {
    rec.captured_epoch = anchor_epoch + (now - anchor_at_ms) / 1000;
    rec.clock_uncertainty = anchor_uncertainty;
  } else {
    rec.captured_epoch = 0;
    rec.clock_uncertainty = 0xFFFF;
  }

#if CM_PULSE_ENABLED
  const PulseReading hr = g_pulse.reading();
  rec.hr_status = hr.status;
  if (hr.valid) {
    rec.flags |= (1 << RF_HR_VALID);
    rec.bpm = hr.bpm;
  }
#else
  // v2: no pulse sensor in the product — honest no_contact, never fabricated.
  rec.hr_status = 2;  // no_contact
#endif

#if CM_GPS_ENABLED
  const GpsFix gps = g_gps.fix();
#else
  GpsFix gps{};  // v2: wearable GPS not part of the product — honest no-fix
  gps.valid = false;
#endif
  if (gps.valid) {
    rec.flags |= (1 << RF_GPS_VALID);
    rec.lat_e6 = gps.lat_e6;
    rec.lon_e6 = gps.lon_e6;
    rec.gps_fix_age_ms = gps.age_ms;
  } else {
    rec.lat_e6 = 0x7FFFFFFF;
    rec.lon_e6 = 0x7FFFFFFF;
    rec.gps_fix_age_ms = 0xFFFF;
  }

  const PeerObservation& peer = g_ble.last_peer();
  if (peer.device != 0 && peer.fresh) {
    rec.flags |= (1 << RF_PEER_OBSERVED);
    rec.peer_device = peer.device;
    rec.peer_heartbeat = peer.heartbeat;
    rec.peer_obs_age_ms = (uint16_t)(now - peer.at_ms);
    rec.peer_token_hash = peer.token_hash;
  }

  // Identity is burned when the record is USED, not when stored: the live
  // send IS the record; the flash queue is only the offline backup (server
  // dedupes by device/boot/sequence, so a queue copy is never required).
  g_record_sequence++;
  bool sent_live = false;
  if (g_ble.phoneConnected()) {
    uint8_t payload[4 + sizeof(rec)];
    memcpy(payload, &g_record_sequence, 4);
    memcpy(payload + 4, &rec, sizeof(rec));
    if (g_ble.send_message(MSG_TELEMETRY, payload, sizeof(payload))) {
      sent_live = true;
    } else {
      SerialLog.println("telemetry notify failed");
    }
  }

  // While the link is up, drain up to 2 records queued during earlier
  // disconnected periods (oldest first). Drained records are re-sequenced
  // under the current boot identity — valid, since a new boot id removes
  // any collision with their original delivery attempt.
  if (sent_live) {
    TelemetryRecord queued;
    for (int drained = 0; drained < 2 && q_peek(0, &queued); drained++) {
      g_record_sequence++;
      uint8_t payload[4 + sizeof(queued)];
      memcpy(payload, &g_record_sequence, 4);
      memcpy(payload + 4, &queued, sizeof(queued));
      if (g_ble.send_message(MSG_TELEMETRY, payload, sizeof(payload))) {
        q_acknowledge(1);
      } else {
        break;  // hole: never acknowledge an unsent record
      }
    }
  }

  if (!sent_live && !q_push(rec)) {
    // Queue full: report the lost BACKUP copy honestly, but at most every
    // 10 s — a 1 Hz print is pure spam and every SerialUSB write is a
    // (suspected) freeze trigger when the host stops reading.
    static uint32_t last_qfull_log = 0;
    if (now - last_qfull_log >= 10000) {
      last_qfull_log = now;
      SerialLog.println("queue full: backup copies dropped (records still sent live)");
    }
    cdiag::bc(cdiag::B_QFULL, (uint8_t)q_pending(), 0);
  }
  cdiag::bc(cdiag::B_RECORD, (uint8_t)(sent_live ? 1 : 0), 0);
}

void setup() {
  SerialLog.begin(115200);
  // Bounded wait for a host: SAMD CDC drops early writes (probes lesson).
  for (uint32_t waited = 0; waited < 60000 && !SerialLog; waited += 100) delay(100);
  SerialLog.println("app: serial attached");
  // FIRST radio-free action: after a watchdog reset, dump the previous
  // life's breadcrumb tail BEFORE this life's BLE init traffic overwrites
  // the ring (128 entries; init alone consumes most of it).
  cdiag::boot_dump();

  SerialLog.println("app: flash queue init");
  external_flash_ok = g_queue.begin();
  if (!external_flash_ok) {
    SerialLog.println("flash: no W25Q shield - LIVE-ONLY telemetry (backups dropped; "
                      "internal flash is never written: writes stall the CPU mid-SPI "
                      "and wedge the BLE module)");
    g_iq.begin();  // boot counter/id only (pre-radio, safe)
  }  strncpy(g_boot_id, external_flash_ok ? g_queue.boot_id() : g_iq.boot_id(), sizeof(g_boot_id) - 1);
  g_boot_id[sizeof(g_boot_id) - 1] = 0;
  SerialLog.print("boot_id=");
  SerialLog.println(g_boot_id);

#if CM_GPS_ENABLED
  SerialLog.println("app: gps init");
  g_gps.begin();
#else
  SerialLog.println("app: gps init SKIPPED (v2: phone GPS is the location source)");
#endif
#if CM_PULSE_ENABLED
  SerialLog.println("app: pulse init");
  g_pulse.begin();
#else
  SerialLog.println("app: pulse init SKIPPED (v2: heart quest removed)");
#endif
  SerialLog.println("app: pet init");
  g_pet.begin();
  g_petcore.begin();
  SerialLog.println("app: ui init");
  g_ui.begin();

  SerialLog.println("app: ble init");
  if (!g_ble.begin()) {
    SerialLog.println("FATAL: BLE init failed");
  }
  SerialLog.print("catch_me device ");
  SerialLog.print(DEVICE_ID);
  SerialLog.print(" up, fw ");
  SerialLog.println(FIRMWARE_VERSION);
  SerialLog.print("app: boot reason: ");
  SerialLog.println(wdt::boot_reason());

#if CM_GAME_GATE
  g_ble.gate_start();
#endif

  // Watchdog LAST: everything above (including the bounded 60 s serial
  // wait) must complete before the 16 s window applies.
  wdt::begin();
  SerialLog.println("app: watchdog on (16s)");

#if CM_WDT_SELFTEST
  // One-shot validation of the crash-forensics ring (build-property flag,
  // never part of product builds): let the watchdog fire on purpose, then
  // the next boot's cdiag::boot_dump() must print this life's breadcrumb
  // tail from no-init RAM (linker fix proof). Rebuild without the flag after.
  SerialLog.println("SELFTEST: freezing now; WDT must reset in 16s");
  cdiag::bc(cdiag::B_TICK, 0x7E, 0);
  delay(20000);  // far beyond the 16 s watchdog window, feeding nothing
#endif
}

void loop() {
  wdt::feed();
  uint32_t now = millis();
  static uint32_t last_alive_ms = 0;
  if (now - last_alive_ms >= 5000) {
    last_alive_ms = now;
    wdt::note_alive(now);  // freeze forensics: last known uptime
  }

  g_ui.tick();  // side-button navigation (edge-detected at 100 Hz)
  g_ui.tick_quiz();  // quiz answer retransmit until phone ack
  g_petcore.tick();
  g_game.tick();

  // Bench triggers (newline-terminated lines): "RAID" starts the raid fight;
  // "QANS <choice 0-3>" answers the current quiz question from this board
  // (mirrors a physical A-D press). ONE reader loop: two readers race for
  // the buffer (verified live — the RAID loop drained the QANS lines).
  while (SerialLog.available()) {
    static char line_buf[8];
    static uint8_t line_len = 0;
    char c = (char)SerialLog.read();
    if (c == '\n' || c == '\r') {
      line_buf[line_len] = 0;
      if (line_len == 4 && strncmp(line_buf, "RAID", 4) == 0 && !g_game.active() &&
          !g_ble.raid_active()) {
        g_ble.raid_start();
      } else if (line_len == 6 && strncmp(line_buf, "QANS ", 5) == 0 &&
                 line_buf[5] >= '0' && line_buf[5] <= '3') {
        const bool ok = g_ui.bench_quiz_answer((uint8_t)(line_buf[5] - '0'));
        SerialLog.print("quiz: bench answer ");
        SerialLog.println(ok ? "sent" : "NOT sent (inactive/already sent/no link)");
      } else if (line_len == 4 && strncmp(line_buf, "CARE", 4) == 0) {
        // Bench trigger: mirrors a physical stroke on the pet screen —
        // queues the daily care event for the phone to claim (+10 XP).
        g_petcore.pet_stroke();
        SerialLog.println("care: stroke queued (bench)");
      } else if (line_len == 7 && strncmp(line_buf, "PETWIPE", 7) == 0) {
        g_petcore.wipe_for_rebond();
        SerialLog.println("care: pet wiped -> rebond flow");
      }
      line_len = 0;
    } else if (line_len < 7) {
      line_buf[line_len++] = c;
    }
  }

  g_ble.tick();
#if CM_GPS_ENABLED
  g_gps.tick();
#endif
#if CM_PULSE_ENABLED
  g_pulse.tick();
#endif

  // Route inbound phone messages.
  uint8_t msg_type;
  uint8_t payload[64];
  uint16_t len;
  while (g_ble.poll_message(&msg_type, payload, &len, sizeof(payload))) {
    switch (msg_type) {
      case MSG_TIME_ANCHOR:
        handle_time_anchor(payload, len);
        break;
      case MSG_ACK:
        handle_ack(payload, len);
        break;
      case MSG_HELLO:
        // Reply with STATUS: boot id, fw, queue depth.
        {
          uint8_t status[16];
          memcpy(status, g_boot_id, 16);
          bool ok = g_ble.send_message(MSG_STATUS, status, sizeof(status));
          SerialLog.print("HELLO -> STATUS send=");
          SerialLog.println(ok ? "ok" : "FAIL");
        }
        break;
      case MSG_QUEUE_PURGE:
        // Explicit admin action from the phone (debug builds only): drop
        // the undelivered BACKUP copies clogging the flash ring. Honest
        // semantics: these records were captured while no phone was linked
        // and were never delivered; purging discards them permanently.
        // Magic bytes guard against accidental triggers.
        if (len >= 3 && payload[0] == 1 && payload[1] == 'P' && payload[2] == 'G') {
          uint16_t dropped = q_pending();
          q_acknowledge(dropped);
          SerialLog.print("queue purged: ");
          SerialLog.print(dropped);
          SerialLog.println(" undelivered backup records dropped");
        }
        break;
      case MSG_INTERACTION_ACK:
        g_ui.apply_interaction_ack(payload, len);
        if (len >= 10) {
          uint64_t ack_nonce = (uint64_t)payload[1] |
                               ((uint64_t)payload[2] << 8) |
                               ((uint64_t)payload[3] << 16) |
                               ((uint64_t)payload[4] << 24) |
                               ((uint64_t)payload[5] << 32) |
                               ((uint64_t)payload[6] << 40) |
                               ((uint64_t)payload[7] << 48) |
                               ((uint64_t)payload[8] << 56);
          g_ble.raid_outcome_acked(ack_nonce);
        }
        g_petcore.care_event_acked(
            (uint64_t)(payload[1] | ((uint64_t)payload[2] << 8) |
                       ((uint64_t)payload[3] << 16) | ((uint64_t)payload[4] << 24) |
                       ((uint64_t)payload[5] << 32) | ((uint64_t)payload[6] << 40) |
                       ((uint64_t)payload[7] << 48) | ((uint64_t)payload[8] << 56)));
        break;
      case MSG_QUIZ_STATE:
        // [ver=1][active u8][idx u8][total u8] — the phone drives the quiz:
        // the question + options render there; the wearable is the A-D pad.
        if (len >= 4 && payload[0] == 1) {
          SerialLog.print("quiz: state active=");
          SerialLog.print(payload[1] != 0);
          SerialLog.print(" idx=");
          SerialLog.print(payload[2]);
          SerialLog.print("/");
          SerialLog.println(payload[3]);
          g_ui.note_quiz_state(payload[1] != 0, payload[2], payload[3]);
        }
        break;
      case MSG_RAID_START:
        if (len >= 2 && payload[0] == 1) {
          SerialLog.println("raid: start requested by the phone");
          g_ble.raid_start();
        }
        break;
      case MSG_GAME_STATE:
        g_game.apply_host_state(payload, len);
        break;
      case MSG_GAME_INPUT:
        g_game.apply_client_input(payload, len);
        break;
      case MSG_PET_STATE:
        // [ver=1][xp LE32][level u8][stage u8][cared u8][nameLen u8][name<=8]
        if (len >= 10 && payload[0] == 1) {
          uint32_t xp = (uint32_t)payload[1] | ((uint32_t)payload[2] << 8) |
                        ((uint32_t)payload[3] << 16) | ((uint32_t)payload[4] << 24);
          char name[9];
          memset(name, 0, sizeof(name));
          uint8_t name_len = payload[8] > 8 ? 8 : payload[8];
          if (name_len) memcpy(name, payload + 9, name_len);
          g_petcore.note_server_pet(xp, payload[5], payload[6],
                                    payload[7] != 0, name);
        }
        break;
      default:
        break;  // SESSION_STATE applied inside BleApp
    }
  }

  // Completion: buzz once per completion id (id in SESSION_STATE.completion).
  const char* completion = g_ble.last_completion();
  if (completion[0] != 0 && strcmp(completion, last_buzzed_completion) != 0) {
    strncpy(last_buzzed_completion, completion, sizeof(last_buzzed_completion) - 1);
    last_buzzed_completion[sizeof(last_buzzed_completion) - 1] = 0;
    buzz_completion();
    g_petcore.celebrate();  // v2: the pet celebrates a quest award
    g_ui.flash_reward("QUEST COMPLETE");  // make the +100 XP impact visible
  }

  if (now - last_record_ms >= CM_RECORD_PERIOD_MS) {
    last_record_ms = now;
    build_and_store_record();
    // v2 pet: derive the care date from the time anchor (days-from-civil
    // inverse; Howard Hinnant's algorithm, integer-only).
    if (anchor_epoch != 0) {
      const uint32_t z = (uint32_t)(anchor_epoch / 86400UL) + 719468;
      const uint32_t era = z / 146097;
      const uint32_t doe = z - era * 146097;
      const uint32_t yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
      const uint32_t y = yoe + era * 400;
      const uint32_t doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
      const uint32_t mp = (5 * doy + 2) / 153;
      const uint32_t d = doy - (153 * mp + 2) / 5 + 1;
      const uint32_t m = mp < 10 ? mp + 3 : mp - 9;
      g_petcore.note_date_ymd((y + (m <= 2 ? 1 : 0)) * 10000UL + m * 100UL + d);
    }
  }

  // Nearby discovery: upload direct scan observations to the phone while
  // linked (phone stamps captured_at from the reported age and relays to
  // the server; retransmissions keep their original identity). Never sent
  // as quest evidence — the flash queue and heartbeat path are untouched.
  if (g_ble.discovery_on() && g_ble.phoneConnected() &&
      now - last_disc_obs_ms >= 5000) {
    last_disc_obs_ms = now;
    uint8_t obs[2 + 10 * 4];
    uint8_t obs_len = g_ble.build_discovery_obs(obs, sizeof(obs));
    if (obs_len > 0) {
      if (!g_ble.send_message(MSG_DISCOVERY_OBS, obs, obs_len)) {
        SerialLog.println("discovery obs notify failed");
      }
    }
  }

  // v2: ~10 Hz while the pet mini-game is live; 1 Hz otherwise. The RAID
  // fight renders slower (400 ms): the display shares SERCOM4 SPI with the
  // BlueNRG, and clearScreen+redraw at 10 FPS alongside the 10 Hz raid
  // traffic corrupted HCI traffic until the watchdog reset BOTH boards
  // (verified live: gate runs with 1 Hz UI never reset; every fight did).
  // 400 ms keeps the fight playable while cutting display SPI duty ~4x.
  const uint32_t fast_render_ms = g_ble.raid_active() ? 400UL : 100UL;
  if (now - last_ui_ms >= (g_ui.wants_fast_render() ? fast_render_ms : CM_UI_REFRESH_MS)) {
    last_ui_ms = now;
    g_ui.render();
  }

  if (now - last_status_ms >= 5000) {
    last_status_ms = now;
    cdiag::bc(cdiag::B_STAT, 0, (uint16_t)(now / 1000));
    SerialLog.print("STAT up=");
    SerialLog.print(now / 1000);
    SerialLog.print(" adv_rx=");
    SerialLog.print(g_ble.adverts_received());
    SerialLog.print(" vbad=");
    SerialLog.print(hci_verify_bads);
    SerialLog.print(" spit=");
    SerialLog.print(spi_xfer_timeouts);
    SerialLog.print(" phone=");
    SerialLog.print(g_ble.phoneConnected());
    SerialLog.print(" peers=");
    SerialLog.print(g_ble.peer_count());
    SerialLog.print(" q=");
    SerialLog.print(q_pending());
    SerialLog.print(" gps_chars=");
    SerialLog.println(g_gps.chars_seen());
  }

  delay(10);
}
