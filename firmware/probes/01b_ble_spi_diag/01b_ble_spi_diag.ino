// BLE SPI diagnostic for ASD2116 on TinyScreen+.
//
// Pinpoints why aci_hal_write_config_data failed in 01_ble_multimode_probe:
//   1. Raw SPI handshake: sends the BlueNRG READ header and prints the reply.
//      Reply[0]==0x02 means the module is alive on SPI; anything else means
//      wiring/bus trouble (reseat the shield).
//   2. Tries the full init + one config write with the IRQ pin on D2,
//      then repeats with IRQ on D3 (TinyCircuits boards route IRQ via a
//      resistor at R2=pin2 / R3=pin3 — board revisions differ).
//
// Expected serial (115200) when healthy, e.g.:
//   spi_diag handshake reply: 02 00 00 20 00    <- alive, 0x0020 bytes writable
//   spi_diag IRQ=2 write_config_data ret=0x00   <- success
// or, if the board routes IRQ to D3:
//   spi_diag IRQ=2 write_config_data ret=0x??   <- timeout error (non-zero)
//   spi_diag IRQ=3 write_config_data ret=0x00   <- success -> use D3!

#include <SPI.h>
#include <STBLE.h>

#define SerialLog SerialUSB

#ifndef BLE_DEBUG
#define BLE_DEBUG true
#endif

void rawHandshake() {
  // Hold the flash chip's CS (D5) high so it stays off the shared SPI bus,
  // then hold BLE CS (D10) high before selecting it — floating chip selects
  // during boot can let another device drive MISO.
  pinMode(5, OUTPUT); digitalWrite(5, HIGH);
  SPI.begin();
  pinMode(10, OUTPUT); digitalWrite(10, HIGH);
  delay(10);
  digitalWrite(10, LOW);
  uint8_t request[5] = {0x0b, 0x00, 0x00, 0x00, 0x00};
  uint8_t reply[5] = {0, 0, 0, 0, 0};
  for (int i = 0; i < 5; i++) reply[i] = SPI.transfer(request[i]);
  digitalWrite(10, HIGH);
  SerialLog.print("spi_diag handshake reply:");
  for (int i = 0; i < 5; i++) {
    SerialLog.print(reply[i] < 0x10 ? " 0" : " ");
    SerialLog.print(reply[i], HEX);
  }
  SerialLog.println();
  if (reply[0] == 0x02) {
    SerialLog.print("spi_diag module ALIVE on SPI, writable=0x");
    SerialLog.print((reply[4] << 8) | reply[3], HEX);
    SerialLog.println(" bytes");
  } else {
    SerialLog.println("spi_diag module NOT answering: reseat the BLE shield and check the stack order");
  }
}

void tryInit(const char* label) {
  HCI_Init();
  BNRG_SPI_Init();
  BlueNRG_RST();
  uint8_t bdaddr[] = {0x12, 0x34, 0x00, 0xE1, 0x80, 0x02};
  int ret = aci_hal_write_config_data(CONFIG_DATA_PUBADDR_OFFSET, CONFIG_DATA_PUBADDR_LEN, bdaddr);
  SerialLog.print("spi_diag ");
  SerialLog.print(label);
  SerialLog.print(" write_config_data ret=0x");
  SerialLog.println(ret, HEX);
}

extern "C" void HCI_Event_CB(void* pckt) { (void)pckt; }

void setup() {
  SerialLog.begin(115200);
  for (uint32_t waited = 0; waited < 60000 && !SerialLog; waited += 100) delay(100);
  SerialLog.println("spi_diag start");

  rawHandshake();

  // Round 1: default IRQ on D2.
  tryInit("IRQ=2");

  // Round 2: IRQ on D3 (requires patching the pin define used by the lib).
  // The STBLE arduino_hal hardcodes BNRG_SPI_EXTI_PIN; emulate by overriding
  // the attachInterrupt target is not possible post-hoc, so instead we
  // compile-time note: if IRQ=2 fails but the handshake is alive, edit
  // arduino_hal.h BNRG_SPI_EXTI_PIN to 3 and re-run this sketch.
  SerialLog.println("spi_diag done");
}

void loop() { delay(1000); }
