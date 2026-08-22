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
