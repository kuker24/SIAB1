/**
 * AUTO-GENERATED FILE.
 * Source modules: static/js/api/modules/*.js
 * Use scripts/build_api_bundle.sh after editing modules.
 */

/* ===== Module: 00-runtime-core.js ===== */

/**
 * PRODUCTION MODE — Silence all console output
 * Remove or comment this block to enable debug logging
 */
(function() {
    var noop = function() {};
    ['log', 'debug', 'info', 'warn', 'dir', 'time', 'timeEnd', 'table', 'group', 'groupEnd'].forEach(function(method) {
        console[method] = noop;
    });
    // console.error tetap aktif untuk monitoring error di production
})();

/**
 * API Client for Sistem Ujian Online v3.0 - GOD MODE
 * ENHANCED WITH: Silent Token Refresh Interceptor + Request Queue Management
 *
 * CRITICAL FEATURES:
 * 1. Token Refresh Interceptor - Auto-refresh on 401 without user knowing
 * 2. Request Queue - Pause/retry failed requests after token refresh
 * 3. Type-safe payload helpers
 */

/**
 * API Base URL Configuration
 *
 * Namespace routing:
 * - Student pages   -> /api/student
 * - Admin pages     -> /api/admin
 * - Developer pages -> /api/admin
 * - Pengawas pages  -> /api/pengawas
 * - Teacher pages   -> /api/teacher
 * - Admin login     -> /api/control (before role is known)
 * - Fallback        -> /api
 */
const API_BASE_URL = (() => {
    const origin = window.location.origin;
    const pathname = window.location.pathname || '/';
    let userRole = '';
    let userJobTitle = '';

    try {
        const rawUser = localStorage.getItem('user');
        if (rawUser) {
            const parsed = JSON.parse(rawUser);
            userRole = String(parsed?.role || '').toLowerCase();
            userJobTitle = String(parsed?.job_title || '').toLowerCase();
        }
    } catch (_) {
        userRole = '';
        userJobTitle = '';
    }

    if (pathname.startsWith('/student')) {
        return `${origin}/api/student`;
    }

    if (pathname.startsWith('/admin')) {
        if (userRole === 'admin' || userRole === 'developer') {
            return `${origin}/api/admin`;
        }
        if (userRole === 'teacher') {
            if (userJobTitle.includes('pengawas') || userJobTitle === 'proktor' || userJobTitle === 'invigilator') {
                return `${origin}/api/pengawas`;
            }
            return `${origin}/api/teacher`;
        }
        return `${origin}/api/control`;
    }

    return `${origin}/api`;
})();

const API_DEBUG_ENABLED = (() => {
    try {
        const query = new URLSearchParams(window.location.search || '');
        const fromQuery = query.get('debug_api') === '1';
        const fromStorage = localStorage.getItem('debug_api') === '1'
            || localStorage.getItem('api_debug') === '1';
        return fromQuery || fromStorage;
    } catch (_) {
        return false;
    }
})();

function apiDebug(...args) {
    if (API_DEBUG_ENABLED) {
        console.log(...args);
    }
}

class ApiClient {
    // Retry configuration constants
    static MAX_RETRIES = 2;
    static BASE_DELAY_MS = 800; // 0.8 second
    static REQUEST_TIMEOUT_MS = 15000; // default requests
    static REQUEST_TIMEOUT_LOGIN_MS = 60000;
    static REQUEST_TIMEOUT_EXAM_START_MS = 90000;
    static REQUEST_TIMEOUT_SUBMIT_MS = 90000;

    static getTimeoutForEndpoint(endpoint) {
        if (/^\/auth\/(signin|login)$/.test(endpoint)) {
            return ApiClient.REQUEST_TIMEOUT_LOGIN_MS;
        }
        if (/^\/exams\/\d+\/start$/.test(endpoint)) {
            return ApiClient.REQUEST_TIMEOUT_EXAM_START_MS;
        }
        if (/^\/exams\/(submit|submit-answer)(\/|$)/.test(endpoint)) {
            return ApiClient.REQUEST_TIMEOUT_SUBMIT_MS;
        }
        return ApiClient.REQUEST_TIMEOUT_MS;
    }

    constructor() {
        this.token = localStorage.getItem('access_token');
        this.isRefreshing = false;
        this.refreshPromise = null;
        this.failedQueue = [];
    }

    isValidAppSignature(signature) {
        if (!signature) return false;
        const normalized = String(signature).trim().replace(/:/g, '').toLowerCase();
        return /^[0-9a-f]{64}$/.test(normalized);
    }

    setToken(token) {
        this.token = token;
        localStorage.setItem('access_token', token);
    }

    clearToken() {
        this.token = null;
        localStorage.removeItem('access_token');
        localStorage.removeItem('user');
    }

    getHeaders() {
        // Keep token in sync with latest localStorage value (important for auto-login injection timing).
        const storageToken = localStorage.getItem('access_token');
        if (storageToken && storageToken !== this.token) {
            this.token = storageToken;
        }

        const headers = {
            'Content-Type': 'application/json'
        };
        if (this.token) {
            headers['Authorization'] = `Bearer ${this.token}`;
        }

        // Optional mobile trust headers injected by Flutter WebView
        const buildToken = localStorage.getItem('sxb_build_token');
        if (buildToken) {
            headers['X-Build-Token'] = buildToken;
        }

        const appSignatureRaw = localStorage.getItem('sxb_app_signature');
        if (this.isValidAppSignature(appSignatureRaw)) {
            const normalized = appSignatureRaw.replace(/:/g, '').toLowerCase();
            headers['X-App-Signature'] = normalized;
            headers['X-App-Timestamp'] = Math.floor(Date.now() / 1000).toString();
        } else if (appSignatureRaw) {
            // Drop broken cache value to prevent repeated 403 signature mismatch.
            localStorage.removeItem('sxb_app_signature');
        }
        return headers;
    }

    /**
     * Process failed request queue after token refresh
     */
    processQueue(error = null, token = null) {
        this.failedQueue.forEach(promise => {
            if (error) {
                promise.reject(error);
            } else {
                promise.resolve(token);
            }
        });
        this.failedQueue = [];
    }

    /**
     * Refresh access token silently
     */
    async refreshAccessToken() {
        if (!this.token) {
            throw new Error('No token to refresh');
        }

        try {
            const response = await fetch(`${API_BASE_URL}/auth/refresh`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.token}`
                }
            });

            if (!response.ok) {
                throw new Error('Token refresh failed');
            }

            const result = await response.json();
            this.setToken(result.access_token);

            // Update user in localStorage if present
            if (result.user) {
                localStorage.setItem('user', JSON.stringify(result.user));
            }

            apiDebug('🔄 Token refreshed silently');
            return result.access_token;
        } catch (error) {
            console.error('Token refresh error:', error);
            throw error;
        }
    }

    /**
     * XMLHttpRequest fallback (bypasses fetch port-stripping bug)
     * Use this for endpoints that have issues with fetch()
     */
    requestXHR(method, endpoint, data = null) {
        return new Promise((resolve, reject) => {
            const xhr = new XMLHttpRequest();
            const fullUrl = `${API_BASE_URL}${endpoint}`;

            apiDebug('🔧 XHR REQUEST (Fallback):');
            apiDebug('   Method:', method);
            apiDebug('   Full URL:', fullUrl);

            xhr.open(method, fullUrl, true);

            // Set headers
            xhr.setRequestHeader('Content-Type', 'application/json');
            if (this.token) {
                xhr.setRequestHeader('Authorization', `Bearer ${this.token}`);
            }

            xhr.onload = () => {
                apiDebug('✅ XHR Response:', xhr.status);
                if (xhr.status >= 200 && xhr.status < 300) {
                    try {
                        const response = xhr.status === 204
                            ? { success: true }
                            : JSON.parse(xhr.responseText);
                        resolve(response);
                    } catch (e) {
                        console.error('❌ XHR JSON parse error:', e);
                        reject(new Error('Invalid JSON response'));
                    }
                } else {
                    reject(new Error(`HTTP ${xhr.status}: ${xhr.statusText}`));
                }
            };

            xhr.onerror = () => {
                console.error('❌ XHR Network Error for:', fullUrl);
                reject(new Error(`Network request failed for ${fullUrl}`));
            };

            xhr.send(data ? JSON.stringify(data) : null);
        });
    }

    /**
     * MAIN REQUEST METHOD WITH TOKEN REFRESH INTERCEPTOR
     */
    async request(method, endpoint, data = null) {
        const config = {
            method,
            headers: this.getHeaders()
        };

        if (data && method !== 'GET') {
            config.body = JSON.stringify(data);
        }

        // Debug logging for URL construction
        const fullUrl = `${API_BASE_URL}${endpoint}`;
        apiDebug('🌐 REQUEST DEBUG:');
        apiDebug('   Method:', method);
        apiDebug('   Endpoint:', endpoint);
        apiDebug('   API_BASE_URL:', API_BASE_URL);
        apiDebug('   Full URL:', fullUrl);
        apiDebug('   Config:', config);

        // ===== RETRY CONFIGURATION (using class constants) =====
        const maxRetries = ApiClient.MAX_RETRIES;
        const baseDelay = ApiClient.BASE_DELAY_MS;
        const timeout = ApiClient.getTimeoutForEndpoint(endpoint);

        let lastError = null;

        for (let attempt = 1; attempt <= maxRetries; attempt++) {
            try {
                // Create abort controller for timeout
                const controller = new AbortController();
                const timeoutId = setTimeout(() => controller.abort(), timeout);

                const response = await fetch(fullUrl, {
                    ...config,
                    signal: controller.signal
                });

                clearTimeout(timeoutId);

                // ===== SILENT TOKEN REFRESH INTERCEPTOR =====
                if (response.status === 401) {
                    // If already refreshing, wait for it
                    if (this.isRefreshing) {
                        return new Promise((resolve, reject) => {
                            this.failedQueue.push({ resolve, reject });
                        }).then(token => {
                            // Retry original request with new token
                            config.headers['Authorization'] = `Bearer ${token}`;
                            return fetch(`${API_BASE_URL}${endpoint}`, config)
                                .then(res => res.status === 204 ? { success: true } : res.json());
                        });
                    }

                    // Start token refresh
                    this.isRefreshing = true;

                    try {
                        const newToken = await this.refreshAccessToken();
                        this.isRefreshing = false;
                        this.processQueue(null, newToken);

                        // Retry original request with new token
                        config.headers['Authorization'] = `Bearer ${newToken}`;
                        const retryResponse = await fetch(`${API_BASE_URL}${endpoint}`, config);

                        if (retryResponse.status === 204) {
                            return { success: true };
                        }

                        const retryResult = await retryResponse.json();

                        if (!retryResponse.ok) {
                            throw new Error(retryResult.detail || 'Request failed');
                        }

                        return retryResult;
                    } catch (refreshError) {
                        this.isRefreshing = false;
                        this.processQueue(refreshError, null);

                        // If refresh failed, logout
                        console.error('Refresh failed, logging out:', refreshError);
                        this.clearToken();

                        const currentPath = window.location.pathname;
                        if (currentPath.startsWith('/student')) {
                            window.location.href = '/student/';
                        } else {
                            window.location.href = '/admin/';
                        }

                        throw new Error('Sesi Anda telah berakhir. Silakan login kembali.');
                    }
                }
                // ===== END TOKEN REFRESH INTERCEPTOR =====

                // Handle 204 No Content (DELETE requests)
                if (response.status === 204) {
                    return { success: true };
                }

                const result = await response.json();

                if (!response.ok) {
                    // Enhanced error logging for debugging
                    console.error('API Error Response:', {
                        status: response.status,
                        endpoint,
                        method,
                        payload: data,
                        error: result
                    });
                    // Extract error message - handle various formats
                    let errorMessage = 'Request failed';
                    if (typeof result.detail === 'string') {
                        errorMessage = result.detail;
                    } else if (Array.isArray(result.detail)) {
                        // FastAPI validation error format
                        errorMessage = result.detail.map(e => e.msg || e.message || JSON.stringify(e)).join(', ');
                    } else if (result.detail && typeof result.detail === 'object') {
                        errorMessage = result.detail.message || result.detail.msg || JSON.stringify(result.detail);
                    } else if (result.message) {
                        errorMessage = result.message;
                    }
                    throw new Error(errorMessage);
                }

                return result;

            } catch (error) {
                lastError = error;

                // Check if it's a network error or timeout (retry-able)
                const isNetworkError = error.name === 'TypeError' ||
                    error.name === 'AbortError' ||
                    error.message.includes('network') ||
                    error.message.includes('Failed to fetch');

                if (isNetworkError && attempt < maxRetries) {
                    // Exponential backoff: 1s, 2s, 4s
                    const delay = baseDelay * Math.pow(2, attempt - 1);
                    apiDebug(`🔄 Network error, retrying in ${delay}ms (attempt ${attempt}/${maxRetries})...`);
                    await new Promise(resolve => setTimeout(resolve, delay));
                    continue;
                }

                // Non-retryable error or max retries reached
                break;
            }
        }

        console.error('API Error after retries:', lastError);
        throw lastError;
    }

    async requestRaw(method, endpoint, options = {}) {
        const headers = { ...this.getHeaders(), ...(options.headers || {}) };
        const config = { method, headers };

        if (options.data !== undefined && method !== 'GET') {
            config.body = JSON.stringify(options.data);
        } else if (options.body !== undefined && method !== 'GET') {
            config.body = options.body;
            if (typeof FormData !== 'undefined' && options.body instanceof FormData) {
                delete config.headers['Content-Type'];
            }
        }

        const fullUrl = `${API_BASE_URL}${endpoint}`;
        const timeout = Number(options.timeoutMs || ApiClient.getTimeoutForEndpoint(endpoint) || 15000);

        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), timeout);
            const response = await fetch(fullUrl, { ...config, signal: controller.signal });
            clearTimeout(timeoutId);

            if (response.status === 401) {
                if (this.isRefreshing) {
                    return new Promise((resolve, reject) => {
                        this.failedQueue.push({ resolve, reject });
                    }).then(async (token) => {
                        const retryHeaders = { ...config.headers, Authorization: `Bearer ${token}` };
                        return fetch(fullUrl, { ...config, headers: retryHeaders });
                    });
                }

                this.isRefreshing = true;
                try {
                    const newToken = await this.refreshAccessToken();
                    this.isRefreshing = false;
                    this.processQueue(null, newToken);
                    const retryHeaders = { ...config.headers, Authorization: `Bearer ${newToken}` };
                    return fetch(fullUrl, { ...config, headers: retryHeaders });
                } catch (refreshError) {
                    this.isRefreshing = false;
                    this.processQueue(refreshError, null);
                    this.clearToken();
                    throw refreshError;
                }
            }

            return response;
        } catch (error) {
            if (error && error.name === 'AbortError') {
                throw new Error(`Request timeout after ${timeout}ms`);
            }
            throw error;
        }
    }

/* ===== Module: 10-endpoints-auth-users-exams.js ===== */

    // Auth endpoints
    async login(username, password) {
        const result = await this.request('POST', '/auth/signin', { username, password });
        this.setToken(result.access_token);
        localStorage.setItem('user', JSON.stringify(result.user));
        return result;
    }

    async getMe() {
        return this.request('GET', '/auth/me');
    }

    async register(userData) {
        return this.request('POST', '/auth/register', userData);
    }

    // Users endpoints
    async getUsers(params = null) {
        return this.get('/users', params);
    }

    async getUser(id) {
        return this.request('GET', `/users/${id}`);
    }

    async createUser(userData) {
        // Use standard POST /users endpoint for single user creation
        // This supports full validation and returns the complete user object
        return this.request('POST', '/users', userData);
    }

    async updateUser(id, userData) {
        return this.request('PUT', `/users/${id}`, userData);
    }

    async deleteUser(id) {
        return this.request('DELETE', `/users/${id}`);
    }

    // === USER MANAGEMENT ===

    async advancedSearchUsers(filters = {}, page = 1, perPage = 20) {
        const cleanFilters = {};
        Object.keys(filters).forEach(key => {
            if (filters[key] !== '' && filters[key] !== null && filters[key] !== undefined) {
                cleanFilters[key] = filters[key];
            }
        });

        const queryParams = new URLSearchParams({
            page: page,
            per_page: perPage,
            ...cleanFilters
        });
        return this.request('GET', `/users/advanced-search?${queryParams.toString()}`);
    }

    async batchCreateUsers(users) {
        return this.request('POST', '/users/batch-create', users);
    }

    async batchUpdateUsers(userIds, updateData) {
        return this.request('PATCH', '/users/batch-update', {
            user_ids: userIds,
            update_data: updateData
        });
    }

    async batchDeleteUsers(userIds, permanent = false) {
        const queryParams = new URLSearchParams();
        userIds.forEach(id => queryParams.append('user_ids', id));
        queryParams.append('permanent', permanent);
        return this.request('DELETE', `/users/batch-delete?${queryParams.toString()}`);
    }

    async exportUsers(filters = {}, format = 'csv') {
        const endpoint = `/users/export?format=${encodeURIComponent(format)}`;
        const config = {
            method: 'POST',
            headers: this.getHeaders(),
            body: JSON.stringify(filters || {})
        };

        try {
            const response = await fetch(`${API_BASE_URL}${endpoint}`, config);
            if (!response.ok) {
                let detail = 'Export failed';
                try {
                    const errorBody = await response.json();
                    detail = errorBody.detail || errorBody.message || detail;
                } catch (_) {}
                throw new Error(detail);
            }

            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `users_export_${new Date().toISOString().slice(0, 10)}.${format}`;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);
            return { success: true };
        } catch (error) {
            console.error('Export error:', error);
            throw error;
        }
    }

    async getStudentClasses() {
        const result = await this.request('GET', '/users/student-classes');
        return result.classes || [];
    }

    async getStudentsByClass(studentClass = null) {
        const url = studentClass ? `/users/students-by-class?student_class=${encodeURIComponent(studentClass)}` : '/users/students-by-class';
        return this.request('GET', url);
    }

    // Exams endpoints
    async getExams(publishedOnly = false) {
        const response = await this.request('GET', `/exams?published_only=${publishedOnly}&limit=10000`);
        return response.exams || response;
    }

    async getExam(id) {
        return this.request('GET', `/exams/${id}`);
    }

    async createExam(examData) {
        return this.request('POST', '/exams', examData);
    }

    async updateExam(id, examData) {
        return this.request('PUT', `/exams/${id}`, examData);
    }

    async deleteExam(id) {
        return this.request('DELETE', `/exams/${id}`);
    }

    async publishExam(id, data = null) {
        return this.request('PATCH', `/exams/${id}/publish`, data);
    }

    async unpublishExam(id) {
        return this.request('PATCH', `/exams/${id}/publish`);
    }

    async createExamFromTemplate(templateId, startTime, endTime) {
        return this.request('POST', '/exams/from-template', {
            template_id: templateId,
            start_time: startTime,
            end_time: endTime
        });
    }

    async duplicateExam(examId, includeQuestions = true) {
        return this.request('POST', `/exams/${examId}/duplicate?include_questions=${includeQuestions}`);
    }

    async getExamAnalytics(examId) {
        return this.request('GET', `/exams/${examId}/analytics`);
    }

    async previewExam(examId, simulateStudentShuffle = false) {
        const query = simulateStudentShuffle ? '?simulate_student_shuffle=true' : '';
        return this.request('GET', `/exams/${examId}/preview${query}`);
    }


    // Questions endpoints
    async getQuestions(examId) {
        return this.request('GET', `/questions/${examId}/all`);
    }

    async createQuestion(questionData) {
        return this.request('POST', `/questions/${questionData.exam_id}`, questionData);
    }

    async updateQuestion(id, questionData) {
        return this.request('PUT', `/questions/${id}`, questionData);
    }

    async deleteQuestion(id) {
        return this.request('DELETE', `/questions/${id}`);
    }

    async uploadImage(file) {
        const formData = new FormData();
        formData.append('file', file);

        const response = await fetch(`${API_BASE_URL}/upload/image`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${this.token}` },
            body: formData
        });

        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || 'Upload failed');
        }
        return response.json();
    }

    // === SUBJECTS ===
    async getSubjects() {
        return this.request('GET', '/subjects');
    }

    async createSubject(data) {
        return this.request('POST', '/subjects', data);
    }

    // === QUESTION BANK ===
    async getCategories() {
        return this.request('GET', '/questions/categories');
    }

    async createCategory(data) {
        return this.request('POST', '/questions/categories', data);
    }

    async getTags() {
        return this.request('GET', '/questions/tags');
    }

    async createTag(data) {
        return this.request('POST', '/questions/tags', data);
    }

    async searchQuestions(filters) {
        return this.request('POST', '/questions/search', filters);
    }

    async bulkUploadQuestions(examId, formData) {
        return fetch(`${API_BASE_URL}/questions/${examId}/bulk-upload`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${this.token}` },
            body: formData
        }).then(res => res.json());
    }

    async exportQuestions(examId, format = 'csv') {
        const response = await fetch(`${API_BASE_URL}/questions/${examId}/export?format=${format}`, {
            method: 'GET',
            headers: { 'Authorization': `Bearer ${this.token}` }
        });

        if (!response.ok) throw new Error('Export failed');
        return response.blob();
    }

    // Exam session endpoints
    async startExam(examId) {
        return this.request('POST', `/exams/${examId}/start`);
    }

    /**
     * Submit answer with strict type casting
     * IMPORTANT: This method auto-casts types to match backend Pydantic schema
     */
    async submitAnswer(sessionId, questionId, answerData) {
        // Normalize payload to match Pydantic AnswerSubmit schema
        const payload = {
            session_id: parseInt(sessionId) || 0,
            question_id: parseInt(questionId) || 0,
            ...this.normalizeAnswerPayload(answerData)
        };

        apiDebug('📤 Submitting answer:', payload);
        return this.request('POST', '/exams/submit-answer', payload);
    }

    /**
     * Normalize answer payload for Pydantic validation
     * Converts loose JS types to strict Python types
     */
    normalizeAnswerPayload(answerData) {
        const normalized = {};

        // Single selection (selected_option_id)
        if (answerData.selected_option_id !== undefined && answerData.selected_option_id !== null) {
            normalized.selected_option_id = parseInt(answerData.selected_option_id) || null;
        }

        // Multiple selections (selected_option_ids)
        if (answerData.selected_option_ids !== undefined && answerData.selected_option_ids !== null) {
            if (Array.isArray(answerData.selected_option_ids)) {
                normalized.selected_option_ids = answerData.selected_option_ids.map(id => parseInt(id)).filter(id => !isNaN(id));
            } else {
                normalized.selected_option_ids = [];
            }
        }

        // Matching pairs (matching_pairs)
        if (answerData.matching_pairs !== undefined && answerData.matching_pairs !== null) {
            if (typeof answerData.matching_pairs === 'object' && !Array.isArray(answerData.matching_pairs)) {
                // Convert all values to integers
                normalized.matching_pairs = {};
                Object.keys(answerData.matching_pairs).forEach(key => {
                    normalized.matching_pairs[key] = parseInt(answerData.matching_pairs[key]) || 0;
                });
            } else {
                normalized.matching_pairs = {};
            }
        }

        // Statement answers for PGK Table Validation (statement_answers)
        if (answerData.statement_answers !== undefined && answerData.statement_answers !== null) {
            if (typeof answerData.statement_answers === 'object' && !Array.isArray(answerData.statement_answers)) {
                // Keep boolean values as-is, convert keys to strings
                normalized.statement_answers = {};
                const parseBool = (v) => {
                    if (typeof v === 'boolean') return v;
                    if (typeof v === 'number') return v !== 0;
                    if (typeof v === 'string') {
                        const s = v.trim().toLowerCase();
                        if (['true', '1', 'yes', 'y', 'benar'].includes(s)) return true;
                        if (['false', '0', 'no', 'n', 'salah'].includes(s)) return false;
                    }
                    return false;
                };
                Object.keys(answerData.statement_answers).forEach(key => {
                    const value = answerData.statement_answers[key];
                    // Ensure boolean value (true/false) without Boolean("false") pitfall
                    normalized.statement_answers[String(key)] = parseBool(value);
                });
            } else {
                normalized.statement_answers = {};
            }
        }

        // Text answer (answer_text)
        if (answerData.answer_text !== undefined && answerData.answer_text !== null) {
            normalized.answer_text = String(answerData.answer_text);
        }

        // Metadata
        if (answerData.answer_metadata) {
            normalized.answer_metadata = answerData.answer_metadata;
        }

        return normalized;
    }

    async autoSave(sessionId, answers) {
        return this.request('POST', '/exams/auto-save', {
            session_id: parseInt(sessionId) || 0,
            answers: answers,
            timestamp: new Date().toISOString()  // Required by AutoSaveRequest schema
        });
    }

    async submitExam(sessionId) {
        return this.request('POST', '/exams/submit', { session_id: sessionId });
    }

    async joinExam(token) {
        return this.request('POST', '/exams/join', { token });
    }

    async regenerateToken(examId) {
        return this.request('POST', `/exams/${examId}/regenerate-token`);
    }

    // Results
    async getExamResults(examId, includeBreakdown = false) {
        const query = new URLSearchParams({
            include_breakdown: includeBreakdown ? 'true' : 'false'
        });
        return this.request('GET', `/exams/${examId}/results?${query.toString()}`);
    }

    async getExamParticipationSummary(examId) {
        return this.request('GET', `/exams/${examId}/participation-summary`);
    }

    async getSessionAnswerReview(examId, sessionId) {
        return this.request('GET', `/exams/${examId}/sessions/${sessionId}/review`);
    }

    async getExamsWithResults() {
        return this.request('GET', '/exams/results/all');
    }

    async getMyResults() {
        return this.request('GET', '/exams/my-results');
    }

    async getDashboardStats() {
        return this.request('GET', '/stats/dashboard');
    }

    // === GRADING ===

/* ===== Module: 20-endpoints-grading-monitoring-templates.js ===== */


    async getPendingEssays(examId = null, page = 1, perPage = 20) {
        const params = new URLSearchParams({ page, per_page: perPage });
        if (examId) params.append('exam_id', examId);
        return this.request('GET', `/grading/pending-essays?${params}`);
    }

    async getGradingStats() {
        return this.request('GET', '/grading/stats');
    }

    async gradeEssay(answerId, pointsEarned, feedback = null) {
        return this.request('POST', '/grading/grade-essay', {
            answer_id: answerId,
            points_earned: pointsEarned,
            feedback
        });
    }

    async batchGradeEssays(grades) {
        return this.request('POST', '/grading/batch-grade', { grades });
    }

    async getAnswerDetail(answerId) {
        return this.request('GET', `/grading/answer/${answerId}`);
    }

    // === ANALYTICS ===

    async getStudentPerformance(studentId) {
        return this.request('GET', `/analytics/student/${studentId}`);
    }

    async getClassPerformance(className, examId = null) {
        const params = new URLSearchParams({ class_name: className });
        if (examId !== null && examId !== undefined && examId !== '') {
            params.append('exam_id', String(examId));
        }
        return this.request('GET', `/analytics/class?${params.toString()}`);
    }

    async getExamClasses(examId) {
        return this.request('GET', `/analytics/exam/${examId}/classes`);
    }

    async getQuestionDifficultyAnalysis(examId) {
        return this.request('GET', `/analytics/exam/${examId}/question-difficulty`);
    }

    async getAssessmentAnalysis(examId, className) {
        const params = new URLSearchParams();
        if (className && typeof className === 'object' && Array.isArray(className.classNames)) {
            params.set('class_names', className.classNames.join(','));
        } else {
            params.set('class_name', className);
        }
        return this.request('GET', `/analytics/exam/${examId}/assessment?${params.toString()}`);
    }

    async getAnalyticsDashboard(days = 7) {
        return this.request('GET', `/analytics/dashboard?days=${days}`);
    }

    // === MONITORING ===

    async getViolationsDashboard(examId = null, dateFrom = null, dateTo = null, options = {}) {
        const params = new URLSearchParams();
        if (examId) params.append('exam_id', examId);
        if (dateFrom) params.append('date_from', dateFrom);
        if (dateTo) params.append('date_to', dateTo);
        if (options && options.summaryOnly) params.append('summary_only', 'true');
        if (options && options.countedOnly) params.append('counted_only', 'true');
        if (options && options.detailLevel) params.append('detail_level', options.detailLevel);
        const query = params.toString();
        return this.request('GET', `/monitoring/violations${query ? `?${query}` : ''}`);
    }

    async getLiveExamStats(examId) {
        return this.request('GET', `/monitoring/exam/${examId}/live-stats`);
    }

    async getExamSessions(examId, status = null, includeRecovery = false) {
        const params = new URLSearchParams();
        if (status) params.append('status', status);
        if (includeRecovery) params.append('include_recovery', 'true');
        const query = params.toString();
        return this.request('GET', `/monitoring/exam/${examId}/sessions${query ? `?${query}` : ''}`);
    }

    async getActiveExams() {
        return this.request('GET', '/monitoring/active-exams');
    }

    async getViolationTypes() {
        return this.request('GET', '/monitoring/violation-types');
    }

    async getRuntimePolicy() {
        return this.request('GET', '/runtime/policy');
    }

    async getOpsSummary() {
        return this.request('GET', '/monitoring/system/ops-summary');
    }

    async setDegradeMode(enabled, reason = 'Manual toggle from monitoring', ttlMinutes = 120) {
        return this.request('POST', '/monitoring/system/degrade-mode', {
            enabled: !!enabled,
            reason,
            ttl_minutes: ttlMinutes
        });
    }

    async getAutoRestartSchedule() {
        return this.request('GET', '/monitoring/system/auto-restart-schedule');
    }

    async setAutoRestartSchedule(payload) {
        return this.request('POST', '/monitoring/system/auto-restart-schedule', payload);
    }

    async runAutoRestartCheck(reason = 'Manual scheduler check', force = true, dryRun = true) {
        return this.request('POST', '/monitoring/system/auto-restart-schedule/check', {
            reason,
            force: !!force,
            dry_run: !!dryRun
        });
    }

    async getResourceMode() {
        return this.request('GET', '/monitoring/system/resource-mode');
    }

    async setResourceMode(mode, reason = 'Manual resource mode update', ttlMinutes = 120) {
        return this.request('POST', '/monitoring/system/resource-mode', {
            mode,
            reason,
            ttl_minutes: ttlMinutes
        });
    }

    async getAutoIntelligenceStatus() {
        return this.request('GET', '/monitoring/system/auto-intelligence');
    }

    async updateAutoIntelligenceControl(payload) {
        return this.request('POST', '/monitoring/system/auto-intelligence', payload);
    }

    async runAutoIntelligence(reason = 'Manual run auto intelligence', force = true, forceHeal = false) {
        return this.request('POST', '/monitoring/system/auto-intelligence/run', {
            reason,
            force: !!force,
            force_heal: !!forceHeal
        });
    }

    async restartSystemSafely(
        reason = 'Restart FULL antar sesi ujian',
        restartBufferMinutes = 30,
        dryRun = false,
        fullRestart = true,
        includeDataServices = true,
        restartTimeoutSeconds = 300
    ) {
        return this.request('POST', '/monitoring/system/restart-safe', {
            reason,
            restart_buffer_minutes: restartBufferMinutes,
            dry_run: !!dryRun,
            full_restart: !!fullRestart,
            include_data_services: !!includeDataServices,
            restart_timeout_seconds: restartTimeoutSeconds
        });
    }

    async getSessionRecoveryStatus(sessionId) {
        return this.request('GET', `/monitoring/sessions/${sessionId}/recovery-status`);
    }

    async resetSessionAfterDisconnect(sessionId, reason = 'Reset sesi karena gangguan koneksi') {
        return this.request('POST', `/monitoring/sessions/${sessionId}/reset`, {
            reason
        });
    }

    async getRecoveryCandidates(examId, limit = 400) {
        const safeLimit = Math.max(50, Math.min(Number(limit || 400), 1000));
        return this.request('GET', `/monitoring/exam/${examId}/recovery-candidates?limit=${safeLimit}`);
    }

    async reopenSessionOverride(sessionId, reason = 'Override pengawas dari Recovery Center', resetViolationCount = true) {
        return this.request('POST', `/monitoring/sessions/${sessionId}/reopen-override`, {
            reason,
            reset_violation_count: !!resetViolationCount
        });
    }

    /**
     * Get session status (for server time sync)
     */
    async getSessionStatus(sessionId) {
        return this.request('GET', `/exams/session/${sessionId}/status`);
    }

    // Generic HTTP helper methods
    async get(endpoint, params = null) {
        let url = endpoint;
        if (params) {
            const queryParams = new URLSearchParams();
            Object.entries(params).forEach(([key, value]) => {
                if (value !== null && value !== undefined && value !== '') {
                    queryParams.append(key, value);
                }
            });
            if (queryParams.toString()) {
                url += (url.includes('?') ? '&' : '?') + queryParams.toString();
            }
        }
        return this.request('GET', url);
    }

    async post(endpoint, data = null) {
        return this.request('POST', endpoint, data);
    }

    async put(endpoint, data = null) {
        return this.request('PUT', endpoint, data);
    }

    async delete(endpoint) {
        return this.request('DELETE', endpoint);
    }

    // === SUBJECTS (BIDANG STUDI) ===

    async getSubjects() {
        return this.request('GET', '/subjects');
    }

    async createSubject(name, description = null) {
        return this.request('POST', '/subjects', { name, description });
    }

    async deleteSubject(id) {
        return this.request('DELETE', `/subjects/${id}`);
    }

    // === EXAM TEMPLATES ===

    async getTemplates(publicOnly = false, page = 1, perPage = 20) {
        const params = new URLSearchParams({
            public_only: publicOnly,
            page,
            per_page: perPage
        });
        return this.request('GET', `/templates/?${params}`);
    }

    async getTemplate(id) {
        return this.request('GET', `/templates/${id}`);
    }

    async createTemplate(templateData) {
        return this.request('POST', '/templates/', templateData);
    }

    async createExamFromTemplate(templateId, examData) {
        return this.request('POST', `/templates/${templateId}/create-exam`, examData);
    }

    async updateTemplate(id, data) {
        return this.request('PUT', `/templates/${id}`, data);
    }

    async deleteTemplate(id) {
        return this.request('DELETE', `/templates/${id}`);
    }

    async saveExamAsTemplate(examId, name, description = null, isPublic = false) {
        // First get the exam with questions
        const exam = await this.request('GET', `/exams/${examId}`);
        const questions = await this.request('GET', `/questions/${examId}/all`);

        // Create template data
        const templateData = {
            name,
            description,
            is_public: isPublic,
            template_data: {
                duration_minutes: exam.duration_minutes,
                passing_score: exam.passing_score,
                max_attempts: exam.max_attempts,
                shuffle_questions: exam.shuffle_questions,
                shuffle_options: exam.shuffle_options,
                show_results: exam.show_results,
                allow_review: exam.allow_review,
                questions: questions
            }
        };

        return this.request('POST', '/templates/', templateData);
    }
}

// Global API instance
// Global API instance
window.api = new ApiClient();
const api = window.api; // Maintain local reference for file internal usage if any

/* ===== Module: 30-ui-shortcuts.js ===== */

/**
 * UI Components - Common UI utilities
 */
const UIComponents = {
    showToast(message, type = 'info', duration = 4000) {
        const existingToast = document.querySelector('.ui-toast');
        if (existingToast) existingToast.remove();

        const iconMap = {
            success: 'fa-check-circle',
            error: 'fa-times-circle',
            warning: 'fa-exclamation-triangle',
            info: 'fa-info-circle'
        };

        const toast = document.createElement('div');
        toast.className = `ui-toast ui-toast-${type}`;
        toast.innerHTML = `
            <div class="toast-icon">
                <i class="fas ${iconMap[type] || iconMap.info}"></i>
            </div>
            <div class="toast-body">
                <span class="toast-message">${message}</span>
            </div>
            <button class="toast-close" onclick="this.parentElement.remove()">
                <i class="fas fa-times"></i>
            </button>
            <div class="toast-progress"></div>
        `;

        if (!document.getElementById('ui-toast-styles')) {
            const style = document.createElement('style');
            style.id = 'ui-toast-styles';
            style.textContent = `
                .ui-toast {
                    position: fixed;
                    top: 24px;
                    right: 24px;
                    min-width: 320px;
                    max-width: 420px;
                    padding: 0;
                    border-radius: 12px;
                    color: white;
                    z-index: 10000;
                    animation: toastSlideIn 0.4s cubic-bezier(0.16, 1, 0.3, 1);
                    box-shadow: 0 8px 32px rgba(0,0,0,0.3), 0 2px 8px rgba(0,0,0,0.2);
                    display: flex;
                    align-items: stretch;
                    overflow: hidden;
                    backdrop-filter: blur(10px);
                    border: 1px solid rgba(255,255,255,0.1);
                }
                .toast-icon {
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    padding: 1rem;
                    font-size: 1.25rem;
                }
                .toast-body {
                    flex: 1;
                    display: flex;
                    align-items: center;
                    padding: 1rem 0.5rem;
                }
                .toast-message {
                    font-size: 0.95rem;
                    font-weight: 500;
                    line-height: 1.4;
                }
                .toast-close {
                    background: transparent;
                    border: none;
                    color: rgba(255,255,255,0.7);
                    padding: 1rem;
                    cursor: pointer;
                    transition: all 0.2s ease;
                    display: flex;
                    align-items: center;
                }
                .toast-close:hover {
                    color: white;
                    background: rgba(255,255,255,0.1);
                }
                .toast-progress {
                    position: absolute;
                    bottom: 0;
                    left: 0;
                    height: 3px;
                    background: rgba(255,255,255,0.4);
                    animation: toastProgress ${duration}ms linear forwards;
                }
                .ui-toast-success {
                    background: linear-gradient(135deg, rgba(16, 185, 129, 0.95), rgba(5, 150, 105, 0.95));
                }
                .ui-toast-error {
                    background: linear-gradient(135deg, rgba(239, 68, 68, 0.95), rgba(220, 38, 38, 0.95));
                }
                .ui-toast-warning {
                    background: linear-gradient(135deg, rgba(245, 158, 11, 0.95), rgba(217, 119, 6, 0.95));
                }
                .ui-toast-info {
                    background: linear-gradient(135deg, rgba(59, 130, 246, 0.95), rgba(37, 99, 235, 0.95));
                }
                @keyframes toastSlideIn {
                    from { transform: translateX(100%) scale(0.9); opacity: 0; }
                    to { transform: translateX(0) scale(1); opacity: 1; }
                }
                @keyframes toastSlideOut {
                    from { transform: translateX(0) scale(1); opacity: 1; }
                    to { transform: translateX(100%) scale(0.9); opacity: 0; }
                }
                @keyframes toastProgress {
                    from { width: 100%; }
                    to { width: 0%; }
                }
            `;
            document.head.appendChild(style);
        }

        document.body.appendChild(toast);

        setTimeout(() => {
            toast.style.animation = 'toastSlideOut 0.3s ease forwards';
            setTimeout(() => toast.remove(), 300);
        }, duration);
    },

    // ============== SUBJECTS (BIDANG STUDI) ==============
    // NOTE: Subjects methods moved to ApiClient class

    async confirmDialog(message, title = 'Konfirmasi') {
        return showConfirm(message);
    }
};

/**
 * Auth helpers
 */
async function checkAuthAndRedirect(allowedRoles = ['developer', 'admin', 'teacher', 'student', 'guruplus']) {
    try {
        const user = await api.getMe();
        const normalizedAllowedRoles = new Set(allowedRoles);
        if (normalizedAllowedRoles.has('student')) {
            normalizedAllowedRoles.add('guruplus');
        }
        if (normalizedAllowedRoles.has('admin')) {
            normalizedAllowedRoles.add('developer');
        }
        if (!user || !normalizedAllowedRoles.has(user.role)) {
            const currentPath = window.location.pathname;
            if (currentPath.startsWith('/student')) {
                window.location.href = '/student/';
            } else {
                window.location.href = '/admin/';
            }
            return null;
        }
        return user;
    } catch (error) {
        const currentPath = window.location.pathname;
        if (currentPath.startsWith('/student')) {
            window.location.href = '/student/';
        } else {
            window.location.href = '/admin/';
        }
        return null;
    }
}

/**
 * Initialize sidebar
 */
function initSidebar() {
    const sidebar = document.getElementById('sidebar');
    const sidebarToggle = document.getElementById('sidebar-toggle');

    if (sidebarToggle && sidebar) {
        sidebarToggle.addEventListener('click', () => {
            sidebar.classList.toggle('collapsed');
        });
    }
}

/**
 * Global apiRequest wrapper function
 * Provides a simple wrapper around api.request() for backward compatibility
 * Used by admin pages like system-monitor.html and security-dashboard.html
 *
 * @param {string} endpoint - API endpoint (e.g., '/api/monitoring/system/metrics')
 * @param {string} method - HTTP method (default: 'GET')
 * @param {object} data - Request payload (default: null)
 * @returns {Promise} API response
 */
function normalizeApiEndpoint(endpoint) {
    let cleanEndpoint = String(endpoint || '').trim();
    if (!cleanEndpoint) return '/';
    if (cleanEndpoint.startsWith(window.location.origin)) {
        cleanEndpoint = cleanEndpoint.slice(window.location.origin.length);
    }
    if (cleanEndpoint.startsWith('/api')) {
        cleanEndpoint = cleanEndpoint.substring(4);
    }
    if (!cleanEndpoint.startsWith('/')) {
        cleanEndpoint = `/${cleanEndpoint}`;
    }
    return cleanEndpoint;
}

async function apiRequest(endpoint, method = 'GET', data = null) {
    const cleanEndpoint = normalizeApiEndpoint(endpoint);
    return api.request(method, cleanEndpoint, data);
}

async function apiRequestRaw(endpoint, options = {}) {
    const cleanEndpoint = normalizeApiEndpoint(endpoint);
    const method = String(options.method || 'GET').toUpperCase();
    return api.requestRaw(method, cleanEndpoint, {
        data: options.data,
        body: options.body,
        headers: options.headers,
        timeoutMs: options.timeoutMs
    });
}

window.apiRequestRaw = apiRequestRaw;

/**
 * Global Keyboard Shortcuts
 * Available on all admin pages
 *
 * Ctrl+Shift+Alt+L = Navigate to Settings page
 * Ctrl+Shift+Alt+K = Toggle APK Token section (only on settings page)
 * Ctrl+Shift+Alt+F = Toggle Freeze section (only on settings page)
 */
/**
 * UNIFIED KEYBOARD SHORTCUTS HANDLER
 * Uses e.code for better hardware compatibility
 */
(function initUnifiedShortcuts() {
    apiDebug('%c[API.JS] Unified Shortcuts v3 (Physical Keys)', 'color: #ff9900; font-weight: bold');

    let apkTokenVisible = false;
    let freezeSectionVisible = false;

    // Helper function to check admin role
    function checkAdmin() {
        const user = JSON.parse(localStorage.getItem('user') || '{}');
        if (!user || !user.role) return false;
        const role = user.role.toLowerCase();
        return role === 'admin' || role === 'developer';
    }

    // ACTION: Toggle APK Token Section
    window.toggleApkSection = function () {
        apiDebug('[API.JS] toggleApkSection called');

        if (!checkAdmin()) {
            apiDebug('[API.JS] toggleApkSection: User is not admin');
            if (typeof showToast === 'function') showToast('Akses ditolak: Hanya admin', 'error');
            return;
        }

        const apkSection = document.getElementById('apk-token-section');
        apiDebug('[API.JS] APK Section element:', apkSection ? 'found' : 'not found');

        if (apkSection) {
            if (apkSection.style.display === 'none' || !apkTokenVisible) {
                apiDebug('[API.JS] Action: Show APK Token');
                apkSection.style.display = 'block';
                apkSection.style.animation = 'slideDown 0.3s ease-out';
                apkTokenVisible = true;
                apkSection.scrollIntoView({ behavior: 'smooth', block: 'center' });
                if (typeof showAlert === 'function') {
                    showAlert('Mode Keamanan APK Token diaktifkan!', 'warning');
                } else if (typeof showToast === 'function') {
                    showToast('APK Token Section ditampilkan!', 'warning');
                }
            } else {
                apiDebug('[API.JS] Action: Hide APK Token');
                apkSection.style.display = 'none';
                apkTokenVisible = false;
                if (typeof showToast === 'function') showToast('APK Token disembunyikan', 'info');
            }
        } else {
            apiDebug('[API.JS] APK Token section not found');
            if (window.location.pathname.includes('/admin/settings.html')) {
                if (typeof showToast === 'function') showToast('Element tidak ditemukan. Refresh halaman.', 'error');
            } else {
                if (typeof showToast === 'function') showToast('Fitur ini hanya ada di halaman Pengaturan', 'warning');
            }
        }
    };

    // ACTION: Toggle Freeze Section (hidden emergency panel)
    window.toggleFreezeSection = function () {
        apiDebug('[API.JS] toggleFreezeSection called');

        if (!checkAdmin()) {
            apiDebug('[API.JS] toggleFreezeSection: User is not admin');
            if (typeof showToast === 'function') showToast('Akses ditolak: Hanya admin', 'error');
            return;
        }

        const freezeSection = document.getElementById('freeze-mode-section');
        apiDebug('[API.JS] Freeze Section element:', freezeSection ? 'found' : 'not found');

        if (freezeSection) {
            if (freezeSection.style.display === 'none' || !freezeSectionVisible) {
                freezeSection.style.display = 'block';
                freezeSection.style.animation = 'slideDown 0.3s ease-out';
                freezeSectionVisible = true;
                freezeSection.scrollIntoView({ behavior: 'smooth', block: 'center' });
                if (typeof showAlert === 'function') {
                    showAlert('Panel Freeze Mode ditampilkan!', 'warning');
                } else if (typeof showToast === 'function') {
                    showToast('Panel Freeze ditampilkan', 'warning');
                }
            } else {
                freezeSection.style.display = 'none';
                freezeSectionVisible = false;
                if (typeof showToast === 'function') showToast('Panel Freeze disembunyikan', 'info');
            }
        } else if (typeof showToast === 'function') {
            showToast('Fitur Freeze hanya ada di halaman Pengaturan', 'warning');
        }
    };

    // ACTION: Show Settings / Navigate
    window.toggleSettingsNav = function () {
        apiDebug('%c[API.JS] toggleSettingsNav called', 'color: #ff9900; font-weight: bold');

        if (!checkAdmin()) {
            apiDebug('[API.JS] toggleSettingsNav: User is not admin');
            if (typeof showToast === 'function') showToast('Akses ditolak: Hanya admin', 'error');
            return;
        }

        // Target the hidden General Settings Item instead of the whole menu
        const generalItem = document.getElementById('settings-general-item');
        const settingsMenu = document.getElementById('settings-menu-container');

        // ENHANCED DEBUGGING
        apiDebug('[API.JS] Element Check:');
        apiDebug('  - generalItem:', generalItem);
        apiDebug('  - settingsMenu:', settingsMenu);

        if (generalItem) {
            // Check if hidden (using computed style for robustness)
            const style = window.getComputedStyle(generalItem);
            apiDebug('  - Current display:', style.display);
            apiDebug('  - Inline style display:', generalItem.style.display);

            if (style.display === 'none' || generalItem.style.display === 'none') {
                apiDebug('%c[API.JS] ✅ Action: SHOW General Settings Item', 'color: #00ff00; font-weight: bold');
                generalItem.style.display = 'list-item'; // Changed from 'block' to 'list-item' for proper <li> display
                generalItem.style.animation = 'fadeIn 0.3s ease-out';

                // Ensure parent menu is open so user sees it
                if (settingsMenu) {
                    settingsMenu.classList.add('open');
                    apiDebug('  - Parent menu opened');
                }

                if (typeof showToast === 'function') showToast('Menu Umum ditampilkan', 'success');
            } else {
                apiDebug('%c[API.JS] ⚠️ Action: HIDE General Settings Item', 'color: #ff9900; font-weight: bold');
                generalItem.style.display = 'none';
                if (typeof showToast === 'function') showToast('Menu Umum disembunyikan', 'info');
            }
        } else {
            console.error('%c[API.JS] ❌ General Settings Item NOT FOUND!', 'color: #ff0000; font-weight: bold');
            apiDebug('  - All elements with ID:', document.querySelectorAll('[id]'));
            apiDebug('  - Sidebar container:', document.getElementById('sidebar-container'));
            if (typeof showToast === 'function') showToast('Item menu tidak ditemukan (refresh halaman)', 'error');
        }
    };

    // KEYBOARD HANDLER - Using CAPTURE phase (true) to intercept before other handlers
    // IMPORTANT: Wait for DOM ready to ensure sidebar elements exist
    function initKeyboardShortcuts() {
        apiDebug('%c[API.JS] 🎹 Initializing keyboard shortcuts...', 'color: #00ffff; font-weight: bold');

        document.addEventListener('keydown', function (e) {
            // Filter for Admin Shortcuts: Ctrl + Shift + Alt + (Key)
            if (e.ctrlKey && e.shiftKey && e.altKey) {

                // Debug logging
                apiDebug('%c[API.JS] ⌨️ Ctrl+Shift+Alt combo detected, key:', e.code, 'color: #ffff00; font-weight: bold');

                // Check Admin - with feedback
                if (!checkAdmin()) {
                    apiDebug('[API.JS] User is not admin, shortcut ignored');
                    return;
                }

                // Handle K (Physical Key) - Toggle APK Token Section
                if (e.code === 'KeyK') {
                    e.preventDefault();
                    e.stopPropagation();
                    e.stopImmediatePropagation();
                    apiDebug('%c[API.JS] 🔑 Shortcut: Ctrl+Shift+Alt+K triggered', 'color: #ff00ff; font-weight: bold');
                    window.toggleApkSection();
                    return false;
                }

                // Handle F (Physical Key) - Toggle Freeze Section
                if (e.code === 'KeyF') {
                    e.preventDefault();
                    e.stopPropagation();
                    e.stopImmediatePropagation();
                    apiDebug('%c[API.JS] 🔑 Shortcut: Ctrl+Shift+Alt+F triggered', 'color: #ff4d6d; font-weight: bold');
                    window.toggleFreezeSection();
                    return false;
                }

                // Handle L (Physical Key) - Navigate to Settings
                if (e.code === 'KeyL') {
                    e.preventDefault();
                    e.stopPropagation();
                    e.stopImmediatePropagation();
                    apiDebug('%c[API.JS] 🔑 Shortcut: Ctrl+Shift+Alt+L triggered', 'color: #00ffff; font-weight: bold');
                    window.toggleSettingsNav();
                    return false;
                }
            }
        }, true); // CAPTURE PHASE - intercept events before they reach other handlers

        apiDebug('%c[API.JS] ✅ Keyboard shortcuts initialized', 'color: #00ff00; font-weight: bold');
    }

    // Wait for DOM ready before attaching keyboard listeners
    apiDebug('%c[API.JS] 📌 Document readyState:', document.readyState, 'color: #ff9900; font-weight: bold');
    if (document.readyState === 'loading') {
        apiDebug('%c[API.JS] ⏳ Waiting for DOMContentLoaded...', 'color: #ff9900; font-weight: bold');
        document.addEventListener('DOMContentLoaded', () => {
            apiDebug('%c[API.JS] ✅ DOMContentLoaded fired, initializing shortcuts', 'color: #00ff00; font-weight: bold');
            initKeyboardShortcuts();
        });
    } else {
        // DOM already loaded, init immediately
        apiDebug('%c[API.JS] ⚡ DOM already ready, initializing shortcuts immediately', 'color: #00ff00; font-weight: bold');
        initKeyboardShortcuts();
    }

    // SECRET MOUSE TRIGGER REMOVED - Restricted to Keyboard Shortcut (Ctrl+Shift+Alt+L)
    apiDebug('%c[API.JS] ✅ Shortcuts v3 initialization complete', 'color: #00ff00; font-weight: bold');
})();

// Add required animation styles
const globalStyleSheet = document.createElement('style');
globalStyleSheet.textContent = `
    @keyframes fadeIn {
        from { opacity: 0; transform: translateY(-10px); }
        to { opacity: 1; transform: translateY(0); }
    }
`;
document.head.appendChild(globalStyleSheet);
