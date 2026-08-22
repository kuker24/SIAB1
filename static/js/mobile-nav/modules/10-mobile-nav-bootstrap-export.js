// Auto-initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => MobileNav.init());
} else {
    MobileNav.init();
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = MobileNav;
}
