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
