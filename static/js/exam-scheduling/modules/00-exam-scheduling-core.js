/**
 * Exam Scheduling Module
 * Handles scheduled publication of exams
 */

class ExamScheduler {
    constructor(examId) {
        this.examId = examId;
        this.schedules = [];
    }

    /**
     * Schedule auto-publish/unpublish
     */
    async schedulePublication(publishAt, unpublishAt = null) {
        try {
            const response = await api.post(`/scheduled/exams/${this.examId}/schedule`, {
                publish_at: publishAt,
                unpublish_at: unpublishAt
            });

            UIComponents.showToast('Jadwal publikasi berhasil disimpan', 'success');
            return response;
        } catch (error) {
            UIComponents.showToast(error.detail || 'Gagal menjadwalkan publikasi', 'error');
            throw error;
        }
    }

    /**
     * Load existing schedules
     */
    async loadSchedules() {
        try {
            this.schedules = await api.get(`/scheduled/exams/${this.examId}/schedules`);
            this.renderSchedulesList();
            return this.schedules;
        } catch (error) {
            console.error('Failed to load schedules:', error);
            return [];
        }
    }

    /**
     * Cancel pending schedule
     */
    async cancelSchedule(scheduleId) {
        if (!await showConfirm(
            'Jadwal publikasi akan dibatalkan.',
            '❌ Batal Jadwal',
            { type: 'warning', confirmText: 'Ya, Batalkan', cancelText: 'Tidak' }
        )) return;

        try {
            await api.delete(`/scheduled/schedules/${scheduleId}`);
            UIComponents.showToast('Jadwal dibatalkan', 'success');
            this.loadSchedules();
        } catch (error) {
            UIComponents.showToast('Gagal membatalkan jadwal', 'error');
        }
    }

    /**
     * Show schedule modal
     */
    showScheduleModal() {
        const modalHTML = `
            <div class="modal-overlay" id="schedule-modal">
                <div class="modal modal-md">
                    <div class="modal-header">
                        <h3><i class="fas fa-clock"></i> Jadwalkan Publikasi Ujian</h3>
                        <button class="modal-close" onclick="closeScheduleModal()">&times;</button>
                    </div>
                    <div class="modal-body">
                        <div class="form-group">
                            <label for="publish-datetime">
                                <i class="fas fa-calendar-check"></i> Waktu Publikasi Otomatis *
                            </label>
                            <input type="datetime-local" 
                                   id="publish-datetime" 
                                   class="form-control" 
                                   required>
                            <small class="text-muted">
                                Ujian akan otomatis dipublish pada waktu ini
                            </small>
                        </div>
                        
                        <div class="form-group">
                            <label for="unpublish-datetime">
                                <i class="fas fa-calendar-times"></i> Waktu Unpublish Otomatis (Opsional)
                            </label>
                            <input type="datetime-local" 
                                   id="unpublish-datetime" 
                                   class="form-control">
                            <small class="text-muted">
                                Ujian akan otomatis ditutup pada waktu ini (kosongkan jika tidak perlu)
                            </small>
                        </div>

                        <div class="alert alert-info" style="margin-top: 1rem;">
                            <i class="fas fa-info-circle"></i>
                            <strong>Catatan:</strong> Sistem akan memproses jadwal setiap 1 menit. 
                            Publikasi mungkin terjadi 1-2 menit setelah waktu yang ditentukan.
                        </div>
                    </div>
                    <div class="modal-footer">
                        <button class="btn btn-secondary" onclick="closeScheduleModal()">
                            <i class="fas fa-times"></i> Batal
                        </button>
                        <button class="btn btn-primary" onclick="examScheduler.saveSchedule()">
                            <i class="fas fa-save"></i> Simpan Jadwal
                        </button>
                    </div>
                </div>
            </div>
        `;

        document.body.insertAdjacentHTML('beforeend', modalHTML);

        // Set minimum datetime to now
        const now = new Date();
        now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
        document.getElementById('publish-datetime').min = now.toISOString().slice(0, 16);
    }

    /**
     * Save schedule from modal
     */
    async saveSchedule() {
        const publishAt = document.getElementById('publish-datetime').value;
        const unpublishAt = document.getElementById('unpublish-datetime').value;

        if (!publishAt) {
            UIComponents.showToast('Waktu publikasi harus diisi', 'error');
            return;
        }

        try {
            await this.schedulePublication(publishAt, unpublishAt || null);
            closeScheduleModal();
            this.loadSchedules();
        } catch (error) {
            // Error already shown
        }
    }

    /**
     * Render schedules list
     */
    renderSchedulesList() {
        const container = document.getElementById('schedules-list');
        if (!container) return;

        if (this.schedules.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <i class="fas fa-calendar-times fa-2x"></i>
                    <p>Belum ada jadwal publikasi</p>
                </div>
            `;
            return;
        }

        container.innerHTML = this.schedules.map(schedule => `
            <div class="schedule-item ${schedule.status}">
                <div class="schedule-info">
                    <div class="schedule-status">
                        <span class="badge badge-${this.getStatusBadge(schedule.status)}">
                            ${schedule.status.toUpperCase()}
                        </span>
                    </div>
                    <div class="schedule-times">
                        <div>
                            <i class="fas fa-calendar-check"></i>
                            <strong>Publish:</strong> ${this.formatDateTime(schedule.publish_at)}
                        </div>
                        ${schedule.unpublish_at ? `
                            <div>
                                <i class="fas fa-calendar-times"></i>
                                <strong>Unpublish:</strong> ${this.formatDateTime(schedule.unpublish_at)}
                            </div>
                        ` : ''}
                    </div>
                    ${schedule.executed_at ? `
                        <div class="schedule-executed">
                            <i class="fas fa-check-circle"></i>
                            Dieksekusi: ${this.formatDateTime(schedule.executed_at)}
                        </div>
                    ` : ''}
                    ${schedule.error_message ? `
                        <div class="schedule-error">
                            <i class="fas fa-exclamation-triangle"></i>
                            Error: ${schedule.error_message}
                        </div>
                    ` : ''}
                </div>
                ${schedule.status === 'pending' ? `
                    <div class="schedule-actions">
                        <button class="btn btn-sm btn-danger" 
                                onclick="examScheduler.cancelSchedule(${schedule.id})">
                            <i class="fas fa-times"></i> Batalkan
                        </button>
                    </div>
                ` : ''}
            </div>
        `).join('');
    }

    getStatusBadge(status) {
        const badges = {
            'pending': 'warning',
            'published': 'success',
            'unpublished': 'secondary',
            'cancelled': 'danger'
        };
        return badges[status] || 'secondary';
    }

    formatDateTime(dateString) {
        const date = new Date(dateString);
        return date.toLocaleString('id-ID', {
            weekday: 'short',
            year: 'numeric',
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        });
    }
}

