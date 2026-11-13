// Stage 1 probe: ASD2501 GPS TinyShield (Rev4) on TinyScreen+.
//
// Verified pin map from TinyCircuits-TinyShield-GPS-ASD2501 GPS.h:
//   A0 = processor TX to GPS, A1 = processor RX from GPS (9600 baud)
//   A2 = GPS SYS_ON status input, A3 = GPS ON_OFF control (pulse to wake)
//
// The probe:
//   1. Wakes the GPS (pulses A3 until SYS_ON goes high).
//   2. Streams raw NMEA lines to SerialUSB (so no-fix behavior is visible).
//   3. Parses with TinyGPS and prints one FIX/NOFIX summary line per 5 s:
//      satellites, HDOP, position, fix age — honest invalid states, no fake data.
//
// Expected serial (115200):
//   gps_probe wake: SYSON=1 after N pulses
//   $GPGGA,... raw NMEA ...
//   FIX t=12000 sats=8 hdop=1.2 lat=43.08xxxx lon=-77.68xxxx age_ms=240
//   NOFIX t=16000 sats=0 last_age=stale  (when no fix: keep visible, never invent)
//
// Outdoors is required for a real fix; indoors expect sats fluctuating and
// NOFIX or fix age growing. Record time-to-first-fix from this output.
//
// Libraries: SoftwareSerialZero + TinyGPS (both from
// TinyCircuits/TinyCircuits-TinyShield-GPS-ASD2501, installed in the
// Arduino user libraries directory).

#include <TinyGPS.h>

#include "SoftwareSerialZero.h"

#define SerialMonitorInterface SerialUSB

const int GPS_ONOFFPin = A3;
const int GPS_SYSONPin = A2;
const int GPS_RXPin = A1;  // data from GPS to processor
const int GPS_TXPin = A0;  // data from processor to GPS
const int GPSBaud = 9600;  // some Rev5 boards use 4800 — switch if NMEA is garbage

SoftwareSerial softSerial(GPS_RXPin, GPS_TXPin);
#define Gps_serial softSerial

TinyGPS gps;

uint32_t startedAt = 0;
uint32_t lastReportAt = 0;
uint32_t charsSeen = 0;
uint32_t firstFixAt = 0;
uint32_t pulseCount = 0;

void gpsInitPins() {
  pinMode(GPS_SYSONPin, INPUT);
  digitalWrite(GPS_ONOFFPin, LOW);
  pinMode(GPS_ONOFFPin, OUTPUT);
}

void gpsOn() {
  while (digitalRead(GPS_SYSONPin) == LOW) {
    digitalWrite(GPS_ONOFFPin, HIGH);
    delay(5);
    digitalWrite(GPS_ONOFFPin, LOW);
    delay(100);
    pulseCount++;
    if (pulseCount > 30) break;  // safety: do not hang forever
  }
}

void setup() {
  SerialMonitorInterface.begin(115200);
  // Wait (bounded) for a host serial connection: SAMD CDC drops early writes.
  for (uint32_t waited = 0; waited < 60000 && !SerialMonitorInterface; waited += 100) delay(100);
  gpsInitPins();
  delay(100);
  gpsOn();
  SerialMonitorInterface.print("gps_probe wake: SYSON=");
  SerialMonitorInterface.print(digitalRead(GPS_SYSONPin) == HIGH ? 1 : 0);
  SerialMonitorInterface.print(" pulses=");
  SerialMonitorInterface.println(pulseCount);
  Gps_serial.begin(GPSBaud);
  startedAt = millis();
}

void loop() {
  // Read everything available; echo raw NMEA lines for transparency.
  while (Gps_serial.available()) {
    char c = Gps_serial.read();
    charsSeen++;
    gps.encode(c);
    SerialMonitorInterface.write(c);
  }

  uint32_t now = millis();
  if (now - lastReportAt >= 5000) {
    lastReportAt = now;
    unsigned long age;
    int year;
    byte month, day, hour, minute, second, hundredths;
    unsigned long statsChars = 0;
    unsigned short sentences = 0, failed = 0;
    long lat, lon;
    gps.get_position(&lat, &lon, &age);
    gps.crack_datetime(&year, &month, &day, &hour, &minute, &second, &hundredths, &age);
    gps.stats(&statsChars, &sentences, &failed);

    if (gps.satellites() != TinyGPS::GPS_INVALID_SATELLITES && gps.satellites() > 0 && age != TinyGPS::GPS_INVALID_AGE && age < 5000) {
      if (firstFixAt == 0) firstFixAt = now;
      SerialMonitorInterface.print("FIX t=");
      SerialMonitorInterface.print(now - startedAt);
      SerialMonitorInterface.print(" ttff_ms=");
      SerialMonitorInterface.print(firstFixAt - startedAt);
      SerialMonitorInterface.print(" sats=");
      SerialMonitorInterface.print(gps.satellites());
      SerialMonitorInterface.print(" lat=");
      SerialMonitorInterface.print(lat == TinyGPS::GPS_INVALID_ANGLE ? 0 : lat / 100000.0, 6);
      SerialMonitorInterface.print(" lon=");
      SerialMonitorInterface.print(lon == TinyGPS::GPS_INVALID_ANGLE ? 0 : lon / 100000.0, 6);
      SerialMonitorInterface.print(" age_ms=");
      SerialMonitorInterface.println(age);
    } else {
      SerialMonitorInterface.print("NOFIX t=");
      SerialMonitorInterface.print(now - startedAt);
      SerialMonitorInterface.print(" sats=");
      SerialMonitorInterface.print(gps.satellites() == TinyGPS::GPS_INVALID_SATELLITES ? -1 : gps.satellites());
      SerialMonitorInterface.print(" age=");
      SerialMonitorInterface.print(age == TinyGPS::GPS_INVALID_AGE ? "invalid" : "stale");
      SerialMonitorInterface.print(" chars=");
      SerialMonitorInterface.print(charsSeen);
      SerialMonitorInterface.print(" sentences=");
      SerialMonitorInterface.print(sentences);
      SerialMonitorInterface.print(" failed_ck=");
      SerialMonitorInterface.println(failed);
    }
  }
}
