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
