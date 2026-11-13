# Hardware inventory and feasibility

## Borrow and retain

Quantities below are **total quantities for two devices**, not necessarily new loans. The user previously selected two complete devices but initially listed parts in the singular. Count actual stock before requesting duplicates.

| Part | Total | Action |
|---|---:|---|
| TinyScreen+ ASM2022 | 2 | Retain; borrow shortfall |
| ST Bluetooth TinyShield ASD2116 | 2 | Retain; existing board confirmed Rev1 |
| GPS TinyShield ASD2501 with antennas | 2 | Retain; existing board confirmed Rev4 |
| Flash TinyShield ASD2202-R-F | 2 | Retain; borrow shortfall |
| Pulse Oximetry Wireling AST1041 | 2 | Retain; one is borrowed now, one more is needed for the two-user heart quest |
| Wireling Adapter TinyShield ASD2022 | 2 | Borrow; user reports two available |
| Compatible rechargeable batteries | 2 | Retain; confirm capacity and condition |
| Buzzer Wireling AST1035 | 2 | Count incoming unit only after confirming model; borrow shortfall |
| Five-pin Wireling cables | 4 | Two per device; user reports one owned, so three additional if that remains the count |
| Micro-USB data cables | 2 | Use existing cables; confirm data capability |

Inventory source inspected: `C:\Users\Joell\Downloads\test\TinyCircuit_Accessories_Oct26.pptx`, slides 2–4. Slide 4 item 24 lists ASD2022. Slide 3 item 15 lists AST1035. The deck lists component types, not confirmed loan quantities or cable stock. No copy of that external file is required to use this handoff.

## Unused / return

- ASD2123 Wi-Fi TinyShield.
- AST2003 Wireling Pi Hat.
- A separate TinyDuino/TinyZero processor, if present in addition to the two TinyScreen+ boards. Do not return the TinyScreen+ processors.
- Accelerometer ASD2511-R-A from a kit, if borrowed and separable under the professor's loan rules.
- Raspberry Pi 4/5 are not used in this architecture. The user's own Pis need not be returned.

Other accessories in the deck are unnecessary. No soldering or hardware modifications are authorized by the chosen design.

## Connection intent

Each stack contains TinyScreen+, BLE, GPS, flash, and Wireling adapter. Connect the pulse sensor and buzzer to separate Wireling ports with separate cables. Confirm exact physical order, connector orientation, GPS antenna placement, and accessible buttons against the boards before assembly.

TinyScreen+ already contains the processor. The Pi Hat is not its Wireling adapter. Use ASD2022.

## Pin audit required before full assembly

Manufacturer documentation lists the following logical connections. Verify them against the actual revisions, SAMD21 board definitions, schematics, and library mappings; some generic TinyDuino documentation labels SPI differently.

| Component | Documented control/bus use | Required check |
|---|---|---|
| ASD2116 BLE | SPI; CS D10; reset D9; IRQ D2 | Keep stock routing; verify host driver and roles |
| ASD2202-R-F flash | SPI; CS D5 | Use SPI transactions and separate chip selects |
| ASD2501 GPS | A0/A1 serial; A2 status; A3 on/off | Confirm Rev4 UART implementation on TinyScreen+; avoid assuming AVR SoftwareSerial works |
| ASD2022 adapter | I²C SDA/SCL; D4 power; mux address 0x70; optional D2/D3 interrupt | Inspect whether optional interrupt routing is populated; prefer polling only when electrically compatible |
| AST1041 pulse | I²C through selected mux channel | Use manufacturer library contact/validity behavior; sample at algorithm-required rate |
| AST1035 buzzer | Port-dependent GPIO | Confirm chosen port does not collide with flash D5 or another signal; check `tone` timer interactions |

Removing Wi-Fi avoids its D2 interrupt conflict with BLE and A3 reset conflict with GPS. It does **not** replace a complete pin/power audit of the remaining stack. Polling in software does not fix an electrical collision.

## Bluetooth gate

Update for the discovery extension: consult the recent physical evidence in `PROGRESS.md` before executing this historical gate. Single-board experiments already established the need for time-division scanning/phone links. Preserve that scheduler and verify two-device timing plus multi-user discovery as specified in [DISCOVERY_PLAN.md](DISCOVERY_PLAN.md); do not treat this checklist as proof that the work has not begun.

1. Identify actual BlueNRG firmware, supported library, board package, and examples.
2. Demonstrate direct A-to-B session heartbeat exchange.
3. Demonstrate each device transferring telemetry to its Android phone.
4. Test both requirements together. Manufacturer support for master/slave roles is not proof that this exact host library supports the required simultaneous connections.
5. Current result: simultaneous scanning/phone operation was rejected in recorded experiments. Use the implemented scheduled alternation with automatic phone reconnect and continued local sampling; validate it with both wearables.
6. To pass, collect at least 10 minutes of stable observations, show partner separation stops evidence, and meet the <=10-second peer-evidence rule. Record phone update latency rather than inventing a rate.
7. If both strategies fail, report the blocker and seek a scope decision. Do not swap to phone-assisted proximity or modify boards without a new user decision.

## Sensor and power checks

- Demonstrate stable fingertip heart-rate readings before attempting the Pocky-style activity. Sensor contact and motion determine whether live readings are valid.
- Do not label the optical pulse waveform as an ECG. BPM alone cannot prove attraction or exercise.
- Test GPS outdoors; record fix acquisition time and behavior when no fix is available.
- Verify flash chip identity and capacity from the actual board/example; do not confuse the -F flash variant with -E EEPROM.
- Measure current/battery runtime with the complete workload. Do not promise runtime from battery capacity alone.
- Ensure buzzer activity does not disrupt sensor acquisition, Bluetooth, or flash writes.

## Primary references

- TinyScreen+: <https://tinycircuits.com/products/tinyscreenplus>
- BLE ASD2116: <https://tinycircuits.com/products/bluetooth-low-energy-tinyshield>
- BLE tutorial/library links: <https://learn.tinycircuits.com/Communication/Bluetooth-Low-Energy_TinyShield_Tutorial/>
- GPS: <https://tinycircuits.com/products/gps-tinyshield>
- Flash: <https://tinycircuits.com/products/flash-memory-tinyshield>
- Wireling adapter: <https://tinycircuits.com/products/wireling-adapter-tinyshield>
- Wireling adapter tutorial: <https://learn.tinycircuits.com/Wirelings/Wireling-Adapter_TinyShield_Tutorial/>
- Pulse sensor design: <https://github.com/TinyCircuits/TinyCircuits-Wireling-Pulse-Oximetry-AST1041>
- Pulse example: <https://learn.tinycircuits.com/Wirelings/Wireling_Healthy_Kit_Tutorial/>
- Buzzer tutorial: <https://learn.tinycircuits.com/Wirelings/Buzzer_Wireling_Tutorial/>

Record exact repository commits and library versions used during implementation in `PROGRESS.md`.
