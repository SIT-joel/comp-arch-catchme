"""Full-duplex GATT test: subscribe, HELLO, then write multi-fragment
SESSION_STATE-sized messages while the board notifies telemetry.
Reports CRC outcome from the board serial indirectly by holding the link."""
import asyncio
import bleak

ADDRESS = "01:80:E1:00:34:12"
UART_TX = bleak.normalize_uuid_str("6e400002-b5a3-f393-e0a9-e50e24dcca9e")
UART_RX = bleak.normalize_uuid_str("6e400003-b5a3-f393-e0a9-e50e24dcca9e")


def crc8(d: bytes) -> int:
    crc = 0
    for b in d:
        crc ^= b
        for _ in range(8):
            crc = ((crc << 1) ^ 0x07) & 0xFF if (crc & 0x80) else (crc << 1) & 0xFF
    return crc


def frame(msg_type: int, msg_id: int, frag: int, count: int, chunk: bytes) -> bytes:
    f = bytearray(8 + len(chunk))
    f[0] = 0xA5
    f[1] = 0x01
    f[2] = msg_type
    f[3] = msg_id
    f[4] = frag
    f[5] = count
    f[6] = len(chunk)
    f[8:8 + len(chunk)] = chunk
    # CRC input: bytes 0..6 then the chunk (byte 7 itself excluded).
    f[7] = crc8(bytes(f[:7]) + chunk)
    return bytes(f)


def frames_for(msg_type: int, msg_id: int, payload: bytes, spacing: float):
    count = (len(payload) + 11) // 12
    out = []
    for i in range(count):
        chunk = payload[i * 12:(i + 1) * 12]
        out.append(frame(msg_type, msg_id, i, count, chunk))
    return out, count


notifications = []


def handler(sender, data):
    notifications.append(data)


async def main():
    print("scanning...", flush=True)
    device = None
    for _ in range(8):
        device = await bleak.BleakScanner.find_device_by_address(ADDRESS, timeout=4.0)
        if device:
            break
    if not device:
        print("BOARD NOT FOUND", flush=True)
        return
    client = bleak.BleakClient(device)
    await client.connect(timeout=10.0)
    print("connected:", client.is_connected, flush=True)
    try:
        await client.start_notify(UART_RX, handler)
        print("subscribed", flush=True)
        await client.write_gatt_char(UART_TX, frame(1, 1, 0, 1, b""), response=False)
        print("HELLO sent", flush=True)
        await asyncio.sleep(3)
        print(f"after HELLO: {len(notifications)} notifications", flush=True)
        # SESSION_STATE-sized write: type 3, 41-byte payload = 4 fragments
        payload = bytes(range(41))
        for msg_id in range(2, 6):
            frames, count = frames_for(3, msg_id, payload, 0.04)
            for f in frames:
                await client.write_gatt_char(UART_TX, f, response=False)
                await asyncio.sleep(0.04)
            print(f"SESSION_STATE #{msg_id} ({count} frags, 40ms) sent", flush=True)
            await asyncio.sleep(1.5)
        await asyncio.sleep(5)
        print(f"TOTAL notifications: {len(notifications)}", flush=True)
        for n in notifications[:6]:
            print("  rx:", n.hex(), flush=True)
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass


asyncio.run(main())
