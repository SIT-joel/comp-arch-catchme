// Bisect step 3: replicate FlashQueue structure (SPIFlash as class member).
#include <SPI.h>
#include <SPIMemory.h>

class FakeQueue {
 public:
  bool begin() {
    SerialUSB.println("fq2: cs pin");
    pinMode(5, OUTPUT);
    digitalWrite(5, HIGH);
    SerialUSB.println("fq2: flash.begin");
    if (!flash_.begin()) { SerialUSB.println("fq2: begin FAIL"); return false; }
    SerialUSB.println("fq2: begin OK");
    return true;
  }
 private:
  SPIFlash flash_{5};
};

FakeQueue g_queue;

#define SerialMonitorInterface SerialUSB
void setup() {
  SerialMonitorInterface.begin(115200);
  for (uint32_t w = 0; w < 60000 && !SerialMonitorInterface; w += 100) delay(100);
  SerialMonitorInterface.println("bisect: attached");
  SerialMonitorInterface.println("bisect: queue init");
  g_queue.begin();
  SerialMonitorInterface.println("bisect: queue done");
}
void loop() { delay(1000); }
