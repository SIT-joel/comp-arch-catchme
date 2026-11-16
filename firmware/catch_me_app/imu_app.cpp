#include "imu_app.h"

#include <Wire.h>

#include "config.h"

#define SerialLog SerialUSB

namespace {

const uint8_t kAccCandidates[2] = {0x18, 0x19};  // CSB selects 0/1
// Sensitivity retune (16 Nov, user feedback): the 16 Nov morning values
// (scale 1000, dead zone 100, active 250) made the basket feel dead —
// the original "too sensitive" complaint was the missing re-zero pinning
// the basket, not the curve itself, so the middle ground sits much
// closer to the original: full sweep at ~35 degrees of tilt, ~8 px of
// basket travel per 10 degrees.
const int32_t kTiltScale = 600;                  // delta for full deflection
const int32_t kTiltDeadzone = 60;                // dead zone (hand jitter)
const int32_t kTiltActiveMin = 140;              // |delta| for "actively steering"
// On this board/shield mounting the X reading RISES as the board tilts
// left, so without the flip the basket ran the wrong way (user feedback
// 15 Nov). Set +1 if a future board mounts the shield rotated.
const int32_t kTiltSign = -1;

bool i2cPresent(uint8_t addr) {
  Wire.beginTransmission(addr);
  return Wire.endTransmission() == 0;
}

bool accReadRegs(uint8_t addr, uint8_t reg, uint8_t *out, uint8_t n) {
  Wire.beginTransmission(addr);
  Wire.write(reg);
  if (Wire.endTransmission(false) != 0) return false;
  if (Wire.requestFrom(addr, n) != n) return false;
  for (uint8_t k = 0; k < n; k++) out[k] = Wire.read();
  return true;
}

bool accWriteReg(uint8_t addr, uint8_t reg, uint8_t val) {
  Wire.beginTransmission(addr);
  Wire.write(reg);
  Wire.write(val);
  return Wire.endTransmission() == 0;
}

// BMA25x / BMX055 shared data decode: 12-bit left-justified, signed.
int16_t axisRaw(const uint8_t *d, uint8_t idx) {
  int16_t v = (int16_t)(((d[idx * 2 + 1] & 0x0F) << 8) | d[idx * 2]);
  if (v & 0x0800) v -= 0x1000;
  return v;
}

}  // namespace

ImuApp g_imu;

void ImuApp::begin() {
  Wire.begin();
  for (uint8_t ci = 0; ci < 2; ci++) {
    uint8_t cand = kAccCandidates[ci];
    if (!i2cPresent(cand)) continue;
    uint8_t id = 0;
    if (!accReadRegs(cand, 0x00, &id, 1)) continue;  // CHIP_ID
    if (id != 0xFA && id != 0xDE) continue;          // BMA25x / BMX055
    acc_addr_ = cand;
    break;
  }
  if (!acc_addr_) {
    SerialLog.println("imu: no accelerometer on I2C; tilt control off");
    return;
  }
  // Normal mode, +-2g (maximum tilt resolution), 250 Hz filter. These
  // registers are shared by the BMA25x and BMX055 families.
  accWriteReg(acc_addr_, 0x11, 0x00);  // PMU_LPW: normal
  accWriteReg(acc_addr_, 0x0F, 0x00);  // PMU_RANGE: +-2g
  accWriteReg(acc_addr_, 0x10, 0x08);  // PMU_BW: 250 Hz
  available_ = true;
  SerialLog.print("imu: accelerometer ready at 0x");
  SerialLog.println(acc_addr_, HEX);
  calibrate();
}

void ImuApp::calibrate() {
  // Average 16 reads as the neutral holding orientation.
  int32_t sx = 0, sy = 0;
  uint8_t ok = 0;
  for (uint8_t k = 0; k < 16; k++) {
    int16_t x, y, z;
    if (readAcc(x, y, z)) {
      sx += x;
      sy += y;
      ok++;
    }
    delay(20);
  }
  if (ok == 0) return;
  neutral_x_ = sx / ok;
  neutral_y_ = sy / ok;
  smooth_x_ = neutral_x_ * 256;
  calibrated_ = true;
  SerialLog.print("imu: calibrated neutral x=");
  SerialLog.print(neutral_x_);
  SerialLog.print(" y=");
  SerialLog.println(neutral_y_);
}

void ImuApp::rezero() {
  // Instant neutral capture from the smoothed value (no blocking reads).
  // Called when Snack Catch starts: the boot-time neutral reflects however
  // the board happened to sit at power-on, but the player holds it very
  // differently — without this the first small tilt reads as a huge delta
  // and pins the basket at the clamp edge (reported 15 Nov).
  if (!available_ || !calibrated_) return;
  neutral_x_ = smooth_x_ / 256;
  tilt_ = 0;
  tilt_active_ = false;
  SerialLog.print("imu: rezero neutral x=");
  SerialLog.println(neutral_x_);
}

bool ImuApp::readAcc(int16_t &x, int16_t &y, int16_t &z) {
  uint8_t d[6];
  if (!accReadRegs(acc_addr_, 0x02, d, 6)) return false;
  x = axisRaw(d, 0);
  y = axisRaw(d, 1);
  z = axisRaw(d, 2);
  return true;
}

void ImuApp::tick() {
  if (!available_ || !calibrated_) return;
  uint32_t now = millis();
  if (now - last_read_ms_ < 50) return;  // 20 Hz
  last_read_ms_ = now;
  int16_t x, y, z;
  if (!readAcc(x, y, z)) return;
  // EMA smoothing (alpha ~= 0.31 at 20 Hz) for a steady basket; the dead
  // zone absorbs the jitter this lets through, and the shorter lag keeps
  // the basket feeling attached to the hand.
  smooth_x_ = (smooth_x_ * 7 + (int32_t)x * 256) / 8;
  int32_t delta = (smooth_x_ / 256) - neutral_x_;
  if (delta > kTiltDeadzone) delta -= kTiltDeadzone;
  else if (delta < -kTiltDeadzone) delta += kTiltDeadzone;
  else delta = 0;
  int32_t scaled = kTiltSign * ((delta * 100) / kTiltScale);
  if (scaled > 100) scaled = 100;
  if (scaled < -100) scaled = -100;
  tilt_ = (int8_t)scaled;
  tilt_active_ = (delta > kTiltActiveMin || delta < -kTiltActiveMin);
}
