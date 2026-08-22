    // Initialize on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initHeaderUser);
    } else {
        initHeaderUser();
    }
})();
