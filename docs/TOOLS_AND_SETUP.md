# Required tools and setup

The repository does not install tools automatically. The scripts below inspect tool availability and print versions. They do not contact the server, install packages, alter configuration, or verify hardware.

## Run the checks

Windows PowerShell, from the repository root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\check-tools.ps1
```

The execution-policy option applies to that process only. The script does not change the machine policy.

Linux/WSL, from the repository root:

```sh
bash scripts/check-tools.sh
```

Exit 0 means all required command-line probes were found and returned successfully; exit 1 means at least one needs attention. Optional CLI probes are informational. A tool absent from PATH may still be installed inside an IDE.

## Tool inventory

| Tool | Purpose | Required where | Official source |
|---|---|---|---|
| Git | Version control | Development workstation | <https://git-scm.com/downloads> |
| GLM 5.3-capable coding agent/account | Implementation assistance | Development workstation | <https://z.ai/blog/glm-5.3> |
| Arduino IDE 2 or Arduino CLI | Build/upload sketches | Firmware workstation | <https://www.arduino.cc/en/software> |
| TinyCircuits/SAMD board support | Compile for TinyScreen+ | Firmware workstation | <https://learn.tinycircuits.com/Processors/TinyScreen+_Setup_Tutorial/> |
| Manufacturer peripheral libraries | Display, BLE, GPS, Wireling, pulse, flash | Firmware project | Follow links in `HARDWARE.md` |
| Android Studio with Android SDK | Build/install Android app | Android workstation | <https://developer.android.com/studio> |
| Compatible JDK | Gradle/Android builds | Android workstation | Prefer Android Studio's bundled JDK; match chosen Android Gradle Plugin |
| ADB/platform-tools | Device logs and APK installation | Android workstation | <https://developer.android.com/tools/releases/platform-tools> |
| Node.js LTS and npm | React/TypeScript tooling | Web workstation/build image | <https://nodejs.org/en/download> |
| Python 3 and venv/pip | FastAPI/tests | Backend workstation/build image | <https://www.python.org/downloads/> |
| Docker Engine/Desktop and Compose v2 | Local integration/server deployment | Development host and Linux server | <https://docs.docker.com/compose/install/> |
| Bash | Linux tool checks/deployment commands | Linux/WSL | Distribution package manager |

No global Gradle installation is required; commit and use the Android project's Gradle wrapper. No host PostgreSQL installation is required; run it in Docker. A C/C++ desktop compiler is not a substitute for the SAMD Arduino toolchain.

## Version policy

The implementing agent must choose mutually compatible supported versions from official documentation, pin them in manifests/lockfiles/build images, and record versions in `PROGRESS.md`. This handoff deliberately does not claim an untested combination of current Android Gradle Plugin, Kotlin, JDK, or firmware libraries works.

For reproducibility, record: OS, Git, Arduino IDE/CLI, board package, each firmware library/commit, Android Studio, SDK/minimum Android version, phone OS versions, JDK, Gradle/AGP/Kotlin, Node/npm, Python, Docker/Compose, and database major version.

## Hardware setup

1. Count parts using `HARDWARE.md`; confirm both GPS antennas, both sensor cables, and buzzer model.
2. Use data-capable USB cables. Identify serial ports without flashing arbitrary connected devices.
3. Configure the TinyScreen+ board using manufacturer instructions and first upload a minimal screen/serial example.
4. Enable USB debugging on the two Android phones and authorize the development computer.
5. Confirm Bluetooth and applicable Android permissions. Prefer testing on the actual two phones early.

## Server inputs needed during implementation

- Reachable API hostname/URL and HTTPS setup.
- Linux host access/deployment method and Docker availability.
- Demo account passwords and device provisioning credentials, supplied outside source control.
- Outdoor demo destination coordinates.

Do not block local API development waiting for these inputs. Use localhost, fixtures, and placeholder `.env.example` entries; require actual values before remote demonstration.

## GLM configuration

Select GLM 5.3 in the chosen agent/provider, give the agent this workspace, and paste the prompt from `GLM_START_HERE.md`. Use provider documentation for endpoint/model IDs and key storage. The repository should not depend on a particular agent product, API subscription, or hosted model at runtime.

## Build commands to document once source exists

Record real working commands for firmware compilation/upload, Android debug APK build/install, backend migrations/tests, web build/tests, Compose startup, seeding, and backup/restore. Do not present placeholder commands as already executable. At handoff creation, only the two tool-check scripts exist.
