/**
 * Frontend API client with comprehensive error handling.
 * Provides consistent error responses and retry logic.
 */

// ============== ERROR HANDLING WRAPPER ==============

class APIError extends Error {
    constructor(message, statusCode, response) {
        super(message);
        this.name = 'APIError';
        this.statusCode = statusCode;
        this.response = response;
    }
}

class NetworkError extends Error {
    constructor(message) {
        super(message);
        this.name = 'NetworkError';
    }
}

class TimeoutError extends Error {
    constructor(message) {
        super(message);
        this.name = 'TimeoutError';
    }
}

/**
 * Enhanced API wrapper with error handling and retry logic
 */
const apiClient = {
    /**
     * Make API request with automatic error handling
     * @param {string} url - API endpoint
     * @param {object} options - Fetch options
     * @param {object} config - Additional config {retries, timeout, showError}
     */
    async request(url, options = {}, config = {}) {
        const {
            retries = 0,
            timeout = 30000,
            showError = true
        } = config;

        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), timeout);

        try {
            const response = await fetch(url, {
                ...options,
                signal: controller.signal,
                headers: {
                    'Content-Type': 'application/json',
                    ...options.headers
                }
            });

            clearTimeout(timeoutId);

            // Handle non-OK responses
            if (!response.ok) {
                let errorMessage = 'Terjadi kesalahan pada server';

                try {
                    const errorData = await response.json();
                    errorMessage = errorData.detail || errorData.message || errorMessage;
                } catch (e) {
                    // Response not JSON, use status text
                    errorMessage = response.statusText || errorMessage;
                }

                if (showError) {
                    this.handleError(new APIError(errorMessage, response.status, response));
                }

                throw new APIError(errorMessage, response.status, response);
            }

            // Parse JSON response
            const data = await response.json();
            return data;

        } catch (error) {
            clearTimeout(timeoutId);

            // Handle abort/timeout
            if (error.name === 'AbortError') {
                const timeoutError = new TimeoutError('Request timeout - please check your connection');
                if (showError) this.handleError(timeoutError);
                throw timeoutError;
            }

            // Handle network errors
            if (error instanceof TypeError && error.message.includes('fetch')) {
                const networkError = new NetworkError('Network error - please check your connection');
                if (showError) this.handleError(networkError);
                throw networkError;
            }

            // Retry logic for network errors
            if (retries > 0 && (error instanceof NetworkError || error instanceof TimeoutError)) {
                console.log(`Retrying request... (${retries} attempts left)`);
                await new Promise(resolve => setTimeout(resolve, 1000)); // Wait 1s before retry
                return this.request(url, options, { ...config, retries: retries - 1 });
            }

            // Re-throw APIError
            if (error instanceof APIError) {
                throw error;
            }

            // Unknown error
            if (showError) this.handleError(error);
            throw error;
        }
    },

    /**
     * Display error to user
     */
    handleError(error) {
        let message = 'Terjadi kesalahan';
        let type = 'danger';

        if (error instanceof APIError) {
            message = error.message;
            if (error.statusCode === 401) {
                message = 'Sesi Anda telah berakhir. Silakan login kembali.';
                // Redirect to login after showing error
                setTimeout(() => {
                    window.location.href = '/admin/login.html';
                }, 2000);
            } else if (error.statusCode === 403) {
                type = 'warning';
            } else if (error.statusCode === 404) {
                type = 'warning';
            }
        } else if (error instanceof NetworkError || error instanceof TimeoutError) {
            message = error.message;
            type = 'warning';
        } else {
            message = error.message || 'Terjadi kesalahan tidak terduga';
        }

        // Use global showAlert if available
        if (typeof showAlert === 'function') {
            showAlert(message, type);
        } else {
            console.error('[API Error]', message, error);
            alert(message);
        }
    },

    /**
     * GET request
     */
    async get(url, config = {}) {
        return this.request(url, { method: 'GET' }, config);
    },

    /**
     * POST request
     */
    async post(url, data, config = {}) {
        return this.request(url, {
            method: 'POST',
            body: JSON.stringify(data)
        }, config);
    },

    /**
     * PUT request
     */
    async put(url, data, config = {}) {
        return this.request(url, {
            method: 'PUT',
            body: JSON.stringify(data)
        }, config);
    },

    /**
     * DELETE request
     */
    async delete(url, config = {}) {
        return this.request(url, { method: 'DELETE' }, config);
    }
};

