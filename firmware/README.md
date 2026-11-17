# Catch Me firmware — build, flash, verify

Two TinyScreen+ boards run the same sketch with different `DEVICE_ID`s
(board 1 = miya's device, board 2 = toma's). This is the exact, working
recipe used on the bench; versions are pinned.

## Prerequisites

| Tool | Version | Where |
|---|---|---|
| arduino-cli | 1.5.2-rc.1 | Portable install at `tools/arduino-cli/` (git-ignored) — or any recent arduino-cli on PATH |
| TinyCircuits SAMD core | 1.1.0 | via board manager (step 2) |
| TinyScreen library | 1.1.0 | Arduino Library Manager |
| SPIMemory library | latest 3.x | Arduino Library Manager (flash queue) |
| STBLE | commit `2dcc1d4` | vendored in this repo: `firmware/lib/STBLE/` |

The sketch itself lives in [`catch_me_app/`](catch_me_app/).

## One-time setup (reproducing the toolchain)

```bash
CLI=tools/arduino-cli/bin/arduino-cli.exe        # adjust if on PATH
CFG=tools/arduino-cli/arduino-cli.yaml           # checked in; points data dirs + board URL

# 1. Board platform (TinyCircuits TinyScreen+)
$CLI --config-file $CFG core update-index
$CLI --config-file $CFG core install TinyCircuits:samd

# 2. Vendor BLE library (ASD2116 BlueNRG transport) from the repo
mkdir -p tools/arduino-cli/data/user/libraries
cp -r firmware/lib/STBLE tools/arduino-cli/data/user/libraries/STBLE

# 3. TinyScreen + SPIMemory from the Library Manager
$CLI --config-file $CFG lib install TinyScreen SPIMemory
```

### REQUIRED core patches (build succeeds without them, hardware breaks)

**a) Bounded SPI (`firmware/core-patch/SERCOM.cpp`)** — the stock core's
`transferDataSPI()` spins forever on a stranded RXC flag (display and BlueNRG
share SERCOM1); this is the root cause of the 14 Nov watchdog-crash family.
Copy it over the core:

```bash
cp firmware/core-patch/SERCOM.cpp \
  tools/arduino-cli/data/packages/TinyCircuits/hardware/samd/1.1.0/cores/arduino/SERCOM.cpp
```

**b) Crash-forensics linker scripts (`firmware/linker/tinyscreen_p/*.ld`)** —
adds a real `.noinit` section pinned above the sam_ba bootloader's `.bss` wipe
range; without it the breadcrumb ring is zeroed before the app ever reads it:

```bash
cp firmware/linker/tinyscreen_p/*.ld \
  tools/arduino-cli/data/packages/TinyCircuits/hardware/samd/1.1.0/variants/tinyscreen_p/linker_scripts/gcc/
```

Details and rationale: [`core-patch/README.md`](core-patch/README.md),
[`linker/tinyscreen_p/README.md`](linker/tinyscreen_p/README.md).

## Build

Compile once per board — `DEVICE_ID` selects the device identity:

```bash
$CLI --config-file $CFG compile --fqbn TinyCircuits:samd:tinyscreen \
  --build-path tools/build/catch_me_d1 \
  --build-property "compiler.cpp.extra_flags=-DDEVICE_ID=1" \
  firmware/catch_me_app

$CLI --config-file $CFG compile --fqbn TinyCircuits:samd:tinyscreen \
  --build-path tools/build/catch_me_d2 \
  --build-property "compiler.cpp.extra_flags=-DDEVICE_ID=2" \
  firmware/catch_me_app
```

Expected output line: `Sketch uses ~55-56 KB (21%) of program storage space.`

## Flash

Boards attach over USB; on this bench **COM3 = board 1, COM7 = board 2**
(check `[System.IO.Ports.SerialPort]::GetPortNames()` — Windows re-enumerates).

```bash
$CLI --config-file $CFG upload --fqbn TinyCircuits:samd:tinyscreen \
  --input-dir tools/build/catch_me_d1 -p COM3
$CLI --config-file $CFG upload --fqbn TinyCircuits:samd:tinyscreen \
  --input-dir tools/build/catch_me_d2 -p COM7
```

Or both at once:

```powershell
powershell -ExecutionPolicy Bypass -File tools/flash_both.ps1 `
  -D1Dir tools/build/catch_me_d1 -D2Dir tools/build/catch_me_d2
```

`flash_both.ps1` also kills the serial loggers first — they hold the COM
ports and race uploads (a `Failed uploading: exit status 1` right after a
successful compile almost always means a logger won the race).

## Verify the boot

A bench logger captures each board's serial to `tools/crash_logs/`:

```bash
python tools/crash_logger.py COM3 tools/crash_logs/b1_com3.log   # keep running
python tools/crash_logger.py COM7 tools/crash_logs/b2_com7.log
```

A healthy boot prints (timestamps aside):

```
imu: accelerometer ready at 0x18
imu: calibrated neutral x=-946 y=-368
pet_core: species=0 name=... stage=...
ble: -> ADVERTISING
STAT up=.. adv_rx=.. vbad=0 spit=0 phone=0 peers=.. q=0 gps_chars=0
```

- `imu: reinit (nodata|bus)` — the accelerometer froze mid-play and the
  watchdog recovered it (~2 s hitch; frequent occurrences = hardware issue).
- Non-invasive serial peek (does not reset the board; SAMD ignores DTR):
  `python tools/serial_peek.py COM3 10`.

## The Snack Catch mini-game (tilt control)

3 lanes on the 96 px screen; a tilt FLICK steps one lane (buttons LL/LR step
too, UL exits). Tuning constants if a feel change is needed:

| Constant | File | Meaning |
|---|---|---|
| `kTiltDeadzone` | `catch_me_app/imu_app.cpp` | shake null band, counts (90 ≈ 5°) |
| `kHoldSplit` | `catch_me_app/imu_app.cpp` | vertical-hold threshold for steering-axis choice (X vs Y) |
| `kTiltSign` | `catch_me_app/imu_app.cpp` | mounting direction; flip if a board feels mirrored |
| `CM_GAME_SNACK_MIN_GAP`, `CM_GAME_ENERGY_COST`, `CM_GAME_STEP_MS` | `catch_me_app/config.h` | gameplay pacing |
| commit / re-arm thresholds (`off >= 45`, `off > -20`) | `catch_me_app/pet_core.cpp` `game_move_tilt` | flick detection, relative to the resting hold |

While the game screen is up the board streams a 1 Hz tilt trace:
`imu dbg: ax=Y neutral=.. raw=.. delta=.. tilt=.. act=..` — the driving axis
(X or Y, chosen by hold angle), the rest reference, and the resulting tilt.
Game-start refusals print `pet_core: game refused hungry/sad/energy=<n>` and
show the reason + fixing button on the CARE screen for 2.5 s.

## Troubleshooting

- **`Failed uploading: exit status 1` / `No device found on COMx`** — a
  logger holds the port (kill it and retry immediately) or the board dropped
  off USB (Windows zombie COM handle after a capture process dies mid-read:
  physical replug fixes it).
- **Board resets on every serial open** — it does not; DTR does not reset
  the SAMD21. If a board resets when you attach a monitor, the upload
  double-tap (1200 bps touch) ran, not your terminal.
- **Compile errors in STBLE / SPI timing** — the vendored `firmware/lib/STBLE`
  and the core patch are a pair; do not mix them with stock upstream copies.
- **Watchdog crash dumps all zeros** — the linker patch (b) is missing.
