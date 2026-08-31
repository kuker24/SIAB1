#!/usr/bin/env python3
"""
SIAB1 APK Builder GUI
=====================
Desktop GUI untuk konfigurasi dan build APK native android-kiosk.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import subprocess
import threading
import os
import sys
from pathlib import Path
from datetime import datetime
import shutil
import secrets
import string
import time
import re
import shlex

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

DEFAULT_APP_NAME = "SIAB1"
DEFAULT_APP_SUBTITLE = "Sistem Informasi Asesmen Berintegritas"


def normalize_apk_display_name(app_name: str | None) -> str:
    """Normalize stale APK display names to the current SIAB1 branding."""
    value = (app_name or "").strip()
    if not value:
        return DEFAULT_APP_NAME
    return value

from apk_builder_core.artifacts import find_latest_artifact, sha256_file
from apk_builder_core.context import detect_project_context
from apk_builder_core.native_kiosk import (
    DEFAULT_PRODUCTION_URL,
    NATIVE_KIOSK_PACKAGE,
    apply_native_kiosk_config,
    is_placeholder_server_url,
    kiosk_release_apk_path,
    load_optional_server_url,
    load_release_signing_env,
    read_native_kiosk_config,
    signing_env_ready,
    signing_status_text,
)
from apk_builder_core.environment import (
    build_tool_env,
    ensure_gradle_memory_config,
    find_android_sdk,
    find_flutter,
    find_jdk,
    get_total_ram_mb,
    recommend_gradle_memory,
    resolve_apksigner,
    resolve_keytool,
)
from apk_builder_core.validators import (
    find_main_activity_file,
    is_valid_package_name,
    is_valid_sha256,
    load_properties_file,
    normalize_server_url,
    parse_pubspec_version,
    save_properties_file,
    validate_version_fields,
)

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    Image = None
    PIL_AVAILABLE = False


RUNTIME_TUNING_PROFILES = {
    "strict_security": {
        "reconnect_probe_interval_seconds": 5,
        "emergency_exit_min_outage_minutes": 5,
        "emergency_exit_min_failed_probes": 10,
        "risk_auto_submit_threshold": 7.0,
        "answer_journal_sync_interval_seconds": 4,
        "answer_journal_batch_size": 120,
        "timer_guard_max_drift_seconds": 8,
    },
    "balanced": {
        "reconnect_probe_interval_seconds": 6,
        "emergency_exit_min_outage_minutes": 4,
        "emergency_exit_min_failed_probes": 8,
        "risk_auto_submit_threshold": 8.0,
        "answer_journal_sync_interval_seconds": 5,
        "answer_journal_batch_size": 100,
        "timer_guard_max_drift_seconds": 10,
    },
    "ux_offline_first": {
        # Safer for real exam Wi-Fi bursts: avoid old 6s/6s rollback.
        "reconnect_probe_interval_seconds": 10,
        "emergency_exit_min_outage_minutes": 3,
        "emergency_exit_min_failed_probes": 6,
        "risk_auto_submit_threshold": 8.5,
        "answer_journal_sync_interval_seconds": 8,
        "answer_journal_batch_size": 80,
        "timer_guard_max_drift_seconds": 12,
    },
}

_UX_OFFLINE_FIRST_MINIMUMS = {
    "reconnect_probe_interval_seconds": 10,
    "answer_journal_sync_interval_seconds": 8,
}

_DART_TUNING_NAMES = {
    "reconnect_probe_interval_seconds": "reconnectProbeIntervalSeconds",
    "emergency_exit_min_outage_minutes": "emergencyExitMinOutageMinutes",
    "emergency_exit_min_failed_probes": "emergencyExitMinFailedProbes",
    "risk_auto_submit_threshold": "riskAutoSubmitThreshold",
    "answer_journal_sync_interval_seconds": "answerJournalSyncIntervalSeconds",
    "answer_journal_batch_size": "answerJournalBatchSize",
    "timer_guard_max_drift_seconds": "timerGuardMaxDriftSeconds",
}


def _resolve_runtime_tuning(
    resilience_profile: str,
    runtime_overrides: dict | None = None,
) -> tuple[str, dict]:
    profile = (resilience_profile or "ux_offline_first").strip()
    if profile not in RUNTIME_TUNING_PROFILES:
        profile = "ux_offline_first"

    tuning = dict(RUNTIME_TUNING_PROFILES[profile])
    for key, value in (runtime_overrides or {}).items():
        if key in tuning and value is not None:
            tuning[key] = value

    if profile == "ux_offline_first":
        for key, minimum in _UX_OFFLINE_FIRST_MINIMUMS.items():
            try:
                tuning[key] = max(int(tuning[key]), minimum)
            except (TypeError, ValueError):
                tuning[key] = minimum

    return profile, tuning


def _dart_bool(value: bool) -> str:
    return str(bool(value)).lower()


def render_config_dart_content(
    *,
    normalized_url: str,
    app_name: str,
    force_https: bool,
    cleartext_allowed: bool,
    build_mode: str,
    build_token: str,
    build_timestamp: int,
    security_settings: dict,
    generated_at: str,
    resilience_profile: str = "ux_offline_first",
    runtime_overrides: dict | None = None,
) -> tuple[str, str, dict]:
    """Render Flutter config.dart content without opening the GUI or building APK."""
    profile, tuning = _resolve_runtime_tuning(resilience_profile, runtime_overrides)
    normalized_app_name = normalize_apk_display_name(app_name)
    safe_app_name = normalized_app_name.replace('"', '\\"')

    content = f'''// Auto-generated configuration by APK Builder GUI
// Generated: {generated_at}
// Build Token: {build_token}

class AppConfig {{
  static const String serverUrl = "{normalized_url}";
  static const String appName = "{safe_app_name}";
  static const String appSubtitle = "{DEFAULT_APP_SUBTITLE}";
  static const bool forceHttps = {_dart_bool(force_https)};
  static const bool allowCleartextTraffic = {_dart_bool(cleartext_allowed)};
  static const String buildMode = "{build_mode}";
  static const String resilienceProfile = "{profile}";

  // Build Token for Version Control
  static const String buildToken = "{build_token}";
  static const int buildTimestamp = {int(build_timestamp)};

  // UX-first offline runtime tuning
  static const bool enableOfflineFirstRuntime = true;
  static const bool showConnectionBadge = true;
  static const bool enableAdaptiveViolationDetection = true;
  static const bool enableDiagnosticsQuickExport = true;
  static const int reconnectProbeIntervalSeconds = {int(tuning["reconnect_probe_interval_seconds"])};
  static const int emergencyExitMinOutageMinutes = {int(tuning["emergency_exit_min_outage_minutes"])};
  static const int emergencyExitMinFailedProbes = {int(tuning["emergency_exit_min_failed_probes"])};
  static const double riskAutoSubmitThreshold = {float(tuning["risk_auto_submit_threshold"])};
  static const int answerJournalSyncIntervalSeconds = {int(tuning["answer_journal_sync_interval_seconds"])};
  static const int answerJournalBatchSize = {int(tuning["answer_journal_batch_size"])};
  static const int timerGuardMaxDriftSeconds = {int(tuning["timer_guard_max_drift_seconds"])};

  // Security Settings
  static const bool enableKiosk = {_dart_bool(security_settings.get("enable_kiosk", True))};
  static const bool blockScreenshot = {_dart_bool(security_settings.get("block_screenshot", True))};
  static const bool detectRoot = {_dart_bool(security_settings.get("detect_root", True))};
  static const bool blockTaskSwitch = {_dart_bool(security_settings.get("block_task_switch", True))};
}}
'''
    return content, profile, tuning


def extract_runtime_tuning_from_config(config_text: str) -> dict:
    """Extract runtime tuning constants from generated config.dart text."""
    values = {}
    for snake_name, dart_name in _DART_TUNING_NAMES.items():
        match = re.search(
            rf"static const (?:int|double) {dart_name}\s*=\s*([0-9]+(?:\.[0-9]+)?);",
            config_text or "",
        )
        if not match:
            continue
        raw_value = match.group(1)
        values[snake_name] = float(raw_value) if "." in raw_value else int(raw_value)
    return values


def validate_generated_config_text(
    config_text: str,
    *,
    expected_profile: str = "ux_offline_first",
) -> tuple[bool, list[str]]:
    """Validate generated config text for safety-sensitive runtime tuning."""
    errors: list[str] = []
    text = config_text or ""
    if f'static const String resilienceProfile = "{expected_profile}";' not in text:
        errors.append(f"resilienceProfile harus {expected_profile}")

    tuning = extract_runtime_tuning_from_config(text)
    if expected_profile == "ux_offline_first":
        reconnect = int(tuning.get("reconnect_probe_interval_seconds", 0) or 0)
        answer_sync = int(tuning.get("answer_journal_sync_interval_seconds", 0) or 0)
        if reconnect < _UX_OFFLINE_FIRST_MINIMUMS["reconnect_probe_interval_seconds"]:
            errors.append("reconnectProbeIntervalSeconds minimal 10 untuk ux_offline_first")
        if answer_sync < _UX_OFFLINE_FIRST_MINIMUMS["answer_journal_sync_interval_seconds"]:
            errors.append("answerJournalSyncIntervalSeconds minimal 8 untuk ux_offline_first")

    return not errors, errors


class APKBuilderGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("SIAB1 - APK Builder v3.2 (Native Kiosk)")
        self.root.geometry("1024x860")
        self.root.resizable(True, True)

        context = detect_project_context(__file__)
        self.project_root = context.project_root
        self.flutter_project = context.flutter_project
        self.config_dart_path = context.config_dart_path
        self.kiosk_project = context.kiosk_project

        # Find JDK, Android SDK, and Flutter paths
        self.jdk_path = find_jdk(self.project_root)
        self.android_sdk = find_android_sdk()
        self.flutter_bin = find_flutter(self.flutter_project, self.project_root)

        # App Configuration Variables
        self.app_name_var = tk.StringVar(value=DEFAULT_APP_NAME)
        self.package_var = tk.StringVar(value=NATIVE_KIOSK_PACKAGE)
        self.version_name_var = tk.StringVar(value="2.0.2")
        self.version_code_var = tk.StringVar(value="4")
        self.icon_path_var = tk.StringVar(value="")

        # Server Configuration Variables
        self.server_url_var = tk.StringVar(value=DEFAULT_PRODUCTION_URL)
        self.use_https_var = tk.BooleanVar(value=True)

        # Security Configuration Variables
        self.enable_kiosk_var = tk.BooleanVar(value=True)
        self.block_screenshot_var = tk.BooleanVar(value=True)
        self.detect_root_var = tk.BooleanVar(value=True)
        self.block_task_switch_var = tk.BooleanVar(value=True)

        # Build Token (Version Control)
        self.build_token_var = tk.StringVar(value="")
        self.auto_token_var = tk.BooleanVar(value=True)
        self._generate_new_token()  # Generate initial token

        # App Signature (Security)
        self.app_signature_var = tk.StringVar(value="Hash belum tersedia - build release + signing dulu")
        self.last_signature_error = ""

        # Build Options
        self.clean_build_var = tk.BooleanVar(value=False)
        self.build_mode_var = tk.StringVar(value="universal_apk")
        self.resilience_profile_var = tk.StringVar(value="ux_offline_first")
        self.preflight_analyze_var = tk.BooleanVar(value=True)
        self.preflight_test_var = tk.BooleanVar(value=True)

        # Build process
        self.build_process = None
        self.last_build_token = ""  # Store last build token for display
        self._last_command_output = []

        self.setup_ui()
        self.load_current_config()

    def _uses_native_kiosk(self) -> bool:
        gradle = self.kiosk_project / "app" / "build.gradle.kts"
        return gradle.is_file()

    def _find_jdk(self):
        """Compatibility wrapper kept for internal call sites."""
        return find_jdk(self.project_root)

    def _find_android_sdk(self):
        """Compatibility wrapper kept for internal call sites."""
        return find_android_sdk()

    def _get_total_ram_mb(self):
        return get_total_ram_mb()

    def _recommend_gradle_memory(self, force_high=False):
        return recommend_gradle_memory(force_high=force_high)

    def _ensure_gradle_memory_config(self, env, force_high=False):
        ensure_gradle_memory_config(
            flutter_project=self.flutter_project,
            env=env,
            log=self.log,
            force_high=force_high,
        )

    def _command_output_contains(self, keyword):
        keyword = (keyword or "").strip().lower()
        if not keyword:
            return False
        return any(keyword in line.lower() for line in self._last_command_output)

    def setup_ui(self):
        """Setup UI components"""
        # Style configuration
        style = ttk.Style()
        style.configure("Title.TLabel", font=("Segoe UI", 11, "bold"))
        style.configure("Accent.TButton", font=("Segoe UI", 10, "bold"))

        # Header
        header = tk.Frame(self.root, bg="#4F46E5", height=70)
        header.pack(fill=tk.X)
        header.pack_propagate(False)

        title = tk.Label(
            header,
            text="APK Builder - SIAB1 Native Kiosk",
            font=("Segoe UI", 20, "bold"),
            bg="#4F46E5",
            fg="white",
        )
        title.pack(pady=18)

        # Main container with scrollbar
        main_canvas = tk.Canvas(self.root)
        scrollbar = ttk.Scrollbar(self.root, orient="vertical", command=main_canvas.yview)
        main_frame = ttk.Frame(main_canvas, padding="15")

        main_frame.bind("<Configure>", lambda e: main_canvas.configure(scrollregion=main_canvas.bbox("all")))
        main_canvas.create_window((0, 0), window=main_frame, anchor="nw", width=980)
        main_canvas.configure(yscrollcommand=scrollbar.set)

        main_canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # ========== APP CONFIGURATION ==========
        app_frame = ttk.LabelFrame(main_frame, text="Konfigurasi Aplikasi", padding="12")
        app_frame.pack(fill=tk.X, pady=(0, 10))

        # App Name
        row = ttk.Frame(app_frame)
        row.pack(fill=tk.X, pady=3)
        ttk.Label(row, text="Nama Aplikasi:", width=18).pack(side=tk.LEFT)
        ttk.Entry(row, textvariable=self.app_name_var, width=50).pack(side=tk.LEFT, padx=(5, 0))

        # Package Name
        row = ttk.Frame(app_frame)
        row.pack(fill=tk.X, pady=3)
        ttk.Label(row, text="Package Name:", width=18).pack(side=tk.LEFT)
        package_entry = ttk.Entry(row, textvariable=self.package_var, width=50)
        package_entry.pack(side=tk.LEFT, padx=(5, 0))
        if self._uses_native_kiosk():
            package_entry.state(["disabled"])

        # Version
        row = ttk.Frame(app_frame)
        row.pack(fill=tk.X, pady=3)
        ttk.Label(row, text="Version Name:", width=18).pack(side=tk.LEFT)
        ttk.Entry(row, textvariable=self.version_name_var, width=15).pack(side=tk.LEFT, padx=(5, 0))
        ttk.Label(row, text="  Version Code:").pack(side=tk.LEFT)
        ttk.Entry(row, textvariable=self.version_code_var, width=8).pack(side=tk.LEFT, padx=(5, 0))

        # Icon
        row = ttk.Frame(app_frame)
        row.pack(fill=tk.X, pady=3)
        ttk.Label(row, text="App Icon (PNG/JPG):", width=18).pack(side=tk.LEFT)
        ttk.Entry(row, textvariable=self.icon_path_var, width=40).pack(side=tk.LEFT, padx=(5, 0))
        ttk.Button(row, text="Browse", command=self.browse_icon).pack(side=tk.LEFT, padx=(5, 0))

        # ========== SERVER CONFIGURATION ==========
        server_frame = ttk.LabelFrame(main_frame, text="Konfigurasi Server", padding="12")
        server_frame.pack(fill=tk.X, pady=(0, 10))

        # Server URL
        row = ttk.Frame(server_frame)
        row.pack(fill=tk.X, pady=3)
        ttk.Label(row, text="Server URL:", width=18).pack(side=tk.LEFT)
        self.url_entry = ttk.Entry(row, textvariable=self.server_url_var, width=50)
        self.url_entry.pack(side=tk.LEFT, padx=(5, 0))

        # URL Helper
        helper_frame = ttk.Frame(server_frame)
        helper_frame.pack(fill=tk.X, pady=3)
        ttk.Label(helper_frame, text="", width=18).pack(side=tk.LEFT)
        ttk.Label(
            helper_frame,
            text=f"Contoh: {DEFAULT_PRODUCTION_URL}",
            foreground="gray",
        ).pack(side=tk.LEFT, padx=(5, 0))

        note_frame = ttk.Frame(server_frame)
        note_frame.pack(fill=tk.X, pady=(6, 0))
        ttk.Label(note_frame, text="", width=18).pack(side=tk.LEFT)
        ttk.Label(
            note_frame,
            text=(
                "APK otomatis membuka /student/ dengan URL bersih. "
                "Token login disuntik ke WebView secara lokal dan build baru "
                "punya retry otomatis untuk gangguan seperti ERR_CONNECTION_RESET."
            ),
            foreground="#2563eb",
            wraplength=760,
            justify=tk.LEFT,
        ).pack(side=tk.LEFT, padx=(5, 0))

        # HTTPS checkbox
        row = ttk.Frame(server_frame)
        row.pack(fill=tk.X, pady=3)
        ttk.Label(row, text="", width=18).pack(side=tk.LEFT)
        ttk.Checkbutton(row, text="Paksa gunakan HTTPS (wajib untuk production)",
                       variable=self.use_https_var, command=self._update_https).pack(side=tk.LEFT)

        # ========== SECURITY CONFIGURATION ==========
        security_frame = ttk.LabelFrame(main_frame, text="Konfigurasi Keamanan", padding="12")
        security_frame.pack(fill=tk.X, pady=(0, 10))

        if self._uses_native_kiosk():
            ttk.Label(
                security_frame,
                text="Proteksi kiosk native selalu aktif: lock task, screenshot, root, dan task switch.",
                foreground="gray",
                wraplength=880,
            ).pack(anchor=tk.W)
        else:
            row = ttk.Frame(security_frame)
            row.pack(fill=tk.X, pady=3)
            ttk.Checkbutton(row, text="Enable Kiosk Mode (Lock Screen)",
                           variable=self.enable_kiosk_var).pack(side=tk.LEFT, padx=(0, 20))
            ttk.Checkbutton(row, text="Block Screenshot",
                           variable=self.block_screenshot_var).pack(side=tk.LEFT)
            row = ttk.Frame(security_frame)
            row.pack(fill=tk.X, pady=3)
            ttk.Checkbutton(row, text="Detect Root/Jailbreak",
                           variable=self.detect_root_var).pack(side=tk.LEFT, padx=(0, 20))
            ttk.Checkbutton(row, text="Block Task Switching (Alt+Tab)",
                           variable=self.block_task_switch_var).pack(side=tk.LEFT)

        # ========== BUILD TOKEN (VERSION CONTROL) ==========
        token_frame = ttk.LabelFrame(main_frame, text="Build Token (Version Control)", padding="12")
        token_frame.pack(fill=tk.X, pady=(0, 10))

        # Token info
        info_label = ttk.Label(token_frame,
                              text="Token unik untuk setiap build. Copy token ini ke Admin Panel untuk invalidate versi lama.",
                              foreground="gray", wraplength=600)
        info_label.pack(anchor=tk.W, pady=(0, 8))

        # Auto generate checkbox
        ttk.Checkbutton(token_frame, text="Auto-generate token baru setiap build",
                       variable=self.auto_token_var).pack(anchor=tk.W)

        # Token display row
        token_row = ttk.Frame(token_frame)
        token_row.pack(fill=tk.X, pady=(8, 0))
        ttk.Label(token_row, text="Current Token:", width=14).pack(side=tk.LEFT)

        self.token_entry = ttk.Entry(token_row, textvariable=self.build_token_var, width=35, font=("Consolas", 10))
        self.token_entry.pack(side=tk.LEFT, padx=(5, 0))

        ttk.Button(token_row, text="Generate", command=self._generate_new_token, width=10).pack(side=tk.LEFT, padx=(5, 0))
        ttk.Button(token_row, text="Copy", command=self._copy_token, width=8).pack(side=tk.LEFT, padx=(5, 0))

        # ========== APP SECURITY SIGNATURE (NEW) ==========
        sig_frame = ttk.LabelFrame(main_frame, text="App Security Signature (Hash)", padding="12")
        sig_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(sig_frame, text="SHA-256 Hash unik dari Keystore. WAJIB didaftarkan di Admin Panel → Pengaturan → APK Signature Hash!",
                 foreground="red", wraplength=600).pack(anchor=tk.W)

        sig_row = ttk.Frame(sig_frame)
        sig_row.pack(fill=tk.X, pady=5)

        ttk.Entry(sig_row, textvariable=self.app_signature_var, width=50, font=("Consolas", 9), state="readonly").pack(side=tk.LEFT)
        ttk.Button(sig_row, text="Copy Hash", command=self._copy_signature).pack(side=tk.LEFT, padx=5)

        # ========== BUILD OPTIONS ==========
        options_frame = ttk.LabelFrame(main_frame, text="Build Options", padding="12")
        options_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Checkbutton(options_frame, text="Clean build (hapus cache sebelum build - lebih lama tapi lebih bersih)",
                       variable=self.clean_build_var).pack(anchor=tk.W)
        if self._uses_native_kiosk():
            ttk.Checkbutton(
                options_frame,
                text="Pre-build check: tes kontrak native kiosk",
                variable=self.preflight_test_var,
            ).pack(anchor=tk.W, pady=(4, 0))
            ttk.Label(
                options_frame,
                text="Build Artifact = assembleRelease android-kiosk. Sideload saja, bukan Play Store.",
                foreground="gray",
                wraplength=880,
            ).pack(anchor=tk.W, pady=(6, 0))
        else:
            ttk.Checkbutton(
                options_frame,
                text="Pre-build check: flutter analyze (errors only, tidak fail karena lint info/warning)",
                variable=self.preflight_analyze_var,
            ).pack(anchor=tk.W, pady=(4, 0))
            ttk.Checkbutton(
                options_frame,
                text="Pre-build check: flutter test (smoke test sebelum artifact build)",
                variable=self.preflight_test_var,
            ).pack(anchor=tk.W, pady=(2, 0))
            mode_row = ttk.Frame(options_frame)
            mode_row.pack(fill=tk.X, pady=(8, 0))
            ttk.Label(mode_row, text="Build Mode:", width=18).pack(side=tk.LEFT)
            ttk.Radiobutton(
                mode_row,
                text="Universal APK (Recommended)",
                value="universal_apk",
                variable=self.build_mode_var,
            ).pack(side=tk.LEFT, padx=(4, 12))
            ttk.Radiobutton(
                mode_row,
                text="Split APK (ABI)",
                value="split_apk",
                variable=self.build_mode_var,
            ).pack(side=tk.LEFT, padx=(0, 12))
            ttk.Radiobutton(
                mode_row,
                text="AAB (Play Store)",
                value="app_bundle",
                variable=self.build_mode_var,
            ).pack(side=tk.LEFT)
            profile_row = ttk.Frame(options_frame)
            profile_row.pack(fill=tk.X, pady=(8, 0))
            ttk.Label(profile_row, text="Resilience Profile:", width=18).pack(side=tk.LEFT)
            ttk.Radiobutton(
                profile_row,
                text="UX Offline-First",
                value="ux_offline_first",
                variable=self.resilience_profile_var,
            ).pack(side=tk.LEFT, padx=(4, 12))
            ttk.Radiobutton(
                profile_row,
                text="Balanced",
                value="balanced",
                variable=self.resilience_profile_var,
            ).pack(side=tk.LEFT, padx=(0, 12))
            ttk.Radiobutton(
                profile_row,
                text="Strict Security",
                value="strict_security",
                variable=self.resilience_profile_var,
            ).pack(side=tk.LEFT)
            ttk.Label(
                options_frame,
                text=(
                    "Universal APK cocok untuk semua HP Android. "
                    "Split APK lebih kecil tapi harus pilih arsitektur yang tepat."
                ),
                foreground="gray",
                wraplength=880,
            ).pack(anchor=tk.W, pady=(6, 0))
            ttk.Label(
                options_frame,
                text=(
                    "Profile menentukan tuning reconnect, ambang auto-submit adaptif, "
                    "dan policy emergency exit saat server outage."
                ),
                foreground="gray",
                wraplength=880,
            ).pack(anchor=tk.W, pady=(2, 0))

        # Environment status
        env_frame = ttk.Frame(options_frame)
        env_frame.pack(fill=tk.X, pady=(10, 0))

        jdk_status = "✅" if self.jdk_path else "❌"
        sdk_status = "✅" if self.android_sdk else "❌"
        kiosk_ready = self._uses_native_kiosk()
        kiosk_status = "✅" if kiosk_ready else "❌"
        flutter_status = "✅" if self.flutter_bin else "❌"

        ttk.Label(env_frame, text=f"JDK: {jdk_status} {self.jdk_path or 'Not found'}",
                 foreground="green" if self.jdk_path else "red").pack(anchor=tk.W)
        ttk.Label(env_frame, text=f"Android SDK: {sdk_status} {self.android_sdk or 'Not found'}",
                 foreground="green" if self.android_sdk else "red").pack(anchor=tk.W)
        ttk.Label(
            env_frame,
            text=f"Native Kiosk: {kiosk_status} {self.kiosk_project if kiosk_ready else 'android-kiosk not found'}",
            foreground="green" if kiosk_ready else "red",
        ).pack(anchor=tk.W)
        signing = load_release_signing_env()
        ttk.Label(
            env_frame,
            text=signing_status_text(signing),
            foreground="green" if signing_env_ready(signing) else "red",
        ).pack(anchor=tk.W)
        if not kiosk_ready:
            ttk.Label(env_frame, text=f"Flutter: {flutter_status} {self.flutter_bin or 'Not found'}",
                     foreground="green" if self.flutter_bin else "red").pack(anchor=tk.W)

        # ========== ACTION BUTTONS ==========
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(0, 10))

        self.save_btn = ttk.Button(button_frame, text="Simpan Konfigurasi",
                                   command=self.save_config)
        self.save_btn.pack(side=tk.LEFT, padx=3)

        self.build_btn = ttk.Button(button_frame, text="Build Artifact",
                                    command=self.start_build)
        self.build_btn.pack(side=tk.LEFT, padx=3)

        self.stop_btn = ttk.Button(button_frame, text="Stop",
                                   command=self.stop_build, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=3)

        ttk.Button(button_frame, text="Reload Config",
                  command=self.load_current_config).pack(side=tk.LEFT, padx=3)

        # ========== BUILD PROGRESS ==========
        progress_frame = ttk.LabelFrame(main_frame, text="Build Progress", padding="12")
        progress_frame.pack(fill=tk.BOTH, expand=True)

        self.progress = ttk.Progressbar(progress_frame, mode='indeterminate')
        self.progress.pack(fill=tk.X, pady=(0, 8))

        self.status_label = ttk.Label(progress_frame, text="Ready", font=("Arial", 10))
        self.status_label.pack(anchor=tk.W, pady=(0, 8))

        # Console Output
        self.console = scrolledtext.ScrolledText(progress_frame, height=12,
                                                 bg="#1E1E1E", fg="#00FF00",
                                                 font=("Consolas", 9))
        self.console.pack(fill=tk.BOTH, expand=True)

    def _update_https(self):
        """Update URL to use HTTPS if checkbox is checked"""
        current_url = self.server_url_var.get().strip()
        if self.use_https_var.get():
            if current_url.startswith("http://"):
                self.server_url_var.set(current_url.replace("http://", "https://", 1))
        else:
            if current_url.startswith("https://"):
                self.server_url_var.set(current_url.replace("https://", "http://", 1))

    def _normalize_server_url(self, raw_url: str) -> str:
        return normalize_server_url(raw_url, use_https=self.use_https_var.get())

    def validate_package_name(self) -> bool:
        """Validate Android applicationId/package format."""
        package_name = self.package_var.get().strip()
        if not is_valid_package_name(package_name):
            messagebox.showerror(
                "Invalid Package Name",
                (
                    "Package name tidak valid.\n\n"
                    "Contoh valid:\n"
                    f"  {NATIVE_KIOSK_PACKAGE}\n"
                    "  id.sekolah.ujian.mobile"
                ),
            )
            return False
        return True

    @staticmethod
    def _load_properties_file(path: Path) -> dict:
        return load_properties_file(path)

    @staticmethod
    def _save_properties_file(path: Path, props: dict):
        save_properties_file(path, props)

    @staticmethod
    def _parse_pubspec_version(version_value: str) -> tuple[str, str]:
        return parse_pubspec_version(version_value)

    def validate_version_fields(self) -> bool:
        is_valid, error_message = validate_version_fields(
            self.version_name_var.get().strip(),
            self.version_code_var.get().strip(),
        )
        if not is_valid:
            messagebox.showerror("Invalid Version", error_message or "Format versi tidak valid.")
            return False
        return True

    def _find_main_activity_file(self) -> Path | None:
        return find_main_activity_file(self.flutter_project)

    def validate_server_url(self):
        """Validate server URL format"""
        url = self._normalize_server_url(self.server_url_var.get())
        self.server_url_var.set(url)

        # Check if empty
        if not url:
            messagebox.showerror("Invalid URL", "Server URL tidak boleh kosong!")
            return False

        # Check URL format
        pattern = r'^https?://[A-Za-z0-9.-]+(:\d+)?(/.*)?$'
        if not re.match(pattern, url):
            messagebox.showerror(
                "Invalid URL",
                f"Format URL tidak valid!\n\n"
                f"URL harus dalam format:\n"
                f"  http://hostname:port/path\n"
                f"  https://hostname:port/path\n\n"
                f"Contoh:\n"
                f"  http://192.168.1.100:8000\n"
                f"  https://ujian.sekolah.id"
            )
            return False

        if self.use_https_var.get() and not url.startswith("https://"):
            messagebox.showerror(
                "Invalid URL",
                "HTTPS mode aktif, URL harus menggunakan https://",
            )
            return False

        if is_placeholder_server_url(url):
            messagebox.showerror(
                "Invalid URL",
                "Jangan build dengan placeholder siab1.invalid.\n"
                "Isi Server URL production, contoh:\n"
                f"  {DEFAULT_PRODUCTION_URL}",
            )
            return False

        return True

    def browse_icon(self):
        """Browse for icon file"""
        filename = filedialog.askopenfilename(
            title="Pilih Icon Aplikasi",
            filetypes=[
                ("Image files", "*.png *.jpg *.jpeg *.webp"),
                ("PNG files", "*.png"),
                ("JPEG files", "*.jpg *.jpeg"),
                ("WEBP files", "*.webp"),
                ("All files", "*.*"),
            ]
        )
        if filename:
            # Security: Validate path to prevent directory traversal
            try:
                filepath = Path(filename).resolve()
                # Only allow files from reasonable locations (not system directories)
                allowed_roots = [
                    Path.home().resolve(),  # User home directory
                    Path.cwd().resolve(),   # Current working directory
                ]

                is_safe = any(str(filepath).startswith(str(root)) for root in allowed_roots)

                if not is_safe:
                    messagebox.showerror("Error", "File berada di lokasi yang tidak diizinkan")
                    self.log(f"❌ Blocked: File outside allowed directory - {filename}")
                    return

                # Additional check: ensure file exists and is a file
                if not filepath.exists() or not filepath.is_file():
                    messagebox.showerror("Error", "File tidak valid")
                    return

                self.icon_path_var.set(str(filepath))
                self.log(f"✅ Icon selected: {filepath}")

            except Exception as e:
                messagebox.showerror("Error", f"Path validation error: {e}")
                self.log(f"❌ Path error: {e}")

    def load_current_config(self):
        """Load current configuration from kiosk gradle or Flutter config."""
        try:
            if self._uses_native_kiosk():
                self._load_native_kiosk_config()
                return
            # 1. Load from config.dart
            if self.config_dart_path.exists():
                with open(self.config_dart_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                # Server URL
                match = re.search(r'serverUrl\s*=\s*"([^"]+)"', content)
                if match:
                    self.server_url_var.set(
                        self._normalize_server_url(match.group(1))
                    )
                    self.use_https_var.set(match.group(1).startswith("https://"))
                force_https_match = re.search(r'forceHttps\s*=\s*(true|false)', content)
                if force_https_match:
                    self.use_https_var.set(force_https_match.group(1) == "true")

                # App Name (prefer from pubspec if available, but config.dart is good backup)
                match = re.search(r'appName\s*=\s*"([^"]+)"', content)
                if match:
                    self.app_name_var.set(normalize_apk_display_name(match.group(1)))

                # Security options
                for var_name, tk_var in [
                    ('enableKiosk', self.enable_kiosk_var),
                    ('blockScreenshot', self.block_screenshot_var),
                    ('detectRoot', self.detect_root_var),
                    ('blockTaskSwitch', self.block_task_switch_var),
                ]:
                    match = re.search(rf'{var_name}\s*=\s*(true|false)', content)
                    if match:
                        tk_var.set(match.group(1) == 'true')

                profile_match = re.search(
                    r'resilienceProfile\s*=\s*"([^"]+)"',
                    content,
                )
                if profile_match:
                    self.resilience_profile_var.set(profile_match.group(1))

                self.log("✅ Configuration loaded from config.dart")
            else:
                self.log("⚠️ config.dart not found, using defaults")

            # 2. Load Package Name from build.gradle
            build_gradle = self.flutter_project / "android" / "app" / "build.gradle"
            if build_gradle.exists():
                with open(build_gradle, 'r', encoding='utf-8') as f:
                    content = f.read()
                match = re.search(r'applicationId\s+"([^"]+)"', content)
                if match:
                    self.package_var.set(match.group(1))
                    self.log(f"✅ Loaded package name: {match.group(1)}")

            # 3. Load App Name/Version from pubspec.yaml (Source of truth for name)
            pubspec = self.flutter_project / "pubspec.yaml"
            version_loaded_from_pubspec = False
            if pubspec.exists():
                with open(pubspec, 'r', encoding='utf-8') as f:
                    content = f.read()
                # Simple regex for name, assuming "name: value" format
                match = re.search(r'^name:\s+([^\s]+)', content, re.MULTILINE)
                if match:
                    # Note: pubspec name is usually snake_case, display name is in AndroidManifest
                    pass
                version_match = re.search(r'^version:\s*([^\s#]+)', content, re.MULTILINE)
                if version_match:
                    version_name, version_code = self._parse_pubspec_version(version_match.group(1))
                    self.version_name_var.set(version_name)
                    self.version_code_var.set(version_code)
                    version_loaded_from_pubspec = True
                    self.log(f"✅ Loaded version from pubspec.yaml: {version_name}+{version_code}")

            # 4. Load Version from local.properties
            local_props = self.flutter_project / "android" / "local.properties"
            if local_props.exists():
                props = self._load_properties_file(local_props)
                if not version_loaded_from_pubspec and props.get("flutter.versionName"):
                    self.version_name_var.set(props["flutter.versionName"])
                if not version_loaded_from_pubspec and props.get("flutter.versionCode"):
                    self.version_code_var.set(props["flutter.versionCode"])
                if props.get("sxb.serverUrl"):
                    self.server_url_var.set(
                        self._normalize_server_url(props["sxb.serverUrl"])
                    )
                if props.get("sxb.usesCleartextTraffic") is not None:
                    self.use_https_var.set(props["sxb.usesCleartextTraffic"].lower() != "true")
                if props.get("sxb.buildMode"):
                    self.build_mode_var.set(props["sxb.buildMode"])
                if props.get("sxb.resilienceProfile"):
                    self.resilience_profile_var.set(props["sxb.resilienceProfile"])

            self.server_url_var.set(
                self._normalize_server_url(self.server_url_var.get())
            )

        except Exception as e:
            self.log(f"⚠️ Could not load config: {str(e)}")

    def _generate_new_token(self):
        """Generate a new unique build token"""
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        alphabet = string.ascii_uppercase + string.digits
        random_suffix = ''.join(secrets.choice(alphabet) for _ in range(6))
        token = f"BUILD-{timestamp}-{random_suffix}"
        self.build_token_var.set(token)
        return token

    def _copy_token(self):
        """Copy current token to clipboard"""
        token = self.build_token_var.get()
        self.root.clipboard_clear()
        self.root.clipboard_append(token)
        self.log(f"📋 Token copied to clipboard: {token}")
        messagebox.showinfo("Copied!", f"Token berhasil di-copy:\n\n{token}\n\nPaste token ini di Admin Panel.")

    def _copy_signature(self):
        """Copy current signature to clipboard"""
        sig = self.app_signature_var.get()
        if not self._is_valid_sha256(sig):
            latest_artifact = self._find_latest_artifact()
            if latest_artifact:
                self.log(f"🔎 Hash belum siap. Mencoba ekstrak dari artifact terbaru: {latest_artifact.name}")
                self._update_signature_from_artifact(latest_artifact)
                sig = self.app_signature_var.get()

        if not self._is_valid_sha256(sig):
            detail = self.last_signature_error or "Hash belum berhasil diekstrak dari artifact/keystore."
            messagebox.showwarning(
                "Hash belum siap",
                f"App Signature (SHA-256) belum tersedia.\n\nDetail:\n{detail}\n\n"
                "Pastikan APK release ter-sign, lalu build ulang."
            )
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(sig)
        self.log(f"📋 Signature copied to clipboard: {sig}")
        messagebox.showinfo("Copied!", f"Signature Hash berhasil di-copy:\n\n{sig}\n\nMasukkan hash ini ke Admin Panel → Pengaturan → APK Signature Hash.")


    def generate_config_dart(self):
        """Generate config.dart with current settings including build token"""
        # Auto-generate new token if enabled
        if self.auto_token_var.get():
            self._generate_new_token()

        current_token = self.build_token_var.get()
        build_timestamp = int(time.time())
        normalized_url = self._normalize_server_url(self.server_url_var.get())
        self.server_url_var.set(normalized_url)
        force_https = self.use_https_var.get()
        cleartext_allowed = not force_https
        build_mode = self.build_mode_var.get()
        resilience_profile = self.resilience_profile_var.get().strip() or "ux_offline_first"

        app_name = normalize_apk_display_name(self.app_name_var.get())
        self.app_name_var.set(app_name)

        config_content, resilience_profile, tuning = render_config_dart_content(
            normalized_url=normalized_url,
            app_name=app_name,
            force_https=force_https,
            cleartext_allowed=cleartext_allowed,
            build_mode=build_mode,
            build_token=current_token,
            build_timestamp=build_timestamp,
            security_settings={
                "enable_kiosk": self.enable_kiosk_var.get(),
                "block_screenshot": self.block_screenshot_var.get(),
                "detect_root": self.detect_root_var.get(),
                "block_task_switch": self.block_task_switch_var.get(),
            },
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            resilience_profile=resilience_profile,
        )

        with open(self.config_dart_path, 'w', encoding='utf-8') as f:
            f.write(config_content)

        # Store for later display
        self.last_build_token = current_token

        self.log(f"✅ Generated config.dart")
        self.log(f"   Server URL: {normalized_url}")
        self.log(f"   Student Entry URL: {normalized_url}student/")
        self.log(f"   App Name: {self.app_name_var.get()}")
        self.log(f"   Build Mode: {build_mode}")
        self.log(f"   Resilience Profile: {resilience_profile}")
        self.log("   Connection Mode: Clean URL + local auth injection + transient retry")
        self.log(f"   Build Token: {current_token}")
        self.log(f"   Kiosk: {self.enable_kiosk_var.get()}, Screenshot Block: {self.block_screenshot_var.get()}")

    def _load_native_kiosk_config(self):
        if not (self.kiosk_project / "app" / "build.gradle.kts").is_file():
            self.log("android-kiosk build.gradle.kts not found")
            return
        cfg = read_native_kiosk_config(self.kiosk_project)
        self.package_var.set(cfg.package_name or NATIVE_KIOSK_PACKAGE)
        if cfg.version_name:
            self.version_name_var.set(cfg.version_name)
        if cfg.version_code:
            self.version_code_var.set(cfg.version_code)
        if cfg.app_name:
            self.app_name_var.set(cfg.app_name)
        if cfg.build_token:
            self.build_token_var.set(cfg.build_token)
            self.last_build_token = cfg.build_token
        optional_url = load_optional_server_url()
        if optional_url and not is_placeholder_server_url(optional_url):
            self.server_url_var.set(self._normalize_server_url(optional_url))
        elif is_placeholder_server_url(self.server_url_var.get()):
            self.server_url_var.set(DEFAULT_PRODUCTION_URL)
        self.use_https_var.set(True)
        self.log("Configuration loaded from android-kiosk")

    def _save_native_kiosk_config(self, show_success: bool = True) -> bool:
        package_name = self.package_var.get().strip()
        if package_name != NATIVE_KIOSK_PACKAGE:
            messagebox.showerror(
                "Invalid Package Name",
                f"Native kiosk wajib package {NATIVE_KIOSK_PACKAGE}",
            )
            return False
        version_name = self.version_name_var.get().strip()
        version_code = self.version_code_var.get().strip()
        app_name = normalize_apk_display_name(self.app_name_var.get())
        self.app_name_var.set(app_name)
        if self.auto_token_var.get():
            self._generate_new_token()
        token = self.build_token_var.get()
        self.last_build_token = token
        apply_native_kiosk_config(
            self.kiosk_project,
            version_name=version_name,
            version_code=version_code,
            app_name=app_name,
            build_token=token,
        )
        if self.icon_path_var.get():
            if not PIL_AVAILABLE:
                messagebox.showerror(
                    "Icon Processing Required",
                    "Python ini tidak bisa import PIL.Image.\n\n"
                    "Jalankan GUI lewat .venv:\n"
                    "  .venv/bin/python tools/apk_builder_gui.py\n"
                    "atau:\n"
                    "  bash bin/run_apk_builder.sh",
                )
                return False
            self.process_icon(self.icon_path_var.get())
        self.update_security_signature()
        self.log("Native kiosk configuration saved")
        self.log(f"   Server URL: {self.server_url_var.get()}")
        self.log(f"   Package: {package_name}")
        self.log(f"   Version: {version_name}+{version_code}")
        self.log(f"   Build Token: {token}")
        if show_success:
            messagebox.showinfo("Success", "Konfigurasi kiosk berhasil disimpan!")
        return True

    def save_config(self, show_success: bool = True):
        """Save all configuration"""
        try:
            # Validate server URL first
            if not self.validate_server_url():
                return False
            if not self.validate_package_name():
                return False
            if not self.validate_version_fields():
                return False
            if self._uses_native_kiosk():
                return self._save_native_kiosk_config(show_success=show_success)

            version_name = self.version_name_var.get().strip()
            version_code = self.version_code_var.get().strip()
            app_name = normalize_apk_display_name(self.app_name_var.get())
            self.version_name_var.set(version_name)
            self.version_code_var.set(version_code)
            self.app_name_var.set(app_name)

            self.log("\n" + "="*50)
            self.log("💾 Saving configuration...")

            # 1. Generate config.dart
            self.generate_config_dart()

            # 2. Update local.properties
            local_props = self.flutter_project / "android" / "local.properties"
            props = self._load_properties_file(local_props)
            props["flutter.versionName"] = version_name
            props["flutter.versionCode"] = version_code
            props["sxb.serverUrl"] = self.server_url_var.get().strip()
            props["sxb.usesCleartextTraffic"] = str(not self.use_https_var.get()).lower()
            props["sxb.buildMode"] = self.build_mode_var.get().strip()
            props["sxb.resilienceProfile"] = self.resilience_profile_var.get().strip()
            self._save_properties_file(local_props, props)
            self.log(f"✅ Updated local.properties (version: {version_name}+{version_code})")

            # 3. Update AndroidManifest app label
            manifest = self.flutter_project / "android" / "app" / "src" / "main" / "AndroidManifest.xml"
            if manifest.exists():
                with open(manifest, 'r', encoding='utf-8') as f:
                    content = f.read()

                content = re.sub(
                    r'android:label="[^"]+"',
                    f'android:label="{app_name}"',
                    content
                )

                with open(manifest, 'w', encoding='utf-8') as f:
                    f.write(content)

                self.log("✅ Updated AndroidManifest.xml (App Label)")

            # 4. Update build.gradle (Application ID)
            build_gradle = self.flutter_project / "android" / "app" / "build.gradle"
            if build_gradle.exists():
                with open(build_gradle, 'r', encoding='utf-8') as f:
                    content = f.read()

                new_package = self.package_var.get()
                content = re.sub(
                    r'applicationId\s+"([^"]+)"',
                    f'applicationId "{new_package}"',
                    content
                )

                with open(build_gradle, 'w', encoding='utf-8') as f:
                    f.write(content)

                self.log(f"✅ Updated build.gradle (Package: {new_package})")

                # Warn if namespace differs from applicationId
                ns_match = re.search(r'namespace\s+"([^"]+)"', content)
                if ns_match and ns_match.group(1) != new_package:
                    self.log(f"⚠️ PERHATIAN: namespace build.gradle ('{ns_match.group(1)}') berbeda dari applicationId ('{new_package}').")
                    self.log(f"   Ini normal jika Anda hanya mengubah applicationId tanpa refactor package.")
                    self.log(f"   Jangan ubah namespace kecuali Anda juga rename folder Kotlin dan import.")

            # 5. Update pubspec.yaml (App Name for Flutter context)
            pubspec = self.flutter_project / "pubspec.yaml"
            if pubspec.exists():
                with open(pubspec, 'r', encoding='utf-8') as f:
                    content = f.read()

                safe_name = re.sub(r'[^a-z0-9_]', '', app_name.lower().replace(' ', '_'))

                # Update name
                content = re.sub(
                    r'^name:\s+[^\s]+',
                    f'name: {safe_name}',
                    content,
                    flags=re.MULTILINE
                )

                # Update description
                content = re.sub(
                    r'^description:\s+.*$',
                    f'description: {app_name} - {DEFAULT_APP_SUBTITLE}',
                    content,
                    flags=re.MULTILINE
                )

                # Update flutter app version used by `flutter build`
                pubspec_version = f"{version_name}+{version_code}"
                if re.search(r'^version:\s*.*$', content, re.MULTILINE):
                    content = re.sub(
                        r'^version:\s*.*$',
                        f'version: {pubspec_version}',
                        content,
                        flags=re.MULTILINE
                    )
                else:
                    # Keep file valid even if template misses version line
                    content = content.rstrip() + f"\nversion: {pubspec_version}\n"

                with open(pubspec, 'w', encoding='utf-8') as f:
                    f.write(content)

                self.log(f"✅ Updated pubspec.yaml (Internal Name: {safe_name})")
                self.log(f"   Version: {pubspec_version}")

            # 6. Process icon if provided
            if self.icon_path_var.get():
                if not PIL_AVAILABLE:
                    message = (
                        "Python ini tidak bisa import PIL.Image, jadi icon APK tidak diproses.\n\n"
                        "Jalankan GUI lewat .venv:\n"
                        "  .venv/bin/python tools/apk_builder_gui.py\n"
                        "atau:\n"
                        "  bash bin/run_apk_builder.sh\n\n"
                        "Build dibatalkan agar APK tidak memakai icon lama tanpa disadari."
                    )
                    self.log("❌ Icon tidak diproses: Pillow/PIL belum terinstall")
                    messagebox.showerror("Icon Processing Required", message)
                    return False
                self.process_icon(self.icon_path_var.get())

            # 7. Update Security Signature (NEW)
            self.update_security_signature()
            if not self._is_valid_sha256(self.app_signature_var.get()):
                latest_artifact = self._find_latest_artifact()
                if latest_artifact:
                    self._update_signature_from_artifact(latest_artifact)

            self.log("\n✅ All configuration saved!")
            if show_success:
                messagebox.showinfo("Success", "Konfigurasi berhasil disimpan!")
            return True

        except Exception as e:
            self.log(f"❌ Error saving config: {str(e)}")
            messagebox.showerror("Error", f"Gagal menyimpan konfigurasi:\n{str(e)}")
            return False

    def _update_native_kiosk_signature(self):
        signing = load_release_signing_env()
        if not signing_env_ready(signing):
            self.log("Keystore rilis belum siap, skip signature extract")
            self.last_signature_error = "SIAB1_RELEASE_* belum lengkap"
            return
        keytool = self._resolve_keytool()
        if not keytool:
            self.last_signature_error = "keytool tidak ditemukan"
            self.log("keytool tidak ditemukan")
            return
        keystore_path = Path(signing["SIAB1_RELEASE_KEYSTORE"]).expanduser()
        key_alias = signing["SIAB1_RELEASE_KEY_ALIAS"]
        store_pass = signing["SIAB1_RELEASE_STORE_PASSWORD"]
        cmd = [
            keytool,
            "-list",
            "-v",
            "-keystore",
            str(keystore_path),
            "-alias",
            key_alias,
        ]
        process = subprocess.run(
            cmd,
            input=f"{store_pass}\n",
            capture_output=True,
            text=True,
            env=self._tool_env(),
        )
        if process.returncode != 0:
            self.last_signature_error = "keytool list gagal"
            self.log("Gagal membaca keystore rilis")
            return
        match = re.search(r"SHA256:\s+([0-9A-Fa-f:]+)", process.stdout)
        if not match:
            self.last_signature_error = "SHA-256 tidak ditemukan di output keytool"
            return
        server_hash = match.group(1).replace(":", "").lower()
        self._set_app_signature(server_hash, wait=True)
        self.last_signature_error = ""
        self.log("Signature hash siap. Daftarkan di Admin Panel.")

    def update_security_signature(self):
        """Extract keystore signature and update source code automatically"""
        try:
            if self._uses_native_kiosk():
                self._update_native_kiosk_signature()
                return
            self.log("🔐 Updating security signatures...")

            # 1. Find keystore and password
            android_dir = self.flutter_project / "android"
            key_props = android_dir / "key.properties"
            key_properties = self._load_properties_file(key_props)
            key_alias = key_properties.get("keyAlias", "release")
            store_pass = key_properties.get("storePassword")
            store_file = key_properties.get("storeFile", "app/release-keystore.jks")
            keystore_path = (android_dir / store_file).resolve()

            if not keystore_path.exists():
                candidates = [
                    p for p in android_dir.rglob("*")
                    if p.is_file() and p.suffix.lower() in {".jks", ".keystore"}
                ]
                if candidates:
                    keystore_path = max(candidates, key=lambda p: p.stat().st_mtime)
                    self.log(f"⚠️ Keystore path dari key.properties tidak ditemukan, pakai fallback: {keystore_path}")
                else:
                    self.log("⚠️ Keystore not found, skipping signature update")
                    self.last_signature_error = f"Keystore tidak ditemukan: {keystore_path}"
                    return

            if not store_pass:
                self.log("⚠️ storePassword not found in key.properties, skipping signature update")
                self.last_signature_error = "storePassword tidak ditemukan di key.properties"
                return

            # 2. Extract SHA-256 using keytool
            cmd = [
                self._resolve_keytool(), "-list", "-v",
                "-keystore", str(keystore_path),
                "-alias", key_alias
            ]

            # Use stdin first to avoid exposing password in process args
            process = subprocess.run(
                cmd,
                input=f"{store_pass}\n",
                capture_output=True,
                text=True,
                env=self._tool_env()
            )
            if process.returncode != 0:
                process = subprocess.run(
                    cmd + ["-storepass", store_pass],
                    capture_output=True,
                    text=True,
                    env=self._tool_env()
                )
            if process.returncode != 0:
                self.log(f"⚠️ Failed to read keystore: {process.stderr}")
                self.last_signature_error = process.stderr.strip() or "keytool list gagal"
                return

            # Parse SHA-256
            # Output format: SHA256: 29:7A:D1:BF...
            match = re.search(r'SHA256:\s+([0-9A-Fa-f:]+)', process.stdout)
            if not match:
                self.log("⚠️ SHA-256 fingerprint not found in keytool output")
                self.last_signature_error = "SHA-256 tidak ditemukan di output keytool"
                return

            sha256_str = match.group(1).strip()
            server_hash = sha256_str.replace(':', '').lower()
            self._set_app_signature(server_hash, wait=True)
            self.last_signature_error = ""
            self.log(f"   Detected Key Hash: {sha256_str[:20]}...")

            # Convert to byte array chunks (32 bytes total)
            # 8 chunks of 4 bytes
            hex_parts = sha256_str.split(':')
            if len(hex_parts) != 32:
                self.log("⚠️ Invalid SHA-256 length")
                self.last_signature_error = "Panjang SHA-256 tidak valid"
                return

            chunks = []
            for i in range(0, 32, 4):
                chunk = hex_parts[i:i+4]
                chunks.append(chunk)

            # 3. Update MainActivity.kt
            kt_file = self._find_main_activity_file()
            if kt_file and kt_file.exists():
                with open(kt_file, 'r', encoding='utf-8') as f:
                    content = f.read()

                # Replace chunks
                for i, chunk in enumerate(chunks):
                    chunk_idx = i + 1
                    # Format: private val sigChunk1 = byteArrayOf(0x29.toByte(), ...)
                    bytes_str = ", ".join([f"0x{b}.toByte()" for b in chunk])
                    new_line = f"    private val sigChunk{chunk_idx} = byteArrayOf({bytes_str})"

                    pattern = rf"^\s*private val sigChunk{chunk_idx}\s*=.*$"
                    content = re.sub(pattern, new_line, content, flags=re.MULTILINE)

                with open(kt_file, 'w', encoding='utf-8') as f:
                    f.write(content)
                self.log(f"✅ Updated MainActivity.kt signature ({kt_file})")
            else:
                self.log("⚠️ MainActivity.kt not found, skipped Kotlin signature update")

            # 4. Update SignatureVerifier.dart
            dart_file = self.flutter_project / "lib/services/signature_verifier.dart"
            if dart_file.exists():
                with open(dart_file, 'r', encoding='utf-8') as f:
                    content = f.read()

                # Replace chunks
                for i, chunk in enumerate(chunks):
                    chunk_idx = i + 1
                    # Format: static const List<int> _sig1 = [41, 122, ...];
                    # Need to convert hex to int
                    int_vals = [str(int(b, 16)) for b in chunk]
                    int_str = ", ".join(int_vals)

                    new_line = f"  static const List<int> _sig{chunk_idx} = [{int_str}];"

                    pattern = rf"^\s*static const List<int> _sig{chunk_idx}\s*=\s*\[.*?\];"
                    content = re.sub(pattern, new_line, content, flags=re.MULTILINE)

                with open(dart_file, 'w', encoding='utf-8') as f:
                    f.write(content)
                self.log("✅ Updated SignatureVerifier.dart signature")

            # 5. Display wichtig instruction for Admin Panel
            # SIGNATURE SEKARANG 100% DIKELOLA VIA DATABASE (ADMIN PANEL)
            # JANGAN LAGI UPDATE config/security.py!
            self.log("")
            self.log("=" * 50)
            self.log("⚠️  PENTING: COPY HASH KE ADMIN PANEL!")
            self.log("=" * 50)
            self.log(f"   Hash: {server_hash}")
            self.log("")
            self.log("   Langkah:")
            self.log("   1. Buka Admin Panel → Pengaturan")
            self.log("   2. Paste hash di 'APK Signature Hash'")
            self.log("   3. Klik Simpan")
            self.log("")
            self.log("   🔴 APK akan TERBLOKIR jika hash tidak terdaftar!")
            self.log("=" * 50)

        except Exception as e:
            self.log(f"⚠️ Error updating signatures: {e}")

    @staticmethod
    def _sha256_file(file_path: Path) -> str:
        return sha256_file(file_path)

    def _run_on_ui_thread(self, func, wait=False):
        """Run callable on Tk main thread (thread-safe helper)."""
        if threading.current_thread() is threading.main_thread():
            return func()

        if not wait:
            self.root.after(0, func)
            return None

        done = threading.Event()
        result = {"value": None, "error": None}

        def wrapped():
            try:
                result["value"] = func()
            except Exception as e:
                result["error"] = e
            finally:
                done.set()

        self.root.after(0, wrapped)
        if not done.wait(timeout=30):
            self.log("⚠️ UI thread timeout while waiting for operation")
            return None
        if result["error"]:
            raise result["error"]
        return result["value"]

    def _show_info(self, title: str, message: str):
        if threading.current_thread() is threading.main_thread():
            messagebox.showinfo(title, message)
        else:
            self._run_on_ui_thread(lambda: messagebox.showinfo(title, message), wait=False)

    def _show_error(self, title: str, message: str):
        if threading.current_thread() is threading.main_thread():
            messagebox.showerror(title, message)
        else:
            self._run_on_ui_thread(lambda: messagebox.showerror(title, message), wait=False)

    def _copy_to_clipboard(self, text: str):
        def _copy():
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
        self._run_on_ui_thread(_copy, wait=False)

    def _set_app_signature(self, value: str, wait=False):
        self._run_on_ui_thread(lambda: self.app_signature_var.set(value), wait=wait)

    @staticmethod
    def _is_valid_sha256(value: str) -> bool:
        return is_valid_sha256(value)

    def _tool_env(self) -> dict:
        flutter_bin = self.flutter_bin or find_flutter(self.flutter_project, self.project_root)
        return build_tool_env(self.jdk_path, self.android_sdk, flutter_bin)

    def _resolve_keytool(self) -> str:
        return resolve_keytool(self.jdk_path)

    def _resolve_apksigner(self) -> str | None:
        return resolve_apksigner(self.android_sdk)

    def _find_latest_artifact(self) -> Path | None:
        return find_latest_artifact(
            self.project_root,
            self.flutter_project,
            self.kiosk_project,
        )

    def _update_signature_from_artifact(self, artifact_path: Path) -> bool:
        """Extract signing SHA-256 from APK/AAB output as fallback when keystore path is missing."""
        try:
            self.log(f"🔎 Reading signer hash from artifact: {artifact_path.name}")
            server_hash = None
            error_parts = []

            # APK often uses v2/v3 signing; apksigner is the most reliable source.
            if artifact_path.suffix.lower() == ".apk":
                apksigner = self._resolve_apksigner()
                if apksigner:
                    cmd = [apksigner, "verify", "--print-certs", str(artifact_path)]
                    process = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        env=self._tool_env()
                    )
                    if process.returncode == 0:
                        m = re.search(
                            r"SHA-256 (?:digest|Digest):\s*([0-9A-Fa-f:]+)",
                            process.stdout
                        )
                        if m:
                            server_hash = m.group(1).replace(":", "").lower()
                        else:
                            error_parts.append("apksigner: SHA-256 tidak ditemukan")
                    else:
                        error_parts.append(process.stderr.strip() or "apksigner verify gagal")
                else:
                    error_parts.append("apksigner tidak ditemukan di Android SDK")

            # Fallback for AAB/JAR or when apksigner path fails.
            if not server_hash:
                cmd = [self._resolve_keytool(), "-printcert", "-jarfile", str(artifact_path)]
                process = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    env=self._tool_env()
                )
                if process.returncode == 0:
                    m = re.search(r"SHA256:\s*([0-9A-Fa-f:]+)", process.stdout)
                    if m:
                        server_hash = m.group(1).replace(":", "").lower()
                    else:
                        error_parts.append("keytool: SHA-256 tidak ditemukan")
                else:
                    error_parts.append(process.stderr.strip() or "keytool printcert gagal")

            if not server_hash:
                self.last_signature_error = "; ".join([p for p in error_parts if p])[:1000]
                self.log(f"⚠️ Gagal ekstrak signer hash: {self.last_signature_error}")
                return False

            if not self._is_valid_sha256(server_hash):
                self.last_signature_error = "Format hash hasil ekstraksi tidak valid"
                self.log("⚠️ Signer hash format tidak valid")
                return False

            self._set_app_signature(server_hash, wait=True)
            self.last_signature_error = ""
            self.log(f"✅ Signer hash extracted from artifact: {server_hash[:24]}...")
            return True
        except Exception as e:
            self.last_signature_error = str(e)
            self.log(f"⚠️ Failed to extract signer hash from artifact: {e}")
            return False

    def process_icon(self, icon_path):
        """Process and replace app icon"""
        try:
            self.log(f"🎨 Processing icon: {icon_path}")

            sizes = {
                "mipmap-mdpi": 48,
                "mipmap-hdpi": 72,
                "mipmap-xhdpi": 96,
                "mipmap-xxhdpi": 144,
                "mipmap-xxxhdpi": 192
            }

            if Image is None:
                raise RuntimeError("PIL.Image tidak tersedia")
            img = Image.open(icon_path).convert("RGBA")
            resample = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
            android_res = (
                self.kiosk_project / "app" / "src" / "main" / "res"
                if self._uses_native_kiosk()
                else self.flutter_project / "android" / "app" / "src" / "main" / "res"
            )

            for folder, size in sizes.items():
                resized = img.resize((size, size), resample)
                output_dir = android_res / folder
                output_dir.mkdir(parents=True, exist_ok=True)
                resized.save(output_dir / "ic_launcher.png")

            self.log(f"✅ Icon processed ({len(sizes)} sizes)")

        except Exception as e:
            self.log(f"⚠️ Error processing icon: {str(e)}")

    def start_build(self):
        """Start APK build"""
        if not self.jdk_path:
            messagebox.showerror("Error", "JDK 17 tidak ditemukan!\n\nDownload dari: https://adoptium.net/")
            return

        if not self.android_sdk:
            messagebox.showerror("Error", "Android SDK tidak ditemukan!")
            return

        if self._uses_native_kiosk():
            signing = load_release_signing_env()
            if not signing_env_ready(signing):
                messagebox.showerror(
                    "Error",
                    "Signing rilis belum siap.\n\n"
                    "Set SIAB1_RELEASE_KEYSTORE, SIAB1_RELEASE_STORE_PASSWORD,\n"
                    "SIAB1_RELEASE_KEY_ALIAS, SIAB1_RELEASE_KEY_PASSWORD\n"
                    "atau isi ~/.android/siab1-release.env",
                )
                return
        else:
            # Re-scan in case local.properties or PATH changed while GUI is open.
            self.flutter_bin = find_flutter(self.flutter_project, self.project_root)
            if not self.flutter_bin:
                messagebox.showerror(
                    "Error",
                    "Flutter SDK tidak ditemukan.\n\n"
                    "Install Flutter atau set salah satu:\n"
                    "• PATH berisi flutter\n"
                    "• FLUTTER_ROOT / FLUTTER_HOME\n"
                    "• flutter_client_code/android/local.properties: flutter.sdk=/path/to/flutter\n\n"
                    "Build belum dijalankan agar tidak gagal di flutter clean."
                )
                return

        if not self.save_config(show_success=False):
            self.log("Build dibatalkan karena konfigurasi belum valid")
            return

        # Disable buttons
        self.build_btn.config(state=tk.DISABLED)
        self.save_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.progress.start()

        # Start build thread
        build_thread = threading.Thread(target=self.build_apk, daemon=True)
        build_thread.start()

    def stop_build(self):
        """Stop current build"""
        if self.build_process:
            try:
                self.build_process.terminate()
                self.log("⚠️ Build process terminated")
            except subprocess.SubprocessError as e:
                self.log(f"⚠️ Error terminating process: {e}")
            except Exception as e:
                self.log(f"⚠️ Unexpected error during termination: {e}")
        self.reset_ui()

    def _build_native_kiosk(self):
        """Build signed android-kiosk release APK."""
        try:
            self.log("\n" + "=" * 60)
            self.log("Starting native kiosk release build")
            self.log("=" * 60 + "\n")
            signing = load_release_signing_env()
            if not signing_env_ready(signing):
                raise Exception("Signing rilis belum siap")
            env = build_tool_env(self.jdk_path, self.android_sdk, None)
            env.update(signing)
            env["SIAB1_SERVER_URL"] = self._normalize_server_url(self.server_url_var.get())
            ensure_gradle_memory_config(
                gradle_properties=self.kiosk_project / "gradle.properties",
                env=env,
                log=self.log,
            )
            if self.preflight_test_var.get():
                self.update_status("Pre-build: tes kontrak kiosk...")
                self.log("Pre-build: pytest tests/test_native_kiosk_contract.py")
                pytest_bin = self.project_root / ".venv" / "bin" / "pytest"
                cmd = (
                    [str(pytest_bin), "tests/test_native_kiosk_contract.py", "-q"]
                    if pytest_bin.is_file()
                    else [sys.executable, "-m", "pytest", "tests/test_native_kiosk_contract.py", "-q"]
                )
                result = self.run_command(cmd, cwd=self.project_root, env=env)
                if not result or result.returncode != 0:
                    raise Exception("Pre-build gagal: tes kontrak kiosk")
            if self.clean_build_var.get():
                self.update_status("Cleaning native kiosk...")
                gradlew = self.kiosk_project / "gradlew"
                clean_cmd = (
                    [str(gradlew), "clean"]
                    if gradlew.is_file()
                    else ["gradle", "clean"]
                )
                clean_result = self.run_command(clean_cmd, cwd=self.kiosk_project, env=env)
                if not clean_result or clean_result.returncode != 0:
                    raise Exception("gradle clean failed")
            self.update_status("Building native kiosk release APK...")
            self.log(f"   Server URL: {env['SIAB1_SERVER_URL']}")
            self.log(f"   Package: {NATIVE_KIOSK_PACKAGE}")
            gradlew = self.kiosk_project / "gradlew"
            build_cmd = (
                [str(gradlew), ":app:assembleRelease", "--no-daemon"]
                if gradlew.is_file()
                else ["gradle", ":app:assembleRelease", "--no-daemon"]
            )
            result = self.run_command(build_cmd, cwd=self.kiosk_project, env=env)
            if result and result.returncode != 0 and self._command_output_contains("java heap space"):
                self.log("Java heap space. Retry with higher Gradle heap...")
                ensure_gradle_memory_config(
                    gradle_properties=self.kiosk_project / "gradle.properties",
                    env=env,
                    log=self.log,
                    force_high=True,
                )
                result = self.run_command(build_cmd, cwd=self.kiosk_project, env=env)
            if not result or result.returncode != 0:
                raise Exception("assembleRelease failed")
            artifact = kiosk_release_apk_path(self.kiosk_project)
            if not artifact.is_file():
                raise FileNotFoundError(f"APK tidak ditemukan: {artifact}")
            output_dir = self.project_root / "apk_builds"
            output_dir.mkdir(exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            app_name = normalize_apk_display_name(self.app_name_var.get())
            safe_name = re.sub(r"[^a-z0-9_]", "", app_name.replace(" ", "_").lower()) or "siab1"
            output_file = output_dir / f"{safe_name}_kiosk_{timestamp}.apk"
            shutil.copy2(artifact, output_file)
            size_mb = output_file.stat().st_size / (1024 * 1024)
            sha256_hex = self._sha256_file(output_file)
            checksum_path = output_file.with_suffix(output_file.suffix + ".sha256")
            checksum_path.write_text(f"{sha256_hex}  {output_file.name}\n", encoding="utf-8")
            self._update_signature_from_artifact(output_file)
            self.log(f"APK: {output_file}")
            self.log(f"Size: {size_mb:.2f} MB")
            self.log(f"Build Token: {self.last_build_token}")
            self.update_status("Build complete! Artifact saved to apk_builds/")
            self._copy_to_clipboard(self.last_build_token)
            self._show_info(
                "Build Successful!",
                f"APK kiosk rilis berhasil.\n\n"
                f"  {output_file.name} ({size_mb:.1f} MB)\n\n"
                f"Token (sudah di-copy):\n{self.last_build_token}\n\n"
                f"Daftarkan token dan signature hash di Admin Panel.",
            )
        except Exception as exc:
            self.log(f"\nBUILD FAILED: {exc}")
            self.update_status("Build failed!")
            self._show_error("Build Failed", f"Build gagal:\n{exc}")
        finally:
            self.reset_ui()

    def build_apk(self):
        """Build APK (runs in background thread)"""
        try:
            if self._uses_native_kiosk():
                self._build_native_kiosk()
                return
            self.log("\n" + "="*60)
            self.log("🚀 Starting Android Build Process")
            self.log("="*60 + "\n")

            # Setup environment
            flutter_bin = self.flutter_bin or find_flutter(self.flutter_project, self.project_root)
            if not flutter_bin:
                raise Exception(
                    "Flutter SDK tidak ditemukan. Set PATH/FLUTTER_ROOT atau flutter.sdk di android/local.properties."
                )
            env = build_tool_env(self.jdk_path, self.android_sdk, flutter_bin)
            build_mode = self.build_mode_var.get()
            app_name = normalize_apk_display_name(self.app_name_var.get())
            self.app_name_var.set(app_name)
            self.log(f"🛠️ Flutter executable: {flutter_bin}")

            # Stabilize Gradle memory to avoid Java heap space on release build.
            self._ensure_gradle_memory_config(env, force_high=False)

            # Clean if requested
            if self.clean_build_var.get():
                self.update_status("Cleaning previous build...")
                self.log("🧹 Cleaning build cache...")
                clean_cmd = [flutter_bin, "clean"]
                clean_result = self.run_command(clean_cmd, cwd=self.flutter_project, env=env)
                if not clean_result or clean_result.returncode != 0:
                    raise Exception("flutter clean failed")

            self.update_status("Running flutter pub get...")
            self.log("📦 Running flutter pub get...")
            pub_get_result = self.run_command([flutter_bin, "pub", "get"], cwd=self.flutter_project, env=env)
            if not pub_get_result or pub_get_result.returncode != 0:
                raise Exception("flutter pub get failed")

            self._run_prebuild_checks(env, flutter_bin)

            # Build artifact
            self.update_status("Building artifact (this may take 2-10 minutes)...")
            self.log("🔨 Building Android artifact with Flutter...")
            self.log(f"   Server URL: {self.server_url_var.get()}")
            self.log(f"   App Name: {app_name}")
            self.log(f"   Build Mode: {build_mode}")
            self.log(f"   Security: ProGuard + Signature Verification")

            if build_mode == "app_bundle":
                build_cmd = [flutter_bin, "build", "appbundle", "--release", "--no-pub"]
            elif build_mode == "split_apk":
                build_cmd = [
                    flutter_bin,
                    "build",
                    "apk",
                    "--release",
                    "--split-per-abi",
                    "--target-platform=android-arm,android-arm64,android-x64",
                    "--no-pub",
                ]
            else:
                build_cmd = [flutter_bin, "build", "apk", "--release", "--no-pub"]

            result = self.run_command(
                build_cmd,
                cwd=self.flutter_project,
                env=env
            )

            # Auto-retry once with higher heap if Gradle OOM detected.
            if result and result.returncode != 0 and self._command_output_contains("java heap space"):
                self.log("⚠️ Detected Java heap space during build. Retrying with higher Gradle heap...")
                self._ensure_gradle_memory_config(env, force_high=True)
                self.update_status("Retry build with higher Gradle heap...")
                result = self.run_command(
                    build_cmd,
                    cwd=self.flutter_project,
                    env=env
                )

            if result and result.returncode == 0:
                # Build successful
                self.update_status("Build successful! Copying artifacts...")
                self.log("\n✅ BUILD SUCCESSFUL!")

                output_dir = self.project_root / "apk_builds"
                output_dir.mkdir(exist_ok=True)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                safe_name = re.sub(r'[^a-z0-9_]', '', app_name.replace(" ", "_").lower())
                copied_files = []
                total_size = 0.0
                checksum_files = []

                if build_mode == "app_bundle":
                    bundle_dir = self.flutter_project / "build" / "app" / "outputs" / "bundle" / "release"
                    artifact_files = list(bundle_dir.glob("*.aab"))
                    if not artifact_files:
                        raise FileNotFoundError(f"No AAB files found in {bundle_dir}")
                else:
                    apk_dir = self.flutter_project / "build" / "app" / "outputs" / "apk" / "release"
                    artifact_files = list(apk_dir.glob("*.apk"))
                    if not artifact_files:
                        raise FileNotFoundError(f"No APK files found in {apk_dir}")

                for artifact in artifact_files:
                    arch = "universal"
                    if "arm64-v8a" in artifact.name:
                        arch = "arm64"
                    elif "armeabi-v7a" in artifact.name:
                        arch = "armv7"
                    elif "x86_64" in artifact.name:
                        arch = "x86_64"
                    elif "x86" in artifact.name:
                        arch = "x86"
                    suffix = ".aab" if artifact.suffix.lower() == ".aab" else ".apk"
                    output_file = output_dir / f"{safe_name}_{arch}_{timestamp}{suffix}"
                    if arch == "universal":
                        output_file = output_dir / f"{safe_name}_{timestamp}{suffix}"

                    shutil.copy2(artifact, output_file)
                    size_mb = output_file.stat().st_size / (1024 * 1024)
                    total_size += size_mb
                    copied_files.append((output_file, size_mb, arch))

                    # Generate artifact checksum sidecar file for integrity verification
                    sha256_hex = self._sha256_file(output_file)
                    checksum_path = output_file.with_suffix(output_file.suffix + ".sha256")
                    checksum_path.write_text(
                        f"{sha256_hex}  {output_file.name}\n",
                        encoding="utf-8"
                    )
                    checksum_files.append((checksum_path, sha256_hex))

                self.log(f"\n📦 Generated {len(copied_files)} artifact file(s):")
                for file, size, arch in copied_files:
                    self.log(f"   • {file.name} ({size:.2f} MB) - {arch}")
                self.log(f"🔐 Generated {len(checksum_files)} SHA-256 checksum file(s)")
                for checksum_path, sha256_hex in checksum_files:
                    self.log(f"   • {checksum_path.name} ({sha256_hex[:20]}...)")

                self.log(f"\n📊 Total Size: {total_size:.2f} MB")
                self.log(f"🌐 Configured Server: {self.server_url_var.get()}")
                self.log(f"🎫 Build Token: {self.last_build_token}")
                self.log("\n⚠️  PENTING: Copy token di atas ke Admin Panel untuk aktivasi!")
                self.update_status("✅ Build complete! Artifact saved to apk_builds/")

                # Refresh signature hash from produced artifact (fallback when keystore path isn't configured)
                if copied_files:
                    for artifact_path, _, _ in copied_files:
                        if self._update_signature_from_artifact(artifact_path):
                            break

                # Auto-copy token to clipboard
                self._copy_to_clipboard(self.last_build_token)

                artifact_list = "\n".join([f"  • {f.name} ({s:.1f} MB)" for f, s, _ in copied_files])
                self._show_info(
                    "Build Successful!",
                    f"Artifact Android berhasil dibuat!\n\n"
                    f"Generated Files:\n{artifact_list}\n\n"
                    f"Total Size: {total_size:.2f} MB\n\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"BUILD TOKEN (sudah di-copy):\n"
                    f"{self.last_build_token}\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"Paste token ini di Admin Panel\n"
                    f"untuk aktivasi versi baru."
                )
            else:
                raise Exception("Build failed - check console output")

        except Exception as e:
            self.log(f"\n❌ BUILD FAILED: {str(e)}")
            self.update_status("❌ Build failed!")
            self._show_error("Build Failed", f"Build gagal:\n{str(e)}")

        finally:
            self.reset_ui()

    def _run_prebuild_checks(self, env, flutter_bin: str):
        """Run optional pre-build checks to reduce build-time surprises."""
        ran_any_check = False

        if self.preflight_analyze_var.get():
            ran_any_check = True
            self.update_status("Pre-build check: flutter analyze...")
            self.log("🧪 Pre-build check #1: flutter analyze (errors only)")
            analyze_cmd = [
                flutter_bin,
                "analyze",
                "--no-pub",
                "--no-fatal-infos",
                "--no-fatal-warnings",
            ]
            analyze_result = self.run_command(analyze_cmd, cwd=self.flutter_project, env=env)
            if not analyze_result or analyze_result.returncode != 0:
                raise Exception("Pre-build check gagal: flutter analyze menemukan error sintaks/static")

        if self.preflight_test_var.get():
            ran_any_check = True
            self.update_status("Pre-build check: flutter test...")
            self.log("🧪 Pre-build check #2: flutter test (compact)")
            test_cmd = [flutter_bin, "test", "--no-pub", "--reporter", "compact"]
            test_result = self.run_command(test_cmd, cwd=self.flutter_project, env=env)
            if not test_result or test_result.returncode != 0:
                raise Exception("Pre-build check gagal: flutter test tidak lulus")

        if not ran_any_check:
            self.log("ℹ️ Pre-build check dilewati (checkbox dinonaktifkan).")
        else:
            self.log("✅ Pre-build checks passed.")


    def run_command(self, cmd_list, cwd=None, env=None):
        """Run command and log output (secure version without shell=True)"""
        try:
            # Ensure cmd_list is a list
            if isinstance(cmd_list, str):
                # Legacy support: if string passed, split it (but warn)
                self.log(f"⚠️ Warning: Converting string command to list")
                cmd_list = shlex.split(cmd_list)

            self.build_process = subprocess.Popen(
                cmd_list,  # List of arguments (secure)
                cwd=cwd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                shell=False  # Explicitly set to False for security
            )

            self._last_command_output = []

            # Read output line by line
            for line in iter(self.build_process.stdout.readline, ''):
                if line:
                    cleaned_line = line.rstrip()
                    self._last_command_output.append(cleaned_line)
                    if len(self._last_command_output) > 5000:
                        self._last_command_output = self._last_command_output[-3000:]
                    self.log(cleaned_line)

            if self.build_process:
                self.build_process.wait()
            return self.build_process

        except FileNotFoundError as e:
            self.log(f"❌ Command not found: {e}")
            return None
        except subprocess.SubprocessError as e:
            self.log(f"❌ Process error: {e}")
            return None
        except Exception as e:
            self.log(f"❌ Unexpected error: {str(e)}")
            return None

    def log(self, message):
        """Log message to console"""
        def _log():
            self.console.insert(tk.END, message + "\n")
            self.console.see(tk.END)
            self.console.update()

        if threading.current_thread() is threading.main_thread():
            _log()
        else:
            self.root.after(0, _log)

    def update_status(self, message):
        """Update status label"""
        def _update():
            self.status_label.config(text=message)

        if threading.current_thread() is threading.main_thread():
            _update()
        else:
            self.root.after(0, _update)

    def reset_ui(self):
        """Reset UI to ready state"""
        def _reset():
            self.progress.stop()
            self.build_btn.config(state=tk.NORMAL)
            self.save_btn.config(state=tk.NORMAL)
            self.stop_btn.config(state=tk.DISABLED)
            self.build_process = None

        self.root.after(0, _reset)

def _reexec_with_project_venv_if_icon_deps_missing():
    """Use project venv when system Python lacks Pillow for icon processing."""
    if PIL_AVAILABLE:
        return

    project_root = TOOLS_DIR.parent
    venv_python = project_root / ".venv" / "bin" / "python"
    if not venv_python.exists():
        return

    current_python = Path(sys.executable).resolve()
    if current_python == venv_python.resolve():
        return

    probe = subprocess.run(
        [str(venv_python), "-c", "from PIL import Image"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if probe.returncode != 0:
        return

    os.execv(
        str(venv_python),
        [str(venv_python), str(Path(__file__).resolve()), *sys.argv[1:]],
    )


def main():
    """Main entry point"""
    _reexec_with_project_venv_if_icon_deps_missing()
    root = tk.Tk()

    # Set icon if available
    try:
        root.iconbitmap(default='')
    except:
        pass

    app = APKBuilderGUI(root)

    # Center window
    root.update_idletasks()
    x = (root.winfo_screenwidth() // 2) - (1024 // 2)
    y = (root.winfo_screenheight() // 2) - (860 // 2)
    root.geometry(f"+{x}+{y}")

    root.mainloop()

if __name__ == "__main__":
    main()
