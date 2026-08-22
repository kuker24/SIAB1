/**
 * Header User Display Handler
 * Manages user dropdown in header with themed dialogs
 * Include this after theme-dialog.js and profile-modal.js
 */

(function () {
    'use strict';

    function sanitizeAvatarUrl(rawUrl) {
        const value = rawUrl == null ? '' : String(rawUrl).trim();
        if (!value) {
            return '';
        }

        if (/^data:image\/[a-z0-9.+-]+;base64,[a-z0-9+/=]+$/i.test(value) || value.startsWith('blob:')) {
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

    function setAvatarContent(container, profilePicture, fallbackText) {
        if (!container) return;

        const safeUrl = sanitizeAvatarUrl(profilePicture);
        container.replaceChildren();

        if (safeUrl) {
            const image = document.createElement('img');
            image.src = safeUrl;
            image.alt = 'Profile';
            image.style.width = '100%';
            image.style.height = '100%';
            image.style.objectFit = 'cover';
            image.style.borderRadius = '50%';
            container.appendChild(image);
            return;
        }

        container.textContent = fallbackText;
    }

    function initHeaderUser() {
        // Get user data
        const user = JSON.parse(localStorage.getItem('user') || '{}');
        if (!user.id) return;

        // Update header user info if elements exist
        const userNameEl = document.getElementById('user-name');
        const userRoleEl = document.getElementById('user-role');
        const userAvatarEl = document.getElementById('user-avatar');

        if (userNameEl) {
            userNameEl.textContent = user.full_name || user.username || 'User';
        }

        if (userRoleEl) {
            const roleLabels = {
                developer: 'Developer',
                admin: 'Administrator',
                teacher: 'Guru',
                student: 'Siswa',
                guruplus: 'GuruPlus',
            };
            userRoleEl.textContent = roleLabels[user.role] || user.role;
        }

        if (userAvatarEl) {
            setAvatarContent(
                userAvatarEl,
                user.profile_picture,
                (user.full_name || user.username || 'U').charAt(0).toUpperCase()
            );
        }

        // Profile button handler
        const profileBtns = document.querySelectorAll('.dropdown-item');
        profileBtns.forEach(btn => {
            const text = btn.textContent.trim().toLowerCase();
            if (text.includes('profil') && !text.includes('logout')) {
                btn.addEventListener('click', (e) => {
                    e.preventDefault();
                    if (typeof ProfileModal !== 'undefined') {
                        ProfileModal.open();
                    }
                });
            }
        });

        // Logout button handler with themed dialog
        const logoutBtn = document.getElementById('logout-btn-2');
        if (logoutBtn) {
            logoutBtn.addEventListener('click', async (e) => {
                e.preventDefault();
                if (window.auth) {
                    window.auth.confirmLogout();
                } else {
                    // Fallback if auth is missing
                    window.location.href = '/logout';
                }
            });
        }
    }
