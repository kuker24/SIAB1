// Global auth instance
window.auth = new AuthManager();
const auth = window.auth; // Maintain local reference


// Auto-apply role-based UI when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    auth.updateUserDisplay();
    auth.applyRoleBasedUI();
});

// Utility functions (continued from original file - keeping only essential ones)
function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleDateString('id-ID', {
        year: 'numeric',
        month: 'long',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
}

function formatDuration(minutes) {
    if (minutes < 60) return `${minutes} menit`;
    const hours = Math.floor(minutes / 60);
    const mins = minutes % 60;
    return mins > 0 ? `${hours} jam ${mins} menit` : `${hours} jam`;
}
