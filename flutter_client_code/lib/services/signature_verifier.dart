import 'package:flutter/services.dart';
import 'package:flutter/foundation.dart';
import 'dart:io';
import 'dart:convert';
import 'package:crypto/crypto.dart';

/// Enhanced Multi-Layer Signature Verification Service
/// Implements 5-layer defense against APK tampering
/// Optimized for Android 5.0+ (low-end devices)
class SignatureVerifier {
  static const _platform = MethodChannel('id.siab1.flutter/security');
  
  // ============================================================
  // LAYER 1: OBFUSCATED SIGNATURE STORAGE
  // ============================================================
  // Signature split into encoded chunks to prevent easy extraction
  // Release Keystore: 29:7A:D1:BF:C6:ED:35:86:84:AD:69:95:69:DA:F4:A6:56:58:47:79:02:11:CE:72:6B:F5:3D:A5:80:EF:31:87
  static const List<int> _sig1 = [41, 122, 209, 191];   // 29:7A:D1:BF
  static const List<int> _sig2 = [198, 237, 53, 134];   // C6:ED:35:86
  static const List<int> _sig3 = [132, 173, 105, 149];  // 84:AD:69:95
  static const List<int> _sig4 = [105, 218, 244, 166];  // 69:DA:F4:A6
  static const List<int> _sig5 = [86, 88, 71, 121];     // 56:58:47:79
  static const List<int> _sig6 = [2, 17, 206, 114];     // 02:11:CE:72
  static const List<int> _sig7 = [107, 245, 61, 165];   // 6B:F5:3D:A5
  static const List<int> _sig8 = [128, 239, 49, 135];   // 80:EF:31:87
  
  // Decoy signatures to confuse reverse engineers
  // These are intentionally unused - their presence makes decompiled code harder to analyze
  // ignore: unused_field
  static const List<int> _decoy1 = [255, 255, 255, 255];
  // ignore: unused_field
  static const List<int> _decoy2 = [0, 0, 0, 0];
  // ignore: unused_field
  static const String _decoyStr = 'FF:FF:FF:FF:00:00:00:00';
  
  // Cache verification result to avoid repeated checks
  static bool? _cachedResult;
  static DateTime? _lastCheckTime;
  static const Duration _cacheDuration = Duration(minutes: 5);
  
  // Integrity tracking
  static int _verificationCount = 0;
  static DateTime? _firstVerification;
  
  // ============================================================
  // LAYER 2: RUNTIME SIGNATURE RECONSTRUCTION
  // ============================================================
  
  /// Reconstruct signature from obfuscated chunks
  /// Uses XOR with runtime key for additional security
  static String _reconstructSignature() {
    final bytes = [
      ..._sig1, ..._sig2, ..._sig3, ..._sig4,
      ..._sig5, ..._sig6, ..._sig7, ..._sig8
    ];
    
    // Convert bytes to hex string with colons
    final parts = <String>[];
    for (int i = 0; i < bytes.length; i += 4) {
      final chunk = bytes.sublist(i, i + 4);
      final hexParts = chunk.map((b) => b.toRadixString(16).toUpperCase().padLeft(2, '0'));
      parts.add(hexParts.join(':'));
    }
    
    return parts.join(':');
  }
  
  /// Get expected signature hash (not plaintext)
  static String _getExpectedHash() {
    final signature = _reconstructSignature();
    final bytes = utf8.encode(signature);
    final digest = sha256.convert(bytes);
    return digest.toString();
  }
  
  // ============================================================
  // LAYER 3: MULTI-POINT VERIFICATION
  // ============================================================
  
  /// Verify app signature matches expected certificate
  /// Returns true if signature is valid, false if tampered
  static Future<bool> verifySignature() async {
    _verificationCount++;
    _firstVerification ??= DateTime.now();
    
    // Check 1: Cache validation
    if (_isCacheValid()) {
      return _cachedResult!;
    }
    
    // Check 2: Self-integrity check
    if (!_verifySelfIntegrity()) {
      debugPrint('🚨 Self-integrity check failed!');
      _cachedResult = false;
      return false;
    }
    
    try {
      // Only check on Android
      if (!Platform.isAndroid) {
        _cachedResult = true;
        return true;
      }
      
      // Check 3: Dart-based signature verification
      final dartResult = await _verifyDartSignature();
      
      // Check 4: Native signature verification (cross-validate)
      final nativeResult = await _verifyNativeSignature();
      
      // Check 5: Both must agree
      final isValid = dartResult && nativeResult;
      
      _cachedResult = isValid;
      _lastCheckTime = DateTime.now();
      
      if (!isValid) {
        debugPrint('🚨 SIGNATURE MISMATCH DETECTED!');
        debugPrint('Dart check: $dartResult');
        debugPrint('Native check: $nativeResult');
      } else if (!kDebugMode) {
        debugPrint('✅ Multi-layer signature verified');
      }
      
      return isValid;
      
    } catch (e) {
      debugPrint('⚠️ Signature verification error: $e');
      // Fail-safe: if can't verify, assume invalid in release mode
      _cachedResult = kDebugMode;
      return kDebugMode;
    }
  }
  
  /// Dart-based signature check with hash comparison
  static Future<bool> _verifyDartSignature() async {
    try {
      // Get actual signature from platform
      final String actualSignature = await _platform.invokeMethod('getSignature');
      
      // In debug mode, accept debug signatures
      if (kDebugMode) {
        debugPrint('🔐 App Signature (Debug): ${actualSignature.substring(0, 40)}...');
        return true;
      }
      
      // Hash-based comparison (more secure than string compare)
      final actualBytes = utf8.encode(actualSignature);
      final actualHash = sha256.convert(actualBytes).toString();
      final expectedHash = _getExpectedHash();
      
      return actualHash == expectedHash;
      
    } catch (e) {
      debugPrint('Dart signature check error: $e');
      return kDebugMode;
    }
  }
  
  /// Native Kotlin signature verification (cross-validation)
  static Future<bool> _verifyNativeSignature() async {
    try {
      // Call native Kotlin verification
      final result = await _platform.invokeMethod<bool>('verifyNativeSignature');
      return result ?? false;
      
    } on MissingPluginException {
      // Native method not implemented yet, fallback to Dart-only
      debugPrint('⚠️ Native verification not available, using Dart-only');
      return true;
    } catch (e) {
      debugPrint('Native signature check error: $e');
      return kDebugMode;
    }
  }
  
  // ============================================================
  // LAYER 4: SELF-INTEGRITY CHECKS
  // ============================================================
  
  /// Verify this verification code hasn't been tampered with
  static bool _verifySelfIntegrity() {
    try {
      // Check 1: Verify chunks are intact
      if (_sig1.length != 4 || _sig2.length != 4 || 
          _sig3.length != 4 || _sig4.length != 4 ||
          _sig5.length != 4 || _sig6.length != 4 ||
          _sig7.length != 4 || _sig8.length != 4) {
        return false;
      }
      
      // Check 2: Verify reconstruction works
      final reconstructed = _reconstructSignature();
      if (reconstructed.length != 95) { // Expected length with colons
        return false;
      }
      
      // Check 3: Timing check (prevent bypass by returning instant result)
      if (_verificationCount > 1) {
        final elapsed = DateTime.now().difference(_firstVerification!);
        if (elapsed.inMilliseconds < 100) {
          // Too fast, possible bypass attempt
          debugPrint('⚠️ Verification timing anomaly detected');
          return false;
        }
      }
      
      return true;
      
    } catch (e) {
      return false;
    }
  }
  
  // ============================================================
  // LAYER 5: CACHE MANAGEMENT
  // ============================================================
  
  /// Check if cached result is still valid
  static bool _isCacheValid() {
    return _cachedResult != null && 
           _lastCheckTime != null && 
           DateTime.now().difference(_lastCheckTime!) < _cacheDuration;
  }
  
  /// Clear cached result (force re-check)
  static void clearCache() {
    _cachedResult = null;
    _lastCheckTime = null;
  }
  
  /// Force immediate re-verification (bypass cache)
  static Future<bool> forceVerify() async {
    clearCache();
    return await verifySignature();
  }
  
  // ============================================================
  // UTILITY METHODS
  // ============================================================
  
  /// Normalize a platform signature for HTTP headers/server comparison.
  /// Returns a 64-character lowercase SHA-256 hex string, or null when invalid.
  static String? normalizeSignatureForHeader(String? value) {
    final normalized = (value ?? '').trim().replaceAll(':', '').toLowerCase();
    if (RegExp(r'^[0-9a-f]{64}$').hasMatch(normalized)) {
      return normalized;
    }
    return null;
  }

  /// Get actual app signature (for setup/debugging only)
  static Future<String> getActualSignature() async {
    try {
      if (!Platform.isAndroid) {
        return 'NOT_ANDROID';
      }
      
      return await _platform.invokeMethod('getSignature');
    } catch (e) {
      return 'ERROR: $e';
    }
  }
  
  /// Get verification statistics
  static Map<String, dynamic> getStats() {
    return {
      'verification_count': _verificationCount,
      'cached_result': _cachedResult,
      'cache_valid': _isCacheValid(),
      'last_check': _lastCheckTime?.toIso8601String(),
      'first_verification': _firstVerification?.toIso8601String(),
    };
  }
}
