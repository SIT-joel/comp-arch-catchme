// Accelerometer input (15 Nov): Bosch BMA25x over I2C (probed at 0x18,
// chip id 0xFA — the ASD2511-R-A shield in the stack; HARDWARE.md). The
// tilt replaces button-mashing in the pet's Snack Catch mini-game: hold
// the board facing you, tilt left/right, the basket follows.
//
// Calibration captures the holding orientation at game start; the tilt is
// the X-axis delta from that neutral (a vertical hold puts ~1 g on X, and
// a left/right tilt swings it sinusoidally — Y barely moves near vertical).
// The raw dump on the bench showed X carrying the gravity split, so X is
// the tilt axis; Y stays available as a future fallback.

#pragma once

#include <Arduino.h>

class ImuApp {
 public:
  void begin();
  void tick();                       // poll at ~20 Hz; call every loop
  bool available() const { return available_; }
  // -100..100: the calibrated tilt (X-axis delta, smoothed, clamped).
  int8_t tilt() const { return tilt_; }
  // True while the tilt exceeds the activation threshold (the user is
  // actively steering) — callers use it to arbitrate with the buttons.
  bool tilt_active() const { return tilt_active_; }

 private:
  bool probe();
  bool readAcc(int16_t &x, int16_t &y, int16_t &z);
  void calibrate();

  bool available_ = false;
  bool calibrated_ = false;
  int8_t tilt_ = 0;
  bool tilt_active_ = false;
  int32_t neutral_x_ = 0;
  int32_t neutral_y_ = 0;
  int32_t smooth_x_ = 0;
  uint32_t last_read_ms_ = 0;
  uint8_t acc_addr_ = 0;
};

extern ImuApp g_imu;
