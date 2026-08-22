/**
 * Exam Templates Module
 * Handles exam template management
 */

class ExamTemplateManager {
    constructor() {
        this.templates = [];
        this.currentPage = 1;
        this.perPage = 20;
        this.total = 0;
    }

    /**
     * Load templates
     */
    async loadTemplates(publicOnly = false) {
        try {
            const response = await api.get('/templates/', {
                page: this.currentPage,
                per_page: this.perPage,
                public_only: publicOnly
            });

            this.templates = response.templates;
            this.total = response.total;
            this.renderTemplatesList();
            return response;
        } catch (error) {
            console.error('Failed to load templates:', error);
            UIComponents.showToast('Gagal memuat templates', 'error');
            return { templates: [], total: 0 };
        }
    }

    /**
     * Create template from current exam
     */
    async createTemplate(examData, name, description, isPublic = false) {
        try {
            const response = await api.post('/templates/', {
                name: name,
                description: description,
                template_data: examData,
                is_public: isPublic
            });

            UIComponents.showToast('Template berhasil dibuat', 'success');
            this.loadTemplates();
            return response;
        } catch (error) {
            UIComponents.showToast(error.detail || 'Gagal membuat template', 'error');
            throw error;
        }
    }

    /**
     * Delete template
     */
    async deleteTemplate(templateId) {
        if (!await showConfirm(
            'Template akan dihapus permanent.',
            '🗑️ Hapus Template',
            { type: 'danger', confirmText: 'Hapus', cancelText: 'Batal' }
        )) return;

        try {
            await api.delete(`/templates/${templateId}`);
            UIComponents.showToast('Template berhasil dihapus', 'success');
            this.loadTemplates();
        } catch (error) {
            UIComponents.showToast('Gagal menghapus template', 'error');
        }
    }

    /**
     * Show create exam from template modal
     */
    showCreateExamModal(template) {
        const now = new Date();
        now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
        const minDate = now.toISOString().slice(0, 16);

        const modalHTML = `
            <div class="modal-overlay" id="create-exam-modal">
                <div class="modal modal-lg">
                    <div class="modal-header">
                        <h3><i class="fas fa-file-import"></i> Buat Ujian dari Template</h3>
                        <button class="modal-close" onclick="closeCreateExamModal()">&times;</button>
                    </div>
                    <div class="modal-body">
                        <div class="template-info">
                            <h4>${template.name}</h4>
                            <p>${template.description || 'Tidak ada deskripsi'}</p>
                        </div>

                        <hr>

                        <div class="form-group">
                            <label for="exam-title">Judul Ujian *</label>
                            <input type="text" id="exam-title" class="form-control"
                                   placeholder="Masukkan judul ujian" required>
                        </div>

                        <div class="form-group">
                            <label for="exam-description">Deskripsi</label>
                            <textarea id="exam-description" class="form-control" rows="3"
                                      placeholder="Deskripsi ujian (opsional)"></textarea>
                        </div>

                        <div class="form-row">
                            <div class="form-group col-md-6">
                                <label for="exam-start-time">Waktu Mulai *</label>
                                <input type="datetime-local" id="exam-start-time"
                                       class="form-control" min="${minDate}" required>
                            </div>
                            <div class="form-group col-md-6">
                                <label for="exam-end-time">Waktu Selesai *</label>
                                <input type="datetime-local" id="exam-end-time"
                                       class="form-control" required>
                            </div>
                        </div>

                        <div class="form-group">
                            <label for="exam-classes">Kelas yang Diizinkan (kosongkan untuk semua kelas)</label>
                            <input type="text" id="exam-classes" class="form-control"
                                   placeholder="Contoh: XII-IPA-1,XII-IPA-2,XII-IPS-1">
                            <small class="text-muted">Pisahkan dengan koma jika lebih dari satu kelas</small>
                        </div>

                        <div class="form-row">
                            <div class="form-group col-md-4">
                                <label for="exam-duration">Durasi (menit)</label>
                                <input type="number" id="exam-duration" class="form-control"
                                       placeholder="Default: dari template" min="1">
                            </div>
                            <div class="form-group col-md-4">
                                <label for="exam-passing-score">Nilai Lulus</label>
                                <input type="number" id="exam-passing-score" class="form-control"
                                       placeholder="Default: dari template" min="0" max="100">
                            </div>
                            <div class="form-group col-md-4">
                                <label for="exam-max-attempts">Max Percobaan</label>
                                <input type="number" id="exam-max-attempts" class="form-control"
                                       placeholder="Default: 1" min="1">
                            </div>
                        </div>
                    </div>
                    <div class="modal-footer">
                        <button class="btn btn-secondary" onclick="closeCreateExamModal()">
                            Batal
                        </button>
                        <button class="btn btn-primary" onclick="templateManager.saveExamFromTemplate(${template.id})">
                            <i class="fas fa-plus"></i> Buat Ujian
                        </button>
                    </div>
                </div>
            </div>
        `;

        document.body.insertAdjacentHTML('beforeend', modalHTML);
    }

    /**
     * Save exam from template
     */
    async saveExamFromTemplate(templateId) {
        const title = document.getElementById('exam-title').value.trim();
        const description = document.getElementById('exam-description').value.trim();
        const startTime = document.getElementById('exam-start-time').value;
        const endTime = document.getElementById('exam-end-time').value;
        const classes = document.getElementById('exam-classes').value.trim();
        const duration = document.getElementById('exam-duration').value;
        const passingScore = document.getElementById('exam-passing-score').value;
        const maxAttempts = document.getElementById('exam-max-attempts').value;

        if (!title || !startTime || !endTime) {
            UIComponents.showToast('Judul dan waktu ujian harus diisi', 'error');
            return;
        }

        try {
            const data = {
                title: title,
                description: description || null,
                start_time: startTime,
                end_time: endTime,
                allowed_classes: classes || null
            };

            if (duration) data.duration_minutes = parseInt(duration);
            if (passingScore) data.passing_score = parseFloat(passingScore);
            if (maxAttempts) data.max_attempts = parseInt(maxAttempts);

            const response = await api.post(`/templates/${templateId}/create-exam`, data);

            UIComponents.showToast('Ujian berhasil dibuat dari template', 'success');
            closeCreateExamModal();

            // Redirect to exam management with draft focus so newly created exam is visible
            if (response.id) {
                window.location.href = `/admin/exams.html?filter=draft&created_id=${response.id}`;
            }

        } catch (error) {
            UIComponents.showToast(error.detail || 'Gagal membuat ujian', 'error');
        }
    }

    /**
     * Render templates list
     */
    renderTemplatesList() {
        const container = document.getElementById('templates-container');
        if (!container) return;

        if (this.templates.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <i class="fas fa-folder-open fa-3x"></i>
                    <h4>Belum ada template</h4>
                    <p>Buat template dari ujian yang sudah ada untuk mempercepat pembuatan ujian baru</p>
                </div>
            `;
            return;
        }

        container.innerHTML = `
            <div class="templates-grid">
                ${this.templates.map(template => `
                    <div class="template-card">
                        <div class="template-header">
                            <h4>${template.name}</h4>
                            ${template.is_public ? '<span class="badge badge-info">Public</span>' : ''}
                        </div>
                        <div class="template-body">
                            <p>${template.description || 'Tidak ada deskripsi'}</p>
                            <div class="template-meta">
                                <small>Dibuat: ${new Date(template.created_at).toLocaleDateString('id-ID')}</small>
                            </div>
                        </div>
                        <div class="template-footer">
                            <button class="btn btn-sm btn-primary"
                                    onclick="templateManager.showCreateExamModal(${JSON.stringify(template).replace(/"/g, '&quot;')})">
                                <i class="fas fa-plus"></i> Gunakan
                            </button>
                            <button class="btn btn-sm btn-secondary"
                                    onclick="templateManager.viewTemplate(${template.id})">
                                <i class="fas fa-eye"></i>
                            </button>
                            <button class="btn btn-sm btn-danger"
                                    onclick="templateManager.deleteTemplate(${template.id})">
                                <i class="fas fa-trash"></i>
                            </button>
                        </div>
                    </div>
                `).join('')}
            </div>
        `;
    }

    /**
     * View template details
     */
    async viewTemplate(templateId) {
        try {
            const template = await api.get(`/templates/${templateId}`);

            const modalHTML = `
                <div class="modal-overlay" id="view-template-modal">
                    <div class="modal modal-lg">
                        <div class="modal-header">
                            <h3>${template.name}</h3>
                            <button class="modal-close" onclick="document.getElementById('view-template-modal').remove()">&times;</button>
                        </div>
                        <div class="modal-body">
                            <p><strong>Deskripsi:</strong> ${template.description || '-'}</p>
                            <p><strong>Publik:</strong> ${template.is_public ? 'Ya' : 'Tidak'}</p>
                            <hr>
                            <h5>Konfigurasi Template:</h5>
                            <pre style="background: var(--bg-tertiary); padding: 1rem; border-radius: 0.5rem; overflow-x: auto;">
${JSON.stringify(template.template_data, null, 2)}
                            </pre>
                        </div>
                    </div>
                </div>
            `;

            document.body.insertAdjacentHTML('beforeend', modalHTML);
        } catch (error) {
            UIComponents.showToast('Gagal memuat detail template', 'error');
        }
    }
}
