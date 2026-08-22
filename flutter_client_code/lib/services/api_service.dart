import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';
import 'package:crypto/crypto.dart';
import 'package:package_info_plus/package_info_plus.dart';
import '../config.dart'; // Import hardcoded config
import 'signature_verifier.dart'; // NEW: For sending signature

/// API Service for Secure Exam Browser
/// Handles all communication with the exam server
class ApiService {
  static final ApiService _instance = ApiService._internal();
  factory ApiService() => _instance;

  late Dio _dio;
  final FlutterSecureStorage _storage = const FlutterSecureStorage();

  String? _serverUrl;
  String? _configKey;
  String? _cachedSignature;
  DateTime? _signatureCachedAt;
  PackageInfo? _cachedPackageInfo;
  static const Duration _signatureCacheTtl = Duration(minutes: 10);
  static const String _violationQueueKey = 'sxb_violation_queue_v1';
  bool _isFlushingViolationQueue = false;
  Map<String, dynamic>? _cachedRuntimePolicy;
  DateTime? _runtimePolicyCachedAt;
  int _lastRetryAfterSeconds = 0;
  static const Duration _runtimePolicyCacheTtl = Duration(minutes: 2);

  ApiService._internal() {
    _dio = Dio(
      BaseOptions(
        connectTimeout: const Duration(seconds: 12),
        receiveTimeout: const Duration(seconds: 15),
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json',
        },
      ),
    );

    // Add interceptor for logging, error handling, and security headers
    _dio.interceptors.add(
      InterceptorsWrapper(
        onRequest: (options, handler) async {
          // Add SEB headers to all requests
          if (_configKey != null) {
            options.headers['X-SafeExamBrowser-ConfigKeyHash'] =
                _generateConfigKeyHash(_configKey!);
          }
          options.headers['User-Agent'] =
              'Mozilla/5.0 (Linux; Android) AppleWebKit/537.36 SEB/3.5 Exambro/1.0';
          options.headers['X-Build-Token'] = AppConfig.buildToken;

          // NEW: Add app signature for server-side validation
          if (Platform.isAndroid) {
            try {
              final signature = await _getCachedSignature();
              if (signature != null) {
                options.headers['X-App-Signature'] = signature;
              }

              // Add timestamp for replay protection (Required by SXB Enforcer)
              options.headers['X-App-Timestamp'] =
                  (DateTime.now().millisecondsSinceEpoch ~/ 1000).toString();

              // Add app version info
              final packageInfo = await _getCachedPackageInfo();
              if (packageInfo != null) {
                options.headers['X-App-Version'] = packageInfo.version;
                options.headers['X-App-Build'] = packageInfo.buildNumber;
              }
            } catch (e) {
              debugPrint('Failed to add signature headers: $e');
            }
          }

          handler.next(options);
        },
        onError: (error, handler) {
          debugPrint('API Error: ${error.message}');
          handler.next(error);
        },
      ),
    );
  }

  String _normalizeBaseUrl(String raw) {
    var value = raw.trim();
    if (value.endsWith('/')) {
      value = value.substring(0, value.length - 1);
    }
    if (value.endsWith('/student')) {
      value = value.substring(0, value.length - 8);
    }
    if (AppConfig.forceHttps && value.startsWith('http://')) {
      value = value.replaceFirst('http://', 'https://');
    }
    return value;
  }

  Future<String?> _getCachedSignature() async {
    if (!Platform.isAndroid) {
      return null;
    }
    final now = DateTime.now();
    if (_cachedSignature != null &&
        _signatureCachedAt != null &&
        now.difference(_signatureCachedAt!) < _signatureCacheTtl) {
      return _cachedSignature;
    }

    // Some devices may return transient platform-channel errors; retry briefly.
    for (int attempt = 0; attempt < 2; attempt++) {
      final sig = await SignatureVerifier.getActualSignature();
      final normalizedSig = SignatureVerifier.normalizeSignatureForHeader(sig);
      if (normalizedSig != null) {
        _cachedSignature = normalizedSig;
        _signatureCachedAt = now;
        return normalizedSig;
      }
      if (attempt == 0) {
        await Future.delayed(const Duration(milliseconds: 150));
      }
    }
    return null;
  }

  Future<PackageInfo?> _getCachedPackageInfo() async {
    if (_cachedPackageInfo != null) {
      return _cachedPackageInfo;
    }
    try {
      _cachedPackageInfo = await PackageInfo.fromPlatform();
      return _cachedPackageInfo;
    } catch (_) {
      return null;
    }
  }

  /// Initialize API service with server URL
  Future<void> initialize(String serverUrl, {String? configKey}) async {
    _serverUrl = _normalizeBaseUrl(serverUrl);
    _configKey = configKey;

    // Store server URL for persistence
    await _storage.write(key: 'server_url', value: _serverUrl);
    if (configKey != null) {
      await _storage.write(key: 'config_key', value: configKey);
    }
  }

  /// Load saved configuration - ALWAYS uses AppConfig.serverUrl as source of truth
  /// This ensures new builds use the correct server URL from config.dart
  Future<bool> loadSavedConfig() async {
    // Load config key from storage (this is dynamic and should be cached)
    _configKey = await _storage.read(key: 'config_key');

    // ALWAYS use hardcoded URL from build config (config.dart)
    // This ensures each new build uses the correct server!
    _serverUrl = _normalizeBaseUrl(AppConfig.serverUrl);

    debugPrint('Server URL from config.dart: $_serverUrl');

    return _serverUrl != null && _serverUrl!.isNotEmpty;
  }

  /// Clear saved configuration
  Future<void> clearConfig() async {
    await _storage.deleteAll();
    _serverUrl = null;
    _configKey = null;
  }

  String get serverUrl => _serverUrl ?? '';
  bool get isConfigured => _serverUrl != null && _serverUrl!.isNotEmpty;

  /// Prepare APK trust context before native login/WebView boot.
  ///
  /// Native login is strict on production for student/guruplus accounts, so the
  /// app should have build token, app signature, timestamp, and package info
  /// ready before the user submits credentials. Android signature reads can be
  /// transiently slow on some devices, so retry briefly without weakening server
  /// validation.
  Future<bool> prepareSecurityContext({int attempts = 3}) async {
    if (!Platform.isAndroid) {
      return true;
    }

    for (var attempt = 0; attempt < attempts; attempt++) {
      try {
        final signature = await _getCachedSignature();
        await _getCachedPackageInfo();
        if (signature != null && signature.isNotEmpty) {
          return true;
        }
      } catch (e) {
        debugPrint('prepareSecurityContext attempt ${attempt + 1} failed: $e');
      }

      if (attempt < attempts - 1) {
        await Future.delayed(Duration(milliseconds: 180 * (attempt + 1)));
      }
    }

    return false;
  }

  Map<String, dynamic> get fallbackRuntimePolicy => const {
        'mode': 'normal',
        'answer_sync_interval_seconds': 15,
        'answer_sync_batch_size': 30,
        'command_poll_seconds': 25,
        'violation_flush_seconds': 30,
        'retry_after_seconds': 8,
        'cheating_detection_enabled': true,
        'cheating_detail_level': 'aggregate',
        'cheating_reporting_mode': 'normal',
        'disabled_violation_types': <String>[],
        'critical_violation_types': <String>[
          'violation_apk_tampering',
          'violation_screenshot_attempt',
          'violation_screen_recording',
          'violation_external_display',
          'violation_devtools_open',
          'violation_copy',
          'violation_paste',
          'violation_clipboard_violation',
        ],
        'force_submit_on_violation_enabled': true,
        'final_submit_priority': true,
      };

  bool _isRetryableStatus(int? statusCode) {
    return statusCode == 429 ||
        statusCode == 502 ||
        statusCode == 503 ||
        statusCode == 504;
  }

  bool isRetryableDioError(DioException error) {
    return _isRetryableStatus(error.response?.statusCode) ||
        error.type == DioExceptionType.connectionTimeout ||
        error.type == DioExceptionType.sendTimeout ||
        error.type == DioExceptionType.receiveTimeout ||
        error.type == DioExceptionType.connectionError ||
        error.type == DioExceptionType.unknown;
  }

  int retryAfterSecondsFromResponse(Response<dynamic>? response) {
    final headerValue = response?.headers.value('Retry-After');
    if (headerValue == null || headerValue.trim().isEmpty) return 0;
    final parsed = int.tryParse(headerValue.trim());
    if (parsed != null && parsed > 0) return parsed;
    return 0;
  }

  Duration computeBackoffDelay({
    required int failureStreak,
    int? retryAfterSeconds,
    int? baseRetryAfterSeconds,
    int maxSeconds = 60,
  }) {
    final baseSeconds = retryAfterSeconds != null && retryAfterSeconds > 0
        ? retryAfterSeconds
        : (baseRetryAfterSeconds != null && baseRetryAfterSeconds > 0
            ? baseRetryAfterSeconds
            : 8);
    final streak = failureStreak < 0 ? 0 : failureStreak;
    final multiplier = 1 << (streak > 6 ? 6 : streak);
    final cappedSeconds = min(baseSeconds * multiplier, maxSeconds);
    final jitterRatio = 0.2 + (Random().nextDouble() * 0.2);
    final jitterMs = (cappedSeconds * 1000 * jitterRatio).round();
    return Duration(milliseconds: (cappedSeconds * 1000) + jitterMs);
  }

  int _policyInt(String key, int fallback) {
    final raw = (_cachedRuntimePolicy ?? fallbackRuntimePolicy)[key];
    final parsed = int.tryParse('$raw');
    return parsed != null && parsed > 0 ? parsed : fallback;
  }

  int get runtimeAnswerSyncIntervalSeconds =>
      _policyInt('answer_sync_interval_seconds', 15);

  int get runtimeAnswerSyncBatchSize =>
      _policyInt('answer_sync_batch_size', 30);

  int get runtimeCommandPollSeconds => _policyInt('command_poll_seconds', 25);

  int get runtimeViolationFlushSeconds =>
      _policyInt('violation_flush_seconds', 30);

  String get runtimeCheatingReportingMode {
    final raw = (_cachedRuntimePolicy ??
        fallbackRuntimePolicy)['cheating_reporting_mode'];
    final mode = '$raw'.trim().toLowerCase();
    return mode.isEmpty ? 'normal' : mode;
  }

  bool get runtimeForceSubmitOnViolationEnabled {
    final raw = (_cachedRuntimePolicy ??
        fallbackRuntimePolicy)['force_submit_on_violation_enabled'];
    if (raw is bool) return raw;
    return '$raw'.trim().toLowerCase() != 'false';
  }

  Set<String> get runtimeDisabledViolationTypes {
    final raw = (_cachedRuntimePolicy ??
        fallbackRuntimePolicy)['disabled_violation_types'];
    if (raw is! List) return <String>{};
    return raw
        .map((item) => _normalizeViolationEventType('$item'))
        .where((item) => item.trim().isNotEmpty)
        .toSet();
  }

  bool isViolationReportingTemporarilyDisabled(String rawType) {
    final normalized = _normalizeViolationEventType(rawType);
    return runtimeDisabledViolationTypes.contains(normalized);
  }

  int get runtimeRetryAfterSeconds => _policyInt('retry_after_seconds', 8);

  int get lastRetryAfterSeconds => _lastRetryAfterSeconds;

  Future<Map<String, dynamic>> getRuntimePolicy(
      {bool forceRefresh = false}) async {
    final now = DateTime.now();
    if (!forceRefresh &&
        _cachedRuntimePolicy != null &&
        _runtimePolicyCachedAt != null &&
        now.difference(_runtimePolicyCachedAt!) < _runtimePolicyCacheTtl) {
      return Map<String, dynamic>.from(_cachedRuntimePolicy!);
    }

    try {
      final response = await _dio.get(
        '$_serverUrl/api/runtime/policy',
        options: Options(
          receiveTimeout: const Duration(seconds: 5),
          validateStatus: (status) => status != null && status < 500,
        ),
      );
      if (response.statusCode == 200 && response.data is Map) {
        _cachedRuntimePolicy = Map<String, dynamic>.from(response.data as Map);
        _runtimePolicyCachedAt = now;
        return Map<String, dynamic>.from(_cachedRuntimePolicy!);
      }
      debugPrint('⚠️ Runtime policy failed: status=${response.statusCode}');
    } catch (e) {
      debugPrint('Runtime policy fetch failed, using fallback: $e');
    }

    _cachedRuntimePolicy = Map<String, dynamic>.from(fallbackRuntimePolicy);
    _runtimePolicyCachedAt = now;
    return Map<String, dynamic>.from(_cachedRuntimePolicy!);
  }

  /// Get SEB configuration info from server
  Future<Map<String, dynamic>?> getConfigInfo() async {
    try {
      final response = await _dio.get('$_serverUrl/api/seb/info');
      return response.data as Map<String, dynamic>;
    } catch (e) {
      debugPrint('Failed to get config info: $e');
      return null;
    }
  }

  /// Verify server connectivity - checks if server is reachable
  Future<bool> verifyConnection({
    Duration timeout = const Duration(seconds: 6),
  }) async {
    try {
      // Prefer health endpoint for a lightweight and deterministic connectivity check.
      final response = await _dio.get(
        '$_serverUrl/health',
        options: Options(
          sendTimeout: timeout,
          receiveTimeout: timeout,
          followRedirects: true,
          validateStatus: (status) =>
              status != null && status < 500, // Accept any non-server-error
        ),
      );
      // Any response (200, 302, 401, 403, etc.) means server is up
      return response.statusCode != null && response.statusCode! < 500;
    } catch (e) {
      debugPrint('Connection check failed: $e');
      return false;
    }
  }

  Future<List<Map<String, dynamic>>> _readViolationQueue() async {
    try {
      final raw = await _storage.read(key: _violationQueueKey);
      if (raw == null || raw.isEmpty) return <Map<String, dynamic>>[];
      final decoded = jsonDecode(raw);
      if (decoded is! List) return <Map<String, dynamic>>[];

      final queue = <Map<String, dynamic>>[];
      for (final item in decoded) {
        if (item is Map) {
          queue.add(Map<String, dynamic>.from(item));
        }
      }
      return queue;
    } catch (_) {
      return <Map<String, dynamic>>[];
    }
  }

  Future<void> _writeViolationQueue(List<Map<String, dynamic>> queue) async {
    try {
      await _storage.write(key: _violationQueueKey, value: jsonEncode(queue));
    } catch (e) {
      debugPrint('⚠️ Failed to persist violation queue: $e');
    }
  }

  Future<int> getQueuedViolationCount() async {
    final queue = await _readViolationQueue();
    return queue.length;
  }

  Future<void> _enqueueViolationPayload(Map<String, dynamic> payload) async {
    final queue = await _readViolationQueue();
    final now = DateTime.now().millisecondsSinceEpoch;

    if (queue.isNotEmpty) {
      final last = queue.last;
      final sameSession = last['session_id'] == payload['session_id'];
      final sameType = last['event_type'] == payload['event_type'];
      final lastCount = (last['event_data'] as Map?)?['violation_count'];
      final nextCount = (payload['event_data'] as Map?)?['violation_count'];
      final sameCount = lastCount == nextCount;
      final lastEnqueuedAt = int.tryParse('${last['_queued_at_ms'] ?? 0}') ?? 0;
      final duplicateBurst = sameSession &&
          sameType &&
          sameCount &&
          (now - lastEnqueuedAt) < 12000;
      if (duplicateBurst) {
        debugPrint('ℹ️ Skipping duplicate violation event burst');
        return;
      }
    }

    payload['_queued_at_ms'] = now;
    queue.add(payload);

    // Keep queue bounded.
    if (queue.length > 500) {
      queue.removeRange(0, queue.length - 500);
    }
    await _writeViolationQueue(queue);
    debugPrint('📥 Violation queued locally (size=${queue.length})');
  }

  Future<bool> _sendViolationPayload({
    required Map<String, dynamic> payload,
    required String token,
    int maxAttempts = 1,
  }) async {
    DioException? lastError;
    Response<dynamic>? response;

    for (int attempt = 1; attempt <= maxAttempts; attempt++) {
      try {
        response = await _dio.post(
          '$_serverUrl/api/exams/log-violation',
          options: Options(
            receiveTimeout: const Duration(seconds: 5),
            headers: {
              'Authorization': 'Bearer $token',
              'Content-Type': 'application/json',
            },
            validateStatus: (status) => status != null && status < 500,
          ),
          data: payload,
        );
        if (response.statusCode == 200 ||
            response.statusCode == 202 ||
            response.statusCode == 204) {
          return true;
        }
        if (!_isRetryableStatus(response.statusCode)) {
          break;
        }
      } on DioException catch (e) {
        lastError = e;
        if (!isRetryableDioError(e)) break;
        if (attempt == maxAttempts) break;
        final delay = computeBackoffDelay(
          failureStreak: attempt - 1,
          retryAfterSeconds: retryAfterSecondsFromResponse(e.response),
          baseRetryAfterSeconds: runtimeRetryAfterSeconds,
        );
        await Future.delayed(delay);
      }
    }

    if (lastError != null) {
      debugPrint(
        '❌ Violation send error: ${lastError.response?.statusCode} - ${lastError.response?.data}',
      );
    } else if (response != null) {
      debugPrint(
        '❌ Violation send rejected: ${response.statusCode} - ${response.data}',
      );
    }
    return false;
  }

  Future<int> flushViolationQueue({String? token}) async {
    if (_isFlushingViolationQueue) return 0;
    _isFlushingViolationQueue = true;

    try {
      final queue = await _readViolationQueue();
      if (queue.isEmpty) return 0;

      final authToken = token ?? await getToken();
      if (authToken == null || authToken.isEmpty) return 0;

      int flushed = 0;
      final remaining = <Map<String, dynamic>>[];

      for (int i = 0; i < queue.length; i++) {
        final payload = queue[i];
        final eventType = '${payload['event_type'] ?? ''}';
        if (isViolationReportingTemporarilyDisabled(eventType)) {
          remaining.add(payload);
          continue;
        }
        final ok = await _sendViolationPayload(
          payload: payload,
          token: authToken,
          maxAttempts: 2,
        );
        if (!ok) {
          remaining.add(payload);
          if (i + 1 < queue.length) {
            remaining.addAll(queue.sublist(i + 1));
          }
          break;
        }
        flushed += 1;
      }

      await _writeViolationQueue(remaining);
      if (flushed > 0) {
        debugPrint(
          '📤 Flushed queued violations: $flushed (remaining=${remaining.length})',
        );
      }
      return flushed;
    } catch (e) {
      debugPrint('⚠️ flushViolationQueue failed: $e');
      return 0;
    } finally {
      _isFlushingViolationQueue = false;
    }
  }

  /// Get student exam URL. This path is the public student portal entry point.
  String getExamUrl() {
    return '$_serverUrl/student/';
  }

  /// Get authenticated student dashboard URL for the APK WebView after native login.
  String getStudentDashboardUrl() {
    return '$_serverUrl/student/dashboard.html';
  }

  /// Get exam URL with auto-login parameters
  String getExamUrlWithAutoLogin(String token, String userData) {
    // Base64 encode user data
    final userB64 = base64Encode(utf8.encode(userData));
    final baseUrl = getExamUrl();
    final tokenParam = Uri.encodeQueryComponent(token);
    final userParam = Uri.encodeQueryComponent(userB64);
    // Use query params for maximum compatibility with server redirects/login page.
    // auth.js still supports hash as fallback for backward compatibility.
    return '$baseUrl?autologin_token=$tokenParam&autologin_user=$userParam';
  }

  /// Get QR code URL
  String getQrCodeUrl({int size = 300}) {
    return '$_serverUrl/api/seb/qr-code?size=$size';
  }

  /// Get SEB headers for manual request (e.g. WebView)
  Map<String, String> getSebHeaders(String url) {
    final headers = <String, String>{
      'User-Agent':
          'Mozilla/5.0 (Linux; Android) AppleWebKit/537.36 SEB/3.5 Exambro/1.0',
      'X-Build-Token': AppConfig.buildToken,
    };

    if (_configKey != null) {
      headers['X-SafeExamBrowser-ConfigKeyHash'] = _generateConfigKeyHash(
        _configKey!,
      );
    }
    if (_cachedSignature != null) {
      headers['X-App-Signature'] = _cachedSignature!;
      headers['X-App-Timestamp'] =
          (DateTime.now().millisecondsSinceEpoch ~/ 1000).toString();
    }

    return headers;
  }

  /// Generate config key hash (SHA256)
  String _generateConfigKeyHash(String configKey) {
    var bytes = utf8.encode(configKey);
    var digest = sha256.convert(bytes);
    return digest.toString();
  }

  /// Log security violation to server
  /// type: 'TAB_SWITCH', 'SCREENSHOT_ATTEMPT', 'APP_EXIT_ATTEMPT', 'SECURITY_WARNING'
  Future<bool> logViolation({
    required String sessionId,
    required String type,
    required int count,
    int? examId,
    String? details,
  }) async {
    try {
      // Get auth token for authenticated request
      final token = await getToken();
      if (token == null) {
        debugPrint('⚠️ logViolation: No auth token available, skipping');
        return false;
      }

      final sessionIdInt = int.tryParse(sessionId) ?? 0;
      if (sessionIdInt == 0) {
        debugPrint('⚠️ logViolation: Invalid session_id=$sessionId, skipping');
        return false;
      }

      final effectiveExamId = examId ?? 0;
      if (effectiveExamId == 0) {
        debugPrint(
          '⚠️ logViolation: exam_id is null/0, broadcast may not reach admin monitor',
        );
      }
      final normalizedEventType = _normalizeViolationEventType(type);
      if (runtimeDisabledViolationTypes.contains(normalizedEventType)) {
        debugPrint(
          '⏸️ Violation reporting temporarily disabled: $normalizedEventType '
          'mode=$runtimeCheatingReportingMode',
        );
        return true;
      }

      debugPrint(
        '📤 Logging violation: type=$type, session=$sessionIdInt, exam=$effectiveExamId, count=$count',
      );

      final payload = <String, dynamic>{
        'session_id': sessionIdInt,
        'exam_id': effectiveExamId,
        'event_type': normalizedEventType,
        'event_data': {
          'violation_count': count,
          'details': details ?? '',
          'source': 'flutter_app',
          'raw_type': type,
        },
        'timestamp': DateTime.now().toIso8601String(),
        'user_agent': 'Flutter Exambro App',
        'screen_resolution': 'mobile',
      };

      final sent = await _sendViolationPayload(payload: payload, token: token);
      if (sent) {
        debugPrint('✅ Violation logged successfully');
        unawaited(flushViolationQueue(token: token));
        return true;
      }

      await _enqueueViolationPayload(payload);
      return true;
    } on DioException catch (e) {
      debugPrint(
        '❌ Failed to log violation: ${e.response?.statusCode} - ${e.response?.data}',
      );
      final sessionIdInt = int.tryParse(sessionId) ?? 0;
      if (sessionIdInt > 0) {
        final normalizedEventType = _normalizeViolationEventType(type);
        await _enqueueViolationPayload({
          'session_id': sessionIdInt,
          'exam_id': examId ?? 0,
          'event_type': normalizedEventType,
          'event_data': {
            'violation_count': count,
            'details': details ?? '',
            'source': 'flutter_app',
            'raw_type': type,
          },
          'timestamp': DateTime.now().toIso8601String(),
          'user_agent': 'Flutter Exambro App',
          'screen_resolution': 'mobile',
        });
        return true;
      }
      return false;
    } catch (e) {
      debugPrint('❌ Failed to log violation: $e');
      return false;
    }
  }

  /// Get token from storage for authenticated requests
  Future<String?> getToken() async {
    return await _storage.read(key: 'auth_token');
  }

  /// Set auth token
  Future<void> setToken(String token) async {
    await _storage.write(key: 'auth_token', value: token);
    _dio.options.headers['Authorization'] = 'Bearer $token';
    unawaited(flushViolationQueue(token: token));
  }

  /// Check session status from server (for admin commands like emergency exit)
  /// Returns null if request fails, otherwise returns session status data
  Future<Map<String, dynamic>?> checkSessionStatus(String sessionId) async {
    try {
      // FIX: Use correct path (singular "session", not plural "sessions")
      // FIX: Include auth token (backend requires get_current_user)
      final token = await getToken();
      final response = await _dio.get(
        '$_serverUrl/api/exams/session/$sessionId/status',
        options: Options(
          receiveTimeout: const Duration(seconds: 5),
          headers: token != null ? {'Authorization': 'Bearer $token'} : null,
          validateStatus: (status) => status != null && status < 500,
        ),
      );

      if (response.statusCode == 200) {
        return response.data as Map<String, dynamic>;
      }
      debugPrint('⚠️ checkSessionStatus: status=${response.statusCode}');
      return null;
    } catch (e) {
      debugPrint('Session status check failed: $e');
      return null;
    }
  }

  /// Fetch signed offline package snapshot for active exam session.
  Future<Map<String, dynamic>?> fetchOfflineExamPackage(
    int sessionId, {
    String? token,
  }) async {
    if (sessionId <= 0) return null;
    try {
      final authToken = token ?? await getToken();
      final response = await _dio.get(
        '$_serverUrl/api/exams/session/$sessionId/offline-package',
        options: Options(
          receiveTimeout: const Duration(seconds: 12),
          headers:
              authToken != null ? {'Authorization': 'Bearer $authToken'} : null,
          validateStatus: (status) => status != null && status < 500,
        ),
      );
      if (response.statusCode == 200 && response.data is Map<String, dynamic>) {
        return response.data as Map<String, dynamic>;
      }
      debugPrint(
        '⚠️ fetchOfflineExamPackage failed: status=${response.statusCode}',
      );
      return null;
    } catch (e) {
      debugPrint('fetchOfflineExamPackage error: $e');
      return null;
    }
  }

  /// Sync append-only answer journal events with idempotent ack.
  Future<Map<String, dynamic>?> syncAnswerJournal({
    required int sessionId,
    required List<Map<String, dynamic>> events,
    String? token,
  }) async {
    if (sessionId <= 0 || events.isEmpty) return null;
    try {
      final authToken = token ?? await getToken();
      if (authToken == null || authToken.isEmpty) return null;

      final response = await _dio.post(
        '$_serverUrl/api/exams/answer-journal/sync',
        options: Options(
          receiveTimeout: const Duration(seconds: 10),
          headers: {
            'Authorization': 'Bearer $authToken',
            'Content-Type': 'application/json',
          },
          validateStatus: (status) => status != null && status < 500,
        ),
        data: {
          'session_id': sessionId,
          'events': events,
        },
      );

      if (response.statusCode == 200 && response.data is Map<String, dynamic>) {
        _lastRetryAfterSeconds = 0;
        return response.data as Map<String, dynamic>;
      }
      _lastRetryAfterSeconds = retryAfterSecondsFromResponse(response);
      debugPrint(
        '⚠️ syncAnswerJournal failed: status=${response.statusCode}, body=${response.data}',
      );
      return null;
    } on DioException catch (e) {
      _lastRetryAfterSeconds = retryAfterSecondsFromResponse(e.response);
      debugPrint('syncAnswerJournal error: $e');
      return null;
    } catch (e) {
      _lastRetryAfterSeconds = 0;
      debugPrint('syncAnswerJournal error: $e');
      return null;
    }
  }

  /// Fetch precise timer info for timer integrity checks.
  Future<Map<String, dynamic>?> getRemainingTimeSnapshot(int sessionId) async {
    if (sessionId <= 0) return null;
    try {
      final token = await getToken();
      final response = await _dio.get(
        '$_serverUrl/api/exams/session/$sessionId/remaining-time',
        options: Options(
          receiveTimeout: const Duration(seconds: 6),
          headers: token != null ? {'Authorization': 'Bearer $token'} : null,
          validateStatus: (status) => status != null && status < 500,
        ),
      );
      if (response.statusCode == 200 && response.data is Map<String, dynamic>) {
        return response.data as Map<String, dynamic>;
      }
      return null;
    } catch (e) {
      debugPrint('getRemainingTimeSnapshot error: $e');
      return null;
    }
  }

  /// Fetch resume snapshot after reconnect/restart.
  Future<Map<String, dynamic>?> getResumeSnapshot(int sessionId) async {
    if (sessionId <= 0) return null;
    try {
      final token = await getToken();
      final response = await _dio.get(
        '$_serverUrl/api/exams/session/$sessionId/resume',
        options: Options(
          receiveTimeout: const Duration(seconds: 8),
          headers: token != null ? {'Authorization': 'Bearer $token'} : null,
          validateStatus: (status) => status != null && status < 500,
        ),
      );
      if (response.statusCode == 200 && response.data is Map<String, dynamic>) {
        return response.data as Map<String, dynamic>;
      }
      return null;
    } catch (e) {
      debugPrint('getResumeSnapshot error: $e');
      return null;
    }
  }

  /// Login with username and password
  /// Returns map with success status and message/data
  /// If captcha is required, pass captcha_id and captcha_answer
  Future<Map<String, dynamic>> login(
    String username,
    String password, {
    String? captchaId,
    String? captchaAnswer,
  }) async {
    try {
      final Map<String, dynamic> payload = {
        'username': username,
        'password': password,
      };

      // Add CAPTCHA data if provided
      if (captchaId != null && captchaAnswer != null) {
        payload['captcha_id'] = captchaId;
        payload['captcha_answer'] = captchaAnswer;
      }

      final response = await _dio.post(
        '$_serverUrl/api/auth/signin',
        data: payload,
      );

      if (response.statusCode == 200) {
        final data = response.data;
        final token = data['access_token'];
        final user = data['user'];

        if (token != null) {
          final role = user is Map ? user['role']?.toString() : null;
          if (role != 'student' && role != 'guruplus') {
            return {
              'success': false,
              'message': 'Portal APK ini khusus untuk peserta ujian',
            };
          }

          // Save token and user data
          await setToken(token);
          await _storage.write(key: 'user_data', value: jsonEncode(user));
          return {'success': true, 'data': data};
        }
      }
      return {'success': false, 'message': 'Login gagal: Respon tidak valid'};
    } on DioException catch (e) {
      String message = 'Terjadi kesalahan koneksi';

      if (e.response != null) {
        final statusCode = e.response?.statusCode;
        final responseData = e.response?.data;
        final detail =
            responseData is Map ? responseData['detail'] : responseData;

        // Handle 428 - CAPTCHA Required
        if (statusCode == 428) {
          if (detail is Map) {
            return {
              'success': false,
              'captcha_required': true,
              'captcha_id': detail['challenge_id'],
              'captcha_question': detail['question'],
              'message': detail['message'] ?? 'CAPTCHA diperlukan',
            };
          }
        }
        // Handle 403 - Access Denied
        else if (statusCode == 403) {
          message = 'Akses Ditolak: ${detail ?? 'Signature Invalid'}';
        }
        // Handle 401 - Auth Failed
        else if (statusCode == 401) {
          if (detail is Map) {
            // Check if CAPTCHA is needed
            if (detail['type'] == 'captcha_required' ||
                detail['type'] == 'captcha_wrong') {
              return {
                'success': false,
                'captcha_required': true,
                'captcha_id': detail['challenge_id'],
                'captcha_question': detail['question'],
                'message':
                    detail['message'] ?? 'Jawaban CAPTCHA salah, coba lagi',
              };
            }
            message =
                detail['message']?.toString() ?? 'Username atau password salah';
          } else {
            message = detail?.toString() ?? 'Username atau password salah';
          }
        } else {
          message = detail is Map
              ? detail['message']?.toString() ?? 'Terjadi kesalahan server'
              : detail?.toString() ?? 'Terjadi kesalahan server';
        }
      }
      return {'success': false, 'message': message};
    } catch (e) {
      return {'success': false, 'message': 'Error: $e'};
    }
  }

  /// Logout
  Future<void> logout() async {
    await _storage.delete(key: 'auth_token');
    await _storage.delete(key: 'user_data');
    _dio.options.headers.remove('Authorization');
  }

  /// Get stored user data for WebView injection
  Future<String?> getStoredUserData() async {
    return await _storage.read(key: 'user_data');
  }

  String _normalizeViolationEventType(String rawType) {
    final normalizedRaw = rawType.trim().toLowerCase().replaceAll(' ', '_');
    final base = normalizedRaw.startsWith('violation_')
        ? normalizedRaw.substring('violation_'.length)
        : normalizedRaw;

    // Keep backend metadata/dashboard stable for soft signals and outage exits.
    final canonical = switch (base) {
      'tab_switch_minor' => 'tab_switch',
      'emergency_exit_offline' => 'security_warning',
      _ => base,
    };

    return 'violation_$canonical';
  }

  /// Validate build token against server's minimum required token
  /// Returns a map with 'valid' boolean and optional 'message'
  Future<Map<String, dynamic>> validateBuildToken() async {
    try {
      final response = await _dio.post(
        '$_serverUrl/api/validate-apk-token',
        data: {
          'token': AppConfig.buildToken,
          'timestamp': AppConfig.buildTimestamp,
        },
        options: Options(
          receiveTimeout: const Duration(seconds: 4),
          sendTimeout: const Duration(seconds: 4),
          validateStatus: (status) => status != null && status < 500,
        ),
      );

      if (response.statusCode == 200) {
        final data = response.data as Map<String, dynamic>;
        return {
          'valid': data['valid'] ?? true,
          'message': data['message'] ?? '',
          'update_required': data['update_required'] ?? false,
        };
      }

      // If endpoint doesn't exist, allow app to continue (backward compatibility)
      return {'valid': true, 'message': ''};
    } catch (e) {
      debugPrint('Build token validation failed: $e');
      // On network error, allow app to continue
      return {'valid': true, 'message': ''};
    }
  }
}
