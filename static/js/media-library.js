/**
 * AUTO-GENERATED FILE.
 * Source modules: static/js/media-library/modules/*.js
 * Use scripts/build_media_library_bundle.sh after editing modules.
 */

/* ===== Module: 00-sanitize-and-render-utils.js ===== */

/**
 * Media Library Module
 * Centralized media file management
 */

function escapeHtml(value) {
    const text = value == null ? '' : String(value);
    return text.replace(/[&<>"'`]/g, (char) => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;',
        '`': '&#96;'
    }[char] || char));
}

function escapeAttribute(value) {
    return escapeHtml(value).replace(/\n/g, '&#10;');
}

function sanitizeMediaUrl(rawUrl, options = {}) {
    const { allowDataImage = false, allowBlob = false } = options;
    const value = rawUrl == null ? '' : String(rawUrl).trim();
    if (!value) {
        return '';
    }

    if (allowDataImage && /^data:image\/[a-z0-9.+-]+;base64,[a-z0-9+/=]+$/i.test(value)) {
        return value;
    }

    if (allowBlob && value.startsWith('blob:')) {
        return value;
    }

    if (/^(\/|\.\/|\.\.\/)/.test(value)) {
        return value;
    }

    try {
        const parsed = new URL(value, window.location.origin);
        if (parsed.protocol === 'http:' || parsed.protocol === 'https:') {
            return parsed.href;
        }
    } catch (error) {
        return '';
    }

    return '';
}

function renderSafeImageMarkup(url, altText, extraAttributes = '') {
    const safeUrl = sanitizeMediaUrl(url);
    if (!safeUrl) {
        return '';
    }
    return `<img src="${escapeAttribute(safeUrl)}" alt="${escapeAttribute(altText)}"${extraAttributes}>`;
}

/* ===== Module: 10-media-library-class.js ===== */

class MediaLibrary {
    constructor() {
        this.files = [];
        this.currentPage = 1;
        this.perPage = 24;
        this.total = 0;
        this.stats = null;

        // Filters
        this.filters = {
            fileType: null,
            tags: null,
            searchQuery: null
        };
    }

    /**
     * Initialize media library
     */
    async init() {
        await Promise.all([
            this.loadFiles(),
            this.loadStats()
        ]);

        this.setupUploadListeners();
    }

    /**
     * Load media files
     */
    async loadFiles() {
        try {
            const params = {
                page: this.currentPage,
                per_page: this.perPage,
                ...this.filters
            };

            Object.keys(params).forEach(key => {
                if (params[key] === null) delete params[key];
            });

            const response = await api.get('/media/', params);

            this.files = response.files;
            this.total = response.total;
            this.renderFileGrid();
            this.renderPagination(response.total_pages);

            return response;
        } catch (error) {
            console.error('Failed to load media files:', error);
            UIComponents.showToast('Gagal memuat file media', 'error');
        }
    }

    /**
     * Load media statistics
     */
    async loadStats() {
        try {
            this.stats = await api.get('/media/stats/summary');
            this.renderStats();
        } catch (error) {
            console.error('Failed to load media stats:', error);
        }
    }

    /**
     * Upload file
     */
    async uploadFile(file, tags = '', description = '') {
        const formData = new FormData();
        formData.append('file', file);
        if (tags) formData.append('tags', tags);
        if (description) formData.append('description', description);

        try {
            const response = await fetch('/api/media/upload', {
                method: 'POST',
                body: formData,
                headers: {
                    'Authorization': `Bearer ${localStorage.getItem('access_token')}`
                }
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Upload gagal');
            }

            const result = await response.json();
            UIComponents.showToast('File berhasil diupload', 'success');
            this.loadFiles();
            this.loadStats();
            return result;
        } catch (error) {
            UIComponents.showToast(error.message || 'Gagal mengupload file', 'error');
            throw error;
        }
    }

    /**
     * Delete file
     */
    async deleteFile(mediaId) {
        if (!await showConfirm(
            'File tidak dapat dikembalikan setelah dihapus.',
            '🗑️ Hapus File Media',
            { type: 'danger', confirmText: 'Hapus', cancelText: 'Batal' }
        )) return;

        try {
            await api.delete(`/media/${mediaId}`);
            UIComponents.showToast('File berhasil dihapus', 'success');
            this.loadFiles();
            this.loadStats();
        } catch (error) {
            UIComponents.showToast('Gagal menghapus file', 'error');
        }
    }

    /**
     * Update file metadata
     */
    async updateMetadata(mediaId, data) {
        try {
            const response = await api.patch(`/media/${mediaId}`, data);
            UIComponents.showToast('Metadata diperbarui', 'success');
            return response;
        } catch (error) {
            UIComponents.showToast('Gagal memperbarui metadata', 'error');
            throw error;
        }
    }

    /**
     * Show upload modal
     */
    showUploadModal() {
        const modalHTML = `
            <div class="modal-overlay" id="upload-modal">
                <div class="modal modal-md">
                    <div class="modal-header">
                        <h3><i class="fas fa-cloud-upload-alt"></i> Upload File</h3>
                        <button class="modal-close" onclick="closeUploadModal()">&times;</button>
                    </div>
                    <div class="modal-body">
                        <div class="upload-zone" id="upload-dropzone">
                            <i class="fas fa-cloud-upload-alt fa-3x"></i>
                            <p>Drag & drop file di sini atau</p>
                            <input type="file" id="file-input" hidden 
                                   accept="image/*,video/*,audio/*,.pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx">
                            <button class="btn btn-primary" onclick="document.getElementById('file-input').click()">
                                Pilih File
                            </button>
                            <p class="upload-hint">Maksimal 10MB per file</p>
                        </div>
                        
                        <div id="file-preview" style="display: none;">
                            <h5>File yang dipilih:</h5>
                            <div id="preview-content"></div>
                        </div>
                        
                        <div class="form-group">
                            <label for="upload-tags">Tags (pisahkan dengan koma)</label>
                            <input type="text" id="upload-tags" class="form-control"
                                   placeholder="Contoh: matematika, soal, kelas-12">
                        </div>
                        
                        <div class="form-group">
                            <label for="upload-description">Deskripsi</label>
                            <textarea id="upload-description" class="form-control" rows="2"
                                      placeholder="Deskripsi file (opsional)"></textarea>
                        </div>
                    </div>
                    <div class="modal-footer">
                        <button class="btn btn-secondary" onclick="closeUploadModal()">Batal</button>
                        <button class="btn btn-primary" id="btn-upload-submit" disabled
                                onclick="mediaLibrary.submitUpload()">
                            <i class="fas fa-upload"></i> Upload
                        </button>
                    </div>
                </div>
            </div>
        `;

        document.body.insertAdjacentHTML('beforeend', modalHTML);
        this.setupDropzone();
    }

    /**
     * Setup dropzone events
     */
    setupDropzone() {
        const dropzone = document.getElementById('upload-dropzone');
        const fileInput = document.getElementById('file-input');

        if (!dropzone || !fileInput) return;

        // Drag & drop events
        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(event => {
            dropzone.addEventListener(event, (e) => {
                e.preventDefault();
                e.stopPropagation();
            });
        });

        ['dragenter', 'dragover'].forEach(event => {
            dropzone.addEventListener(event, () => {
                dropzone.classList.add('drag-over');
            });
        });

        ['dragleave', 'drop'].forEach(event => {
            dropzone.addEventListener(event, () => {
                dropzone.classList.remove('drag-over');
            });
        });

        dropzone.addEventListener('drop', (e) => {
            const files = e.dataTransfer.files;
            if (files.length > 0) {
                this.previewFile(files[0]);
            }
        });

        fileInput.addEventListener('change', (e) => {
            if (e.target.files.length > 0) {
                this.previewFile(e.target.files[0]);
            }
        });
    }

    /**
     * Preview selected file
     */
    previewFile(file) {
        this.selectedFile = file;

        const preview = document.getElementById('file-preview');
        const content = document.getElementById('preview-content');
        const submitBtn = document.getElementById('btn-upload-submit');

        if (!preview || !content) return;

        preview.style.display = 'block';
        submitBtn.disabled = false;

        const isImage = file.type.startsWith('image/');

        if (isImage) {
            const reader = new FileReader();
            reader.onload = (e) => {
                const previewUrl = sanitizeMediaUrl(e.target.result, { allowDataImage: true, allowBlob: true });
                content.innerHTML = `
                    <div class="file-preview-item">
                        <img src="${escapeAttribute(previewUrl)}" alt="${escapeAttribute(file.name)}" style="max-width: 200px; max-height: 150px;">
                        <div class="file-info">
                            <strong>${escapeHtml(file.name)}</strong>
                            <span>${this.formatFileSize(file.size)}</span>
                        </div>
                    </div>
                `;
            };
            reader.readAsDataURL(file);
        } else {
            content.innerHTML = `
                <div class="file-preview-item">
                    <i class="fas ${this.getFileIcon(file.type)} fa-3x"></i>
                    <div class="file-info">
                        <strong>${escapeHtml(file.name)}</strong>
                        <span>${this.formatFileSize(file.size)}</span>
                    </div>
                </div>
            `;
        }
    }

    /**
     * Submit upload
     */
    async submitUpload() {
        if (!this.selectedFile) return;

        const tags = document.getElementById('upload-tags').value;
        const description = document.getElementById('upload-description').value;

        const submitBtn = document.getElementById('btn-upload-submit');
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Uploading...';

        try {
            await this.uploadFile(this.selectedFile, tags, description);
            closeUploadModal();
        } catch (error) {
            submitBtn.disabled = false;
            submitBtn.innerHTML = '<i class="fas fa-upload"></i> Upload';
        }
    }

    /**
     * Render file grid
     */
    renderFileGrid() {
        const container = document.getElementById('media-grid');
        if (!container) return;

        if (this.files.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <i class="fas fa-images fa-3x"></i>
                    <h4>Tidak ada file</h4>
                    <p>Upload file pertama Anda untuk memulai</p>
                    <button class="btn btn-primary" onclick="mediaLibrary.showUploadModal()">
                        <i class="fas fa-upload"></i> Upload File
                    </button>
                </div>
            `;
            return;
        }

        container.innerHTML = `
            <div class="media-grid">
                ${this.files.map(file => `
                    <div class="media-card" onclick="mediaLibrary.showFileDetails(${file.id})">
                        <div class="media-thumbnail">
                            ${file.file_type === 'image'
                ? (renderSafeImageMarkup(file.file_url, file.original_filename, ' loading="lazy"')
                    || `<i class="fas ${this.getFileIcon(file.mime_type)} fa-3x"></i>`)
                : `<i class="fas ${this.getFileIcon(file.mime_type)} fa-3x"></i>`
            }
                            <div class="media-type-badge">
                                ${escapeHtml(file.file_type)}
                            </div>
                        </div>
                        <div class="media-info">
                            <span class="media-name" title="${escapeAttribute(file.original_filename)}">
                                ${escapeHtml(this.truncateName(file.original_filename, 20))}
                            </span>
                            <span class="media-size">${this.formatFileSize(file.file_size)}</span>
                        </div>
                    </div>
                `).join('')}
            </div>
        `;
    }

    /**
     * Show file details modal
     */
    async showFileDetails(mediaId) {
        try {
            const file = await api.get(`/media/${mediaId}`);
            const safeFileUrl = sanitizeMediaUrl(file.file_url);
            const safeOriginalFilename = escapeHtml(file.original_filename);
            const safeUploaderName = escapeHtml(file.uploader_name || 'Unknown');
            const safeTags = Array.isArray(file.tags) && file.tags.length > 0
                ? file.tags.map(tag => escapeHtml(tag)).join(', ')
                : '-';
            const safeDescription = file.description ? escapeHtml(file.description) : '-';
            const safePreviewMarkup = file.file_type === 'image'
                ? (renderSafeImageMarkup(file.file_url, file.original_filename) || `<i class="fas ${this.getFileIcon(file.mime_type)} fa-5x"></i>`)
                : `<i class="fas ${this.getFileIcon(file.mime_type)} fa-5x"></i>`;
            const safeDownloadUrl = safeFileUrl || '#';

            const modalHTML = `
                <div class="modal-overlay" id="file-details-modal">
                    <div class="modal modal-lg">
                        <div class="modal-header">
                            <h3>${safeOriginalFilename}</h3>
                            <button class="modal-close" onclick="document.getElementById('file-details-modal').remove()">&times;</button>
                        </div>
                        <div class="modal-body">
                            <div class="file-details-layout">
                                <div class="file-preview-large">
                                    ${safePreviewMarkup}
                                </div>
                                
                                <div class="file-metadata">
                                    <div class="metadata-item">
                                        <label>URL:</label>
                                        <div class="url-copy">
                                            <input type="text" value="${escapeAttribute(safeFileUrl)}" readonly id="file-url-input">
                                            <button class="btn btn-sm btn-secondary" onclick="copyFileUrl()">
                                                <i class="fas fa-copy"></i>
                                            </button>
                                        </div>
                                    </div>
                                    
                                    <div class="metadata-item">
                                        <label>Ukuran:</label>
                                        <span>${this.formatFileSize(file.file_size)}</span>
                                    </div>
                                    
                                    ${file.width && file.height ? `
                                        <div class="metadata-item">
                                            <label>Dimensi:</label>
                                            <span>${file.width} x ${file.height} px</span>
                                        </div>
                                    ` : ''}
                                    
                                    <div class="metadata-item">
                                        <label>Diupload:</label>
                                        <span>${new Date(file.created_at).toLocaleString('id-ID')}</span>
                                    </div>
                                    
                                    <div class="metadata-item">
                                        <label>Oleh:</label>
                                        <span>${safeUploaderName}</span>
                                    </div>
                                    
                                    <div class="metadata-item">
                                        <label>Tags:</label>
                                        <span>${safeTags}</span>
                                    </div>
                                    
                                    <div class="metadata-item">
                                        <label>Deskripsi:</label>
                                        <span>${safeDescription}</span>
                                    </div>
                                    
                                    <div class="metadata-item">
                                        <label>Digunakan:</label>
                                        <span>${file.usage_count || 0} kali</span>
                                    </div>
                                </div>
                            </div>
                        </div>
                        <div class="modal-footer">
                            <button class="btn btn-danger" onclick="mediaLibrary.deleteFile(${file.id}); document.getElementById('file-details-modal').remove();">
                                <i class="fas fa-trash"></i> Hapus
                            </button>
                            <a href="${escapeAttribute(safeDownloadUrl)}" class="btn btn-primary" download target="_blank" rel="noopener noreferrer">
                                <i class="fas fa-download"></i> Download
                            </a>
                        </div>
                    </div>
                </div>
            `;

            document.body.insertAdjacentHTML('beforeend', modalHTML);
        } catch (error) {
            UIComponents.showToast('Gagal memuat detail file', 'error');
        }
    }

    /**
     * Render statistics
     */
    renderStats() {
        const container = document.getElementById('media-stats');
        if (!container || !this.stats) return;

        container.innerHTML = `
            <div class="stat-card">
                <div class="stat-icon bg-primary">
                    <i class="fas fa-files"></i>
                </div>
                <div class="stat-details">
                    <span class="stat-value">${this.stats.total_files}</span>
                    <span class="stat-label">Total File</span>
                </div>
            </div>
            <div class="stat-card">
                <div class="stat-icon bg-info">
                    <i class="fas fa-hdd"></i>
                </div>
                <div class="stat-details">
                    <span class="stat-value">${this.stats.total_size_mb} MB</span>
                    <span class="stat-label">Storage Digunakan</span>
                </div>
            </div>
        `;
    }

    /**
     * Setup upload listeners
     */
    setupUploadListeners() {
        // Search filter
        document.getElementById('media-search')?.addEventListener('input',
            this.debounce((e) => {
                this.filters.searchQuery = e.target.value || null;
                this.currentPage = 1;
                this.loadFiles();
            }, 500)
        );

        // Type filter
        document.getElementById('media-type-filter')?.addEventListener('change', (e) => {
            this.filters.fileType = e.target.value || null;
            this.currentPage = 1;
            this.loadFiles();
        });
    }

    /**
     * Render pagination
     */
    renderPagination(totalPages) {
        const container = document.getElementById('media-pagination');
        if (!container || totalPages <= 1) {
            if (container) container.innerHTML = '';
            return;
        }

        let html = '<div class="pagination">';

        if (this.currentPage > 1) {
            html += `<button class="page-btn" onclick="mediaLibrary.goToPage(${this.currentPage - 1})">
                        <i class="fas fa-chevron-left"></i>
                     </button>`;
        }

        html += `<span class="page-info">Page ${this.currentPage} of ${totalPages}</span>`;

        if (this.currentPage < totalPages) {
            html += `<button class="page-btn" onclick="mediaLibrary.goToPage(${this.currentPage + 1})">
                        <i class="fas fa-chevron-right"></i>
                     </button>`;
        }

        html += '</div>';
        container.innerHTML = html;
    }

    goToPage(page) {
        this.currentPage = page;
        this.loadFiles();
    }

    // Helpers
    formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    getFileIcon(mimeType) {
        if (!mimeType) return 'fa-file';
        if (mimeType.startsWith('image/')) return 'fa-image';
        if (mimeType.startsWith('video/')) return 'fa-video';
        if (mimeType.startsWith('audio/')) return 'fa-music';
        if (mimeType.includes('pdf')) return 'fa-file-pdf';
        if (mimeType.includes('word')) return 'fa-file-word';
        if (mimeType.includes('excel') || mimeType.includes('spreadsheet')) return 'fa-file-excel';
        if (mimeType.includes('powerpoint') || mimeType.includes('presentation')) return 'fa-file-powerpoint';
        return 'fa-file';
    }

    truncateName(name, maxLength) {
        if (name.length <= maxLength) return name;
        return name.substring(0, maxLength - 3) + '...';
    }

    debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }
}


/* ===== Module: 20-media-library-bootstrap.js ===== */

// Global instance
let mediaLibrary;

function initMediaLibrary() {
    mediaLibrary = new MediaLibrary();
    mediaLibrary.init();
}

function closeUploadModal() {
    const modal = document.getElementById('upload-modal');
    if (modal) modal.remove();
}

function copyFileUrl() {
    const input = document.getElementById('file-url-input');
    if (input) {
        input.select();
        document.execCommand('copy');
        UIComponents.showToast('Tautan berhasil disalin ke clipboard.', 'success');
    }
}
