"""PC-as-relay: put a wearable into discovery mode over GATT (TEST TOOL).

Stands in for the phone link on a board that has no phone bound nearby
(board 2 in the single-phone bench). Clearly labeled test harness — the
real product path is always phone -> wearable (docs/DISCOVERY_PLAN.md).

Connects during an advertising window, subscribes to the UART service,
sends one framed MSG_DISCOVERY_MODE [ver=1][mode][token LE16] and waits
for the MSG_DISCOVERY_ACK echo.

Usage: py -3 tools/discovery_mode_relay.py <address> <mode 0|1> <token>
"""

import asyncio
import sys

import bleak

UART_TX = bleak.normalize_uuid_str("6e400002-b5a3-f393-e0a9-e50e24dcca9e")
UART_RX = bleak.normalize_uuid_str("6e400003-b5a3-f393-e0a9-e50e24dcca9e")

MSG_DISCOVERY_MODE = 8
MSG_DISCOVERY_ACK = 11


def crc8(data: bytes, seed: int = 0x00) -> int:
    crc = seed
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = ((crc << 1) ^ 0x07) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc


def frame(msg_id: int, msg_type: int, payload: bytes) -> bytes:
    header = bytes([0xA5, 0x01, msg_type, msg_id, 0x00, 0x01, len(payload)])
    return header + bytes([crc8(header + payload)]) + payload


acks = []


def handler(sender, data):
    print("NOTIFY:", data.hex(), flush=True)
    # Reassemble trivially: a complete single-fragment message.
    if len(data) >= 9 and data[0] == 0xA5:
        mtype = data[2]
        chunk = data[6]
        body = data[8:8 + chunk]
        if crc8(data[:7] + body) == data[7]:
            if mtype == MSG_DISCOVERY_ACK and len(body) >= 2:
                acks.append((body[0], body[1]))
                print(f"DISCOVERY_ACK: version={body[0]} mode={body[1]}", flush=True)


async def main():
    address = sys.argv[1] if len(sys.argv) > 1 else "01:80:E1:00:34:13"
    mode = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    token = int(sys.argv[3]) if len(sys.argv) > 3 else 0

    payload = bytes([1, mode, token & 0xFF, (token >> 8) & 0xFF])
    client = bleak.BleakClient(address, timeout=10.0)
    for attempt in range(6):
        try:
            await client.connect()
            break
        except Exception as exc:
            print(f"connect attempt {attempt + 1}: {exc!r}", flush=True)
            await asyncio.sleep(1.5)
    else:
        print("CONNECT FAILED (board may be mid-TDD-cycle; retry)", flush=True)
        return
    print("connected; subscribing", flush=True)
    await client.start_notify(UART_RX, handler)
    await asyncio.sleep(0.3)
    frame_bytes = frame(1, MSG_DISCOVERY_MODE, payload)
    print("writing:", frame_bytes.hex(), flush=True)
    await client.write_gatt_char(UART_TX, frame_bytes, response=False)
    for _ in range(12):
        await asyncio.sleep(0.5)
        if acks:
            break
    await client.disconnect()
    print("ACK RECEIVED" if acks else "NO ACK (board logs would tell why)", flush=True)


asyncio.run(main())
