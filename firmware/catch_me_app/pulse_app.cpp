#include "pulse_app.h"

PulseApp g_pulse;

#if PULSE_ENABLED
#include <Wire.h>
#include <Wireling.h>
#include <MAX30105.h>
#include <heartRate.h>

// AST1041 = MAX30101 pulse oximeter behind the ASD2022 Wireling adapter's
// I2C multiplexer. TinyCircuits ships no Arduino library for this Wireling;
// the SparkFun MAX3010x driver (vendored, commit 72d5308) is the standard
// MAX30101 driver and provides the beat detector used below.

static MAX30105 pulse_sensor;
static bool sensor_present = false;
static uint8_t active_port = 0;

// Contact/quality thresholds follow the SparkFun HeartRate example profile.
static const uint32_t FINGER_MIN_IR = 50000;
static const int32_t BEAT_MIN_MS = 300;
static const int32_t BEAT_MAX_MS = 2500;
static const uint32_t BEAT_STALE_MS = 3000;

static int32_t beat_deltas[4];           // last four inter-beat intervals
static uint8_t beat_deltas_filled = 0;
static int32_t last_beat_at_ms = -1;
static uint32_t last_tick_ms = 0;
#endif

void PulseApp::begin() {
#if PULSE_ENABLED
  Wireling.begin();  // Wire.begin, adapter power (D4), mux port 0

  // The physical Wireling port the sensor sits on is not fixed: probe all
  // four mux ports for a MAX30101 ACK and use whichever answers.
  for (uint8_t port = 0; port < 4 && !sensor_present; port++) {
    Wireling.selectPort(port);
    Wire.beginTransmission(CM_PULSE_I2C_ADDR);
    if (Wire.endTransmission() == 0) {
      active_port = port;
      sensor_present = true;
    }
  }
  if (!sensor_present) {
    SerialUSB.println("pulse: MAX30101 not found on any adapter port");
    latest_ = PulseReading{false, 0, HR_STATUS_NO_CONTACT};
    return;
  }
  Wireling.selectPort(active_port);
  if (!pulse_sensor.begin(Wire, I2C_SPEED_FAST)) {
    SerialUSB.println("pulse: MAX30101 init failed");
    sensor_present = false;
    latest_ = PulseReading{false, 0, HR_STATUS_NO_CONTACT};
    return;
  }
  // SparkFun HeartRate-example profile: LED 0x1F, avg 8 samples, red+IR mode,
  // 400 Hz, 411 us pulse width, 4096 nA ADC range.
  pulse_sensor.setup(0x1F, 8, 2, 400, 411, 4096);
  SerialUSB.print("pulse: MAX30101 on adapter port ");
  SerialUSB.println(active_port);
  latest_ = PulseReading{false, 0, HR_STATUS_WARMING_UP};
#else
  latest_ = PulseReading{false, 0, HR_STATUS_NO_CONTACT};
#endif
}

void PulseApp::tick() {
#if PULSE_ENABLED
  if (!sensor_present) return;

  // ~100 Hz sampling: the beat detector needs a steady cadence; the 10 ms
  // main loop already provides it. The FIFO produces 400/8 = 50 samples/s,
  // so polling at 100 Hz never overflows it.
  uint32_t now = millis();
  if (now - last_tick_ms < 10) return;
  last_tick_ms = now;

  uint32_t ir = pulse_sensor.getIR();
  if (ir < FINGER_MIN_IR) {
    if (latest_.status != HR_STATUS_NO_CONTACT) {
      beat_deltas_filled = 0;
      last_beat_at_ms = -1;
      latest_ = PulseReading{false, 0, HR_STATUS_NO_CONTACT};
    }
    return;
  }

  if (latest_.status == HR_STATUS_NO_CONTACT) {
    beat_deltas_filled = 0;
    last_beat_at_ms = -1;
    latest_.valid = false;
    latest_.bpm = 0;
    latest_.status = HR_STATUS_WARMING_UP;
  }

  if (checkForBeat(ir)) {
    if (last_beat_at_ms > 0) {
      int32_t delta = (int32_t)(now - (uint32_t)last_beat_at_ms);
      if (delta >= BEAT_MIN_MS && delta <= BEAT_MAX_MS) {
        // Shift-in keeps the four most recent in-range intervals.
        beat_deltas[0] = beat_deltas[1];
        beat_deltas[1] = beat_deltas[2];
        beat_deltas[2] = beat_deltas[3];
        beat_deltas[3] = delta;
        if (beat_deltas_filled < 4) beat_deltas_filled++;
        if (beat_deltas_filled >= 2) {
          int32_t sum = 0;
          for (uint8_t i = 4 - beat_deltas_filled; i < 4; i++) sum += beat_deltas[i];
          uint32_t avg = (uint32_t)(sum / beat_deltas_filled);
          latest_.bpm = (uint8_t)(60000UL / avg);
          latest_.valid = beat_deltas_filled >= 3;
          latest_.status = beat_deltas_filled >= 3 ? HR_STATUS_VALID : HR_STATUS_WARMING_UP;
        }
      }
      last_beat_at_ms = now;
    } else {
      last_beat_at_ms = now;  // first beat only anchors the interval timer
    }
  }

  // In contact but no beat for a while: still warming (or noisy contact) —
  // do not republish a stale BPM as valid.
  if (latest_.valid && now - (uint32_t)last_beat_at_ms > BEAT_STALE_MS) {
    latest_.valid = false;
    latest_.bpm = 0;
    latest_.status = HR_STATUS_WARMING_UP;
  }
#endif
}

PulseReading PulseApp::reading() const {
  return latest_;
}
