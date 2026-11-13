"""PC-as-fake-peer transmitter (FIXTURE — clearly labeled test tool).

Advertises CATCHME-format manufacturer payloads from the PC's BLE dongle so
a wearable's RECEIVE path can be validated without a second board:
  - quest heartbeat: [0x30 LE company][0xC5][device][counter LE16][0,0]
  - discovery advert: [0x30 LE company][0xC6][version][token LE16]
Fixtures never become production evidence (docs/AGENTS.md); this tests
radio reception only, and anything the wearable logs from it is test data.

Usage: py -3 tools/fake_peer_adv.py [seconds]   (default 90)
"""

import asyncio
import sys
import time

import winrt.windows.devices.bluetooth.advertisement as adv

COMPANY_ID = 0x0030  # ST — same company id the boards use


def heartbeat_payload(device: int, counter: int) -> bytes:
    return bytes([0xC5, device, counter & 0xFF, (counter >> 8) & 0xFF, 0, 0])


def discovery_payload(token: int) -> bytes:
    return bytes([0xC6, 0x01, token & 0xFF, (token >> 8) & 0xFF])


async def main() -> None:
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 90.0

    heart = adv.BluetoothLEAdvertisementPublisher()
    heart.advertisement.manufacturer_data.append(
        _mfr(heartbeat_payload(1, 1)))
    # A second publisher for discovery; only one runs at a time (Windows
    # allows multiple publishers but alternating keeps payloads distinct).
    disc = adv.BluetoothLEAdvertisementPublisher()

    counter = 100
    t0 = time.time()
    use_heart = True
    heart.start()
    print(f"advertising fake CATCHME-1 heartbeats for {seconds:.0f}s "
          "(alternating with discovery token 61495 every 3s)", flush=True)

    while time.time() - t0 < seconds:
        await asyncio.sleep(3.0)
        counter += 1
        try:
            if use_heart:
                heart.stop()
                disc.advertisement.manufacturer_data.clear()
                disc.advertisement.manufacturer_data.append(
                    _mfr(discovery_payload(61495)))
                disc.start()
            else:
                disc.stop()
                heart.advertisement.manufacturer_data.clear()
                heart.advertisement.manufacturer_data.append(
                    _mfr(heartbeat_payload(1, counter)))
                heart.start()
        except Exception as exc:
            print("publisher swap:", exc, flush=True)
        use_heart = not use_heart

    try:
        heart.stop()
    except Exception:
        pass
    try:
        disc.stop()
    except Exception:
        pass
    print("done", flush=True)


def _mfr(payload: bytes):
    m = adv.BluetoothLEManufacturerData()
    m.company_id = COMPANY_ID
    from winrt.windows.storage.streams import DataWriter
    w = DataWriter()
    w.write_bytes(bytes(payload))
    m.data = w.detach_buffer()
    return m


if __name__ == "__main__":
    asyncio.run(main())
