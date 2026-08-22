class ExamSystem {
    constructor(sessionId, examId, durationMinutes, startTime, showResults = true) {
        this.sessionId = sessionId;
        this.examId = examId;
        this.durationMinutes = durationMinutes;
        this.questions = [];
        this.answers = {};
        this.flagged = new Set();
        this.currentQuestionIndex = 0;
        this.timeRemaining = durationMinutes * 60;
        this.startTime = new Date(startTime || Date.now());
        if (Number.isNaN(this.startTime.getTime())) {
            this.startTime = new Date();
        }
        this.endTime = new Date(this.startTime.getTime() + (durationMinutes * 60 * 1000));
        this.timerInterval = null;
        this.autoSaveInterval = null;
        this.isPaused = false;
        this.globallyPaused = false;
        this.pausedAt = null;
        this.elapsedBeforePause = 0;
        this.autoSaveTimer = null;
        this.showResults = showResults;  // Store show_results flag

        this.flagged = new Set();
        this.serverTimeOffset = 0; // milliseconds offset from server time
        this.shuffleQuestions = false;
        this.shuffleOptions = false;
        this.answerRevisions = {};
        this.serverSubmitHandled = false;
        this.serverKickHandled = false;
        this.submitInProgress = false;
        this.pendingSyncTimeout = null;
        this.runtimePolicy = {
            auto_save_interval_ms: 35000,
            answer_sync_debounce_ms: 15000,
            answer_sync_interval_seconds: 15,
            answer_sync_batch_size: 30,
            retry_after_seconds: 8,
            final_submit_priority: true
        };
        this.lastViolationTimestamps = {};
        this.wsReconnectAttempts = 0;
        this.wsReconnectTimer = null;
        this.wsReconnectEnabled = true;
        this.wsAuthFailed = false;
        this.lastNativeTimerSyncAt = 0;
        this.lastNativeStateSyncAt = 0;

        this.init();
    }

    async init() {
        console.log('Exam System initialized v4.1');


        // Initialize offline storage
        await this.initOfflineStorage();
        if (syncWorker && this.sessionId) {
            syncWorker.start(this.sessionId);
        }

        // Initialize server time sync
        await this.initServerTimeSync();

        // Pull runtime policy (degrade/normal) before timers start.
        await this.loadRuntimePolicy();

        // Initialize WebSocket for real-time pause/resume and heartbeat
        this.initWebSocket();

        this.setupAutoSave();
        this.setupTimer();
        this.setupBeforeUnload();
        this.setupKeyboardNavigation();

        // Setup clipboard protection
        this.setupClipboardProtection();

        this.saveSessionToStorage();

        // Notify Flutter app that session has started (for security features)
        this.notifyFlutterSessionStart();

        // Initialize violation counter
        this.clipboardViolationCount = 0;
        this.totalViolationCount = 0;
    }

    shouldThrottleViolation(key, cooldownMs = 1200) {
        const now = Date.now();
        const lastAt = this.lastViolationTimestamps[key] || 0;
        if (now - lastAt < cooldownMs) {
            return true;
        }
        this.lastViolationTimestamps[key] = now;
        return false;
    }

    isClipboardLikeViolation(eventType, eventData = {}) {
        const normalizedType = String(eventType || '').toLowerCase().replace(/^violation_/, '');
        const action = String(eventData.action || '').toLowerCase();
        return ['copy', 'paste', 'cut', 'clipboard_violation'].includes(normalizedType)
            || ['copy', 'paste', 'cut', 'keyboard_ctrl_c', 'keyboard_ctrl_v', 'keyboard_ctrl_x'].includes(action);
    }

    getViolationLabel(type) {
        const normalizedType = String(type || '').toLowerCase().replace(/^violation_/, '');
        const labels = {
            tab_switch: 'Pindah Tab',
            focus_lost: 'Fokus Hilang',
            browser_minimize: 'Browser Diminimize',
            copy: 'Copy',
            paste: 'Paste',
            cut: 'Cut',
            right_click: 'Klik Kanan',
            clipboard_violation: 'Akses Clipboard',
            devtools_attempt: 'Developer Tools',
            devtools_open: 'Developer Tools',
            screenshot_attempt: 'Screenshot',
            screen_recording: 'Rekam Layar',
            overlay_app: 'Overlay App',
            external_display: 'Display Eksternal',
            accessibility_risk: 'Aksesibilitas Berisiko',
            apk_tampering: 'APK Dimodifikasi',
            security_warning: 'Peringatan Keamanan'
        };
        return labels[normalizedType] || normalizedType.replace(/_/g, ' ').trim() || 'Pelanggaran';
    }

    async logBrowserViolation(eventType, eventData = {}, options = {}) {
        const throttleKey = options.throttleKey || eventType;
        const cooldownMs = options.cooldownMs ?? 1200;

        if (this.shouldThrottleViolation(throttleKey, cooldownMs)) {
            return null;
        }

        if (this.isClipboardLikeViolation(eventType, eventData)) {
            this.clipboardViolationCount++;
        }
        this.totalViolationCount++;

        const timestamp = new Date().toISOString();
        const violationPayload = {
            ...eventData,
            source: eventData.source || 'web_browser',
            clipboard_count: this.clipboardViolationCount,
            total_count: this.totalViolationCount,
            timestamp
        };

        let responseData = null;
        try {
            const response = await fetch('/api/exams/log-violation', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.getToken()}`
                },
                body: JSON.stringify({
                    session_id: this.sessionId,
                    exam_id: this.examId,
                    event_type: eventType,
                    event_data: violationPayload,
                    timestamp,
                    user_agent: navigator.userAgent,
                    screen_resolution: `${screen.width}x${screen.height}`
                })
            });

            if (response.ok) {
                responseData = await response.json();
            } else {
                console.error('Failed to log violation:', response.status, await response.text());
            }
        } catch (error) {
            console.error('Failed to log browser violation:', error);
        }

        const violationCount = Number(responseData?.violation_count || this.totalViolationCount);
        this.recordViolation(eventType, violationCount, true);

        if (responseData?.warning) {
            showNotification(responseData.warning, 'error');
        }

        if (violationCount >= 8) {
            showNotification('⚠️ Terlalu banyak pelanggaran! Ujian akan dikumpulkan otomatis.', 'error');
            setTimeout(() => {
                this.submitExam(false);
            }, 2000);
        }

        return responseData;
    }

    async loadRuntimePolicy() {
        try {
            const policy = await api.getRuntimePolicy();
            if (!policy || typeof policy !== 'object') return;

            const answerSyncSeconds = Number(policy.answer_sync_interval_seconds);
            const answerBatchSize = Number(policy.answer_sync_batch_size);
            const retryAfterSeconds = Number(policy.retry_after_seconds);

            if (Number.isFinite(answerSyncSeconds) && answerSyncSeconds >= 10 && answerSyncSeconds <= 120) {
                this.runtimePolicy.answer_sync_interval_seconds = answerSyncSeconds;
                this.runtimePolicy.auto_save_interval_ms = answerSyncSeconds * 1000;
                this.runtimePolicy.answer_sync_debounce_ms = Math.max(5000, Math.min(30000, answerSyncSeconds * 500));
            } else {
                const autoSaveMs = Number(policy.auto_save_interval_ms);
                const debounceMs = Number(policy.answer_sync_debounce_ms);
                if (Number.isFinite(autoSaveMs) && autoSaveMs >= 10000 && autoSaveMs <= 120000) {
                    this.runtimePolicy.auto_save_interval_ms = autoSaveMs;
                }
                if (Number.isFinite(debounceMs) && debounceMs >= 1000 && debounceMs <= 30000) {
                    this.runtimePolicy.answer_sync_debounce_ms = debounceMs;
                }
            }
            if (Number.isFinite(answerBatchSize) && answerBatchSize >= 10 && answerBatchSize <= 100) {
                this.runtimePolicy.answer_sync_batch_size = answerBatchSize;
            }
            if (Number.isFinite(retryAfterSeconds) && retryAfterSeconds >= 1 && retryAfterSeconds <= 60) {
                this.runtimePolicy.retry_after_seconds = retryAfterSeconds;
            }

            if (syncWorker) {
                syncWorker.setSyncInterval(this.runtimePolicy.auto_save_interval_ms || 35000);
                if (typeof syncWorker.setBatchSize === 'function') {
                    syncWorker.setBatchSize(this.runtimePolicy.answer_sync_batch_size || 30);
                }
                if (typeof syncWorker.setRetryAfterSeconds === 'function') {
                    syncWorker.setRetryAfterSeconds(this.runtimePolicy.retry_after_seconds || 8);
                }
            }

            if (policy.degrade_mode === true || policy.mode === 'busy' || policy.mode === 'degraded' || policy.mode === 'exam_peak') {
                console.warn('⚠️ Runtime policy: degrade mode active');
            }
        } catch (error) {
            console.warn('Runtime policy fetch failed, using defaults:', error?.message || error);
        }
    }

    // Notify Flutter app about session start (for kiosk mode, screenshot blocking)
    notifyFlutterSessionStart() {
        try {
            // Check if running in Flutter WebView
            if (window.flutter_inappwebview) {
                window.flutter_inappwebview.callHandler('setSessionId', this.sessionId, this.examId);
                console.log('📱 Notified Flutter: session started', this.sessionId);
            }
        } catch (e) {
            console.log('Not running in Flutter WebView');
        }
    }

    // Notify Flutter app that exam is submitted (disable kiosk mode)
    notifyFlutterExamSubmitted() {
        try {
            if (window.flutter_inappwebview) {
                window.flutter_inappwebview.callHandler('examSubmitted');
                console.log('📱 Notified Flutter: exam submitted');
            }
        } catch (e) {
            console.log('Not running in Flutter WebView');
        }
    }

    // Record violation (called by Web detection or Native injection)
    recordViolation(type, count, fromNative = false) {
        const label = this.getViolationLabel(type);
        console.warn(`Violation detected: ${type} (${count})`);
        showNotification(`PERINGATAN: ${label} terdeteksi! (${count})`, count >= 3 ? 'error' : 'warning');

        // If from native, we don't need to send back to native (avoid loop)
        // If from web, send to native to log
        if (!fromNative && window.flutter_inappwebview) {
            try {
                window.flutter_inappwebview.callHandler('logViolation', type, count);
            } catch (e) { }
        }
    }

    // Force submit triggered by Flutter (e.g. enhanced security violation)
    async forceSubmitDueToViolations() {
        console.error('FORCE SUBMIT triggered due to violations');
        showNotification('Ujian dihentikan paksa karena pelanggaran keamanan!', 'error');

        // Wait a small moment to ensure user sees the notification
        await new Promise(r => setTimeout(r, 1500));

        await this.submitExam(false); // Submit without confirmation
    }

    // ============================================================================
    // CLIPBOARD PROTECTION SYSTEM
    // ============================================================================

    setupClipboardProtection() {
        const examContainer = document.body; // Protect entire page

        document.addEventListener('visibilitychange', () => {
            if (document.hidden) {
                this.logBrowserViolation('tab_switch', {
                    action: 'visibility_hidden'
                }, {
                    throttleKey: 'tab_switch',
                    cooldownMs: 2000
                });
            }
        });

        window.addEventListener('blur', () => {
            if (document.hidden) return;
            this.logBrowserViolation('focus_lost', {
                action: 'window_blur'
            }, {
                throttleKey: 'focus_lost',
                cooldownMs: 2000
            });
        });

        // Prevent copy
        examContainer.addEventListener('copy', (e) => {
            e.preventDefault();
            this.logBrowserViolation('copy', { action: 'copy' });
        });

        // Prevent paste
        examContainer.addEventListener('paste', (e) => {
            e.preventDefault();
            this.logBrowserViolation('paste', { action: 'paste' });
        });

        // Prevent cut
        examContainer.addEventListener('cut', (e) => {
            e.preventDefault();
            this.logBrowserViolation('cut', { action: 'cut' });
        });

        // Prevent context menu (right-click)
        examContainer.addEventListener('contextmenu', (e) => {
            e.preventDefault();
            this.logBrowserViolation('right_click', { action: 'right_click' });
        });

        // Prevent keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            const key = String(e.key || '').toLowerCase();

            // Ctrl+C, Ctrl+V, Ctrl+X
            if (e.ctrlKey && ['c', 'v', 'x'].includes(key)) {
                e.preventDefault();
                const eventTypeMap = { c: 'copy', v: 'paste', x: 'cut' };
                this.logBrowserViolation(eventTypeMap[key], {
                    action: `keyboard_ctrl_${key}`
                });
            }

            // F12 (DevTools)
            if (e.key === 'F12') {
                e.preventDefault();
                this.logBrowserViolation('devtools_attempt', { action: 'f12' });
            }

            // Ctrl+Shift+I/J/C (DevTools)
            if (e.ctrlKey && e.shiftKey && ['i', 'j', 'c'].includes(key)) {
                e.preventDefault();
                this.logBrowserViolation('devtools_attempt', {
                    action: `keyboard_ctrl_shift_${key}`
                });
            }

            // Print screen / snipping shortcuts
            if (
                e.key === 'PrintScreen'
                || (e.metaKey && e.shiftKey && ['3', '4', '5', 's'].includes(key))
            ) {
                e.preventDefault();
                this.logBrowserViolation('screenshot_attempt', {
                    action: `keyboard_${key}`
                }, {
                    throttleKey: 'screenshot_attempt',
                    cooldownMs: 2000
                });
            }
        });

        console.log('🔒 Clipboard protection enabled');
    }

    async logClipboardViolation(action) {
        const eventTypeMap = {
            copy: 'copy',
            paste: 'paste',
            cut: 'cut',
            right_click: 'right_click',
            devtools_attempt: 'devtools_attempt'
        };
        const eventType = eventTypeMap[action] || 'clipboard_violation';
        await this.logBrowserViolation(eventType, { action });
    }

    async loadExam() {
        try {
            const startData = await api.startExam(this.examId);

            this.sessionId = startData.session_id;
            this.questions = startData.questions || [];
            this.examData = {
                title: startData.exam_title,
                duration: startData.duration_minutes,
                endTime: new Date(startData.end_time),
                show_results: startData.show_results === true,  // FIX: Explicit true check
                show_teacher_name: startData.show_teacher_name !== false,
                teacher_name: startData.teacher_name
            };

            // FIX BUG #2: Update showResults property from API
            this.showResults = startData.show_results === true;  // FIX: Explicit true check to prevent undefined/null being treated as true
            console.log('📊 Show Results Flag:', this.showResults);
            this.shuffleQuestions = startData.shuffle_questions === true;
            this.shuffleOptions = startData.shuffle_options === true;

            // Update exam system properties based on loaded data
            this.durationMinutes = startData.duration_minutes;
            this.endTime = new Date(startData.end_time);

            // Start sync worker
            if (syncWorker) {
                syncWorker.start(this.sessionId);
            }

            // Fix 3: Restore previous answers on refresh
            await this.loadPreviousAnswers();

            // Render first question
            this.renderQuestion(0);
            this.updateNavigator();

        } catch (error) {
            console.error('Failed to load exam:', error);
            showNotification('Gagal memuat ujian. Silakan coba lagi.', 'error');
            // Optionally redirect or show a more prominent error message
        }
    }

    saveSessionToStorage() {
        try {
            // Skip if times are not initialized yet
            if (!this.startTime || !this.endTime) {
                return;
            }
            const sessionData = {
                sessionId: this.sessionId,
                examId: this.examId,
                durationMinutes: this.durationMinutes,
                startTime: this.startTime.toISOString(),
                endTime: this.endTime.toISOString(),
                currentQuestionIndex: this.currentQuestionIndex,
                timestamp: Date.now()
            };
            localStorage.setItem('active_exam_session', JSON.stringify(sessionData));
            this.pushRuntimeStateToNative(true);
        } catch (error) {
            console.warn('Failed to save session to localStorage:', error);
        }
    }

    getApproxRemainingSeconds() {
        const now = Date.now() + (this.serverTimeOffset || 0);
        const remainingMs = Math.max(0, this.endTime - now);
        return Math.floor(remainingMs / 1000);
    }

    pushRuntimeStateToNative(force = false) {
        const now = Date.now();
        if (!force && (now - this.lastNativeStateSyncAt) < 1500) {
            return;
        }
        this.lastNativeStateSyncAt = now;

        notifyNativeExamState({
            session_id: this.sessionId,
            exam_id: this.examId,
            current_question_index: this.currentQuestionIndex,
            time_remaining_seconds: this.getApproxRemainingSeconds(),
            connection_state: navigator.onLine ? 'online' : 'offline'
        });
    }

    pushTimerStateToNative(force = false) {
        const now = Date.now();
        if (!force && (now - this.lastNativeTimerSyncAt) < 5000) {
            return;
        }
        this.lastNativeTimerSyncAt = now;

        notifyNativeTimerSync({
            session_id: this.sessionId,
            server_time_epoch_ms: now + (this.serverTimeOffset || 0),
            remaining_seconds: this.getApproxRemainingSeconds(),
            current_question_index: this.currentQuestionIndex
        });
    }

    static clearSessionStorage() {
        try {
            localStorage.removeItem('active_exam_session');
        } catch (error) {
            console.warn('Failed to clear session from localStorage:', error);
        }
    }

    async initServerTimeSync() {
        // Initial sync
        await this.syncTime();

        // Periodic re-sync every 60 seconds to prevent clock manipulation
        this.timeSyncInterval = setInterval(() => {
            if (navigator.onLine) this.syncTime();
        }, 60000);
    }

    async syncTime() {
        try {
            const startPing = Date.now();
            const sessionStatus = await api.getSessionStatus(this.sessionId);
            const endPing = Date.now();
            const latency = (endPing - startPing) / 2; // Estimate network latency

            const serverTime = new Date(sessionStatus.server_time || new Date());
            const clientTime = new Date();

            console.log('🕐 TIME SYNC DEBUG:', {
                server_time_raw: sessionStatus.server_time,
                server_time_parsed: serverTime.toISOString(),
                client_time: clientTime.toISOString(),
                latency_ms: latency,
                previous_offset: this.serverTimeOffset
            });

            // Calculate offset with latency compensation
            const newOffset = (serverTime.getTime() - clientTime.getTime()) + latency;

            // Log if significant drift detected (> 2 seconds)
            if (Math.abs(newOffset - this.serverTimeOffset) > 2000 && this.serverTimeOffset !== 0) {
                console.warn(`⚠️ Time drift detected! Re-syncing. Old offset: ${this.serverTimeOffset}, New: ${newOffset}`);
            }

            this.serverTimeOffset = newOffset;
            // console.log(`🕐 Server time synced. Offset: ${this.serverTimeOffset}ms (Latency: ${latency}ms)`);

            if (sessionStatus.time_remaining_seconds) {
                const syncedNow = Date.now() + this.serverTimeOffset;
                // Update end time based on authoritative remaining time from server
                this.endTime = new Date(syncedNow + (sessionStatus.time_remaining_seconds * 1000));
            }
            this.pushTimerStateToNative(true);
            this.pushRuntimeStateToNative(true);

            // Check pause state from server
            if (sessionStatus.is_paused !== undefined) {
                this.handlePauseState(sessionStatus.is_paused, sessionStatus.pause_message, sessionStatus.paused_by);
            }

            // Fallback admin command handling via status polling.
            // This covers cases where WebSocket force_submit/force_kick is missed.
            if ((sessionStatus.status === 'submitted' || sessionStatus.status === 'completed') && !this.serverSubmitHandled) {
                this.serverSubmitHandled = true;
                showNotification('Ujian telah dikumpulkan oleh pengawas.', 'warning');
                setTimeout(() => this.submitExam(false), 800);
                return;
            }
            const isServerKick =
                sessionStatus.status === 'kicked' ||
                (
                    sessionStatus.status === 'terminated' &&
                    sessionStatus.terminated_by_admin === true &&
                    sessionStatus.emergency_exit_allowed !== true
                );

            if (isServerKick && !this.serverKickHandled) {
                this.serverKickHandled = true;
                this.handleForceKick(sessionStatus.kick_reason || 'Dikeluarkan oleh pengawas');
                return;
            }
        } catch (error) {
            console.warn('Server time sync failed:', error);
            // Don't reset offset on failure, keep using last known good offset
        }
    }

    // Handle pause state from server
    handlePauseState(isPaused, message, pausedBy) {
        if (isPaused && !this.globallyPaused) {
            // Exam just got paused
            console.log('⏸️ Exam paused by:', pausedBy);
            this.globallyPaused = true;
            this.pausedAt = Date.now();
            this.showPauseOverlay(message, pausedBy);

            // Start fast polling to detect resume (every 5 seconds)
            this.pauseSyncInterval = setInterval(() => {
                if (navigator.onLine) this.syncTime();
            }, 5000);
        } else if (!isPaused && this.globallyPaused) {
            // Exam just resumed
            console.log('▶️ Exam resumed');
            this.globallyPaused = false;
            this.hidePauseOverlay();

            // Stop fast polling
            if (this.pauseSyncInterval) {
                clearInterval(this.pauseSyncInterval);
                this.pauseSyncInterval = null;
            }
        }
    }

    // Show pause overlay to student
    showPauseOverlay(message, pausedBy) {
        // Remove existing overlay if any
        this.hidePauseOverlay();

        // CRITICAL: Block all interactions on the main content
        document.body.style.pointerEvents = 'none';
        document.body.style.userSelect = 'none';

        const overlay = document.createElement('div');
        overlay.id = 'exam-pause-overlay';
        overlay.style.pointerEvents = 'auto'; // Re-enable for overlay itself
        overlay.innerHTML = `
            <div style="
                position: fixed;
                top: 0; left: 0; right: 0; bottom: 0;
                background: rgba(0, 0, 0, 0.95);
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                z-index: 999999;
                color: white;
                font-family: 'Inter', sans-serif;
                pointer-events: auto;
            ">
                <div style="
                    background: linear-gradient(135deg, rgba(30,30,50,0.95), rgba(20,20,40,0.98));
                    border: 1px solid rgba(255, 200, 50, 0.3);
                    border-radius: 20px;
                    padding: 3rem;
                    text-align: center;
                    max-width: 500px;
                    box-shadow: 0 20px 60px rgba(0,0,0,0.5);
                    animation: pulseGlow 2s infinite;
                ">
                    <style>
                        @keyframes pulseGlow {
                            0%, 100% { box-shadow: 0 0 30px rgba(255, 200, 50, 0.3); }
                            50% { box-shadow: 0 0 50px rgba(255, 200, 50, 0.5); }
                        }
                        @keyframes pulse {
                            0%, 100% { transform: scale(1); }
                            50% { transform: scale(1.1); }
                        }
                    </style>
                    <div style="font-size: 4rem; margin-bottom: 1rem; animation: pulse 2s infinite;">⏸️</div>
                    <h2 style="font-size: 2rem; margin-bottom: 1rem; color: #ffc832;">UJIAN DI-PAUSE</h2>
                    <p style="font-size: 1.2rem; margin-bottom: 1.5rem; color: #ccc;">
                        ${message || 'Ujian sedang di-pause oleh pengawas'}
                    </p>
                    ${pausedBy ? `<p style="font-size: 0.9rem; color: #888;">Oleh: ${pausedBy}</p>` : ''}
                    <div style="margin-top: 2rem; padding: 1rem; background: rgba(255,200,50,0.1); border-radius: 10px;">
                        <i class="fas fa-info-circle" style="margin-right: 0.5rem;"></i>
                        Timer dihentikan. Tunggu sampai pengawas melanjutkan ujian.
                    </div>
                    <div style="margin-top: 1rem; padding: 0.75rem; background: rgba(255,100,100,0.15); border-radius: 10px; border: 1px solid rgba(255,100,100,0.3);">
                        <i class="fas fa-ban" style="margin-right: 0.5rem; color: #ff6b6b;"></i>
                        <span style="color: #ff9999;">Semua aksi dinonaktifkan selama pause</span>
                    </div>
                    <div style="margin-top: 1.5rem; font-size: 0.85rem; color: #666;">
                        <span id="pause-elapsed-timer">00:00</span> sejak di-pause
                    </div>
                </div>
            </div>
        `;
        document.body.appendChild(overlay);

        // Start pause elapsed timer
        this.pauseElapsedInterval = setInterval(() => {
            const elapsed = Math.floor((Date.now() - this.pausedAt) / 1000);
            const mins = Math.floor(elapsed / 60).toString().padStart(2, '0');
            const secs = (elapsed % 60).toString().padStart(2, '0');
            const timerEl = document.getElementById('pause-elapsed-timer');
            if (timerEl) timerEl.textContent = `${mins}:${secs}`;
        }, 1000);
    }

    // Hide pause overlay
    hidePauseOverlay() {
        // CRITICAL: Restore interactions
        document.body.style.pointerEvents = '';
        document.body.style.userSelect = '';

        const overlay = document.getElementById('exam-pause-overlay');
        if (overlay) overlay.remove();
        if (this.pauseElapsedInterval) {
            clearInterval(this.pauseElapsedInterval);
            this.pauseElapsedInterval = null;
        }
    }

    // ============================================================================
    // WEBSOCKET FOR REAL-TIME PAUSE/RESUME AND HEARTBEAT
    // ============================================================================

    initWebSocket() {
        if (!this.wsReconnectEnabled) {
            return;
        }

        // Get user ID from localStorage
        let user = {};
        try {
            user = JSON.parse(localStorage.getItem('user') || '{}');
        } catch (error) {
            console.warn('Invalid user data in localStorage for WebSocket init');
        }
        const userId = user.id;
        const wsToken = localStorage.getItem('access_token');

        if (!userId || !this.examId || !wsToken) {
            console.warn('⚠️ WebSocket not initialized: missing userId, examId, or token');
            this.scheduleWebSocketReconnect('missing_context', 1500);
            return;
        }

        if (
            this.examSocket &&
            (this.examSocket.readyState === WebSocket.OPEN || this.examSocket.readyState === WebSocket.CONNECTING)
        ) {
            return;
        }

        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/exam/${this.examId}/${userId}?token=${wsToken}`;

        console.log(`🔌 Connecting to Exam WebSocket`);

        try {
            this.examSocket = new WebSocket(wsUrl);

            this.examSocket.onopen = () => {
                console.log('✅ Exam WebSocket Connected');
                this.wsReconnectAttempts = 0;
                this.wsAuthFailed = false;
                // Start heartbeat every 30 seconds
                this.wsHeartbeatInterval = setInterval(() => {
                    if (this.examSocket && this.examSocket.readyState === WebSocket.OPEN) {
                        this.examSocket.send(JSON.stringify({ type: 'heartbeat', timestamp: new Date().toISOString() }));
                    }
                }, 30000);
            };

            this.examSocket.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    this.handleWebSocketMessage(data);
                } catch (e) {
                    console.error('WebSocket message parse error:', e);
                }
            };

            this.examSocket.onclose = (e) => {
                console.warn('⚠️ Exam WebSocket Disconnected:', e.reason);
                this.clearWsHeartbeat();
                this.examSocket = null;

                if (!this.wsReconnectEnabled) {
                    return;
                }

                // Authentication/authorization close code: do not loop reconnect forever
                if ([4401, 4403, 4404].includes(Number(e.code))) {
                    this.wsAuthFailed = true;
                    console.warn(`🛑 WebSocket reconnect stopped due to auth/permission close code ${e.code}`);
                    return;
                }

                this.scheduleWebSocketReconnect(`close_${e.code}`);
            };

            this.examSocket.onerror = (error) => {
                console.error('Exam WebSocket Error:', error);
            };

        } catch (error) {
            console.error('Failed to initialize WebSocket:', error);
            this.scheduleWebSocketReconnect('init_exception');
        }
    }

    scheduleWebSocketReconnect(reason = 'unknown', forcedDelayMs = null) {
        if (!this.wsReconnectEnabled || this.wsAuthFailed) {
            return;
        }
        if (this.wsReconnectTimer) {
            return;
        }

        this.wsReconnectAttempts += 1;
        if (this.wsReconnectAttempts > 12) {
            console.warn('🛑 WebSocket reconnect stopped after max attempts');
            return;
        }

        const delayMs = forcedDelayMs ?? Math.min(30000, 1000 * (2 ** (this.wsReconnectAttempts - 1)));
        console.log(`🔄 WebSocket reconnect attempt ${this.wsReconnectAttempts} in ${delayMs}ms (reason=${reason})`);

        this.wsReconnectTimer = setTimeout(() => {
            this.wsReconnectTimer = null;
            this.initWebSocket();
        }, delayMs);
    }

    handleWebSocketMessage(data) {
        console.log('📨 WebSocket Message:', data.type, data);

        switch (data.type) {
            case 'exam_paused':
                // Exam paused by admin
                console.log('⏸️ Exam paused via WebSocket');
                this.handlePauseState(true, data.message, data.paused_by);
                break;

            case 'exam_resumed':
                // Exam resumed by admin
                console.log('▶️ Exam resumed via WebSocket');
                this.handlePauseState(false);
                // Sync time immediately to get accurate remaining time
                this.syncTime();
                break;

            case 'force_submit':
                // Admin forced submission
                console.warn('🚨 Force submit from admin:', data.reason);
                showNotification(data.reason || 'Ujian dikumpulkan oleh pengawas', 'warning');

                // Notify Flutter app if running in APK
                try {
                    if (window.flutter_inappwebview) {
                        window.flutter_inappwebview.callHandler('forceSubmit', data.reason || 'Dikumpulkan oleh pengawas');
                        console.log('📱 Notified Flutter: force submit');
                    }
                } catch (e) {
                    console.log('Not running in Flutter WebView');
                }

                setTimeout(async () => {
                    await this.flushPendingAnswersForForceSubmit();
                    await this.submitExam(false);
                }, 1200);
                break;

            case 'force_kick':
                // Admin forced kick - logout student immediately
                console.error('🚫 [DEBUG] force_kick received via WebSocket!');
                console.error('🚫 [DEBUG] data:', JSON.stringify(data));
                console.error('🚫 [DEBUG] reason:', data.reason);
                this.handleForceKick(data.reason || 'Anda telah dikeluarkan dari ujian oleh pengawas');
                break;

            case 'exam_cancelled':
                // Exam was unpublished/cancelled by admin
                console.warn('🚫 Exam cancelled by admin:', data.cancelled_by);
                this.handleExamCancelled(data.reason, data.cancelled_by);
                break;

            case 'admin_message':
                // Message from admin
                showNotification(data.message, 'info');
                break;

            default:
                // Ignore unknown message types
                break;
        }
    }

    // Handle force kick - show notification and redirect
    handleForceKick(reason) {
        console.log('🔴 [DEBUG] handleForceKick called with reason:', reason);

        // Stop all intervals
        this.cleanup();

        // Show prominent notification
        showNotification(`🚫 ${reason}`, 'error');

        // Show modal overlay
        this.showKickedModal(reason);

        // Notify Flutter app if running in APK
        console.log('🔴 [DEBUG] Checking for Flutter WebView...');
        console.log('🔴 [DEBUG] window.flutter_inappwebview exists:', !!window.flutter_inappwebview);

        try {
            if (window.flutter_inappwebview) {
                console.log('🔴 [DEBUG] Calling Flutter forceKicked handler...');
                window.flutter_inappwebview.callHandler('forceKicked', reason);
                console.log('📱 [DEBUG] Notified Flutter: force kicked SUCCESS');
            } else {
                console.log('📱 [DEBUG] Not running in Flutter WebView (flutter_inappwebview not found)');
            }
        } catch (e) {
            console.error('🔴 [DEBUG] Error calling Flutter handler:', e);
        }

        // Redirect to dashboard after 5 seconds
        setTimeout(() => {
            ExamSystem.clearSessionStorage();
            window.location.href = '/student/dashboard.html?kicked=1';
        }, 5000);
    }

    // Show kicked modal overlay
    showKickedModal(reason) {
        // Remove any existing modal
        const existingModal = document.getElementById('kicked-modal');
        if (existingModal) existingModal.remove();

        const modal = document.createElement('div');
        modal.id = 'kicked-modal';
        modal.innerHTML = `
            <div style="
                position: fixed;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                background: rgba(0, 0, 0, 0.95);
                z-index: 99999;
                display: flex;
                align-items: center;
                justify-content: center;
                flex-direction: column;
                padding: 2rem;
                animation: fadeIn 0.3s ease;
            ">
                <div style="
                    text-align: center;
                    max-width: 500px;
                    background: linear-gradient(135deg, #1e293b, #0f172a);
                    border: 2px solid #ef4444;
                    border-radius: 1.5rem;
                    padding: 3rem;
                    box-shadow: 0 0 60px rgba(239, 68, 68, 0.3);
                ">
                    <div style="font-size: 5rem; margin-bottom: 1rem;">🚫</div>
                    <h1 style="
                        color: #ef4444;
                        font-size: 2rem;
                        margin-bottom: 1rem;
                        font-weight: 700;
                    ">Anda Dikeluarkan dari Ujian</h1>
                    <p style="
                        color: #94a3b8;
                        font-size: 1.1rem;
                        margin-bottom: 1.5rem;
                        line-height: 1.6;
                    ">${reason}</p>
                    <div style="
                        background: rgba(239, 68, 68, 0.1);
                        border: 1px solid rgba(239, 68, 68, 0.3);
                        border-radius: 0.75rem;
                        padding: 1rem;
                        color: #f87171;
                        font-size: 0.9rem;
                    ">
                        <i class="fas fa-info-circle"></i>
                        Anda akan dialihkan ke dashboard dalam 5 detik...
                    </div>
                </div>
            </div>
            <style>
                @keyframes fadeIn {
                    from { opacity: 0; }
                    to { opacity: 1; }
                }
            </style>
        `;
        document.body.appendChild(modal);
    }

    // Handle exam cancelled - show professional dialog and redirect to login
    handleExamCancelled(reason, cancelledBy) {
        console.warn('🚫 Exam cancelled - cleaning up...');

        // Clear any pause overlay first
        this.hidePauseOverlay();
        this.globallyPaused = false;

        // Stop all timers and intervals
        this.cleanup();

        // Remove any existing cancelled modal
        const existingModal = document.getElementById('cancelled-modal');
        if (existingModal) existingModal.remove();

        const modal = document.createElement('div');
        modal.id = 'cancelled-modal';
        modal.innerHTML = `
            <div style="
                position: fixed;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                background: rgba(0, 0, 0, 0.95);
                z-index: 999999;
                display: flex;
                align-items: center;
                justify-content: center;
                flex-direction: column;
                padding: 2rem;
                animation: fadeIn 0.3s ease;
            ">
                <div style="
                    text-align: center;
                    max-width: 500px;
                    background: linear-gradient(135deg, #1e293b, #0f172a);
                    border: 2px solid #f59e0b;
                    border-radius: 1.5rem;
                    padding: 3rem;
                    box-shadow: 0 0 60px rgba(245, 158, 11, 0.3);
                ">
                    <div style="font-size: 5rem; margin-bottom: 1rem;">⏸️</div>
                    <h1 style="
                        color: #f59e0b;
                        font-size: 1.8rem;
                        margin-bottom: 1rem;
                        font-weight: 700;
                    ">Ujian Ditunda / Dibatalkan</h1>
                    <p style="
                        color: #94a3b8;
                        font-size: 1.1rem;
                        margin-bottom: 1rem;
                        line-height: 1.6;
                    ">${reason || 'Ujian telah dibatalkan atau ditunda oleh pengawas.'}</p>
                    ${cancelledBy ? `<p style="
                        color: #64748b;
                        font-size: 0.9rem;
                        margin-bottom: 1.5rem;
                    ">Oleh: <strong>${cancelledBy}</strong></p>` : ''}
                    <div style="
                        background: rgba(245, 158, 11, 0.1);
                        border: 1px solid rgba(245, 158, 11, 0.3);
                        border-radius: 0.75rem;
                        padding: 1rem;
                        color: #fbbf24;
                        font-size: 0.9rem;
                        margin-bottom: 1.5rem;
                    ">
                        <i class="fas fa-info-circle"></i>
                        Silakan hubungi pengawas untuk informasi lebih lanjut.
                    </div>
                    <button id="cancelled-ok-btn" style="
                        background: linear-gradient(135deg, #f59e0b, #d97706);
                        color: white;
                        border: none;
                        padding: 1rem 3rem;
                        font-size: 1.1rem;
                        font-weight: 600;
                        border-radius: 0.75rem;
                        cursor: pointer;
                        transition: all 0.3s ease;
                        box-shadow: 0 4px 15px rgba(245, 158, 11, 0.3);
                    ">OK, SAYA MENGERTI</button>
                </div>
            </div>
            <style>
                @keyframes fadeIn {
                    from { opacity: 0; }
                    to { opacity: 1; }
                }
                #cancelled-ok-btn:hover {
                    transform: translateY(-2px);
                    box-shadow: 0 6px 20px rgba(245, 158, 11, 0.4);
                }
            </style>
        `;
        document.body.appendChild(modal);

        // Handle OK button click
        document.getElementById('cancelled-ok-btn').addEventListener('click', () => {
            // Notify Flutter app if running in APK
            try {
                if (window.flutter_inappwebview) {
                    window.flutter_inappwebview.callHandler('examCancelled', reason);
                    console.log('📱 Notified Flutter: exam cancelled');
                }
            } catch (e) {
                console.log('Not running in Flutter WebView');
            }

            // Clear session and redirect to login
            ExamSystem.clearSessionStorage();
            window.location.href = '/login.html?cancelled=1';
        });

        // Also notify Flutter immediately (in case WebView handles it differently)
        try {
            if (window.flutter_inappwebview) {
                window.flutter_inappwebview.callHandler('examCancelled', reason);
            }
        } catch (e) {
            // Ignore
        }
    }

    // Cleanup method to stop all intervals
    cleanup() {
        if (this.timerInterval) clearInterval(this.timerInterval);
        if (this.autoSaveInterval) clearInterval(this.autoSaveInterval);
        if (this.timeSyncInterval) clearInterval(this.timeSyncInterval);
        if (this.pauseSyncInterval) clearInterval(this.pauseSyncInterval);
        if (this.pauseElapsedInterval) clearInterval(this.pauseElapsedInterval);
        if (this.pendingSyncTimeout) clearTimeout(this.pendingSyncTimeout);
        if (this.textAnswerTimeout) clearTimeout(this.textAnswerTimeout);
        this.clearWsHeartbeat();
        this.wsReconnectEnabled = false;
        this.wsAuthFailed = false;
        this.wsReconnectAttempts = 0;
        if (this.wsReconnectTimer) {
            clearTimeout(this.wsReconnectTimer);
            this.wsReconnectTimer = null;
        }
        if (this.examSocket) {
            this.examSocket.close();
            this.examSocket = null;
        }
    }

    clearWsHeartbeat() {
        if (this.wsHeartbeatInterval) {
            clearInterval(this.wsHeartbeatInterval);
            this.wsHeartbeatInterval = null;
        }
    }
