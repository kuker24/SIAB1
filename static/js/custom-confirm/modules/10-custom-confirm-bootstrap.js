// Auto-initialize on DOM ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initCustomConfirmModal);
} else {
    initCustomConfirmModal();
}
