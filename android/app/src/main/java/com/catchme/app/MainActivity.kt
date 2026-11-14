package com.catchme.app

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import com.catchme.app.ble.BleLink
import com.catchme.app.data.AppModel
import java.util.UUID

/** Foreground-only companion app (docs/PROJECT_SPEC.md scope). */
class MainActivity : ComponentActivity() {

    private lateinit var model: AppModel

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        // Cloudflare Access + API base: launch extras are PERSISTED to prefs
        // on first launch, so normal icon-taps keep working without adb.
        // Values are trimmed: CRLF .env endings otherwise leak control chars
        // into the headers and Cloudflare Access rejects them (verified).
        val apiPrefs = getSharedPreferences("api", MODE_PRIVATE)
        val extraBase = intent?.getStringExtra("api_base")
        val extraId = intent?.getStringExtra("cf_id")?.trim()
        val extraSecret = intent?.getStringExtra("cf_secret")?.trim()
        if (extraBase != null || extraId != null) {
            apiPrefs.edit()
                .putString("api_base", extraBase ?: apiPrefs.getString("api_base", null))
                .putString("cf_id", extraId ?: apiPrefs.getString("cf_id", null))
                .putString("cf_secret", extraSecret ?: apiPrefs.getString("cf_secret", null))
                .apply()
        }
        val apiBase = extraBase ?: apiPrefs.getString("api_base", null) ?: BuildConfig.API_BASE
        model = AppModel(this, apiBase)
        model.api.accessId = extraId ?: apiPrefs.getString("cf_id", null) ?: BuildConfig.CF_ACCESS_ID
        model.api.accessSecret = extraSecret ?: apiPrefs.getString("cf_secret", null) ?: BuildConfig.CF_ACCESS_SECRET
        requestBlePermissions()
        // Auto-start the wearable link after every launch (14 Nov): the app
        // restores the session and connects without on-screen taps — the GPS
        // keep-alive lives in the link supervisor, so an idle link also froze
        // the quest fix stamps. startLink no-ops when no session was
        // restored (deviceAlias absent), so the sign-in screen is unaffected.
        model.restoreSession {
            model.startLink()
        }
        setContent {
            MaterialTheme {
                AppScreens(model)
            }
        }
    }

    private fun requestBlePermissions() {
        val needed = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            arrayOf(Manifest.permission.BLUETOOTH_SCAN, Manifest.permission.BLUETOOTH_CONNECT)
        } else {
            arrayOf(Manifest.permission.ACCESS_FINE_LOCATION)
        }
        val missing = needed.filter {
            ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED
        }
        if (missing.isNotEmpty()) {
            ActivityCompat.requestPermissions(this, missing.toTypedArray(), 1)
        }
    }

    override fun onResume() {
        super.onResume()
        // Discovery polls only while the screen is visible (5 s cadence).
        model.screenVisible = true
        model.refreshDiscoveryState()
    }

    override fun onPause() {
        super.onPause()
        model.screenVisible = false
    }

    override fun onDestroy() {
        model.close()
        super.onDestroy()
    }
}

@Composable
fun AppScreens(model: AppModel) {
    val ui by model.ui.collectAsState()
    if (!ui.signedIn) LoginScreen(model) else MainScreen(model, ui)
}

@Composable
fun LoginScreen(model: AppModel) {
    var username by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var error by remember { mutableStateOf<String?>(null) }
    Column(
        Modifier.fillMaxSize().padding(24.dp),
        verticalArrangement = Arrangement.Center
    ) {
        Text("Catch Me", style = MaterialTheme.typography.headlineLarge)
        Spacer(Modifier.height(16.dp))
        OutlinedTextField(username, { username = it }, label = { Text("Username") },
            modifier = Modifier.fillMaxWidth())
        OutlinedTextField(password, { password = it }, label = { Text("Password") },
            modifier = Modifier.fillMaxWidth())
        error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        Spacer(Modifier.height(8.dp))
        Button(onClick = {
            model.login(username, password) { ok, msg -> if (!ok) error = msg }
        }) { Text("Sign in") }
    }
}

@Composable
fun MainScreen(model: AppModel, ui: AppModel.UiState) {
    val bleState by model.ble.state.collectAsState()
    var pairingCode by remember { mutableStateOf("") }
    var demoMode by remember { mutableStateOf(true) }
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text("Catch Me — ${ui.username ?: ""}", style = MaterialTheme.typography.titleLarge)
        if (demoMode) Text("DEMO MODE", color = MaterialTheme.colorScheme.tertiary)

        Card {
            Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text("Wearable link")
                Text(
                    when (bleState) {
                        BleLink.State.Idle -> "idle"
                        BleLink.State.Scanning -> "scanning…"
                        BleLink.State.Connecting -> "connecting…"
                        is BleLink.State.Connected -> "connected"
                        is BleLink.State.Failed -> (bleState as BleLink.State.Failed).reason
                    }
                )
                if (ui.deviceId == null) {
                    Row {
                        OutlinedTextField(pairingCode, { pairingCode = it },
                            label = { Text("Pairing code") }, modifier = Modifier.weight(1f))
                        Button(onClick = {
                            model.bindDevice(pairingCode) { _, _ -> }
                        }) { Text("Bind") }
                    }
                } else {
                    Button(onClick = { model.startLink() }) { Text("Connect wearable") }
                }
            }
        }

        Card {
            Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text("Upload queue")
                Text("${ui.pendingUploads} pending · last upload " +
                    (ui.lastUploadOk?.let { if (it) "OK" else "failed" } ?: "—"))
                if (BuildConfig.DEBUG) {
                    Button(onClick = { model.injectFixtureTelemetry() }) {
                        Text("FIXTURE: inject 5 test records")
                    }
                    Button(onClick = { model.purgeBoardQueue() }) {
                        Text("ADMIN: purge wearable backup queue")
                    }
                }
            }
        }

        // v2 'Know Your Partner' quiz: the phone shows the question, the
        // wearable is the A-D pad (UL=A UR=B LL=C LR=D).
        if (ui.quiz != null && (ui.quiz.active || ui.quiz.completed)) {
            QuizCard(model, ui.quiz)
        }

        DiscoveryCard(model, ui)

        // v2: pet mirror card (species/name live on the wearable; level/XP server-owned).
        ui.pet?.let { pet ->
            Card {
                Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text("Pet")
                    val species = pet.optString("species", "")
                    val stage = pet.optInt("evolution_stage", 1)
                    val stageLabel = when (stage) { 2 -> "teen"; 3 -> "adult"; else -> "baby" }
                    if (species.isBlank()) {
                        Text("No pet yet — bond with one on your TinyScreen+")
                    } else {
                        Text("${pet.optString("name", species)} · ${species.replaceFirstChar { it.uppercase() }} ($stageLabel)")
                        Text(
                            "Level ${pet.optInt("level", 1)} · ${pet.optInt("lifetime_xp", 0)} XP · " +
                                "streak ${pet.optInt("care_streak", 0)} · " +
                                if (pet.optBoolean("cared_today", false)) "cared today ✓" else "not cared today"
                        )
                    }
                }
            }
        }

        Card {
            Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text("Quests")
                Row {
                    Switch(demoMode, { demoMode = it })
                    Text("Demo mode (short durations)")
                }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(onClick = { model.questAction("together", demoMode) { _, _ -> } }) {
                        Text("Together")
                    }
                    Button(onClick = { model.questAction("explore", demoMode) { _, _ -> } }) {
                        Text("Explore")
                    }
                    Button(onClick = { model.questAction("quiz", demoMode) { _, _ -> } }) {
                        Text("Quiz")
                    }
                }
                // v2: raid needs a landmark; the buttons WRAP (a single Row
                // pushed them off-screen — six buttons never fit a phone
                // width, so the Raid buttons were invisible, 14 Nov).
                @OptIn(ExperimentalLayoutApi::class)
                FlowRow(
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalArrangement = Arrangement.spacedBy(6.dp),
                ) {
                    val landmarkOptions = ui.landmarks
                    if (landmarkOptions.isEmpty()) {
                        Text("Raid: loading landmarks...", style = MaterialTheme.typography.bodySmall)
                    }
                    landmarkOptions.forEach { lm ->
                        Button(onClick = { model.questAction("raid", demoMode, lm.id) { _, _ -> } }) {
                            Text("Raid: ${lm.name}")
                        }
                    }
                }
            }
        }
    }
}

/** v2 quiz card: Kahoot-style colored options for the current question.
 *  Answers are pressed on the wearable; this screen mirrors progress. */
@Composable
fun QuizCard(model: AppModel, quiz: AppModel.QuizView) {
    val optionColors = listOf(
        MaterialTheme.colorScheme.error,      // A red
        MaterialTheme.colorScheme.primary,    // B blue
        MaterialTheme.colorScheme.tertiary,   // C yellow-ish
        MaterialTheme.colorScheme.secondary,  // D green-ish
    )
    Card {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text("Know Your Partner", style = MaterialTheme.typography.titleMedium)
            if (quiz.completed) {
                Text("Quiz complete! +100 points & XP each",
                    color = MaterialTheme.colorScheme.primary)
                Text("You ${quiz.myAnswered}/${quiz.myTotal} answered · partner ${quiz.partnerAnswered}/${quiz.partnerTotal}")
            } else {
                Text("Q${quiz.index + 1}/${quiz.total}: ${quiz.question ?: "..."}")
                quiz.options.forEachIndexed { i, opt ->
                    Text(
                        "${'A' + i}: $opt",
                        color = optionColors.getOrElse(i) { MaterialTheme.colorScheme.onSurface },
                    )
                }
                Text(
                    "Answer with the wearable: UL=A  UR=B  LL=C  LR=D",
                    style = MaterialTheme.typography.bodySmall,
                )
                Text(
                    "You ${quiz.myAnswered}/${quiz.myTotal} · partner ${quiz.partnerAnswered}/${quiz.partnerTotal}",
                    style = MaterialTheme.typography.bodySmall,
                )
                quiz.lastError?.let {
                    Text(it, color = MaterialTheme.colorScheme.error,
                        style = MaterialTheme.typography.bodySmall)
                }
            }
        }
    }
}

private val INTEREST_CHOICES = listOf(
    "gaming", "music", "fitness", "food", "movies", "travel", "reading", "outdoors")

/** Nearby discovery: profile editor, opt-ins, live results, invitations,
 * partnership end (docs/DISCOVERY_PLAN.md). */
@Composable
fun DiscoveryCard(model: AppModel, ui: AppModel.UiState) {
    val profile = ui.profile
    var editing by remember { mutableStateOf(false) }
    var name by remember { mutableStateOf("") }
    var age by remember { mutableStateOf("") }
    var minAge by remember { mutableStateOf("18") }
    var maxAge by remember { mutableStateOf("99") }
    var radius by remember { mutableStateOf("500") }
    var interests by remember { mutableStateOf(setOf<String>()) }
    var bleOn by remember { mutableStateOf(false) }
    var gpsOn by remember { mutableStateOf(false) }
    var actionError by remember { mutableStateOf<String?>(null) }

    // Seed editor fields from the server snapshot once.
    LaunchedEffect(profile) {
        profile?.let {
            name = it.optString("display_name", "")
            age = it.optInt("age").takeIf { v -> v > 0 }?.toString() ?: ""
            minAge = it.optInt("pref_min_age", 18).toString()
            maxAge = it.optInt("pref_max_age", 99).toString()
            radius = it.optInt("radius_m", 500).toString()
            interests = it.optJSONArray("interests")?.let { arr ->
                (0 until arr.length()).map { k -> arr.getString(k) }.toSet()
            } ?: emptySet()
            bleOn = it.optBoolean("bluetooth_enabled", false)
            gpsOn = it.optBoolean("gps_enabled", false)
        }
    }

    Card {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text("Discovery")

            if (ui.partnered) {
                Text("Partnered with ${ui.partnerName ?: "?"}",
                    style = MaterialTheme.typography.titleMedium)
                Button(onClick = {
                    model.endPartnership { ok, err -> if (!ok) actionError = err }
                }) { Text("End partnership") }
            } else {
                Row {
                    Switch(bleOn, { v ->
                        bleOn = v
                        model.setOptIns(v, gpsOn) { ok, err -> if (!ok) actionError = err }
                    })
                    Text("Bluetooth")
                    Spacer(Modifier.width(8.dp))
                    Switch(gpsOn, { v ->
                        gpsOn = v
                        model.setOptIns(bleOn, v) { ok, err -> if (!ok) actionError = err }
                    })
                    Text("GPS")
                }
                if (bleOn || gpsOn) {
                    Text(
                        if (ui.boardModeAcked) "wearable discovery active"
                        else "wearable sync pending (will sync on next link)",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.tertiary)
                }

                if (editing) {
                    OutlinedTextField(name, { name = it }, label = { Text("Display name") },
                        modifier = Modifier.fillMaxWidth())
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        OutlinedTextField(age, { age = it }, label = { Text("Age") },
                            modifier = Modifier.weight(1f))
                        OutlinedTextField(minAge, { minAge = it }, label = { Text("Min age") },
                            modifier = Modifier.weight(1f))
                        OutlinedTextField(maxAge, { maxAge = it }, label = { Text("Max age") },
                            modifier = Modifier.weight(1f))
                    }
                    OutlinedTextField(radius, { radius = it },
                        label = { Text("Radius m (100-5000)") }, modifier = Modifier.fillMaxWidth())
                    Text("Interests (at least one)")
                    INTEREST_CHOICES.forEach { tag ->
                        Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                            androidx.compose.material3.Checkbox(
                                interests.contains(tag),
                                { on ->
                                    interests = if (on) interests + tag else interests - tag
                                })
                            Text(tag)
                        }
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Button(onClick = {
                            val body = org.json.JSONObject()
                                .put("display_name", name.trim())
                                .put("age", age.toIntOrNull() ?: 0)
                                .put("pref_min_age", minAge.toIntOrNull() ?: 0)
                                .put("pref_max_age", maxAge.toIntOrNull() ?: 0)
                                .put("radius_m", radius.toIntOrNull() ?: 0)
                                .put("interests", org.json.JSONArray(interests.sorted()))
                            model.saveProfile(body) { ok, err ->
                                if (ok) editing = false else actionError = err
                            }
                        }) { Text("Save") }
                        Button(onClick = { editing = false }) { Text("Cancel") }
                    }
                } else {
                    val complete = profile?.optBoolean("complete") == true
                    Text(if (complete)
                        "Profile: ${profile?.optString("display_name")}, age ${profile?.optInt("age")}, " +
                            "radius ${profile?.optInt("radius_m")} m"
                    else "Profile incomplete — complete it to appear in discovery")
                    Button(onClick = { editing = true }) { Text("Edit profile") }
                }

                // Incoming invitations.
                val incoming = ui.invitations?.optJSONArray("incoming")
                for (i in 0 until (incoming?.length() ?: 0)) {
                    val inv = incoming!!.getJSONObject(i)
                    Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text("${inv.optString("from_name")} invited you")
                        Button(onClick = {
                            model.respondInvitation(UUID.fromString(inv.getString("id")), true) { _, _ -> }
                        }) { Text("Accept") }
                        Button(onClick = {
                            model.respondInvitation(UUID.fromString(inv.getString("id")), false) { _, _ -> }
                        }) { Text("Decline") }
                    }
                }

                // Live discovery results (5 s refresh; honest stale labels).
                ui.discoveryError?.let {
                    Text("Discovery unavailable: $it", color = MaterialTheme.colorScheme.error)
                }
                val disco = ui.discovery
                if (disco != null) {
                    disco.optJSONArray("notices")?.let { notices ->
                        for (i in 0 until notices.length()) {
                            val n = notices.getJSONObject(i)
                            Text(n.optString("message") +
                                (n.optInt("age_seconds", -1).takeIf { it >= 0 }
                                    ?.let { " (${it}s ago)" } ?: ""),
                                color = MaterialTheme.colorScheme.tertiary,
                                style = MaterialTheme.typography.bodySmall)
                        }
                    }
                    val results = disco.optJSONArray("results")
                    if (results == null || results.length() == 0) {
                        Text("No matches nearby")
                    }
                    for (i in 0 until (results?.length() ?: 0)) {
                        val r = results!!.getJSONObject(i)
                        Column(Modifier.padding(top = 6.dp)) {
                            Text("${r.optString("display_name")} · " +
                                r.optJSONArray("shared_interests").join(","),
                                style = MaterialTheme.typography.titleSmall)
                            val bits = ArrayList<String>()
                            val bt = r.optJSONObject("bluetooth")
                            if (bt != null) bits.add(bt.optString("label"))
                            r.optJSONObject("gps")?.let { g ->
                                bits.add("~${g.optInt("distance_m")} m")
                                g.optJSONArray("labels")?.let { l ->
                                    for (k in 0 until l.length()) bits.add(l.getString(k))
                                }
                            }
                            Text(bits.joinToString(" · "),
                                style = MaterialTheme.typography.bodySmall)
                            Button(onClick = {
                                model.invite(UUID.fromString(r.getString("user_id"))) { _, _ -> }
                            }) { Text("Invite") }
                        }
                    }
                }
            }
            actionError?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        }
    }
}
