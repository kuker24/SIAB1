/**
 * AUTO-GENERATED FILE.
 * Source modules: static/js/exam/*.js
 * Use scripts/build_exam_system_bundle.sh after editing modules.
 */

/* ===== Module: core.js ===== */

/* exam/core.js — utils + IndexedDB storage */

/**
 * Exam System JavaScript - Ultimate Fix v4.0
 * * CRITICAL FIXES:
 * - Matching Question: Fixed 'pair_id' vs 'id' bug (Auto-detection)
 * - Matching Question: Added fallback for missing option_group
 * - UUID Compatibility: Smart Type Casting for Strings/Integers
 * - Rendering: Added Null Safety to prevent blank screens
 */

// ============================================================================
// NOTIFICATION HELPER
// ============================================================================

function showNotification(message, type = 'info') {
    const existingNotif = document.querySelector('.exam-notification');
    if (existingNotif) existingNotif.remove();

    // Icon mapping for different types
    const icons = {
        success: 'fa-check-circle',
        warning: 'fa-exclamation-triangle',
        error: 'fa-times-circle',
        info: 'fa-info-circle'
    };

    const colors = {
        success: 'linear-gradient(135deg, #10b981, #059669)',
        warning: 'linear-gradient(135deg, #f59e0b, #d97706)',
        error: 'linear-gradient(135deg, #ef4444, #dc2626)',
        info: 'linear-gradient(135deg, #6366f1, #4f46e5)'
    };

    const notif = document.createElement('div');
    notif.className = `exam-notification ${type}`;
    notif.innerHTML = `
        <div style="display: flex; align-items: center; gap: 0.75rem;">
            <i class="fas ${icons[type] || icons.info}" style="font-size: 1.25rem;"></i>
            <span style="flex: 1;">${escapeHtml(message)}</span>
            <button onclick="this.closest('.exam-notification').remove()" style="background: none; border: none; color: white; cursor: pointer; padding: 0.25rem; opacity: 0.8;">
                <i class="fas fa-times"></i>
            </button>
        </div>
        <div style="position: absolute; bottom: 0; left: 0; right: 0; height: 3px; background: rgba(255,255,255,0.3); border-radius: 0 0 0.75rem 0.75rem;">
            <div style="height: 100%; background: white; animation: notifProgress 5s linear forwards;"></div>
        </div>
    `;
    notif.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        min-width: 300px;
        max-width: 450px;
        padding: 1rem 1rem 1.25rem 1rem;
        border-radius: 0.75rem;
        background: ${colors[type] || colors.info};
        color: white;
        z-index: 10000;
        box-shadow: 0 10px 40px rgba(0,0,0,0.4), 0 0 0 1px rgba(255,255,255,0.1);
        animation: slideIn 0.4s ease;
        backdrop-filter: blur(10px);
        font-weight: 500;
    `;

    if (!document.getElementById('notif-styles')) {
        const style = document.createElement('style');
        style.id = 'notif-styles';
        style.textContent = `
            @keyframes slideIn {
                from { transform: translateX(100%); opacity: 0; }
                to { transform: translateX(0); opacity: 1; }
            }
            @keyframes notifProgress {
                from { width: 100%; }
                to { width: 0%; }
            }
        `;
        document.head.appendChild(style);
    }

    document.body.appendChild(notif);
    setTimeout(() => notif.remove(), 5000);
}

function escapeHtml(value) {
    const text = value == null ? '' : String(value);
    return text.replace(/[&<>"'`]/g, (char) => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;',
        '`': '&#96;'
    }[char] || char));
}

function renderExamRichText(value) {
    const escaped = escapeHtml(value);
    if (!escaped) return '';

    return escaped
        .replace(/\[b\]([\s\S]*?)\[\/b\]/gi, '<strong>$1</strong>')
        .replace(/\[i\]([\s\S]*?)\[\/i\]/gi, '<em>$1</em>')
        .replace(/\[u\]([\s\S]*?)\[\/u\]/gi, '<u>$1</u>')
        .replace(/\[(?:ar|arabic)\]([\s\S]*?)\[\/(?:ar|arabic)\]/gi, '<span class="rich-arabic">$1</span>')
        .replace(/\r?\n/g, '<br>');
}

function escapeAttribute(value) {
    return escapeHtml(value).replace(/\n/g, '&#10;');
}

function sanitizeMediaUrl(rawUrl, options = {}) {
    const { allowDataImage = false, allowBlob = false } = options;
    const value = rawUrl == null ? '' : String(rawUrl).trim();
    if (!value) {
        return '';
    }

    if (allowDataImage && /^data:image\/[a-z0-9.+-]+;base64,[a-z0-9+/=]+$/i.test(value)) {
        return value;
    }

    if (allowBlob && value.startsWith('blob:')) {
        return value;
    }

    if (/^(\/|\.\/|\.\.\/)/.test(value)) {
        return value;
    }

    try {
        const parsed = new URL(value, window.location.origin);
        if (parsed.protocol === 'http:' || parsed.protocol === 'https:') {
            return parsed.href;
        }
    } catch (error) {
        return '';
    }

    return '';
}

function extractYouTubeId(url) {
    if (!url) return null;
    const patterns = [
        /youtube\.com\/watch\?v=([a-zA-Z0-9_-]{11})/,
        /youtu\.be\/([a-zA-Z0-9_-]{11})/,
        /youtube\.com\/embed\/([a-zA-Z0-9_-]{11})/
    ];
    for (const pattern of patterns) {
        const match = String(url).match(pattern);
        if (match) return match[1];
    }
    return null;
}

function renderQuestionImage(url, alt = 'Question image', extraAttributes = '') {
    const safeUrl = sanitizeMediaUrl(url);
    if (!safeUrl) {
        return '';
    }
    const hasZoomAttribute = /\sdata-(?:no-)?zoom\s*=/.test(extraAttributes || '');
    const zoomAttribute = hasZoomAttribute ? '' : ' data-zoomable="true"';
    return `<img src="${escapeAttribute(safeUrl)}" class="question-image" alt="${escapeAttribute(alt)}"${zoomAttribute}${extraAttributes}>`;
}

function renderQuestionVideo(url) {
    const videoId = extractYouTubeId(url);
    if (!videoId) {
        return '';
    }
    return `
        <div class="question-video">
            <iframe src="https://www.youtube.com/embed/${escapeAttribute(videoId)}" allowfullscreen></iframe>
        </div>
    `;
}

function renderQuestionAudio(url, wrapperStyle = '', audioStyle = '') {
    const safeUrl = sanitizeMediaUrl(url);
    if (!safeUrl) {
        return '';
    }

    const wrapperAttr = wrapperStyle ? ` style="${escapeAttribute(wrapperStyle)}"` : '';
    const audioAttr = audioStyle ? ` style="${escapeAttribute(audioStyle)}"` : '';
    return `
        <div class="question-audio"${wrapperAttr}>
            <audio controls${audioAttr}>
                <source src="${escapeAttribute(safeUrl)}" type="audio/mpeg">
                <source src="${escapeAttribute(safeUrl)}" type="audio/wav">
                <source src="${escapeAttribute(safeUrl)}" type="audio/ogg">
                Your browser does not support the audio element.
            </audio>
        </div>
    `;
}


// ============================================================================
// INDEXEDDB STORAGE MANAGER
// ============================================================================

class ExamStorageManager {
    constructor() {
        this.dbName = 'ExamSystemDB';
        this.storeName = 'answers';
        this.db = null;
    }

    async init() {
        return new Promise((resolve, reject) => {
            const request = indexedDB.open(this.dbName, 1);

            request.onerror = () => reject(request.error);
            request.onsuccess = () => {
                this.db = request.result;
                console.log('📦 IndexedDB initialized');
                resolve();
            };

            request.onupgradeneeded = (event) => {
                const db = event.target.result;
                if (!db.objectStoreNames.contains(this.storeName)) {
                    const store = db.createObjectStore(this.storeName, { keyPath: 'question_id' });
                    store.createIndex('session_id', 'session_id', { unique: false });
                    store.createIndex('synced', 'synced', { unique: false });
                    store.createIndex('timestamp', 'timestamp', { unique: false });
                }
            };
        });
    }

    async saveAnswerLocal(sessionId, questionId, answerData) {
        return this.saveAnswer(sessionId, questionId, answerData, false);
    }

    async saveAnswer(sessionId, questionId, answerData, synced = true) {
        if (!this.db) return;

        const transaction = this.db.transaction([this.storeName], 'readwrite');
        const store = transaction.objectStore(this.storeName);

        const record = {
            question_id: questionId,
            session_id: sessionId,
            answer_data: answerData,
            timestamp: Date.now(),
            synced: synced,
            retry_count: 0
        };

        return new Promise((resolve, reject) => {
            const request = store.put(record);
            request.onsuccess = () => {
                // console.log(`💾 Answer saved locally for question ${questionId}`);
                resolve();
            };
            request.onerror = () => reject(request.error);
        });
    }

    async getUnsyncedAnswers(sessionId) {
        if (!this.db) return [];

        const transaction = this.db.transaction([this.storeName], 'readonly');
        const store = transaction.objectStore(this.storeName);

        return new Promise((resolve, reject) => {
            const request = store.getAll();
            request.onsuccess = () => {
                const allRecords = request.result;
                const unsynced = allRecords.filter(r =>
                    !r.synced && r.session_id === sessionId
                );
                resolve(unsynced);
            };
            request.onerror = () => reject(request.error);
        });
    }

    async markAsSynced(questionIds) {
        if (!this.db || questionIds.length === 0) return;

        const transaction = this.db.transaction([this.storeName], 'readwrite');
        const store = transaction.objectStore(this.storeName);

        for (const qid of questionIds) {
            const getRequest = store.get(qid);
            getRequest.onsuccess = () => {
                const record = getRequest.result;
                if (record) {
                    record.synced = true;
                    record.synced_at = Date.now();
                    store.put(record);
                }
            };
        }

        return new Promise((resolve) => {
            transaction.oncomplete = () => {
                console.log(`✅ Marked ${questionIds.length} answers as synced`);
                resolve();
            };
        });
    }

    async clearSessionAnswers(sessionId) {
        if (!this.db) return;

        const transaction = this.db.transaction([this.storeName], 'readwrite');
        const store = transaction.objectStore(this.storeName);
        const index = store.index('session_id');

        return new Promise((resolve) => {
            const request = index.openCursor(IDBKeyRange.only(sessionId));
            request.onsuccess = (e) => {
                const cursor = e.target.result;
                if (cursor) {
                    cursor.delete();
                    cursor.continue();
                } else {
                    console.log(`🧹 Cleared local answers for session ${sessionId}`);
                    resolve();
                }
            };
        });
    }
}

/* ===== Module: bridge.js ===== */

/* exam/bridge.js — flutter_inappwebview callHandler */

function callFlutterHandler(handlerName, payload) {
    try {
        if (!window.flutter_inappwebview || typeof window.flutter_inappwebview.callHandler !== 'function') {
            return false;
        }
        if (payload === undefined) {
            window.flutter_inappwebview.callHandler(handlerName);
        } else {
            window.flutter_inappwebview.callHandler(handlerName, payload);
        }
        return true;
    } catch (error) {
        console.warn(`Flutter handler '${handlerName}' failed:`, error?.message || error);
        return false;
    }
}

function notifyNativeAnswerJournal(payload) {
    return callFlutterHandler('answerJournalEvent', payload);
}

function notifyNativeExamState(payload) {
    return callFlutterHandler('examStateUpdate', payload);
}

function notifyNativeTimerSync(payload) {
    return callFlutterHandler('timerSync', payload);
}

/* ===== Module: autosave.js ===== */

/* exam/autosave.js — AnswerSyncWorker */

// ============================================================================
// ANSWER SYNC WORKER
// ============================================================================

class AnswerSyncWorker {
    constructor(storage, getTokenFn) {
        this.storage = storage;
        this.getToken = getTokenFn;
        this.sessionId = null;
        this.intervalId = null;
        this.syncInterval = 20000; // 20 seconds baseline to reduce write pressure
        this.batchSize = 30;
        this.retryAfterSeconds = 8;
        this.failureStreak = 0;
        this.backoffUntil = 0;
        this.syncInFlight = false;
    }

    setSyncInterval(intervalMs) {
        const parsed = Number(intervalMs);
        if (!Number.isFinite(parsed)) return;
        this.syncInterval = Math.min(120000, Math.max(8000, Math.round(parsed)));
        if (this.sessionId) {
            this.start(this.sessionId);
        }
    }

    start(sessionId) {
        this.sessionId = sessionId;
        if (this.intervalId) {
            clearInterval(this.intervalId);
        }
        this.intervalId = setInterval(async () => {
            if (navigator.onLine) {
                this.syncNow();
            }
        }, this.syncInterval);
        console.log('🔄 Sync worker started');
    }

    setBatchSize(batchSize) {
        const parsed = Number(batchSize);
        if (!Number.isFinite(parsed)) return;
        this.batchSize = Math.min(100, Math.max(10, Math.round(parsed)));
    }

    setRetryAfterSeconds(seconds) {
        const parsed = Number(seconds);
        if (!Number.isFinite(parsed)) return;
        this.retryAfterSeconds = Math.min(60, Math.max(1, Math.round(parsed)));
    }

    computeBackoffDelayMs(response = null) {
        const retryHeader = response?.headers?.get?.('Retry-After');
        const retryAfter = Number.parseInt(retryHeader || '', 10);
        const baseSeconds = Number.isFinite(retryAfter) && retryAfter > 0
            ? retryAfter
            : this.retryAfterSeconds;
        const exponent = Math.min(6, Math.max(0, this.failureStreak));
        const cappedSeconds = Math.min(baseSeconds * (2 ** exponent), 60);
        const jitter = 0.2 + (Math.random() * 0.2);
        return Math.round((cappedSeconds * 1000) + (cappedSeconds * 1000 * jitter));
    }

    shouldRetryStatus(status) {
        return [429, 502, 503, 504].includes(Number(status));
    }

    stop() {
        if (this.intervalId) {
            clearInterval(this.intervalId);
            this.intervalId = null;
        }
        console.log('🔄 Sync worker stopped');
    }

    async syncNow() {
        if (!this.sessionId) return;
        if (this.syncInFlight) return;
        if (Date.now() < this.backoffUntil) return;

        this.syncInFlight = true;
        try {
            const allUnsyncedAnswers = await this.storage.getUnsyncedAnswers(this.sessionId);
            const unsyncedAnswers = allUnsyncedAnswers.slice(0, this.batchSize);

            if (unsyncedAnswers.length === 0) return;

            console.log(`🔄 Syncing ${unsyncedAnswers.length}/${allUnsyncedAnswers.length} answers...`);

            // Prepare batch payload with type normalization
            const answers = unsyncedAnswers
                .map(a => ({
                    question_id: parseInt(a.question_id) || 0,
                    ...this.normalizeAnswerData(a.answer_data)
                }))
                .filter(a => a.question_id && Object.keys(a).length > 1);

            if (answers.length === 0) {
                return;
            }

            // Send to server (batch endpoint)
            const response = await fetch('/api/exams/auto-save-batch', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.getToken()}`
                },
                body: JSON.stringify({
                    session_id: parseInt(this.sessionId) || 0,
                    answers: answers
                })
            });

            if (response.ok) {
                this.failureStreak = 0;
                this.backoffUntil = 0;
                const syncedIds = unsyncedAnswers.map(a => a.question_id);
                await this.storage.markAsSynced(syncedIds);
                console.log(`✅ Synced ${syncedIds.length} answers`);
            } else {
                this.failureStreak = Math.min(6, this.failureStreak + 1);
                if (this.shouldRetryStatus(response.status)) {
                    const delayMs = this.computeBackoffDelayMs(response);
                    this.backoffUntil = Date.now() + delayMs;
                    console.warn(`Sync busy (${response.status}), retry in ${Math.round(delayMs / 1000)}s`);
                } else {
                    console.warn('Sync failed, will retry on next interval...');
                }
            }
        } catch (error) {
            this.failureStreak = Math.min(6, this.failureStreak + 1);
            const delayMs = this.computeBackoffDelayMs();
            this.backoffUntil = Date.now() + delayMs;
            console.error(`Sync error, retry in ${Math.round(delayMs / 1000)}s:`, error);
        } finally {
            this.syncInFlight = false;
        }
    }

    /**
     * Normalize answer data - Robust Type Checking
     */
    normalizeAnswerData(data) {
        const normalized = {};

        // Helper to smart cast: "123" -> 123, "abc" -> "abc"
        const smartCast = (val) => {
            if (typeof val === 'string' && /^\d+$/.test(val)) return parseInt(val);
            return val;
        };

        // Single selection
        if (data.selected_option_id !== undefined && data.selected_option_id !== null) {
            normalized.selected_option_id = smartCast(data.selected_option_id);
        }

        // Multiple selections
        if (data.selected_option_ids !== undefined) {
            if (Array.isArray(data.selected_option_ids)) {
                normalized.selected_option_ids = data.selected_option_ids.map(smartCast);
            }
        }

        // Text answer
        if (data.answer_text !== undefined) {
            normalized.answer_text = String(data.answer_text);
        }

        // Table validation answers
        if (data.statement_answers && typeof data.statement_answers === 'object' && !Array.isArray(data.statement_answers)) {
            normalized.statement_answers = {};
            Object.keys(data.statement_answers).forEach(key => {
                normalized.statement_answers[String(key)] = data.statement_answers[key];
            });
        }

        if (data.answer_metadata && typeof data.answer_metadata === 'object') {
            normalized.answer_metadata = data.answer_metadata;
        }

        return normalized;
    }
}

class AnswerJournalWorker {
    constructor(getTokenFn) {
        this.getToken = getTokenFn;
        this.sessionId = null;
        this.timerId = null;
        this.intervalId = null;
        this.syncInFlight = false;
        this.failureStreak = 0;
        this.backoffUntil = 0;
        this.baseIntervalMs = 10000;
        this.batchSize = 80;
        this.storageKey = 'sxb_js_answer_journal_v1';
    }

    enqueue(payload) {
        const sessionId = parseInt(payload?.session_id || this.sessionId, 10) || 0;
        const questionId = parseInt(payload?.question_id, 10) || 0;
        if (sessionId <= 0 || questionId <= 0) return;
        const state = this.readState();
        const nextSeq = parseInt(state.next_sequence, 10) || 1;
        const nowMs = Date.now();
        const event = {
            event_id: `jr_${sessionId}_${nextSeq}_${nowMs}_${this.randomSuffix(5)}`,
            sequence: nextSeq,
            question_id: questionId,
            local_timestamp_ms: nowMs,
            session_id: sessionId,
        };
        if (payload.selected_option_id != null) {
            event.selected_option_id = payload.selected_option_id;
        }
        if (Array.isArray(payload.selected_option_ids)) {
            event.selected_option_ids = payload.selected_option_ids;
        }
        if (payload.answer_text != null) {
            event.answer_text = String(payload.answer_text);
        }
        if (payload.statement_answers && typeof payload.statement_answers === 'object') {
            event.statement_answers = payload.statement_answers;
        }
        if (payload.answer_metadata && typeof payload.answer_metadata === 'object') {
            event.answer_metadata = payload.answer_metadata;
        }
        state.events.push(event);
        if (state.events.length > 500) {
            state.events = state.events.slice(-500);
        }
        state.next_sequence = nextSeq + 1;
        this.writeState(state);
    }

    start(sessionId) {
        this.sessionId = sessionId;
        this.stopTimer();
        const firstDelay = Math.round(Math.random() * this.baseIntervalMs);
        this.timerId = setTimeout(() => {
            this.flushNow();
            this.intervalId = setInterval(() => this.flushNow(), this.baseIntervalMs);
        }, firstDelay);
    }

    stop() {
        this.stopTimer();
    }

    stopTimer() {
        if (this.timerId) {
            clearTimeout(this.timerId);
            this.timerId = null;
        }
        if (this.intervalId) {
            clearInterval(this.intervalId);
            this.intervalId = null;
        }
    }

    async flushNow() {
        if (!this.sessionId || this.syncInFlight) return;
        if (Date.now() < this.backoffUntil) return;
        if (!navigator.onLine) return;
        const state = this.readState();
        const pending = state.events.filter((event) => {
            return (parseInt(event.session_id, 10) || 0) === parseInt(this.sessionId, 10);
        });
        if (pending.length === 0) return;
        const batch = pending.slice(0, this.batchSize);
        this.syncInFlight = true;
        try {
            const response = await fetch('/api/exams/answer-journal/sync', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.getToken()}`
                },
                body: JSON.stringify({
                    session_id: parseInt(this.sessionId, 10) || 0,
                    events: batch.map((event) => {
                        const { session_id, ...rest } = event;
                        return rest;
                    })
                })
            });
            if (!response.ok) {
                this.failureStreak = Math.min(6, this.failureStreak + 1);
                const retryAfter = Number.parseInt(response.headers.get('Retry-After') || '', 10);
                const baseSeconds = Number.isFinite(retryAfter) && retryAfter > 0 ? retryAfter : 8;
                const jitter = 0.2 + (Math.random() * 0.2);
                this.backoffUntil = Date.now() + Math.min(
                    60000,
                    Math.round((baseSeconds * (2 ** this.failureStreak) * 1000) * (1 + jitter))
                );
                return;
            }
            this.failureStreak = 0;
            this.backoffUntil = 0;
            const body = await response.json();
            const acked = new Set();
            (body.acks || []).forEach((ack) => {
                const status = String(ack?.status || '').toLowerCase();
                const eventId = String(ack?.event_id || '').trim().toLowerCase();
                if (eventId && (status === 'applied' || status === 'duplicate')) {
                    acked.add(eventId);
                }
            });
            if (acked.size === 0) return;
            state.events = state.events.filter((event) => {
                return !acked.has(String(event.event_id || '').trim().toLowerCase());
            });
            this.writeState(state);
        } catch (_error) {
            this.failureStreak = Math.min(6, this.failureStreak + 1);
            const jitter = 0.2 + (Math.random() * 0.2);
            this.backoffUntil = Date.now() + Math.min(
                60000,
                Math.round((8 * (2 ** this.failureStreak) * 1000) * (1 + jitter))
            );
        } finally {
            this.syncInFlight = false;
        }
    }

    readState() {
        try {
            const raw = localStorage.getItem(this.storageKey);
            if (!raw) return { next_sequence: 1, events: [] };
            const parsed = JSON.parse(raw);
            return {
                next_sequence: parseInt(parsed.next_sequence, 10) || 1,
                events: Array.isArray(parsed.events) ? parsed.events : [],
            };
        } catch (_error) {
            return { next_sequence: 1, events: [] };
        }
    }

    writeState(state) {
        localStorage.setItem(this.storageKey, JSON.stringify(state));
    }

    randomSuffix(length) {
        const chars = 'abcdefghijklmnopqrstuvwxyz0123456789';
        let out = '';
        for (let i = 0; i < length; i += 1) {
            out += chars[Math.floor(Math.random() * chars.length)];
        }
        return out;
    }
}

// ============================================================================
// SERVICE WORKER REGISTRATION
// ============================================================================

if ('serviceWorker' in navigator) {
    window.addEventListener('load', async () => {
        try {
            const registration = await navigator.serviceWorker.register('/static/sw.js');
            // console.log('📱 Service Worker registered:', registration.scope);
        } catch (error) {
            console.warn('Service Worker registration failed:', error);
        }
    });
}

// ============================================================================
// GLOBAL STORAGE INSTANCES
// ============================================================================

let storageManager = null;
let syncWorker = null;
let journalWorker = null;

/* ===== Module: security.js ===== */

/* exam/security.js — ExamSystem security/clipboard */

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
        if (journalWorker && this.sessionId) {
            journalWorker.start(this.sessionId);
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

            if (syncWorker) {
                syncWorker.start(this.sessionId);
            }
            if (journalWorker) {
                journalWorker.start(this.sessionId);
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

/* ===== Module: reconnect.js ===== */

/* exam/reconnect.js — websocket pause/kick/reconnect */

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

/* ===== Module: timer.js ===== */

/* exam/timer.js — timer + autosave hooks */


    async initOfflineStorage() {
        try {
            storageManager = new ExamStorageManager();
            await storageManager.init();
            syncWorker = new AnswerSyncWorker(storageManager, () => this.getToken());
            journalWorker = new AnswerJournalWorker(() => this.getToken());

            console.log('📦 Offline storage initialized');
        } catch (error) {
            console.warn('Offline storage initialization failed:', error);
        }
    }

    setupAutoSave() {
        const jitter = Math.random() * 5000;
        const intervalMs = this.runtimePolicy.auto_save_interval_ms || 30000;
        setTimeout(() => {
            this.autoSaveInterval = setInterval(() => {
                this.autoSave();
            }, intervalMs);
        }, jitter);
    }

    setupTimer() {
        this.updateTimer();
        this.timerInterval = setInterval(() => {
            this.updateTimer();
        }, 1000);
    }

    async updateTimer() {
        // Skip countdown if exam is paused
        if (this.globallyPaused) {
            return; // Timer frozen during pause
        }

        const now = Date.now() + this.serverTimeOffset;
        const remaining = Math.max(0, this.endTime - now);

        const hours = Math.floor(remaining / (1000 * 60 * 60));
        const minutes = Math.floor((remaining % (1000 * 60 * 60)) / (1000 * 60));
        const seconds = Math.floor((remaining % (1000 * 60)) / 1000);

        const timerElement = document.getElementById('timer-value');
        const timerContainer = document.getElementById('timer-container');
        if (timerElement) {
            if (hours > 0) {
                timerElement.textContent = `${hours}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
            } else {
                timerElement.textContent = `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
            }

            // Apply state classes to both timer value and container
            timerElement.classList.remove('timer-warning', 'timer-danger');
            if (timerContainer) {
                timerContainer.classList.remove('warning', 'danger');
            }

            if (remaining <= 60000) {
                timerElement.classList.add('timer-danger');
                if (timerContainer) timerContainer.classList.add('danger');
            } else if (remaining <= 300000) {
                timerElement.classList.add('timer-warning');
                if (timerContainer) timerContainer.classList.add('warning');
            }
        }

        this.pushTimerStateToNative(false);

        if (remaining <= 0) {
            clearInterval(this.timerInterval);

            // CRITICAL FIX: Don't await showAlert - it blocks auto-submit!
            // Instead, show non-blocking notification and submit immediately
            console.log('⏰ Timer expired! Auto-submitting exam...');
            showNotification('Waktu ujian telah habis! Mengumpulkan ujian...', 'warning');

            // Submit immediately without confirmation
            this.submitExam(false);
        }
    }

    setupBeforeUnload() {
        window.addEventListener('beforeunload', (e) => {
            this.autoSave();
            e.preventDefault();
            e.returnValue = 'Anda yakin ingin meninggalkan ujian?';
            return e.returnValue;
        });
    }

/* ===== Module: navigation.js ===== */

/* exam/navigation.js — soal, nav, submit */

    setupKeyboardNavigation() {
        document.addEventListener('keydown', (e) => {
            if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
                e.preventDefault();
                this.nextQuestion();
            } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
                e.preventDefault();
                this.prevQuestion();
            }

            if (['1', '2', '3', '4', '5'].includes(e.key)) {
                const options = document.querySelectorAll('.option-item');
                const index = parseInt(e.key) - 1;
                if (options[index]) {
                    options[index].click();
                }
            }
        });
    }

    setQuestions(questions) {
        this.questions = questions;
        // Ensure sync worker always has active session context.
        if (syncWorker && this.sessionId && syncWorker.sessionId !== this.sessionId) {
            syncWorker.start(this.sessionId);
        }
        if (journalWorker && this.sessionId && journalWorker.sessionId !== this.sessionId) {
            journalWorker.start(this.sessionId);
        }
        this.renderQuestion(0);
        this.updateNavigator();
    }

    // Fix 3: Load previous answers from database
    async loadPreviousAnswers() {
        try {
            const response = await api.request('GET', `/exams/session/${this.sessionId}/answers`);
            if (response.answers && Object.keys(response.answers).length > 0) {
                console.log('📥 Restoring', response.answered_count, 'previous answers');

                // Restore to local storage and UI
                for (const [questionId, answerData] of Object.entries(response.answers)) {
                    const qId = parseInt(questionId);
                    this.answers[qId] = answerData;

                    // Also save to IndexedDB for offline support
                    if (storageManager) {
                        await storageManager.saveAnswer(this.sessionId, qId, answerData);
                    }
                }

                showNotification(`Memulihkan ${response.answered_count} jawaban sebelumnya`, 'success');
            }
        } catch (error) {
            console.warn('⚠️ No previous answers to restore:', error.message);
        }
    }

    renderQuestion(index) {
        if (index < 0 || index >= this.questions.length) return;

        this.currentQuestionIndex = index;
        const question = this.questions[index];

        const container = document.getElementById('question-container');
        if (!container) return;

        let questionHtml = '';
        switch (question.question_type) {
            case 'multiple_choice':
            case 'true_false':
                questionHtml = this.renderMultipleChoice(question, index);
                break;
            case 'multiple_choice_complex':
                questionHtml = this.renderComplexChoice(question, index);
                break;
            case 'essay':
                questionHtml = this.renderEssay(question, index);
                break;
            case 'short_answer':
                questionHtml = this.renderShortAnswer(question, index);
                break;
            default:
                questionHtml = this.renderMultipleChoice(question, index);
        }

        container.innerHTML = questionHtml;
        this.updateNavigator();
        this.saveSessionToStorage();
        this.pushRuntimeStateToNative(false);
    }

    isManualGradingQuestion(question) {
        if (!question) return false;
        const settings = question.question_settings || {};
        if (question.question_type === 'essay') return true;
        if (question.question_type === 'short_answer') {
            return settings.require_manual_grading === true;
        }
        return false;
    }

    renderQuestionBehaviorHint(question) {
        return '';
    }

    isModel2Enabled(question, options = []) {
        return false;
    }

    getModel2Slots(question, options = []) {
        const settings = question.question_settings || {};
        const rawSlots = settings.model2_runtime_slots || settings.model2_slots || [];
        if (Array.isArray(rawSlots) && rawSlots.length >= 2) {
            return rawSlots.slice(0, options.length).map((slot, idx) => ({
                slot: idx,
                x: Number(slot?.x ?? 50),
                y: Number(slot?.y ?? 50)
            }));
        }

        // Fallback safe layout if slot data unavailable
        const count = Math.max(options.length, 4);
        if (count <= 4) {
            return [
                { slot: 0, x: 20, y: 20 },
                { slot: 1, x: 80, y: 20 },
                { slot: 2, x: 20, y: 78 },
                { slot: 3, x: 80, y: 78 }
            ].slice(0, options.length);
        }
        if (count === 5) {
            return [
                { slot: 0, x: 18, y: 18 },
                { slot: 1, x: 82, y: 18 },
                { slot: 2, x: 18, y: 50 },
                { slot: 3, x: 82, y: 50 },
                { slot: 4, x: 50, y: 82 }
            ];
        }
        const slots = [];
        const cols = 3;
        const rows = Math.ceil(options.length / cols);
        for (let i = 0; i < options.length; i++) {
            const col = i % cols;
            const row = Math.floor(i / cols);
            slots.push({
                slot: i,
                x: 12 + (col * (76 / Math.max(cols - 1, 1))),
                y: 14 + (row * (72 / Math.max(rows - 1, 1)))
            });
        }
        return slots;
    }

    renderModel2Layout(question, options, selectedValue, isMulti = false) {
        const letters = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H'];
        const slots = this.getModel2Slots(question, options);
        const selectedIds = isMulti
            ? (Array.isArray(selectedValue) ? selectedValue.map(v => String(v)) : [])
            : [String(selectedValue ?? '')];
        const safeImageMarkup = renderQuestionImage(
            question.image_url,
            'Question image',
            ' style="display:block; max-width:100%; border-radius:0.5rem;"'
        );

        const hotspotsHtml = options.map((opt, idx) => {
            const slot = slots[idx] || { x: 50, y: 50 };
            const optionId = String(opt.id);
            const isSelected = selectedIds.includes(optionId);
            const rawLabel = (opt.option_text || '').trim();
            const fallbackLabel = letters[idx] || `${idx + 1}`;
            const displayLabel = rawLabel ? rawLabel : fallbackLabel;
            const safeLabel = escapeHtml(displayLabel);
            const clickHandler = isMulti
                ? `window.examSystem.toggleComplexOption(${question.id}, '${optionId}', ${!isSelected})`
                : `window.examSystem.selectOption(${question.id}, '${optionId}')`;

            return `
                <button type="button"
                        class="model2-hotspot ${isSelected ? 'selected' : ''} ${isMulti ? 'multi' : 'single'}"
                        data-option-id="${escapeAttribute(optionId)}"
                        data-label="${escapeAttribute(displayLabel)}"
                        onclick="event.stopPropagation(); ${clickHandler}"
                        style="position:absolute; left:${slot.x}%; top:${slot.y}%; transform:translate(-50%, -50%); width:44px; height:44px; border-radius:999px; border:2px solid ${isSelected ? '#22c55e' : 'rgba(148,163,184,0.75)'}; background:${isSelected ? 'linear-gradient(135deg,#22c55e,#16a34a)' : 'rgba(15,23,42,0.8)'}; color:white; font-weight:700; display:flex; align-items:center; justify-content:center; cursor:pointer; box-shadow:0 8px 20px rgba(0,0,0,0.35); z-index:3;">
                    <span class="model2-hotspot-badge">${isSelected ? '✓' : safeLabel}</span>
                </button>
            `;
        }).join('');

        const legendHtml = options.map((opt, idx) => {
            const rawLabel = (opt.option_text || '').trim();
            const fallbackLabel = letters[idx] || `${idx + 1}`;
            const displayLabel = rawLabel ? rawLabel : fallbackLabel;
            return `<span style="padding:0.2rem 0.45rem; border:1px solid rgba(148,163,184,0.35); border-radius:0.35rem; background:rgba(15,23,42,0.45); color:#cbd5e1; font-size:0.74rem;">${escapeHtml(displayLabel)}</span>`;
        }).join('');

        return `
            <div style="margin-bottom:0.65rem; padding:0.5rem 0.6rem; border:1px solid rgba(59,130,246,0.3); border-radius:0.45rem; background:rgba(59,130,246,0.1); color:#bfdbfe; font-size:0.8rem;">
                <i class="fas fa-image"></i> Soal bergambar ditampilkan dalam mode normal.
            </div>
            <div style="position:relative; display:inline-block; max-width:100%;">
                ${safeImageMarkup}
                ${hotspotsHtml}
            </div>
            <div style="display:flex; gap:0.35rem; flex-wrap:wrap; margin-top:0.55rem;">${legendHtml}</div>
        `;
    }

    renderMultipleChoice(question, index) {
        const savedAnswer = this.answers[question.id];
        let optionsHtml = '';
        const letters = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H'];

        // Null safety for options
        const options = question.options || [];
        const model2Enabled = this.isModel2Enabled(question, options);

        if (model2Enabled) {
            optionsHtml = this.renderModel2Layout(question, options, savedAnswer, false);
        } else {
            options.forEach((opt, i) => {
                const isSelected = savedAnswer == opt.id;
                const letter = letters[i] || (i + 1);
                optionsHtml += `
                    <div class="option-item ${isSelected ? 'selected' : ''}"
                         data-option-id="${opt.id}"
                         onclick="window.examSystem.selectOption(${question.id}, '${opt.id}')">
                        <div class="option-letter">${isSelected ? '✓' : letter}</div>
                        <span class="option-text">${escapeHtml(opt.option_text)}</span>
                    </div>
                `;
            });
        }

        // Render video if present
        const videoHtml = renderQuestionVideo(question.video_url);

        // Render audio if present
        const audioHtml = renderQuestionAudio(question.audio_url);

        // Determine Badge Label and Color based on type
        const isTrueFalse = question.question_type === 'true_false';
        const typeLabel = isTrueFalse ? 'Benar / Salah' : 'Pilihan Ganda';
        // Blue (#3b82f6) for Multiple Choice, Orange (#f59e0b) for True/False to distinguish
        const badgeColor = isTrueFalse ? '#f59e0b' : '#3b82f6';

        return `
            <div class="question-card fade-in">
                <div class="question-header">
                    <span class="question-number">Soal ${index + 1} dari ${this.questions.length}</span>
                    <span class="question-badge" style="background: ${badgeColor}; padding: 0.25rem 0.5rem; border-radius: 0.25rem; font-size: 0.75rem; color: white;">${typeLabel}</span>
                </div>
                <div class="question-text">${renderExamRichText(question.question_text)}</div>
                ${this.renderQuestionBehaviorHint(question)}
                ${question.image_url && !model2Enabled ? renderQuestionImage(question.image_url) : ''}
                ${videoHtml}
                ${audioHtml}
                <div class="options-list">${optionsHtml}</div>
            </div>
            ${this.renderNavigationButtons(index)}
        `;
    }

    renderComplexChoice(question, index) {
        const savedAnswers = this.answers[question.id] || [];
        const settings = question.question_settings || {};
        const minCorrect = settings.min_correct || 1;
        const letters = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H'];

        // Null safety for options
        const options = question.options || [];
        const maxCorrect = settings.max_correct || options.length;

        // Render stimulus if available (AKM-style)
        let stimulusHtml = '';
        if (question.stimulus && question.stimulus.trim()) {
            stimulusHtml = `
                <div class="stimulus-card">
                    <div class="stimulus-label">
                        <i class="fas fa-book-open"></i>
                        <span>Stimulus / Konteks</span>
                    </div>
                    <div class="stimulus-text">${renderExamRichText(question.stimulus)}</div>
                </div>
            `;
        }

        // Get pgk_type from question settings or direct field
        const pgkType = question.pgk_type || settings.pgk_type || 'checkbox';
        const model2Enabled = pgkType !== 'table_validation' && this.isModel2Enabled(question, options);

        let contentHtml = '';

        if (pgkType === 'table_validation') {
            // TYPE B: Table Validation (Benar/Salah statements)
            const statements = settings.statements || question.statements || [];
            const savedStatementAnswers = typeof savedAnswers === 'object' && !Array.isArray(savedAnswers)
                ? savedAnswers : {};

            let tableRowsHtml = '';
            statements.forEach((stmt, displayIndex) => {
                // Handle shuffled statements (objects) or legacy/unshuffled (strings)
                const isObject = typeof stmt === 'object' && stmt !== null;
                const text = isObject ? stmt.text : stmt;
                const logicIndex = isObject ? stmt.original_index : displayIndex;

                // Use logicIndex (original DB index) for retrieving saved answer
                const savedValue = savedStatementAnswers[logicIndex];
                const isBenarSelected = savedValue === true;
                const isSalahSelected = savedValue === false;

                tableRowsHtml += `
                    <div class="statement-row" data-statement-index="${logicIndex}">
                        <div class="statement-num">${displayIndex + 1}</div>
                        <div class="statement-text">${renderExamRichText(text)}</div>
                        <div>
                            <label class="radio-btn benar ${isBenarSelected ? 'selected' : ''}">
                                <input type="radio" name="stmt_${question.id}_${logicIndex}" value="true"
                                       ${isBenarSelected ? 'checked' : ''}
                                       onchange="window.examSystem.setStatementAnswer(${question.id}, ${logicIndex}, true)"
                                       style="display: none;">
                                <span>Benar</span>
                            </label>
                        </div>
                        <div>
                            <label class="radio-btn salah ${isSalahSelected ? 'selected' : ''}">
                                <input type="radio" name="stmt_${question.id}_${logicIndex}" value="false"
                                       ${isSalahSelected ? 'checked' : ''}
                                       onchange="window.examSystem.setStatementAnswer(${question.id}, ${logicIndex}, false)"
                                       style="display: none;">
                                <span>Salah</span>
                            </label>
                        </div>
                    </div>
                `;
            });

	            contentHtml = `
	                <div class="table-hint">
	                    <i class="fas fa-table"></i>
	                    <span>Tentukan setiap pernyataan Benar atau Salah</span>
	                </div>
	                <div class="table-validation">
	                    <div class="table-header">
                        <div>No</div>
                        <div>Pernyataan</div>
                        <div>Benar</div>
                        <div>Salah</div>
                    </div>
                    ${tableRowsHtml}
                </div>
            `;
        } else {
            // TYPE A: Multiple Response (Checkbox)
            if (model2Enabled) {
                contentHtml = this.renderModel2Layout(question, options, savedAnswers, true);
            } else {
                let optionsHtml = '';
                options.forEach((opt, i) => {
                    const isSelected = Array.isArray(savedAnswers) && savedAnswers.some(id => id == opt.id);
                    const letter = letters[i] || (i + 1);
                    optionsHtml += `
                        <div class="option-item checkbox-option ${isSelected ? 'selected' : ''}"
                             data-option-id="${opt.id}"
                             onclick="document.getElementById('opt_${opt.id}').click()">
                            <div class="option-letter">${isSelected ? '✓' : letter}</div>
                            <input type="checkbox"
                                   id="opt_${opt.id}"
                                   value="${opt.id}"
                                   ${isSelected ? 'checked' : ''}
                                   onchange="event.stopPropagation(); window.examSystem.toggleComplexOption(${question.id}, '${opt.id}', this.checked)"
                                   style="display: none;">
                            <span class="option-text">${escapeHtml(opt.option_text)}</span>
                        </div>
                    `;
                });

                contentHtml = `
                    <div class="table-hint">
                        <i class="fas fa-info-circle"></i>
                        <span>Pilih semua jawaban yang benar</span>
                    </div>
                    <div class="options-list">${optionsHtml}</div>
                `;
            }
        }

        // Render video if present
        const videoHtml = renderQuestionVideo(question.video_url);

        // Render audio if present
        const audioHtml = renderQuestionAudio(question.audio_url);

        return `
            <div class="question-card fade-in">
                <div class="question-header">
                    <span class="question-number">Soal ${index + 1} dari ${this.questions.length}</span>
                    <span class="question-badge">HOTS - ${pgkType === 'table_validation' ? 'Tabel' : 'PGK'}</span>
                </div>
                ${stimulusHtml}
                <div class="question-text">${renderExamRichText(question.question_text)}</div>
                ${this.renderQuestionBehaviorHint(question)}
                ${question.image_url && !model2Enabled ? renderQuestionImage(question.image_url) : ''}
                ${videoHtml}
                ${audioHtml}
                ${contentHtml}
            </div>
            ${this.renderNavigationButtons(index)}
        `;
    }


    renderEssay(question, index) {
        const savedAnswer = this.answers[question.id] || '';
        const settings = question.question_settings || {};
        const minWords = settings.min_words || 0;

        // Render video if present
        const videoHtml = renderQuestionVideo(question.video_url);

        // Render audio if present
        const audioHtml = renderQuestionAudio(
            question.audio_url,
            'margin: 1.5rem 0;',
            'width: 100%; max-width: 600px; border-radius: 0.5rem; box-shadow: 0 4px 12px rgba(0,0,0,0.3);'
        );

        return `
            <div class="question-card fade-in essay">
                <div class="question-header">
                    <span class="question-number">Soal ${index + 1} dari ${this.questions.length}</span>
                    <span class="question-badge" style="background: #6366f1; padding: 0.25rem 0.5rem; border-radius: 0.25rem; font-size: 0.75rem; color: white;">Essay</span>
                </div>
                <div class="question-text">${renderExamRichText(question.question_text)}</div>
                ${this.renderQuestionBehaviorHint(question)}
                ${question.image_url ? renderQuestionImage(question.image_url) : ''}
                ${videoHtml}
                ${audioHtml}
                <div class="answer-input-wrapper" style="margin-top: 1rem;">
                    <textarea
                        class="essay-input form-control"
                        style="min-height: 200px; width: 100%; resize: vertical;"
                        placeholder="Ketik jawaban Anda di sini..."
                        oninput="window.examSystem.updateTextAnswer(${question.id}, this.value)">${escapeHtml(savedAnswer)}</textarea>
                    ${minWords > 0 ? `<small style="color: #888;">Minimal ${minWords} kata</small>` : ''}
                </div>
            </div>
            ${this.renderNavigationButtons(index)}
        `;
    }

    renderShortAnswer(question, index) {
        const savedAnswer = this.answers[question.id] || '';

        // Render video if present
        const videoHtml = renderQuestionVideo(question.video_url);

        // Render audio if present
        const audioHtml = renderQuestionAudio(
            question.audio_url,
            'margin: 1.5rem 0;',
            'width: 100%; max-width: 600px; border-radius: 0.5rem; box-shadow: 0 4px 12px rgba(0,0,0,0.3);'
        );

        return `
            <div class="question-card fade-in short-answer">
                <div class="question-header">
                    <span class="question-number">Soal ${index + 1} dari ${this.questions.length}</span>
                    <span class="question-badge" style="background: #10b981; padding: 0.25rem 0.5rem; border-radius: 0.25rem; font-size: 0.75rem; color: white;">Isian Singkat</span>
                </div>
                <div class="question-text">${renderExamRichText(question.question_text)}</div>
                ${this.renderQuestionBehaviorHint(question)}
                ${question.image_url ? renderQuestionImage(question.image_url) : ''}
                ${videoHtml}
                ${audioHtml}
                <div class="answer-input-wrapper" style="margin-top: 1rem;">
                    <input type="text"
                           class="short-answer-input form-control"
                           style="padding: 0.75rem; width: 100%;"
                           placeholder="Ketik jawaban Anda di sini..."
                           value="${escapeAttribute(savedAnswer)}"
                           oninput="window.examSystem.updateTextAnswer(${question.id}, this.value)">
                </div>
            </div>
            ${this.renderNavigationButtons(index)}
        `;
    }

    renderNavigationButtons(index) {
        // Navigation is now handled by fixed footer, return empty string
        // Update flag button state in footer
        const questionId = this.questions[index]?.id;
        const isFlagged = this.flagged.has(questionId);
        const flagBtn = document.getElementById('flag-btn');
        if (flagBtn) {
            flagBtn.classList.toggle('flagged', isFlagged);
            const icon = flagBtn.querySelector('i');
            if (icon) {
                icon.className = isFlagged ? 'fas fa-flag' : 'far fa-flag';
            }
        }
        return '';
    }

    async selectOption(questionId, optionId) {
        const finalId = /^\d+$/.test(optionId) ? parseInt(optionId) : optionId;
        this.answers[questionId] = finalId;

        // UI Update (Faster feedback)
        const container = document.getElementById('question-container');
        if (container) {
            container.querySelectorAll('.option-item').forEach(item => {
                const isSelected = item.dataset.optionId == String(optionId);
                item.classList.toggle('selected', isSelected);
                const radio = item.querySelector('.option-radio');
                if (radio) radio.textContent = isSelected ? '✓' : radio.textContent.replace('✓', '').trim() || '-';
            });
            container.querySelectorAll('.model2-hotspot').forEach((item) => {
                const isSelected = item.dataset.optionId == String(optionId);
                item.classList.toggle('selected', isSelected);
                item.style.border = isSelected ? '2px solid #22c55e' : '2px solid rgba(148,163,184,0.75)';
                item.style.background = isSelected
                    ? 'linear-gradient(135deg,#22c55e,#16a34a)'
                    : 'rgba(15,23,42,0.8)';
                const badge = item.querySelector('.model2-hotspot-badge');
                if (badge) badge.textContent = isSelected ? '✓' : (item.dataset.label || '?');
            });
        }

        try {
            await this.submitAnswer(questionId, { selected_option_id: finalId });
        } catch (error) { console.error(error); }
        this.updateNavigator();
    }

    async toggleComplexOption(questionId, optionId, isChecked) {
        if (!this.answers[questionId]) this.answers[questionId] = [];
        const finalId = /^\d+$/.test(optionId) ? parseInt(optionId) : optionId;

        if (isChecked) {
            if (!this.answers[questionId].some(id => String(id) === String(finalId))) {
                this.answers[questionId].push(finalId);
            }
        } else {
            this.answers[questionId] = this.answers[questionId].filter(id => String(id) !== String(finalId));
        }

        // UI Update - Instant visual feedback (same pattern as selectOption)
        const container = document.getElementById('question-container');
        if (container) {
            container.querySelectorAll('.option-item.checkbox-option').forEach(item => {
                const itemOptionId = item.dataset.optionId;
                const isThisSelected = this.answers[questionId].some(id => String(id) === String(itemOptionId));

                // Update selected class
                item.classList.toggle('selected', isThisSelected);

                // Update visual styling directly
                item.style.background = isThisSelected
                    ? 'linear-gradient(135deg, rgba(34, 197, 94, 0.15), rgba(34, 197, 94, 0.05))'
                    : 'rgba(30, 41, 59, 0.6)';
                item.style.border = isThisSelected
                    ? '2px solid #22c55e'
                    : '2px solid rgba(99, 102, 241, 0.3)';

                // Update letter/checkmark indicator
                const letterDiv = item.querySelector('div[style*="width: 44px"]');
                if (letterDiv) {
                    const letters = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H'];
                    const itemIndex = Array.from(container.querySelectorAll('.option-item.checkbox-option')).indexOf(item);
                    letterDiv.textContent = isThisSelected ? '✓' : (letters[itemIndex] || (itemIndex + 1));
                    letterDiv.style.background = isThisSelected
                        ? 'linear-gradient(135deg, #22c55e, #16a34a)'
                        : 'rgba(99, 102, 241, 0.2)';
                    letterDiv.style.color = isThisSelected ? 'white' : '#a5b4fc';
                }

                // Update hidden checkbox state
                const checkbox = item.querySelector('input[type="checkbox"]');
                if (checkbox) {
                    checkbox.checked = isThisSelected;
                }
            });

            container.querySelectorAll('.model2-hotspot.multi').forEach((item) => {
                const itemOptionId = item.dataset.optionId;
                const isThisSelected = this.answers[questionId].some(id => String(id) === String(itemOptionId));
                item.classList.toggle('selected', isThisSelected);
                item.style.border = isThisSelected ? '2px solid #22c55e' : '2px solid rgba(148,163,184,0.75)';
                item.style.background = isThisSelected
                    ? 'linear-gradient(135deg,#22c55e,#16a34a)'
                    : 'rgba(15,23,42,0.8)';
                const badge = item.querySelector('.model2-hotspot-badge');
                if (badge) badge.textContent = isThisSelected ? '✓' : (item.dataset.label || '?');
            });
        }

        // Defensive: Pastikan array jawaban tidak kosong sebelum submit
        const currentAnswers = this.answers[questionId] || [];
        if (currentAnswers.length > 0) {
            try {
                await this.submitAnswer(questionId, { selected_option_ids: currentAnswers });
            } catch (error) { console.error(error); }
        } else {
            console.warn('⚠️ toggleComplexOption: Tidak ada jawaban untuk Q', questionId);
        }

        this.updateNavigator();
    }

    // Type B: Table Validation - Set statement answer (Benar/Salah)
    async setStatementAnswer(questionId, statementIndex, isBenar) {
        // Initialize as object if not exists or if wrong type
        if (!this.answers[questionId] || typeof this.answers[questionId] !== 'object' || Array.isArray(this.answers[questionId])) {
            this.answers[questionId] = {};
        }

        // Set the boolean value for this statement
        this.answers[questionId][statementIndex] = isBenar;

        // UI Update - Instant visual feedback using CSS classes
        const container = document.getElementById('question-container');
        if (container) {
            const statementRow = container.querySelector(`.statement-row[data-statement-index="${statementIndex}"]`);
            if (statementRow) {
                // Get benar and salah labels using their specific classes
                const benarLabel = statementRow.querySelector('label.radio-btn.benar');
                const salahLabel = statementRow.querySelector('label.radio-btn.salah');

                // Toggle selected class based on answer
                if (benarLabel) {
                    benarLabel.classList.toggle('selected', isBenar === true);
                }
                if (salahLabel) {
                    salahLabel.classList.toggle('selected', isBenar === false);
                }
            }
        }

        // Defensive: Pastikan object jawaban tidak kosong sebelum submit
        const currentStatementAnswers = this.answers[questionId] || {};
        const hasAnswers = Object.keys(currentStatementAnswers).length > 0;

        // Submit to server - use statement_answers format
        if (hasAnswers) {
            try {
                await this.submitAnswer(questionId, { statement_answers: currentStatementAnswers });
            } catch (error) { console.error(error); }
        } else {
            console.warn('⚠️ setStatementAnswer: Tidak ada jawaban untuk Q', questionId);
        }

        this.updateNavigator();
    }

    async updateTextAnswer(questionId, text) {
        this.answers[questionId] = text;
        if (this.textAnswerTimeout) clearTimeout(this.textAnswerTimeout);

        this.textAnswerTimeout = setTimeout(async () => {
            // Defensive: Pastikan text tidak kosong sebelum submit
            if (!text || text.trim() === '') {
                console.warn('⚠️ updateTextAnswer: Text kosong, skip submit untuk Q', questionId);
                return;
            }
            const textToSubmit = String(text).trim();
            console.log('📝 updateTextAnswer: Submitting text untuk Q', questionId, ':', textToSubmit.substring(0, 50) + '...');
            try {
                await this.submitAnswer(questionId, { answer_text: textToSubmit });
            } catch (error) { console.error(error); }
        }, 2000);
        this.updateNavigator();
    }

    async updateMatchingPair(pairId, rightOptionId, questionId) {
        if (!this.answers[questionId]) this.answers[questionId] = {};

        // Smart Cast Value
        let finalValue = rightOptionId;
        if (typeof rightOptionId === 'string' && /^\d+$/.test(rightOptionId)) {
            finalValue = parseInt(rightOptionId);
        }

        if (rightOptionId && rightOptionId !== "") {
            this.answers[questionId][pairId] = finalValue;
        } else {
            delete this.answers[questionId][pairId];
        }

        try {
            await this.submitAnswer(questionId, { matching_pairs: this.answers[questionId] });
        } catch (error) { console.error(error); }
        this.updateNavigator();
    }

    async submitAnswer(questionId, answerData) {
        // DEBUG: Log data yang akan dikirim
        console.log('🔍 DEBUG submitAnswer:', {
            questionId,
            answerData,
            currentAnswers: this.answers[questionId],
            sessionId: this.sessionId
        });

        // Defensive check: Pastikan data tidak kosong
        if (!answerData || Object.keys(answerData).length === 0) {
            console.warn('⚠️ submitAnswer: answerData kosong, skip submit');
            return;
        }

        // Defensive check: Pastikan tidak ada nilai undefined/null yang tidak perlu
        const cleanedAnswerData = {};
        for (const [key, value] of Object.entries(answerData)) {
            if (value !== undefined && value !== null) {
                cleanedAnswerData[key] = value;
            }
        }

        // Jika setelah cleaning data kosong, skip submit
        if (Object.keys(cleanedAnswerData).length === 0) {
            console.warn('⚠️ submitAnswer: cleanedAnswerData kosong, skip submit');
            return;
        }

        if (!this.answerRevisions[questionId]) {
            this.answerRevisions[questionId] = 0;
        }
        this.answerRevisions[questionId] += 1;

        const metadata = (typeof cleanedAnswerData.answer_metadata === 'object' && cleanedAnswerData.answer_metadata !== null)
            ? { ...cleanedAnswerData.answer_metadata }
            : {};
        metadata.client_revision = this.answerRevisions[questionId];
        metadata.client_answer_ts = Date.now();
        cleanedAnswerData.answer_metadata = metadata;

        const journalPayload = {
            session_id: this.sessionId,
            exam_id: this.examId,
            question_id: parseInt(questionId) || 0,
            ...cleanedAnswerData
        };
        notifyNativeAnswerJournal(journalPayload);
        if (journalWorker) {
            journalWorker.enqueue(journalPayload);
        }
        this.pushRuntimeStateToNative(false);

        // Legacy matching payloads still use the old direct endpoint.
        if (cleanedAnswerData.matching_pairs !== undefined) {
            try {
                await api.submitAnswer(this.sessionId, questionId, cleanedAnswerData);
                if (storageManager) {
                    await storageManager.saveAnswer(this.sessionId, questionId, cleanedAnswerData);
                }
                console.log('✅ submitAnswer berhasil untuk Q', questionId);
            } catch (error) {
                console.error('❌ submitAnswer error:', error);
                throw error;
            }
            return;
        }

        if (storageManager) {
            await storageManager.saveAnswerLocal(this.sessionId, questionId, cleanedAnswerData);
        }

        this.scheduleAnswerSync();
    }

    scheduleAnswerSync() {
        if (this.pendingSyncTimeout) {
            clearTimeout(this.pendingSyncTimeout);
        }

        this.pendingSyncTimeout = setTimeout(async () => {
            this.pendingSyncTimeout = null;
            if (!navigator.onLine || !syncWorker) return;

            try {
                await syncWorker.syncNow();
            } catch (error) {
                console.warn('⚠️ Debounced sync failed:', error?.message || error);
            }
        }, this.runtimePolicy.answer_sync_debounce_ms || 5000);
    }

    async autoSave() {
        try {
            if (syncWorker) {
                if (!syncWorker.sessionId && this.sessionId) {
                    syncWorker.start(this.sessionId);
                }
                await syncWorker.syncNow();
                if (storageManager && this.sessionId) {
                    const pendingAnswers = await storageManager.getUnsyncedAnswers(this.sessionId);
                    if (pendingAnswers.length > 0) {
                        await this.flushPendingAnswersForForceSubmit();
                    }
                }
            } else {
                await this.flushPendingAnswersForForceSubmit();
            }
            if (journalWorker) {
                if (!journalWorker.sessionId && this.sessionId) {
                    journalWorker.start(this.sessionId);
                }
                await journalWorker.flushNow();
            }
        } catch (error) { console.error('Auto-save failed:', error); }
    }

    /**
     * Notify Flutter that exam is submitted
     * This disables the kiosk mode and security features
     */
    notifyFlutterExamSubmitted() {
        try {
            if (window.flutter_inappwebview && window.flutter_inappwebview.callHandler) {
                console.log('Notifying Flutter: exam submitted');
                window.flutter_inappwebview.callHandler('examSubmitted');
            }
        } catch (e) { console.log('Flutter handler not available'); }
    }

    /**
     * Record violation from Flutter/Native
     * Called by injected JS from Flutter
     */
    recordViolation(type, count) {
        const label = this.getViolationLabel(type);
        console.warn(`Violation recorded: ${type} (${count})`);
        showNotification(`PERINGATAN: ${label} terdeteksi! (${count})`, count >= 3 ? 'error' : 'warning');
    }

    /**
     * Force submit triggered by Flutter (e.g. enhanced security violation)
     * Called by injected JS from Flutter
     */
    async forceSubmitDueToViolations() {
        console.error('FORCE SUBMIT triggered due to violations');
        showNotification('Ujian dihentikan paksa karena pelanggaran keamanan!', 'error');

        // Wait a small moment to ensure user sees the notification
        await new Promise(r => setTimeout(r, 1500));

        await this.flushPendingAnswersForForceSubmit();
        await this.submitExam(false); // Submit without confirmation
    }

    buildBatchAnswersPayload() {
        const items = [];

        for (const [questionIdRaw, value] of Object.entries(this.answers || {})) {
            const questionId = parseInt(questionIdRaw, 10);
            if (!questionId || Number.isNaN(questionId)) continue;

            let answerObj = null;
            if (Array.isArray(value)) {
                answerObj = { selected_option_ids: value };
            } else if (typeof value === 'number') {
                answerObj = { selected_option_id: value };
            } else if (typeof value === 'string') {
                const trimmed = value.trim();
                if (!trimmed) continue;
                answerObj = { answer_text: trimmed };
            } else if (value && typeof value === 'object') {
                // True/False table answers (all boolean-like values)
                const entries = Object.entries(value);
                const isStatementAnswers = entries.length > 0 && entries.every(([_, v]) =>
                    typeof v === 'boolean' || typeof v === 'number' || typeof v === 'string'
                );
                answerObj = isStatementAnswers
                    ? { statement_answers: value }
                    : value;
            } else {
                continue;
            }

            const normalized = api.normalizeAnswerPayload(answerObj || {});
            if (!normalized || Object.keys(normalized).length === 0) continue;

            items.push({
                question_id: questionId,
                ...normalized
            });
        }

        return items;
    }

    async flushPendingAnswersForForceSubmit() {
        try {
            if (this.pendingSyncTimeout) {
                clearTimeout(this.pendingSyncTimeout);
                this.pendingSyncTimeout = null;
            }
            if (this.textAnswerTimeout) {
                clearTimeout(this.textAnswerTimeout);
                this.textAnswerTimeout = null;
            }

            const answers = this.buildBatchAnswersPayload();
            if (!answers.length) return;

            await api.request('POST', '/exams/auto-save-batch', {
                session_id: parseInt(this.sessionId) || 0,
                answers
            });
            console.log(`💾 Force-submit flush saved ${answers.length} answers`);
        } catch (e) {
            console.warn('⚠️ Force-submit flush failed:', e?.message || e);
        }
    }

    async submitExam(shouldShowConfirm = true) {
        if (this.submitInProgress) {
            return;
        }
        this.submitInProgress = true;

        // Note: shouldShowConfirm is a boolean flag, not a modal function
        // The confirmation is handled by the submit modal in HTML, not here
        // This method is called with shouldShowConfirm=false for auto-submit (timer expired, force submit)

        try {
            const submitModal = document.getElementById('submit-modal');
            if (submitModal) submitModal.classList.remove('active');

            await this.autoSave();
            await this.flushPendingAnswersForForceSubmit();
            const result = await api.submitExam(this.sessionId);

            console.log('📊 Submit Result:', result);
            console.log('📊 Show Results Flag:', this.showResults);
            console.log('📊 Score:', result.score);

            clearInterval(this.timerInterval);
            clearInterval(this.autoSaveInterval);
            if (syncWorker) syncWorker.stop();
            if (journalWorker) journalWorker.stop();
            if (storageManager) await storageManager.clearSessionAnswers(this.sessionId);
            ExamSystem.clearSessionStorage();

            // 🔓 CRITICAL: Notify Flutter app to disable security features
            this.notifyFlutterExamSubmitted();
            // Wait for Flutter to process unlock before navigating
            await new Promise(resolve => setTimeout(resolve, 500));

            // DECISION POINT: Show results or skip?
            // FIX: Check for both undefined AND null to handle show_results=False properly
            if (this.showResults && result.score !== undefined && result.score !== null) {
                // ✅ SHOW RESULTS with 10-second timer
                console.log('✅ Showing results with timer');
                this.showResultsWithTimer(result.score);
            } else {
                // ❌ SKIP RESULTS, redirect immediately
                console.log('❌ Skipping results, redirecting...');
                showNotification('Ujian berhasil dikumpulkan! Nilai akan diumumkan oleh guru.', 'success');
                setTimeout(() => {
                    window.location.href = '/student/';
                }, 2000);  // Small delay to show notification
            }
        } catch (error) {
            console.error('Submit error:', error);

            // Check if exam was already submitted
            if (error.message && error.message.includes('sudah dikumpulkan')) {
                console.log('✅ Exam already submitted, redirecting to dashboard...');
                showNotification('Ujian sudah dikumpulkan sebelumnya. Mengarahkan ke dashboard...', 'info');
                setTimeout(() => {
                    window.location.href = '/student/';
                }, 2000);
                return;
            }

            const errorMsg = 'Gagal mengumpulkan ujian: ' + error.message;
            showNotification(errorMsg, 'error');
        } finally {
            this.submitInProgress = false;
        }
    }

    showResultsWithTimer(score) {
        // 🛡️ DEFENSE IN DEPTH: Safety check to prevent showing results when disabled
        // Even if this method is called incorrectly, we validate again
        if (!this.showResults || score === null || score === undefined) {
            console.warn('⚠️ showResultsWithTimer called but show_results=false or score invalid');
            console.log('showResults flag:', this.showResults, 'score:', score);
            showNotification('Ujian berhasil dikumpulkan! Nilai akan diumumkan oleh guru.', 'success');
            setTimeout(() => {
                window.location.href = '/student/';
            }, 2000);
            return;
        }

        const successModal = document.getElementById('success-modal');
        if (!successModal) {
            // Prepare result data for result.html page
            const resultData = {
                score: score,
                correct: 0, // Will be calculated by server
                total: this.questions.length,
                passed: true, // Will be recalculated
                // Include metadata for result page display
                subject: this.examMetadata?.subject || null,
                exam_type: this.examMetadata?.exam_type || null,
                exam_title: this.examMetadata?.exam_title || null
            };
            sessionStorage.setItem('exam_result', JSON.stringify(resultData));
            window.location.href = '/student/result.html';
            return;
        }

        // Display modal
        successModal.classList.add('active');

        // Update score display with professional styling
        const statusEl = document.getElementById('success-status');
        if (statusEl) {
            statusEl.innerHTML = `
                <div style="font-size: 2.5rem; font-weight: 700; margin-bottom: 0.5rem; background: linear-gradient(135deg, #22c55e, #10b981); background-clip: text; -webkit-background-clip: text; -webkit-text-fill-color: transparent;">
                    ${score}
                </div>
                <div style="font-size: 0.9rem; opacity: 0.9; color: var(--text-secondary);">Nilai Anda</div>
            `;
        }

        // Update button to show countdown
        const resultButton = document.getElementById('result-button');
        if (!resultButton) return;

        let countdown = 10;
        resultButton.innerHTML = `<i class="fas fa-chart-bar"></i> Kembali ke Dashboard (${countdown})`;

        // Countdown interval
        const countdownInterval = setInterval(() => {
            countdown--;
            if (countdown > 0) {
                resultButton.innerHTML = `<i class="fas fa-chart-bar"></i> Kembali ke Dashboard (${countdown})`;
            } else {
                clearInterval(countdownInterval);
                window.location.href = '/student/';
            }
        }, 1000);

        // Allow user to skip countdown by clicking button
        resultButton.onclick = () => {
            clearInterval(countdownInterval);
            window.location.href = '/student/';
        };
    }

    nextQuestion() {
        if (this.currentQuestionIndex < this.questions.length - 1) {
            this.renderQuestion(this.currentQuestionIndex + 1);
        }
    }

    prevQuestion() {
        if (this.currentQuestionIndex > 0) {
            this.renderQuestion(this.currentQuestionIndex - 1);
        }
    }

    jumpToQuestion(index) {
        if (index >= 0 && index < this.questions.length) {
            this.renderQuestion(index);
        }
    }

    toggleFlag() {
        const questionId = this.questions[this.currentQuestionIndex]?.id;
        if (!questionId) return;

        if (this.flagged.has(questionId)) {
            this.flagged.delete(questionId);
        } else {
            this.flagged.add(questionId);
        }
        this.renderQuestion(this.currentQuestionIndex);
        this.updateNavigator();
    }

    updateNavigator() {
        const navigator = document.getElementById('question-navigator');
        if (!navigator) return;

        let navHtml = '';
        this.questions.forEach((q, i) => {
            let isAnswered = false;
            const ans = this.answers[q.id];
            if (ans !== undefined && ans !== null && ans !== '') {
                if (Array.isArray(ans)) isAnswered = ans.length > 0;
                else if (typeof ans === 'object') isAnswered = Object.keys(ans).length > 0;
                else isAnswered = true;
            }

            const isCurrent = i === this.currentQuestionIndex;
            const isFlagged = this.flagged.has(q.id);

            navHtml += `
                <button class="question-nav-btn ${isAnswered ? 'answered' : ''} ${isCurrent ? 'current' : ''} ${isFlagged ? 'flagged' : ''}"
                     onclick="window.examSystem.jumpToQuestion(${i}); toggleNavigator();"
                     title="Soal ${i + 1}">
                    ${i + 1}
                </button>
            `;
        });
        navigator.innerHTML = navHtml;

        const answeredCount = this.questions.reduce((count, q) => {
            const ans = this.answers[q.id];
            let hasAnswer = false;
            if (ans !== undefined && ans !== null && ans !== '') {
                if (Array.isArray(ans)) hasAnswer = ans.length > 0;
                else if (typeof ans === 'object') hasAnswer = Object.keys(ans).length > 0;
                else hasAnswer = true;
            }
            return count + (hasAnswer ? 1 : 0);
        }, 0);

        const countEl = document.getElementById('answered-count');
        if (countEl) countEl.textContent = `${answeredCount}/${this.questions.length}`;

        const flaggedEl = document.getElementById('flagged-count');
        if (flaggedEl) flaggedEl.textContent = this.flagged.size;

        const remainingEl = document.getElementById('remaining-count');
        if (remainingEl) remainingEl.textContent = this.questions.length - answeredCount;

        // Update progress bar with dynamic color
        const progressBar = document.getElementById('progress-bar');
        if (progressBar && this.questions.length > 0) {
            const percentage = (answeredCount / this.questions.length) * 100;
            progressBar.style.width = `${percentage}%`;

            // Remove all color classes
            progressBar.classList.remove('low', 'medium', 'high', 'complete');

            // Add appropriate color class based on percentage
            if (percentage >= 100) {
                progressBar.classList.add('complete');
            } else if (percentage >= 75) {
                progressBar.classList.add('high');
            } else if (percentage >= 40) {
                progressBar.classList.add('medium');
            } else {
                progressBar.classList.add('low');
            }
        }
    }

    getToken() {
        return localStorage.getItem('access_token');
    }
}

window.examSystem = null;
