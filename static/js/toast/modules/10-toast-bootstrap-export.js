// Global instance
const Toast = new ToastNotification();

// Export for modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = Toast;
}
