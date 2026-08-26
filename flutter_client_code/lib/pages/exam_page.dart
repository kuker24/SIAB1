import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_inappwebview/flutter_inappwebview.dart';
import 'dart:async';
import 'dart:collection'; // Added for UnmodifiableListView
import 'dart:convert';
import '../services/security_service.dart';
import '../services/api_service.dart';
import '../services/exam_resilience_service.dart';
import '../services/signature_verifier.dart';
import '../security/trusted_origin.dart';
import '../config.dart';
import '../widgets/common_widgets.dart';
import 'session_ended_page.dart';
import 'package:screenshot_callback/screenshot_callback.dart';

enum _ConnectionStateUi { online, degraded, offline }

/// Enhanced Exam Page with comprehensive security
class ExamPage extends StatefulWidget {
  final String examUrl;

  const ExamPage({super.key, required this.examUrl});

  @override
  State<ExamPage> createState() => _ExamPageState();
}

class _ExamPageState extends State<ExamPage> with WidgetsBindingObserver {
  InAppWebViewController? _webViewController;
  bool _isLoading = true;
  double _loadingProgress = 0;
  String? _errorMessage;
  bool _kioskActive = false;
  bool _showSecurityWarning = false;
  final String _securityWarningMessage = '';

  // Tab switch detection
  int _tabSwitchCount = 0;
  DateTime? _lastBackgroundTime;

  // Screenshot detection
  final ScreenshotCallback _screenshotCallback = ScreenshotCallback();
  int _screenshotCount = 0;

  // Session tracking for violation logging
  String? _currentSessionId;
  int? _currentExamId;
  bool _examSubmitted = false;

  // Server command polling timer
  Timer? _serverCommandTimer;
  bool _emergencyExitTriggered = false;

  // UI state to prevent frozen dialogs
  bool _isDialogShowing = false;

  // Debounce timer for screen lock handling - FIX for stuck pop-up
  Timer? _violationDebounceTimer;
  DateTime? _lastResumeTime;
  Timer? _mainFrameRetryTimer;
  int _mainFrameRetryCount = 0;
  bool _retryInProgress = false;
  Timer? _serverReconnectTimer;
  Timer? _answerJournalSyncTimer;
  bool _serverReconnectProbeInFlight = false;
  DateTime? _serverOutageStartedAt;
  int _serverOutageProbeFailures = 0;
  bool _allowEmergencyExit = false;
  String _lastOutageReason = 'Koneksi ke server ujian terputus';
  bool _needsMainFrameReloadAfterReconnect = false;
  int _queuedViolationCount = 0;
  int _queuedAnswerEventCount = 0;
  int _currentQuestionIndex = 0;
  int _lastKnownTimeRemainingSeconds = 0;
  int? _lastServerTimeEpochMs;
  int _answerJournalSyncSeconds = 15;
  int _answerJournalBatchSize = 30;
  int _commandPollSeconds = 25;

  // Smart violation/risk scoring (reduce false-positive, prioritize real cheating)
  final List<Map<String, dynamic>> _riskEvents = [];
  double _violationRiskScore = 0.0;
  DateTime? _lastTabViolationAt;
  DateTime? _lastScreenshotViolationAt;
  final Map<String, DateTime> _lastSecurityViolationAt = {};

  final SecurityService _securityService = SecurityService();
  final ApiService _apiService = ApiService();
  final ExamResilienceService _resilienceService = ExamResilienceService();

  // Auth injection script
  UserScript? _authScript;
  bool _authPrepared = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _initSecurity();
    _prepareAuthScript();
    unawaited(_refreshQueueIndicators());
  }

  Future<void> _prepareAuthScript() async {
    final token = await _apiService.getToken();
    final userData = await _apiService.getStoredUserData();
    final trustedOrigin = trustedWebOrigin(_apiService.serverUrl);
    String? appSignature;

    if (trustedOrigin == null ||
        !isTrustedWebOrigin(widget.examUrl, _apiService.serverUrl)) {
      if (mounted) {
        setState(() {
          _errorMessage = 'Origin server ujian tidak valid';
        });
      }
      return;
    }

    try {
      final appSignatureRaw = await SignatureVerifier.getActualSignature();
      appSignature = SignatureVerifier.normalizeSignatureForHeader(
        appSignatureRaw,
      );
    } catch (e) {
      debugPrint('SXB signature preload skipped: $e');
    }

    String? encodedUserData;
    if (token != null && userData != null) {
      encodedUserData = base64Encode(utf8.encode(userData));
    }

    final source = _buildAuthInjectionSource(
      token: token,
      encodedUserData: encodedUserData,
      appSignature: appSignature,
      trustedOrigin: trustedOrigin,
    );

    if (!mounted) return;
    setState(() {
      _authScript = UserScript(
        source: source,
        injectionTime: UserScriptInjectionTime.AT_DOCUMENT_START,
        allowedOriginRules: {trustedOrigin},
        forMainFrameOnly: true,
      );
      _authPrepared = true;
    });
    if (_webViewController != null) {
      await _injectAuthNow(_webViewController!);
    }
    if (appSignature == null) {
      unawaited(_injectSignatureIntoWebContext());
    }
  }

  Future<void> _injectSignatureIntoWebContext() async {
    try {
      final appSignatureRaw = await SignatureVerifier.getActualSignature();
      final appSignature = SignatureVerifier.normalizeSignatureForHeader(
        appSignatureRaw,
      );
      if (appSignature == null) {
        return;
      }

      final signatureLiteral = jsonEncode(appSignature);
      final trustedOrigin = trustedWebOrigin(_apiService.serverUrl);
      if (trustedOrigin == null) return;
      final script = """
        try {
          if (window.top !== window || window.location.origin !== ${jsonEncode(trustedOrigin)}) return;
          localStorage.setItem('sxb_app_signature', $signatureLiteral);
        } catch (_) {}
      """;

      if (_webViewController != null &&
          await _isTrustedControllerOrigin(_webViewController!)) {
        await _webViewController!.evaluateJavascript(source: script);
      }

      if (mounted && _authScript != null) {
        final mergedSource = "${_authScript!.source}\n$script";
        setState(() {
          _authScript = UserScript(
            source: mergedSource,
            injectionTime: UserScriptInjectionTime.AT_DOCUMENT_START,
            allowedOriginRules: {trustedOrigin},
            forMainFrameOnly: true,
          );
        });
      }
    } catch (e) {
      debugPrint('SXB signature injection skipped: $e');
    }
  }

  String _buildAuthInjectionSource({
    String? token,
    String? encodedUserData,
    String? appSignature,
    required String trustedOrigin,
  }) {
    final tokenLiteral = token == null ? 'null' : jsonEncode(token);
    final userDataLiteral =
        encodedUserData == null ? 'null' : jsonEncode(encodedUserData);
    final buildTokenLiteral = jsonEncode(AppConfig.buildToken);
    final signatureLiteral =
        appSignature == null ? 'null' : jsonEncode(appSignature);
    final trustedOriginLiteral = jsonEncode(trustedOrigin);

    return """
      try {
        if (window.top !== window || window.location.origin !== $trustedOriginLiteral) return;
        const token = $tokenLiteral;
        const userB64 = $userDataLiteral;
        const buildToken = $buildTokenLiteral;
        const appSig = $signatureLiteral;

        if (token) {
          localStorage.setItem('access_token', token);
        }

        if (userB64) {
          // Robust UTF-8 base64 decode for user JSON.
          let userJson = '';
          try {
            const raw = atob(userB64);
            userJson = decodeURIComponent(Array.prototype.map.call(raw, function(c) {
              return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);
            }).join(''));
          } catch (_) {
            userJson = atob(userB64);
          }
          localStorage.setItem('user', userJson);
        }

        // Always seed APK security headers before the web login page makes API calls.
        localStorage.setItem('sxb_build_token', buildToken);

        if (appSig) {
          localStorage.setItem('sxb_app_signature', appSig);
        }
      } catch (e) {
        console.error('SXB: Failed to inject auth token', e);
      }
    """;
  }

  Future<void> _injectAuthNow(InAppWebViewController controller) async {
    final source = _authScript?.source;
    if (source == null || source.isEmpty) return;
    if (!await _isTrustedControllerOrigin(controller)) return;
    try {
      await controller.evaluateJavascript(source: source);
    } catch (e) {
      debugPrint('SXB auth injection runtime failed: $e');
    }
  }

  Future<bool> _isTrustedControllerOrigin(
    InAppWebViewController controller,
  ) async {
    try {
      final currentUrl = await controller.getUrl();
      return isTrustedWebOrigin(
        currentUrl?.toString(),
        _apiService.serverUrl,
      );
    } catch (e) {
      debugPrint('SXB trusted-origin check failed: $e');
      return false;
    }
  }

  void _addTrustedJavaScriptHandler(
    InAppWebViewController controller, {
    required String handlerName,
    required FutureOr<dynamic> Function(List<dynamic>) callback,
  }) {
    controller.addJavaScriptHandler(
      handlerName: handlerName,
      callback: (args) async {
        if (!await _isTrustedControllerOrigin(controller)) {
          debugPrint(
              'SXB bridge call blocked outside trusted origin: $handlerName');
          return false;
        }
        return callback(args);
      },
    );
  }

  bool _isTransientNetworkError(String description) {
    final normalized = description.toLowerCase();
    const transientMarkers = [
      'err_connection_reset',
      'err_connection_closed',
      'err_network_changed',
      'err_timed_out',
      'err_connection_timed_out',
      'err_connection_aborted',
      'err_internet_disconnected',
      'err_address_unreachable',
      'software caused connection abort',
    ];

    for (final marker in transientMarkers) {
      if (normalized.contains(marker)) {
        return true;
      }
    }
    return false;
  }

  Future<void> _loadMainFrame() async {
    final controller = _webViewController;
    if (controller == null) return;

    await controller.loadUrl(
      urlRequest: URLRequest(
        url: WebUri(widget.examUrl),
        headers: _apiService.getSebHeaders(widget.examUrl),
      ),
    );
  }

  Future<void> _retryMainFrameLoad({
    required String reason,
    bool forceErrorScreen = false,
  }) async {
    if (_retryInProgress) return;

    final controller = _webViewController;
    if (controller == null) {
      if (forceErrorScreen && mounted) {
        setState(() {
          _errorMessage = 'Gagal memuat: $reason';
          _isLoading = false;
        });
      }
      return;
    }

    if (_mainFrameRetryCount >= 3) {
      _enterServerOutageMode(
        reason: reason,
        showErrorScreen: true,
        triggerReloadOnRecover: true,
      );
      return;
    }

    _retryInProgress = true;
    _mainFrameRetryCount += 1;
    final retryAttempt = _mainFrameRetryCount;

    if (mounted) {
      setState(() {
        _errorMessage = forceErrorScreen
            ? 'Koneksi ke server sempat terputus. Mencoba menyambung ulang...'
            : null;
        _isLoading = true;
      });
    }

    final serverReachable = await _apiService.verifyConnection(
      timeout: const Duration(seconds: 5),
    );
    if (!mounted) return;

    if (!serverReachable) {
      _retryInProgress = false;
      _enterServerOutageMode(
        reason: reason,
        showErrorScreen: forceErrorScreen || retryAttempt >= 2,
        triggerReloadOnRecover: true,
      );
      return;
    }

    _stopServerReconnectLoop(resetState: true);

    _mainFrameRetryTimer?.cancel();
    _mainFrameRetryTimer = Timer(
      Duration(milliseconds: 700 * retryAttempt),
      () {
        unawaited(_loadMainFrame());
        _retryInProgress = false;
      },
    );
  }

  String _buildOutageMessage() {
    final startedAt = _serverOutageStartedAt;
    final minutesDown =
        startedAt == null ? 0 : DateTime.now().difference(startedAt).inMinutes;
    final downInfo = minutesDown > 0 ? ' (downtime ${minutesDown}m)' : '';
    final emergencyInfo = _allowEmergencyExit
        ? '\n\nMode darurat aktif: Anda bisa keluar aplikasi tanpa terjebak.'
        : '\n\nAplikasi akan terus mencoba reconnect otomatis.';

    return 'Server ujian sedang tidak merespons$downInfo.\n'
        'Pemeriksaan gagal: $_serverOutageProbeFailures kali.\n'
        'Detail: $_lastOutageReason.$emergencyInfo';
  }

  void _updateEmergencyExitPolicy() {
    final hasActiveExam = _currentSessionId != null && !_examSubmitted;
    final startedAt = _serverOutageStartedAt;
    if (!hasActiveExam || startedAt == null) {
      _allowEmergencyExit = false;
      return;
    }

    final outageDuration = DateTime.now().difference(startedAt);
    _allowEmergencyExit = outageDuration.inMinutes >=
            AppConfig.emergencyExitMinOutageMinutes &&
        _serverOutageProbeFailures >= AppConfig.emergencyExitMinFailedProbes;
  }

  void _enterServerOutageMode({
    required String reason,
    bool showErrorScreen = true,
    bool triggerReloadOnRecover = false,
  }) {
    _lastOutageReason = reason;
    _serverOutageStartedAt ??= DateTime.now();
    _serverOutageProbeFailures += 1;
    _needsMainFrameReloadAfterReconnect =
        _needsMainFrameReloadAfterReconnect || triggerReloadOnRecover;
    _updateEmergencyExitPolicy();

    if (showErrorScreen && mounted) {
      setState(() {
        _isLoading = false;
        _errorMessage = _buildOutageMessage();
      });
    }

    unawaited(_refreshQueueIndicators());
    unawaited(_persistResumeSnapshot(connectionState: 'Offline'));
    _startServerReconnectLoop();
  }

  void _startServerReconnectLoop() {
    if (_serverReconnectTimer != null) return;

    const minProbeIntervalSeconds = 3;
    const probeIntervalSeconds =
        AppConfig.reconnectProbeIntervalSeconds < minProbeIntervalSeconds
            ? minProbeIntervalSeconds
            : AppConfig.reconnectProbeIntervalSeconds;

    _serverReconnectTimer =
        Timer.periodic(const Duration(seconds: probeIntervalSeconds), (
      _,
    ) async {
      if (_examSubmitted) {
        _stopServerReconnectLoop(resetState: true);
        return;
      }

      if (_serverReconnectProbeInFlight) return;
      _serverReconnectProbeInFlight = true;

      try {
        final reachable = await _apiService.verifyConnection(
          timeout: const Duration(seconds: 4),
        );

        if (reachable) {
          _recoverFromServerOutage();
          return;
        }

        _serverOutageProbeFailures += 1;
        _updateEmergencyExitPolicy();
        unawaited(_refreshQueueIndicators());
        if (mounted && _errorMessage != null) {
          setState(() {
            _errorMessage = _buildOutageMessage();
          });
        }
      } finally {
        _serverReconnectProbeInFlight = false;
      }
    });
  }

  void _recoverFromServerOutage() {
    final shouldReload = _needsMainFrameReloadAfterReconnect;
    _stopServerReconnectLoop(resetState: true);
    unawaited(_apiService.flushViolationQueue());
    unawaited(_flushAnswerJournalQueue());
    unawaited(
      Future<void>.delayed(
        const Duration(milliseconds: 500),
        _refreshQueueIndicators,
      ),
    );

    if (shouldReload && mounted) {
      setState(() {
        _errorMessage = null;
        _isLoading = true;
      });
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Koneksi server pulih. Memuat ulang ujian...'),
          backgroundColor: Colors.green,
          duration: Duration(seconds: 2),
        ),
      );
    }

    if (shouldReload) {
      unawaited(_loadMainFrame());
    }

    unawaited(_persistResumeSnapshot(connectionState: 'Online'));
  }

  void _stopServerReconnectLoop({bool resetState = false}) {
    _serverReconnectTimer?.cancel();
    _serverReconnectTimer = null;
    _serverReconnectProbeInFlight = false;

    if (resetState) {
      _serverOutageStartedAt = null;
      _serverOutageProbeFailures = 0;
      _allowEmergencyExit = false;
      _lastOutageReason = 'Koneksi ke server ujian terputus';
      _needsMainFrameReloadAfterReconnect = false;
    }
  }

  Future<void> _refreshQueuedViolationCount() async {
    final queued = await _apiService.getQueuedViolationCount();
    if (!mounted) return;
    if (_queuedViolationCount != queued) {
      setState(() {
        _queuedViolationCount = queued;
      });
    }
  }

  Future<void> _refreshQueuedAnswerEventCount() async {
    final sessionId = int.tryParse(_currentSessionId ?? '') ?? 0;
    if (sessionId <= 0) {
      if (_queuedAnswerEventCount != 0 && mounted) {
        setState(() {
          _queuedAnswerEventCount = 0;
        });
      }
      return;
    }

    final pending =
        await _resilienceService.getPendingAnswerEventCount(sessionId);
    if (!mounted) return;
    if (_queuedAnswerEventCount != pending) {
      setState(() {
        _queuedAnswerEventCount = pending;
      });
    }
  }

  Future<void> _refreshQueueIndicators() async {
    await _refreshQueuedViolationCount();
    await _refreshQueuedAnswerEventCount();
  }

  int _clampRuntimeInt(int value, int minValue, int maxValue, int fallback) {
    if (value < minValue || value > maxValue) return fallback;
    return value;
  }

  Future<void> _refreshRuntimePolicy({bool forceRefresh = false}) async {
    try {
      await _apiService.getRuntimePolicy(forceRefresh: forceRefresh);
      _answerJournalSyncSeconds = _clampRuntimeInt(
        _apiService.runtimeAnswerSyncIntervalSeconds,
        10,
        120,
        15,
      );
      _answerJournalBatchSize = _clampRuntimeInt(
        _apiService.runtimeAnswerSyncBatchSize,
        10,
        100,
        30,
      );
      _commandPollSeconds = _clampRuntimeInt(
        _apiService.runtimeCommandPollSeconds,
        15,
        120,
        25,
      );
      debugPrint(
        '📋 Runtime policy: answerSync=${_answerJournalSyncSeconds}s '
        'batch=$_answerJournalBatchSize commandPoll=${_commandPollSeconds}s '
        'cheatingMode=${_apiService.runtimeCheatingReportingMode}',
      );
    } catch (e) {
      debugPrint('Runtime policy refresh skipped: $e');
    }
  }

  Future<void> _startAnswerJournalSyncLoop() async {
    _answerJournalSyncTimer?.cancel();
    await _refreshRuntimePolicy();
    _answerJournalSyncTimer =
        Timer.periodic(Duration(seconds: _answerJournalSyncSeconds), (_) {
      unawaited(_flushAnswerJournalQueue());
    });
  }

  void _stopAnswerJournalSyncLoop() {
    _answerJournalSyncTimer?.cancel();
    _answerJournalSyncTimer = null;
  }

  Future<void> _flushAnswerJournalQueue() async {
    final sessionId = int.tryParse(_currentSessionId ?? '') ?? 0;
    if (sessionId <= 0 || _examSubmitted) return;

    final acked = await _resilienceService.flushAnswerJournal(
      sessionId: sessionId,
      batchSize: _answerJournalBatchSize,
    );
    if (acked > 0) {
      unawaited(_refreshQueueIndicators());
    }
  }

  Future<void> _primeOfflinePackageForSession(int sessionId) async {
    if (!AppConfig.enableOfflineFirstRuntime || sessionId <= 0) return;
    await _resilienceService.preloadOfflinePackage(sessionId: sessionId);
  }

  Future<void> _restoreResumeStateForSession(int sessionId) async {
    if (!AppConfig.enableOfflineFirstRuntime || sessionId <= 0) return;

    final resumeState = await _resilienceService.getResumeState(sessionId);
    if (resumeState == null) return;

    final savedIndex =
        int.tryParse('${resumeState['current_question_index'] ?? 0}') ?? 0;
    final savedRemaining =
        int.tryParse('${resumeState['time_remaining_seconds'] ?? 0}') ?? 0;
    _currentQuestionIndex = savedIndex < 0 ? 0 : savedIndex;
    _lastKnownTimeRemainingSeconds = savedRemaining < 0 ? 0 : savedRemaining;

    final jsIndex = _currentQuestionIndex;
    if (_webViewController != null && jsIndex > 0) {
      await _webViewController!.evaluateJavascript(
        source: '''
          try {
            if (window.examSystem && typeof window.examSystem.jumpToQuestion === 'function') {
              window.examSystem.jumpToQuestion($jsIndex);
            }
          } catch (_) {}
        ''',
      );
    }

    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('Sesi ujian dipulihkan dari state lokal.'),
        backgroundColor: Colors.blueGrey,
        duration: Duration(seconds: 2),
      ),
    );
  }

  Future<void> _persistResumeSnapshot({
    int? serverTimeEpochMs,
    String? connectionState,
  }) async {
    final sessionId = int.tryParse(_currentSessionId ?? '') ?? 0;
    if (sessionId <= 0 || _examSubmitted) return;

    await _resilienceService.persistResumeState(
      sessionId: sessionId,
      currentQuestionIndex: _currentQuestionIndex,
      timeRemainingSeconds: _lastKnownTimeRemainingSeconds,
      queuedViolationCount: _queuedViolationCount,
      pendingAnswerEvents: _queuedAnswerEventCount,
      serverTimeEpochMs: serverTimeEpochMs ?? _lastServerTimeEpochMs,
      connectionState: connectionState,
    );
  }

  Future<void> _clearCurrentSessionRuntimeData() async {
    final sessionId = int.tryParse(_currentSessionId ?? '') ?? 0;
    if (sessionId <= 0) return;
    await _resilienceService.clearSessionRuntimeData(sessionId);
  }

  _ConnectionStateUi _getConnectionUiState() {
    final inOutage = _serverOutageStartedAt != null;
    if (!inOutage) {
      return _ConnectionStateUi.online;
    }

    if (_allowEmergencyExit || _serverOutageProbeFailures >= 3) {
      return _ConnectionStateUi.offline;
    }

    return _ConnectionStateUi.degraded;
  }

  Color _getConnectionUiColor(_ConnectionStateUi state) {
    switch (state) {
      case _ConnectionStateUi.online:
        return const Color(0xFF16a34a);
      case _ConnectionStateUi.degraded:
        return const Color(0xFFf59e0b);
      case _ConnectionStateUi.offline:
        return const Color(0xFFef4444);
    }
  }

  String _getConnectionUiLabel(_ConnectionStateUi state) {
    switch (state) {
      case _ConnectionStateUi.online:
        return 'Online';
      case _ConnectionStateUi.degraded:
        return 'Degraded';
      case _ConnectionStateUi.offline:
        return 'Offline';
    }
  }

  String _getConnectionUiDetails(_ConnectionStateUi state) {
    final totalQueue = _queuedViolationCount + _queuedAnswerEventCount;
    if (state == _ConnectionStateUi.online) {
      return totalQueue > 0
          ? 'v$_queuedViolationCount/a$_queuedAnswerEventCount'
          : 'sinkron';
    }
    if (totalQueue > 0) {
      return 'lokal v$_queuedViolationCount a$_queuedAnswerEventCount';
    }
    return 'reconnect';
  }

  Widget _buildConnectionBadge() {
    if (!AppConfig.showConnectionBadge) {
      return const SizedBox.shrink();
    }

    final state = _getConnectionUiState();
    final totalQueue = _queuedViolationCount + _queuedAnswerEventCount;
    if (state == _ConnectionStateUi.online && totalQueue <= 0) {
      return const SizedBox.shrink();
    }

    final color = _getConnectionUiColor(state);
    final label = _getConnectionUiLabel(state);
    final details = _getConnectionUiDetails(state);

    return GestureDetector(
      onLongPress: () {
        if (AppConfig.enableDiagnosticsQuickExport &&
            _currentSessionId != null &&
            !_examSubmitted) {
          unawaited(_showDiagnosticBundleDialog());
        }
      },
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.9),
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: Colors.white.withValues(alpha: 0.35)),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              Icons.circle,
              size: 8,
              color: Colors.white.withValues(alpha: 0.95),
            ),
            const SizedBox(width: 6),
            Text(
              '$label • $details',
              style: const TextStyle(
                color: Colors.white,
                fontSize: 11,
                fontWeight: FontWeight.w700,
              ),
            ),
          ],
        ),
      ),
    );
  }

  String _normalizeViolationTypeForPolicy(String rawType) {
    final normalized = rawType.trim().toLowerCase().replaceAll(' ', '_');
    if (normalized.isEmpty) return normalized;
    return normalized.startsWith('violation_')
        ? normalized
        : 'violation_$normalized';
  }

  bool _isViolationTemporarilyDisabled(String violationType) {
    final normalized = _normalizeViolationTypeForPolicy(violationType);
    final disabled = _apiService.runtimeDisabledViolationTypes;
    final disabledNow = disabled.contains(normalized);
    if (disabledNow) {
      debugPrint(
        '⏸️ Violation temporarily disabled by runtime policy: $normalized '
        'mode=${_apiService.runtimeCheatingReportingMode}',
      );
    }
    return disabledNow;
  }

  bool _canForceSubmitForViolation(String violationType) {
    return _apiService.runtimeForceSubmitOnViolationEnabled &&
        !_isViolationTemporarilyDisabled(violationType);
  }

  void _pruneRiskEvents() {
    final now = DateTime.now();
    _riskEvents.removeWhere((event) {
      final ts = event['at'] as DateTime?;
      if (ts == null) return true;
      return now.difference(ts).inMinutes > 20;
    });
  }

  void _recalculateRiskScore() {
    _pruneRiskEvents();
    final now = DateTime.now();
    double score = 0.0;

    for (final event in _riskEvents) {
      final ts = event['at'] as DateTime?;
      final weight = (event['weight'] as num?)?.toDouble() ?? 0.0;
      if (ts == null || weight <= 0) continue;

      final ageMinutes = now.difference(ts).inMinutes;
      final decay = ageMinutes <= 5
          ? 1.0
          : ageMinutes <= 15
              ? 0.6
              : 0.3;
      score += weight * decay;
    }

    _violationRiskScore = score;
  }

  void _registerRiskEvent({
    required String type,
    required double weight,
    required String details,
  }) {
    _riskEvents.add({
      'type': type,
      'weight': weight,
      'details': details,
      'at': DateTime.now(),
    });
    _recalculateRiskScore();
  }

  bool _shouldForceSubmitByRisk() {
    final hardCount = _tabSwitchCount + _screenshotCount;
    const fallbackRiskThreshold = 8.0;
    const adaptiveThreshold = AppConfig.riskAutoSubmitThreshold <= 0
        ? fallbackRiskThreshold
        : AppConfig.riskAutoSubmitThreshold;
    return _violationRiskScore >= adaptiveThreshold || hardCount >= 5;
  }

  Map<String, dynamic> _classifySecurityViolation(String message) {
    final text = message.toLowerCase();
    if (text.contains('apk tampering') ||
        text.contains('dimodifikasi') ||
        text.contains('signature')) {
      return {
        'type': 'APK_TAMPERING',
        'weight': 10.0,
        'cooldownSec': 5,
        'enforceSubmit': false,
      };
    }
    if (text.contains('overlay')) {
      return {
        'type': 'OVERLAY_APP',
        'weight': 2.5,
        'cooldownSec': 30,
        'enforceSubmit': true,
      };
    }
    if (text.contains('screen recording') ||
        text.contains('screen_recording')) {
      return {
        'type': 'SCREEN_RECORDING',
        'weight': 3.0,
        'cooldownSec': 20,
        'enforceSubmit': true,
      };
    }
    if (text.contains('external display') ||
        text.contains('hdmi') ||
        text.contains('usb')) {
      return {
        'type': 'EXTERNAL_DISPLAY',
        'weight': 2.5,
        'cooldownSec': 30,
        'enforceSubmit': true,
      };
    }
    if (text.contains('accessibility')) {
      return {
        'type': 'ACCESSIBILITY_RISK',
        'weight': 1.5,
        'cooldownSec': 30,
        'enforceSubmit': false,
      };
    }

    // Generic violation message from background checks: log only, low weight.
    return {
      'type': 'SECURITY_WARNING',
      'weight': 0.4,
      'cooldownSec': 45,
      'enforceSubmit': false,
    };
  }

  Future<void> _initSecurity() async {
    // NOTE: Security check is now done at splash screen level
    // If user reaches this page, APK has been verified as secure

    // NOTE: Kiosk mode is NOT started here!
    // It will be activated when exam actually starts (setSessionId handler)
    // This allows user to browse/login/logout freely before exam

    // Splash already performed full blocking security check.
    // Here we only attach handlers; periodic checks start when exam session starts.
    await _securityService.initialize(
      runInitialChecks: false,
      startPeriodicChecks: false,
    );
    _securityService.onSecurityViolation = (msg) {
      _handleSecurityViolation(msg);
    };

    // Initialize screenshot detection
    _screenshotCallback.addListener(() {
      _handleScreenshotDetected();
    });
    debugPrint('📸 Screenshot detection enabled');
  }

  /// Start exam security - called when exam session begins
  Future<void> _startExamSecurity() async {
    // Start kiosk mode
    _kioskActive = await SecurityService.startKioskMode();

    // Set immersive mode
    await SecurityService.setImmersiveMode();

    // Disable clipboard (block copy/paste)
    await SecurityService.disableClipboard();

    // Check keyboard security (AI/translate detection)
    final keyboardResult = await SecurityService.checkKeyboardSecurity();
    // Only show warning for DANGEROUS keyboards (level 2 - red)
    // Hide notifications for safe (level 0) and unknown (level 1) keyboards
    if (keyboardResult.isDangerous && mounted) {
      debugPrint('⌨️ Keyboard DANGER: ${keyboardResult.message}');
      // Show warning snackbar for suspicious keyboard
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Row(
            children: [
              Icon(
                keyboardResult.isDangerous ? Icons.warning : Icons.info,
                color: Colors.white,
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Text(
                  keyboardResult.message,
                  style: const TextStyle(fontSize: 13),
                ),
              ),
            ],
          ),
          backgroundColor:
              keyboardResult.isDangerous ? Colors.red : Colors.orange,
          duration: const Duration(seconds: 5),
          behavior: SnackBarBehavior.floating,
        ),
      );
    }

    // Inject JS to disable autocomplete on WebView
    _webViewController?.evaluateJavascript(
      source: SecurityService.getJsToDisableAutocomplete(),
    );

    // Start periodic background security checks only during active exam session.
    _securityService.startPeriodicChecks();

    // Start anti-cheat monitoring (overlay, screen recording, HDMI, accessibility)
    _securityService.startAntiCheatMonitoring(
      onViolation: (message) {
        debugPrint('🚨 ANTI-CHEAT: $message');
        _handleSecurityViolation(message);
      },
    );

    // Start server command polling for admin controls
    _startServerCommandPolling();

    debugPrint('🛡️ Exam security fully activated: kiosk=$_kioskActive');
  }

  void _stopRuntimeSecurityMonitoring() {
    _securityService.stopPeriodicChecks();
    _securityService.stopAntiCheatMonitoring();
  }

  /// Start polling server for admin commands (emergency exit, terminate)
  void _startServerCommandPolling() {
    _serverCommandTimer?.cancel();
    _serverCommandTimer =
        Timer.periodic(Duration(seconds: _commandPollSeconds), (_) {
      _checkServerCommands();
    });
    debugPrint('🔄 Server command polling started (${_commandPollSeconds}s)');
  }

  /// Stop server command polling
  void _stopServerCommandPolling() {
    _serverCommandTimer?.cancel();
    _serverCommandTimer = null;
    debugPrint('🔄 Server command polling stopped');
  }

  /// Check server for admin commands
  Future<void> _checkServerCommands() async {
    if (_currentSessionId == null || _emergencyExitTriggered) return;

    try {
      final status = await _apiService.checkSessionStatus(_currentSessionId!);
      if (status == null) return;

      // Check for emergency exit flag
      if (status['emergency_exit_allowed'] == true &&
          !_emergencyExitTriggered) {
        debugPrint('🚨 Emergency exit enabled by admin!');
        await _handleEmergencyExit();
        return;
      }

      // Check for force kick (legacy status "kicked" or canonical terminated+flag)
      final bool isForceKick = status['status'] == 'kicked' ||
          (status['status'] == 'terminated' &&
              status['terminated_by_admin'] == true &&
              status['emergency_exit_allowed'] != true);
      if (isForceKick) {
        debugPrint('🚫 Session kicked by admin!');
        await _handleForceKicked(
          status['kick_reason'] ?? 'Dikeluarkan oleh pengawas',
        );
        return;
      }

      // Check for admin termination
      if (status['terminated_by_admin'] == true ||
          status['status'] == 'terminated') {
        debugPrint('🚫 Session terminated by admin!');
        await _handleAdminTermination();
        return;
      }

      // Fallback force-submit detection via polling when WebSocket command is missed.
      if (status['status'] == 'submitted' || status['status'] == 'completed') {
        debugPrint('📝 Session already submitted by server command');
        await _handleSubmittedFromServer();
        return;
      }
    } catch (e) {
      debugPrint('Server command check failed: $e');
      _enterServerOutageMode(
        reason: 'Sinkronisasi status sesi gagal',
        showErrorScreen: false,
        triggerReloadOnRecover: false,
      );
    }
  }

  Future<void> _handleSubmittedFromServer() async {
    if (_examSubmitted) return;

    _stopServerCommandPolling();
    _stopServerReconnectLoop(resetState: true);
    _stopRuntimeSecurityMonitoring();
    _stopAnswerJournalSyncLoop();
    setState(() {
      _examSubmitted = true;
    });

    try {
      // Ask web runtime to perform graceful submit/redirect flow if still available.
      await _webViewController?.evaluateJavascript(
        source: '''
        try {
          if (window.examSystem && typeof window.examSystem.submitExam === 'function') {
            window.examSystem.submitExam(false);
          } else if (typeof window.submitExam === 'function') {
            window.submitExam(true);
          } else {
            window.location.href = '/student/';
          }
        } catch (_) {
          window.location.href = '/student/';
        }
      ''',
      );
    } catch (e) {
      debugPrint('Submitted status JS handoff failed: $e');
    }

    await SecurityService.stopKioskMode();
    await SecurityService.restoreSystemUI();

    await _clearCurrentSessionRuntimeData();
    _currentSessionId = null;
    _currentExamId = null;

    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('Ujian telah dikumpulkan oleh pengawas.'),
        backgroundColor: Colors.orange,
        duration: Duration(seconds: 3),
      ),
    );
  }

  /// Handle force kicked status from server
  Future<void> _handleForceKicked(String reason) async {
    _emergencyExitTriggered = true;
    _stopServerCommandPolling();
    _stopServerReconnectLoop(resetState: true);
    _stopRuntimeSecurityMonitoring();
    _stopAnswerJournalSyncLoop();

    // Mark exam as submitted to allow exit
    setState(() {
      _examSubmitted = true;
    });

    // Stop all security features
    await SecurityService.stopKioskMode();
    await SecurityService.restoreSystemUI();

    // Clear session
    await _clearCurrentSessionRuntimeData();
    _currentSessionId = null;
    _currentExamId = null;

    if (!mounted) return;

    // Show kicked dialog
    showDialog(
      context: context,
      barrierDismissible: false,
      barrierColor: Colors.red.withValues(alpha: 0.9),
      builder: (ctx) => PopScope(
        canPop: false,
        child: AlertDialog(
          backgroundColor: const Color(0xFF1e293b),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(20),
            side: const BorderSide(color: Colors.red, width: 3),
          ),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.block_rounded, color: Colors.red, size: 80),
              const SizedBox(height: 20),
              const Text(
                '🚫 ANDA DIKELUARKAN',
                style: TextStyle(
                  color: Colors.red,
                  fontSize: 24,
                  fontWeight: FontWeight.bold,
                ),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 16),
              Text(
                reason,
                style: const TextStyle(color: Colors.white, fontSize: 16),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 24),
              const Text(
                'Anda telah dikeluarkan dari ujian oleh pengawas.\nSilakan hubungi pengawas untuk informasi lebih lanjut.',
                style: TextStyle(color: Colors.white70, fontSize: 12),
                textAlign: TextAlign.center,
              ),
            ],
          ),
          actions: [
            SizedBox(
              width: double.infinity,
              child: ElevatedButton(
                onPressed: () {
                  // Close dialog first
                  Navigator.of(ctx).pop();

                  // Navigate to session-ended page and clear entire navigation stack
                  // This prevents black screen by ensuring proper destination
                  Navigator.of(context).pushAndRemoveUntil(
                    MaterialPageRoute(builder: (_) => const SessionEndedPage()),
                    (route) => false, // Remove all routes
                  );
                },
                style: ElevatedButton.styleFrom(
                  backgroundColor: Colors.red,
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(vertical: 14),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(10),
                  ),
                ),
                child: const Text(
                  'KEMBALI KE BERANDA',
                  style: TextStyle(fontWeight: FontWeight.bold, fontSize: 14),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  /// Handle emergency exit - allow user to exit gracefully
  Future<void> _handleEmergencyExit() async {
    _emergencyExitTriggered = true;
    _stopServerCommandPolling();
    _stopServerReconnectLoop(resetState: true);
    _stopRuntimeSecurityMonitoring();
    _stopAnswerJournalSyncLoop();

    // Stop kiosk mode
    await SecurityService.stopKioskMode();
    await SecurityService.restoreSystemUI();

    if (!mounted) return;

    // Show notification with exit button
    setState(() => _isDialogShowing = true);

    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (dialogContext) => PopScope(
        canPop: false,
        child: AlertDialog(
          backgroundColor: const Color(0xFF1e293b),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(20),
            side: const BorderSide(color: Colors.orange, width: 2),
          ),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(
                Icons.exit_to_app_rounded,
                color: Colors.orange,
                size: 64,
              ),
              const SizedBox(height: 20),
              const Text(
                '🚨 Emergency Exit Aktif',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 20,
                  fontWeight: FontWeight.bold,
                ),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 16),
              Text(
                'Admin telah mengizinkan Anda untuk keluar dari aplikasi.\n\nSilakan tutup aplikasi jika diperlukan.',
                style: TextStyle(
                  color: Colors.white.withValues(alpha: 0.8),
                  fontSize: 14,
                ),
                textAlign: TextAlign.center,
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () {
                Navigator.of(context).pop();
                if (mounted) setState(() => _isDialogShowing = false);
              },
              child: const Text(
                'Lanjut Ujian',
                style: TextStyle(color: Colors.grey),
              ),
            ),
            ElevatedButton(
              onPressed: () => SystemNavigator.pop(),
              style: ElevatedButton.styleFrom(backgroundColor: Colors.orange),
              child: const Text('Keluar Aplikasi'),
            ),
          ],
        ),
      ),
    );
  }

  /// Handle admin termination - force exit
  Future<void> _handleAdminTermination() async {
    _emergencyExitTriggered = true;
    _stopServerCommandPolling();
    _stopServerReconnectLoop(resetState: true);
    _stopRuntimeSecurityMonitoring();
    _stopAnswerJournalSyncLoop();

    // Stop kiosk mode
    await SecurityService.stopKioskMode();
    await SecurityService.restoreSystemUI();

    if (!mounted) return;

    // Show termination message
    showDialog(
      context: context,
      barrierDismissible: false,
      barrierColor: Colors.red.withValues(alpha: 0.8),
      builder: (context) => AlertDialog(
        backgroundColor: const Color(0xFF1e293b),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(20),
          side: const BorderSide(color: Colors.red, width: 3),
        ),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.gavel_rounded, color: Colors.red, size: 64),
            const SizedBox(height: 20),
            const Text(
              '🚫 Sesi Dihentikan',
              style: TextStyle(
                color: Colors.red,
                fontSize: 22,
                fontWeight: FontWeight.bold,
              ),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 16),
            Text(
              'Sesi ujian Anda telah dihentikan oleh admin.\n\nAplikasi akan ditutup.',
              style: TextStyle(
                color: Colors.white.withValues(alpha: 0.8),
                fontSize: 14,
              ),
              textAlign: TextAlign.center,
            ),
          ],
        ),
      ),
    );

    // Wait then exit
    await Future.delayed(const Duration(seconds: 3));
    await _clearCurrentSessionRuntimeData();
    SystemNavigator.pop();
  }

  void _handleSecurityViolation(String message) {
    // Log violation to debug
    debugPrint('🚨 Security violation: $message');

    final classified = _classifySecurityViolation(message);
    final violationType = '${classified['type']}';
    final weight = (classified['weight'] as num?)?.toDouble() ?? 0.0;
    final cooldownSec = (classified['cooldownSec'] as num?)?.toInt() ?? 30;
    final enforceSubmit = classified['enforceSubmit'] == true;

    final now = DateTime.now();
    final lastTime = _lastSecurityViolationAt[violationType];
    if (lastTime != null &&
        now.difference(lastTime).inSeconds < cooldownSec &&
        violationType != 'APK_TAMPERING') {
      debugPrint('ℹ️ Duplicate security signal ignored: $violationType');
      return;
    }
    _lastSecurityViolationAt[violationType] = now;

    final temporarilyDisabled = _isViolationTemporarilyDisabled(violationType);

    if (weight > 0 && !temporarilyDisabled) {
      _registerRiskEvent(type: violationType, weight: weight, details: message);
    }

    // Send to server if we have a session and the runtime policy allows it.
    if (_currentSessionId != null && !temporarilyDisabled) {
      _apiService.logViolation(
        sessionId: _currentSessionId!,
        examId: _currentExamId,
        type: violationType,
        count: 1,
        details:
            '$message | risk=${_violationRiskScore.toStringAsFixed(2)} | weight=${weight.toStringAsFixed(2)}',
      );
      unawaited(_refreshQueueIndicators());
    }

    // Special handling for APK tampering
    if (violationType == 'APK_TAMPERING') {
      _handleApkTamperingDetected();
      return;
    }

    if (enforceSubmit &&
        _canForceSubmitForViolation(violationType) &&
        _shouldForceSubmitByRisk()) {
      _forceSubmitExam(
        reason: 'Pelanggaran keamanan serius berulang terdeteksi.',
      );
    }
  }

  /// Handle APK tampering detection - critical security issue
  void _handleApkTamperingDetected() {
    if (!mounted) return;

    showDialog(
      context: context,
      barrierDismissible: false,
      barrierColor: Colors.red.withValues(alpha: 0.9),
      builder: (dialogContext) => PopScope(
        canPop: false,
        child: AlertDialog(
          backgroundColor: const Color(0xFF1e293b),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(20),
            side: const BorderSide(color: Colors.red, width: 3),
          ),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.security_rounded, color: Colors.red, size: 80),
              const SizedBox(height: 20),
              const Text(
                '🚫 APK TERMODIFIKASI',
                style: TextStyle(
                  color: Colors.red,
                  fontSize: 24,
                  fontWeight: FontWeight.bold,
                ),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 16),
              Text(
                'Sistem mendeteksi bahwa aplikasi ini telah dimodifikasi atau tidak resmi.',
                style: TextStyle(
                  color: Colors.white.withValues(alpha: 0.9),
                  fontSize: 16,
                ),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 24),
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: Colors.red.withValues(alpha: 0.2),
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: Colors.red.withValues(alpha: 0.5)),
                ),
                child: Column(
                  children: [
                    const Text(
                      '⚠️ PERINGATAN KEAMANAN',
                      style: TextStyle(
                        color: Colors.white,
                        fontSize: 16,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    const SizedBox(height: 12),
                    Text(
                      'Penggunaan APK yang dimodifikasi melanggar kebijakan ujian dan dapat mengakibatkan diskualifikasi.',
                      style: TextStyle(
                        color: Colors.white.withValues(alpha: 0.8),
                        fontSize: 12,
                      ),
                      textAlign: TextAlign.center,
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 16),
              Text(
                'Pelanggaran ini telah dicatat dan dilaporkan ke pengawas.',
                style: TextStyle(
                  color: Colors.white.withValues(alpha: 0.6),
                  fontSize: 10,
                ),
                textAlign: TextAlign.center,
              ),
            ],
          ),
          actions: [
            SizedBox(
              width: double.infinity,
              child: ElevatedButton(
                onPressed: () async {
                  Navigator.of(dialogContext).pop();

                  // Force submit and exit after tampering detected
                  await Future.delayed(const Duration(milliseconds: 500));

                  if (!mounted) return;

                  // Show final message
                  showDialog(
                    context: context,
                    barrierDismissible: false,
                    barrierColor: Colors.red.withValues(alpha: 0.95),
                    builder: (context) => AlertDialog(
                      backgroundColor: const Color(0xFF1e293b),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(20),
                        side: const BorderSide(color: Colors.red, width: 3),
                      ),
                      content: Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          const Icon(Icons.block, color: Colors.red, size: 64),
                          const SizedBox(height: 16),
                          const Text(
                            'Sesi Diblokir',
                            style: TextStyle(
                              color: Colors.red,
                              fontSize: 20,
                              fontWeight: FontWeight.bold,
                            ),
                          ),
                          const SizedBox(height: 12),
                          Text(
                            'Silakan gunakan APK resmi dari penyelenggara ujian.',
                            style: TextStyle(
                              color: Colors.white.withValues(alpha: 0.8),
                              fontSize: 14,
                            ),
                            textAlign: TextAlign.center,
                          ),
                        ],
                      ),
                    ),
                  );

                  // Exit app after 3 seconds
                  await Future.delayed(const Duration(seconds: 3));
                  await SecurityService.stopKioskMode();
                  await SecurityService.restoreSystemUI();
                  SystemNavigator.pop();
                },
                style: ElevatedButton.styleFrom(
                  backgroundColor: Colors.red,
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(vertical: 14),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(10),
                  ),
                ),
                child: const Text(
                  'TUTUP APLIKASI',
                  style: TextStyle(fontWeight: FontWeight.bold, fontSize: 14),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    switch (state) {
      case AppLifecycleState.paused:
        // App went to background - potential tab switch
        _lastBackgroundTime = DateTime.now();
        // Cancel any pending violation dialog to prevent race conditions
        _violationDebounceTimer?.cancel();
        _violationDebounceTimer = null;

        // Pause WebView to save resources (Android only)
        if (_webViewController != null) {
          _webViewController!.pause();
        }
        unawaited(_persistResumeSnapshot(connectionState: 'paused'));
        break;

      case AppLifecycleState.resumed:
        // Resume WebView immediately to prevent black screen
        // This must happen FIRST before any other logic
        if (_webViewController != null) {
          _webViewController!.resume();

          // Force a repaint by evaluating simple JS
          Future.delayed(const Duration(milliseconds: 100), () {
            if (mounted && _webViewController != null) {
              _webViewController!.evaluateJavascript(
                source: "document.body.style.display='none'; "
                    "setTimeout(function() { document.body.style.display=''; }, 10);",
              );
            }
          });
        }

        // App resumed - check if this was a tab switch
        // But only if exam is not yet submitted
        if (_lastBackgroundTime != null && !_examSubmitted) {
          final now = DateTime.now();
          final backgroundDuration = now.difference(_lastBackgroundTime!);

          // Debounce: Ignore rapid resume events within 1 second of last resume
          // This prevents stack overflow of dialogs on rapid screen toggles
          if (_lastResumeTime != null &&
              now.difference(_lastResumeTime!).inSeconds < 1) {
            debugPrint('Screen toggle debounced - ignoring rapid resume');
            break;
          }
          _lastResumeTime = now;

          // Only process if app was backgrounded long enough.
          // Short transitions are treated as low-risk to reduce false positives.
          if (backgroundDuration.inSeconds > 3) {
            // Cancel any existing pending timer
            _violationDebounceTimer?.cancel();

            // Use a longer delay (800ms) and debounce to prevent stuck dialogs
            _violationDebounceTimer = Timer(
              const Duration(milliseconds: 800),
              () {
                if (mounted && !_examSubmitted && !_isDialogShowing) {
                  _handleTabSwitch(backgroundDuration: backgroundDuration);
                }
              },
            );
          }
        }

        // Re-enable immersive mode only if exam is active and no dialog is showing
        if (!_examSubmitted && _currentSessionId != null && !_isDialogShowing) {
          // Delay immersive mode more (1000ms) to avoid conflict with dialog
          Future.delayed(const Duration(milliseconds: 1000), () {
            if (mounted && !_isDialogShowing) {
              SecurityService.setImmersiveMode();
            }
          });
        }
        unawaited(_flushAnswerJournalQueue());
        unawaited(_refreshQueueIndicators());
        unawaited(_persistResumeSnapshot(connectionState: 'resumed'));
        break;

      default:
        break;
    }
  }

  void _handleTabSwitch({required Duration backgroundDuration}) {
    // Don't count violations if exam is already submitted
    if (_examSubmitted) {
      debugPrint('Tab switch detected but exam already submitted - ignoring');
      return;
    }

    // Only count violations if exam is active (session started)
    if (_currentSessionId == null) {
      debugPrint('Tab switch detected but no active exam session');
      return;
    }

    final now = DateTime.now();
    if (_lastTabViolationAt != null &&
        now.difference(_lastTabViolationAt!).inSeconds < 20) {
      debugPrint('Tab switch ignored by cooldown guard');
      return;
    }
    _lastTabViolationAt = now;

    final durationSec = backgroundDuration.inSeconds;
    final bool minorSwitch = durationSec < 8;
    final bool severeSwitch = durationSec >= 20;
    final double weight = minorSwitch
        ? 0.25
        : severeSwitch
            ? 2.0
            : 1.0;

    final tabViolationType = minorSwitch ? 'TAB_SWITCH_MINOR' : 'TAB_SWITCH';
    final temporarilyDisabled =
        _isViolationTemporarilyDisabled(tabViolationType);

    // Minor switch is logged as low-confidence and doesn't increase hard count.
    if (!minorSwitch && !temporarilyDisabled) {
      _tabSwitchCount++;
    }

    if (!temporarilyDisabled) {
      _registerRiskEvent(
        type: tabViolationType,
        weight: weight,
        details: 'Background for ${durationSec}s',
      );
    }

    // Log tab switch violation
    debugPrint(
      'Tab switch detected (duration=${durationSec}s, minor=$minorSwitch) '
      'count=$_tabSwitchCount risk=${_violationRiskScore.toStringAsFixed(2)}',
    );

    // Send violation to server (await for diagnostics)
    if (!temporarilyDisabled) {
      _apiService
          .logViolation(
        sessionId: _currentSessionId!,
        examId: _currentExamId,
        type: tabViolationType,
        count: _tabSwitchCount,
        details:
            'User left app for ${durationSec}s | risk=${_violationRiskScore.toStringAsFixed(2)}',
      )
          .then((success) {
        if (!success) {
          debugPrint('🔴 TAB_SWITCH violation failed to send to server!');
        }
        unawaited(_refreshQueueIndicators());
      });
    }

    // Check risk-based auto-submit for repeated/high-confidence signals
    if (_canForceSubmitForViolation(tabViolationType) &&
        _shouldForceSubmitByRisk()) {
      _forceSubmitExam(
        reason: 'Aktivitas keluar aplikasi berulang terdeteksi.',
      );
      return;
    }

    // Show warning overlay only for non-minor switches
    if (!minorSwitch && !_isDialogShowing) {
      _showViolationWarningOverlay();
    }

    // Inject violation count into WebView
    _webViewController?.evaluateJavascript(
      source: '''
      if (window.onTabSwitch) {
        window.onTabSwitch($_tabSwitchCount);
      }
      // Also update exam system if available
      if (window.examSystem && window.examSystem.recordViolation) {
        window.examSystem.recordViolation('${minorSwitch ? 'tab_switch_minor' : 'tab_switch'}', $_tabSwitchCount, true); // true = fromNative
      }
    ''',
    );
  }

  /// Handle screenshot detection
  void _handleScreenshotDetected() {
    // Ignore if exam not active
    if (_currentSessionId == null || _examSubmitted) {
      debugPrint('Screenshot detected but no active exam session');
      return;
    }

    final now = DateTime.now();
    if (_lastScreenshotViolationAt != null &&
        now.difference(_lastScreenshotViolationAt!).inSeconds < 15) {
      debugPrint('Screenshot signal ignored by cooldown guard');
      return;
    }
    _lastScreenshotViolationAt = now;

    _screenshotCount++;
    _registerRiskEvent(
      type: 'SCREENSHOT_ATTEMPT',
      weight: 2.0,
      details: 'Screenshot detected by system callback',
    );

    debugPrint(
      '🚨 SCREENSHOT DETECTED! Count=$_screenshotCount risk=${_violationRiskScore.toStringAsFixed(2)}',
    );

    // Log to server
    _apiService
        .logViolation(
      sessionId: _currentSessionId!,
      examId: _currentExamId,
      type: 'SCREENSHOT_ATTEMPT',
      count: _screenshotCount,
      details:
          'Screenshot taken during exam | risk=${_violationRiskScore.toStringAsFixed(2)}',
    )
        .then((success) {
      if (!success) {
        debugPrint('🔴 SCREENSHOT violation failed to send to server!');
      }
      unawaited(_refreshQueueIndicators());
    });

    // Calculate total violations (tab switch + screenshot)
    final totalViolations = _tabSwitchCount + _screenshotCount;

    // Check for auto-submit (risk-aware + hard limit fallback)
    if (_canForceSubmitForViolation('SCREENSHOT_ATTEMPT') &&
        _shouldForceSubmitByRisk()) {
      debugPrint(
        '🚨 AUTO-SUBMIT: Total violations = $totalViolations, risk=${_violationRiskScore.toStringAsFixed(2)}',
      );
      _forceSubmitExam(reason: 'Pelanggaran keamanan berulang terdeteksi.');
      return;
    }

    // Show warning overlay (if not already showing)
    if (!_isDialogShowing) {
      _showScreenshotWarningOverlay();
    }

    // Inject into WebView
    _webViewController?.evaluateJavascript(
      source: '''
      if (window.examSystem && window.examSystem.recordViolation) {
        window.examSystem.recordViolation('screenshot_attempt', $_screenshotCount, true);
      }
    ''',
    );
  }

  /// Show screenshot warning overlay
  void _showScreenshotWarningOverlay() {
    if (!mounted) return;

    setState(() => _isDialogShowing = true);

    showDialog(
      context: context,
      barrierDismissible: false,
      barrierColor: Colors.red.withValues(alpha: 0.8),
      builder: (context) => PopScope(
        canPop: false,
        child: AlertDialog(
          backgroundColor: const Color(0xFF1e293b),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(20),
            side: const BorderSide(color: Colors.red, width: 3),
          ),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(
                Icons.screenshot_outlined,
                color: Colors.red,
                size: 80,
              ),
              const SizedBox(height: 20),
              const Text(
                '📸 SCREENSHOT TERDETEKSI!',
                style: TextStyle(
                  color: Colors.red,
                  fontSize: 24,
                  fontWeight: FontWeight.bold,
                ),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 16),
              Text(
                'Mengambil screenshot tidak diperbolehkan!',
                style: TextStyle(
                  color: Colors.white.withValues(alpha: 0.9),
                  fontSize: 16,
                ),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 24),
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: Colors.red.withValues(alpha: 0.2),
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: Colors.red.withValues(alpha: 0.5)),
                ),
                child: Column(
                  children: [
                    Text(
                      'Pelanggaran #$_screenshotCount',
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 18,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      'Total: ${_tabSwitchCount + _screenshotCount} dari 5',
                      style: const TextStyle(
                        color: Colors.orange,
                        fontSize: 14,
                      ),
                    ),
                    const SizedBox(height: 12),
                    LinearProgressIndicator(
                      value: (_tabSwitchCount + _screenshotCount) / 5,
                      backgroundColor: Colors.white24,
                      valueColor: AlwaysStoppedAnimation<Color>(
                        (_tabSwitchCount + _screenshotCount) >= 4
                            ? Colors.red
                            : Colors.orange,
                      ),
                      minHeight: 10,
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 16),
              const Text(
                'Pelanggaran ini tercatat dan dilaporkan ke pengawas.',
                style: TextStyle(color: Colors.white70, fontSize: 12),
                textAlign: TextAlign.center,
              ),
            ],
          ),
          actions: [
            SizedBox(
              width: double.infinity,
              child: ElevatedButton(
                onPressed: () {
                  Navigator.of(context).pop();
                  if (mounted) {
                    setState(() => _isDialogShowing = false);
                    SecurityService.setImmersiveMode();
                  }
                },
                style: ElevatedButton.styleFrom(
                  backgroundColor: Colors.red,
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(vertical: 14),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(10),
                  ),
                ),
                child: const Text(
                  'SAYA MENGERTI',
                  style: TextStyle(fontWeight: FontWeight.bold, fontSize: 14),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  /// Show big warning overlay when violation detected
  void _showViolationWarningOverlay() {
    if (!mounted) return;

    setState(() => _isDialogShowing = true);

    showDialog(
      context: context,
      barrierDismissible: false,
      barrierColor: Colors.red.withValues(alpha: 0.8),
      builder: (context) => PopScope(
        canPop: false,
        child: AlertDialog(
          backgroundColor: const Color(0xFF1e293b),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(20),
            side: const BorderSide(color: Colors.red, width: 3),
          ),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(
                Icons.warning_amber_rounded,
                color: Colors.red,
                size: 80,
              ),
              const SizedBox(height: 20),
              const Text(
                '⚠️ PERINGATAN KERAS!',
                style: TextStyle(
                  color: Colors.red,
                  fontSize: 24,
                  fontWeight: FontWeight.bold,
                ),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 16),
              Text(
                'Anda terdeteksi meninggalkan aplikasi ujian!',
                style: TextStyle(
                  color: Colors.white.withValues(alpha: 0.9),
                  fontSize: 16,
                ),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 24),
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: Colors.red.withValues(alpha: 0.2),
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: Colors.red.withValues(alpha: 0.5)),
                ),
                child: Column(
                  children: [
                    Text(
                      'Pelanggaran ke-$_tabSwitchCount dari 5',
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 18,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    const SizedBox(height: 8),
                    LinearProgressIndicator(
                      value: _tabSwitchCount / 5,
                      backgroundColor: Colors.white24,
                      valueColor: AlwaysStoppedAnimation<Color>(
                        _tabSwitchCount >= 4 ? Colors.red : Colors.orange,
                      ),
                      minHeight: 10,
                    ),
                    const SizedBox(height: 8),
                    Text(
                      _tabSwitchCount >= 4
                          ? '🚨 PERINGATAN TERAKHIR!'
                          : 'Ujian akan dikumpulkan otomatis pada pelanggaran ke-5',
                      style: TextStyle(
                        color:
                            _tabSwitchCount >= 4 ? Colors.red : Colors.orange,
                        fontSize: 12,
                        fontWeight: FontWeight.bold,
                      ),
                      textAlign: TextAlign.center,
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 24),
              const Text(
                'Pelanggaran ini tercatat dan dilaporkan ke pengawas.',
                style: TextStyle(color: Colors.white70, fontSize: 12),
                textAlign: TextAlign.center,
              ),
            ],
          ),
          actions: [
            SizedBox(
              width: double.infinity,
              child: ElevatedButton(
                onPressed: () {
                  Navigator.of(context).pop();
                  if (mounted) {
                    setState(() => _isDialogShowing = false);
                    SecurityService.setImmersiveMode();
                  }
                },
                style: ElevatedButton.styleFrom(
                  backgroundColor: Colors.red,
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(vertical: 14),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(10),
                  ),
                ),
                child: const Text(
                  'SAYA MENGERTI, LANJUTKAN UJIAN',
                  style: TextStyle(fontWeight: FontWeight.bold, fontSize: 14),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Future<bool> _handleOpenImagePreview(List<dynamic> args) async {
    if (args.isEmpty) return false;

    final rawUrl = '${args[0] ?? ''}'.trim();
    if (rawUrl.isEmpty) return false;

    final title = args.length > 1 && '${args[1] ?? ''}'.trim().isNotEmpty
        ? '${args[1]}'.trim()
        : 'Preview gambar';

    try {
      final resolvedUrl = await _resolveImagePreviewUrl(rawUrl);
      if (resolvedUrl == null || resolvedUrl.isEmpty) return false;

      final uri = Uri.tryParse(resolvedUrl);
      if (uri == null ||
          !uri.hasScheme ||
          !['http', 'https'].contains(uri.scheme.toLowerCase())) {
        return false;
      }

      final headers = await _buildImagePreviewHeaders(resolvedUrl);
      if (!mounted) return false;

      await _showNativeImagePreview(
        imageUrl: resolvedUrl,
        title: title,
        headers: headers,
      );
      return true;
    } catch (e) {
      debugPrint('Native image preview failed: $e');
      return false;
    }
  }

  Future<String?> _resolveImagePreviewUrl(String rawUrl) async {
    final trimmed = rawUrl.trim();
    if (trimmed.isEmpty) return null;

    final parsed = Uri.tryParse(trimmed);
    if (parsed == null) return null;
    if (parsed.hasScheme) return parsed.toString();

    try {
      final currentUrl = await _webViewController?.getUrl();
      final base =
          currentUrl != null ? Uri.tryParse(currentUrl.toString()) : null;
      if (base != null) {
        return base.resolveUri(parsed).toString();
      }
    } catch (e) {
      debugPrint('Failed resolving image URL against WebView URL: $e');
    }

    final serverBase = Uri.tryParse(_apiService.serverUrl);
    if (serverBase != null) {
      return serverBase.resolve(trimmed).toString();
    }
    return null;
  }

  Future<Map<String, String>> _buildImagePreviewHeaders(String imageUrl) async {
    final headers =
        Map<String, String>.from(_apiService.getSebHeaders(imageUrl));
    final token = await _apiService.getToken();
    if (token != null && token.isNotEmpty) {
      headers['Authorization'] = 'Bearer $token';
    }
    return headers;
  }

  Future<void> _showNativeImagePreview({
    required String imageUrl,
    required String title,
    required Map<String, String> headers,
  }) async {
    if (!mounted) return;

    final transformationController = TransformationController();
    var zoomed = false;

    try {
      await showDialog<void>(
        context: context,
        barrierColor: Colors.black,
        barrierDismissible: true,
        builder: (dialogContext) => PopScope(
          canPop: true,
          child: Material(
            color: Colors.black,
            child: SafeArea(
              child: Stack(
                children: [
                  Positioned.fill(
                    child: Center(
                      child: GestureDetector(
                        behavior: HitTestBehavior.opaque,
                        onDoubleTap: () {
                          zoomed = !zoomed;
                          transformationController.value = zoomed
                              ? Matrix4.diagonal3Values(2.5, 2.5, 1)
                              : Matrix4.identity();
                        },
                        child: InteractiveViewer(
                          transformationController: transformationController,
                          minScale: 1,
                          maxScale: 5,
                          panEnabled: true,
                          scaleEnabled: true,
                          child: Image.network(
                            imageUrl,
                            headers: headers,
                            fit: BoxFit.contain,
                            loadingBuilder: (context, child, loadingProgress) {
                              if (loadingProgress == null) return child;
                              return const SizedBox(
                                width: 96,
                                height: 96,
                                child: Center(
                                  child: CircularProgressIndicator(
                                    color: Colors.white,
                                  ),
                                ),
                              );
                            },
                            errorBuilder: (context, error, stackTrace) {
                              return const Padding(
                                padding: EdgeInsets.all(24),
                                child: Column(
                                  mainAxisSize: MainAxisSize.min,
                                  children: [
                                    Icon(
                                      Icons.broken_image_outlined,
                                      color: Colors.white70,
                                      size: 56,
                                    ),
                                    SizedBox(height: 12),
                                    Text(
                                      'Gambar gagal dimuat',
                                      style: TextStyle(
                                        color: Colors.white,
                                        fontSize: 16,
                                        fontWeight: FontWeight.w700,
                                      ),
                                      textAlign: TextAlign.center,
                                    ),
                                  ],
                                ),
                              );
                            },
                          ),
                        ),
                      ),
                    ),
                  ),
                  Positioned(
                    top: 12,
                    right: 12,
                    child: ElevatedButton.icon(
                      onPressed: () => Navigator.of(dialogContext).pop(),
                      icon: const Icon(Icons.close),
                      label: const Text('Tutup'),
                      style: ElevatedButton.styleFrom(
                        backgroundColor: Colors.white.withValues(alpha: 0.16),
                        foregroundColor: Colors.white,
                        padding: const EdgeInsets.symmetric(
                          horizontal: 16,
                          vertical: 12,
                        ),
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(999),
                          side: const BorderSide(color: Colors.white30),
                        ),
                      ),
                    ),
                  ),
                  Positioned(
                    left: 16,
                    right: 16,
                    bottom: 16,
                    child: DecoratedBox(
                      decoration: BoxDecoration(
                        color: Colors.black.withValues(alpha: 0.55),
                        borderRadius: BorderRadius.circular(999),
                      ),
                      child: Padding(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 16,
                          vertical: 10,
                        ),
                        child: Text(
                          '$title • Cubit untuk zoom, geser untuk pan, double tap untuk zoom cepat',
                          style: const TextStyle(
                            color: Colors.white70,
                            fontSize: 12,
                          ),
                          textAlign: TextAlign.center,
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      );
    } finally {
      transformationController.dispose();
      if (mounted) {
        await SecurityService.setImmersiveMode();
      }
    }
  }

  /// Force submit exam due to too many violations
  Future<void> _forceSubmitExam({
    String reason = 'Anda telah mencapai ambang pelanggaran keamanan.',
  }) async {
    if (!mounted) return;

    // Show final warning
    showDialog(
      context: context,
      barrierDismissible: false,
      barrierColor: Colors.red.withValues(alpha: 0.9),
      builder: (context) => PopScope(
        canPop: false,
        child: AlertDialog(
          backgroundColor: const Color(0xFF1e293b),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(20),
            side: const BorderSide(color: Colors.red, width: 3),
          ),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.gavel_rounded, color: Colors.red, size: 80),
              const SizedBox(height: 20),
              const Text(
                '🚫 UJIAN DIAKHIRI',
                style: TextStyle(
                  color: Colors.red,
                  fontSize: 24,
                  fontWeight: FontWeight.bold,
                ),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 16),
              Text(
                '$reason\nUjian akan dikumpulkan secara otomatis.',
                style: const TextStyle(color: Colors.white, fontSize: 16),
                textAlign: TextAlign.center,
              ),
            ],
          ),
        ),
      ),
    );

    // Wait a moment then force submit via JavaScript
    await Future.delayed(const Duration(seconds: 2));

    _webViewController?.evaluateJavascript(
      source: '''
      if (window.examSystem && window.examSystem.forceSubmitDueToViolations) {
        window.examSystem.forceSubmitDueToViolations();
      } else if (window.submitExam) {
        window.submitExam(true); // force submit
      }
    ''',
    );

    // Disable kiosk after force submit
    await Future.delayed(const Duration(seconds: 3));
    setState(() {
      _examSubmitted = true;
    });
    _stopServerReconnectLoop(resetState: true);
    _stopRuntimeSecurityMonitoring();
    _stopAnswerJournalSyncLoop();
    await _clearCurrentSessionRuntimeData();
    _currentSessionId = null;
    _currentExamId = null;
    await SecurityService.stopKioskMode();
    await SecurityService.restoreSystemUI();

    if (mounted) {
      Navigator.of(context).pop(); // Close dialog
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_showSecurityWarning && _securityWarningMessage.isNotEmpty) {
      return _buildSecurityWarningScreen();
    }

    if (_errorMessage != null) {
      return _buildErrorScreen();
    }

    return PopScope(
      canPop: _examSubmitted, // Allow pop only after exam is submitted
      onPopInvokedWithResult: (didPop, _) {
        if (didPop) return;
        if (_examSubmitted) {
          // Exam already submitted, allow exit
          Navigator.of(context).pop();
        } else {
          _showExitWarning();
        }
      },
      child: Scaffold(
        backgroundColor: const Color(0xFF0f172a),
        body: SafeArea(
          child: Stack(
            children: [
              // WebView
              if (_authPrepared)
                InAppWebView(
                  initialUrlRequest: URLRequest(
                    url: WebUri(widget.examUrl),
                    headers: ApiService().getSebHeaders(widget.examUrl),
                  ),
                  initialUserScripts: _authScript != null
                      ? UnmodifiableListView([_authScript!])
                      : null,
                  initialSettings: InAppWebViewSettings(
                    // JavaScript
                    javaScriptEnabled: true,
                    domStorageEnabled: true,
                    databaseEnabled: true,

                    // Zoom
                    supportZoom: true,
                    builtInZoomControls: true,
                    displayZoomControls: false,

                    // Security - Block file access
                    allowFileAccess: false,
                    allowContentAccess: false,

                    // Text selection
                    disableContextMenu: true, // Disable long-press menu
                    // Cache
                    cacheEnabled: true,
                    clearCache: false,

                    // User Agent (identify as SEB/Exambro)
                    userAgent:
                        'Mozilla/5.0 (Linux; Android) AppleWebKit/537.36 SEB/3.5 Exambro/1.0',

                    // Media - Enable inline playback and fullscreen for YouTube embeds
                    mediaPlaybackRequiresUserGesture: false,
                    allowsInlineMediaPlayback: true,
                    useWideViewPort: true,
                    loadWithOverviewMode: true,

                    // Enable fullscreen video support
                    javaScriptCanOpenWindowsAutomatically: false,

                    // Third party cookies for embedded content
                    thirdPartyCookiesEnabled: true,

                    // Mixed content
                    mixedContentMode: AppConfig.allowCleartextTraffic
                        ? MixedContentMode.MIXED_CONTENT_COMPATIBILITY_MODE
                        : MixedContentMode.MIXED_CONTENT_NEVER_ALLOW,

                    // Scrolling
                    verticalScrollBarEnabled: true,
                    horizontalScrollBarEnabled: false,
                  ),
                  onWebViewCreated: (controller) {
                    _webViewController = controller;
                    unawaited(_injectAuthNow(controller));

                    // Handler: stable native image preview for Android APK/WebView.
                    _addTrustedJavaScriptHandler(
                      controller,
                      handlerName: 'openImagePreview',
                      callback: (args) async {
                        return await _handleOpenImagePreview(args);
                      },
                    );

                    // Handler untuk security events
                    _addTrustedJavaScriptHandler(
                      controller,
                      handlerName: 'securityHandler',
                      callback: (args) {
                        debugPrint('Security event from web: $args');
                      },
                    );

                    // Handler untuk set session ID dan exam ID (dari exam start)
                    _addTrustedJavaScriptHandler(
                      controller,
                      handlerName: 'setSessionId',
                      callback: (args) async {
                        if (args.isNotEmpty) {
                          _currentSessionId = args[0].toString();
                          // Also get exam_id if provided (second argument)
                          if (args.length > 1) {
                            _currentExamId = int.tryParse(args[1].toString());
                          }

                          // FIX: Fallback — extract exam_id from URL if not provided by JS
                          if (_currentExamId == null || _currentExamId == 0) {
                            try {
                              final currentUrl =
                                  await _webViewController?.getUrl();
                              if (currentUrl != null) {
                                final examIdParam =
                                    currentUrl.queryParameters['exam_id'];
                                if (examIdParam != null) {
                                  _currentExamId = int.tryParse(examIdParam);
                                  debugPrint(
                                    '📋 exam_id extracted from URL: $_currentExamId',
                                  );
                                }
                              }
                            } catch (e) {
                              debugPrint(
                                '⚠️ Failed to extract exam_id from URL: $e',
                              );
                            }
                          }

                          debugPrint(
                            'Session ID set: $_currentSessionId, Exam ID: $_currentExamId',
                          );

                          // Exam is starting - activate security now!
                          await _refreshRuntimePolicy(forceRefresh: true);
                          await _startExamSecurity();
                          await _startAnswerJournalSyncLoop();

                          final sessionIdInt =
                              int.tryParse(_currentSessionId ?? '') ?? 0;
                          if (sessionIdInt > 0) {
                            unawaited(
                                _primeOfflinePackageForSession(sessionIdInt));
                            unawaited(
                                _restoreResumeStateForSession(sessionIdInt));
                            unawaited(_flushAnswerJournalQueue());
                          }
                          unawaited(_refreshQueueIndicators());
                        }
                        return true;
                      },
                    );

                    // Handler: append-only answer event bridge (web -> native journal)
                    _addTrustedJavaScriptHandler(
                      controller,
                      handlerName: 'answerJournalEvent',
                      callback: (args) async {
                        if (args.isEmpty || _currentSessionId == null) {
                          return false;
                        }
                        final payload = args[0];
                        if (payload is! Map) {
                          return false;
                        }

                        final sessionIdInt =
                            int.tryParse(_currentSessionId ?? '') ?? 0;
                        final questionId =
                            int.tryParse('${payload['question_id'] ?? 0}') ?? 0;
                        if (sessionIdInt <= 0 || questionId <= 0) {
                          return false;
                        }

                        final answerPayload = <String, dynamic>{};
                        if (payload['selected_option_id'] != null) {
                          answerPayload['selected_option_id'] =
                              payload['selected_option_id'];
                        }
                        if (payload['selected_option_ids'] is List) {
                          answerPayload['selected_option_ids'] =
                              payload['selected_option_ids'];
                        }
                        if (payload['answer_text'] != null) {
                          answerPayload['answer_text'] = payload['answer_text'];
                        }
                        if (payload['statement_answers'] is Map) {
                          answerPayload['statement_answers'] =
                              Map<String, dynamic>.from(
                            payload['statement_answers'] as Map,
                          );
                        }
                        if (payload['answer_metadata'] is Map) {
                          answerPayload['answer_metadata'] =
                              Map<String, dynamic>.from(
                            payload['answer_metadata'] as Map,
                          );
                        }

                        await _resilienceService.appendAnswerEvent(
                          sessionId: sessionIdInt,
                          questionId: questionId,
                          answerPayload: answerPayload,
                        );
                        unawaited(_flushAnswerJournalQueue());
                        unawaited(_refreshQueueIndicators());
                        return true;
                      },
                    );

                    // Handler: resume state snapshot bridge (web -> native)
                    _addTrustedJavaScriptHandler(
                      controller,
                      handlerName: 'examStateUpdate',
                      callback: (args) async {
                        if (args.isEmpty) return false;
                        final payload = args[0];
                        if (payload is! Map) return false;

                        _currentQuestionIndex = int.tryParse(
                              '${payload['current_question_index'] ?? _currentQuestionIndex}',
                            ) ??
                            _currentQuestionIndex;
                        _lastKnownTimeRemainingSeconds = int.tryParse(
                              '${payload['time_remaining_seconds'] ?? _lastKnownTimeRemainingSeconds}',
                            ) ??
                            _lastKnownTimeRemainingSeconds;

                        await _persistResumeSnapshot(
                          connectionState:
                              '${payload['connection_state'] ?? 'unknown'}',
                        );
                        return true;
                      },
                    );

                    // Handler: timer sync bridge for anti clock-tamper
                    _addTrustedJavaScriptHandler(
                      controller,
                      handlerName: 'timerSync',
                      callback: (args) async {
                        if (args.isEmpty || _currentSessionId == null) {
                          return false;
                        }
                        final payload = args[0];
                        if (payload is! Map) return false;

                        final sessionIdInt =
                            int.tryParse(_currentSessionId ?? '') ?? 0;
                        final serverTimeEpochMs = int.tryParse(
                                '${payload['server_time_epoch_ms'] ?? 0}') ??
                            0;
                        final remainingSeconds = int.tryParse(
                                '${payload['remaining_seconds'] ?? 0}') ??
                            0;
                        if (sessionIdInt <= 0 ||
                            serverTimeEpochMs <= 0 ||
                            remainingSeconds < 0) {
                          return false;
                        }

                        _lastServerTimeEpochMs = serverTimeEpochMs;
                        _lastKnownTimeRemainingSeconds = remainingSeconds;
                        final suspicious =
                            await _resilienceService.evaluateTimerIntegrity(
                          sessionId: sessionIdInt,
                          serverTimeEpochMs: serverTimeEpochMs,
                          remainingSeconds: remainingSeconds,
                        );

                        if (suspicious && _currentSessionId != null) {
                          await _apiService.logViolation(
                            sessionId: _currentSessionId!,
                            examId: _currentExamId,
                            type: 'SECURITY_WARNING',
                            count: 1,
                            details:
                                'Timer integrity anomaly detected by native guard',
                          );
                          unawaited(_refreshQueueIndicators());
                        }

                        await _persistResumeSnapshot(
                          serverTimeEpochMs: serverTimeEpochMs,
                          connectionState:
                              _getConnectionUiLabel(_getConnectionUiState()),
                        );
                        return true;
                      },
                    );

                    // Handler untuk exam submitted (allow exit)
                    _addTrustedJavaScriptHandler(
                      controller,
                      handlerName: 'examSubmitted',
                      callback: (args) async {
                        debugPrint('Exam submitted!');
                        setState(() {
                          _examSubmitted = true;
                        });

                        // Stop all security features
                        _stopServerCommandPolling();
                        _stopServerReconnectLoop(resetState: true);
                        _stopRuntimeSecurityMonitoring();
                        _stopAnswerJournalSyncLoop();
                        await SecurityService.stopKioskMode();
                        await SecurityService.restoreSystemUI();

                        // Clear session to prevent any more violation logging
                        await _clearCurrentSessionRuntimeData();
                        _currentSessionId = null;
                        _currentExamId = null;

                        if (!mounted) return true;

                        // Show success and allow exit
                        ScaffoldMessenger.of(this.context).showSnackBar(
                          const SnackBar(
                            content: Text(
                              'Ujian berhasil dikumpulkan! Anda dapat menutup aplikasi.',
                            ),
                            backgroundColor: Colors.green,
                            duration: Duration(seconds: 3),
                          ),
                        );
                        return true;
                      },
                    );

                    // Handler untuk log violation dari web
                    _addTrustedJavaScriptHandler(
                      controller,
                      handlerName: 'logViolation',
                      callback: (args) {
                        if (args.length >= 2 && _currentSessionId != null) {
                          final type = args[0].toString();
                          final count = int.tryParse(args[1].toString()) ?? 1;
                          final details =
                              args.length > 2 ? args[2].toString() : null;

                          if (!_isViolationTemporarilyDisabled(type)) {
                            _apiService.logViolation(
                              sessionId: _currentSessionId!,
                              type: type,
                              count: count,
                              details: details,
                            );
                          }
                        }
                        return true;
                      },
                    );

                    // Handler untuk logout - tutup aplikasi
                    _addTrustedJavaScriptHandler(
                      controller,
                      handlerName: 'userLogout',
                      callback: (args) async {
                        debugPrint(
                          'User logout - clearing credentials and closing app',
                        );

                        // IMPORTANT: Clear credentials BEFORE closing app
                        // This prevents auto-login on next app open
                        await _apiService.clearConfig();

                        // Stop kiosk mode if active
                        _stopServerCommandPolling();
                        _stopServerReconnectLoop(resetState: true);
                        _stopRuntimeSecurityMonitoring();
                        _stopAnswerJournalSyncLoop();
                        await SecurityService.stopKioskMode();
                        await SecurityService.restoreSystemUI();

                        // Exit the application immediately
                        // Don't wait - prevent WebView from showing login page
                        SystemNavigator.pop();
                        return true;
                      },
                    );

                    // Handler untuk force kick dari admin
                    _addTrustedJavaScriptHandler(
                      controller,
                      handlerName: 'forceKicked',
                      callback: (args) async {
                        final reason = args.isNotEmpty
                            ? args[0].toString()
                            : 'Dikeluarkan oleh pengawas';
                        debugPrint('🚫 Force kicked: $reason');

                        // Mark exam as submitted to allow exit
                        setState(() {
                          _examSubmitted = true;
                        });

                        // Stop all security features
                        _stopServerCommandPolling();
                        _stopServerReconnectLoop(resetState: true);
                        _stopRuntimeSecurityMonitoring();
                        _stopAnswerJournalSyncLoop();
                        await SecurityService.stopKioskMode();
                        await SecurityService.restoreSystemUI();

                        // Clear session
                        await _clearCurrentSessionRuntimeData();
                        _currentSessionId = null;
                        _currentExamId = null;

                        if (!mounted) return true;

                        // Show kicked dialog
                        showDialog(
                          context: this.context,
                          barrierDismissible: false,
                          barrierColor: Colors.red.withValues(alpha: 0.9),
                          builder: (ctx) => PopScope(
                            canPop: false,
                            child: AlertDialog(
                              backgroundColor: const Color(0xFF1e293b),
                              shape: RoundedRectangleBorder(
                                borderRadius: BorderRadius.circular(20),
                                side: const BorderSide(
                                  color: Colors.red,
                                  width: 3,
                                ),
                              ),
                              content: Column(
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  const Icon(
                                    Icons.block_rounded,
                                    color: Colors.red,
                                    size: 80,
                                  ),
                                  const SizedBox(height: 20),
                                  const Text(
                                    '🚫 ANDA DIKELUARKAN',
                                    style: TextStyle(
                                      color: Colors.red,
                                      fontSize: 24,
                                      fontWeight: FontWeight.bold,
                                    ),
                                    textAlign: TextAlign.center,
                                  ),
                                  const SizedBox(height: 16),
                                  Text(
                                    reason,
                                    style: const TextStyle(
                                      color: Colors.white,
                                      fontSize: 16,
                                    ),
                                    textAlign: TextAlign.center,
                                  ),
                                  const SizedBox(height: 24),
                                  const Text(
                                    'Anda telah dikeluarkan dari ujian oleh pengawas.\nSilakan hubungi pengawas untuk informasi lebih lanjut.',
                                    style: TextStyle(
                                      color: Colors.white70,
                                      fontSize: 12,
                                    ),
                                    textAlign: TextAlign.center,
                                  ),
                                ],
                              ),
                              actions: [
                                SizedBox(
                                  width: double.infinity,
                                  child: ElevatedButton(
                                    onPressed: () {
                                      // Close dialog first
                                      Navigator.of(ctx).pop();

                                      // Navigate to session-ended page and clear entire navigation stack
                                      // This prevents black screen by ensuring proper destination
                                      Navigator.of(this.context)
                                          .pushAndRemoveUntil(
                                        MaterialPageRoute(
                                          builder: (_) =>
                                              const SessionEndedPage(),
                                        ),
                                        (route) => false, // Remove all routes
                                      );
                                    },
                                    style: ElevatedButton.styleFrom(
                                      backgroundColor: Colors.red,
                                      foregroundColor: Colors.white,
                                      padding: const EdgeInsets.symmetric(
                                        vertical: 14,
                                      ),
                                      shape: RoundedRectangleBorder(
                                        borderRadius: BorderRadius.circular(
                                          10,
                                        ),
                                      ),
                                    ),
                                    child: const Text(
                                      'KEMBALI KE BERANDA',
                                      style: TextStyle(
                                        fontWeight: FontWeight.bold,
                                        fontSize: 14,
                                      ),
                                    ),
                                  ),
                                ),
                              ],
                            ),
                          ),
                        );
                        return true;
                      },
                    );

                    // Handler untuk force submit dari admin (submit paksa)
                    _addTrustedJavaScriptHandler(
                      controller,
                      handlerName: 'forceSubmit',
                      callback: (args) async {
                        final reason = args.isNotEmpty
                            ? args[0].toString()
                            : 'Dikumpulkan oleh pengawas';
                        debugPrint('📝 Force submit: $reason');

                        // Show snackbar notification
                        if (mounted) {
                          ScaffoldMessenger.of(context).showSnackBar(
                            SnackBar(
                              content: Row(
                                children: [
                                  const Icon(
                                    Icons.warning_amber_rounded,
                                    color: Colors.white,
                                  ),
                                  const SizedBox(width: 12),
                                  Expanded(
                                    child: Text(
                                      'Ujian dikumpulkan: $reason',
                                      style: const TextStyle(fontSize: 14),
                                    ),
                                  ),
                                ],
                              ),
                              backgroundColor: Colors.orange,
                              duration: const Duration(seconds: 5),
                              behavior: SnackBarBehavior.floating,
                            ),
                          );
                        }

                        // The web will handle the actual submission
                        // APK just needs to show notification and prepare for exit
                        return true;
                      },
                    );

                    // Handler untuk exam cancelled (ujian dibatalkan/ditunda)
                    _addTrustedJavaScriptHandler(
                      controller,
                      handlerName: 'examCancelled',
                      callback: (args) async {
                        final reason = args.isNotEmpty
                            ? args[0].toString()
                            : 'Ujian telah dibatalkan atau ditunda';
                        debugPrint('⏸️ Exam cancelled: $reason');

                        // Mark exam as submitted to allow exit
                        setState(() {
                          _examSubmitted = true;
                        });

                        // Stop all security features
                        _stopServerCommandPolling();
                        _stopServerReconnectLoop(resetState: true);
                        _stopRuntimeSecurityMonitoring();
                        _stopAnswerJournalSyncLoop();
                        await SecurityService.stopKioskMode();
                        await SecurityService.restoreSystemUI();

                        // Clear session
                        await _clearCurrentSessionRuntimeData();
                        _currentSessionId = null;
                        _currentExamId = null;

                        if (!mounted) return true;

                        // Show cancelled dialog
                        showDialog(
                          context: this.context,
                          barrierDismissible: false,
                          barrierColor: Colors.orange.withValues(alpha: 0.9),
                          builder: (ctx) => PopScope(
                            canPop: false,
                            child: AlertDialog(
                              backgroundColor: const Color(0xFF1e293b),
                              shape: RoundedRectangleBorder(
                                borderRadius: BorderRadius.circular(20),
                                side: const BorderSide(
                                  color: Colors.orange,
                                  width: 3,
                                ),
                              ),
                              content: Column(
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  const Icon(
                                    Icons.pause_circle_rounded,
                                    color: Colors.orange,
                                    size: 80,
                                  ),
                                  const SizedBox(height: 20),
                                  const Text(
                                    '⏸️ UJIAN DITUNDA',
                                    style: TextStyle(
                                      color: Colors.orange,
                                      fontSize: 22,
                                      fontWeight: FontWeight.bold,
                                    ),
                                    textAlign: TextAlign.center,
                                  ),
                                  const SizedBox(height: 16),
                                  Text(
                                    reason,
                                    style: const TextStyle(
                                      color: Colors.white,
                                      fontSize: 16,
                                    ),
                                    textAlign: TextAlign.center,
                                  ),
                                  const SizedBox(height: 24),
                                  const Text(
                                    'Ujian telah ditunda atau dibatalkan oleh pengawas.\nSilakan hubungi pengawas untuk informasi lebih lanjut.',
                                    style: TextStyle(
                                      color: Colors.white70,
                                      fontSize: 12,
                                    ),
                                    textAlign: TextAlign.center,
                                  ),
                                ],
                              ),
                              actions: [
                                SizedBox(
                                  width: double.infinity,
                                  child: ElevatedButton(
                                    onPressed: () {
                                      // Close dialog first
                                      Navigator.of(ctx).pop();

                                      // Navigate to session-ended page and clear entire navigation stack
                                      Navigator.of(this.context)
                                          .pushAndRemoveUntil(
                                        MaterialPageRoute(
                                          builder: (_) =>
                                              const SessionEndedPage(),
                                        ),
                                        (route) => false,
                                      );
                                    },
                                    style: ElevatedButton.styleFrom(
                                      backgroundColor: Colors.orange,
                                      foregroundColor: Colors.white,
                                      padding: const EdgeInsets.symmetric(
                                        vertical: 14,
                                      ),
                                      shape: RoundedRectangleBorder(
                                        borderRadius: BorderRadius.circular(10),
                                      ),
                                    ),
                                    child: const Text(
                                      'OK, SAYA MENGERTI',
                                      style: TextStyle(
                                        fontWeight: FontWeight.bold,
                                        fontSize: 14,
                                      ),
                                    ),
                                  ),
                                ),
                              ],
                            ),
                          ),
                        );
                        return true;
                      },
                    );
                  },
                  onLoadStart: (controller, url) {
                    setState(() {
                      _isLoading = true;
                      _loadingProgress = 0;
                    });
                  },
                  onProgressChanged: (controller, progress) {
                    setState(() {
                      _loadingProgress = progress / 100;
                    });
                  },
                  onLoadStop: (controller, url) async {
                    setState(() {
                      _isLoading = false;
                      _errorMessage = null;
                    });
                    _stopServerReconnectLoop(resetState: true);
                    unawaited(_apiService.flushViolationQueue());
                    unawaited(_flushAnswerJournalQueue());
                    _mainFrameRetryCount = 0;
                    _retryInProgress = false;
                    _mainFrameRetryTimer?.cancel();
                    unawaited(_refreshQueueIndicators());

                    if (!isTrustedWebOrigin(
                      url?.toString(),
                      _apiService.serverUrl,
                    )) {
                      return;
                    }

                    // Inject security info
                    await controller.evaluateJavascript(
                      source: '''
                    window.SEB = {
                      isSecure: true,
                      tabSwitchCount: $_tabSwitchCount,
                      kioskMode: $_kioskActive
                    };
                  ''',
                    );

                    // Inject autocomplete disabler on every page load
                    await controller.evaluateJavascript(
                      source: SecurityService.getJsToDisableAutocomplete(),
                    );
                    await _injectAuthNow(controller);
                  },
                  onReceivedError: (controller, request, error) {
                    if (request.isForMainFrame == true) {
                      if (_isTransientNetworkError(error.description)) {
                        unawaited(
                          _retryMainFrameLoad(
                            reason: error.description,
                            forceErrorScreen: true,
                          ),
                        );
                        return;
                      }
                      setState(() {
                        _errorMessage = 'Gagal memuat: ${error.description}';
                        _isLoading = false;
                      });
                    }
                  },
                  onReceivedHttpError: (controller, request, response) {
                    if (response.statusCode != null &&
                        response.statusCode! >= 400 &&
                        request.isForMainFrame == true) {
                      if (response.statusCode! >= 500) {
                        _enterServerOutageMode(
                          reason: 'HTTP ${response.statusCode}',
                          showErrorScreen: true,
                          triggerReloadOnRecover: true,
                        );
                        return;
                      }
                      setState(() {
                        _errorMessage = 'Error ${response.statusCode}';
                        _isLoading = false;
                      });
                    }
                  },
                  shouldOverrideUrlLoading: (controller, action) async {
                    final url = action.request.url?.toString() ?? '';
                    final serverUrl = ApiService().serverUrl;
                    final urlLower = url.toLowerCase();

                    // Require an exact scheme, host, and port match.
                    if (isTrustedWebOrigin(url, serverUrl)) {
                      return NavigationActionPolicy.ALLOW;
                    }
                    if (url.startsWith('data:') || url.startsWith('blob:')) {
                      return NavigationActionPolicy.ALLOW;
                    }

                    // YOUTUBE EMBED RESTRICTION
                    // Allow only youtube.com/embed URLs (the actual video player)
                    // Block all other YouTube URLs (channel, watch, settings, etc.)
                    if (urlLower.contains('youtube.com') ||
                        urlLower.contains('youtu.be') ||
                        urlLower.contains('youtube-nocookie.com')) {
                      // Only allow /embed/ paths
                      if (urlLower.contains('/embed/')) {
                        debugPrint('🎬 YouTube embed allowed: $url');
                        return NavigationActionPolicy.ALLOW;
                      }
                      // Block all other YouTube navigation (channel, watch, settings, etc.)
                      debugPrint('🚫 YouTube navigation blocked: $url');
                      return NavigationActionPolicy.CANCEL;
                    }

                    // Block other social/video platforms that could distract
                    final blockedDomains = [
                      'facebook.com',
                      'twitter.com',
                      'x.com',
                      'instagram.com',
                      'tiktok.com',
                      'vimeo.com',
                      'dailymotion.com',
                      'twitch.tv',
                      'google.com/accounts',
                      'accounts.google.com',
                    ];
                    for (final domain in blockedDomains) {
                      if (urlLower.contains(domain)) {
                        debugPrint('🚫 Blocked domain: $domain in $url');
                        return NavigationActionPolicy.CANCEL;
                      }
                    }

                    // Block external URLs
                    _showBlockedUrlDialog(url);
                    return NavigationActionPolicy.CANCEL;
                  },
                  // Auto-confirm "beforeunload" dialog (prevents "changes won't be saved" popup)
                  onJsBeforeUnload: (controller, jsBeforeUnloadRequest) async {
                    debugPrint('onJsBeforeUnload triggered - auto confirming');
                    // Return action CONFIRM to proceed without showing dialog
                    return JsBeforeUnloadResponse(
                      handledByClient: true,
                      action: JsBeforeUnloadResponseAction.CONFIRM,
                    );
                  },
                  // Handle fullscreen for YouTube embeds
                  onEnterFullscreen: (controller) {
                    debugPrint('🎬 Entering fullscreen (YouTube video)');
                    // Hide system UI for immersive fullscreen experience
                    SystemChrome.setEnabledSystemUIMode(
                      SystemUiMode.immersiveSticky,
                    );
                  },
                  onExitFullscreen: (controller) {
                    debugPrint('🎬 Exiting fullscreen');
                    // Restore system UI
                    SystemChrome.setEnabledSystemUIMode(
                      SystemUiMode.edgeToEdge,
                    );
                  },
                ),
              if (!_authPrepared)
                const LoadingOverlay(message: 'Menyiapkan keamanan APK...'),

              // Loading indicator
              if (_isLoading)
                Positioned(
                  top: 0,
                  left: 0,
                  right: 0,
                  child: LinearProgressIndicator(
                    value: _loadingProgress > 0 ? _loadingProgress : null,
                    backgroundColor: Colors.transparent,
                    valueColor: const AlwaysStoppedAnimation<Color>(
                      Color(0xFF3b82f6),
                    ),
                    minHeight: 3,
                  ),
                ),

              // Full loading overlay
              if (_isLoading && _loadingProgress < 0.3)
                const LoadingOverlay(message: 'Memuat halaman ujian...'),

              if (AppConfig.showConnectionBadge)
                Positioned(
                  right: 10,
                  bottom: 10,
                  child: _buildConnectionBadge(),
                ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildSecurityWarningScreen() {
    return Scaffold(
      backgroundColor: const Color(0xFF0f172a),
      body: SafeArea(
        child: Center(
          child: Padding(
            padding: const EdgeInsets.all(32),
            child: GlassContainer(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Container(
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      color: Colors.orange.withValues(alpha: 0.2),
                      shape: BoxShape.circle,
                    ),
                    child: const Icon(
                      Icons.warning_amber_rounded,
                      size: 48,
                      color: Colors.orange,
                    ),
                  ),
                  const SizedBox(height: 24),
                  const Text(
                    'Peringatan Keamanan',
                    style: TextStyle(
                      color: Colors.white,
                      fontSize: 22,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                  const SizedBox(height: 16),
                  Text(
                    _securityWarningMessage,
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      color: Colors.white.withValues(alpha: 0.7),
                      fontSize: 14,
                    ),
                  ),
                  const SizedBox(height: 24),
                  Text(
                    'Anda tetap dapat melanjutkan ujian, namun pelanggaran ini akan dicatat.',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      color: Colors.white.withValues(alpha: 0.5),
                      fontSize: 12,
                    ),
                  ),
                  const SizedBox(height: 32),
                  GradientButton(
                    text: 'Lanjutkan Ujian',
                    icon: Icons.play_arrow_rounded,
                    colors: const [Color(0xFFf59e0b), Color(0xFFd97706)],
                    onPressed: () {
                      setState(() {
                        _showSecurityWarning = false;
                      });
                    },
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildErrorScreen() {
    return Scaffold(
      backgroundColor: const Color(0xFF0f172a),
      body: SafeArea(
        child: Center(
          child: Padding(
            padding: const EdgeInsets.all(32),
            child: GlassContainer(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Container(
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      color: Colors.red.withValues(alpha: 0.2),
                      shape: BoxShape.circle,
                    ),
                    child: const Icon(
                      Icons.error_outline_rounded,
                      size: 48,
                      color: Colors.red,
                    ),
                  ),
                  const SizedBox(height: 24),
                  const Text(
                    'Terjadi Kesalahan',
                    style: TextStyle(
                      color: Colors.white,
                      fontSize: 22,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                  const SizedBox(height: 16),
                  Text(
                    _errorMessage ?? 'Unknown error',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      color: Colors.white.withValues(alpha: 0.7),
                      fontSize: 14,
                    ),
                  ),
                  if (AppConfig.showConnectionBadge) ...[
                    const SizedBox(height: 14),
                    _buildConnectionBadge(),
                  ],
                  const SizedBox(height: 32),
                  GradientButton(
                    text: 'Coba Lagi',
                    icon: Icons.refresh_rounded,
                    onPressed: () {
                      setState(() {
                        _errorMessage = null;
                        _isLoading = true;
                      });
                      _mainFrameRetryCount = 0;
                      _retryInProgress = false;
                      _mainFrameRetryTimer?.cancel();
                      unawaited(_loadMainFrame());
                    },
                  ),
                  if (AppConfig.enableDiagnosticsQuickExport &&
                      _currentSessionId != null &&
                      !_examSubmitted) ...[
                    const SizedBox(height: 12),
                    GradientButton(
                      text: 'Export Diagnostik',
                      icon: Icons.fact_check_outlined,
                      colors: const [Color(0xFF0ea5e9), Color(0xFF0369a1)],
                      onPressed: () {
                        unawaited(_showDiagnosticBundleDialog());
                      },
                    ),
                  ],
                  if (_allowEmergencyExit &&
                      _currentSessionId != null &&
                      !_examSubmitted) ...[
                    const SizedBox(height: 12),
                    GradientButton(
                      text: 'Keluar Darurat',
                      icon: Icons.exit_to_app_rounded,
                      colors: const [Color(0xFFf59e0b), Color(0xFFea580c)],
                      onPressed: _showEmergencyOfflineExitDialog,
                    ),
                  ],
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  void _showEmergencyOfflineExitDialog() {
    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (ctx) => AlertDialog(
        backgroundColor: const Color(0xFF1e293b),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(16),
          side: const BorderSide(color: Colors.orange, width: 2),
        ),
        title: const Text(
          'Keluar Darurat',
          style: TextStyle(color: Colors.orange, fontWeight: FontWeight.bold),
        ),
        content: const Text(
          'Server tidak merespons cukup lama.\n\n'
          'Keluar darurat akan menghentikan sesi lokal agar Anda tidak terjebak di aplikasi. '
          'Tindakan ini akan dicatat sebagai insiden dan disinkronkan saat koneksi pulih.',
          style: TextStyle(color: Colors.white),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(),
            child: const Text('Batal'),
          ),
          ElevatedButton(
            onPressed: () async {
              Navigator.of(ctx).pop();
              await _performEmergencyOfflineExit();
            },
            style: ElevatedButton.styleFrom(backgroundColor: Colors.orange),
            child: const Text('Ya, Keluar Darurat'),
          ),
        ],
      ),
    );
  }

  Future<void> _performEmergencyOfflineExit() async {
    if (_currentSessionId != null) {
      await _apiService
          .logViolation(
            sessionId: _currentSessionId!,
            examId: _currentExamId,
            type: 'EMERGENCY_EXIT_OFFLINE',
            count: 1,
            details:
                'Emergency exit activated due to prolonged server outage ($_serverOutageProbeFailures failed probes)',
          )
          .timeout(
            const Duration(seconds: 2),
            onTimeout: () => false,
          );
    }

    _stopServerCommandPolling();
    _stopServerReconnectLoop(resetState: true);
    _stopRuntimeSecurityMonitoring();
    _stopAnswerJournalSyncLoop();
    await _clearCurrentSessionRuntimeData();
    setState(() {
      _examSubmitted = true;
      _currentSessionId = null;
      _currentExamId = null;
    });

    await SecurityService.stopKioskMode();
    await SecurityService.restoreSystemUI();
    SecurityService.enableClipboard();

    if (!mounted) return;
    SystemNavigator.pop();
  }

  Future<void> _showDiagnosticBundleDialog() async {
    final sessionId = int.tryParse(_currentSessionId ?? '') ?? 0;
    if (sessionId <= 0) return;

    final bundle = await _resilienceService.exportDiagnosticBundle(
      sessionId: sessionId,
    );
    if (!mounted) return;

    if (bundle == null || bundle.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Gagal membuat diagnostic bundle.'),
          backgroundColor: Colors.red,
          duration: Duration(seconds: 2),
        ),
      );
      return;
    }

    final preview =
        bundle.length > 1200 ? '${bundle.substring(0, 1200)}...' : bundle;
    showDialog(
      context: context,
      barrierDismissible: true,
      builder: (ctx) => AlertDialog(
        backgroundColor: const Color(0xFF111827),
        title: const Text(
          'Diagnostic Bundle',
          style: TextStyle(color: Colors.white),
        ),
        content: SizedBox(
          width: double.maxFinite,
          child: SingleChildScrollView(
            child: SelectableText(
              preview,
              style: const TextStyle(
                color: Colors.white70,
                fontSize: 12,
                fontFamily: 'monospace',
              ),
            ),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(),
            child: const Text('Tutup'),
          ),
          ElevatedButton(
            onPressed: () async {
              await Clipboard.setData(ClipboardData(text: bundle));
              if (!mounted) return;
              Navigator.of(context).pop();
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(
                  content: Text('Diagnostic bundle disalin ke clipboard.'),
                  backgroundColor: Colors.green,
                  duration: Duration(seconds: 2),
                ),
              );
            },
            child: const Text('Salin'),
          ),
        ],
      ),
    );
  }

  void _showExitWarning() {
    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (context) => Dialog(
        backgroundColor: Colors.transparent,
        child: GlassContainer(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(
                Icons.block_rounded,
                size: 48,
                color: Color(0xFFef4444),
              ),
              const SizedBox(height: 16),
              const Text(
                'Tidak Dapat Keluar',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 18,
                  fontWeight: FontWeight.bold,
                ),
              ),
              const SizedBox(height: 12),
              Text(
                'Anda tidak dapat keluar dari aplikasi selama ujian berlangsung.',
                textAlign: TextAlign.center,
                style: TextStyle(
                  color: Colors.white.withValues(alpha: 0.7),
                  fontSize: 14,
                ),
              ),
              const SizedBox(height: 24),
              SizedBox(
                width: double.infinity,
                child: GradientButton(
                  text: 'Mengerti',
                  onPressed: () => Navigator.of(context).pop(),
                ),
              ),
              if (_allowEmergencyExit &&
                  _currentSessionId != null &&
                  !_examSubmitted) ...[
                const SizedBox(height: 10),
                SizedBox(
                  width: double.infinity,
                  child: GradientButton(
                    text: 'Keluar Darurat',
                    icon: Icons.exit_to_app_rounded,
                    colors: const [Color(0xFFf59e0b), Color(0xFFea580c)],
                    onPressed: () {
                      Navigator.of(context).pop();
                      _showEmergencyOfflineExitDialog();
                    },
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }

  void _showBlockedUrlDialog(String url) {
    showDialog(
      context: context,
      builder: (context) => Dialog(
        backgroundColor: Colors.transparent,
        child: GlassContainer(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(
                Icons.link_off_rounded,
                size: 48,
                color: Color(0xFFef4444),
              ),
              const SizedBox(height: 16),
              const Text(
                'URL Diblokir',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 18,
                  fontWeight: FontWeight.bold,
                ),
              ),
              const SizedBox(height: 12),
              Text(
                'Akses ke URL eksternal tidak diizinkan selama ujian.',
                textAlign: TextAlign.center,
                style: TextStyle(
                  color: Colors.white.withValues(alpha: 0.7),
                  fontSize: 14,
                ),
              ),
              const SizedBox(height: 24),
              SizedBox(
                width: double.infinity,
                child: GradientButton(
                  text: 'OK',
                  onPressed: () => Navigator.of(context).pop(),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _screenshotCallback.dispose(); // Clean up screenshot listener
    _stopRuntimeSecurityMonitoring();
    _stopAnswerJournalSyncLoop();
    _securityService.dispose();
    _stopServerCommandPolling(); // Stop polling when page is disposed
    _stopServerReconnectLoop(resetState: true);
    _violationDebounceTimer?.cancel(); // Clean up debounce timer
    _mainFrameRetryTimer?.cancel();

    if (_kioskActive) {
      SecurityService.stopKioskMode();
    }
    SecurityService.restoreSystemUI();
    SecurityService.enableClipboard(); // Restore clipboard

    super.dispose();
  }
}
