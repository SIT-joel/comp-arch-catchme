package com.catchme.app.data

import android.content.Context
import android.os.SystemClock
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
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import org.json.JSONArray
import org.json.JSONObject
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.time.Instant
import java.util.UUID

/**
 * Application model: owns the BLE link, the persistent queue, and the API.
 *
 * Data path: wearable -> (BLE UART) -> queue -> HTTPS ->
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
        // --- Nearby discovery ---
        val partnered: Boolean = false,
        val partnerName: String? = null,
        val profile: JSONObject? = null,
        val discovery: JSONObject? = null,
        val invitations: JSONObject? = null,
        val boardModeAcked: Boolean = false,
        val discoveryError: String? = null,
        // --- v2: pet + quests ---
        val pet: JSONObject? = null,
        val gpsFix: GpsFixView? = null,
        val activeSession: SessionView? = null,
        val quiz: QuizView? = null,  // v2 quiz: active 'Know Your Partner' state
        val proximityAlert: String? = null,  // non-null when out of BT range during an active quest
        // --- achievements (15 Nov): the catalog + this user's unlocks ---
        val achievements: List<AccView> = emptyList(),
        val newAchievement: String? = null,  // latest unlock name (banner)
        val newAchievementAt: Long = 0,  // ms epoch of the banner appearance
        val bleLinkHealthy: Boolean = false,
        val pinVerifyStatus: String? = null,
        val pinVerifyIsError: Boolean = false,
        val pinVerifyBusy: Boolean = false,
    )

    data class SessionView(
        val sessionId: UUID,
        val questId: String,
        val state: String,
        val demo: Boolean,
        val progressMs: Long,
        val targetMs: Long?,
        val needsMyAccept: Boolean,
        val interactionSummary: String? = null,
        val interactionPhase: String? = null,
        val interactionStage: String? = null,
        val ownPin: String? = null,
        val partnerCodeVersion: Int = 0,
        val myPinConfirmed: Boolean = false,
        val partnerPinConfirmed: Boolean = false,
        val timerRunning: Boolean = false,
        val progressAnchorMs: Long? = null,
    )

    /** One achievement row for the achievements card (unlocked=false rows
     *  render greyed with their description as the "how to earn" hint). */
    data class AccView(
        val id: String,
        val name: String,
        val description: String,
        val unlocked: Boolean,
        val unlockedAt: String?,
    )

    data class QuizQuestionResult(
        val index: Int,
        val text: String,
        val options: List<String>,
        val answered: Boolean,
        val choice: Int?,
        val rightIndex: Int?,
        val isCorrect: Boolean?,
    )

    /** v2 quiz: the phone renders the question; the wearable is the A-D pad. */
    data class QuizView(
        val active: Boolean,
        val index: Int,          // current question (first unanswered)
        val total: Int,
        val question: String?,
        val options: List<String>,
        val myAnswered: Int,
        val myTotal: Int,
        val myCorrect: Int,
        val partnerAnswered: Int,
        val partnerTotal: Int,
        val partnerCorrect: Int,
        val completed: Boolean,
        val results: List<QuizQuestionResult> = emptyList(),
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
    @Volatile private var serverClockOffsetMs: Long = 0L
    @Volatile private var serverClockSynced: Boolean = false

    fun displayProgressMs(
        session: SessionView,
        nowElapsedMs: Long = SystemClock.elapsedRealtime(),
    ): Long {
        val target = session.targetMs ?: return session.progressMs
        if (target <= 0L || session.progressMs >= target) return session.progressMs
        if (!session.timerRunning || session.progressAnchorMs == null || _ui.value.proximityAlert != null) {
            return session.progressMs
        }
        val serverNowMs = if (serverClockSynced) serverClockOffsetMs + nowElapsedMs else System.currentTimeMillis()
        val extraMs = (serverNowMs - session.progressAnchorMs).coerceIn(0L, 12_000L)
        val capMs = (target - 1000L).coerceAtLeast(session.progressMs)
        return (session.progressMs + extraMs).coerceAtMost(capMs)
    }

    private var collectJob: Job? = null
    private var uploaderJob: Job? = Job().also { } // placeholder; started below

    // --- Discovery relay state ---
    // Poll /me/discovery every 5 s while the app is visible (the plan's
    // expiry-driven refresh; SSE alone cannot age results out).
    @Volatile var screenVisible: Boolean = false
    @Volatile private var discoveryTokenValue: Int? = null
    @Volatile private var boardAckedMode: Int = -1  // -1 = no ack yet
    private var discoveryJob: Job? = null
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
                _ui.update {
                    it.copy(
                        signedIn = true, username = username,
                        userId = me.getJSONObject("user").optString("id"),
                        deviceId = device?.let { d -> UUID.fromString(d.optString("id")) },
                        deviceAlias = device?.optInt("firmware_alias"),
                    )
                }
                refreshDeviceState()
                startDiscoveryLoop()
                refreshDiscoveryState()
                refreshPetAndAchievements()
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
            // The tunnel hiccups (Cloudflare 403/error bursts, observed live).
            // A single failed /me must NOT sign the user out — retry before
            // falling back; only a definitive 401 clears the session.
            val me = runCatching {
                var last: Exception? = null
                for (attempt in 1..3) {
                    try {
                        return@runCatching api.me()
                    } catch (e: Exception) {
                        last = e
                        android.util.Log.w("AppModel", "restore /me attempt $attempt failed: ${e.message}")
                        kotlinx.coroutines.delay(1500L * attempt)
                    }
                }
                throw (last ?: IllegalStateException("restore failed"))
            }.getOrElse {
                android.util.Log.w("AppModel", "restore gave up after retries; falling back to sign-in")
                api.token = null
                return@launch
            }
            android.util.Log.i("AppModel", "session restored (token validated)")
            runCatching {
                val device = me.optJSONObject("device")
                _ui.update {
                    it.copy(
                        signedIn = true,
                        username = prefs.getString("username", null),
                        userId = me.getJSONObject("user").optString("id"),
                        deviceId = device?.let { d -> UUID.fromString(d.optString("id")) },
                        deviceAlias = device?.optInt("firmware_alias"),
                    )
                }
                refreshDeviceState()
                startDiscoveryLoop()
                refreshDiscoveryState()
                refreshPetAndAchievements()
                startGps()
                onRestored()
            }.onFailure {
                android.util.Log.w("AppModel", "restore post-me setup failed: ${it.message}", it)
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
                _ui.update {
                    it.copy(
                        deviceId = UUID.fromString(device.getString("id")),
                        deviceAlias = device.getInt("firmware_alias"),
                    )
                }
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
     * below reconnects whenever the link drops and expects
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
            scope.launch { syncOnBleConnectLoop() }
        }
    }

    /** Push session/quiz/time/pet state immediately after BLE connects so the
     *  short TDD LINKED window does not wait up to 3 s for stateLoop. */
    private suspend fun syncOnBleConnectLoop() {
        var wasConnected = false
        ble.state.collect { state ->
            val nowConnected = state is BleLink.State.Connected
            if (nowConnected && !wasConnected) {
                bleDisconnectedAtMs = 0L
                lastIdleInteractionSentOnConn = false
                lastTimeAnchorSentAtMs = 0L
                updateProximityAlert()
                refreshDeviceStateSync()
            } else if (!nowConnected && wasConnected) {
                bleDisconnectedAtMs = System.currentTimeMillis()
                updateProximityAlert()
            }
            wasConnected = nowConnected
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
            updateProximityAlert()
            val state = ble.state.value
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
                _ui.update { it.copy(boardModeAcked = false) }
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
     * progress.
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
            val count = db.dao().pendingCount()
            _ui.update { it.copy(pendingUploads = count) }
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
            Frame.MSG_PET_IDENTITY -> handlePetIdentity(msg.payload)
            Frame.MSG_QUIZ_ANSWER -> handleQuizAnswer(msg.payload)
            Frame.MSG_DISCOVERY_ACK -> {
                // [ver][mode] — the wearable confirmed its applied mode.
                if (msg.payload.size >= 2 && msg.payload[0].toInt() == 1) {
                    boardAckedMode = msg.payload[1].toInt()
                    _ui.update { it.copy(boardModeAcked = boardAckedMode == desiredBoardMode()) }
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
            // Track fresh direct partner wearable BLE observations for live proximity alerts.
            val peerJson = rec.optJSONObject("peer")
            val expectedPartnerAlias = state.deviceAlias?.let { if (it == 1) 2 else 1 } ?: 0
            if (peerJson?.optBoolean("observed") == true &&
                (expectedPartnerAlias == 0 || peerJson.optInt("_alias", 0) == expectedPartnerAlias)
            ) {
                val obsAgeMs = peerJson.optLong("observation_age_ms", 0L).coerceAtLeast(0L)
                val obsAt = System.currentTimeMillis() - obsAgeMs
                if (obsAt > lastPeerBleSeenMs) lastPeerBleSeenMs = obsAt
                updateProximityAlert()
            }
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
            val count = db.dao().pendingCount()
            _ui.update { it.copy(pendingUploads = count) }
        }.onFailure { android.util.Log.w("AppModel", "enqueue failed (${payload.size}B): ${it.message}") }
    }

    @Volatile private var peerHbBootEpoch = 1
    @Volatile private var lastPeerHbCounter = -1

    /** Firmware aliases -> server UUIDs/tokens using known device state.
     * Verifies both expected partner alias AND advertised 16-bit session token
     * hash (fnv16) before stamping session_token, and tracks partner wearable
     * reboots so reset heartbeat counters do not stall server scoring. */
    private fun resolveAliases(rec: JSONObject): JSONObject {
        val peer = rec.optJSONObject("peer") ?: return rec
        val observedAlias = peer.optInt("_alias", 0)
        val observedTokenHash = peer.optInt("_token_hash", 0)
        peer.remove("_alias")
        peer.remove("_token_hash")
        if (!peer.optBoolean("observed")) return rec
        val partner = _ui.value.partnerDeviceId
        val token = _ui.value.sessionToken
        val expectedAlias = _ui.value.deviceAlias?.let { if (it == 1) 2 else 1 } ?: 0
        val expectedTokenHash = if (token != null) fnv16(tokenBytes(token)) else 0
        if (partner != null && token != null &&
            observedAlias == expectedAlias &&
            observedTokenHash != 0 && observedTokenHash == expectedTokenHash
        ) {
            val hbSeq = peer.optInt("heartbeat_sequence", -1)
            if (hbSeq >= 0 && lastPeerHbCounter > 0 && hbSeq < lastPeerHbCounter) {
                peerHbBootEpoch++
            }
            if (hbSeq >= 0) lastPeerHbCounter = hbSeq
            peer.put("device_id", partner.toString())
            peer.put("session_token", token)
            peer.put("boot_id", "d${expectedAlias}-e${peerHbBootEpoch}")
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
            delay(if (_ui.value.activeSession != null) 1000L else 2000L)
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
                val ackSeqs = ArrayList<Long>(rows.size)
                val byIdentity = rows.associateBy { it.bootId to it.sequence }
                val activeBoot = bootIdCache
                for (i in 0 until ack.getJSONArray("accepted").length()) {
                    val a = ack.getJSONArray("accepted").getJSONObject(i)
                    byIdentity[a.getString("boot_id") to a.getLong("sequence")]?.let {
                        okIds.add(it.id)
                        if (activeBoot == null || it.bootId == activeBoot) ackSeqs.add(it.sequence)
                    }
                }
                // Duplicates are confirmed persisted too (idempotent no-op).
                for (i in 0 until ack.getJSONArray("duplicates").length()) {
                    val a = ack.getJSONArray("duplicates").getJSONObject(i)
                    byIdentity[a.getString("boot_id") to a.getLong("sequence")]?.let {
                        okIds.add(it.id)
                        if (activeBoot == null || it.bootId == activeBoot) ackSeqs.add(it.sequence)
                    }
                }
                if (okIds.isNotEmpty()) {
                    db.dao().markSynced(okIds)
                    sendAck(ackSeqs)
                }
                validationFailures = 0
                val pending = db.dao().pendingCount()
                _ui.update {
                    it.copy(pendingUploads = pending, lastUploadOk = true, lastTick = System.currentTimeMillis())
                }
                if (okIds.isNotEmpty() && state.activeSession != null) {
                    refreshDeviceStateSync()
                }
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
                _ui.update { it.copy(lastUploadOk = false) }
            } catch (e: Exception) {
                _ui.update { it.copy(lastUploadOk = false) }
            }
        }
    }

    /** Relay server-persisted record sequences to the wearable (contiguous prefix). */
    private fun sendAck(sequences: List<Long>) {
        if (sequences.isEmpty()) return
        val capped = sequences.take(16)
        val payload = ByteArray(1 + capped.size * 4)
        payload[0] = capped.size.toByte()
        val buf = ByteBuffer.wrap(payload, 1, capped.size * 4).order(ByteOrder.LITTLE_ENDIAN)
        for (seq in capped) {
            buf.putInt(seq.toInt())
        }
        ble.send(Frame.MSG_ACK, payload)
    }

    /** Periodically: device state -> SESSION_STATE + TIME_ANCHOR to wearable. */
    private suspend fun stateLoop() {
        while (true) {
            delay(if (_ui.value.activeSession != null) 1500 else 3000)
            refreshDeviceStateSync()
            updateProximityAlert()
        }
    }

    private val relayMutex = Mutex()
    @Volatile private var lastTimeAnchorFetchMs = 0L
    @Volatile private var lastTimeAnchorSentAtMs = 0L
    @Volatile private var lastIdleInteractionSentOnConn = false
    @Volatile private var lastRelayConnSessionId = 0L
    @Volatile private var lastPeerBleSeenMs = 0L
    @Volatile private var bleDisconnectedAtMs = 0L
    @Volatile private var activeQuestIdTracked: UUID? = null
    @Volatile private var activeQuestStartedAtMs = 0L
    @Volatile private var lastQuizSessionId: UUID? = null

    private fun updateProximityAlert() {
        val active = _ui.value.activeSession
        val now = System.currentTimeMillis()
        val linkHealthy = ble.isLinkHealthy(22_000L)
        if (_ui.value.bleLinkHealthy != linkHealthy) {
            _ui.update { it.copy(bleLinkHealthy = linkHealthy) }
        }
        if (active == null || active.state != "active") {
            if (active == null) {
                activeQuestIdTracked = null
                activeQuestStartedAtMs = 0L
            }
            if (_ui.value.proximityAlert != null) {
                _ui.update { it.copy(proximityAlert = null) }
            }
            return
        }
        if (activeQuestIdTracked != active.sessionId || activeQuestStartedAtMs == 0L) {
            activeQuestIdTracked = active.sessionId
            activeQuestStartedAtMs = now
            lastPeerHbCounter = -1
            if (ble.state.value !is BleLink.State.Connected && bleDisconnectedAtMs == 0L) {
                bleDisconnectedAtMs = now
            }
        }
        val btOff = !ble.ensureAdapter() || ble.state.value is BleLink.State.Failed
        val linkGraceMs = if (btOff) 4_000L else 22_000L
        val linkAlert = ble.state.value !is BleLink.State.Connected &&
            bleDisconnectedAtMs != 0L && (now - bleDisconnectedAtMs) >= linkGraceMs
        val supportsPeerGap = active.questId == "explore" || active.questId == "together"
        val peerMissing = supportsPeerGap &&
            (now - activeQuestStartedAtMs) >= 25_000L &&
            (lastPeerBleSeenMs == 0L || (now - lastPeerBleSeenMs) >= 28_000L)
        val timerActive = active.questId == "explore" ||
            (active.questId == "together" && active.interactionSummary?.startsWith("Codes confirmed") == true)
        val alert: String? = when {
            linkAlert -> "Out of Bluetooth range of your TinyScreen+ — move closer to your wearable."
            peerMissing -> if (timerActive) {
                "Out of Bluetooth proximity range of partner's TinyScreen+ — quest timer paused."
            } else {
                "Out of Bluetooth proximity range of partner's TinyScreen+ — move closer."
            }
            else -> null
        }
        if (_ui.value.proximityAlert != alert) {
            _ui.update { it.copy(proximityAlert = alert) }
        }
    }

    private suspend fun relayDeviceStateToWearable(ds: JSONObject) {
        if (ble.state.value !is BleLink.State.Connected) return
        relayMutex.withLock {
            if (ble.state.value !is BleLink.State.Connected) return
            flushPendingInteractionAcks()
            val nowMs = System.currentTimeMillis()
            if (nowMs - lastPetRefreshMs >= 10_000) {
                lastPetRefreshMs = nowMs
                refreshPetAndAchievements()
            }
            sendSessionState(ds)
            sendPhoneGpsState(ds)
            sendInteractionState(ds)
            sendTimeAnchor()
            sendPartnerInfo(ds)
            sendPetState()
            if (bootIdCache == null) {
                ble.send(Frame.MSG_HELLO, ByteArray(0))
            }
            relayModeToBoard(force = false)
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
            val view = _ui.value.activeSession
            val shownProgress = if (view != null && view.state == "active") {
                displayProgressMs(view)
            } else {
                session.optLong("progress_ms")
            }
            val runningFlag = view != null &&
                view.state == "active" &&
                view.timerRunning &&
                _ui.value.proximityAlert == null &&
                view.progressMs < (view.targetMs ?: 0L)
            out[0] = 1
            out[1] = when (session.getString("quest_id")) {
                "together" -> 1; "explore" -> 2; "quiz" -> 5; else -> 3 // 3 = legacy heart
            }
            out[2] = if (session.optBoolean("demo")) 1 else 0
            putU32(out, 3, shownProgress)
            putU32(out, 7, session.optLong("target_ms"))
            out[11] = (ds.optInt("partner_alias", 0)).toByte()
            putU16(out, 12, fnv16(tokenBytes(session.optString("token"))))
            out[14] = 0
            out[15] = if (runningFlag) 1 else 0
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

    @Volatile private var lastGpsRelayMs = 0L

    /** Relay latest real phone GPS coordinates + true age over Bluetooth BLE to TinyScreen+. */
    private fun sendPhoneGpsState(ds: JSONObject) {
        val session = ds.optJSONObject("session")
        val questId = session?.optString("quest_id") ?: ""
        val state = session?.optString("state") ?: ""
        val inExplore = questId == "explore" && (state == "active" || state == "pending")
        val now = System.currentTimeMillis()
        if (!inExplore && now - lastGpsRelayMs < 6_000L) return
        val fix = _ui.value.gpsFix
        val out = ByteArray(13)
        out[0] = 1
        out[1] = if (fix != null) 1 else 0
        out[2] = if (session?.optBoolean("demo") == true) 1 else 0
        if (fix != null) {
            val ageSec = ((now - fix.fixTimeMs).coerceAtLeast(0L) / 1000L)
                .coerceAtMost(65535L).toInt()
            val buf = ByteBuffer.wrap(out, 3, 10).order(ByteOrder.LITTLE_ENDIAN)
            buf.putInt((fix.latitude * 1_000_000.0).toInt())
            buf.putInt((fix.longitude * 1_000_000.0).toInt())
            buf.putShort(ageSec.toShort())
        }
        if (ble.send(Frame.MSG_GPS_STATE, out)) {
            lastGpsRelayMs = now
        }
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
            if (!lastIdleInteractionSentOnConn) {
                if (ble.send(Frame.MSG_INTERACTION_STATE, out)) {
                    lastIdleInteractionSentOnConn = true
                }
            }
            return
        }
        lastIdleInteractionSentOnConn = false
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

    private val interactionNonceLock = Any()
    private val inFlightInteractionNonces = HashSet<Long>()
    private val completedInteractionAcks = LinkedHashMap<Long, Int>()
    private val pendingInteractionAcks = LinkedHashMap<Long, Int>()

    private fun buildInteractionAck(nonce: Long, ackCode: Int): ByteArray {
        val ack = ByteArray(10)
        ack[0] = 1
        ByteBuffer.wrap(ack, 1, 8).order(ByteOrder.LITTLE_ENDIAN).putLong(nonce)
        ack[9] = ackCode.toByte()
        return ack
    }

    private fun sendOrQueueInteractionAck(nonce: Long, ackCode: Int) {
        val sent = ble.send(Frame.MSG_INTERACTION_ACK, buildInteractionAck(nonce, ackCode))
        synchronized(interactionNonceLock) {
            if (!sent) {
                pendingInteractionAcks[nonce] = ackCode
                while (pendingInteractionAcks.size > 32) {
                    val oldest = pendingInteractionAcks.keys.first()
                    pendingInteractionAcks.remove(oldest)
                }
            } else {
                pendingInteractionAcks.remove(nonce)
            }
        }
    }

    private fun flushPendingInteractionAcks() {
        val snapshot = synchronized(interactionNonceLock) { pendingInteractionAcks.entries.map { it.key to it.value } }
        for ((nonce, ackCode) in snapshot) {
            if (ble.send(Frame.MSG_INTERACTION_ACK, buildInteractionAck(nonce, ackCode))) {
                synchronized(interactionNonceLock) { pendingInteractionAcks.remove(nonce) }
            } else {
                break
            }
        }
    }

    private suspend fun submitPinWithRetry(
        sessionId: UUID,
        stage: String,
        pin: String,
        initialVersion: Int,
        nonce: Long,
        alias: Int,
    ) {
        var ver = initialVersion
        if (ver <= 0) {
            ver = _ui.value.activeSession?.partnerCodeVersion?.takeIf { it > 0 }
                ?: runCatching { api.interaction(sessionId).optInt("partner_code_version", 1) }.getOrDefault(1)
        }
        var versionRefreshed = false
        var lastErr: Throwable? = null
        for (attempt in 1..3) {
            val suffix = if (ver != initialVersion) ":v$ver" else ""
            val cmdId = UUID.nameUUIDFromBytes("$sessionId:$alias:$nonce$suffix".toByteArray(Charsets.US_ASCII))
            try {
                api.submitInteractionPin(sessionId, stage, pin, ver, cmdId)
                return
            } catch (e: Api.ApiError) {
                if (e.status == 409 && !versionRefreshed) {
                    val msg = (e.message ?: "").lowercase()
                    if ("expired" in msg || "changed" in msg || e.code == "pin_expired") {
                        versionRefreshed = true
                        val latestVer = runCatching { api.interaction(sessionId) }.getOrNull()?.let { obj ->
                            val curStage = obj.optString("stage", "")
                            if (curStage == stage) obj.optInt("partner_code_version", 0) else 0
                        } ?: 0
                        if (latestVer > ver) {
                            ver = latestVer
                            continue
                        }
                    }
                }
                if (e.status in 400..499) throw e
                lastErr = e
            } catch (e: Exception) {
                lastErr = e
            }
            if (attempt < 3) delay(if (attempt == 1) 400L else 900L)
        }
        throw (lastErr ?: IllegalStateException("Network error verifying PIN"))
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
        val cachedAck = synchronized(interactionNonceLock) {
            val done = completedInteractionAcks[nonce]
            if (done != null) {
                done
            } else if (!inFlightInteractionNonces.add(nonce)) {
                return
            } else {
                null
            }
        }
        if (cachedAck != null) {
            scope.launch { sendOrQueueInteractionAck(nonce, cachedAck) }
            return
        }
        val alias = _ui.value.deviceAlias ?: 0
        if (kind == 1) {
            _ui.update {
                it.copy(
                    pinVerifyBusy = true,
                    pinVerifyIsError = false,
                    pinVerifyStatus = "PIN received from TinyScreen+ — verifying with server…",
                )
            }
        }
        scope.launch {
            var ackCode = 0
            try {
                try {
                    when (kind) {
                        1 -> {
                            if (stage.isEmpty() || valueLen != 4) error("invalid PIN command")
                            submitPinWithRetry(sessionId, stage, value, codeVersion, nonce, alias)
                        }
                        2 -> {
                            if (stage.isEmpty()) error("invalid refresh command")
                            val cmdId = UUID.nameUUIDFromBytes("$sessionId:$alias:$nonce".toByteArray(Charsets.US_ASCII))
                            var lastErr: Throwable? = null
                            var refreshed = false
                            for (attempt in 1..2) {
                                try {
                                    api.refreshInteractionPin(sessionId, stage, cmdId)
                                    refreshed = true
                                    break
                                } catch (e: Api.ApiError) {
                                    if (e.status in 400..499) throw e
                                    lastErr = e
                                } catch (e: Exception) {
                                    lastErr = e
                                }
                                if (attempt < 2) delay(400L)
                            }
                            if (!refreshed) throw (lastErr ?: IllegalStateException("Refresh failed"))
                        }
                        // v2: heart-quest kinds (3 truth / 4 dare / 5 skip) are gone.
                        else -> error("unknown interaction command")
                    }
                    ackCode = 1
                    if (kind == 1) {
                        _ui.update {
                            it.copy(
                                pinVerifyBusy = false,
                                pinVerifyIsError = false,
                                pinVerifyStatus = "PIN verified by server ✓",
                            )
                        }
                    }
                    refreshDeviceStateSync()
                } catch (err: Throwable) {
                    val apiErr = err as? Api.ApiError
                    val isClientReject = apiErr != null && apiErr.status in 400..499
                    ackCode = when {
                        !isClientReject -> 2  // transient network/server error -> retry automatically
                        apiErr?.status == 409 || apiErr?.status == 429 -> 3
                        else -> 0
                    }
                    if (kind == 1) {
                        val uiMsg = when (ackCode) {
                            0 -> "Incorrect PIN — check your partner's code and try again"
                            3 -> apiErr?.message ?: "PIN expired or attempt limit reached — ask partner to refresh"
                            else -> "Network error verifying PIN — auto-retrying…"
                        }
                        _ui.update {
                            it.copy(
                                pinVerifyBusy = false,
                                pinVerifyIsError = true,
                                pinVerifyStatus = uiMsg,
                            )
                        }
                    }
                    android.util.Log.w("AppModel", "interaction cmd kind=$kind failed ack=$ackCode: ${err.message}")
                }
                synchronized(interactionNonceLock) {
                    if (ackCode != 2) {
                        completedInteractionAcks[nonce] = ackCode
                        while (completedInteractionAcks.size > 32) {
                            val oldest = completedInteractionAcks.keys.first()
                            completedInteractionAcks.remove(oldest)
                        }
                    }
                }
                sendOrQueueInteractionAck(nonce, ackCode)
            } finally {
                synchronized(interactionNonceLock) { inFlightInteractionNonces.remove(nonce) }
            }
        }
    }

    fun submitPinFromApp(sessionId: UUID, stage: String, pin: String, onDone: (Boolean, String?) -> Unit) {
        if (pin.length != 4 || !pin.all { it.isDigit() }) {
            val msg = "Enter all 4 digits"
            _ui.update { it.copy(pinVerifyIsError = true, pinVerifyStatus = msg) }
            onDone(false, msg)
            return
        }
        val alias = _ui.value.deviceAlias ?: 0
        val nonce = System.currentTimeMillis()
        _ui.update {
            it.copy(
                pinVerifyBusy = true,
                pinVerifyIsError = false,
                pinVerifyStatus = "Verifying PIN with server…",
            )
        }
        scope.launch {
            runCatching {
                val curVer = _ui.value.activeSession?.partnerCodeVersion ?: 0
                submitPinWithRetry(sessionId, stage, pin, curVer, nonce, alias)
            }.onSuccess {
                _ui.update {
                    it.copy(
                        pinVerifyBusy = false,
                        pinVerifyIsError = false,
                        pinVerifyStatus = "PIN verified by server ✓",
                    )
                }
                refreshDeviceStateSync()
                onDone(true, null)
            }.onFailure { err ->
                val apiErr = err as? Api.ApiError
                val msg = when (apiErr?.status) {
                    422 -> "Incorrect PIN — check your partner's code and try again"
                    409, 429 -> apiErr.message
                    else -> err.message ?: "Failed to verify PIN"
                }
                _ui.update {
                    it.copy(
                        pinVerifyBusy = false,
                        pinVerifyIsError = true,
                        pinVerifyStatus = msg,
                    )
                }
                onDone(false, msg)
            }
        }
    }

    fun refreshPinFromApp(sessionId: UUID, stage: String, onDone: (Boolean, String?) -> Unit) {
        _ui.update { it.copy(pinVerifyBusy = true, pinVerifyIsError = false, pinVerifyStatus = "Refreshing your PIN…") }
        scope.launch {
            runCatching {
                api.refreshInteractionPin(sessionId, stage, UUID.randomUUID())
            }.onSuccess {
                _ui.update {
                    it.copy(
                        pinVerifyBusy = false,
                        pinVerifyIsError = false,
                        pinVerifyStatus = "Generated new PIN — share the new code with your partner",
                    )
                }
                refreshDeviceStateSync()
                onDone(true, null)
            }.onFailure { err ->
                val msg = err.message ?: "Failed to refresh PIN"
                _ui.update { it.copy(pinVerifyBusy = false, pinVerifyIsError = true, pinVerifyStatus = msg) }
                onDone(false, msg)
            }
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
        val now = System.currentTimeMillis()
        if (!timeSynced || now - lastTimeAnchorFetchMs >= 30_000L) {
            runCatching {
                val t = api.serverTimeMs()
                anchorEpoch = t / 1000
                lastTimeAnchorFetchMs = now
                timeSynced = true
            }
        }
        if (timeSynced && now - lastTimeAnchorSentAtMs >= 15_000L) {
            val epochNow = anchorEpoch + ((now - lastTimeAnchorFetchMs) / 1000L).coerceAtLeast(0L)
            val payload = ByteArray(6)
            putU32(payload, 0, epochNow)
            putU16(payload, 4, 500)
            if (ble.send(Frame.MSG_TIME_ANCHOR, payload)) {
                lastTimeAnchorSentAtMs = now
            }
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

    private fun parseSessionView(session: JSONObject?): SessionView? {
        if (session == null) return null
        val idStr = session.optString("session_id").takeIf { it.isNotBlank() }
            ?: session.optString("id").takeIf { it.isNotBlank() }
            ?: return null
        val id = runCatching { UUID.fromString(idStr) }.getOrNull() ?: return null
        val questId = session.optString("quest_id", "")
        val state = session.optString("state", "")
        var needsAccept = session.optBoolean("needs_my_accept", false)
        if (!session.has("needs_my_accept") && state == "pending") {
            val myId = _ui.value.userId
            val parts = session.optJSONArray("participants")
            if (myId != null && parts != null) {
                for (i in 0 until parts.length()) {
                    val p = parts.optJSONObject(i) ?: continue
                    if (p.optString("user_id") == myId) {
                        needsAccept = !p.optBoolean("accepted", false)
                    }
                }
            }
        }
        val interaction = session.optJSONObject("interaction")
        val phase = if (questId == "together" && state == "active") interaction?.optString("phase", "") else null
        val stage = if (questId == "together" && state == "active") interaction?.optString("stage", "") else null
        val ownCode = if (questId == "together" && state == "active") interaction?.optString("own_code", "") else null
        val partnerVer = if (questId == "together" && state == "active") interaction?.optInt("partner_code_version", 0) ?: 0 else 0
        val myDone = interaction?.optBoolean("partner_code_confirmed_by_me", false) ?: false
        val partnerDone = interaction?.optBoolean("own_code_confirmed_by_partner", false) ?: false
        val summary = if (questId == "together" && state == "active" && interaction != null) {
            when (phase) {
                "start_pin", "end_pin" -> {
                    val stageLabel = if (phase == "start_pin") "Start PIN" else "End PIN"
                    "$stageLabel · Your PIN: ${ownCode.orEmpty().ifBlank { "----" }} · " +
                        "You ${if (myDone) "✓" else "waiting"} / Partner ${if (partnerDone) "✓" else "waiting"}"
                }
                "timing" -> "Codes confirmed — stay within Bluetooth range of partner's TinyScreen+"
                else -> null
            }
        } else null
        val timerRunning = state == "active" && session.optBoolean("timer_running", false)
        val progressAnchorMs = session.optString("progress_anchor_at", "")
            .takeIf { it.isNotBlank() && it != "null" }
            ?.let { runCatching { Instant.parse(it).toEpochMilli() }.getOrNull() }
        return SessionView(
            sessionId = id,
            questId = questId,
            state = state,
            demo = session.optBoolean("demo", false),
            progressMs = session.optLong("progress_ms", 0L),
            targetMs = if (session.isNull("target_ms")) null else session.optLong("target_ms", 0L),
            needsMyAccept = needsAccept,
            interactionSummary = summary,
            interactionPhase = phase?.takeIf { it.isNotBlank() },
            interactionStage = stage?.takeIf { it.isNotBlank() },
            ownPin = ownCode?.takeIf { it.isNotBlank() },
            partnerCodeVersion = partnerVer,
            myPinConfirmed = myDone,
            partnerPinConfirmed = partnerDone,
            timerRunning = timerRunning,
            progressAnchorMs = progressAnchorMs,
        )
    }

    private suspend fun refreshDeviceStateSync() {
        runCatching {
            val devId = _ui.value.deviceId
            if (devId == null) {
                val arr = api.listSessions().optJSONArray("sessions")
                var found: JSONObject? = null
                if (arr != null) {
                    for (i in 0 until arr.length()) {
                        val s = arr.optJSONObject(i) ?: continue
                        val st = s.optString("state")
                        if (st == "pending" || st == "active") {
                            found = s
                            break
                        }
                    }
                }
                val active = found != null && found.optString("state") == "active"
                val sid = found?.let { runCatching { UUID.fromString(it.getString("id")) }.getOrNull() }
                val nextView = parseSessionView(found)
                _ui.update {
                    val resetPinUi = it.activeSession?.sessionId != nextView?.sessionId ||
                        it.activeSession?.interactionPhase != nextView?.interactionPhase
                    it.copy(
                        sessionToken = if (active) found?.optString("token")?.takeIf { t -> t.isNotBlank() } else null,
                        sessionId = sid,
                        activeSession = nextView,
                        pinVerifyStatus = if (resetPinUi) null else it.pinVerifyStatus,
                        pinVerifyIsError = if (resetPinUi) false else it.pinVerifyIsError,
                        pinVerifyBusy = if (resetPinUi) false else it.pinVerifyBusy,
                    )
                }
                if (active && found?.optString("quest_id") == "quiz" && sid != null) {
                    lastQuizSessionId = sid
                    refreshQuizSync(sid.toString())
                } else {
                    val prevQuizSid = lastQuizSessionId
                    if (_ui.value.quiz != null && _ui.value.quiz?.completed != true && prevQuizSid != null) {
                        refreshQuizSync(prevQuizSid.toString())
                    }
                    if (found != null && found.optString("quest_id") != "quiz") {
                        lastQuizSessionId = null
                        _ui.update { it.copy(quiz = null) }
                    }
                }
                return@runCatching
            }
            val ds = api.deviceState(devId)
            runCatching { Instant.parse(ds.optString("server_time")).toEpochMilli() }.getOrNull()?.let { srvMs ->
                serverClockOffsetMs = srvMs - SystemClock.elapsedRealtime()
                serverClockSynced = true
            }
            val session = ds.optJSONObject("session")
            val active = session != null && session.optString("state") == "active"
            val token = if (active) session?.optString("token")?.takeIf { it.isNotBlank() } else null
            val isPartnered = !ds.isNull("partner_alias")
            val partnerDevice = if (ds.isNull("partner_device_id")) null
                else UUID.fromString(ds.getString("partner_device_id"))
            val sidStr = session?.optString("session_id")
            val sidUuid = sidStr?.let { s -> runCatching { UUID.fromString(s) }.getOrNull() }
            val nextView = parseSessionView(session)
            _ui.update {
                val resetPinUi = it.activeSession?.sessionId != nextView?.sessionId ||
                    it.activeSession?.interactionPhase != nextView?.interactionPhase
                it.copy(
                    partnered = isPartnered,
                    partnerDeviceId = partnerDevice,
                    sessionToken = token,
                    sessionId = sidUuid,
                    activeSession = nextView,
                    pinVerifyStatus = if (resetPinUi) null else it.pinVerifyStatus,
                    pinVerifyIsError = if (resetPinUi) false else it.pinVerifyIsError,
                    pinVerifyBusy = if (resetPinUi) false else it.pinVerifyBusy,
                )
            }
            if (active && session?.optString("quest_id") == "quiz" && sidStr != null) {
                if (sidUuid != null) lastQuizSessionId = sidUuid
                refreshQuizSync(sidStr)
            } else {
                val prevQuizSid = lastQuizSessionId
                if (_ui.value.quiz != null && _ui.value.quiz?.completed != true && prevQuizSid != null) {
                    refreshQuizSync(prevQuizSid.toString())
                    refreshPetAndAchievements()
                }
                if (session != null && session.optString("quest_id") != "quiz") {
                    lastQuizSessionId = null
                    _ui.update { it.copy(quiz = null) }
                }
            }
            relayDeviceStateToWearable(ds)
        }.onFailure {
            android.util.Log.w("AppModel", "refreshDeviceState failed: ${it.message}")
        }
    }

    fun refreshDeviceState() {
        scope.launch { refreshDeviceStateSync() }
    }

    fun questAction(questId: String, demo: Boolean, landmarkId: String? = null, onResult: (Boolean, String?) -> Unit) {
        scope.launch {
            try {
                lastQuizSessionId = null
                _ui.update {
                    it.copy(
                        quiz = null,
                        proximityAlert = null,
                        pinVerifyStatus = null,
                        pinVerifyIsError = false,
                        pinVerifyBusy = false,
                    )
                }
                api.createSession(questId, demo, landmarkId)
                refreshDeviceStateSync()
                onResult(true, null)
            } catch (e: Exception) {
                refreshDeviceStateSync()
                onResult(false, e.message ?: "Failed to start $questId")
            }
        }
    }

    // (practiceRaid removed 14 Nov: the raid quest was cut — the
    //  board-to-board sustained link drops at 23-30 s, a hardware wall.)

    fun acceptSession(id: UUID, onResult: (Boolean, String?) -> Unit) {
        scope.launch {
            try {
                api.acceptSession(id)
                refreshDeviceStateSync()
                onResult(true, null)
            } catch (e: Exception) {
                refreshDeviceStateSync()
                onResult(false, e.message ?: "Failed to accept quest")
            }
        }
    }

    fun cancelSession(id: UUID, onResult: (Boolean, String?) -> Unit) {
        scope.launch {
            try {
                api.cancelSession(id)
                lastQuizSessionId = null
                _ui.update {
                    it.copy(
                        quiz = null,
                        proximityAlert = null,
                        pinVerifyStatus = null,
                        pinVerifyIsError = false,
                        pinVerifyBusy = false,
                    )
                }
                refreshDeviceStateSync()
                onResult(true, null)
            } catch (e: Exception) {
                refreshDeviceStateSync()
                onResult(false, e.message ?: "Failed to cancel quest")
            }
        }
    }

    // ==================== v2: pet + phone GPS ====================

    /** Refresh the server pet mirror and achievements. */
    fun refreshPetAndAchievements() {
        scope.launch {
            try {
                val p = api.pet()
                _ui.update { it.copy(pet = p) }
            } catch (e: Exception) {
                android.util.Log.w("AppModel", "pet fetch failed: ${e.message}")
            }
            refreshAchievements()
        }
    }

    // Phone GPS (v2): the ONLY location source in the product. One shared
    // LocationManager fix stamped onto relayed telemetry with its TRUE age.
    private var gpsListener: android.location.LocationListener? = null
    private var lastGpsReRegisterMs = 0L

    /** Achievements (15 Nov): fetch the catalog + this user's unlocks and
     *  diff against the previous fetch — any NEW unlock surfaces as a
     *  banner (newAchievement/newAchievementAt) for the main screen. */
    fun refreshAchievements() {
        scope.launch {
            try {
                val arr = api.achievements().getJSONArray("achievements")
                val opts = (0 until arr.length()).mapNotNull { i ->
                    val item = arr.optJSONObject(i) ?: return@mapNotNull null
                    AccView(
                        id = item.optString("id"),
                        name = item.optString("name"),
                        description = item.optString("description"),
                        unlocked = item.optBoolean("unlocked"),
                        unlockedAt = item.optString("unlocked_at").takeIf { it != "null" },
                    )
                }
                val newest = opts.filter { it.unlocked }
                    .maxByOrNull { it.unlockedAt ?: "" }
                val now = System.currentTimeMillis()
                _ui.update { cur ->
                    val prevUnlocked = cur.achievements.filter { it.unlocked }.map { it.id }.toSet()
                    if (newest != null && newest.id !in prevUnlocked) {
                        cur.copy(achievements = opts, newAchievement = newest.name, newAchievementAt = now)
                    } else {
                        cur.copy(achievements = opts)
                    }
                }
            } catch (e: Exception) {
                android.util.Log.w("AppModel", "achievements fetch failed: ${e.message}")
            }
        }
    }

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
                    2000L, 0f, listener, android.os.Looper.getMainLooper())
            }
            runCatching {
                lm.requestLocationUpdates(android.location.LocationManager.NETWORK_PROVIDER,
                    3000L, 0f, listener, android.os.Looper.getMainLooper())
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
            val fix = GpsFixView(
                latitude = location.latitude,
                longitude = location.longitude,
                fixTimeMs = location.time,
                accuracyM = location.accuracy,
            )
            _ui.update { it.copy(gpsFix = fix) }
        }
        try {
            // GPS is the real fix source; network provider is a fallback.
            // Registration (and callbacks) explicitly on the main looper:
            // requestLocationUpdates builds its callback Handler from the
            // CALLING thread, and startGps runs on a dispatcher worker that
            // has no Looper (verified: both registrations failed silently).
            runCatching {
                lm.requestLocationUpdates(android.location.LocationManager.GPS_PROVIDER,
                    2000L, 0f, listener, android.os.Looper.getMainLooper())
            }.onFailure { android.util.Log.w("AppModel", "GPS_PROVIDER failed: ${it.message}") }
            runCatching {
                lm.requestLocationUpdates(android.location.LocationManager.NETWORK_PROVIDER,
                    3000L, 0f, listener, android.os.Looper.getMainLooper())
            }.onFailure { android.util.Log.w("AppModel", "NETWORK_PROVIDER failed: ${it.message}") }
            gpsListener = listener
            android.util.Log.i("AppModel", "GPS listeners registered")
            val lastKnown = lm.getLastKnownLocation(android.location.LocationManager.GPS_PROVIDER)
                ?: lm.getLastKnownLocation(android.location.LocationManager.NETWORK_PROVIDER)
            lastKnown?.let {
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

    /** Handle MSG_PET_IDENTITY (25): [ver][species u8][nameLen u8][nonce LE64][name<=8].
     * Mirrors the wearable's bonded species/name to PUT /api/v1/me/pet and
     * ACKs via the shared MSG_INTERACTION_ACK nonce reply. */
    private fun handlePetIdentity(payload: ByteArray) {
        if (payload.size < 12 || payload[0].toInt() != 1) return
        val species = when (payload[1].toInt() and 0xFF) {
            0 -> "spark"
            1 -> "fluff"
            2 -> "pip"
            else -> return
        }
        val nameLen = payload[2].toInt() and 0xFF
        if (nameLen == 0 || nameLen > 8 || payload.size < 11 + nameLen) return
        val nonce = ByteBuffer.wrap(payload, 3, 8).order(ByteOrder.LITTLE_ENDIAN).long
        val rawName = String(payload, 11, nameLen, Charsets.US_ASCII).trim()
        val name = if (rawName.isEmpty() || rawName.equals("null", ignoreCase = true)) {
            species.replaceFirstChar { it.uppercase() }
        } else {
            rawName
        }
        scope.launch {
            val ok = runCatching {
                val updated = api.putPet(species, name)
                _ui.update { it.copy(pet = updated) }
                if (ble.state.value is BleLink.State.Connected) {
                    sendPetState()
                }
            }.isSuccess
            val ack = ByteArray(10)
            ack[0] = 1
            ByteBuffer.wrap(ack, 1, 8).order(ByteOrder.LITTLE_ENDIAN).putLong(nonce)
            ack[9] = if (ok) 1 else 0
            ble.send(Frame.MSG_INTERACTION_ACK, ack)
        }
    }

    /** Handle MSG_PET_CARE_EVENT (18): [ver][kind u8][date ASCII 10][nonce LE64].
     * Maps to POST /me/pet/care and ACKs via MSG_INTERACTION_ACK (nonce-reused). */
    private fun handlePetCareEvent(payload: ByteArray) {
        if (payload.size < 17 || payload[0].toInt() != 1) return
        val date = String(payload, 2, 10, Charsets.US_ASCII)
        val nonce = java.nio.ByteBuffer.wrap(payload, 12, 8)
            .order(java.nio.ByteOrder.LITTLE_ENDIAN).long
        scope.launch {
            val ok = runCatching {
                val updated = api.petCare(date)
                _ui.update { it.copy(pet = updated) }
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
        scope.launch { refreshQuizSync(sessionIdStr) }
    }

    private suspend fun refreshQuizSync(sessionIdStr: String) {
        val sid = runCatching { UUID.fromString(sessionIdStr) }.getOrNull() ?: return
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
            _ui.update { it.copy(quiz = view) }
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

    private fun buildQuizView(
        q: JSONObject, currentIdx: Int, total: Int, active: Boolean,
        error: String?,
    ): QuizView {
        val questions = q.getJSONArray("questions")
        var question: String? = null
        var options: List<String> = emptyList()
        val parsedResults = ArrayList<QuizQuestionResult>(questions.length())
        for (i in 0 until questions.length()) {
            val item = questions.getJSONObject(i)
            val idx = item.optInt("index")
            val text = item.optString("text")
            val arr = item.optJSONArray("options")
            val opts = (0 until (arr?.length() ?: 0)).map { arr!!.optString(it) }
            if (idx == currentIdx) {
                question = text
                options = opts
            }
            val answered = item.optBoolean("answered", false)
            val choice = if (item.isNull("choice")) null else item.optInt("choice")
            val rightIdx = if (item.isNull("right_index")) null else item.optInt("right_index")
            val isCorrect = if (item.isNull("is_correct")) null else item.optBoolean("is_correct")
            parsedResults.add(
                QuizQuestionResult(
                    index = idx,
                    text = text,
                    options = opts,
                    answered = answered,
                    choice = choice,
                    rightIndex = rightIdx,
                    isCorrect = isCorrect,
                )
            )
        }
        return QuizView(
            active = active,
            index = currentIdx,
            total = total,
            question = question,
            options = options,
            myAnswered = q.optInt("my_answered"),
            myTotal = q.optInt("my_total"),
            myCorrect = q.optInt("my_correct", 0),
            partnerAnswered = q.optInt("partner_answered"),
            partnerTotal = q.optInt("partner_total"),
            partnerCorrect = q.optInt("partner_correct", 0),
            completed = q.optBoolean("completed"),
            results = parsedResults,
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
            if (ble.state.value is BleLink.State.Connected) {
                ble.send(Frame.MSG_QUIZ_STATE, byteArrayOf(1, 0, 0, 0))
            }
            return
        }
        val sessionId = _ui.value.sessionId ?: lastQuizSessionId ?: return
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
                val view = buildQuizView(q, next, questions.length(), active, null)
                _ui.update { it.copy(quiz = view) }
                // Tell the wearable the next question (or end of quiz).
                val st = ByteArray(4)
                st[0] = 1
                st[1] = if (active) 1 else 0
                st[2] = (if (next >= 0) next else 0).toByte()
                st[3] = questions.length().toByte()
                if (ble.state.value is BleLink.State.Connected) {
                    ble.send(Frame.MSG_QUIZ_STATE, st)
                }
                if (q.optBoolean("completed")) {
                    refreshDeviceStateSync()
                    refreshPetAndAchievements()
                }
            }.onFailure { err ->
                android.util.Log.w("AppModel", "quiz answer failed: ${err.message}")
                _ui.update { cur ->
                    cur.copy(quiz = (cur.quiz ?: quiz).copy(lastError = err.message ?: "answer failed"))
                }
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
        // In Android JSONObject, optString returns "null" when the JSON value is NULL.
        val rawName = if (pet.isNull("species") || pet.isNull("name")) "" else pet.optString("name", "")
        val name = if (rawName.equals("null", ignoreCase = true)) "" else rawName
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

    // ==================== Nearby discovery ====================
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
                _ui.update {
                    it.copy(
                        partnered = partner != null,
                        partnerName = partner?.optString("display_name"),
                        partnerUserId = partner?.optString("id"),
                    )
                }
            }
            runCatching {
                val prof = api.discoveryProfile()
                _ui.update { it.copy(profile = prof) }
            }
            runCatching {
                val inv = api.invitations()
                _ui.update { it.copy(invitations = inv) }
            }.onFailure {
                _ui.update { it.copy(invitations = null) }
            }
        }
    }

    private suspend fun pollDiscovery() {
        try {
            // Refresh partnership + profile first: the desired board mode
            // derives from them, and either can change server-side (profile
            // edits, partnership end) without this phone being the actor.
            val me = api.me()
            val partner = me.optJSONObject("partner")
            _ui.update {
                it.copy(
                    partnered = partner != null,
                    partnerName = partner?.optString("display_name"),
                    partnerUserId = partner?.optString("id"),
                )
            }
            runCatching {
                val prof = api.discoveryProfile()
                _ui.update { it.copy(profile = prof) }
            }
            val out = api.discovery()
            _ui.update { it.copy(discovery = out, discoveryError = null) }
            refreshInvitationsQuiet()
            relayResultsToBoard(out)
            relayModeToBoard(force = false)
        } catch (e: Exception) {
            // Connection loss: mark discovery unavailable/stale honestly
            // instead of presenting cached profiles as current matches.
            _ui.update { it.copy(discoveryError = e.message ?: "discovery unavailable") }
        }
    }

    private suspend fun refreshInvitationsQuiet() {
        runCatching {
            val inv = api.invitations()
            _ui.update { it.copy(invitations = inv) }
        }
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
        _ui.update { it.copy(boardModeAcked = boardAckedMode == mode) }
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
                val prof = api.putDiscoveryProfile(body)
                _ui.update { it.copy(profile = prof) }
                relayModeToBoard(force = true)
                onResult(true, null)
            } catch (e: Exception) { onResult(false, e.message) }
        }
    }

    fun setOptIns(bluetoothEnabled: Boolean, gpsEnabled: Boolean, onResult: (Boolean, String?) -> Unit) {
        scope.launch {
            try {
                val prof = api.putDiscoverySettings(bluetoothEnabled, gpsEnabled)
                _ui.update { it.copy(profile = prof) }
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
