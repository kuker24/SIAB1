/**
 * Activity Logs Dashboard Module
 * Handles user activity logging and statistics
 */

class ActivityLogsDashboard {
    constructor() {
        this.logs = [];
        this.stats = null;
        this.eventTypes = [];
        this.currentPage = 1;
        this.perPage = 50;
        this.total = 0;

        // Filters
        this.filters = {
            userId: null,
            eventType: null,
            dateFrom: null,
            dateTo: null
        };
    }

    /**
     * Initialize dashboard
     */
    async init() {
        await Promise.all([
            this.loadEventTypes(),
            this.loadStats(),
            this.loadLogs()
        ]);

        this.setupFilters();
    }

    /**
     * Load activity logs
     */
    async loadLogs() {
        try {
            const params = {
                page: this.currentPage,
                per_page: this.perPage,
                ...this.filters
            };

            // Remove null values
            Object.keys(params).forEach(key => {
                if (params[key] === null) delete params[key];
            });

            const response = await api.get('/activity/logs', params);

            this.logs = response.logs;
            this.total = response.total;
            this.renderLogsTable();
            this.renderPagination(response.total_pages);

            return response;
        } catch (error) {
            console.error('Failed to load logs:', error);
            UIComponents.showToast('Gagal memuat log aktivitas', 'error');
        }
    }

    /**
     * Load activity statistics
     */
    async loadStats(days = 7) {
        try {
            this.stats = await api.get('/activity/stats', { days });
            this.renderStats();
            this.renderChart();
            return this.stats;
        } catch (error) {
            console.error('Failed to load stats:', error);
        }
    }

    /**
     * Load event types for filter dropdown
     */
    async loadEventTypes() {
        try {
            const response = await api.get('/activity/event-types');
            this.eventTypes = response.event_types;
            this.renderEventTypesDropdown();
        } catch (error) {
            console.error('Failed to load event types:', error);
        }
    }

    /**
     * Render statistics cards
     */
    renderStats() {
        const container = document.getElementById('activity-stats');
        if (!container || !this.stats) return;

        container.innerHTML = `
            <div class="stat-card">
                <div class="stat-icon bg-primary">
                    <i class="fas fa-chart-line"></i>
                </div>
                <div class="stat-details">
                    <span class="stat-value">${this.stats.total_activities.toLocaleString()}</span>
                    <span class="stat-label">Total Aktivitas (${this.stats.period_days} hari)</span>
                </div>
            </div>

            <div class="stat-card">
                <div class="stat-icon bg-success">
                    <i class="fas fa-sign-in-alt"></i>
                </div>
                <div class="stat-details">
                    <span class="stat-value">${this.stats.by_type.login || 0}</span>
                    <span class="stat-label">Login</span>
                </div>
            </div>

            <div class="stat-card">
                <div class="stat-icon bg-info">
                    <i class="fas fa-file-alt"></i>
                </div>
                <div class="stat-details">
                    <span class="stat-value">${this.stats.by_type.exam_submit || 0}</span>
                    <span class="stat-label">Ujian Dikumpulkan</span>
                </div>
            </div>

            <div class="stat-card">
                <div class="stat-icon bg-warning">
                    <i class="fas fa-exclamation-triangle"></i>
                </div>
                <div class="stat-details">
                    <span class="stat-value">${this.stats.by_type.violation || 0}</span>
                    <span class="stat-label">Pelanggaran</span>
                </div>
            </div>
        `;
    }

    /**
     * Render activity trend chart
     */
    renderChart() {
        const canvas = document.getElementById('activity-chart');
        if (!canvas || !this.stats?.daily_trend) return;

        const ctx = canvas.getContext('2d');

        // Destroy existing chart
        if (window.activityChart) {
            window.activityChart.destroy();
        }

        window.activityChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: this.stats.daily_trend.map(d => d.date),
                datasets: [{
                    label: 'Aktivitas Harian',
                    data: this.stats.daily_trend.map(d => d.count),
                    borderColor: '#6366f1',
                    backgroundColor: 'rgba(99, 102, 241, 0.1)',
                    fill: true,
                    tension: 0.3
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true
                    }
                }
            }
        });
    }

    /**
     * Render top users list
     */
    renderTopUsers() {
        const container = document.getElementById('top-users-list');
        if (!container || !this.stats?.top_users) return;

        container.innerHTML = this.stats.top_users.map((user, index) => `
            <div class="top-user-item">
                <span class="rank">${index + 1}</span>
                <span class="user-name">${user.user_name}</span>
                <span class="activity-count">${user.activity_count}</span>
            </div>
        `).join('');
    }

    /**
     * Render logs table
     */
    renderLogsTable() {
        const container = document.getElementById('logs-table-body');
        if (!container) return;

        if (this.logs.length === 0) {
            container.innerHTML = `
                <tr>
                    <td colspan="6" class="text-center">
                        <div class="empty-state">
                            <i class="fas fa-search fa-2x"></i>
                            <p>Tidak ada log aktivitas yang ditemukan</p>
                        </div>
                    </td>
                </tr>
            `;
            return;
        }

        container.innerHTML = this.logs.map(log => `
            <tr>
                <td>${this.formatDateTime(log.created_at)}</td>
                <td>
                    <span class="user-info">
                        ${log.user_name || 'Unknown'}
                        ${log.user_role ? `<span class="badge badge-${this.getRoleBadge(log.user_role)}">${log.user_role}</span>` : ''}
                    </span>
                </td>
                <td>
                    <span class="badge badge-${this.getEventBadge(log.event_type)}">
                        ${log.event_type}
                    </span>
                </td>
                <td class="ip-address">${log.ip_address || '-'}</td>
                <td>
                    <button class="btn btn-sm btn-secondary"
                            onclick="activityDashboard.showLogDetails(${JSON.stringify(log).replace(/"/g, '&quot;')})">
                        <i class="fas fa-eye"></i>
                    </button>
                </td>
            </tr>
        `).join('');
    }

    /**
     * Show log details modal
     */
    showLogDetails(log) {
        const modalHTML = `
            <div class="modal-overlay" id="log-details-modal">
                <div class="modal modal-md">
                    <div class="modal-header">
                        <h3>Detail Log Aktivitas</h3>
                        <button class="modal-close" onclick="document.getElementById('log-details-modal').remove()">&times;</button>
                    </div>
                    <div class="modal-body">
                        <div class="log-details-grid">
                            <div class="detail-item">
                                <label>Waktu:</label>
                                <span>${this.formatDateTime(log.created_at)}</span>
                            </div>
                            <div class="detail-item">
                                <label>User:</label>
                                <span>${log.user_name || 'Unknown'}</span>
                            </div>
                            <div class="detail-item">
                                <label>Event Type:</label>
                                <span class="badge badge-${this.getEventBadge(log.event_type)}">${log.event_type}</span>
                            </div>
                            <div class="detail-item">
                                <label>IP Address:</label>
                                <span>${log.ip_address || '-'}</span>
                            </div>
                        </div>

                        <hr>

                        <h5>Event Data:</h5>
                        <pre style="background: var(--bg-tertiary); padding: 1rem; border-radius: 0.5rem; overflow-x: auto;">
${JSON.stringify(log.event_data, null, 2)}
                        </pre>
                    </div>
                </div>
            </div>
        `;

        document.body.insertAdjacentHTML('beforeend', modalHTML);
    }

    /**
     * Render event types dropdown
     */
    renderEventTypesDropdown() {
        const select = document.getElementById('filter-event-type');
        if (!select) return;

        select.innerHTML = `
            <option value="">Semua Tipe Event</option>
            ${this.eventTypes.map(type => `
                <option value="${type}">${type}</option>
            `).join('')}
        `;
    }

    /**
     * Setup filter event listeners
     */
    setupFilters() {
        const filterForm = document.getElementById('activity-filters');
        if (!filterForm) return;

        // Event type filter
        document.getElementById('filter-event-type')?.addEventListener('change', (e) => {
            this.filters.eventType = e.target.value || null;
            this.currentPage = 1;
            this.loadLogs();
        });

        // Date range filters
        document.getElementById('filter-date-from')?.addEventListener('change', (e) => {
            this.filters.dateFrom = e.target.value || null;
            this.currentPage = 1;
            this.loadLogs();
        });

        document.getElementById('filter-date-to')?.addEventListener('change', (e) => {
            this.filters.dateTo = e.target.value || null;
            this.currentPage = 1;
            this.loadLogs();
        });
    }

    /**
     * Render pagination
     */
    renderPagination(totalPages) {
        const container = document.getElementById('logs-pagination');
        if (!container) return;

        if (totalPages <= 1) {
            container.innerHTML = '';
            return;
        }

        let html = '<div class="pagination">';

        // Previous button
        html += `<button class="page-btn" ${this.currentPage === 1 ? 'disabled' : ''}
                         onclick="activityDashboard.goToPage(${this.currentPage - 1})">
                    <i class="fas fa-chevron-left"></i>
                 </button>`;

        // Page numbers
        for (let i = 1; i <= totalPages; i++) {
            if (i === 1 || i === totalPages || (i >= this.currentPage - 2 && i <= this.currentPage + 2)) {
                html += `<button class="page-btn ${i === this.currentPage ? 'active' : ''}"
                                 onclick="activityDashboard.goToPage(${i})">${i}</button>`;
            } else if (i === this.currentPage - 3 || i === this.currentPage + 3) {
                html += '<span class="page-dots">...</span>';
            }
        }

        // Next button
        html += `<button class="page-btn" ${this.currentPage === totalPages ? 'disabled' : ''}
                         onclick="activityDashboard.goToPage(${this.currentPage + 1})">
                    <i class="fas fa-chevron-right"></i>
                 </button>`;

        html += '</div>';
        container.innerHTML = html;
    }

    goToPage(page) {
        this.currentPage = page;
        this.loadLogs();
    }

    // Helpers
    formatDateTime(dateString) {
        return new Date(dateString).toLocaleString('id-ID');
    }

    getRoleBadge(role) {
        const badges = { admin: 'danger', teacher: 'primary', student: 'success' };
        return badges[role] || 'secondary';
    }

    getEventBadge(eventType) {
        if (eventType.includes('login')) return 'success';
        if (eventType.includes('violation')) return 'danger';
        if (eventType.includes('exam')) return 'info';
        return 'secondary';
    }
}

// Global instance
