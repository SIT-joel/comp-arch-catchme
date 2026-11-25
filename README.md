# Catch Me

Catch Me is a two-wearable, two-phone social quest prototype with a digital pet system, real-time companion relay, FastAPI backend, PostgreSQL database, and React web dashboard.

Two users wear **TinyScreen+** devices that exchange direct Bluetooth Low Energy (BLE) peer presence advertisements, relay telemetry and phone GPS fixes through their paired Android phones, complete shared timed/location/quiz quests, earn server-authoritative points and XP, care for their wearable tamagotchi-style pets, and unlock badges.

---

## System Architecture

```text
Wearable A (TinyScreen+, ID=1) <--- direct BLE peer ads (0xC5 / 0xC6) ---> Wearable B (TinyScreen+, ID=2)
           | BLE (Nordic UART)                                                       | BLE (Nordic UART)
     Android Phone A                                                           Android Phone B
           | HTTPS (+ CF Access headers)                                             | HTTPS (+ CF Access headers)
           +---------------------------- Cloudflare Tunnel --------------------------+
                                         (cloudflared)
                                               |
                                  http://host.docker.internal:8000
                                               |
                                    FastAPI Backend (--workers 1)
                                       |                   |
                                  PostgreSQL 17      Static Web UI
                                   (infra db)        (web/dist or :8080)
```

### Component Responsibilities

| Component | Path | Role |
|---|---|---|
| **Wearable Firmware** | `firmware/catch_me_app/` | Arduino C++ firmware on TinyScreen+ (`SAMD21`) + BlueNRG-MS (`ASD2116`), NOR Flash (`ASD2202-R-F`), Wireling adapter (`ASD2022`), and accelerometer (`ASD2511-R-A`). Runs a time-division BLE scheduler alternating phone GATT and peer scanning/advertising, buffers telemetry in flash (`flash_queue`), renders quest timers/PINs and the digital pet UI, and runs the tilt-controlled **Snack Catch** mini-game. |
| **Android App** | `android/` | Native Kotlin + Jetpack Compose companion app (`BleLink`, `QueueDb`, `AppModel`). Maintains the BLE UART link to the user's own wearable, attaches true phone GPS fixes (`fix_age_ms`) to relayed telemetry, buffers uploads in Room, pushes session/PIN/pet state to the board, and renders quest progress and completion screens. |
| **Backend API** | `backend/` | FastAPI + SQLAlchemy + Alembic + PostgreSQL (`--workers 1` for in-memory SSE fan-out). Enforces server-authoritative quest evidence intervals, mutual PIN checks, once-per-session `+100` points / `+100` XP awards, daily pet care cap (`+10 XP` per user per day), compatibility-based discovery, and transactional badge shop purchases. |
| **Web Frontend** | `web/` | React + TypeScript + Vite SPA showing paired dashboard state, live quest timers, badge shop, nearby discovery, and transaction history. Built into `api.Dockerfile` (`/srv/web/dist`) and also runnable standalone via `web.Dockerfile` or Vite dev server. |
| **Infrastructure** | `infra/` | Docker Compose definitions for PostgreSQL (`db`), FastAPI + bundled web (`api`), standalone Nginx frontend (`web`), and Cloudflare Tunnel (`cloudflared`). |

### Core Quest Set

- **`together` (Together Time)**: Cooperative 4-digit start PIN entry on both wearables, direct wearable-to-wearable BLE proximity accumulation (`20 s` max peer gap), and 4-digit end PIN entry before awards (`30 s` demo / `600 s` normal).
- **`explore` (Outdoor Visit)**: Direct wearable BLE proximity plus valid phone GPS fixes from both participants inside the configured geofence radius (`1000 m` default, `30 s` max fix age; `20 s` demo / `120 s` normal).
- **`quiz` (Know-Your-Partner)**: Synchronized multi-question partner trivia entered via the wearable/app (`5` questions).

---

## Repository Layout

- `android/` — Android Studio / Gradle Kotlin Compose project (`com.catchme.app`)
- `backend/` — FastAPI application (`app/`), Alembic migrations (`alembic/`), seed script (`seed.py`), unit & integration tests (`tests/`)
- `firmware/` — Wearable sketch (`catch_me_app/`), vendored `STBLE` library (`lib/STBLE/`), SAMD SPI patch (`core-patch/`), and `.noinit` linker scripts (`linker/tinyscreen_p/`)
- `infra/` — `docker-compose.yml`, `api.Dockerfile`, `web.Dockerfile`, `nginx.conf`
- `web/` — React + TypeScript + Vite web application
- `scripts/` — Environment probe scripts (`check-tools.ps1`, `check-tools.sh`)
- `tools/` — Serial inspection, firmware flash, and bench helper scripts

---

## Prerequisites

- **Docker Engine / Docker Desktop** with Compose v2 (`db`, `api`, `web`, `cloudflared`)
- **Python 3.12+** (backend local dev & tests)
- **Node.js 22 LTS + npm** (web frontend build/tests)
- **Android SDK + JDK 17/21 + Gradle** (building `app-debug.apk`)
- **Arduino CLI** + TinyCircuits SAMD board package (`1.1.0`) for flashing TinyScreen+ boards
- *(Optional)* A **Cloudflare Zero Trust** tunnel and Access service token for HTTPS mobile connectivity outside LAN

Check available CLI tools with:

```powershell
# Windows
./scripts/check-tools.ps1
```

```bash
# Linux / macOS / WSL
./scripts/check-tools.sh
```

---

## Docker Compose Stack & Cloudflare Tunnel

`infra/docker-compose.yml` defines four services:

| Service | Image / Build | Port | Purpose |
|---|---|---|---|
| `db` | `postgres:17-alpine` | `127.0.0.1:5432` | Persistent PostgreSQL database (`catch_me_pgdata` volume) |
| `api` | `infra/api.Dockerfile` | `8000` | Multi-stage image that builds `web/` and serves FastAPI + static UI (`uvicorn --workers 1`) |
| `web` | `infra/web.Dockerfile` | `8080` | Standalone Nginx frontend proxying `/api/` to `api:8000` (SSE buffering disabled) |
| `cloudflared` | `cloudflare/cloudflared:latest` | — | Runs `tunnel --no-autoupdate run --token ${TOKEN}` |

### 1. Configure `infra/.env`

Create `infra/.env` (never commit secrets) with your Cloudflare Tunnel and Access credentials:

```dotenv
SUBDOMAIN=catchme.example.com
TOKEN=<cloudflare-tunnel-token>
CLIENT_ID=<cloudflare-access-service-token-id>
CLIENT_SECRET=<cloudflare-access-service-token-secret>
```

How each variable is used:

- **`TOKEN`**: Authenticates the `cloudflared` container to your Cloudflare Zero Trust tunnel. In the Cloudflare Zero Trust dashboard, configure the tunnel's **Public Hostname** (`https://<SUBDOMAIN>`) to forward traffic to:
  ```text
  http://host.docker.internal:8000
  ```
  Both the `api` container (port `8000`) and any host-run `uvicorn` on port `8000` are reachable at `host.docker.internal:8000` (`extra_hosts: host.docker.internal:host-gateway` is enabled on `cloudflared` and `api`).
- **`SUBDOMAIN`**, **`CLIENT_ID`**, **`CLIENT_SECRET`**: Read at build time by `android/app/build.gradle.kts` from `../infra/.env` to populate `BuildConfig.API_BASE` (`https://$SUBDOMAIN`) and Cloudflare Access headers (`CF_ACCESS_ID`, `CF_ACCESS_SECRET`) so the Android app can authenticate through Cloudflare Access without interactive browser login.

### 2. Start the Stack

Start PostgreSQL, the API/web container, and the Cloudflare Tunnel container:

```bash
docker compose -f infra/docker-compose.yml up -d --build db api cloudflared
```

If you also want the separate Nginx web container on port `8080`:

```bash
docker compose -f infra/docker-compose.yml up -d --build
```

Run database migrations and seed accounts/devices after `db` is healthy (from `backend/`):

```bash
cd backend
python -m alembic upgrade head
python seed.py
```

Verify health:

```bash
curl http://127.0.0.1:8000/api/v1/health
```

> **Note:** `api` runs with `--workers 1` intentionally because Server-Sent Events (SSE) fan-out is held in-memory per process.

---

## Application Build & Test Instructions

### Backend (FastAPI)

```powershell
cd backend
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
```

Edit `backend/.env` with `CM_DATABASE_URL`, `CM_GEOFENCE_LAT`, `CM_GEOFENCE_LON`, and `CM_GEOFENCE_RADIUS_M`, then migrate, seed, and run:

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe seed.py
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
```

Run unit & integration tests (requires PostgreSQL reachable at `CM_TEST_DATABASE_URL`, default port `5433` or configured test DB):

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit tests/integration -q
```

### Web Frontend (React + TypeScript)

```bash
cd web
npm ci
npm run dev       # Local Vite dev server
npm run build     # Typecheck + production bundle (dist/)
npm test          # Vitest suite
```

### Android Companion App

Ensure `infra/.env` has your `SUBDOMAIN`, `CLIENT_ID`, and `CLIENT_SECRET` (optional — launch intent extras `"api_base"`, `"cf_id"`, and `"cf_secret"` can also override them at runtime).

Build the debug APK:

```powershell
cd android
gradle assembleDebug
```

*(If running on Windows with local project toolchains in `tools/android/`, set `JAVA_HOME` and `GRADLE_USER_HOME` appropriately before invoking `gradle.bat assembleDebug`.)*

Output APK:

```text
android/app/build/outputs/apk/debug/app-debug.apk
```

Install onto connected devices via ADB:

```bash
adb -s <device-serial> install -r android/app/build/outputs/apk/debug/app-debug.apk
```

### Wearable Firmware (TinyScreen+)

#### 1. Toolchain & Required Core Patches

Install the TinyCircuits SAMD core and libraries (`arduino-cli` config at `tools/arduino-cli/arduino-cli.yaml`):

```bash
CLI=tools/arduino-cli/bin/arduino-cli.exe
CFG=tools/arduino-cli/arduino-cli.yaml

$CLI --config-file $CFG core update-index
$CLI --config-file $CFG core install TinyCircuits:samd
$CLI --config-file $CFG lib install TinyScreen SPIMemory
```

Copy the vendored `STBLE` library from `firmware/lib/STBLE` into your Arduino user libraries folder (`tools/arduino-cli/data/user/libraries/STBLE`), and apply the two **required** SAMD core patches before compiling for hardware:

1. **Bounded SPI (`firmware/core-patch/SERCOM.cpp`)**: Prevents `transferDataSPI()` hangs on shared `SERCOM1` (display + BlueNRG). Copy to `TinyCircuits/hardware/samd/1.1.0/cores/arduino/SERCOM.cpp`.
2. **`.noinit` Linker Scripts (`firmware/linker/tinyscreen_p/*.ld`)**: Preserves crash breadcrumb telemetry across watchdog resets above the bootloader `.bss` clear range. Copy to `TinyCircuits/hardware/samd/1.1.0/variants/tinyscreen_p/linker_scripts/gcc/`.

#### 2. Compile & Flash Both Wearables

Compile one build per wearable identity (`DEVICE_ID=1` and `DEVICE_ID=2`):

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

Flash both boards via their serial ports (replace `COM4`/`COM7` with your active ports):

```bash
$CLI --config-file $CFG upload --fqbn TinyCircuits:samd:tinyscreen \
  --input-dir tools/build/catch_me_d1 -p COM4 --verify

$CLI --config-file $CFG upload --fqbn TinyCircuits:samd:tinyscreen \
  --input-dir tools/build/catch_me_d2 -p COM7 --verify
```
