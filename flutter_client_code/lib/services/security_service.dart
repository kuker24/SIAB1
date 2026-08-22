import 'package:flutter_jailbreak_detection/flutter_jailbreak_detection.dart';
import 'package:flutter/services.dart';
import 'package:flutter/foundation.dart';
import 'dart:io';
import 'dart:async';
import 'signature_verifier.dart';

/// Enhanced Security Service for Secure Exam Browser
/// Comprehensive anti-cheat and security features
class SecurityService {
  static const _kioskChannel = MethodChannel('com.example.sxb_client/kiosk');

  // Singleton pattern
  static final SecurityService _instance = SecurityService._internal();
  factory SecurityService() => _instance;
  SecurityService._internal();

  bool _kioskActive = false;
  bool _isSecure = true;
  Timer? _securityCheckTimer;
  Timer? _signatureCheckTimer;
  Timer? _antiCheatTimer;
  Function(String)? onSecurityViolation;

  // Signature verification tracking
  int _signatureFailures = 0;
  static const int _maxSignatureFailures = 3;

  bool get isKioskActive => _kioskActive;
  bool get isDeviceSecure => _isSecure;

  /// Initialize security features.
  ///
  /// The optional flags keep compatibility with ExamPage, which initializes
  /// lightweight hooks first and starts heavy runtime checks only after an exam
  /// session begins. Defaults preserve the older eager behavior.
  Future<void> initialize({
    bool runInitialChecks = true,
    bool startPeriodicChecks = true,
  }) async {
    if (runInitialChecks) {
      await _performSecurityChecks();
    }
    if (startPeriodicChecks) {
      this.startPeriodicChecks();
    }
  }

  /// Dispose security monitoring
  void dispose() {
    stopPeriodicChecks();
    stopAntiCheatMonitoring();
  }

  /// Perform comprehensive security checks
  Future<Map<String, bool>> _performSecurityChecks() async {
    final results = <String, bool>{};

    // Check root/jailbreak
    results['root'] = await _checkRootStatus();

    // Check developer mode
    results['developerMode'] = await _checkDeveloperMode();

    // Check USB debugging
    results['usbDebugging'] = await _checkUsbDebugging();

    // Check signature integrity
    results['signatureInvalid'] = !(await SignatureVerifier.verifySignature());

    // Determine overall security status
    _isSecure = !results.values.any((isViolation) => isViolation);

    return results;
  }

  /// Start periodic security checks.
  /// Optimized for low-end devices: 60-second interval instead of 30.
  void startPeriodicChecks() {
    _securityCheckTimer?.cancel();
    _securityCheckTimer = Timer.periodic(const Duration(seconds: 60), (_) async {
      await _performSecurityChecks();
      if (!_isSecure && onSecurityViolation != null) {
        onSecurityViolation!('Security violation detected');
      }
    });

    // Start random interval signature re-verification
    _startSignatureReVerification();
  }

  void stopPeriodicChecks() {
    _securityCheckTimer?.cancel();
    _securityCheckTimer = null;
    _signatureCheckTimer?.cancel();
    _signatureCheckTimer = null;
  }

  /// Start random interval signature re-verification (Layer 3)
  /// Uses random 30-90 second intervals to prevent predictable bypass
  void _startSignatureReVerification() {
    _signatureCheckTimer?.cancel();

    void scheduleNextCheck() {
      // Random interval between 30-90 seconds
      final randomSeconds = 30 + (DateTime.now().millisecondsSinceEpoch % 61);
      final duration = Duration(seconds: randomSeconds);

      _signatureCheckTimer = Timer(duration, () async {
        final isValid = await SignatureVerifier.forceVerify();

        if (!isValid) {
          _signatureFailures++;
          debugPrint(
            '⚠️ Signature re-verification failed ($_signatureFailures/$_maxSignatureFailures)',
          );

          if (_signatureFailures >= _maxSignatureFailures) {
            // Critical: Multiple failures detected
            if (onSecurityViolation != null) {
              onSecurityViolation!('APK tampering detected');
            }
          }
        } else {
          _signatureFailures = 0; // Reset on success
        }

        // Schedule next check if periodic monitoring is still active.
        if (_signatureCheckTimer != null) {
          scheduleNextCheck();
        }
      });
    }

    // Start first check
    scheduleNextCheck();
  }

  /// Check if device is rooted/jailbroken
  static Future<bool> isDeviceRooted() async {
    try {
      if (Platform.isAndroid || Platform.isIOS) {
        return await FlutterJailbreakDetection.jailbroken;
      }
      return false;
    } catch (e) {
      debugPrint('Root check error: $e');
      return false;
    }
  }

  Future<bool> _checkRootStatus() async {
    try {
      return await FlutterJailbreakDetection.jailbroken;
    } catch (e) {
      return false;
    }
  }

  /// Check if developer mode is enabled
  static Future<bool> isDeveloperModeEnabled() async {
    try {
      return await FlutterJailbreakDetection.developerMode;
    } catch (e) {
      return false;
    }
  }

  Future<bool> _checkDeveloperMode() async {
    try {
      return await FlutterJailbreakDetection.developerMode;
    } catch (e) {
      return false;
    }
  }

  /// Check if USB debugging is enabled (Android)
  Future<bool> _checkUsbDebugging() async {
    // This requires platform channel implementation.
    // Developer-mode detection remains active above; do not claim USB debugging
    // is safe, simply mark this specific signal as unavailable/non-blocking.
    return false;
  }

  /// Comprehensive device security check
  static Future<SecurityCheckResult> performFullSecurityCheck() async {
    final result = SecurityCheckResult();

    try {
      result.isRooted = await isDeviceRooted();
      result.isDeveloperMode = await isDeveloperModeEnabled();
      result.isDebuggerAttached = kDebugMode;
      result.isEmulator = await _checkEmulator();

      // Check app signature for tampering
      result.isSignatureValid = await SignatureVerifier.verifySignature();

      result.isSecure = !result.isRooted &&
          !result.isDeveloperMode &&
          !result.isDebuggerAttached &&
          !result.isEmulator &&
          result.isSignatureValid;
    } catch (e) {
      result.errorMessage = e.toString();
    }

    return result;
  }

  /// Check if running on emulator
  static Future<bool> _checkEmulator() async {
    if (!Platform.isAndroid) return false;

    try {
      // Basic emulator detection hints
      // More sophisticated checks would require platform channels
      return false; // Default to false, real check in native code
    } catch (e) {
      return false;
    }
  }

  /// Start kiosk mode (lock device to this app)
  static Future<bool> startKioskMode() async {
    try {
      final result = await _kioskChannel.invokeMethod('startLockTask');
      SecurityService()._kioskActive = result == true;
      return result == true;
    } on PlatformException catch (e) {
      debugPrint('Failed to start kiosk mode: ${e.message}');
      return false;
    }
  }

  /// Stop kiosk mode
  static Future<bool> stopKioskMode() async {
    try {
      final result = await _kioskChannel.invokeMethod('stopLockTask');
      SecurityService()._kioskActive = false;
      return result == true;
    } on PlatformException catch (e) {
      debugPrint('Failed to stop kiosk mode: ${e.message}');
      return false;
    }
  }

  /// Check if kiosk mode is active
  static Future<bool> isKioskModeActive() async {
    try {
      final result = await _kioskChannel.invokeMethod('isKioskMode');
      return result == true;
    } catch (e) {
      return SecurityService()._kioskActive;
    }
  }

  /// Clear current clipboard contents when an exam starts.
  static Future<void> disableClipboard() async {
    try {
      await Clipboard.setData(const ClipboardData(text: ''));
    } catch (e) {
      debugPrint('Failed to clear clipboard: $e');
    }
  }

  /// Compatibility hook for restoring clipboard behavior after exam exit.
  /// Flutter cannot re-enable a platform clipboard permission it never disabled,
  /// so this intentionally performs no privileged action.
  static Future<void> enableClipboard() async {
    return;
  }

  /// Check keyboard risk. Platform-channel keyboard identification is not yet
  /// available, so unknown keyboards are reported as non-blocking unknown—not
  /// as verified safe. ExamPage only warns for dangerous keyboards.
  static Future<KeyboardSecurityResult> checkKeyboardSecurity() async {
    return KeyboardSecurityResult(
      level: 1,
      isDangerous: false,
      message: 'Keyboard tidak dapat diverifikasi otomatis di perangkat ini.',
    );
  }

  /// JavaScript hardening injected into the WebView during exams.
  static String getJsToDisableAutocomplete() {
    return r'''
      try {
        document.querySelectorAll('input, textarea').forEach(function (el) {
          el.setAttribute('autocomplete', 'off');
          el.setAttribute('autocorrect', 'off');
          el.setAttribute('autocapitalize', 'off');
          el.setAttribute('spellcheck', 'false');
        });
        document.addEventListener('copy', function (event) { event.preventDefault(); }, true);
        document.addEventListener('cut', function (event) { event.preventDefault(); }, true);
        document.addEventListener('paste', function (event) { event.preventDefault(); }, true);
        document.addEventListener('contextmenu', function (event) { event.preventDefault(); }, true);
      } catch (_) {}
    ''';
  }

  /// Start additional anti-cheat monitoring while an exam is active.
  /// This complements screenshot/kiosk/native guards in MainActivity and keeps
  /// root/developer/signature checks active without weakening existing flows.
  void startAntiCheatMonitoring({
    required void Function(String message) onViolation,
  }) {
    _antiCheatTimer?.cancel();
    _antiCheatTimer = Timer.periodic(const Duration(seconds: 45), (_) async {
      final check = await performFullSecurityCheck();
      if (!check.isSecure) {
        final details = check.violations.isEmpty
            ? 'Security violation detected'
            : check.violations.join(', ');
        onViolation(details);
      }
    });
  }

  void stopAntiCheatMonitoring() {
    _antiCheatTimer?.cancel();
    _antiCheatTimer = null;
  }

  /// Set immersive mode (hide system UI)
  static Future<void> setImmersiveMode() async {
    await SystemChrome.setEnabledSystemUIMode(
      SystemUiMode.immersiveSticky,
      overlays: [],
    );
  }

  /// Restore system UI
  static Future<void> restoreSystemUI() async {
    await SystemChrome.setEnabledSystemUIMode(
      SystemUiMode.edgeToEdge,
      overlays: SystemUiOverlay.values,
    );
  }

  /// Lock orientation to landscape
  static Future<void> lockLandscape() async {
    await SystemChrome.setPreferredOrientations([
      DeviceOrientation.landscapeLeft,
      DeviceOrientation.landscapeRight,
    ]);
  }

  /// Lock orientation to portrait
  static Future<void> lockPortrait() async {
    await SystemChrome.setPreferredOrientations([
      DeviceOrientation.portraitUp,
      DeviceOrientation.portraitDown,
    ]);
  }

  /// Allow all orientations
  static Future<void> unlockOrientation() async {
    await SystemChrome.setPreferredOrientations(DeviceOrientation.values);
  }

  /// Get security status summary
  static Future<Map<String, dynamic>> getSecurityStatus() async {
    final check = await performFullSecurityCheck();
    return {
      'secure': check.isSecure,
      'rooted': check.isRooted,
      'developer_mode': check.isDeveloperMode,
      'debugger': check.isDebuggerAttached,
      'emulator': check.isEmulator,
      'kiosk_active': SecurityService()._kioskActive,
    };
  }
}

/// Result of keyboard security check.
class KeyboardSecurityResult {
  final int level;
  final bool isDangerous;
  final String message;

  const KeyboardSecurityResult({
    required this.level,
    required this.isDangerous,
    required this.message,
  });
}

/// Result of security check
class SecurityCheckResult {
  bool isSecure = true;
  bool isRooted = false;
  bool isDeveloperMode = false;
  bool isDebuggerAttached = false;
  bool isEmulator = false;
  bool isSignatureValid = true;
  String? errorMessage;

  List<String> get violations {
    final list = <String>[];
    if (isRooted) list.add('Perangkat di-root/jailbreak');
    if (isDeveloperMode) list.add('Mode developer aktif');
    if (isDebuggerAttached) list.add('Debugger terdeteksi');
    if (isEmulator) list.add('Berjalan di emulator');
    if (!isSignatureValid) list.add('APK telah dimodifikasi');
    return list;
  }

  String get summary {
    if (isSecure) return 'Perangkat aman';
    return 'Terdeteksi ${violations.length} masalah keamanan';
  }
}
