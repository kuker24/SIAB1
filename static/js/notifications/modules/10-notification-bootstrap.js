// Global instance
let notificationManager;

function initNotifications() {
    notificationManager = new NotificationManager();
    notificationManager.init();
}

// Auto-init if DOM is ready
if (document.readyState === 'complete') {
    initNotifications();
} else {
    document.addEventListener('DOMContentLoaded', () => {
        // Only init if notification bell exists
        if (document.getElementById('notification-toggle')) {
            initNotifications();
        }
    });
}
