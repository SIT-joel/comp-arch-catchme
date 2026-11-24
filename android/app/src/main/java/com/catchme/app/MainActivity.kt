package com.catchme.app

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.os.SystemClock
import java.util.Locale
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
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.ui.text.input.KeyboardType
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
import kotlinx.coroutines.delay
import java.util.UUID

/** Foreground-only companion app. */
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
        val extraBase = intent?.getStringExtra("api_base")?.trim()?.takeIf { it.isNotEmpty() }
        val extraId = intent?.getStringExtra("cf_id")?.trim()?.takeIf { it.isNotEmpty() }
        val extraSecret = intent?.getStringExtra("cf_secret")?.trim()?.takeIf { it.isNotEmpty() }
        if (extraBase != null || extraId != null) {
            apiPrefs.edit()
                .putString("api_base", extraBase ?: apiPrefs.getString("api_base", null))
                .putString("cf_id", extraId ?: apiPrefs.getString("cf_id", null))
                .putString("cf_secret", extraSecret ?: apiPrefs.getString("cf_secret", null))
                .apply()
        }
        val savedBase = apiPrefs.getString("api_base", null)?.trim()?.takeIf { it.isNotEmpty() }
        val apiBase = extraBase
            ?: if (savedBase != null && (savedBase.startsWith("https://") || !BuildConfig.API_BASE.startsWith("https://"))) {
                savedBase
            } else {
                BuildConfig.API_BASE
            }
        model = AppModel(this, apiBase)
        model.api.accessId = extraId
            ?: apiPrefs.getString("cf_id", null)?.trim()?.takeIf { it.isNotEmpty() }
            ?: BuildConfig.CF_ACCESS_ID
        model.api.accessSecret = extraSecret
            ?: apiPrefs.getString("cf_secret", null)?.trim()?.takeIf { it.isNotEmpty() }
            ?: BuildConfig.CF_ACCESS_SECRET
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
        if (model.ui.value.signedIn) {
            model.refreshDiscoveryState()
            model.refreshDeviceState()
        }
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
        Spacer(Modifier.height(12.dp))
        Text("Server: ${model.api.baseUrl}", style = MaterialTheme.typography.bodySmall)
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
        Text("Server: ${model.api.baseUrl}", style = MaterialTheme.typography.bodySmall)
        ui.proximityAlert?.let { alertMsg ->
            Card(
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.errorContainer),
            ) {
                Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text(
                        "Bluetooth Proximity Alert",
                        style = MaterialTheme.typography.titleSmall,
                        color = MaterialTheme.colorScheme.onErrorContainer,
                    )
                    Text(
                        alertMsg,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onErrorContainer,
                    )
                }
            }
        }
        if (demoMode) Text("DEMO MODE", color = MaterialTheme.colorScheme.tertiary)

        Card {
            Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text("Wearable link")
                Text(
                    when (bleState) {
                        BleLink.State.Idle -> if (ui.bleLinkHealthy) "connected (syncing…)" else "idle"
                        BleLink.State.Scanning -> if (ui.bleLinkHealthy) "connected (syncing…)" else "scanning…"
                        BleLink.State.Connecting -> if (ui.bleLinkHealthy) "connected (syncing…)" else "reconnecting…"
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

        // Achievement unlock banner (15 Nov): the newest unlock shows for a
        // few seconds before the card takes over — the friend-journey reward.
        ui.newAchievement?.let { name ->
            val age = System.currentTimeMillis() - ui.newAchievementAt
            if (age < 8000) {
                Card {
                    Column(Modifier.padding(12.dp)) {
                        Text("Achievement unlocked!", style = MaterialTheme.typography.titleMedium)
                        Text(name, color = MaterialTheme.colorScheme.primary)
                    }
                }
            }
        }

        if (ui.achievements.isNotEmpty()) {
            AchievementsCard(ui.achievements)
        }

        DiscoveryCard(model, ui)

        // v2: pet mirror card (species/name live on the wearable; level/XP server-owned).
        ui.pet?.let { pet ->
            Card {
                Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text("Pet")
                    val species = if (pet.isNull("species")) "" else pet.optString("species", "")
                    val rawPetName = if (pet.isNull("name")) "" else pet.optString("name", "")
                    val petName = if (rawPetName.isBlank() || rawPetName.equals("null", ignoreCase = true)) {
                        species.replaceFirstChar { it.uppercase() }
                    } else {
                        rawPetName
                    }
                    val stage = pet.optInt("evolution_stage", 1)
                    val stageLabel = when (stage) { 2 -> "teen"; 3 -> "adult"; else -> "baby" }
                    if (species.isBlank()) {
                        Text("No pet yet — bond with one on your TinyScreen+")
                    } else {
                        Text("$petName · ${species.replaceFirstChar { it.uppercase() }} ($stageLabel)")
                        Text(
                            "Level ${pet.optInt("level", 1)} · ${pet.optInt("lifetime_xp", 0)} XP · " +
                                "streak ${pet.optInt("care_streak", 0)} · " +
                                if (pet.optBoolean("cared_today", false)) "cared today ✓" else "not cared today"
                        )
                    }
                }
            }
        }

        // v2 'Know Your Partner' quiz: placed adjacent to Quests so tapping Quiz
        // keeps the live question + A-D options in view without scrolling up.
        if (ui.quiz != null && (ui.quiz.active || ui.quiz.completed || ui.quiz.myAnswered > 0)) {
            QuizCard(model, ui.quiz)
        }

        var questError by remember { mutableStateOf<String?>(null) }
        var questBusy by remember { mutableStateOf(false) }
        Card {
            Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text("Quests")
                val fix = ui.gpsFix
                val fixAgeSec = fix?.let { ((System.currentTimeMillis() - it.fixTimeMs).coerceAtLeast(0L) / 1000L) }
                Text(
                    if (fix != null) {
                        "Phone GPS: ${String.format(Locale.US, "%.5f, %.5f", fix.latitude, fix.longitude)} (${fixAgeSec}s ago)"
                    } else {
                        "Phone GPS: acquiring fix…"
                    },
                    style = MaterialTheme.typography.bodySmall,
                )
                ui.activeSession?.let { active ->
                    val qTitle = when (active.questId) {
                        "together" -> "Together Time"
                        "explore" -> "Outdoor Visit"
                        "quiz" -> "Know Your Partner"
                        else -> active.questId
                    }
                    Text(
                        "$qTitle · ${active.state}${if (active.demo) " (demo)" else ""}",
                        style = MaterialTheme.typography.titleSmall,
                    )
                    if (active.questId == "explore") {
                        Text(
                            if (fix != null) {
                                "Your GPS: ${String.format(Locale.US, "%.5f, %.5f", fix.latitude, fix.longitude)} (age ${fixAgeSec}s)"
                            } else {
                                "Your GPS: no fix yet (indoors)"
                            },
                            style = MaterialTheme.typography.bodySmall,
                        )
                        if (active.demo) {
                            Text(
                                "Demo indoor view: live GPS coordinates shown on phone & TinyScreen+",
                                style = MaterialTheme.typography.bodySmall,
                            )
                        }
                    }
                    active.interactionSummary?.let { summary ->
                        Text(summary, style = MaterialTheme.typography.bodySmall)
                    }
                    if (active.questId == "together" && active.state == "active" &&
                        (active.interactionPhase == "start_pin" || active.interactionPhase == "end_pin")
                    ) {
                        val stageKey = active.interactionStage
                            ?: if (active.interactionPhase == "start_pin") "start" else "end"
                        val stageTitle = if (active.interactionPhase == "start_pin") "Start PIN" else "End PIN"
                        var pinInput by remember(active.sessionId, active.interactionPhase) { mutableStateOf("") }
                        Text(
                            "Your $stageTitle: ${active.ownPin ?: "----"}",
                            style = MaterialTheme.typography.titleSmall,
                        )
                        ui.pinVerifyStatus?.let { status ->
                            Text(
                                status,
                                color = if (ui.pinVerifyIsError) MaterialTheme.colorScheme.error
                                        else MaterialTheme.colorScheme.primary,
                                style = MaterialTheme.typography.bodySmall,
                            )
                        }
                        if (!active.myPinConfirmed) {
                            Text(
                                "Enter partner's 4-digit PIN on TinyScreen+ or verify here",
                                style = MaterialTheme.typography.bodySmall,
                            )
                            OutlinedTextField(
                                value = pinInput,
                                onValueChange = { raw ->
                                    if (raw.length <= 4 && raw.all { it.isDigit() }) {
                                        pinInput = raw
                                    }
                                },
                                label = { Text("Partner's 4-digit PIN") },
                                singleLine = true,
                                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                                modifier = Modifier.fillMaxWidth(),
                            )
                            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                Button(
                                    enabled = pinInput.length == 4 && !ui.pinVerifyBusy && !questBusy,
                                    onClick = {
                                        questError = null
                                        model.submitPinFromApp(active.sessionId, stageKey, pinInput) { ok, _ ->
                                            if (ok) pinInput = ""
                                        }
                                    },
                                ) { Text("Verify PIN") }
                                Button(
                                    enabled = !ui.pinVerifyBusy && !questBusy,
                                    onClick = {
                                        questError = null
                                        model.refreshPinFromApp(active.sessionId, stageKey) { _, _ -> }
                                    },
                                ) { Text("Refresh my PIN") }
                            }
                        }
                    }
                    ui.proximityAlert?.let { alertMsg ->
                        Text(
                            "⚠ $alertMsg",
                            color = MaterialTheme.colorScheme.error,
                            style = MaterialTheme.typography.bodySmall,
                        )
                    }
                    if (active.questId == "quiz") {
                        val quizState = ui.quiz
                        if (quizState != null) {
                            Text(
                                "Answered ${quizState.myAnswered}/${quizState.myTotal} questions · ${quizState.myCorrect} right",
                                style = MaterialTheme.typography.bodySmall,
                            )
                        }
                    } else if (active.targetMs != null && active.targetMs > 0) {
                        var displayTickMs by remember(active.sessionId) { mutableStateOf(SystemClock.elapsedRealtime()) }
                        LaunchedEffect(active.sessionId, active.timerRunning, active.progressMs, active.progressAnchorMs) {
                            displayTickMs = SystemClock.elapsedRealtime()
                            while (active.timerRunning) {
                                delay(500L)
                                displayTickMs = SystemClock.elapsedRealtime()
                            }
                        }
                        val shownProgressMs = model.displayProgressMs(active, displayTickMs)
                        val frac = (shownProgressMs.toFloat() / active.targetMs.toFloat()).coerceIn(0f, 1f)
                        val remSec = ((active.targetMs - shownProgressMs).coerceAtLeast(0L) + 999L) / 1000L
                        LinearProgressIndicator(progress = { frac }, modifier = Modifier.fillMaxWidth())
                        Text(
                            "${remSec}s left (${shownProgressMs / 1000}s / ${active.targetMs / 1000}s)",
                            style = MaterialTheme.typography.bodySmall,
                        )
                    }
                    if (active.state == "pending" && !active.needsMyAccept) {
                        Text("Waiting for partner to accept…", style = MaterialTheme.typography.bodySmall)
                    }
                    var showCancelConfirm by remember(active.sessionId) { mutableStateOf(false) }
                    if (showCancelConfirm) {
                        AlertDialog(
                            onDismissRequest = { showCancelConfirm = false },
                            title = { Text("Cancel active quest?") },
                            text = { Text("Are you sure you want to leave this active quest? Progress so far may be lost.") },
                            confirmButton = {
                                TextButton(
                                    enabled = !questBusy,
                                    onClick = {
                                        showCancelConfirm = false
                                        questBusy = true
                                        questError = null
                                        model.cancelSession(active.sessionId) { ok, err ->
                                            questBusy = false
                                            if (!ok) questError = err
                                        }
                                    },
                                ) { Text("Yes, cancel") }
                            },
                            dismissButton = {
                                TextButton(onClick = { showCancelConfirm = false }) { Text("Keep going") }
                            },
                        )
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        if (active.state == "pending" && active.needsMyAccept) {
                            Button(
                                enabled = !questBusy,
                                onClick = {
                                    questBusy = true
                                    questError = null
                                    model.acceptSession(active.sessionId) { ok, err ->
                                        questBusy = false
                                        if (!ok) questError = err
                                    }
                                },
                            ) { Text("Accept") }
                        }
                        Button(
                            enabled = !questBusy,
                            onClick = {
                                if (active.state == "active") {
                                    showCancelConfirm = true
                                } else {
                                    questBusy = true
                                    questError = null
                                    model.cancelSession(active.sessionId) { ok, err ->
                                        questBusy = false
                                        if (!ok) questError = err
                                    }
                                }
                            },
                        ) { Text("Cancel") }
                    }
                }
                Row {
                    Switch(demoMode, { demoMode = it })
                    Text("Demo mode (short durations)")
                }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(
                        enabled = ui.activeSession == null && !questBusy,
                        onClick = {
                            questBusy = true
                            questError = null
                            model.questAction("together", demoMode) { ok, err ->
                                questBusy = false
                                if (!ok) questError = err
                            }
                        },
                    ) {
                        Text("Together")
                    }
                    Button(
                        enabled = ui.activeSession == null && !questBusy,
                        onClick = {
                            questBusy = true
                            questError = null
                            model.questAction("explore", demoMode) { ok, err ->
                                questBusy = false
                                if (!ok) questError = err
                            }
                        },
                    ) {
                        Text("Explore")
                    }
                    Button(
                        enabled = ui.activeSession == null && !questBusy,
                        onClick = {
                            questBusy = true
                            questError = null
                            model.questAction("quiz", demoMode) { ok, err ->
                                questBusy = false
                                if (!ok) questError = err
                            }
                        },
                    ) {
                        Text("Quiz")
                    }
                }
                if (questBusy) {
                    Text("Sending quest request…", style = MaterialTheme.typography.bodySmall)
                } else if (ui.activeSession != null) {
                    Text("Cancel or finish current quest before starting a new one.",
                        style = MaterialTheme.typography.bodySmall)
                }
                questError?.let {
                    Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
                }
            }
        }
    }
}

/** Achievements card (15 Nov): the friend-journey milestones. Unlocked rows
 *  show their name in the primary color; locked rows render greyed with the
 *  description as the "how to earn it" hint. */
@Composable
fun AchievementsCard(items: List<AppModel.AccView>) {
    Card {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text("Achievements",
                 style = MaterialTheme.typography.titleMedium)
            val unlockedCount = items.count { it.unlocked }
            Text("$unlockedCount of ${items.size} unlocked",
                 style = MaterialTheme.typography.bodySmall)
            items.forEach { item ->
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                    Column {
                        Text(
                            item.name,
                            color = if (item.unlocked) MaterialTheme.colorScheme.primary
                                    else MaterialTheme.colorScheme.onSurface.copy(alpha = 0.45f),
                        )
                        Text(item.description,
                             style = MaterialTheme.typography.bodySmall)
                    }
                    Text(if (item.unlocked) "✓" else "",
                         color = MaterialTheme.colorScheme.primary)
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
                Text(
                    "Your score: ${quiz.myCorrect}/${quiz.myTotal} right · Partner: ${quiz.partnerCorrect}/${quiz.partnerTotal} right",
                    style = MaterialTheme.typography.titleSmall,
                )
                quiz.results.forEach { q ->
                    val chosenStr = q.choice?.let { "${'A' + it}: ${q.options.getOrNull(it) ?: ""}" } ?: "Unanswered"
                    val rightStr = q.rightIndex?.let { "${'A' + it}: ${q.options.getOrNull(it) ?: ""}" }
                    if (q.isCorrect == true) {
                        Text(
                            "Q${q.index + 1}: ✓ $chosenStr (Right!)",
                            color = MaterialTheme.colorScheme.secondary,
                            style = MaterialTheme.typography.bodySmall,
                        )
                    } else {
                        Text(
                            "Q${q.index + 1}: ✗ You picked $chosenStr" +
                                if (rightStr != null) " · Right: $rightStr" else "",
                            color = MaterialTheme.colorScheme.error,
                            style = MaterialTheme.typography.bodySmall,
                        )
                    }
                }
            } else if (quiz.index < 0) {
                Text(
                    "All ${quiz.myTotal} answered (${quiz.myCorrect} right) · waiting for partner (${quiz.partnerAnswered}/${quiz.partnerTotal})…",
                    style = MaterialTheme.typography.bodySmall,
                )
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
                    "You ${quiz.myAnswered}/${quiz.myTotal} (${quiz.myCorrect} right) · partner ${quiz.partnerAnswered}/${quiz.partnerTotal}",
                    style = MaterialTheme.typography.bodySmall,
                )
                quiz.results.filter { it.answered }.forEach { q ->
                    val chosenStr = q.choice?.let { "${'A' + it}: ${q.options.getOrNull(it) ?: ""}" } ?: ""
                    val rightStr = q.rightIndex?.let { "${'A' + it}: ${q.options.getOrNull(it) ?: ""}" }
                    Text(
                        if (q.isCorrect == true) "Q${q.index + 1}: ✓ $chosenStr"
                        else "Q${q.index + 1}: ✗ $chosenStr" + if (rightStr != null) " (Right: $rightStr)" else "",
                        color = if (q.isCorrect == true) MaterialTheme.colorScheme.secondary
                                else MaterialTheme.colorScheme.error,
                        style = MaterialTheme.typography.bodySmall,
                    )
                }
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
 * partnership end. */
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
