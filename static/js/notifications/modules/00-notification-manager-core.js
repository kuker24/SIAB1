/**
 * Notifications Module
 * In-app notification system (NO EMAIL/PUSH)
 */

class NotificationManager {
    constructor(options = {}) {
        this.notifications = [];
        this.unreadCount = 0;
        this.pollingInterval = options.pollingInterval || 30000; // 30 seconds
        this.pollingTimer = null;
        this.isDropdownOpen = false;
        this.isLoadingUnreadCount = false;
    }

    /**
     * Initialize notification manager
     */
    async init() {
        await this.loadUnreadCount();
        this.setupDropdown();
        this.startPolling();
    }

    /**
     * Start polling for new notifications
     */
    startPolling() {
        this.stopPolling();
        this.pollingTimer = setInterval(() => {
            if (!document.hidden) {
                this.loadUnreadCount();
            }
        }, this.pollingInterval);
    }

    /**
     * Stop polling
     */
    stopPolling() {
        if (this.pollingTimer) {
            clearInterval(this.pollingTimer);
            this.pollingTimer = null;
        }
    }

    /**
     * Load unread count
     */
    async loadUnreadCount() {
        if (document.hidden || this.isLoadingUnreadCount) {
            return this.unreadCount;
        }
        this.isLoadingUnreadCount = true;

        try {
            const response = await api.get('/notifications/unread-count');
            this.unreadCount = response.unread_count;
            this.updateBadge();
            return this.unreadCount;
        } catch (error) {
            console.error('Failed to load unread count:', error);
            return 0;
        } finally {
            this.isLoadingUnreadCount = false;
        }
    }

    /**
     * Load notifications
     */
    async loadNotifications(unreadOnly = false, page = 1) {
        try {
            const response = await api.get('/notifications/', {
                unread_only: unreadOnly,
                page: page,
                per_page: 10
            });

            this.notifications = response.notifications;
            this.renderNotificationsList();
            return response;
        } catch (error) {
            console.error('Failed to load notifications:', error);
            return { notifications: [], total: 0 };
        }
    }

    /**
     * Mark notification as read
     */
    async markAsRead(notificationId) {
        try {
            await api.patch(`/notifications/${notificationId}/mark-read`);

            // Update local state
            const notification = this.notifications.find(n => n.id === notificationId);
            if (notification) {
                notification.is_read = true;
            }

            this.unreadCount = Math.max(0, this.unreadCount - 1);
            this.updateBadge();
            this.renderNotificationsList();

        } catch (error) {
            console.error('Failed to mark as read:', error);
        }
    }

    /**
     * Mark all as read
     */
    async markAllAsRead() {
        try {
            await api.patch('/notifications/mark-all-read');

            this.notifications.forEach(n => n.is_read = true);
            this.unreadCount = 0;
            this.updateBadge();
            this.renderNotificationsList();

            UIComponents.showToast('Semua notifikasi ditandai sudah dibaca', 'success');
        } catch (error) {
            UIComponents.showToast('Gagal menandai notifikasi', 'error');
        }
    }

    /**
     * Delete notification
     */
    async deleteNotification(notificationId) {
        try {
            await api.delete(`/notifications/${notificationId}`);

            const index = this.notifications.findIndex(n => n.id === notificationId);
            if (index > -1) {
                if (!this.notifications[index].is_read) {
                    this.unreadCount = Math.max(0, this.unreadCount - 1);
                    this.updateBadge();
                }
                this.notifications.splice(index, 1);
            }
            this.renderNotificationsList();

        } catch (error) {
            console.error('Failed to delete notification:', error);
        }
    }

    /**
     * Clear all read notifications
     */
    async clearAll() {
        try {
            await api.delete('/notifications/clear-all', { read_only: true });
            this.notifications = this.notifications.filter(n => !n.is_read);
            this.renderNotificationsList();
            UIComponents.showToast('Notifikasi yang sudah dibaca dihapus', 'success');
        } catch (error) {
            UIComponents.showToast('Gagal menghapus notifikasi', 'error');
        }
    }

    /**
     * Update badge count
     */
    updateBadge() {
        const badge = document.getElementById('notification-badge');
        if (!badge) return;

        if (this.unreadCount > 0) {
            badge.textContent = this.unreadCount > 99 ? '99+' : this.unreadCount;
            badge.style.display = 'flex';
        } else {
            badge.style.display = 'none';
        }
    }

    /**
     * Setup dropdown
     */
    setupDropdown() {
        const toggle = document.getElementById('notification-toggle');
        const dropdown = document.getElementById('notification-dropdown');

        if (!toggle || !dropdown) return;

        toggle.addEventListener('click', async (e) => {
            e.stopPropagation();

            if (this.isDropdownOpen) {
                this.closeDropdown();
            } else {
                this.openDropdown();
                await this.loadNotifications();
            }
        });

        // Close on outside click
        document.addEventListener('click', (e) => {
            if (!dropdown.contains(e.target) && !toggle.contains(e.target)) {
                this.closeDropdown();
            }
        });
    }

    openDropdown() {
        const dropdown = document.getElementById('notification-dropdown');
        if (dropdown) {
            dropdown.classList.add('show');
            this.isDropdownOpen = true;
        }
    }

    closeDropdown() {
        const dropdown = document.getElementById('notification-dropdown');
        if (dropdown) {
            dropdown.classList.remove('show');
            this.isDropdownOpen = false;
        }
    }

    /**
     * Render notifications list
     */
    renderNotificationsList() {
        const container = document.getElementById('notification-list');
        if (!container) return;

        if (this.notifications.length === 0) {
            container.innerHTML = `
                <div class="notification-empty">
                    <i class="fas fa-bell-slash"></i>
                    <p>Tidak ada notifikasi</p>
                </div>
            `;
            return;
        }

        container.innerHTML = this.notifications.map(notification => `
            <div class="notification-item ${notification.is_read ? 'read' : 'unread'}"
                 onclick="notificationManager.handleNotificationClick(${notification.id}, '${notification.action_url || ''}')">
                <div class="notification-icon ${this.getIconClass(notification.type)}">
                    <i class="fas ${this.getIcon(notification.type)}"></i>
                </div>
                <div class="notification-content">
                    <div class="notification-title">${notification.title}</div>
                    <div class="notification-message">${this.truncate(notification.message, 60)}</div>
                    <div class="notification-time">${this.formatTime(notification.created_at)}</div>
                </div>
                <button class="notification-delete" onclick="event.stopPropagation(); notificationManager.deleteNotification(${notification.id})">
                    <i class="fas fa-times"></i>
                </button>
            </div>
        `).join('');
    }

    /**
     * Handle notification click
     */
    async handleNotificationClick(notificationId, actionUrl) {
        await this.markAsRead(notificationId);

        if (actionUrl) {
            window.location.href = actionUrl;
        }
    }

    // Helpers
    getIcon(type) {
        const icons = {
            'exam_published': 'fa-file-alt',
            'exam_graded': 'fa-check-circle',
            'violation_detected': 'fa-exclamation-triangle',
            'exam_starting_soon': 'fa-clock',
            'grade_updated': 'fa-star',
            'system': 'fa-cog'
        };
        return icons[type] || 'fa-bell';
    }

    getIconClass(type) {
        const classes = {
            'exam_published': 'bg-primary',
            'exam_graded': 'bg-success',
            'violation_detected': 'bg-danger',
            'exam_starting_soon': 'bg-warning',
            'grade_updated': 'bg-info',
            'system': 'bg-secondary'
        };
        return classes[type] || 'bg-secondary';
    }

    formatTime(dateString) {
        const date = new Date(dateString);
        const now = new Date();
        const diff = Math.floor((now - date) / 1000);

        if (diff < 60) return 'Baru saja';
        if (diff < 3600) return `${Math.floor(diff / 60)} menit lalu`;
        if (diff < 86400) return `${Math.floor(diff / 3600)} jam lalu`;
        if (diff < 604800) return `${Math.floor(diff / 86400)} hari lalu`;

        return date.toLocaleDateString('id-ID');
    }

    truncate(text, maxLength) {
        if (text.length <= maxLength) return text;
        return text.substring(0, maxLength) + '...';
    }
}
