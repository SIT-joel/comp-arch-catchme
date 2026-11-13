package com.catchme.app.ble

import android.annotation.SuppressLint
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothGatt
import android.bluetooth.BluetoothGattCallback
import android.bluetooth.BluetoothGattCharacteristic
import android.bluetooth.BluetoothGattDescriptor
import android.bluetooth.BluetoothManager
import android.bluetooth.BluetoothProfile
import android.bluetooth.le.ScanRecord
import android.content.Context
import android.os.Build
import android.util.Log
import com.catchme.app.BuildConfig
import kotlinx.coroutines.channels.BufferOverflow
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import java.util.UUID

/**
 * Owns the single wearable connection: scans for the CATCHME peer advertisement
 * (manufacturer-specific field with the 0xC5 magic), connects, enables
 * notifications on the UART RX characteristic, writes to the TX characteristic.
 *
 * The wearable is the peripheral; the phone is the only central connection it
 * accepts. Peer-to-peer evidence never flows through this link — the two
 * wearables observe each other's advertisements directly (docs/AGENTS.md).
 */
class BleLink(private val context: Context) {

    // Nordic UART service UUIDs — must match firmware/catch_me_app/ble_app.cpp.
    private val uartService: UUID = UUID.fromString("6e400001-b5a3-f393-e0a9-e50e24dcca9e")
    private val uartTxChar: UUID = UUID.fromString("6e400002-b5a3-f393-e0a9-e50e24dcca9e") // phone writes
    private val uartRxChar: UUID = UUID.fromString("6e400003-b5a3-f393-e0a9-e50e24dcca9e") // phone listens
    private val cccd: UUID = UUID.fromString("00002902-0000-1000-8000-00805f9b34fb")

    sealed interface State {
        data object Idle : State
        data object Scanning : State
        data object Connecting : State
        data object Connected : State
        data class Failed(val reason: String) : State
    }

    private val _state = MutableStateFlow<State>(State.Idle)
    val state: StateFlow<State> = _state

    private val _messages = MutableSharedFlow<Message>(
        extraBufferCapacity = 32, onBufferOverflow = BufferOverflow.DROP_OLDEST
    )
    val messages: SharedFlow<Message> = _messages

    private val assembler = FrameAssembler()
    private var adapter: BluetoothAdapter? = null
    private var gatt: BluetoothGatt? = null
    private var txCharacteristic: BluetoothGattCharacteristic? = null
    private var msgCounter = 0
    private var rxLogged = 0

    fun ensureAdapter(): Boolean {
        val manager = context.getSystemService(Context.BLUETOOTH_SERVICE) as? BluetoothManager
        adapter = manager?.adapter
        return adapter != null && adapter!!.isEnabled
    }

    @SuppressLint("MissingPermission")
    fun connect(ownAlias: Int) {
        if (!ensureAdapter()) {
            _state.value = State.Failed("Bluetooth unavailable or not enabled")
            return
        }
        val current = _state.value
        if (current is State.Scanning || current is State.Connecting || current is State.Connected) {
            return // connect is called by the screen and supervisor; keep it idempotent
        }
        // Fail visibly instead of crashing when runtime grants are missing
        // (SecurityException from startScan otherwise kills the process).
        // API < 31 has no runtime BLUETOOTH_* permissions; scanning there is
        // gated by ACCESS_FINE_LOCATION (e.g. the Tab S5e on Android 11).
        val scanGranted = context.checkSelfPermission(android.Manifest.permission.BLUETOOTH_SCAN) ==
            android.content.pm.PackageManager.PERMISSION_GRANTED
        val connGranted = context.checkSelfPermission(android.Manifest.permission.BLUETOOTH_CONNECT) ==
            android.content.pm.PackageManager.PERMISSION_GRANTED
        val bleOk = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            scanGranted && connGranted
        } else {
            context.checkSelfPermission(android.Manifest.permission.ACCESS_FINE_LOCATION) ==
                android.content.pm.PackageManager.PERMISSION_GRANTED
        }
        if (!bleOk) {
            _state.value = State.Failed("Bluetooth permission not granted")
            return
        }
        val scanner = adapter?.bluetoothLeScanner
        if (scanner == null) {
            _state.value = State.Failed("Bluetooth scanner unavailable")
            return
        }
        // The wearable advertises its heartbeat in manufacturer-specific data
        // ([0]=0xC5 magic, [1]=DEVICE_ID, [2..3]=counter, [4..5]=token hash).
        // The phone connects to ITS OWN wearable only (alias match); peer
        // evidence flows wearable-to-wearable, never through this link.
        wantedAlias = ownAlias
        beginScan()
    }

    /** Stop any stale registration and start a scan with the CURRENT callback.
     * UNFILTERED scan + software match in onScanResult: on Samsung OneUI,
     * hardware-filtered scans are counted by the stack but NOT delivered
     * to the app while other scan clients are active (observed live:
     * filter Results=343→391 over 20 s with zero callbacks; 12 system
     * scan clients registered). Screen must be on for unfiltered scans —
     * acceptable for the demo (the app is used actively).
     * BALANCED, not LOW_LATENCY: Samsung throttles aggressive duty cycles
     * from non-system apps; balanced delivers reliably (board advertises
     * three times per 10 s TDD cycle, so latency impact is negligible). */
    @SuppressLint("MissingPermission")
    private fun beginScan() {
        val scanner = adapter?.bluetoothLeScanner ?: return
        runCatching { scanner.stopScan(scanCallback) }
        // FRESH callback for EVERY scan session: the S21+ (Android 15) refuses
        // scanner re-registration of a callback that already delivered results
        // and was stopped after a GATT connect — the wedge that produced
        // SCAN_FAILED_REGISTRATION_FAILED on every post-disconnect rescan.
        // The FE (Android 16) tolerates reuse; rotating is safe on both.
        scanCallback = newScanCallback()
        _state.value = State.Scanning
        scanStartedAt = System.currentTimeMillis()
        val balanced = android.bluetooth.le.ScanSettings.Builder()
            .setScanMode(android.bluetooth.le.ScanSettings.SCAN_MODE_BALANCED)
            .build()
        scanner.startScan(null, balanced, scanCallback)
    }

    private var wantedAlias = 1
    private var scanStartedAt = 0L
    private var lastDevice: BluetoothDevice? = null
    private var reconnectTries = 0
    // Samsung eventually refuses scanner re-registration after many stop/start
    // cycles of ONE callback instance (observed live on the S21+/S24 FE as
    // onScanFailed errorCode 2, REGISTRATION_FAILED, hitting both phones
    // repeatedly). A fresh callback object per scan session gives the stack a
    // clean registration; bounded auto-retry recovers transient refusals.
    private var scanCallback: android.bluetooth.le.ScanCallback = newScanCallback()
    private var scanFailures = 0

    /** Samsung stops delivering scan results after a while; restart the scan
     * (through beginScan so every restart also gets a fresh callback). */
    fun restartScanIfStale(maxAgeMs: Long = 30000) {
        val state = _state.value
        if (state is State.Scanning && System.currentTimeMillis() - scanStartedAt > maxAgeMs) {
            beginScan()
        }
    }

    /** Parses an advertisement record for our manufacturer heartbeat field:
     *  [len][0xFF][company LE 2B = 0x0030][0xC5][device][counter 2B][token 2B].
     *  NB: every Byte must be masked with `and 0xFF` before comparing —
     *  Byte.toInt() sign-extends (0xFF -> -1), so `== 0xFF` never matches. */
    private fun parseHeartbeatAlias(record: ByteArray?): Int? {
        if (record == null) return null
        var i = 0
        while (i + 1 < record.size) {
            val fieldLen = record[i].toInt() and 0xFF
            if (fieldLen == 0 || i + 1 + fieldLen > record.size) return null
            if ((record[i + 1].toInt() and 0xFF) == 0xFF && fieldLen >= 9 &&
                (record[i + 2].toInt() and 0xFF) == 0x30 &&
                (record[i + 3].toInt() and 0xFF) == 0x00 &&
                (record[i + 4].toInt() and 0xFF) == 0xC5
            ) {
                return record[i + 5].toInt() and 0xFF
            }
            i += 1 + fieldLen
        }
        return null
    }

    /** Android exposes manufacturer data separately from the raw AD bytes.
     * Use it as a fallback for devices whose ScanRecord omits/reformats AD fields. */
    private fun parseHeartbeatManufacturerAlias(record: ScanRecord?): Int? {
        val payload = record?.getManufacturerSpecificData(0x0030) ?: return null
        if (payload.size < 2 || (payload[0].toInt() and 0xFF) != 0xC5) return null
        return payload[1].toInt() and 0xFF
    }

    private fun newScanCallback(): android.bluetooth.le.ScanCallback = object : android.bluetooth.le.ScanCallback() {
        @Volatile private var resultCount = 0
        @Volatile private var scanRecordCount = 0
        @Volatile private var company30Count = 0
        @Volatile private var heartbeatCount = 0
        @Volatile private var discoveryCount = 0
        @Volatile private var alias1Count = 0
        @Volatile private var alias2Count = 0
        private val lastAliasLogAt = LongArray(3)

        @SuppressLint("MissingPermission")
        override fun onScanResult(callbackType: Int, result: android.bluetooth.le.ScanResult) {
            resultCount++
            scanFailures = 0  // a working scan proves the stack recovered
            val record = result.scanRecord
            if (record != null) scanRecordCount++
            val manufacturer = record?.getManufacturerSpecificData(0x0030)
            if (manufacturer != null) {
                company30Count++
                if (manufacturer.isNotEmpty()) {
                    when (manufacturer[0].toInt() and 0xFF) {
                        0xC5 -> {
                            heartbeatCount++
                        }
                        0xC6 -> discoveryCount++
                    }
                }
            }
            val rawAlias = parseHeartbeatAlias(record?.bytes)
            val alias = rawAlias ?: parseHeartbeatManufacturerAlias(record)
            if (alias == 1) alias1Count++
            if (alias == 2) alias2Count++
            if (resultCount % 20 == 1) {
                Log.i(TAG, "scan results=$resultCount records=$scanRecordCount company30=$company30Count " +
                    "heartbeat=$heartbeatCount discovery=$discoveryCount alias1=$alias1Count alias2=$alias2Count")
            }
            if (result.device.address == "01:80:E1:00:34:12") {
                Log.i(TAG, "board-1 address observed; raw alias=" + parseHeartbeatAlias(result.scanRecord?.bytes))
            }
            if (alias == null) return
            if (BuildConfig.DEBUG && alias in 1..2) {
                val now = System.currentTimeMillis()
                if (now - lastAliasLogAt[alias] >= 5000) {
                    lastAliasLogAt[alias] = now
                    Log.i(TAG, "CATCHME heartbeat alias=$alias rssi=${result.rssi}")
                }
            }
            if (alias != wantedAlias) return
            val device: BluetoothDevice = result.device
            Log.i(TAG, "scan hit alias=$alias addr=${device.address}")
            lastDevice = device
            reconnectTries = 0
            adapter?.bluetoothLeScanner?.stopScan(this)
            _state.value = State.Connecting
            gatt?.close()  // release any stale client before taking its slot
            gatt = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                device.connectGatt(context, false, gattCallback, BluetoothDevice.TRANSPORT_LE)
            } else {
                device.connectGatt(context, false, gattCallback)
            }
        }

        override fun onScanFailed(errorCode: Int) {
            Log.w(TAG, "scan failed: $errorCode (consecutive=$scanFailures)")
            runCatching { adapter?.bluetoothLeScanner?.stopScan(this) }
            if (scanFailures >= 3) {
                _state.value = State.Failed("Scan failed: $errorCode")
                return
            }
            scanFailures++
            // Re-register with a BRAND-NEW callback after a short cool-down;
            // most Samsung REGISTRATION_FAILED refusals clear this way.
            android.os.Handler(android.os.Looper.getMainLooper()).postDelayed({
                if (_state.value is State.Scanning || _state.value is State.Failed) {
                    scanCallback = newScanCallback()
                    beginScan()
                }
            }, 2000)
        }
    }

    /** Controller-level reconnect after a scheduled TDD disconnect (see the
     * disconnect branch). Returns false when no cached device remains or the
     * retry budget is spent, so the caller falls back to Idle + fresh scan. */
    @SuppressLint("MissingPermission")
    private fun reconnectControllerLevel(): Boolean {
        val dev = lastDevice ?: return false
        if (reconnectTries >= 5) return false
        reconnectTries++
        _state.value = State.Connecting
        val old = gatt
        gatt = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            dev.connectGatt(context, true, gattCallback, BluetoothDevice.TRANSPORT_LE)
        } else {
            dev.connectGatt(context, true, gattCallback)
        }
        // The previous client's link is already down (its own disconnect
        // callback led here); without close() its controller-level slot
        // LEAKS every TDD cycle — observed live as 13 concurrent zombie
        // GATTs, status-257 storms, and the scan-registration wedge.
        runCatching { old?.close() }
        return gatt != null
    }

    private val gattCallback: BluetoothGattCallback = object : BluetoothGattCallback() {
        @SuppressLint("MissingPermission")
        override fun onConnectionStateChange(g: BluetoothGatt, status: Int, newState: Int) {
            if (g !== gatt) {
                // Zombie client (leaked before the close-on-replace fix, or a
                // raced autoConnect): release it and ignore its events — its
                // callbacks must never drive the app state or the assembler.
                Log.w(TAG, "stale gatt released (state=$newState status=$status)")
                runCatching { g.close() }
                return
            }
            Log.i(TAG, "conn state: $newState status=$status")
            when (newState) {
                BluetoothProfile.STATE_CONNECTED -> {
                    reconnectTries = 0
                    g.discoverServices()
                }
                BluetoothProfile.STATE_DISCONNECTED -> {
                    Log.w(TAG, "GATT disconnected (status=$status)")
                    // Reconnect at the CONTROLLER level: autoConnect=true makes
                    // the chip wait for the board's advertisement itself — no
                    // app-level scanner registration, which is exactly what the
                    // S21+ (One UI 6.1) refuses after one scan->GATT cycle
                    // (SCAN_FAILED_REGISTRATION_FAILED). The board's static
                    // public address makes autoConnect safe. Supervisor stays
                    // as fallback if the controller connect cannot start.
                    if (!reconnectControllerLevel()) _state.value = State.Idle
                }
            }
        }

        @SuppressLint("MissingPermission")
        override fun onServicesDiscovered(g: BluetoothGatt, status: Int) {
            Log.i(TAG, "services discovered status=$status")
            if (status != BluetoothGatt.GATT_SUCCESS) {
                _state.value = State.Failed("Service discovery failed: $status")
                return
            }
            val service = g.getService(uartService) ?: run {
                _state.value = State.Failed("UART service missing on device")
                return
            }
            val rx = service.getCharacteristic(uartRxChar)
            val tx = service.getCharacteristic(uartTxChar)
            if (rx == null || tx == null) {
                _state.value = State.Failed("UART characteristics missing")
                return
            }
            txCharacteristic = tx
            g.setCharacteristicNotification(rx, true)
            val descriptor = rx.getDescriptor(cccd) ?: return
            descriptor.value = BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE
            g.writeDescriptor(descriptor)
        }

        override fun onDescriptorWrite(g: BluetoothGatt, d: android.bluetooth.BluetoothGattDescriptor, status: Int) {
            if (d.uuid == cccd) {
                Log.i(TAG, "CCCD written status=$status -> CONNECTED")
                _state.value = State.Connected
                send(Frame.MSG_HELLO, ByteArray(0))
            }
        }

        override fun onCharacteristicChanged(
            g: BluetoothGatt,
            characteristic: BluetoothGattCharacteristic,
            value: ByteArray,
        ) {
            if (rxLogged < 6) {
                rxLogged++
                Log.i(TAG, "notify rx: " + value.joinToString("") { "%02x".format(it) })
            }
            if (characteristic.uuid == uartRxChar) {
                assembler.feed(value)?.let { _messages.tryEmit(it) }
            }
        }
    }

    /** Serialized: concurrent senders (state loop, uploader acks, HELLO) must
     *  never interleave fragments of different messages. */
    @Synchronized
    @SuppressLint("MissingPermission")
    fun send(type: Int, payload: ByteArray): Boolean {
        val g = gatt ?: return false
        val tx = txCharacteristic ?: return false
        val id = ++msgCounter
        for (frame in Frame.encode(type, id, payload)) {
            tx.value = frame
            if (!g.writeCharacteristic(tx)) return false
            // BlueNRG's write-without-response queue is tiny: fragments sent
            // faster than ~40 ms apart arrive corrupted (verified as CRC
            // mismatches on the board). This send runs on IO dispatchers.
            Thread.sleep(90)
        }
        return true
    }

    @SuppressLint("MissingPermission")
    fun close() {
        adapter?.bluetoothLeScanner?.stopScan(scanCallback)
        gatt?.disconnect()
        gatt?.close()
        gatt = null
        _state.value = State.Idle
    }

    companion object {
        private const val TAG = "BleLink"
    }
}
