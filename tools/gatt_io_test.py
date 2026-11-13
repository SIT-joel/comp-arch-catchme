"""Full GATT I/O test against the wearable: subscribe to UART notifications,
write a HELLO frame, listen for telemetry frames. Exercises both directions
exactly like the Android app does."""
import asyncio
import bleak

ADDRESS = "01:80:E1:00:34:12"
UART_SERVICE = bleak.normalize_uuid_str("6e400001-b5a3-f393-e0a9-e50e24dcca9e")
UART_TX = bleak.normalize_uuid_str("6e400002-b5a3-f393-e0a9-e50e24dcca9e")  # phone writes
UART_RX = bleak.normalize_uuid_str("6e400003-b5a3-f393-e0a9-e50e24dcca9e")  # device notifies


def crc8(d: bytes) -> int:
    crc = 0
    for b in d:
        crc ^= b
        for _ in range(8):
            crc = ((crc << 1) ^ 0x07) & 0xFF if (crc & 0x80) else (crc << 1) & 0xFF
    return crc


def hello_frame() -> bytes:
    f = bytearray(8)
    f[0] = 0xA5
    f[1] = 0x01
    f[2] = 0x01  # MSG_HELLO
    f[3] = 0x01  # msg id
    f[4] = 0     # frag idx
    f[5] = 1     # frag count
    f[6] = 0     # chunk len
    f[7] = crc8(bytes(f[:7]))
    return bytes(f)


notifications = []


def handler(sender, data):
    notifications.append(data)
    print("NOTIFY:", data.hex(), flush=True)


async def main():
    print("scanning...", flush=True)
    device = None
    for _ in range(6):
        device = await bleak.BleakScanner.find_device_by_address(ADDRESS, timeout=4.0)
        if device:
            break
    if not device:
        print("BOARD NOT FOUND", flush=True)
        return
    client = bleak.BleakClient(device)
    await client.connect(timeout=8.0)
    print("connected:", client.is_connected, flush=True)
    try:
        await client.start_notify(UART_RX, handler)
        print("subscribed to", UART_RX, flush=True)
        await client.write_gatt_char(UART_TX, hello_frame(), response=False)
        print("HELLO written", flush=True)
        for i in range(12):
            await asyncio.sleep(1)
            if notifications:
                print(f"t+{i+1}s: {len(notifications)} notifications so far", flush=True)
    finally:
        try:
            await client.stop_notify(UART_RX)
            await client.disconnect()
        except Exception:
            pass
    print(f"TOTAL notifications: {len(notifications)}", flush=True)


asyncio.run(main())
