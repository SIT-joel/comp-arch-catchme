package com.catchme.app.data

import android.content.Context
import com.catchme.app.ble.BleLink
import com.catchme.app.ble.Frame
import com.catchme.app.ble.Message
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.cancel
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.UUID

/**
 * Application model: owns the BLE link, the persistent queue, and the API.
 *
 * Data path per docs/AGENTS.md: wearable -> (BLE UART) -> queue -> HTTPS ->
 * server; server ACK identities -> wearable. Peer evidence is decoded from
 * the wearable's own records (it observed the partner directly); the phone
 * only maps firmware aliases to server UUIDs/tokens using device state.
 */
class AppModel(private val context: Context, baseUrl: String) {

    val api = Api(baseUrl)
    val ble = BleLink(context)
    private val db = QueueDb.build(context)
    private val scope = CoroutineScope(Dispatchers.IO + Job())

    data class UiState(
        val signedIn: Boolean = false,
        val username: String? = null,
        val userId: String? = null,
        val deviceId: UUID? = null,
        val deviceAlias: Int? = null,
        val partnerDeviceId: UUID? = null,
        val partnerUserId: String? = null,
        val sessionToken: String? = null,
        val sessionId: UUID? = null,
        val lastTick: Long = 0,
        val pendingUploads: Int = 0,
        val lastUploadOk: Boolean? = null,
        val liveBpm: Int? = null,
        val liveBpmValid: Boolean = false,
        // --- Nearby discovery (docs/DISCOVERY_PLAN.md) ---
        val partnered: Boolean = false,
        val partnerName: String? = null,
        val profile: JSONObject? = null,
        val discovery: JSONObject? = null,
        val invitations: JSONObject? = null,
        val boardModeAcked: Boolean = false,
        val discoveryError: String? = null,
        // --- v2: pet + raid ---
        val pet: JSONObject? = null,
        val landmarks: List<LandmarkOpt> = emptyList(),
        val gpsFix: GpsFixView? = null,
        val raidFight: Boolean = false,  // wearable is fighting; phone link paused
        val quiz: QuizView? = null,  // v2 quiz: active 'Know Your Partner' state
    )

    data class LandmarkOpt(val id: String, val name: String)

    /** v2 quiz: the phone renders the question; the wearable is the A-D pad. */
    data class QuizView(
        val active: Boolean,
        val index: Int,          // current question (first unanswered)
        val total: Int,
        val question: String?,
        val options: List<String>,
        val myAnswered: Int,
        val myTotal: Int,
        val partnerAnswered: Int,
        val partnerTotal: Int,
        val completed: Boolean,
        val lastError: String? = null,
    )

    data class GpsFixView(
        val latitude: Double,
        val longitude: Double,
        val fixTimeMs: Long,
        val accuracyM: Float,
    )

    private val _ui = MutableStateFlow(UiState())
    val ui: StateFlow<UiState> = _ui

    // Time anchor state (phone -> device and queue records).
    @Volatile private var timeSynced = false
    @Volatile private var anchorEpoch = 0L
    @Volatile private var anchorUptime = 0L

    private var collectJob: Job? = null
    private var uploaderJob: Job? = Job().also { } // placeholder; started below

    // --- Discovery relay state ---
    // Poll /me/discovery every 5 s while the app is visible (the plan's
    // expiry-driven refresh; SSE alone cannot age results out).
    @Volatile var screenVisible: Boolean = false
    @Volatile private var discoveryTokenValue: Int? = null
    @Volatile private var boardAckedMode: Int = -1  // -1 = no ack yet
    private var discoveryJob: Job? = null
    // v2 raid: the raid-start relay fires once per raid session activation;
    // the link supervisor pauses while the wearables fight (radio is theirs).
    @Volatile private var raidStartSentFor: String? = null
    @Volatile private var raidFightUntil: Long = 0
    private var lastResultsWire: String? = null

    fun login(username: String, password: String, onResult: (Boolean, String?) -> Unit) {
        scope.launch {
            try {
                val out = api.login(username, password)
                val me = api.me()
                val device = me.optJSONObject("device")
                val prefs = context.getSharedPreferences("session", Context.MODE_PRIVATE)
                prefs.edit()
                    .putString("token", api.token)
                    .putString("username", username)
                    .putString("device", device?.optString("id"))
                    .putInt("alias", device?.optInt("firmware_alias") ?: 0)
                    .apply()
                _ui.value = _ui.value.copy(
                    signedIn = true, username = username,
                    userId = me.getJSONObject("user").optString("id"),
                    deviceId = device?.let { UUID.fromString(it.optString("id")) },
                    deviceAlias = device?.optInt("firmware_alias"))
                refreshDeviceState()
                startDiscoveryLoop()
                refreshDiscoveryState()
                refreshPetAndLandmarks()
                startGps()
                onResult(true, null)
            } catch (e: Exception) {
                onResult(false, e.message)
            }
        }
    }

    /**
     * Restore the session persisted by login() (SharedPreferences "session").
     * The token is validated with /me before entering the main screen; a stale
     * token silently falls back to the login screen.
     */
    fun restoreSession(onRestored: () -> Unit = {}) {
        val prefs = context.getSharedPreferences("session", Context.MODE_PRIVATE)
        val token = prefs.getString("token", null) ?: return
        api.token = token
        scope.launch {
            try {
                val me = api.me()
                val device = me.optJSONObject("device")
                _ui.value = _ui.value.copy(
                    signedIn = true,
                    username = prefs.getString("username", null),
                    userId = me.getJSONObject("user").optString("id"),
                    deviceId = device?.let { UUID.fromString(it.optString("id")) },
                    deviceAlias = device?.optInt("firmware_alias"))
                refreshDeviceState()
                startDiscoveryLoop()
                refreshDiscoveryState()
                refreshPetAndLandmarks()
                startGps()
                onRestored()
            } catch (e: Exception) {
                api.token = null
            }
        }
    }

    fun bindDevice(pairingCode: String, onResult: (Boolean, String?) -> Unit) {
        scope.launch {
            try {
                api.bindDevice(pairingCode)
                val me = api.me()
                val device = me.getJSONObject("device")
                val prefs = context.getSharedPreferences("session", Context.MODE_PRIVATE)
                prefs.edit().putString("device", device.getString("id"))
                    .putInt("alias", device.getInt("firmware_alias")).apply()
                _ui.value = _ui.value.copy(
                    deviceId = UUID.fromString(device.getString("id")),
                    deviceAlias = device.getInt("firmware_alias"))
                onResult(true, null)
            } catch (e: Exception) {
                onResult(false, e.message)
            }
        }
    }

    /** Connect the wearable and start the collect/upload loop.
     *
     * The wearable runs a strict time-division radio scheduler (verified on
     * hardware: no scan-while-connected), so it intentionally disconnects
     * every ~8.5 s to scan for peer evidence and re-advertise. The supervisor
     * below reconnects whenever the link drops — docs/ARCHITECTURE.md expects
     * exactly this: reconnect after scheduled radio transitions and keep them
     * distinct from real outages. */
    fun startLink() {
        val alias = _ui.value.deviceAlias ?: return
        ble.connect(alias)
        if (collectJob == null) {
            collectJob = scope.launch { collect() }
            scope.launch { uploaderLoop() }
            scope.launch { stateLoop() }
            scope.launch { linkSupervisor(alias) }
        }
    }

    private suspend fun linkSupervisor(alias: Int) {
        var failedStreak = 0
        while (true) {
            delay(2500)
            // GPS keep-alive: Samsungs throttle the app's location request to
            // a 10-MINUTE interval under battery management (verified 14 Nov:
            // ProviderRequest @2s rewritten to @10m0s0ms — quest fix stamps
            // froze and the explore geofence rejected them). Both phones are
            // also deviceidle-whitelisted; re-request updates every ~20 s so
            // delivery resumes within one keep-alive cycle if the OS scales
            // the interval back.
            keepGpsAlive()
            val state = ble.state.value
            // v2 raid: while the wearables fight they own the radio — the
            // phone must NOT hammer reconnects. Pause until the window ends
            // (the fight is minutes; the wearable relinks after).
            if (System.currentTimeMillis() < raidFightUntil) {
                continue
            }
            if (state is BleLink.State.Idle || state is BleLink.State.Failed) {
                // Back off when the stack keeps refusing scans (observed on the
                // S21+ as persistent SCAN_FAILED_REGISTRATION_FAILED): retrying
                // every 2.5 s only adds failed registrations and holds the wedge.
                ble.connect(alias)  // wearable re-advertises each TDD cycle
                failedStreak = if (state is BleLink.State.Failed) failedStreak + 1 else 0
                if (state is BleLink.State.Failed) {
                    delay((5_000L + (failedStreak * 5_000L).coerceAtMost(25_000L)))
                    continue
                }
            } else if (state is BleLink.State.Scanning) {
                failedStreak = 0
                ble.restartScanIfStale()  // Samsung throttles long-running scans
            }
            // TDD disconnects every cycle; a rebooted board starts with
            // discovery off, so drop the ack and re-send the mode on the
            // next link (4-byte message, negligible cost per window).
            if (state !is BleLink.State.Connected && boardAckedMode != -1) {
                boardAckedMode = -1
                _ui.value = _ui.value.copy(boardModeAcked = false)
            }
        }
    }

    private var fixtureSequence = 0L

    /**
     * DEBUG FIXTURE (never a production path): inject five clearly-labeled
     * synthetic telemetry records into the queue so the queue → upload →
     * server path can be validated on an emulator, which has no Bluetooth.
     * boot_id is prefixed "emulator-fixture" and no session_id is attached,
     * so the server retains them as diagnostics; they can never score quest
     * progress (docs/AGENTS.md fixture rules).
     */
    fun injectFixtureTelemetry() {
        val device = _ui.value.deviceId ?: return
        scope.launch {
            val bootId = "emulator-fixture-boot1"
            for (i in 1..5) {
                fixtureSequence += 1
                val rec = JSONObject()
                    .put("boot_id", bootId)
                    .put("sequence", fixtureSequence)
                    .put("session_id", JSONObject.NULL)
                    .put("uptime_ms", i * 1000L)
                    .put("captured_at", java.time.Instant.now().toString())
                    .put("clock", JSONObject()
                        .put("source", "phone_server_anchor")
                        .put("uncertainty_ms", 500))
                    .put("gps", JSONObject()
                        .put("valid", false)
                        .put("latitude", JSONObject.NULL)
                        .put("longitude", JSONObject.NULL)
                        .put("fix_age_ms", JSONObject.NULL))
                    .put("heart_rate", JSONObject()
                        .put("valid", true)
                        .put("bpm", 72 + i)
                        .put("status", "valid"))
                    .put("peer", JSONObject().put("observed", false))
                db.dao().insert(
                    QueueRow(
                        deviceId = device.toString(),
                        bootId = bootId,
                        sequence = fixtureSequence,
                        sessionId = null,
                        payload = rec.toString(),
                        capturedAtMs = System.currentTimeMillis(),
                    )
                )
            }
            _ui.value = _ui.value.copy(pendingUploads = db.dao().pendingCount())
        }
    }

    private suspend fun collect() {
        ble.messages.collect { msg -> onMessage(msg) }
    }

    private fun onMessage(msg: Message) {
        when (msg.type) {
            Frame.MSG_TELEMETRY -> enqueueTelemetry(msg.payload)
            Frame.MSG_STATUS -> {
                // Boot id echo (16-byte null-terminated string from HELLO).
                val bytes = msg.payload
                val end = bytes.indexOf(0.toByte())
                val id = String(bytes, 0, if (end >= 0) end else bytes.size, Charsets.US_ASCII)
                if (id.isNotBlank()) bootIdCache = id
            }
            Frame.MSG_DISCOVERY_OBS -> handleDiscoveryObs(msg.payload)
            Frame.MSG_INTERACTION_COMMAND -> handleInteractionCommand(msg.payload)
            Frame.MSG_PET_CARE_EVENT -> handlePetCareEvent(msg.payload)
            Frame.MSG_RAID_OUTCOME -> handleRaidOutcome(msg.payload)
            Frame.MSG_QUIZ_ANSWER -> handleQuizAnswer(msg.payload)
            Frame.MSG_DISCOVERY_ACK -> {
                // [ver][mode] — the wearable confirmed its applied mode.
                if (msg.payload.size >= 2 && msg.payload[0].toInt() == 1) {
                    boardAckedMode = msg.payload[1].toInt()
                    _ui.value = _ui.value.copy(boardModeAcked = boardAckedMode == desiredBoardMode())
                }
            }
        }
    }

    private var enqueueLogCount = 0

    private fun enqueueTelemetry(payload: ByteArray) {
        val state = _ui.value
        val bootId = decodeBootId(payload)
        if (enqueueLogCount < 6) {
            enqueueLogCount++
            android.util.Log.i("AppModel",
                "enqueue#${enqueueLogCount}: gpsFix=${state.gpsFix != null} " +
                "bytes=${payload.size} boot=$bootId")
        }
        runCatching {
            val (seq, rec) = RecordCodec.decode(
                payload, bootId ?: "unknown", state.sessionId != null, state.sessionId,
                timeSynced, anchorEpoch, 500)
            // v2: the phone's real GPS fix is the product's only location
            // source; stamp it with its true age (never clamped).
            stampPhoneGps(rec, System.currentTimeMillis())
            val row = QueueRow(
                deviceId = state.deviceId?.toString() ?: return,
                bootId = rec.getString("boot_id"),
                sequence = seq,
                sessionId = state.sessionId?.toString(),
                payload = resolveAliases(rec).toString(),
                capturedAtMs = System.currentTimeMillis())
            db.dao().insert(row)
            _ui.value = _ui.value.copy(pendingUploads = db.dao().pendingCount())
        }.onFailure { android.util.Log.w("AppModel", "enqueue failed (${payload.size}B): ${it.message}") }
    }

    /** Firmware aliases -> server UUIDs/tokens using known device state.
     * When the peer device cannot be resolved (unpaired discovery neighbor),
     * the peer fields are STRIPPED: the server contract requires
     * peer.observed=true to carry a device_id, and an unresolved neighbor
     * has no quest meaning anyway (evidence binds to the session token). */
    private fun resolveAliases(rec: JSONObject): JSONObject {
        val peer = rec.optJSONObject("peer") ?: return rec
        if (!peer.optBoolean("observed")) return rec
        val partner = _ui.value.partnerDeviceId
        val token = _ui.value.sessionToken
        if (partner != null && token != null) {
            peer.put("device_id", partner.toString())
            peer.put("session_token", token)
            peer.put("boot_id", "d${_ui.value.deviceAlias?.let { if (it == 1) 2 else 1 } ?: 0}")
        } else {
            peer.put("observed", false)
            peer.remove("device_id")
            peer.remove("session_token")
            peer.put("boot_id", JSONObject.NULL)
            peer.put("heartbeat_sequence", JSONObject.NULL)
            peer.put("observation_age_ms", JSONObject.NULL)
        }
        return rec
    }

    private fun decodeBootId(payload: ByteArray): String? = bootIdCache

    companion object {
        @Volatile var bootIdCache: String? = null
    }

    private suspend fun uploaderLoop() {
        var validationFailures = 0
        while (true) {
            delay(2000)
            val state = _ui.value
            val device = state.deviceId ?: continue
            val rows = runCatching { db.dao().pending(20) }.getOrDefault(emptyList())
            if (rows.isEmpty()) { validationFailures = 0; continue }
            val batch = JSONArray()
            for (row in rows) batch.put(JSONObject(row.payload))
            try {
                val ack = api.uploadBatch(device, batch)
                // Mark exactly the acknowledged identities as synced.
                val okIds = ArrayList<Long>(rows.size)
                val byIdentity = rows.associateBy { it.bootId to it.sequence }
                for (i in 0 until ack.getJSONArray("accepted").length()) {
                    val a = ack.getJSONArray("accepted").getJSONObject(i)
                    byIdentity[a.getString("boot_id") to a.getLong("sequence")]?.let { okIds.add(it.id) }
                }
                // Duplicates are confirmed persisted too (idempotent no-op).
                for (i in 0 until ack.getJSONArray("duplicates").length()) {
                    val a = ack.getJSONArray("duplicates").getJSONObject(i)
                    byIdentity[a.getString("boot_id") to a.getLong("sequence")]?.let { okIds.add(it.id) }
                }
                if (okIds.isNotEmpty()) {
                    db.dao().markSynced(okIds)
                    sendAck(okIds.size)
                }
                validationFailures = 0
                _ui.value = _ui.value.copy(
                    pendingUploads = db.dao().pendingCount(), lastUploadOk = true, lastTick = System.currentTimeMillis())
            } catch (e: Api.ApiError) {
                // 422 = the server permanently rejected this batch's content
                // (e.g. records from an intermediate firmware build with an
                // invalid heart-rate combination). A batch that fails twice is
                // undeliverable: drop it so it cannot block newer records.
                if (e.status == 422) {
                    validationFailures++
                    if (validationFailures >= 2) {
                        db.dao().markSynced(rows.map { it.id })
                        android.util.Log.w("AppModel",
                            "dropped ${rows.size} undeliverable records after repeated 422")
                        validationFailures = 0
                    }
                }
                _ui.value = _ui.value.copy(lastUploadOk = false)
            } catch (e: Exception) {
                _ui.value = _ui.value.copy(lastUploadOk = false)
            }
        }
    }

    /** Relay server-persisted record count to the wearable (contiguous prefix). */
    private fun sendAck(count: Int) {
        val payload = ByteArray(1 + count * 4)
        payload[0] = count.toByte()
        // Sequences are implied by queue order in this slice; the firmware
        // validates against its own queue, holes are never acked.
        ble.send(Frame.MSG_ACK, payload)
    }

    /** Periodically: device state -> SESSION_STATE + TIME_ANCHOR to wearable. */
    private suspend fun stateLoop() {
        while (true) {
            delay(3000)
            val state = _ui.value
            val device = state.deviceId ?: continue
            runCatching {
                val ds = api.deviceState(device)
                val session = ds.optJSONObject("session")
                val active = session != null && session.getString("state") == "active"
                val token = if (active) session?.optString("token") else null
                // partner_alias present => partnered: keep the discovery
                // mode current even while the app is backgrounded (pairing
                // must stop general discovery on the next phone link).
                if (!ds.isNull("partner_alias")) {
                    if (!_ui.value.partnered) {
                        _ui.value = _ui.value.copy(partnered = true)
                    }
                } else if (_ui.value.partnered) {
                    _ui.value = _ui.value.copy(partnered = false)
                }
                // The partner's device UUID resolves peer observations in
                // relayed telemetry (server contract: peer.device_id).
                val partnerDevice = if (ds.isNull("partner_device_id")) null
                    else UUID.fromString(ds.getString("partner_device_id"))
                _ui.value = _ui.value.copy(partnerDeviceId = partnerDevice)
                _ui.value = _ui.value.copy(
                    sessionToken = token,
                    sessionId = session?.let { UUID.fromString(it.getString("session_id")) })
                if (ble.state.value is BleLink.State.Connected) {
                    // v2 XP visibility: the pet mirror (level/XP) must refresh
                    // after quest awards, not only at sign-in — otherwise the
                    // pet card and the wearable's level stay stale until the
                    // app restarts. Throttled to one fetch per 10 s.
                    val nowMs = System.currentTimeMillis()
                    if (nowMs - lastPetRefreshMs >= 10_000) {
                        lastPetRefreshMs = nowMs
                        refreshPetAndLandmarks()
                    }
                    sendSessionState(ds)
                    sendInteractionState(ds)
                    sendTimeAnchor()
                    sendPartnerInfo(ds)
                    sendPetState()
                    // Ask for STATUS (boot id) until the board answers; records
                    // are otherwise queued with boot_id "unknown", which breaks
                    // per-boot identity once the board reboots.
                    if (bootIdCache == null) {
                        ble.send(Frame.MSG_HELLO, ByteArray(0))
                    }
                    // Keep the wearable's discovery mode in sync (no-op once
                    // acked; resends after reconnects until confirmed).
                    relayModeToBoard(force = false)
                    // v2 quiz: while a quiz session is active, fetch the
                    // per-answerer state and relay the CURRENT question to
                    // the wearable (the question renders here; the wearable
                    // is the A-D pad).
                    if (session?.optString("quest_id") == "quiz") {
                        refreshQuiz(session.getString("session_id"))
                    } else if (_ui.value.quiz?.active == true) {
                        _ui.value = _ui.value.copy(quiz = null)
                    }
                }
            }.onFailure {
                android.util.Log.w("AppModel", "stateLoop failed: ${it.message}")
            }
        }
    }

    // Completions already relayed to the wearable: the server keeps
    // returning the latest completed session forever; without this gate
    // every SESSION_STATE cycle re-sends it (and a rebooted board would
    // re-buzz an old completion).
    private val deliveredCompletions = HashSet<String>()

    private fun sendSessionState(ds: JSONObject) {
        val session = ds.optJSONObject("session")
        val out = ByteArray(17 + 24)
        if (session != null && session.getString("state") == "active") {
            // v2 raid: the moment a raid session activates, tell the wearable
            // to enter raid mode (drop the phone link, fight over the direct
            // connection). Once per session id; the supervisor pauses while
            // the radio belongs to the fight.
            // Contract: the session object's id field is "session_id" (an
            // earlier build read "id", which threw and aborted the whole
            // SESSION_STATE relay whenever a raid session was active).
            val sessionIdStr = session.getString("session_id")
            // Re-send EVERY connected cycle while the raid is active: the
            // fire-once version landed in disconnected TDD windows and the
            // boards never entered raid mode (verified live 12 Nov). The
            // board's raid_start() is idempotent, the fight drops the phone
            // link (stopping the relay naturally), and a rebooted board is
            // re-triggered on its phone's next relink. Session completion
            // (state != active) ends the relay.
            if (session.getString("quest_id") == "raid") {
                raidFightUntil = System.currentTimeMillis() + 4 * 60_000L
                // The fight owns the radio: drop the phone link and hold all
                // reconnects (the paced post-TDD reconnect raced the board's
                // staged raid teardown and starved the board-to-board link —
                // observed live 14 Nov as create_connection-rejected loops).
                ble.pauseReconnects(4 * 60_000L)
                val start = ByteArray(2)
                start[0] = 1
                start[1] = if (session.optBoolean("demo")) 1 else 0
                ble.send(Frame.MSG_RAID_START, start)
                _ui.value = _ui.value.copy(raidFight = true)
                if (raidStartSentFor != sessionIdStr) {
                    raidStartSentFor = sessionIdStr
                    android.util.Log.i("AppModel", "raid-start relayed for $sessionIdStr")
                }
            }
            out[0] = 1
            out[1] = when (session.getString("quest_id")) {
                "together" -> 1; "explore" -> 2; "raid" -> 4; else -> 3 // 3 = legacy heart
            }
            out[2] = if (session.optBoolean("demo")) 1 else 0
            putU32(out, 3, session.optLong("progress_ms"))
            putU32(out, 7, session.optLong("target_ms"))
            out[11] = (ds.optInt("partner_alias", 0)).toByte()
            putU16(out, 12, fnv16(tokenBytes(session.optString("token"))))
            out[14] = 0
        }
        val completion = ds.optJSONObject("completion")
        if (completion != null) {
            val id = completion.optString("completion_event_id", "")
            if (id.isNotEmpty() && !deliveredCompletions.contains(id)) {
                out[14] = 1
                val bytes = id.toByteArray(Charsets.US_ASCII)
                System.arraycopy(bytes, 0, out, 17, minOf(bytes.size, 23))
                deliveredCompletions.add(id)
            }
        }
        ble.send(Frame.MSG_SESSION_STATE, out)
    }

    /** Relay only this account's code plus non-secret phase metadata. */
    private fun sendInteractionState(ds: JSONObject) {
        val session = ds.optJSONObject("session")
        val completion = ds.optJSONObject("completion")
        val isFinished = session == null && completion != null
        val interaction = session?.optJSONObject("interaction")
            ?: completion?.optJSONObject("interaction")
        val out = ByteArray(58)
        out[0] = 1
        if ((!isFinished && (session == null || session.optString("state") != "active")) || interaction == null) {
            ble.send(Frame.MSG_INTERACTION_STATE, out)
            return
        }
        val keepSummary = !isFinished || interaction.optString("quest_id") == "heart_challenge"
        out[1] = if (keepSummary) when (interaction.optString("phase")) {
            "start_pin" -> 1; "timing" -> 2; "end_pin" -> 3
            "baseline" -> 4; "select_prompt" -> 5; "round" -> 6; "summary" -> 7
            else -> 0
        } else 0
        out[2] = 0 // reserved, retained for a future compatible extension
        out[3] = when (interaction.optString("stage")) { "start" -> 1; "end" -> 2; else -> 0 }
        val code = interaction.optString("own_code", "----").take(4).padEnd(4, '-')
            .toByteArray(Charsets.US_ASCII)
        System.arraycopy(code, 0, out, 4, 4)
        putU16(out, 8, interaction.optInt("own_code_version", 0))
        putU16(out, 10, interaction.optInt("partner_code_version", 0))
        out[12] = if (interaction.optBoolean("own_code_confirmed_by_partner")) 1 else 0
        out[13] = if (interaction.optBoolean("partner_code_confirmed_by_me")) 1 else 0
        out[14] = interaction.optInt("round_index", 0).toByte()
        val meId = _ui.value.userId
        out[15] = if (meId != null && interaction.optString("active_user_id") == meId) 1 else 0
        out[16] = when (interaction.optString("prompt_kind")) { "truth" -> 1; "dare" -> 2; else -> 0 }
        var promptText = interaction.optString("prompt", "")
        if (isFinished && interaction.optString("quest_id") == "heart_challenge") {
            val changes = interaction.optJSONObject("results")?.optJSONObject("bpm_changes")
            val own = _ui.value.userId?.let { changes?.optJSONArray(it)?.optInt(0) }
            val other = _ui.value.partnerUserId?.let { changes?.optJSONArray(it)?.optInt(0) }
            if (own != null && other != null) {
                promptText = "YOU ${if (own >= 0) "+" else ""}$own / PARTNER ${if (other >= 0) "+" else ""}$other BPM"
            }
        }
        val prompt = promptText.take(24).toByteArray(Charsets.US_ASCII)
        out[17] = prompt.size.toByte()
        System.arraycopy(prompt, 0, out, 18, prompt.size)
        val sessionId = runCatching { UUID.fromString(interaction.getString("session_id")) }.getOrNull()
        if (sessionId != null) {
            val bb = ByteBuffer.wrap(out, 42, 16).order(ByteOrder.BIG_ENDIAN)
            bb.putLong(sessionId.mostSignificantBits)
            bb.putLong(sessionId.leastSignificantBits)
        }
        ble.send(Frame.MSG_INTERACTION_STATE, out)
    }

    /** Device commands are retried with the same nonce; API idempotency maps
     * that stable command identity to a server UUID. PIN payloads are never
     * written to logs or persisted by the phone. */
    private fun handleInteractionCommand(payload: ByteArray) {
        if (payload.size < 30 || payload[0].toInt() != 1) return
        val kind = payload[1].toInt() and 0xFF
        val stage = when (payload[2].toInt() and 0xFF) { 1 -> "start"; 2 -> "end"; else -> "" }
        val codeVersion = (payload[3].toInt() and 0xFF) or ((payload[4].toInt() and 0xFF) shl 8)
        val nonceBuf = ByteBuffer.wrap(payload, 5, 8).order(ByteOrder.LITTLE_ENDIAN)
        val nonce = nonceBuf.long
        val sessionBuf = ByteBuffer.wrap(payload, 13, 16).order(ByteOrder.BIG_ENDIAN)
        val sessionId = UUID(sessionBuf.long, sessionBuf.long)
        val valueLen = payload[29].toInt() and 0xFF
        if (valueLen > 4 || payload.size < 30 + valueLen) return
        val value = String(payload, 30, valueLen, Charsets.US_ASCII)
        val commandId = UUID.nameUUIDFromBytes(
            "${sessionId}:${_ui.value.deviceAlias ?: 0}:$nonce".toByteArray(Charsets.US_ASCII))
        scope.launch {
            val ok = runCatching {
                when (kind) {
                    1 -> if (stage.isNotEmpty() && valueLen == 4) api.submitInteractionPin(
                        sessionId, stage, value, codeVersion, commandId)
                        else error("invalid PIN command")
                    2 -> if (stage.isNotEmpty()) api.refreshInteractionPin(sessionId, stage, commandId)
                        else error("invalid refresh command")
                    // v2: heart-quest kinds (3 truth / 4 dare / 5 skip) are gone.
                    else -> error("unknown interaction command")
                }
            }.isSuccess
            val ack = ByteArray(10)
            ack[0] = 1
            ByteBuffer.wrap(ack, 1, 8).order(ByteOrder.LITTLE_ENDIAN).putLong(nonce)
            ack[9] = if (ok) 1 else 0
            ble.send(Frame.MSG_INTERACTION_ACK, ack)
        }
    }

    private fun tokenBytes(token: String?): ByteArray =
        (token ?: "").toByteArray(Charsets.US_ASCII)

    /**
     * Relay matched-partner display data to the wearable:
     * [ver=1][nameLen][name<=12][dist_m LE16][flags bit0=dist valid].
     * Name comes from /me (partner display name); distance from the
     * device-state snapshot (both wearables' latest GPS fixes — absent
     * indoors, which the board renders honestly as "dist ?").
     */
    private fun sendPartnerInfo(ds: JSONObject) {
        val name = (_ui.value.partnerName ?: "?").take(12)
        val distRaw = if (ds.isNull("partner_distance_m")) -1.0
                      else ds.optDouble("partner_distance_m", -1.0)
        val dist = if (distRaw in 0.0..65535.0) distRaw.toInt() else -1
        val distValid = dist >= 0
        val nameBytes = name.toByteArray(Charsets.US_ASCII)
        val payload = ByteArray(2 + nameBytes.size + 3)
        payload[0] = 1
        payload[1] = nameBytes.size.toByte()
        System.arraycopy(nameBytes, 0, payload, 2, nameBytes.size)
        val off = 2 + nameBytes.size
        payload[off] = (dist and 0xFF).toByte()
        payload[off + 1] = ((dist shr 8) and 0xFF).toByte()
        payload[off + 2] = if (distValid) 1 else 0
        ble.send(Frame.MSG_PARTNER_INFO, payload)
    }

    private fun sendTimeAnchor() {
        runCatching {
            val t = api.serverTimeMs()
            anchorEpoch = t / 1000
            timeSynced = true
            val payload = ByteArray(6)
            putU32(payload, 0, anchorEpoch)
            putU16(payload, 4, 500)
            ble.send(Frame.MSG_TIME_ANCHOR, payload)
        }
    }

    private fun putU32(a: ByteArray, off: Int, v: Long) {
        a[off] = (v and 0xFF).toByte(); a[off + 1] = ((v shr 8) and 0xFF).toByte()
        a[off + 2] = ((v shr 16) and 0xFF).toByte(); a[off + 3] = ((v shr 24) and 0xFF).toByte()
    }

    private fun putU16(a: ByteArray, off: Int, v: Int) {
        a[off] = (v and 0xFF).toByte(); a[off + 1] = ((v shr 8) and 0xFF).toByte()
    }

    private fun fnv16(data: ByteArray): Int {
        var h = 2166136261u
        for (b in data) { h = h xor (b.toUInt() and 0xFFu); h *= 16777619u }
        return ((h xor (h shr 16)) and 0xFFFFu).toInt()
    }

    private fun refreshDeviceState() {
        scope.launch {
            runCatching {
                val ds = _ui.value.deviceId?.let { api.deviceState(it) } ?: return@launch
                val session = ds.optJSONObject("session")
                _ui.value = _ui.value.copy(
                    sessionToken = session?.optString("token"),
                    sessionId = session?.let { UUID.fromString(it.getString("session_id")) })
            }
        }
    }

    fun questAction(questId: String, demo: Boolean, landmarkId: String? = null, onResult: (Boolean, String?) -> Unit) {
        scope.launch {
            try {
                api.createSession(questId, demo, landmarkId)
                onResult(true, null)
            } catch (e: Exception) {
                onResult(false, e.message)
            }
        }
    }

    fun acceptSession(id: UUID, onResult: (Boolean, String?) -> Unit) {
        scope.launch {
            try { api.acceptSession(id); onResult(true, null) }
            catch (e: Exception) { onResult(false, e.message) }
        }
    }

    fun cancelSession(id: UUID, onResult: (Boolean, String?) -> Unit) {
        scope.launch {
            try { api.cancelSession(id); onResult(true, null) }
            catch (e: Exception) { onResult(false, e.message) }
        }
    }

    // ==================== v2: pet + phone GPS ====================

    /** Refresh the server pet mirror and the raid landmark options. */
    fun refreshPetAndLandmarks() {
        scope.launch {
            try {
                _ui.value = _ui.value.copy(pet = api.pet())
            } catch (e: Exception) {
                android.util.Log.w("AppModel", "pet fetch failed: ${e.message}")
            }
            try {
                val arr = api.landmarks()
                val opts = (0 until arr.length()).mapNotNull { i ->
                    val lm = arr.optJSONObject(i) ?: return@mapNotNull null
                    LandmarkOpt(lm.optString("id"), lm.optString("name"))
                }
                _ui.value = _ui.value.copy(landmarks = opts)
            } catch (e: Exception) {
                android.util.Log.w("AppModel", "landmarks fetch failed: ${e.message}")
            }
        }
    }

    // Phone GPS (v2): the ONLY location source in the product. One shared
    // LocationManager fix stamped onto relayed telemetry with its TRUE age.
    private var gpsListener: android.location.LocationListener? = null
    private var lastGpsReRegisterMs = 0L

    /** Re-register the location listeners WITHOUT dropping the fix. Verified
     * live (14 Nov): both Samsungs (S21+ One UI, S24 FE Android 16) PERMANENTLY
     * stop delivering location updates after a screen off/on cycle — the
     * listener survives but never fires again until the app restarts, which
     * froze every quest's fix stamp (record relays carried a growing fix age
     * and the explore geofence rejected them). Re-requesting updates on the
     * same listener resumes delivery instantly. Called periodically from the
     * state loop; cheap (two provider registrations, no scan). */
    fun keepGpsAlive() {
        val listener = gpsListener ?: return
        val now = System.currentTimeMillis()
        if (now - lastGpsReRegisterMs < 8_000) return
        lastGpsReRegisterMs = now
        try {
            val lm = context.getSystemService(Context.LOCATION_SERVICE) as? android.location.LocationManager
                ?: return
            lm.removeUpdates(listener)
            runCatching {
                lm.requestLocationUpdates(android.location.LocationManager.GPS_PROVIDER,
                    2000L, 1f, listener, android.os.Looper.getMainLooper())
            }
            runCatching {
                lm.requestLocationUpdates(android.location.LocationManager.NETWORK_PROVIDER,
                    5000L, 5f, listener, android.os.Looper.getMainLooper())
            }
            android.util.Log.i("AppModel", "GPS listeners re-registered (keep-alive)")
        } catch (e: SecurityException) {
            android.util.Log.w("AppModel", "GPS keep-alive refused: ${e.message}")
        }
    }

    fun startGps() {
        if (gpsListener != null) return
        lastGpsReRegisterMs = System.currentTimeMillis()
        val lm = context.getSystemService(Context.LOCATION_SERVICE) as? android.location.LocationManager
            ?: return
        val listener = android.location.LocationListener { location ->
            android.util.Log.i("AppModel", "GPS fix: ${location.latitude},${location.longitude} acc=${location.accuracy}")
            _ui.value = _ui.value.copy(
                gpsFix = GpsFixView(
                    latitude = location.latitude,
                    longitude = location.longitude,
                    fixTimeMs = location.time,
                    accuracyM = location.accuracy,
                ),
            )
        }
        try {
            // GPS is the real fix source; network provider is a fallback.
            // Registration (and callbacks) explicitly on the main looper:
            // requestLocationUpdates builds its callback Handler from the
            // CALLING thread, and startGps runs on a dispatcher worker that
            // has no Looper (verified: both registrations failed silently).
            runCatching {
                lm.requestLocationUpdates(android.location.LocationManager.GPS_PROVIDER,
                    2000L, 1f, listener, android.os.Looper.getMainLooper())
            }.onFailure { android.util.Log.w("AppModel", "GPS_PROVIDER failed: ${it.message}") }
            runCatching {
                lm.requestLocationUpdates(android.location.LocationManager.NETWORK_PROVIDER,
                    5000L, 5f, listener, android.os.Looper.getMainLooper())
            }.onFailure { android.util.Log.w("AppModel", "NETWORK_PROVIDER failed: ${it.message}") }
            gpsListener = listener
            android.util.Log.i("AppModel", "GPS listeners registered")
            lm.getLastKnownLocation(android.location.LocationManager.GPS_PROVIDER)?.let {
                listener.onLocationChanged(it)
            } ?: android.util.Log.i("AppModel", "GPS no last-known fix yet")
        } catch (e: SecurityException) {
            android.util.Log.w("AppModel", "GPS permission missing: ${e.message}")
        }
    }

    /** Stamp the phone's latest real fix into the record's gps object with its
     * TRUE age (fix time - record capture time); never clamped or fabricated.
     * v2: the wearable GPS shield is not part of the product. */
    private fun stampPhoneGps(rec: JSONObject, capturedAtMs: Long): JSONObject {
        val fix = _ui.value.gpsFix ?: run {
            if (enqueueLogCount <= 6) android.util.Log.w("AppModel", "stamp: NO fix available")
            return rec
        }
        val gps = rec.optJSONObject("gps") ?: JSONObject()
        gps.put("valid", true)
        gps.put("latitude", fix.latitude)
        gps.put("longitude", fix.longitude)
        gps.put("fix_age_ms", (capturedAtMs - fix.fixTimeMs).coerceAtLeast(0L))
        gps.put("source", "phone")
        rec.put("gps", gps)
        return rec
    }

    /** Handle MSG_PET_CARE_EVENT (18): [ver][kind u8][date ASCII 10][nonce LE64].
     * Maps to POST /me/pet/care and ACKs via MSG_INTERACTION_ACK (nonce-reused). */
    /** v2 raid: MSG_RAID_OUTCOME (21) —
     * [ver][outcome u8 1=win/2=lose][duration s LE16][nonce LE64][session UUID 16].
     * Maps to POST /sessions/{id}/raid/outcome; fight start/end are derived
     * honestly (ended = now; started = ended - duration). ACKs via the shared
     * MSG_INTERACTION_ACK nonce reply. */
    private fun handleRaidOutcome(payload: ByteArray) {
        if (payload.size < 14 || payload[0].toInt() != 1) return
        val outcome = when (payload[1].toInt()) { 1 -> "win"; 2 -> "lose"; else -> return }
        val durationS = (payload[2].toInt() and 0xFF) or ((payload[3].toInt() and 0xFF) shl 8)
        val nonceBuf = java.nio.ByteBuffer.wrap(payload, 4, 8)
            .order(java.nio.ByteOrder.LITTLE_ENDIAN)
        val nonce = nonceBuf.long
        val sessionBuf = java.nio.ByteBuffer.wrap(payload, 12, 16)
            .order(java.nio.ByteOrder.BIG_ENDIAN)
        val wireSession = UUID(sessionBuf.long, sessionBuf.long)
        // The phone's own raid session id is authoritative; the wire UUID is
        // a cross-check (the wearable may not have received an interaction
        // relay, in which case it sends zeros).
        val sessionId = _ui.value.sessionId ?: wireSession.takeIf { it != UUID(0, 0) } ?: run {
            android.util.Log.w("AppModel", "raid outcome without a session id; dropped")
            return
        }
        val ended = java.time.Instant.now()
        val started = ended.minusSeconds(durationS.toLong())
        scope.launch {
            val ok = runCatching {
                api.raidOutcome(
                    sessionId, outcome, started.toString(), ended.toString(),
                    UUID.nameUUIDFromBytes(
                        "$sessionId:raid:$nonce".toByteArray(Charsets.US_ASCII)),
                )
            }.onSuccess {
                _ui.value = _ui.value.copy(raidFight = false)
                refreshDeviceState()
            }.isSuccess
            val ack = ByteArray(10)
            ack[0] = 1
            java.nio.ByteBuffer.wrap(ack, 1, 8)
                .order(java.nio.ByteOrder.LITTLE_ENDIAN).putLong(nonce)
            ack[9] = if (ok) 1 else 0
            ble.send(Frame.MSG_INTERACTION_ACK, ack)
        }
    }

    private fun handlePetCareEvent(payload: ByteArray) {
        if (payload.size < 17 || payload[0].toInt() != 1) return
        val date = String(payload, 2, 10, Charsets.US_ASCII)
        val nonce = java.nio.ByteBuffer.wrap(payload, 12, 8)
            .order(java.nio.ByteOrder.LITTLE_ENDIAN).long
        scope.launch {
            val ok = runCatching {
                _ui.value = _ui.value.copy(pet = api.petCare(date))
            }.isSuccess
            val ack = ByteArray(10)
            ack[0] = 1
            java.nio.ByteBuffer.wrap(ack, 1, 8)
                .order(java.nio.ByteOrder.LITTLE_ENDIAN).putLong(nonce)
            ack[9] = if (ok) 1 else 0
            ble.send(Frame.MSG_INTERACTION_ACK, ack)
        }
    }

    /** Handle MSG_PET_STATE downlink? No — that is phone->wearable, sent by
     * sendPetState() from the state loop when the pet mirror changes. */

    // ==================== v2 quiz ('Know Your Partner') ====================

    /** Fetch the per-answerer quiz state; relay the CURRENT question to the
     *  wearable: MSG_QUIZ_STATE [ver][active][idx][total]. The first
     *  unanswered question is current; when everything (or the session) is
     *  done, active=0 returns the pad to the pet screen. */
    private fun refreshQuiz(sessionIdStr: String) {
        scope.launch {
            val sid = runCatching { UUID.fromString(sessionIdStr) }.getOrNull() ?: return@launch
            runCatching {
                val q = api.quiz(sid)
                val questions = q.getJSONArray("questions")
                var idx = -1
                for (i in 0 until questions.length()) {
                    val item = questions.getJSONObject(i)
                    if (!item.optBoolean("answered")) { idx = item.optInt("index"); break }
                }
                val total = questions.length()
                val active = !q.optBoolean("completed") && idx >= 0
                val view = buildQuizView(q, idx, total, active, null)
                _ui.value = _ui.value.copy(quiz = view)
                // Relay to the wearable (cheap 4-byte state; idempotent).
                val st = ByteArray(4)
                st[0] = 1
                st[1] = if (active) 1 else 0
                st[2] = (if (idx >= 0) idx else 0).toByte()
                st[3] = total.toByte()
                if (ble.state.value is BleLink.State.Connected) {
                    ble.send(Frame.MSG_QUIZ_STATE, st)
                    android.util.Log.i("AppModel",
                        "quiz relayed active=$active idx=$idx total=$total")
                } else {
                    android.util.Log.w("AppModel", "quiz relay skipped: link down")
                }
            }.onFailure {
                android.util.Log.w("AppModel", "quiz fetch failed: ${it.message}")
            }
        }
    }

    private fun buildQuizView(
        q: JSONObject, currentIdx: Int, total: Int, active: Boolean,
        error: String?,
    ): QuizView {
        val questions = q.getJSONArray("questions")
        var question: String? = null
        var options: List<String> = emptyList()
        for (i in 0 until questions.length()) {
            val item = questions.getJSONObject(i)
            if (item.optInt("index") == currentIdx) {
                question = item.optString("text")
                val arr = item.optJSONArray("options")
                options = (0 until (arr?.length() ?: 0)).map { arr!!.optString(it) }
                break
            }
        }
        return QuizView(
            active = active,
            index = currentIdx,
            total = total,
            question = question,
            options = options,
            myAnswered = q.optInt("my_answered"),
            myTotal = q.optInt("my_total"),
            partnerAnswered = q.optInt("partner_answered"),
            partnerTotal = q.optInt("partner_total"),
            completed = q.optBoolean("completed"),
            lastError = error,
        )
    }

    /** MSG_QUIZ_ANSWER [ver][idx][choice]: the wearable's A-D press for the
     *  current question. The server upserts (latest wins) and completes +
     *  awards the session when every question has an answer. */
    private fun handleQuizAnswer(payload: ByteArray) {
        if (payload.size < 3 || payload[0].toInt() != 1) {
            android.util.Log.w("AppModel", "quiz answer malformed len=${payload.size}")
            return
        }
        val idx = payload[1].toInt() and 0xFF
        val choice = payload[2].toInt() and 0xFF
        android.util.Log.i("AppModel", "quiz answer received idx=$idx choice=$choice")
        val quiz = _ui.value.quiz ?: run {
            android.util.Log.w("AppModel", "quiz answer without quiz state; dropped")
            return
        }
        val sessionId = _ui.value.sessionId ?: return
        scope.launch {
            runCatching {
                val q = api.quizAnswer(sessionId, idx, choice)
                val questions = q.getJSONArray("questions")
                var next = -1
                for (i in 0 until questions.length()) {
                    val item = questions.getJSONObject(i)
                    if (!item.optBoolean("answered")) { next = item.optInt("index"); break }
                }
                val active = !q.optBoolean("completed") && next >= 0
                _ui.value = _ui.value.copy(
                    quiz = buildQuizView(q, next, questions.length(), active, null))
                // Tell the wearable the next question (or end of quiz).
                val st = ByteArray(4)
                st[0] = 1
                st[1] = if (active) 1 else 0
                st[2] = (if (next >= 0) next else 0).toByte()
                st[3] = questions.length().toByte()
                if (ble.state.value is BleLink.State.Connected) {
                    ble.send(Frame.MSG_QUIZ_STATE, st)
                }
            }.onFailure {
                android.util.Log.w("AppModel", "quiz answer failed: ${it.message}")
                _ui.value = _ui.value.copy(
                    quiz = quiz.copy(lastError = it.message ?: "answer failed"))
            }
        }
    }

    private fun sendPetState() {
        val pet = _ui.value.pet ?: run {
            android.util.Log.w("AppModel", "sendPetState: no pet mirror")
            return
        }
        // [ver=1][xp LE32][level u8][stage u8][care-today u8][name-len][name<=8]
        // Byte layout MUST match the firmware parser exactly (ver at 0, xp
        // at 1..4) — an earlier build shifted everything by one.
        val out = ByteArray(9 + 8)
        out[0] = 1 // ver
        val name = pet.optString("name", "")
        val buf = java.nio.ByteBuffer.wrap(out).order(java.nio.ByteOrder.LITTLE_ENDIAN)
        buf.putInt(1, pet.optInt("lifetime_xp", 0))
        out[5] = pet.optInt("level", 1).toByte()
        out[6] = pet.optInt("evolution_stage", 1).toByte()
        out[7] = if (pet.optBoolean("cared_today", false)) 1 else 0
        val nameBytes = name.take(8).toByteArray(Charsets.US_ASCII)
        out[8] = nameBytes.size.toByte()
        System.arraycopy(nameBytes, 0, out, 9, nameBytes.size)
        val sent = ble.send(Frame.MSG_PET_STATE, out)
        if (rxLoggedPet < 3) {
            rxLoggedPet++
            android.util.Log.i("AppModel", "sendPetState sent=$sent xp=${pet.optInt("lifetime_xp")} level=${pet.optInt("level")}")
        }
    }

    private var rxLoggedPet = 0
    private var lastPetRefreshMs = 0L

    // ==================== Nearby discovery (docs/DISCOVERY_PLAN.md) ====================
    //
    // The phone relays three things: (1) the provisioned opaque token +
    // mode to the wearable (DISCOVERY_MODE, confirmed by DISCOVERY_ACK),
    // (2) the wearable's direct scan observations to the server (15 s
    // presence, idempotent identity = token + original capture time),
    // (3) filtered compact results back to the wearable display. The phone
    // itself never scans for discovery and never contributes location.

    private fun startDiscoveryLoop() {
        if (discoveryJob != null) return
        discoveryJob = scope.launch {
            while (true) {
                delay(5000)
                if (!screenVisible || !_ui.value.signedIn) continue
                pollDiscovery()
            }
        }
    }

    /** Profile, opt-ins, partnership and invitations snapshot. */
    fun refreshDiscoveryState() {
        scope.launch {
            runCatching {
                val me = api.me()
                val partner = me.optJSONObject("partner")
                _ui.value = _ui.value.copy(
                    partnered = partner != null,
                    partnerName = partner?.optString("display_name"),
                    partnerUserId = partner?.optString("id"))
            }
            runCatching {
                _ui.value = _ui.value.copy(profile = api.discoveryProfile())
            }
            runCatching {
                _ui.value = _ui.value.copy(invitations = api.invitations())
            }.onFailure { _ui.value = _ui.value.copy(invitations = null) }
        }
    }

    private suspend fun pollDiscovery() {
        try {
            // Refresh partnership + profile first: the desired board mode
            // derives from them, and either can change server-side (profile
            // edits, partnership end) without this phone being the actor.
            val me = api.me()
            val partner = me.optJSONObject("partner")
            _ui.value = _ui.value.copy(
                partnered = partner != null,
                partnerName = partner?.optString("display_name"),
                partnerUserId = partner?.optString("id"))
            runCatching {
                _ui.value = _ui.value.copy(profile = api.discoveryProfile())
            }
            val out = api.discovery()
            _ui.value = _ui.value.copy(discovery = out, discoveryError = null)
            refreshInvitationsQuiet()
            relayResultsToBoard(out)
            relayModeToBoard(force = false)
        } catch (e: Exception) {
            // Connection loss: mark discovery unavailable/stale honestly
            // instead of presenting cached profiles as current matches.
            _ui.value = _ui.value.copy(discoveryError = e.message ?: "discovery unavailable")
        }
    }

    private suspend fun refreshInvitationsQuiet() {
        runCatching { _ui.value = _ui.value.copy(invitations = api.invitations()) }
    }

    /** Desired wearable discovery mode: unpaired + any method opted in. */
    private fun desiredBoardMode(): Int {
        val state = _ui.value
        val ble = state.profile?.optBoolean("bluetooth_enabled", false) ?: false
        val gps = state.profile?.optBoolean("gps_enabled", false) ?: false
        return if (!state.partnered && (ble || gps)) 1 else 0
    }

    /**
     * Send DISCOVERY_MODE [ver][mode][token LE16] while connected; resends
     * until the wearable's DISCOVERY_ACK matches (covers reconnects and
     * opt-out syncing on the next phone link).
     */
    private suspend fun relayModeToBoard(force: Boolean) {
        if (ble.state.value !is BleLink.State.Connected) return
        val mode = desiredBoardMode()
        if (!force && boardAckedMode == mode) return
        var token = discoveryTokenValue
        if (mode == 1 && token == null) {
            token = runCatching { api.discoveryToken().optInt("token_value") }
                .getOrNull()?.also { discoveryTokenValue = it }
        }
        val payload = ByteArray(4)
        payload[0] = 1  // discovery payload version
        payload[1] = mode.toByte()
        putU16(payload, 2, token ?: 0)
        ble.send(Frame.MSG_DISCOVERY_MODE, payload)
        _ui.value = _ui.value.copy(boardModeAcked = boardAckedMode == mode)
    }

    /** Compact results (<=3) to the wearable display:
     * [ver][n] + n * ([shared][flags][len][name<=12]). */
    private fun relayResultsToBoard(out: JSONObject) {
        if (ble.state.value !is BleLink.State.Connected) return
        val results = out.optJSONArray("results") ?: return
        val n = minOf(3, results.length())
        if (n == 0) {
            if (lastResultsWire != "0") { lastResultsWire = "0"; sendResultsWire(emptyList()) }
            return
        }
        val entries = ArrayList<Triple<Int, Int, String>>(n)  // shared, flags, name
        for (i in 0 until n) {
            val r = results.getJSONObject(i)
            var flags = 0
            val sources = r.optJSONArray("sources")
            for (k in 0 until (sources?.length() ?: 0)) {
                if (sources!!.getString(k) == "bluetooth") flags = flags or 0x01
                if (sources.getString(k) == "gps") flags = flags or 0x02
            }
            entries.add(Triple(r.optInt("shared_count"), flags, r.optString("display_name")))
        }
        val wire = entries.joinToString("|") { "${it.first},${it.second},${it.third}" }
        if (wire == lastResultsWire) return  // unchanged: no radio traffic
        lastResultsWire = wire
        sendResultsWire(entries)
    }

    private fun sendResultsWire(entries: List<Triple<Int, Int, String>>) {
        var size = 2
        for (e in entries) size += 3 + minOf(12, e.third.toByteArray(Charsets.US_ASCII).size)
        val payload = ByteArray(size)
        payload[0] = 1  // discovery payload version
        payload[1] = entries.size.coerceAtMost(255).toByte()
        var off = 2
        for (e in entries) {
            val bytes = e.third.toByteArray(Charsets.US_ASCII)
            val len = minOf(12, bytes.size)
            payload[off++] = e.first.coerceAtMost(255).toByte()
            payload[off++] = e.second.toByte()
            payload[off++] = len.toByte()
            System.arraycopy(bytes, 0, payload, off, len)
            off += len
        }
        ble.send(Frame.MSG_DISCOVERY_RESULTS, payload.copyOf(off))
    }

    /** DISCOVERY_OBS [ver][n] + n*(token LE16, age_ms LE16): stamp the
     * ORIGINAL capture time (now - age) and upload idempotently. */
    private fun handleDiscoveryObs(payload: ByteArray) {
        if (payload.size < 2 || payload[0].toInt() != 1) return  // unknown version
        val n = payload[1].toInt() and 0xFF
        if (n == 0 || payload.size < 2 + n * 4) return
        val receivedMs = System.currentTimeMillis()
        val batch = JSONArray()
        for (i in 0 until n) {
            val off = 2 + i * 4
            val token = (payload[off].toInt() and 0xFF) or
                ((payload[off + 1].toInt() and 0xFF) shl 8)
            val ageMs = (payload[off + 2].toInt() and 0xFF) or
                ((payload[off + 3].toInt() and 0xFF) shl 8)
            val capturedMs = receivedMs - ageMs
            batch.put(JSONObject()
                .put("token", token)
                .put("captured_at",
                    java.time.Instant.ofEpochMilli(capturedMs).toString()))
        }
        scope.launch {
            runCatching { api.uploadObservations(batch) }
                .onFailure { android.util.Log.w("AppModel", "obs upload failed: ${it.message}") }
        }
    }

    // --- Profile / invitation / partnership actions ---

    fun saveProfile(body: JSONObject, onResult: (Boolean, String?) -> Unit) {
        scope.launch {
            try {
                _ui.value = _ui.value.copy(profile = api.putDiscoveryProfile(body))
                relayModeToBoard(force = true)
                onResult(true, null)
            } catch (e: Exception) { onResult(false, e.message) }
        }
    }

    fun setOptIns(bluetoothEnabled: Boolean, gpsEnabled: Boolean, onResult: (Boolean, String?) -> Unit) {
        scope.launch {
            try {
                _ui.value = _ui.value.copy(
                    profile = api.putDiscoverySettings(bluetoothEnabled, gpsEnabled))
                relayModeToBoard(force = true)
                onResult(true, null)
            } catch (e: Exception) { onResult(false, e.message) }
        }
    }

    fun invite(userId: UUID, onResult: (Boolean, String?) -> Unit) {
        scope.launch {
            try { api.createInvitation(userId); refreshInvitationsQuiet(); onResult(true, null) }
            catch (e: Exception) { onResult(false, e.message) }
        }
    }

    fun respondInvitation(id: UUID, accept: Boolean, onResult: (Boolean, String?) -> Unit) {
        scope.launch {
            try {
                if (accept) api.acceptInvitation(id) else api.declineInvitation(id)
                refreshDiscoveryState()
                relayModeToBoard(force = true)  // pairing stops general discovery
                pollDiscovery()
                onResult(true, null)
            } catch (e: Exception) { onResult(false, e.message) }
        }
    }

    fun endPartnership(onResult: (Boolean, String?) -> Unit) {
        scope.launch {
            try {
                api.endPartnership()
                refreshDiscoveryState()
                relayModeToBoard(force = true)
                pollDiscovery()
                onResult(true, null)
            } catch (e: Exception) { onResult(false, e.message) }
        }
    }

    /** Debug/admin: drop the wearable's undelivered BACKUP queue records
     * (captured while no phone was linked; never delivered). Labeled admin
     * action — permanent discard, never automatic. */
    fun purgeBoardQueue() {
        val payload = byteArrayOf(1, 'P'.code.toByte(), 'G'.code.toByte())
        ble.send(Frame.MSG_QUEUE_PURGE, payload)
    }

    fun close() {
        // Full teardown on Activity destruction: cancel every loop (collect,
        // state, uploader, discovery, supervisor) — without this a recreated
        // Activity leaves ZOMBIE instances running against the old BLE link
        // (stale Connected state, duplicate scan loops; verified live 12 Nov).
        runCatching { collectJob?.cancel() }
        runCatching { discoveryJob?.cancel() }
        runCatching { uploaderJob?.cancel() }
        scope.cancel()
        ble.close()
    }
}
