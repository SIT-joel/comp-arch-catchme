# Patched TinyCircuits SAMD core SERCOM.cpp (REQUIRED for crash resilience)

`transferDataSPI()` originally spun forever on the SERCOM RXC flag. On the
TinyScreen+ the display and the BlueNRG share one SERCOM (SERCOM1), and a
module reset mid-transaction (or bus interleave) strands the flag — the
sketch then hangs silently until the watchdog resets it. Two watchdog crash
dumps (14 Nov: board 2, 52.6 min and 134.7 min uptimes) locate the stall in
this spin, first in the BLE transport and, after that was bounded, aligned
with the display render.

The patch bounds each byte at 50 ms (~6000x a normal byte at 12 MHz):
on timeout return 0xFF (one glitched byte, recovered by CRC/next frame),
drain any late byte from a previously aborted transfer on entry. ISR-context
calls keep the old spin (SysTick cannot preempt an ISR); the ISR drain is
separately capped and the watchdog remains the final net there.

## Install (reproducing a build)

Copy the file over the toolchain's copy:

```
cp firmware/core-patch/SERCOM.cpp \
  <arduino-cli-data>/packages/TinyCircuits/hardware/samd/1.1.0/cores/arduino/SERCOM.cpp
```

Consumers: every SPI.transfer() in every library (TinyScreen display, STBLE
BlueNRG transport, flash). The STBLE transport additionally has its own
bounded path with breadcrumbs (`spi_xfer_bounded`, `spit=` STAT counter).
