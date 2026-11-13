#include "gps_app.h"

GpsApp g_gps;

void GpsApp::begin() {
  pinMode(GPS_SYSONPin, INPUT);
  digitalWrite(GPS_ONOFFPin, LOW);
  pinMode(GPS_ONOFFPin, OUTPUT);
  delay(100);

  // Wake pulses until SYS_ON (same sequence as the TinyCircuits GPSLogger).
  uint8_t pulses = 0;
  while (digitalRead(GPS_SYSONPin) == LOW && pulses < 30) {
    digitalWrite(GPS_ONOFFPin, HIGH);
    delay(5);
    digitalWrite(GPS_ONOFFPin, LOW);
    delay(100);
    pulses++;
  }
  soft_serial_ = new SoftwareSerial(GPS_RXPin, GPS_TXPin);
  soft_serial_->begin(9600);
}

void GpsApp::tick() {
  if (soft_serial_ == nullptr) return;
  while (soft_serial_->available()) {
    char c = (char)soft_serial_->read();
    chars_++;
    gps_.encode(c);
  }
}

GpsFix GpsApp::fix() {
  GpsFix out{};
  unsigned long age;
  long lat, lon;
  gps_.get_position(&lat, &lon, &age);
  out.satellites =
      gps_.satellites() == TinyGPS::GPS_INVALID_SATELLITES ? 0 : (uint8_t)gps_.satellites();
  bool has = lat != TinyGPS::GPS_INVALID_ANGLE && lon != TinyGPS::GPS_INVALID_ANGLE &&
             age != TinyGPS::GPS_INVALID_AGE;
  out.valid = has && age < GPS_FIX_STALE_MS;
  out.age_ms = has ? (age > 0xFFFF ? 0xFFFF : (uint16_t)age) : 0xFFFF;
  if (has) {
    // TinyGPS (v13) returns hundred-thousandths of a degree; records use 1e6.
    out.lat_e6 = (int32_t)lat * 10;
    out.lon_e6 = (int32_t)lon * 10;
  } else {
    out.lat_e6 = 0x7FFFFFFF;
    out.lon_e6 = 0x7FFFFFFF;
  }
  return out;
}
