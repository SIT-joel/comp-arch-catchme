// Pulse sensor interface (AST1041 Wireling over the ASD2022 adapter).
//
// PULSE_ENABLED=0 in this stack because the sensor/adapter are not connected
// yet. The disabled path reports honestly: no contact, no fabricated BPM.
// When the Wireling hardware arrives, enable and implement against the
// TinyCircuits AST1041 library (vendor it then; sampling cadence must follow
// the manufacturer algorithm, publishing BPM ~1 Hz).

#pragma once

#include <Arduino.h>
#include "records.h"

struct PulseReading {
  bool valid;
  uint8_t bpm;      // 0 when invalid
  uint8_t status;   // HR_STATUS_*
};

class PulseApp {
 public:
  void begin();
  void tick();  // keep the acquisition cadence when enabled
  PulseReading reading() const;

 private:
#if PULSE_ENABLED
  // Place the AST1041 driver state here once vendored.
  uint32_t last_sample_ms_ = 0;
#endif
  PulseReading latest_ = {false, 0, HR_STATUS_NO_CONTACT};
};

extern PulseApp g_pulse;
