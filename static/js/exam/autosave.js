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
