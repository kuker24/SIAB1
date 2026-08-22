// 1. CONFIRM DIALOG (Replacement for confirm())
// ============================================
async function showConfirm(message, titleOrOptions = 'Konfirmasi', optionsParam = {}) {
    let title = titleOrOptions;
    let options = optionsParam;

    // Handle overloaded call: showConfirm(message, options)
    if (typeof titleOrOptions === 'object' && titleOrOptions !== null) {
        options = titleOrOptions;
        title = options.title || 'Konfirmasi';
    }

    const {
        confirmText = 'Ya, Lanjutkan',
        cancelText = 'Batal',
        type = 'warning' // warning, danger, info, success
    } = options;

    const icons = {
        warning: '⚠️',
        danger: '🗑️',
        info: 'ℹ️',
        success: '✅'
    };

    const btnClass = {
        warning: 'warning',
        danger: 'danger',
        info: 'primary',
        success: 'success'
    };

    return new Promise((resolve) => {
        // Convert \n to <br> for proper line breaks
        const formattedMessage = message.replace(/\n/g, '<br>');

        const content = `
            <div class="modern-modal-header">
                <h3 class="modern-modal-title">
                    <span class="icon">${icons[type] || icons.warning}</span>
                    ${title}
                </h3>
                <button class="modern-modal-close" data-action="close">&times;</button>
            </div>
            <div class="modern-modal-body">${formattedMessage}</div>
            <div class="modern-modal-footer">
                <button class="modern-modal-btn modern-modal-btn-secondary" data-action="cancel">
                    <i class="fas fa-times"></i> ${cancelText}
                </button>
                <button class="modern-modal-btn modern-modal-btn-${btnClass[type] || 'primary'}" data-action="confirm">
                    <i class="fas fa-check"></i> ${confirmText}
                </button>
            </div>
        `;

        const overlay = createModal(content, type);
        let resolved = false;

        const handleAction = (action) => {
            if (resolved) return;
            resolved = true;
            closeModal(overlay, () => resolve(action === 'confirm'));
        };

        // Explicitly attach listeners to buttons
        const buttons = overlay.querySelectorAll('[data-action]');
        buttons.forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const action = btn.dataset.action;
                handleAction(action);
            });
        });

        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) {
                handleAction('close');
            }
        });

        // ESC key closes
        const handleEsc = (e) => {
            if (e.key === 'Escape') {
                handleAction('close');
                document.removeEventListener('keydown', handleEsc);
            }
        };
        document.addEventListener('keydown', handleEsc);
    });
}

// ============================================
// 2. ALERT DIALOG (Replacement for alert())
// ============================================
async function showAlert(message, type = 'info', title = null) {
    const configs = {
        success: { icon: '✅', title: 'Berhasil' },
        error: { icon: '❌', title: 'Error' },
        warning: { icon: '⚠️', title: 'Peringatan' },
        info: { icon: 'ℹ️', title: 'Informasi' }
    };

    const config = configs[type] || configs.info;
    const modalTitle = title || config.title;

    return new Promise((resolve) => {
        // Convert \n to <br> for proper line breaks
        const formattedMessage = message.replace(/\n/g, '<br>');

        const content = `
            <div class="modern-modal-header">
                <h3 class="modern-modal-title">
                    <span class="icon">${config.icon}</span>
                    ${modalTitle}
                </h3>
                <button class="modern-modal-close" data-action="close">&times;</button>
            </div>
            <div class="modern-modal-body">${formattedMessage}</div>
            <div class="modern-modal-footer">
                <button class="modern-modal-btn modern-modal-btn-primary" data-action="close">
                    <i class="fas fa-check"></i> OK
                </button>
            </div>
        `;

        const overlay = createModal(content, type);

        const close = () => {
            closeModal(overlay, resolve);
        };

        // Explicitly attach listeners to buttons
        const buttons = overlay.querySelectorAll('[data-action]');
        buttons.forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const action = btn.dataset.action;
                if (action === 'close') {
                    close();
                }
            });
        });

        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) {
                close();
            }
        });

        // ESC or Enter closes
        const handleKey = (e) => {
            if (e.key === 'Escape' || e.key === 'Enter') {
                close();
                document.removeEventListener('keydown', handleKey);
            }
        };
        document.addEventListener('keydown', handleKey);
    });
}

// ============================================
