/**
 * Toast Notification System
 * 
 * Usage:
 *   Toast.success('Data berhasil disimpan');
 *   Toast.error('Terjadi kesalahan');
 *   Toast.warning('Perhatian!');
 *   Toast.info('Info penting');
 */

class ToastNotification {
    constructor() {
        this.container = null;
        this.init();
    }

    init() {
        // Create container if not exists
        if (!document.getElementById('toast-container')) {
            this.container = document.createElement('div');
            this.container.id = 'toast-container';
            this.container.className = 'toast-container';
            document.body.appendChild(this.container);
        } else {
            this.container = document.getElementById('toast-container');
        }

        // Inject styles
        this.injectStyles();
    }

    injectStyles() {
        if (document.getElementById('toast-styles')) return;

        const styles = document.createElement('style');
        styles.id = 'toast-styles';
        styles.textContent = `
            .toast-container {
                position: fixed;
                top: 20px;
                right: 20px;
                z-index: 10000;
                display: flex;
                flex-direction: column;
                gap: 12px;
                max-width: 400px;
                pointer-events: none;
            }

            .toast {
                display: flex;
                align-items: flex-start;
                gap: 12px;
                padding: 16px 20px;
                border-radius: 12px;
                background: rgba(30, 41, 59, 0.95);
                backdrop-filter: blur(20px);
                border: 1px solid rgba(255, 255, 255, 0.1);
                box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
                color: #f8fafc;
                font-size: 14px;
                line-height: 1.5;
                pointer-events: auto;
                transform: translateX(120%);
                opacity: 0;
                transition: all 0.4s cubic-bezier(0.34, 1.56, 0.64, 1);
            }

            .toast.show {
                transform: translateX(0);
                opacity: 1;
            }

            .toast.hide {
                transform: translateX(120%);
                opacity: 0;
            }

            .toast-icon {
                font-size: 20px;
                flex-shrink: 0;
                margin-top: 1px;
            }

            .toast-content {
                flex: 1;
            }

            .toast-title {
                font-weight: 600;
                margin-bottom: 4px;
            }

            .toast-message {
                color: rgba(255, 255, 255, 0.8);
            }

            .toast-close {
                background: none;
                border: none;
                color: rgba(255, 255, 255, 0.5);
                cursor: pointer;
                padding: 4px;
                margin: -4px -4px -4px 8px;
                font-size: 18px;
                line-height: 1;
                transition: color 0.2s;
            }

            .toast-close:hover {
                color: white;
            }

            .toast-progress {
                position: absolute;
                bottom: 0;
                left: 0;
                height: 3px;
                border-radius: 0 0 12px 12px;
                transition: width linear;
            }

            /* Toast variants */
            .toast-success {
                border-left: 4px solid #22c55e;
            }
            .toast-success .toast-icon { color: #22c55e; }
            .toast-success .toast-progress { background: #22c55e; }

            .toast-error {
                border-left: 4px solid #ef4444;
            }
            .toast-error .toast-icon { color: #ef4444; }
            .toast-error .toast-progress { background: #ef4444; }

            .toast-warning {
                border-left: 4px solid #f59e0b;
            }
            .toast-warning .toast-icon { color: #f59e0b; }
            .toast-warning .toast-progress { background: #f59e0b; }

            .toast-info {
                border-left: 4px solid #3b82f6;
            }
            .toast-info .toast-icon { color: #3b82f6; }
            .toast-info .toast-progress { background: #3b82f6; }

            /* Mobile responsive */
            @media (max-width: 480px) {
                .toast-container {
                    top: auto;
                    bottom: 20px;
                    left: 16px;
                    right: 16px;
                    max-width: none;
                }
            }
        `;
        document.head.appendChild(styles);
    }

    show(options) {
        const {
            type = 'info',
            title = '',
            message = '',
            duration = 5000,
            closable = true
        } = options;

        const icons = {
            success: 'fa-check-circle',
            error: 'fa-times-circle',
            warning: 'fa-exclamation-triangle',
            info: 'fa-info-circle'
        };

        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.innerHTML = `
            <div class="toast-icon"><i class="fas ${icons[type]}"></i></div>
            <div class="toast-content">
                ${title ? `<div class="toast-title">${title}</div>` : ''}
                <div class="toast-message">${message}</div>
            </div>
            ${closable ? '<button class="toast-close">&times;</button>' : ''}
            ${duration > 0 ? '<div class="toast-progress" style="width: 100%"></div>' : ''}
        `;

        // Close button handler
        if (closable) {
            toast.querySelector('.toast-close').addEventListener('click', () => {
                this.dismiss(toast);
            });
        }

        this.container.appendChild(toast);

        // Trigger animation
        requestAnimationFrame(() => {
            toast.classList.add('show');
        });

        // Auto dismiss with progress
        if (duration > 0) {
            const progress = toast.querySelector('.toast-progress');
            if (progress) {
                progress.style.transition = `width ${duration}ms linear`;
                requestAnimationFrame(() => {
                    progress.style.width = '0%';
                });
            }

            setTimeout(() => {
                this.dismiss(toast);
            }, duration);
        }

        return toast;
    }

    dismiss(toast) {
        toast.classList.remove('show');
        toast.classList.add('hide');
        setTimeout(() => {
            toast.remove();
        }, 400);
    }

    // Convenience methods
    success(message, title = 'Berhasil', duration = 4000) {
        return this.show({ type: 'success', title, message, duration });
    }

    error(message, title = 'Error', duration = 6000) {
        return this.show({ type: 'error', title, message, duration });
    }

    warning(message, title = 'Perhatian', duration = 5000) {
        return this.show({ type: 'warning', title, message, duration });
    }

    info(message, title = 'Info', duration = 4000) {
        return this.show({ type: 'info', title, message, duration });
    }
}
