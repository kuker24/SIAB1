        },

        updateSidebarDisplay() {
            // Update sidebar avatar (simplified - photo only)
            const sidebarAvatarImg = document.getElementById('sidebar-avatar-img');
            const sidebarAvatarInitial = document.getElementById('sidebar-avatar-initial');

            if (sidebarAvatarImg && sidebarAvatarInitial) {
                const safeUrl = sanitizeAvatarUrl(this.currentUser.profile_picture);
                if (safeUrl) {
                    sidebarAvatarImg.src = safeUrl;
                    sidebarAvatarImg.style.display = 'block';
                    sidebarAvatarInitial.style.display = 'none';
                } else {
                    sidebarAvatarImg.style.display = 'none';
                    sidebarAvatarImg.removeAttribute('src');
                    sidebarAvatarInitial.style.display = 'flex';
                    sidebarAvatarInitial.textContent = (this.currentUser.full_name || 'U').charAt(0).toUpperCase();
                }
            }
        },

        updateHeaderAvatar() {
            // Update header avatar (top-right dropdown)
            const headerAvatarEl = document.getElementById('user-avatar');
            if (headerAvatarEl) {
                updateAvatarContainer(
                    headerAvatarEl,
                    this.currentUser.profile_picture,
                    (this.currentUser.full_name || 'U').charAt(0).toUpperCase()
                );
            }
        }
    };

    // Initialize on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => ProfileModal.init());
    } else {
        ProfileModal.init();
    }
})();
