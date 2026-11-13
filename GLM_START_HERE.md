# Start GLM 5.3 here

Open this folder in your coding agent and select GLM 5.3 using that agent/provider's supported configuration. Model identifiers and credentials are provider-specific; do not assume a universal identifier or put API keys in this repository.

Official model information: <https://z.ai/blog/glm-5.3>

## Initial prompt

Copy the following into the agent:

```text
Implement the Catch Me project in this workspace. Read AGENTS.md, README.md,
docs/PROJECT_SPEC.md, docs/HARDWARE.md, docs/INTERFACES.md, and docs/PROGRESS.md
before making changes. Read docs/DISCOVERY_PLAN.md for the newly approved
extension and follow docs/IMPLEMENTATION_PLAN.md in stages.
Read docs/QUEST_INTERACTION_PLAN.md for the newest quest changes: a 30-second
demo together quest with mutual four-digit start/end PIN exchange on the
wearables, and Keep Your Cool truth-or-dare using a 10-second shared baseline
and two 10-second valid-evidence rounds. No lie verdict or BPM pass threshold.
The primary physical course demo is the Together Bluetooth proximity/PIN flow.
Only one AST1041 pulse sensor is currently borrowed, so Keep Your Cool's
two-participant sensor run remains pending a second real sensor. Keep the
missing reading invalid; do not use synthetic or fixture data in the demo.
Retain stable quest IDs and legacy-session history. Gate awards on the full
interaction flow; a timer reaching target alone cannot award together points.

Extend the existing code; do not rebuild completed scaffolds or repeat setup.
Preserve recorded hardware fixes and the time-division BLE scheduler. Actual
experiments rejected simultaneous scanning and a phone connection. Complete
pending two-board verification while implementing discovery independently.
Do not modify boards or replace direct peer detection with phone detection.
Treat the ASD2123 wearable Wi-Fi shield as unavailable for this implementation;
do not troubleshoot it. Android phones provide internet transport. This is a
scope assumption, not proof that the Wi-Fi board is defective.

Implement editable profiles, mutual age/interest filtering, direct wearable
Bluetooth discovery, and GPS discovery using only wearable fixes. GPS fixes
are fresh through 30 seconds; use the last known fix through 15 minutes with
explicit age labels, then expire it. Never use phone location. Store last-known
fixes with original timestamps on the server, not as artificially fresh records.
Add partner invitations and safe partnership lifecycle/migrations. Preserve
existing data and quest behavior; explore still needs GPS <=10 seconds old.
Use clearly labeled fixtures for independent tests when hardware is absent.
Tell me the exact physical test and required output when user action is needed.

Preserve all fixed requirements, implement the complete three-quest experience,
and update docs/PROGRESS.md at each milestone. Report actual commands and
results without inventing successes. GLM is a development tool only; the app
must not depend on an LLM API at runtime.
```

## Resume prompt

```text
Read AGENTS.md and docs/PROGRESS.md. Inspect the current source and tests.
Continue from the recorded next action without redoing completed work.
Resolve independent work while any physical verification is pending.
Keep the progress log and interface documentation accurate.
```

## First expected output from the implementing agent

- Assessment of existing code, recent evidence, and remaining hardware checks.
- Non-destructive migration and discovery implementation starting with backend tests.
- Preservation of the working BLE scheduler, flash driver, and quest semantics.
- Exact two-device discovery test procedure when hardware is required.

The coding agent cannot infer physical success from a compile, nor access hardware that is not connected to its environment. Hardware evidence must come from actual serial logs and observations supplied or collected during testing.
