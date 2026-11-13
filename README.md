# Catch Me — course prototype

A computer architecture course prototype: two TinyScreen+ wearables collect GPS, heart rate, and direct Bluetooth peer-presence evidence. Two Android phones relay readings to a server. A web app awards points for shared quests.

**Deadline:** 28 November 2026. **Current state:** see [Progress](docs/PROGRESS.md) — backend + web implemented and tested, firmware probes + app compiling, first physical board verified end-to-end for programming; BLE peer gate pending the second device.

## Start here

Newest GLM task: [Quest interaction plan](docs/QUEST_INTERACTION_PLAN.md) — 30-second together demo with mutual four-digit start/end PIN exchange on TinyScreen+, and Keep Your Cool truth-or-dare with live heart-rate comparisons. Planned work; preserve the existing application and hardware results.

The next approved extension is [Nearby discovery](docs/DISCOVERY_PLAN.md): Bluetooth plus fresh/last-known wearable GPS, editable profiles, and partner invitations. GPS is fresh through 30 seconds and usable with age labels through 15 minutes. No phone location. This documentation revision does not claim those features are implemented.

1. Read [AGENTS.md](AGENTS.md), then the [implementation plan](docs/IMPLEMENTATION_PLAN.md).
2. Tooling: [tools and setup](docs/TOOLS_AND_SETUP.md); portable arduino-cli toolchain lives in `tools/arduino-cli/` (git-ignored).
3. Local stack quickstart: `docker compose -f infra/docker-compose.yml up -d db`, then migrations/seed/server per [backend/README.md](backend/README.md). Web: `cd web && npm install && npm run dev`.

## Repository layout

| Path | Contents |
|---|---|
| `firmware/probes/` | Stage 1 hardware probes (screen, BLE multi-role, GPS, flash) |
| `firmware/catch_me_app/` | Main wearable firmware modules |
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

- No board modifications or soldering. Remove the Wi-Fi shield from the wearable stack.
- Direct wearable-to-wearable Bluetooth detection is required. A phone connection is not partner-presence evidence.
- Bluetooth peer detection alongside phone communication is **not yet verified**. Resolve this before promising live end-to-end behavior.
- Preserve live local heart-rate display even if phone transfers must be scheduled.
- Use two borrowed ASD2022 adapters for the heart-rate sensors; the AST2003 Pi Hat is not part of this design.
- GLM is the implementation assistant, not a runtime dependency of the product.

Documentation assumptions and pending decisions are recorded in [Progress](docs/PROGRESS.md). Do not treat planned behavior as a passed test.
