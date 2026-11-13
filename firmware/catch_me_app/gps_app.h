// GPS reader wrapper (ASD2501 + SoftwareSerialZero + TinyGPS).

#pragma once

#include <Arduino.h>
#include <TinyGPS.h>

#include "SoftwareSerialZero.h"
#include "config.h"

struct GpsFix {
  bool valid;          // a fix exists AND is newer than GPS_FIX_STALE_MS
  int32_t lat_e6;      // degrees * 1e6
  int32_t lon_e6;
  uint16_t age_ms;     // age of the fix at the last query
  uint8_t satellites;
};

class GpsApp {
 public:
  void begin();
  void tick();  // drain available bytes into the parser
  GpsFix fix();  // non-const: TinyGPS getters are non-const
  uint32_t chars_seen() const { return chars_; }

 private:
  // Lazily constructed in begin(): a global SoftwareSerial interferes with
  // SPIMemory's begin() on this board (hangs inside flash chip detection).
  SoftwareSerial* soft_serial_ = nullptr;
  TinyGPS gps_;
  uint32_t chars_ = 0;
  uint32_t last_query_ms_ = 0;
  GpsFix cached_{};
};

extern GpsApp g_gps;
