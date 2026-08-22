/**
 * Authentication Handler for Sistem Ujian Online
 */

class AuthManager {
    constructor() {
        this.checkAutoLogin(); // Check for URL tokens first
        this.user = this.getStoredUser();
    }

    checkAutoLogin() {
        try {
            // Prefer hash fragment to avoid leaking token via server logs.
            const hashRaw = (window.location.hash || '').replace(/^#/, '');
            const hashParams = new URLSearchParams(hashRaw);
            const queryParams = new URLSearchParams(window.location.search);

            const token = hashParams.get('autologin_token') || queryParams.get('autologin_token');
            const userB64 = hashParams.get('autologin_user') || queryParams.get('autologin_user');

            if (token && userB64) {
                console.log('SXB: Auto-login detected');
                localStorage.setItem('access_token', token);
                // Decode Base64 (handle utf8)
                const userJson = decodeURIComponent(escape(window.atob(userB64)));
                localStorage.setItem('user', userJson);

                // Clean URL to hide token
                const newUrl = window.location.pathname;
                window.history.replaceState({}, document.title, newUrl);
            }
        } catch (e) {
            console.error('Auto-login failed:', e);
        }
    }

    getStoredUser() {
        try {
            return JSON.parse(localStorage.getItem('user'));
        } catch {
            return null;
        }
    }

    isLoggedIn() {
        return !!localStorage.getItem('access_token') && !!this.user;
    }

    getUser() {
        return this.user;
    }

    isAdmin() {
        return this.user?.role === 'admin' || this.user?.role === 'developer';
    }

    isTeacher() {
        return this.user?.role === 'teacher' || this.user?.role === 'admin' || this.user?.role === 'developer';
    }

    getNormalizedJobTitle() {
        return String(this.user?.job_title || '').trim().toLowerCase();
    }

    isPengawas() {
        if (this.user?.role !== 'teacher') return false;
        const jobTitle = this.getNormalizedJobTitle();
        return jobTitle.includes('pengawas') || jobTitle === 'proktor' || jobTitle === 'invigilator';
    }

    isPengawasAllowedPath(pathname) {
        const normalized = String(pathname || '').toLowerCase();
        return normalized === '/admin/'
            || normalized === '/admin/index.html'
            || normalized === '/admin/exams.html'
            || normalized === '/admin/monitoring.html'
            || normalized === '/admin/violations.html'
            || normalized === '/admin/account-security.html';
    }

    isStudent() {
        return this.user?.role === 'student' || this.user?.role === 'guruplus';
    }

    logout() {
        // Determine redirect URL based on current user role before clearing
        const user = this.getUser();
        const isStudent = user?.role === 'student' || user?.role === 'guruplus';
        const redirectUrl = isStudent ? '/student/' : '/admin/';

        // Clear auth data
        localStorage.removeItem('access_token');
        localStorage.removeItem('user');

        // Check if running in Flutter InAppWebView
        const isFlutterApp = !!(window.flutter_inappwebview && window.flutter_inappwebview.callHandler);

        if (isFlutterApp) {
            // Notify Flutter app to exit - Flutter will handle closing
            // DON'T redirect - this causes the login page flash
            this.notifyFlutterLogout();
        } else {
            // Normal browser - redirect to login page
            window.location.href = redirectUrl;
        }
    }

    /**
     * Show confirmation dialog before logging out
     * Compatible with custom-confirm.js and modern-modals.js
     */
    async confirmLogout() {
        let confirmed = false;

        // 1. Try Custom Confirm (custom-confirm.js) - Best visual
        if (typeof window.showCustomConfirm === 'function') {
            confirmed = await window.showCustomConfirm('Apakah Anda yakin ingin logout?', '🚪 Konfirmasi Logout');
        }
        // 2. Try Modern Modal Confirm (modern-modals.js) - Good visual
        else if (typeof window.showConfirm === 'function') {
            confirmed = await window.showConfirm('Apakah Anda yakin ingin logout?', {
                title: 'Konfirmasi Logout',
                type: 'warning',
                confirmText: 'Ya, Logout',
                cancelText: 'Batal'
            });
        }
        // 3. Fallback to native browser confirm
        else {
            confirmed = confirm('Apakah Anda yakin ingin logout?');
        }

        if (confirmed) {
            this.logout();
        }
    }

    /**
     * Notify Flutter app that user logged out
     * This will cause the APK to close/exit
     */
    notifyFlutterLogout() {
        try {
            // Check if running in Flutter InAppWebView
            if (window.flutter_inappwebview && window.flutter_inappwebview.callHandler) {
                console.log('Notifying Flutter: user logout');
                window.flutter_inappwebview.callHandler('userLogout');
            }
        } catch (e) {
            console.log('Not in Flutter app or handler not available');
        }
    }

    requireAuth(allowedRoles = null) {
        // Re-check auto-login source once before redirecting.
        // This prevents false logout when injected auth token arrives slightly later.
        if (!this.isLoggedIn()) {
            this.checkAutoLogin();
            this.user = this.getStoredUser();
        }

        if (!this.isLoggedIn()) {
            const currentPath = window.location.pathname || '';
            window.location.href = currentPath.startsWith('/student') ? '/student/' : '/admin/';
            return false;
        }

        if (this.isPengawas()) {
            const currentPath = window.location.pathname || '';
            if (!this.isPengawasAllowedPath(currentPath)) {
                window.location.href = '/admin/exams.html';
                return false;
            }
        }

        if (allowedRoles) {
            const normalizedAllowedRoles = new Set(allowedRoles);
            if (normalizedAllowedRoles.has('student')) {
                normalizedAllowedRoles.add('guruplus');
            }
            if (normalizedAllowedRoles.has('admin')) {
                normalizedAllowedRoles.add('developer');
            }
            if (!normalizedAllowedRoles.has(this.user.role)) {
                alert('Anda tidak memiliki akses ke halaman ini');
                this.logout();
                return false;
            }
        }

        return true;
    }

    updateUserDisplay() {
        const userNameEl = document.getElementById('user-name');
        const userAvatarEl = document.getElementById('user-avatar');
        const userRoleEl = document.getElementById('user-role');

        if (this.user) {
            if (userNameEl) userNameEl.textContent = this.user.full_name || this.user.username;
            if (userAvatarEl) userAvatarEl.textContent = (this.user.full_name || this.user.username).charAt(0).toUpperCase();
            if (userRoleEl) {
                if (this.isPengawas()) {
                    userRoleEl.textContent = 'Pengawas';
                } else {
                    const roleLabels = {
                        developer: 'Developer',
                        admin: 'Admin',
                        teacher: 'Guru',
                        student: 'Siswa',
                        guruplus: 'GuruPlus',
                    };
                    userRoleEl.textContent = roleLabels[this.user.role]
                        || (this.user.role.charAt(0).toUpperCase() + this.user.role.slice(1));
                }
            }
        }
    }

    /**
     * Apply role-based UI modifications.
     * Hides admin-only menu items for teachers.
     */
    applyRoleBasedUI() {
        if (!this.user) return;

        const isAdmin = this.isAdmin();

        if (!isAdmin) {
            // Hide "Pengguna" menu item for non-admin
            const usersMenuItem = document.querySelector('a[href="/admin/users.html"]');
            if (usersMenuItem) {
                usersMenuItem.closest('.nav-item')?.remove();
            }

            // Hide any "add user" buttons
            const addUserLinks = document.querySelectorAll('a[href*="users.html?action=create"]');
            addUserLinks.forEach(link => link.style.display = 'none');
        }
    }
}
