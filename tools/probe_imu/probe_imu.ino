// I2C probe + IMU tilt stream (15 Nov): identify the accelerometer/gyro in
// the board stack (HARDWARE.md lists Accelerometer ASD2511-R-A) and verify
// tilt readings before integrating them into the pet mini-game.
//
// TinyCircuits' 9-axis IMU TinyShield uses a Bosch BMX055: three I2C
// sub-chips — accel 0x18/0x19, gyro 0x68/0x69, mag 0x10/0x11 (CSB selects).
// Expected accel chip ID (reg 0x00) = 0xDE.
//
// Output: the I2C scan (found addresses), the accel chip ID, then a 5 Hz
// tilt stream (x/y/z in milli-g) so the tilt-to-move mapping can be tuned.

#include <Arduino.h>
#include <Wire.h>

static uint8_t g_accAddr = 0;
static uint8_t g_chipId = 0;

static bool i2cPresent(uint8_t addr) {
  Wire.beginTransmission(addr);
  return Wire.endTransmission() == 0;
}

static bool accReadRegs(uint8_t reg, uint8_t *out, uint8_t n) {
  Wire.beginTransmission(g_accAddr);
  Wire.write(reg);
  if (Wire.endTransmission(false) != 0) return false;
  if (Wire.requestFrom(g_accAddr, n) != n) return false;
  for (uint8_t k = 0; k < n; k++) out[k] = Wire.read();
  return true;
}

static bool accWriteReg(uint8_t reg, uint8_t val) {
  Wire.beginTransmission(g_accAddr);
  Wire.write(reg);
  Wire.write(val);
  return Wire.endTransmission() == 0;
}

void setup() {
  SerialUSB.begin(115200);
  uint32_t waited = 0;
  while (!SerialUSB && waited < 15000) { delay(100); waited += 100; }
  SerialUSB.println("imu-probe up");
  Wire.begin();

  SerialUSB.println("I2C scan 0x08-0x77:");
  for (uint8_t addr = 0x08; addr < 0x78; addr++) {
    if (i2cPresent(addr)) {
      SerialUSB.print("  found 0x");
      SerialUSB.println(addr, HEX);
    }
  }

  // Accelerometer candidates: BMX055 (0xDE) / BMA25x (0xFA) at 0x18/0x19.
  const uint8_t accCandidates[2] = {0x18, 0x19};
  for (uint8_t ci = 0; ci < 2; ci++) {
    uint8_t cand = accCandidates[ci];
    if (!i2cPresent(cand)) continue;
    uint8_t id = 0;
    Wire.beginTransmission(cand);
    Wire.write(0x00);  // CHIP_ID
    Wire.endTransmission(false);
    Wire.requestFrom(cand, 1);
    if (Wire.available()) id = Wire.read();
    SerialUSB.print("addr 0x");
    SerialUSB.print(cand, HEX);
    SerialUSB.print(" chip id 0x");
    SerialUSB.println(id, HEX);
    if (id == 0xDE || id == 0xFA) {  // BMX055 / BMA25x accelerometer
      g_accAddr = cand;
      g_chipId = id;
    }
  }

  if (!g_accAddr) {
    SerialUSB.println("no accelerometer found; nothing to stream");
    return;
  }
  // Wake to normal mode + +-2g for maximum tilt resolution (1 mg/LSB at
  // 12-bit), 250 Hz filter. The BMA25x and BMX055 share these registers.
  accWriteReg(0x11, 0x00);  // PMU_LPW: normal mode
  accWriteReg(0x0F, 0x00);  // PMU_RANGE: +-2g
  accWriteReg(0x10, 0x08);  // PMU_BW: 250 Hz
  SerialUSB.print("accel ready (chip 0x");
  SerialUSB.print(g_chipId, HEX);
  SerialUSB.println("); streaming tilt (milli-g, +-2g scale)");
}

static int16_t accAxis(uint8_t msbReg) {
  uint8_t b[2];
  if (!accReadRegs(msbReg, b, 2)) return 0;
  // 12-bit signed: MSB reg = bits 11:4, LSB reg high nibble = bits 3:0.
  // Empirical scale on this module: 1 g ~= 1024 counts (17 Nov bench).
  int32_t v = ((int32_t)b[1] << 4) | (b[0] >> 4);
  if (v & 0x0800) v -= 0x1000;  // sign-extend
  return (int16_t)(v * 977 / 1000);  // ~0.98 mg/LSB -> milli-g
}

void loop() {
  if (!g_accAddr) { delay(1000); return; }
  // Burst 0x02..0x07: X LSB/MSB, Y LSB/MSB, Z LSB/MSB.
  uint8_t d[6];
  if (accReadRegs(0x02, d, 6)) {
    // 12-bit signed decode (see accAxis); ~0.98 mg/LSB.
    int32_t xr = ((int32_t)d[1] << 4) | (d[0] >> 4);
    int32_t yr = ((int32_t)d[3] << 4) | (d[2] >> 4);
    int32_t zr = ((int32_t)d[5] << 4) | (d[4] >> 4);
    if (xr & 0x0800) xr -= 0x1000;
    if (yr & 0x0800) yr -= 0x1000;
    if (zr & 0x0800) zr -= 0x1000;
    SerialUSB.print("mg x=");
    SerialUSB.print(xr * 977 / 1000);
    SerialUSB.print(" y=");
    SerialUSB.print(yr * 977 / 1000);
    SerialUSB.print(" z=");
    SerialUSB.println(zr * 977 / 1000);
  }
  delay(200);
}
