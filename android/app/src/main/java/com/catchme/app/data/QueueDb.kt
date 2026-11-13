package com.catchme.app.data

import android.content.Context
import androidx.room.Dao
import androidx.room.Database
import androidx.room.Entity
import androidx.room.Insert
import androidx.room.PrimaryKey
import androidx.room.Query
import androidx.room.Room
import androidx.room.RoomDatabase
import org.json.JSONArray
import org.json.JSONObject
import java.util.UUID

/**
 * Persistent upload queue. Rows keep the server-record identity (device/boot/
 * sequence) so retries never mint new identities (docs/INTERFACES.md).
 */
@Entity(tableName = "queue")
data class QueueRow(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val deviceId: String,
    val bootId: String,
    val sequence: Long,
    val sessionId: String?,   // null when captured outside a session
    val payload: String,      // full server-format record JSON (built once)
    val capturedAtMs: Long,   // capture wall time for anchoring
    val synced: Boolean = false,
)

@Dao
interface QueueDao {
    @Insert
    fun insert(row: QueueRow): Long

    @Query("SELECT * FROM queue WHERE synced = 0 ORDER BY id LIMIT :n")
    fun pending(n: Int): List<QueueRow>

    @Query("UPDATE queue SET synced = 1 WHERE id IN (:ids)")
    fun markSynced(ids: List<Long>)

    @Query("DELETE FROM queue WHERE synced = 1 AND id < :beforeId")
    fun pruneSynced(beforeId: Long)

    @Query("SELECT COUNT(*) FROM queue WHERE synced = 0")
    fun pendingCount(): Int
}

@Database(entities = [QueueRow::class], version = 1, exportSchema = false)
abstract class QueueDb : RoomDatabase() {
    abstract fun dao(): QueueDao

    companion object {
        fun build(context: Context): QueueDb =
            Room.databaseBuilder(context, QueueDb::class.java, "catch_me_queue")
                .fallbackToDestructiveMigration() // prototype: queue is a cache
                .build()
    }
}

/** Expands firmware binary telemetry (32-byte record + u32 sequence) into the
 * server JSON record format. Capture time comes from the phone's receive
 * timeline anchored by TIME_ANCHOR; when unsynced, captured_at is null. */
object RecordCodec {
    fun decode(payload: ByteArray, bootId: String, sessionActive: Boolean, sessionId: UUID?,
               synced: Boolean, capturedEpoch: Long, uncertaintyMs: Int): Pair<Long, JSONObject> {
        require(payload.size >= 4 + 32) { "short telemetry payload" }
        var p = 0
        fun u32(): Long {
            val v = (payload[p].toInt() and 0xFF) or ((payload[p + 1].toInt() and 0xFF) shl 8) or
                ((payload[p + 2].toInt() and 0xFF) shl 16) or ((payload[p + 3].toInt() and 0xFF) shl 24)
            p += 4; return v.toLong() and 0xFFFFFFFFL
        }
        fun u16(): Int {
            val v = (payload[p].toInt() and 0xFF) or ((payload[p + 1].toInt() and 0xFF) shl 8)
            p += 2; return v
        }
        fun u8(): Int { val v = payload[p].toInt() and 0xFF; p += 1; return v }

        val sequence = u32()
        val uptime = u32()
        val capturedEpochRec = u32().toInt()
        val uncertainty = u16()
        val flags = u8()
        val bpm = u8()
        val hrStatus = u8()
        val lat = payload.toIntAt(p).also { p += 4 }
        val lon = payload.toIntAt(p).also { p += 4 }
        val fixAge = u16()
        val peerDevice = u8()
        val peerHeartbeat = u16()
        val peerObsAge = u16()
        val peerTokenHash = u16()
        p += 2 // reserved

        val hrValid = flags and 0x02 != 0
        val gpsValid = flags and 0x01 != 0
        val peerObserved = flags and 0x04 != 0

        val statusName = when (hrStatus) {
            0 -> "valid"; 1 -> "warming_up"; 2 -> "no_contact"; else -> "invalid_signal"
        }

        val clock = if (synced && capturedEpochRec != 0) {
            JSONObject().put("source", "phone_server_anchor").put("uncertainty_ms", uncertainty)
        } else {
            JSONObject().put("source", "unsynced").put("uncertainty_ms", JSONObject.NULL)
        }

        val rec = JSONObject()
            .put("boot_id", bootId)
            .put("sequence", sequence)
            .put("session_id", sessionId?.toString() ?: JSONObject.NULL)
            .put("uptime_ms", uptime)
            .put("captured_at", if (synced && capturedEpochRec != 0)
                java.time.Instant.ofEpochSecond(capturedEpochRec.toLong()).toString()
            else JSONObject.NULL)
            .put("clock", clock)
            .put("gps", JSONObject()
                .put("valid", gpsValid)
                .put("latitude", if (gpsValid) lat / 1_000_000.0 else JSONObject.NULL)
                .put("longitude", if (gpsValid) lon / 1_000_000.0 else JSONObject.NULL)
                .put("fix_age_ms", if (gpsValid) fixAge else JSONObject.NULL))
            .put("heart_rate", JSONObject()
                .put("valid", hrValid)
                .put("bpm", if (hrValid) bpm else JSONObject.NULL)
                .put("status", statusName))
        val peerJson = if (peerObserved) {
            JSONObject()
                .put("observed", true)
                .put("device_id", JSONObject.NULL) // filled by uploader via alias map
                .put("boot_id", "d$peerDevice")     // provisional; server matches alias
                .put("heartbeat_sequence", peerHeartbeat)
                .put("session_token", JSONObject.NULL) // resolved via alias map
                .put("observation_age_ms", peerObsAge)
        } else {
            JSONObject().put("observed", false)
        }
        rec.put("peer", peerJson)
        return Pair(sequence, rec)
    }

    private fun ByteArray.toIntAt(off: Int): Int =
        (this[off].toInt()) or (this[off + 1].toInt() shl 8) or
            (this[off + 2].toInt() shl 16) or (this[off + 3].toInt() shl 24)
}
