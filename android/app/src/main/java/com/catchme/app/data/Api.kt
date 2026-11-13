package com.catchme.app.data

import android.util.Log
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject
import java.util.UUID
import java.util.concurrent.TimeUnit

/**
 * Minimal API client for the Catch Me backend (contract: docs/INTERFACES.md).
 * Bearer-token authentication; the token is kept in memory + SharedPreferences
 * (no device secrets beyond the signed-in session).
 */
class Api(private val baseUrl: String) {

    /** Cloudflare Access service token headers; empty strings = not sent. */
    var accessId: String? = null
    var accessSecret: String? = null

    private val client = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(20, TimeUnit.SECONDS)
        .addInterceptor { chain ->
            val id = accessId
            val secret = accessSecret
            val request = if (!id.isNullOrEmpty() && !secret.isNullOrEmpty()) {
                chain.request().newBuilder()
                    .header("CF-Access-Client-Id", id)
                    .header("CF-Access-Client-Secret", secret)
                    .build()
            } else {
                chain.request()
            }
            chain.proceed(request)
        }
        .build()

    var token: String? = null

    class ApiError(val status: Int, val code: String, message: String) : Exception(message)

    private fun call(method: String, path: String, body: JSONObject? = null): JSONObject {
        val builder = Request.Builder()
            .url(baseUrl.trimEnd('/') + path)
            .method(method, body?.toString()?.toRequestBody("application/json".toMediaType())
                ?: if (method == "POST" || method == "PUT") "{}".toRequestBody() else null)
        token?.let { builder.addHeader("Authorization", "Bearer $it") }
        client.newCall(builder.build()).execute().use { resp ->
            val text = resp.body?.string() ?: "{}"
            val json = if (text.isBlank()) JSONObject() else runCatching { JSONObject(text) }
                .getOrElse { JSONObject() }
            if (!resp.isSuccessful) {
                val err = json.optJSONObject("error")
                throw ApiError(resp.code, err?.optString("code") ?: "error",
                    err?.optString("message") ?: resp.message)
            }
            return json
        }
    }

    fun login(username: String, password: String): JSONObject {
        val out = call("POST", "/api/v1/auth/login",
            JSONObject().put("username", username).put("password", password))
        token = out.getString("token")
        return out
    }

    fun me(): JSONObject = call("GET", "/api/v1/me")
    fun quests(): JSONArray = call("GET", "/api/v1/quests").getJSONArray("quests")

    fun bindDevice(pairingCode: String): JSONObject =
        call("POST", "/api/v1/devices/bind", JSONObject().put("pairing_code", pairingCode))

    fun deviceState(deviceId: UUID): JSONObject = call("GET", "/api/v1/devices/$deviceId/state")

    fun createSession(questId: String, demo: Boolean, landmarkId: String? = null): JSONObject {
        val body = JSONObject().put("quest_id", questId).put("demo", demo)
        if (landmarkId != null) body.put("landmark_id", landmarkId)
        return call("POST", "/api/v1/sessions", body)
    }

    // --- v2 pet + landmarks ---
    fun landmarks(): JSONArray = call("GET", "/api/v1/landmarks").getJSONArray("landmarks")
    fun pet(): JSONObject = call("GET", "/api/v1/me/pet")
    fun putPet(species: String, name: String): JSONObject =
        call("PUT", "/api/v1/me/pet", JSONObject().put("species", species).put("name", name))
    fun petCare(date: String): JSONObject =
        call("POST", "/api/v1/me/pet/care", JSONObject().put("date", date))

    fun acceptSession(id: UUID): JSONObject = call("POST", "/api/v1/sessions/$id/accept")

    /** 'Know Your Partner' quiz (server-generated; no correct index here). */
    fun quiz(sessionId: UUID): JSONObject =
        call("GET", "/api/v1/sessions/$sessionId/quiz")

    fun quizAnswer(sessionId: UUID, questionIndex: Int, choice: Int): JSONObject =
        call("POST", "/api/v1/sessions/$sessionId/quiz/answer",
            JSONObject().put("question_index", questionIndex).put("choice", choice))

    fun raidOutcome(
        id: UUID,
        outcome: String,
        fightStartedAt: String,
        fightEndedAt: String,
        commandId: UUID,
    ): JSONObject = call(
        "POST", "/api/v1/sessions/$id/raid/outcome",
        JSONObject()
            .put("outcome", outcome)
            .put("fight_started_at", fightStartedAt)
            .put("fight_ended_at", fightEndedAt)
            .put("command_id", commandId.toString()),
    )
    fun cancelSession(id: UUID): JSONObject = call("POST", "/api/v1/sessions/$id/cancel")
    fun session(id: UUID): JSONObject = call("GET", "/api/v1/sessions/$id")

    fun interaction(id: UUID): JSONObject = call("GET", "/api/v1/sessions/$id/interaction")

    fun submitInteractionPin(
        id: UUID, stage: String, pin: String, version: Int, commandId: UUID,
    ): JSONObject = call("POST", "/api/v1/sessions/$id/interaction/pin/submit",
        JSONObject().put("stage", stage).put("pin", pin)
            .put("code_version", version).put("command_id", commandId.toString()))

    fun refreshInteractionPin(id: UUID, stage: String, commandId: UUID): JSONObject =
        call("POST", "/api/v1/sessions/$id/interaction/pin/refresh",
            JSONObject().put("stage", stage).put("command_id", commandId.toString()))

    /** Server time for the device anchor: returns unix_ms. */
    fun serverTimeMs(): Long = call("GET", "/api/v1/time").getLong("unix_ms")

    /**
     * Upload queued records; returns the ack JSON (accepted identities,
     * duplicates, state_version). Retries send the SAME record identities —
     * identity is preserved in the queue rows, never regenerated.
     */
    fun uploadBatch(deviceId: UUID, records: JSONArray): JSONObject =
        call("POST", "/api/v1/telemetry/batches",
            JSONObject()
                .put("schema_version", 1)
                .put("device_id", deviceId.toString())
                .put("records", records))

    // --- Nearby discovery (docs/DISCOVERY_PLAN.md) ---

    fun discoveryProfile(): JSONObject = call("GET", "/api/v1/me/discovery-profile")

    fun putDiscoveryProfile(body: JSONObject): JSONObject =
        call("PUT", "/api/v1/me/discovery-profile", body)

    fun putDiscoverySettings(bluetoothEnabled: Boolean, gpsEnabled: Boolean): JSONObject =
        call("PUT", "/api/v1/me/discovery-settings",
            JSONObject()
                .put("bluetooth_enabled", bluetoothEnabled)
                .put("gps_enabled", gpsEnabled))

    fun discovery(): JSONObject = call("GET", "/api/v1/me/discovery")

    fun discoveryToken(): JSONObject =
        call("POST", "/api/v1/me/discovery-token")

    /** Idempotent upload of direct wearable scan observations. */
    fun uploadObservations(observations: JSONArray): JSONObject =
        call("POST", "/api/v1/discovery/observations",
            JSONObject()
                .put("schema_version", 1)
                .put("observations", observations))

    fun invitations(): JSONObject = call("GET", "/api/v1/invitations")

    fun createInvitation(toUserId: UUID): JSONObject =
        call("POST", "/api/v1/invitations", JSONObject().put("to_user_id", toUserId.toString()))

    fun acceptInvitation(id: UUID): JSONObject = call("POST", "/api/v1/invitations/$id/accept")

    fun declineInvitation(id: UUID): JSONObject = call("POST", "/api/v1/invitations/$id/decline")

    fun partnership(): JSONObject = call("GET", "/api/v1/me/partnership")

    fun endPartnership(): JSONObject = call("DELETE", "/api/v1/me/partnership")

    companion object {
        private const val TAG = "Api"
        fun warn(msg: String) = Log.w(TAG, msg)
    }
}
