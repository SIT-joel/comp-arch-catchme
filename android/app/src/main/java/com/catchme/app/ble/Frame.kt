package com.catchme.app.ble

/**
 * Wire framing shared with the wearable firmware (firmware/catch_me_app/ble_app.cpp).
 *
 * Fragment (one BLE notification, <= 20 bytes):
 *   [0]=0xA5 [1]=ver [2]=type [3]=msgId [4]=fragIdx [5]=fragCount
 *   [6]=chunkLen [7]=crc8(bytes 0..6 + chunk bytes)
 *   [8..]=chunk
 *
 * Dropped/duplicate/reordered fragments must not corrupt a message: only a
 * complete, CRC-valid, in-order fragment set is delivered.
 */
object Frame {
    const val MAGIC: Int = 0xA5
    const val VERSION: Int = 1
    const val HEADER_SIZE = 8
    const val PAYLOAD_MAX = 12

    const val MSG_HELLO = 1
    const val MSG_TIME_ANCHOR = 2
    const val MSG_SESSION_STATE = 3
    const val MSG_PEER_HEARTBEAT = 4
    const val MSG_TELEMETRY = 5
    const val MSG_ACK = 6
    const val MSG_STATUS = 7
    // Nearby discovery (docs/DISCOVERY_PLAN.md) — versioned payloads,
    // separate from quest transport; unknown payload versions rejected.
    const val MSG_DISCOVERY_MODE = 8
    const val MSG_DISCOVERY_OBS = 9
    const val MSG_DISCOVERY_RESULTS = 10
    const val MSG_DISCOVERY_ACK = 11
    const val MSG_QUEUE_PURGE = 12
    const val MSG_PARTNER_INFO = 13
    const val MSG_INTERACTION_STATE = 14
    const val MSG_INTERACTION_COMMAND = 15
    const val MSG_INTERACTION_ACK = 16
    // v2 messages
    const val MSG_PET_STATE = 17
    const val MSG_PET_CARE_EVENT = 18
    const val MSG_GAME_STATE = 19
    const val MSG_GAME_INPUT = 20
    const val MSG_RAID_OUTCOME = 21
    const val MSG_RAID_START = 22
    const val MSG_QUIZ_STATE = 23
    const val MSG_QUIZ_ANSWER = 24

    fun crc8(data: ByteArray, n: Int): Int = crc8(data, n, 0x00)

    private fun crc8(data: ByteArray, n: Int, seed: Int): Int {
        var crc = seed
        for (i in 0 until n) {
            crc = crc xor (data[i].toInt() and 0xFF)
            repeat(8) {
                crc = if (crc and 0x80 != 0) ((crc shl 1) xor 0x07) and 0xFF else (crc shl 1) and 0xFF
            }
        }
        return crc
    }

    /**
     * Frame checksum input is bytes [0..6] followed by the payload chunk —
     * the CRC byte at [7] is never part of the input (matches the firmware's
     * crc8_frame; including [7] on receive would never validate).
     */
    fun crc8Frame(frame: ByteArray, chunk: Int): Int {
        var crc = 0x00
        fun step(b: Int) {
            crc = crc xor b
            repeat(8) {
                crc = if (crc and 0x80 != 0) ((crc shl 1) xor 0x07) and 0xFF else (crc shl 1) and 0xFF
            }
        }
        for (i in 0 until HEADER_SIZE - 1) step(frame[i].toInt() and 0xFF)
        for (i in 0 until chunk) step(frame[HEADER_SIZE + i].toInt() and 0xFF)
        return crc
    }

    /** Splits payload into framed fragments. Zero-payload messages (HELLO)
     * still send one empty fragment — the firmware's convention. */
    fun encode(type: Int, msgId: Int, payload: ByteArray): List<ByteArray> {
        val fragCount = maxOf(1, (payload.size + PAYLOAD_MAX - 1) / PAYLOAD_MAX)
        val out = ArrayList<ByteArray>(fragCount)
        for (frag in 0 until fragCount) {
            val off = frag * PAYLOAD_MAX
            val chunk = minOf(PAYLOAD_MAX, payload.size - off)
            val frame = ByteArray(HEADER_SIZE + chunk)
            frame[0] = MAGIC.toByte()
            frame[1] = VERSION.toByte()
            frame[2] = type.toByte()
            frame[3] = msgId.toByte()
            frame[4] = frag.toByte()
            frame[5] = fragCount.toByte()
            frame[6] = chunk.toByte()
            System.arraycopy(payload, off, frame, HEADER_SIZE, chunk)
            frame[7] = crc8Frame(frame, chunk).toByte()
            out.add(frame)
        }
        return out
    }
}

data class Message(val type: Int, val payload: ByteArray)

/** Reassembles fragments into complete messages. */
class FrameAssembler {
    private var expectedId = -1
    private var fragsLeft = 0
    private var buffer = ByteArray(0)

    /** Feed one fragment; returns a complete message or null.
     *  Synchronized: notifications arrive on arbitrary binder threads
     *  (verified: fragments of one message on 3+ workers), and a concurrent
     *  feed observing fragsLeft mid-update silently drops a middle fragment. */
    @Synchronized
    fun feed(frame: ByteArray): Message? {
        if (frame.size < Frame.HEADER_SIZE) return null
        if (frame[0].toInt() and 0xFF != Frame.MAGIC) return null
        if (frame[1].toInt() != Frame.VERSION) return null
        val chunk = frame[6].toInt() and 0xFF
        if (frame.size < Frame.HEADER_SIZE + chunk) return null
        val expected = Frame.crc8Frame(frame, chunk)
        if (expected != frame[7].toInt() and 0xFF) {
            reset(); return null // CRC failure: drop the partial message
        }
        val msgId = frame[3].toInt() and 0xFF
        val fragIdx = frame[4].toInt() and 0xFF
        val fragCount = frame[5].toInt() and 0xFF

        if (expectedId != msgId) {
            if (fragIdx != 0) return null // middle of an unknown message
            expectedId = msgId
            fragsLeft = fragCount
            buffer = ByteArray(0)
        }
        if (fragsLeft == 0) return null
        buffer += frame.copyOfRange(Frame.HEADER_SIZE, Frame.HEADER_SIZE + chunk)
        fragsLeft--
        return if (fragsLeft == 0) {
            val msg = Message(frame[2].toInt() and 0xFF, buffer)
            reset()
            msg
        } else {
            null
        }
    }

    @Synchronized
    fun reset() {
        fragsLeft = 0
        buffer = ByteArray(0)
    }
}
