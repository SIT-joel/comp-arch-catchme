# Catch Me — course prototype

A computer architecture course prototype for making friends: two TinyScreen+ wearables (with a tamagotchi-style digital pet each) detect direct Bluetooth proximity, two Android phones relay evidence and GPS fixes to a FastAPI server, and the web app awards server-owned points/XP for shared quests. Quest set: **together** (mutual PIN), **explore** (landmark visit via phone GPS), **quiz** (Know-Your-Partner). Each wearable also plays a 3-lane tilt-controlled snack-catching game on its accelerometer.

**Deadline:** 28 November 2026. **Current state:** see [Progress](docs/PROGRESS.md) — all layers implemented and hardware-verified: dual-phone E2E (proximity, explore, quiz, care, XP awards, achievements), pet system live on both boards, tilt mini-game on both boards.

## Start here

The v2 product revision (6 Nov 2026, user-directed; see [AGENTS.md](AGENTS.md)) supersedes older documents where they conflict: **phone GPS** replaces the wearable GPS shield, the **heart-rate quest is removed** (no sensor in the required stack), a **digital pet** lives on each board (server-owned XP, daily care cap), and the landmark **raid quest was removed** on 14 Nov (board-to-board sustained link drops at 23-30 s — a documented hardware wall).

1. Read [AGENTS.md](AGENTS.md), then the [implementation plan](docs/IMPLEMENTATION_PLAN.md).
2. Tooling: [tools and setup](docs/TOOLS_AND_SETUP.md); portable arduino-cli toolchain lives in `tools/arduino-cli/` (git-ignored).
3. **Firmware build/flash/verify recipe: [firmware/README.md](firmware/README.md)** — pinned toolchain, required core patches, per-board build flags, flash scripts, boot verification, tilt tuning.
4. Local stack quickstart: `docker compose -f infra/docker-compose.yml up -d db`, then migrations/seed/server per [backend/README.md](backend/README.md). Web: `cd web && npm install && npm run dev`.

## Repository layout

| Path | Contents |
|---|---|
| `firmware/probes/` | Stage 1 hardware probes (screen, BLE multi-role, GPS, flash) |
| `firmware/catch_me_app/` | Main wearable firmware modules (pet, BLE proximity, quests, tilt game) |
| `firmware/core-patch/`, `firmware/linker/` | REQUIRED SAMD core patches (see [firmware/README.md](firmware/README.md)) |
| `backend/` | FastAPI + SQLAlchemy + Alembic + tests + seed |
| `web/` | React/TypeScript dashboard, live graph, shop |
| `android/` | Kotlin/Compose companion app source |
| `infra/` | Docker Compose, Dockerfiles, nginx config |
| `docs/` | Specifications, plans, OpenAPI (`openapi.json`), progress log |

## Critical constraints

- No board modifications or soldering. The Wi-Fi shield is out of scope for this implementation.
- Direct wearable-to-wearable Bluetooth detection is required. A phone connection is not partner-presence evidence.
- Bluetooth peer detection alongside phone communication is **not yet physically verified**. Resolve this before promising live end-to-end behavior.
- Wearable GPS (ASD2501) and AST1041 heart rate only in the real demonstration — no phone GPS or synthetic sensor data.
- GLM is the implementation assistant, not a runtime dependency of the product.

## Documents

| Document | Purpose |
|---|---|
| [Project specification](docs/PROJECT_SPEC.md) | Product behavior, scope, quests, acceptance criteria |
| [Discovery implementation plan](docs/DISCOVERY_PLAN.md) | Current GLM task: nearby discovery, GPS fallback, profiles, partnerships |
| [Hardware](docs/HARDWARE.md) | Borrow/keep/return list, pin audit, physical checks |
| [Architecture](docs/ARCHITECTURE.md) | Device, Android, server, web, storage responsibilities |
| [Interfaces](docs/INTERFACES.md) | Initial API and telemetry contracts |
| [Tools and setup](docs/TOOLS_AND_SETUP.md) | Development tools, installation sources, checks |
| [Implementation plan](docs/IMPLEMENTATION_PLAN.md) | Stages and dates |
| [Test plan](docs/TEST_PLAN.md) | Software tests and physical acceptance checks |
| [Progress](docs/PROGRESS.md) | Actual state, unresolved questions, handoff log |
| [Demo and report](docs/DEMO_AND_REPORT.md) | Demo sequence and architecture report outline |

## Critical constraints

- No board modifications or soldering. The Wi-Fi shield is out of scope.
- Direct wearable-to-wearable Bluetooth detection is required. A phone connection is not partner-presence evidence.
- Location comes from **phone GPS fixes relayed with telemetry** (true fix ages; never fabricated). The wearable ASD2501 GPS shield is not part of the product.
- The heart-rate quest is removed; records honestly report `hr_valid=false`. No pulse sensor in the required stack.
- Quest set: `together`, `explore`, `quiz` (raid removed 14 Nov — hardware wall, see [Progress](docs/PROGRESS.md)).
- XP/points are server-owned and awarded exactly once per completed session; the wearable owns cosmetic pet state only (daily care capped at +10 XP/user/day).
- Show freshness/age honestly everywhere; display invalid or stale readings with their reason.
- GLM is the implementation assistant, not a runtime dependency of the product.

Documentation assumptions and pending decisions are recorded in [Progress](docs/PROGRESS.md). Do not treat planned behavior as a passed test.
