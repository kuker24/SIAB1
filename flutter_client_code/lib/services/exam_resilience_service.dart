import 'dart:convert';
import 'dart:math';
import 'dart:typed_data';

import 'package:crypto/crypto.dart';
import 'package:encrypt/encrypt.dart' as encrypt;
import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../config.dart';
import 'api_service.dart';

class ExamResilienceService {
  static final ExamResilienceService _instance =
      ExamResilienceService._internal();
  factory ExamResilienceService() => _instance;

  final FlutterSecureStorage _storage = const FlutterSecureStorage();
  final ApiService _apiService = ApiService();

  static const String _offlinePackageKey = 'sxb_offline_package_v2';
  static const String _answerJournalKey = 'sxb_answer_journal_v2';
  static const String _resumeStateKey = 'sxb_resume_state_v2';
  static const String _diagnosticEventsKey = 'sxb_diag_events_v2';
  static const String _journalBackoffUntilKey =
      'sxb_journal_backoff_until_ms_v1';

  static const int _maxJournalEvents = 5000;
  static const int _maxDiagnosticEvents = 400;

  bool _journalSyncInFlight = false;
  int _journalFailureStreak = 0;

  ExamResilienceService._internal();

  encrypt.Key _deriveKey() {
    const seed =
        '${AppConfig.buildToken}|${AppConfig.serverUrl}|${AppConfig.appName}';
    final digest = sha256.convert(utf8.encode(seed));
    return encrypt.Key(Uint8List.fromList(digest.bytes));
  }

  String _randomSuffix([int length = 6]) {
    const chars = 'abcdefghijklmnopqrstuvwxyz0123456789';
    final random = Random.secure();
    return List.generate(length, (_) => chars[random.nextInt(chars.length)])
        .join();
  }

  String _encryptMap(Map<String, dynamic> payload) {
    final key = _deriveKey();
    final ivBytes = List<int>.generate(16, (_) => Random.secure().nextInt(256));
    final iv = encrypt.IV(Uint8List.fromList(ivBytes));
    final cipher =
        encrypt.Encrypter(encrypt.AES(key, mode: encrypt.AESMode.cbc));
    final plaintext = jsonEncode(payload);
    final encrypted = cipher.encrypt(plaintext, iv: iv);
    return '${iv.base64}.${encrypted.base64}';
  }

  Map<String, dynamic>? _decryptMap(String? ciphertext) {
    if (ciphertext == null || ciphertext.isEmpty) return null;
    final parts = ciphertext.split('.');
    if (parts.length != 2) return null;

    try {
      final key = _deriveKey();
      final iv = encrypt.IV.fromBase64(parts[0]);
      final encrypted = encrypt.Encrypted.fromBase64(parts[1]);
      final cipher =
          encrypt.Encrypter(encrypt.AES(key, mode: encrypt.AESMode.cbc));
      final jsonText = cipher.decrypt(encrypted, iv: iv);
      final decoded = jsonDecode(jsonText);
      if (decoded is Map<String, dynamic>) {
        return decoded;
      }
      if (decoded is Map) {
        return Map<String, dynamic>.from(decoded);
      }
      return null;
    } catch (_) {
      return null;
    }
  }

  dynamic _canonicalizeJson(dynamic value) {
    if (value is Map) {
      final keys = value.keys.map((k) => k.toString()).toList()..sort();
      final result = <String, dynamic>{};
      for (final key in keys) {
        result[key] = _canonicalizeJson(value[key]);
      }
      return result;
    }
    if (value is List) {
      return value.map(_canonicalizeJson).toList();
    }
    return value;
  }

  String _sha256OfJson(dynamic value) {
    final canonical = _canonicalizeJson(value);
    final encoded = jsonEncode(canonical);
    return sha256.convert(utf8.encode(encoded)).toString();
  }

  Future<Map<String, dynamic>> _readJournalState() async {
    final raw = await _storage.read(key: _answerJournalKey);
    final parsed = _decryptMap(raw);
    if (parsed == null) {
      return {
        'next_sequence': 1,
        'events': <Map<String, dynamic>>[],
      };
    }

    final events = <Map<String, dynamic>>[];
    final decodedEvents = parsed['events'];
    if (decodedEvents is List) {
      for (final item in decodedEvents) {
        if (item is Map) {
          events.add(Map<String, dynamic>.from(item));
        }
      }
    }

    return {
      'next_sequence': int.tryParse('${parsed['next_sequence'] ?? 1}') ?? 1,
      'events': events,
    };
  }

  Future<void> _writeJournalState(Map<String, dynamic> state) async {
    final payload = {
      'next_sequence': int.tryParse('${state['next_sequence'] ?? 1}') ?? 1,
      'events': state['events'] ?? <Map<String, dynamic>>[],
      'updated_at_ms': DateTime.now().millisecondsSinceEpoch,
    };
    await _storage.write(key: _answerJournalKey, value: _encryptMap(payload));
  }

  Future<void> _appendDiagnosticEvent(
    String event, {
    Map<String, dynamic>? data,
  }) async {
    final raw = await _storage.read(key: _diagnosticEventsKey);
    final parsed = _decryptMap(raw) ??
        <String, dynamic>{'events': <Map<String, dynamic>>[]};

    final events = <Map<String, dynamic>>[];
    if (parsed['events'] is List) {
      for (final item in (parsed['events'] as List)) {
        if (item is Map) {
          events.add(Map<String, dynamic>.from(item));
        }
      }
    }

    events.add({
      'event': event,
      'at_ms': DateTime.now().millisecondsSinceEpoch,
      'data': data ?? <String, dynamic>{},
    });

    if (events.length > _maxDiagnosticEvents) {
      events.removeRange(0, events.length - _maxDiagnosticEvents);
    }

    await _storage.write(
      key: _diagnosticEventsKey,
      value: _encryptMap({'events': events}),
    );
  }

  Future<void> preloadOfflinePackage({required int sessionId}) async {
    if (!AppConfig.enableOfflineFirstRuntime || sessionId <= 0) {
      return;
    }

    final package = await _apiService.fetchOfflineExamPackage(sessionId);
    if (package == null || package['payload'] == null) {
      await _appendDiagnosticEvent('offline_package_fetch_failed', data: {
        'session_id': sessionId,
      });
      return;
    }

    final payload = package['payload'];
    final expectedHash = '${package['package_hash'] ?? ''}'.trim();
    final actualHash = _sha256OfJson(payload);
    if (expectedHash.isNotEmpty && expectedHash != actualHash) {
      await _appendDiagnosticEvent('offline_package_hash_mismatch', data: {
        'session_id': sessionId,
      });
      return;
    }

    final envelope = {
      'session_id': sessionId,
      'package': package,
      'cached_at_ms': DateTime.now().millisecondsSinceEpoch,
    };
    await _storage.write(key: _offlinePackageKey, value: _encryptMap(envelope));

    await _appendDiagnosticEvent('offline_package_cached', data: {
      'session_id': sessionId,
      'package_id': package['package_id'],
    });
  }

  Future<Map<String, dynamic>?> getCachedOfflinePackage(int sessionId) async {
    final raw = await _storage.read(key: _offlinePackageKey);
    final parsed = _decryptMap(raw);
    if (parsed == null) return null;

    final parsedSessionId = int.tryParse('${parsed['session_id'] ?? 0}') ?? 0;
    if (parsedSessionId != sessionId) {
      return null;
    }

    final pkg = parsed['package'];
    if (pkg is Map<String, dynamic>) {
      return pkg;
    }
    if (pkg is Map) {
      return Map<String, dynamic>.from(pkg);
    }
    return null;
  }

  Future<void> appendAnswerEvent({
    required int sessionId,
    required int questionId,
    required Map<String, dynamic> answerPayload,
  }) async {
    if (!AppConfig.enableOfflineFirstRuntime ||
        sessionId <= 0 ||
        questionId <= 0) {
      return;
    }

    final state = await _readJournalState();
    final nextSeq = int.tryParse('${state['next_sequence'] ?? 1}') ?? 1;
    final nowMs = DateTime.now().millisecondsSinceEpoch;
    final eventId = 'jr_${sessionId}_${nextSeq}_${nowMs}_${_randomSuffix(5)}';

    final eventPayload = <String, dynamic>{};
    final selectedOptionId = answerPayload['selected_option_id'];
    if (selectedOptionId != null) {
      eventPayload['selected_option_id'] =
          int.tryParse('$selectedOptionId') ?? selectedOptionId;
    }

    final selectedOptionIds = answerPayload['selected_option_ids'];
    if (selectedOptionIds is List) {
      eventPayload['selected_option_ids'] = selectedOptionIds;
    }

    final answerText = answerPayload['answer_text'];
    if (answerText != null) {
      eventPayload['answer_text'] = '$answerText';
    }

    final statementAnswers = answerPayload['statement_answers'];
    if (statementAnswers is Map) {
      eventPayload['statement_answers'] =
          Map<String, dynamic>.from(statementAnswers);
    }

    final answerMetadata = answerPayload['answer_metadata'];
    if (answerMetadata is Map) {
      eventPayload['answer_metadata'] =
          Map<String, dynamic>.from(answerMetadata);
    }

    if (eventPayload.isEmpty) {
      return;
    }

    final events = <Map<String, dynamic>>[];
    final rawEvents = state['events'];
    if (rawEvents is List) {
      for (final item in rawEvents) {
        if (item is Map) {
          events.add(Map<String, dynamic>.from(item));
        }
      }
    }

    events.add({
      'event_id': eventId,
      'session_id': sessionId,
      'sequence': nextSeq,
      'question_id': questionId,
      'local_timestamp_ms': nowMs,
      ...eventPayload,
    });

    if (events.length > _maxJournalEvents) {
      events.removeRange(0, events.length - _maxJournalEvents);
    }

    await _writeJournalState({
      'next_sequence': nextSeq + 1,
      'events': events,
    });

    await _appendDiagnosticEvent('journal_event_appended', data: {
      'session_id': sessionId,
      'question_id': questionId,
      'event_id': eventId,
      'pending_events': events
          .where(
            (e) =>
                (int.tryParse('${e['session_id'] ?? sessionId}') ??
                    sessionId) ==
                sessionId,
          )
          .length,
    });
  }

  Future<int> getPendingAnswerEventCount(int sessionId) async {
    if (sessionId <= 0) return 0;
    final state = await _readJournalState();
    final events = state['events'];
    if (events is! List) return 0;

    int count = 0;
    for (final item in events) {
      if (item is! Map) continue;
      final sid =
          int.tryParse('${item['session_id'] ?? sessionId}') ?? sessionId;
      if (sid == sessionId) {
        count += 1;
      }
    }
    return count;
  }

  Future<int> flushAnswerJournal({
    required int sessionId,
    int batchSize = 80,
  }) async {
    if (sessionId <= 0 || _journalSyncInFlight) {
      return 0;
    }

    final nowMs = DateTime.now().millisecondsSinceEpoch;
    final backoffUntilRaw = await _storage.read(key: _journalBackoffUntilKey);
    final backoffUntil = int.tryParse('${backoffUntilRaw ?? 0}') ?? 0;
    if (backoffUntil > nowMs) {
      return 0;
    }

    final state = await _readJournalState();
    final allEvents = <Map<String, dynamic>>[];
    final decoded = state['events'];
    if (decoded is List) {
      for (final item in decoded) {
        if (item is Map) {
          allEvents.add(Map<String, dynamic>.from(item));
        }
      }
    }

    if (allEvents.isEmpty) {
      return 0;
    }

    allEvents.sort((a, b) {
      final seqA = int.tryParse('${a['sequence'] ?? 0}') ?? 0;
      final seqB = int.tryParse('${b['sequence'] ?? 0}') ?? 0;
      if (seqA != seqB) return seqA.compareTo(seqB);
      final tsA = int.tryParse('${a['local_timestamp_ms'] ?? 0}') ?? 0;
      final tsB = int.tryParse('${b['local_timestamp_ms'] ?? 0}') ?? 0;
      return tsA.compareTo(tsB);
    });

    final targetBatchSize = batchSize < 1
        ? 1
        : batchSize > 200
            ? 200
            : batchSize;

    final eventsToSync = allEvents.take(targetBatchSize).toList();

    _journalSyncInFlight = true;
    try {
      final response = await _apiService.syncAnswerJournal(
        sessionId: sessionId,
        events: eventsToSync,
      );
      if (response == null) {
        _journalFailureStreak = (_journalFailureStreak + 1).clamp(0, 6);
        final delay = _apiService.computeBackoffDelay(
          failureStreak: _journalFailureStreak,
          retryAfterSeconds: _apiService.lastRetryAfterSeconds,
          baseRetryAfterSeconds: _apiService.runtimeRetryAfterSeconds,
        );
        final untilMs = nowMs + delay.inMilliseconds;
        await _storage.write(key: _journalBackoffUntilKey, value: '$untilMs');
        await _appendDiagnosticEvent('journal_sync_failed', data: {
          'session_id': sessionId,
          'batch_size': eventsToSync.length,
          'failure_streak': _journalFailureStreak,
          'backoff_ms': delay.inMilliseconds,
          'retry_after_seconds': _apiService.lastRetryAfterSeconds,
        });
        return 0;
      }

      _journalFailureStreak = 0;
      await _storage.delete(key: _journalBackoffUntilKey);

      final ackedEventIds = <String>{};
      final acks = response['acks'];
      if (acks is List) {
        for (final ack in acks) {
          if (ack is! Map) continue;
          final status = '${ack['status'] ?? ''}'.trim().toLowerCase();
          final eventId = '${ack['event_id'] ?? ''}'.trim().toLowerCase();
          if (eventId.isEmpty) continue;
          if (status == 'applied' || status == 'duplicate') {
            ackedEventIds.add(eventId);
          }
        }
      }

      if (ackedEventIds.isEmpty) {
        return 0;
      }

      final remainingEvents = allEvents.where((event) {
        final eventId = '${event['event_id'] ?? ''}'.trim().toLowerCase();
        return !ackedEventIds.contains(eventId);
      }).toList();

      await _writeJournalState({
        'next_sequence': state['next_sequence'] ?? 1,
        'events': remainingEvents,
      });

      await _appendDiagnosticEvent('journal_sync_success', data: {
        'session_id': sessionId,
        'acked_events': ackedEventIds.length,
        'remaining_events': remainingEvents.length,
      });

      return ackedEventIds.length;
    } finally {
      _journalSyncInFlight = false;
    }
  }

  Future<void> persistResumeState({
    required int sessionId,
    required int currentQuestionIndex,
    required int timeRemainingSeconds,
    required int queuedViolationCount,
    required int pendingAnswerEvents,
    int? serverTimeEpochMs,
    String? connectionState,
  }) async {
    if (sessionId <= 0) return;

    final payload = {
      'session_id': sessionId,
      'current_question_index': currentQuestionIndex,
      'time_remaining_seconds': timeRemainingSeconds,
      'queued_violation_count': queuedViolationCount,
      'pending_answer_events': pendingAnswerEvents,
      'connection_state': connectionState ?? 'unknown',
      'server_time_epoch_ms': serverTimeEpochMs,
      'saved_at_ms': DateTime.now().millisecondsSinceEpoch,
    };

    await _storage.write(key: _resumeStateKey, value: _encryptMap(payload));
  }

  Future<Map<String, dynamic>?> getResumeState(int sessionId) async {
    if (sessionId <= 0) return null;
    final raw = await _storage.read(key: _resumeStateKey);
    final parsed = _decryptMap(raw);
    if (parsed == null) return null;

    final storedSessionId = int.tryParse('${parsed['session_id'] ?? 0}') ?? 0;
    if (storedSessionId != sessionId) return null;
    return parsed;
  }

  Future<void> clearResumeState() async {
    await _storage.delete(key: _resumeStateKey);
  }

  Future<bool> evaluateTimerIntegrity({
    required int sessionId,
    required int serverTimeEpochMs,
    required int remainingSeconds,
  }) async {
    final previous = await getResumeState(sessionId);
    if (previous == null) {
      return false;
    }

    final prevServerMs =
        int.tryParse('${previous['server_time_epoch_ms'] ?? 0}') ?? 0;
    final prevRemaining =
        int.tryParse('${previous['time_remaining_seconds'] ?? 0}') ?? 0;

    if (prevServerMs <= 0 || prevRemaining <= 0) {
      return false;
    }

    final serverDeltaSec = (serverTimeEpochMs - prevServerMs) / 1000.0;
    final remainingDeltaSec = (prevRemaining - remainingSeconds).toDouble();

    if (serverDeltaSec < -1.0) {
      await _appendDiagnosticEvent('timer_guard_server_backwards', data: {
        'session_id': sessionId,
        'server_delta_sec': serverDeltaSec,
      });
      return true;
    }

    if (remainingDeltaSec < -3) {
      await _appendDiagnosticEvent('timer_guard_remaining_increased', data: {
        'session_id': sessionId,
        'remaining_delta_sec': remainingDeltaSec,
      });
      return true;
    }

    final drift = (remainingDeltaSec - serverDeltaSec).abs();
    final driftThreshold = AppConfig.timerGuardMaxDriftSeconds <= 0
        ? 12.0
        : AppConfig.timerGuardMaxDriftSeconds.toDouble();
    if (drift > driftThreshold) {
      await _appendDiagnosticEvent('timer_guard_drift_large', data: {
        'session_id': sessionId,
        'drift_sec': drift,
      });
      return true;
    }

    return false;
  }

  Future<String?> exportDiagnosticBundle({required int sessionId}) async {
    final rawDiag = await _storage.read(key: _diagnosticEventsKey);
    final diagParsed = _decryptMap(rawDiag) ??
        <String, dynamic>{'events': <Map<String, dynamic>>[]};
    final resumeState = await getResumeState(sessionId);
    final offlinePackage = await getCachedOfflinePackage(sessionId);
    final pendingEvents = await getPendingAnswerEventCount(sessionId);

    final bundle = {
      'session_id': sessionId,
      'generated_at_ms': DateTime.now().millisecondsSinceEpoch,
      'resilience_profile': AppConfig.resilienceProfile,
      'build_token': AppConfig.buildToken,
      'server_url': AppConfig.serverUrl,
      'pending_answer_events': pendingEvents,
      'resume_state': resumeState,
      'offline_package_meta': {
        'package_id': offlinePackage?['package_id'],
        'cached_payload_hash': offlinePackage?['package_hash'],
      },
      'events': diagParsed['events'] ?? <Map<String, dynamic>>[],
    };

    final encrypted = _encryptMap(bundle);
    await _appendDiagnosticEvent('diagnostic_bundle_exported', data: {
      'session_id': sessionId,
      'pending_answer_events': pendingEvents,
    });
    return encrypted;
  }

  Future<void> clearSessionRuntimeData(int sessionId) async {
    await clearResumeState();

    final journalState = await _readJournalState();
    final events = <Map<String, dynamic>>[];
    if (journalState['events'] is List) {
      for (final item in journalState['events'] as List) {
        if (item is Map) {
          events.add(Map<String, dynamic>.from(item));
        }
      }
    }

    final remaining = events.where((item) {
      final sid =
          int.tryParse('${item['session_id'] ?? sessionId}') ?? sessionId;
      return sid != sessionId;
    }).toList();

    await _writeJournalState({
      'next_sequence': journalState['next_sequence'] ?? 1,
      'events': remaining,
    });
  }
}
