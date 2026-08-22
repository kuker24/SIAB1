// Auto-initialize
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => PerformanceOptimizer.init());
} else {
    PerformanceOptimizer.init();
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = PerformanceOptimizer;
}
