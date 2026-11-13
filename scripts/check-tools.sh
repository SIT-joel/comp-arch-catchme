#!/usr/bin/env bash
# Read-only prerequisite probe; no installs, network calls, or configuration writes.
set -u

missing_required=0

check_tool() {
    local label="$1"
    local required="$2"
    shift 2
    local executable="$1"
    local output
    local first_line

    if ! command -v "$executable" >/dev/null 2>&1; then
        if [[ "$required" == "yes" ]]; then
            printf '[MISSING] %s: not on PATH\n' "$label"
            missing_required=$((missing_required + 1))
        else
            printf '[OPTIONAL] %s: not on PATH\n' "$label"
        fi
        return
    fi

    if output=$("$@" 2>&1); then
        first_line="${output//$'\n'/ | }"
        printf '[OK] %s: %s\n' "$label" "$first_line"
    else
        first_line="${output//$'\n'/ | }"
        printf '[CHECK] %s: version probe failed; %s\n' "$label" "$first_line"
        if [[ "$required" == "yes" ]]; then
            missing_required=$((missing_required + 1))
        fi
    fi
}

printf 'Catch Me development tool check (read-only)\n'
check_tool 'Git' yes git --version
check_tool 'Node.js' yes node --version
check_tool 'npm' yes npm --version
check_tool 'Python 3' yes python3 --version
check_tool 'Java/JDK (Android Studio may bundle it)' yes java -version
check_tool 'ADB (may need SDK platform-tools on PATH)' yes adb version
check_tool 'Docker client' yes docker --version
check_tool 'Docker Compose v2' yes docker compose version
check_tool 'Arduino CLI (optional if using Arduino IDE)' no arduino-cli version

printf '\nManual checks: Android Studio/SDK, TinyScreen+ board support, firmware libraries, two phones/devices, GLM access.\n'
printf 'Docker version checks do not verify a running daemon. Version probes do not establish compatibility or hardware support.\n'
printf 'Required command-line probes needing attention: %s\n' "$missing_required"
if [[ "$missing_required" -gt 0 ]]; then
    exit 1
fi
exit 0
