/**
 * 🔧 BOOTSTRAP MODAL CENTERING FIX
 * Fixes Bootstrap 5 modal centering issues
 */

(function () {
    'use strict';

    console.log('🔧 Bootstrap Modal Centering Fix initialized');

    function fixBootstrapModals() {
        // Add CSS fix for Bootstrap modals
        const style = document.createElement('style');
        style.id = 'bootstrap-modal-centering-fix';
        style.textContent = `
            /* BOOTSTRAP MODAL CENTERING FIX */
            .modal.show {
                display: flex !important;
                align-items: center !important;
                justify-content: center !important;
            }

            .modal-dialog {
                margin: 0 !important;
                max-width: 90%;
                width: 800px;
            }

            .modal-dialog-centered {
                display: flex;
                align-items: center;
                min-height: calc(100% - 1rem);
            }

            /* Ensure modal content is clickable */
            .modal-content {
                position: relative;
                z-index: 1;
                pointer-events: auto !important;
            }

            /* Ensure backdrop closes modal */
            .modal.show {
                pointer-events: auto !important;
            }

            .modal-backdrop {
                pointer-events: none !important;
            }
        `;

        // Remove existing fix if present
        const existingFix = document.getElementById('bootstrap-modal-centering-fix');
        if (existingFix) {
            existingFix.remove();
        }

        document.head.appendChild(style);
        console.log('✅ Bootstrap modal centering styles injected');
    }

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', fixBootstrapModals);
    } else {
        fixBootstrapModals();
    }

    // Re-apply fix whenever a modal is shown
    document.addEventListener('show.bs.modal', function (e) {
        console.log('📢 Bootstrap modal shown:', e.target.id);
        fixBootstrapModals();
    });
})();
