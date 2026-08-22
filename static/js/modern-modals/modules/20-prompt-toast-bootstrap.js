// 3. PROMPT DIALOG (Replacement for prompt())
// ============================================
async function showPrompt(message, defaultValue = '', title = 'Input') {
    return new Promise((resolve) => {
        const inputId = 'prompt_input_' + Date.now();

        const content = `
            <div class="modern-modal-header">
                <h3 class="modern-modal-title">
                    <span class="icon">📝</span>
                    ${title}
                </h3>
                <button class="modern-modal-close" data-action="close">&times;</button>
            </div>
            <div class="modern-modal-body">
                ${message}
                <input type="text" class="modern-modal-input" id="${inputId}" value="${defaultValue.replace(/"/g, '&quot;')}" placeholder="Ketik di sini..." />
            </div>
            <div class="modern-modal-footer">
                <button class="modern-modal-btn modern-modal-btn-secondary" data-action="cancel">
                    <i class="fas fa-times"></i> Batal
                </button>
                <button class="modern-modal-btn modern-modal-btn-primary" data-action="submit">
                    <i class="fas fa-check"></i> OK
                </button>
            </div>
        `;

        const overlay = createModal(content, 'info');
        const input = document.getElementById(inputId);
        let resolved = false;

        const submit = (value) => {
            if (resolved) return;
            resolved = true;
            closeModal(overlay, () => resolve(value));
        };

        // Explicitly attach listeners to buttons
        const buttons = overlay.querySelectorAll('[data-action]');
        buttons.forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const action = btn.dataset.action;
                if (action === 'submit') {
                    submit(input.value);
                } else if (action === 'cancel' || action === 'close') {
                    submit(null);
                }
            });
        });

        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) {
                submit(null);
            }
        });

        input.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                submit(input.value);
            }
        });

        const handleEsc = (e) => {
            if (e.key === 'Escape') {
                submit(null);
                document.removeEventListener('keydown', handleEsc);
            }
        };
        document.addEventListener('keydown', handleEsc);

        // Auto-focus input
        setTimeout(() => {
            input.focus();
            input.select();
        }, 100);
    });
}

// ============================================
// 4. TOAST NOTIFICATION (Bonus)
// ============================================
function showToast(message, type = 'info', duration = 3000) {
    // Inject toast styles if not present
    if (!document.getElementById('toast-styles')) {
        const styles = document.createElement('style');
        styles.id = 'toast-styles';
        styles.textContent = `
            .modern-toast-container {
                position: fixed;
                top: 20px;
                right: 20px;
                z-index: 10001;
                display: flex;
                flex-direction: column;
                gap: 10px;
            }
            .modern-toast {
                padding: 14px 20px;
                border-radius: 12px;
                background: linear-gradient(145deg, rgba(30, 41, 59, 0.95) 0%, rgba(15, 23, 42, 0.95) 100%);
                backdrop-filter: blur(8px);
                box-shadow: 0 10px 40px rgba(0,0,0,0.4);
                color: #f1f5f9;
                font-size: 14px;
                display: flex;
                align-items: center;
                gap: 12px;
                transform: translateX(120%);
                transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
                border-left: 4px solid;
            }
            .modern-toast.show { transform: translateX(0); }
            .modern-toast.type-success { border-color: #10b981; }
            .modern-toast.type-error { border-color: #ef4444; }
            .modern-toast.type-warning { border-color: #f59e0b; }
            .modern-toast.type-info { border-color: #3b82f6; }
        `;
        document.head.appendChild(styles);
    }

    let container = document.querySelector('.modern-toast-container');
    if (!container) {
        container = document.createElement('div');
        container.className = 'modern-toast-container';
        document.body.appendChild(container);
    }

    const icons = { success: '✅', error: '❌', warning: '⚠️', info: 'ℹ️' };

    const toast = document.createElement('div');
    toast.className = `modern-toast type-${type}`;
    toast.innerHTML = `<span>${icons[type] || icons.info}</span><span>${message}</span>`;
    container.appendChild(toast);

    requestAnimationFrame(() => toast.classList.add('show'));

    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, duration);
}

console.log('✅ Modern Modal Library v2.1 loaded (Enhanced Glassmorphism)');
