/**
 * Dashboard Widgets Module
 * Handles loading and rendering of dashboard statistics.
 */

class DashboardWidgets {
    constructor() {
        this.init();
    }

    init() {
        // Only run if we are on the dashboard
        if (!document.getElementById('dashboard-stats-container')) return;

        this.loadStats();
    }

    async loadStats() {
        try {
            // Note: /stats/dashboard endpoint might still be mock in backend or basic
            // We can enhance it or fetch specific data here
            const stats = await api.getDashboardStats();

            this.renderStatCards(stats);

            // If we have exam analytics, we could load charts here
            // this.loadCharts();

        } catch (error) {
            console.error('Failed to load dashboard stats:', error);
        }
    }

    renderStatCards(stats) {
        // Map backend keys to UI elements
        const mapping = {
            'total_users': { el: 'stat-total-users', formatter: n => n },
            'total_exams': { el: 'stat-total-exams', formatter: n => n },
            'active_sessions': { el: 'stat-active-sessions', formatter: n => n },
            'completed_exams': { el: 'stat-completed-exams', formatter: n => n }
        };

        for (const [key, config] of Object.entries(mapping)) {
            const el = document.getElementById(config.el);
            if (el && stats[key] !== undefined) {
                el.innerText = config.formatter(stats[key]);
            }
        }
    }
}
