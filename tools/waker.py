"""Screen waker: keeps the given adb devices' screens on and the app foregrounded.

Usage: python waker.py <serial1> <serial2>   (runs 30 min, then exits)
"""
import subprocess, sys, time

ADB = r"C:\Users\Joell\AppData\Local\Android\Sdk\platform-tools\adb.exe"
devs = sys.argv[1:]
end = time.time() + 1800

while time.time() < end:
    for dev in devs:
        try:
            subprocess.run([ADB, "-s", dev, "shell",
                            "input keyevent 224; input keyevent 82; "
                            "am start -n com.catchme.app/.MainActivity"],
                           capture_output=True, timeout=20)
        except Exception as e:
            print(dev, e, flush=True)
    time.sleep(50)
print("waker done", flush=True)
