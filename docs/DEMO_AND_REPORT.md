# Demonstration and course report

## New quest demonstration (planned, 30 October)

Follow [QUEST_INTERACTION_PLAN.md](QUEST_INTERACTION_PLAN.md) after implementation. Show DEMO mode: each wearable displays its own four-digit code, users verbally exchange and enter the other's code, both confirm, then the 30-second together timer accumulates Bluetooth evidence. At target, exchange new codes and show points awarded only after both final entries.

Then demonstrate Keep Your Cool: 10-second shared baseline, Truth/Dare selection, one 10-second valid-reading turn per user, live BPM, and baseline-to-round comparison. Both can skip prompts; sensor invalidity pauses. Use the provided stationary truth/dare examples. State that heart-rate changes do not identify lies or attraction and never determine the reward.

These interactions replace the generic together/heart presentation in the older sequence below; they have not been physically demonstrated by this documentation update.

## Preparation

- For the new discovery demonstration, use [DISCOVERY_PLAN.md](DISCOVERY_PLAN.md). Edit compatible profiles, enable both discovery methods, and explicitly end any seeded partnership through the new UI before discovering; do not reset accounts or balances.
- Obtain valid outdoor fixes on both wearables, then enter the classroom. Show **“Near your last GPS location”**, increasing age, and approximate distance based on stored positions. Demonstrate **“Detected nearby”** through direct BLE even without a fresh GPS fix, then invite/accept a partnership before the quest sequence.
- Verify GPS discovery expiry with a controlled-clock automated test; if showing a shortened expiry live, label it as a test configuration. Never change explore's 10-second requirement to make an indoor demo pass.
- Charge both devices and phones. Use the exact tested firmware/app/server versions.
- Confirm API reachability, login, assigned devices, and Bluetooth permissions.
- Configure the actual outdoor geofence and verify GPS before the location demonstration.
- Confirm fingertip sensor placement and invalid-reading feedback.
- Use a labeled fresh demo session. Keep any reset/seed operation separate and explicit; never erase evidence automatically on startup.
- Keep recorded evidence of the full-duration together quest, since the live classroom demo uses shortened durations.

## Suggested demonstration sequence

1. **System introduction:** show both wearable stacks, Android companions, and server dashboard. Explain which device supplies each reading.
2. **Sensor evidence:** show actual GPS validity and live BPM. Remove a finger and demonstrate that the UI marks the reading invalid.
3. **Time together:** both accept a demo session. Show direct peer heartbeat status and accumulating time. Demonstrate a connection interruption/separation and no credit for the gap.
4. **Outdoor exploration:** use a real outdoor location and both GPS fixes. If presenting indoors, show a clearly labeled recording from the outdoor test; do not silently substitute simulated coordinates.
5. **Heart challenge:** both accept, hold the fingertip sensors steadily, and show the live graph. The activity is optional social context; the system measures valid shared participation, not attraction.
6. **Reward:** show one award per person, level increase, badge purchase, and unchanged XP after spending points.
7. **Resilience:** briefly disconnect phone internet, show queued records, restore connectivity, and demonstrate no duplicate points.

## Report outline

1. Problem, scope, and success criteria.
2. Hardware inventory and why TinyScreen+ serves as processor/display.
3. Processor resources and constraints: memory budget, sampling deadlines, power, display limits.
4. Bus/interface design: SPI device selection, I²C multiplexer, GPS serial, Bluetooth transport, interrupt/polling choices.
5. Firmware state machines and actual BLE role/scheduling results.
6. Phone gateway and server division of responsibilities.
7. Flash record format, recovery, acknowledgement, and duplicate suppression.
8. Quest evidence evaluation and transactional rewards.
9. Test method and measured results: GPS fix behavior, valid pulse acquisition, BLE intervals, end-to-end latency, runtime, failure recovery.
10. Limitations and improvements supported by evidence.

## Evidence to capture

- Assembly photos with labels and exact revisions.
- Pin-use table and measured working library versions.
- Timing diagram based on actual peer/phone communication logs.
- Example real telemetry with personal identifiers removed.
- Screen/web states for missing GPS, lost contact, peer loss, and queueing.
- Battery/runtime measurements and complete test checklist.
- Tests proving duplicate upload/award/purchase handling.

Do not claim precise Bluetooth ranging, medical-grade heart rate, attraction detection, continuous background phone operation, or production anti-cheating. Explain observed performance and practical limitations plainly.
