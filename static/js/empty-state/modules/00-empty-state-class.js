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
