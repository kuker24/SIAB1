/**
 * AUTO-GENERATED FILE.
 * Source modules: static/js/empty-state/modules/*.js
 * Use scripts/build_empty_state_bundle.sh after editing modules.
 */

/* ===== Module: 00-empty-state-class.js ===== */

/**
 * Empty State Component
 *
 * Usage:
 * const emptyState = new EmptyState({
 *     container: '#container',
 *     icon: 'fas fa-inbox',
 *     title: 'Tidak Ada Data',
 *     description: 'Belum ada data yang tersedia',
 *     action: { text: 'Tambah Baru', onClick: () => {} }
 * });
 */

class EmptyState {
    constructor(options = {}) {
        this.container = options.container;
        this.icon = options.icon || 'fas fa-inbox';
        this.title = options.title || 'Tidak Ada Data';
        this.description = options.description || 'Belum ada data yang tersedia';
        this.action = options.action || null;
        this.variant = options.variant || 'default'; // default, success, warning, error

        this.render();
    }

    render() {
        const container = typeof this.container === 'string'
            ? document.querySelector(this.container)
            : this.container;

        if (!container) return;

        container.innerHTML = this.getHTML();

        // Bind action if exists
        if (this.action) {
            const btn = container.querySelector('.empty-state-action');
            if (btn) {
                btn.addEventListener('click', this.action.onClick);
            }
        }
    }

    getHTML() {
        const variantColors = {
            default: 'var(--primary)',
            success: 'var(--success)',
            warning: 'var(--warning)',
            error: 'var(--danger)'
        };

        const iconColor = variantColors[this.variant] || variantColors.default;

        return `
            <div class="empty-state">
                <div class="empty-state-icon" style="color: ${iconColor}">
                    <i class="${this.icon}"></i>
                </div>
                <h3 class="empty-state-title">${this.title}</h3>
                <p class="empty-state-description">${this.description}</p>
                ${this.action ? `
                    <button class="btn btn-primary empty-state-action">
                        ${this.action.icon ? `<i class="${this.action.icon}"></i>` : ''}
                        ${this.action.text}
                    </button>
                ` : ''}
            </div>
        `;
    }

    // Static method for quick display
    static show(container, options = {}) {
        return new EmptyState({ container, ...options });
    }
}

/* ===== Module: 10-empty-state-presets-export.js ===== */

// Pre-configured empty states
const EmptyStates = {
    noExams: (container, action) => new EmptyState({
        container,
        icon: 'fas fa-file-alt',
        title: 'Belum Ada Ujian',
        description: 'Klik tombol di bawah untuk membuat ujian baru',
        action: action || null,
        variant: 'default'
    }),

    noStudents: (container, action) => new EmptyState({
        container,
        icon: 'fas fa-users',
        title: 'Belum Ada Siswa',
        description: 'Belum ada siswa yang terdaftar di sistem',
        action: action || null,
        variant: 'default'
    }),

    noResults: (container) => new EmptyState({
        container,
        icon: 'fas fa-chart-bar',
        title: 'Belum Ada Hasil',
        description: 'Hasil ujian akan muncul setelah siswa mengumpulkan jawaban',
        variant: 'default'
    }),

    noQuestions: (container, action) => new EmptyState({
        container,
        icon: 'fas fa-question-circle',
        title: 'Belum Ada Soal',
        description: 'Tambahkan soal untuk ujian ini',
        action: action || null,
        variant: 'warning'
    }),

    error: (container, message) => new EmptyState({
        container,
        icon: 'fas fa-exclamation-triangle',
        title: 'Terjadi Kesalahan',
        description: message || 'Silakan coba lagi nanti',
        variant: 'error'
    }),

    notFound: (container) => new EmptyState({
        container,
        icon: 'fas fa-search',
        title: 'Tidak Ditemukan',
        description: 'Data yang Anda cari tidak ditemukan',
        variant: 'warning'
    }),

    success: (container, title, description) => new EmptyState({
        container,
        icon: 'fas fa-check-circle',
        title: title || 'Berhasil!',
        description: description || 'Operasi berhasil dilakukan',
        variant: 'success'
    })
};

// Export for modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { EmptyState, EmptyStates };
}
