"""Direct-address connect (no scan; Windows dedup suppresses static ADVs),
subscribe to UART notifications, listen while the feeder types on serial."""
import asyncio
import bleak

ADDRESS = "01:80:E1:00:34:12"
UART_TX = bleak.normalize_uuid_str("6e400002-b5a3-f393-e0a9-e50e24dcca9e")
UART_RX = bleak.normalize_uuid_str("6e400003-b5a3-f393-e0a9-e50e24dcca9e")

notifications = []


def handler(sender, data):
    notifications.append(data)
    print("NOTIFY:", data, flush=True)


async def main():
    client = bleak.BleakClient(ADDRESS, timeout=10.0)
    for attempt in range(4):
        try:
            await client.connect()
            break
        except Exception as exc:
            print(f"connect attempt {attempt + 1} failed: {exc!r}", flush=True)
            await asyncio.sleep(2)
    else:
        print("DIRECT CONNECT FAILED", flush=True)
        return
    print("connected:", client.is_connected, flush=True)
    try:
        await client.start_notify(UART_RX, handler)
        print("subscribed; listening 20s (feeder types every 3s)", flush=True)
        for _ in range(20):
            await asyncio.sleep(1)
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass
    print(f"TOTAL notifications: {len(notifications)}", flush=True)


asyncio.run(main())
