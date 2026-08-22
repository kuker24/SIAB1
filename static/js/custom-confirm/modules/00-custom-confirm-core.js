/**
 * Custom Confirmation Dialog - Global Utility
 * Provides modern, animated confirmation modal for all admin pages
 * Usage: const confirmed = await showCustomConfirm('message', 'title');
 */

// Create modal HTML if not exists
function initCustomConfirmModal() {
    if (document.getElementById('customConfirmModal')) return;

    const modalHTML = `
        <div class="custom-confirm-overlay" id="customConfirmModal" style="display: none;">
            <div class="custom-confirm-modal">
                <div class="custom-confirm-icon">
                    <i class="fas fa-exclamation-triangle"></i>
                </div>
                <div class="custom-confirm-content">
                    <h3 class="custom-confirm-title" id="customConfirmTitle">Konfirmasi</h3>
                    <p class="custom-confirm-message" id="customConfirmMessage">Apakah Anda yakin?</p>
                </div>
                <div class="custom-confirm-actions">
                    <button type="button" class="btn-custom-confirm btn-custom-cancel" id="customConfirmCancelBtn">
                        <i class="fas fa-times"></i> Batal
                    </button>
                    <button type="button" class="btn-custom-confirm btn-custom-ok" id="customConfirmOkBtn">
                        <i class="fas fa-check"></i> Ya, Lanjutkan
                    </button>
                </div>
            </div>
        </div>
    `;

    const modalStyles = `
        <style id="customConfirmStyles">
            .custom-confirm-overlay {
                position: fixed;
                top: 0; left: 0; right: 0; bottom: 0;
                background: rgba(0, 0, 0, 0.75);
                backdrop-filter: blur(10px);
                z-index: 999999;
                display: flex;
                align-items: center;
                justify-content: center;
                animation: customFadeIn 0.3s ease;
            }
            @keyframes customFadeIn {
                from { opacity: 0; }
                to { opacity: 1; }
            }
            .custom-confirm-modal {
                background: linear-gradient(145deg, rgba(30, 41, 59, 0.98), rgba(15, 23, 42, 0.98));
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 24px;
                max-width: 440px;
                width: 90%;
                box-shadow: 0 25px 70px rgba(0, 0, 0, 0.6), 0 0 0 1px rgba(255, 255, 255, 0.05);
                animation: customSlideIn 0.4s cubic-bezier(0.34, 1.56, 0.64, 1);
                overflow: hidden;
            }
            @keyframes customSlideIn {
                from { transform: scale(0.7) translateY(-40px); opacity: 0; }
                to { transform: scale(1) translateY(0); opacity: 1; }
            }
            .custom-confirm-icon {
                text-align: center;
                padding: 2.5rem 2rem 1rem;
            }
            .custom-confirm-icon i {
                font-size: 4.5rem;
                background: linear-gradient(135deg, #f59e0b, #ef4444);
                -webkit-background-clip: text;
                background-clip: text;
                -webkit-text-fill-color: transparent;
                animation: customPulse 2.5s ease-in-out infinite;
            }
            @keyframes customPulse {
                0%, 100% { transform: scale(1); filter: drop-shadow(0 0 12px rgba(245, 158, 11, 0.5)); }
                50% { transform: scale(1.15); filter: drop-shadow(0 0 24px rgba(239, 68, 68, 0.8)); }
            }
            .custom-confirm-content {
                text-align: center;
                padding: 0 2rem 2rem;
            }
            .custom-confirm-title {
                font-size: 1.75rem;
                font-weight: 700;
                color: #e2e8f0;
                margin: 0 0 0.75rem 0;
            }
            .custom-confirm-message {
                font-size: 1.05rem;
                color: #94a3b8;
                line-height: 1.7;
                margin: 0;
                white-space: pre-line;
            }
            .custom-confirm-actions {
                display: flex;
                gap: 0.875rem;
                padding: 1.75rem 2rem 2rem;
                background: rgba(0, 0, 0, 0.25);
            }
            .btn-custom-confirm {
                flex: 1;
                padding: 1rem 1.75rem;
                border: none;
                border-radius: 14px;
                font-size: 1.05rem;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.35s cubic-bezier(0.4, 0, 0.2, 1);
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 0.65rem;
            }
            .btn-custom-cancel {
                background: rgba(255, 255, 255, 0.08);
                color: #94a3b8;
                border: 1px solid rgba(255, 255, 255, 0.12);
            }
            .btn-custom-cancel:hover {
                background: rgba(255, 255, 255, 0.16);
                color: #e2e8f0;
                transform: translateY(-3px);
                box-shadow: 0 10px 20px rgba(0, 0, 0, 0.4);
            }
            .btn-custom-ok {
                background: linear-gradient(135deg, #ef4444, #dc2626);
                color: white;
                box-shadow: 0 6px 16px rgba(239, 68, 68, 0.45);
            }
            .btn-custom-ok:hover {
                background: linear-gradient(135deg, #dc2626, #b91c1c);
                transform: translateY(-3px);
                box-shadow: 0 12px 28px rgba(239, 68, 68, 0.65);
            }
            .btn-custom-confirm:active {
                transform: translateY(1px);
            }
            .custom-confirm-overlay.closing {
                animation: customFadeOut 0.25s ease forwards;
            }
            .custom-confirm-overlay.closing .custom-confirm-modal {
                animation: customSlideOut 0.3s ease forwards;
            }
            @keyframes customFadeOut {
                to { opacity: 0; }
            }
            @keyframes customSlideOut {
                to { transform: scale(0.85) translateY(30px); opacity: 0; }
            }
        </style>
    `;

    // Add to document
    if (!document.getElementById('customConfirmStyles')) {
        document.head.insertAdjacentHTML('beforeend', modalStyles);
    }
    document.body.insertAdjacentHTML('beforeend', modalHTML);
}

/**
 * Show Custom Confirmation Dialog
 * @param {string} message - Message to display
 * @param {string} title - Dialog title (default: 'Konfirmasi')
 * @returns {Promise<boolean>} - Resolves to true if OK, false if Cancel
 */
window.showCustomConfirm = function (message, title = 'Konfirmasi') {
    // Initialize modal if needed
    initCustomConfirmModal();

    return new Promise((resolve) => {
        const modal = document.getElementById('customConfirmModal');
        const titleEl = document.getElementById('customConfirmTitle');
        const messageEl = document.getElementById('customConfirmMessage');
        const okBtn = document.getElementById('customConfirmOkBtn');
        const cancelBtn = document.getElementById('customConfirmCancelBtn');

        // Set content
        titleEl.textContent = title;
        messageEl.textContent = message;

        // Show modal
        modal.style.display = 'flex';
        modal.classList.remove('closing');

        // Track if already resolved to prevent double resolve
        let resolved = false;

        // Close with animation, resolve AFTER animation completes
        function closeModal(result) {
            if (resolved) return; // Prevent double resolve
            resolved = true;

            modal.classList.add('closing');

            // Cleanup listeners immediately
            okBtn.removeEventListener('click', handleOk);
            cancelBtn.removeEventListener('click', handleCancel);
            document.removeEventListener('keydown', handleEsc);
            modal.removeEventListener('click', handleClickOutside);

            // Wait for animation to complete, THEN resolve
            setTimeout(() => {
                modal.style.display = 'none';
                modal.classList.remove('closing');
                resolve(result); // Resolve AFTER animation is done
            }, 300);
        }

        // Event handlers
        const handleOk = () => closeModal(true);
        const handleCancel = () => closeModal(false);
        const handleEsc = (e) => {
            if (e.key === 'Escape') closeModal(false);
        };
        const handleClickOutside = (e) => {
            if (e.target === modal) closeModal(false);
        };

        // Attach listeners
        okBtn.addEventListener('click', handleOk);
        cancelBtn.addEventListener('click', handleCancel);
        document.addEventListener('keydown', handleEsc);
        modal.addEventListener('click', handleClickOutside);
    });
};

