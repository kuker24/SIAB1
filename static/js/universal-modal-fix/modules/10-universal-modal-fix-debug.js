// Make functions available globally for debugging
window.debugModals = function () {
    console.log('🔍 Active modals:');
    console.log('Modern modals:', document.querySelectorAll('.modern-modal-overlay.active'));
    console.log('Confirm modals:', document.querySelectorAll('.confirm-modal-overlay[style*="display: block"]'));
    console.log('Standard modals:', document.querySelectorAll('.modal-overlay[style*="display: block"]'));
};
