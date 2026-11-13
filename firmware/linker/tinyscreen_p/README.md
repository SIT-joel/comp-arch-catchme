# Patched TinyScreen+ linker scripts (REQUIRED for crash forensics)

These are the TinyCircuits SAMD 1.1.0 core's `tinyscreen_p` linker scripts
with one change: a real `.noinit` output section, pinned at `0x20001C00`
(NOBODY's default: the stock script has no `.noinit` at all, and GNU ld's
orphan placement put `.noinit` variables right after `.data` at ~0x20000190).

## Why the address matters

The sam_ba bootloader runs on EVERY reset and zeroes its own `.bss`
(`_szero`..`_ebss` = `0x20000068`..`0x20001bbc` in its ELF). Anything below
`0x20001bbc` is wiped before the app's `setup()` runs. Evidence (14 Nov):
watchdog recoveries always printed "previous life 0 ms" because the orphan
`.noinit` vars were destroyed by the bootloader before the app could read
them. `0x20001C00` sits above the wipe range; the app's `.bss` ends around
`0x20001800`, the heap follows `.noinit`, and the stack is at the top of RAM.

## Install (reproducing a build)

Copy both `.ld` files over the toolchain's copies:

```
cp firmware/linker/tinyscreen_p/*.ld \
  <arduino-cli-data>/packages/TinyCircuits/hardware/samd/1.1.0/variants/tinyscreen_p/linker_scripts/gcc/
```

`boards.txt` selects `flash_with_bootloader.ld` for the TinyScreen+; the
`flash_without_bootloader.ld` copy is kept in sync for completeness.

## Consumers

- `firmware/catch_me_app/crash_diag.{h,cpp}` — no-init breadcrumb ring
  (survives watchdog resets; dumped on the next boot after a watchdog
  recovery).
- `firmware/catch_me_app/watchdog_app.cpp` — `previous_life_ms()` forensics.

Without this patch the build still succeeds, but every forensics value is
silently zero — the ring would be wiped before the first dump.
