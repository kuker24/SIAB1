/**
 * AUTO-GENERATED FILE.
 * Source modules: static/js/universal-modal-fix/modules/*.js
 * Use scripts/build_universal_modal_fix_bundle.sh after editing modules.
 */

/* ===== Module: 00-universal-modal-fix-core.js ===== */

/**
 * 🛡️ UNIVERSAL MODAL CLOSE FIXER
 * Ensures ALL modals in the application can be closed via:
 * - X button (close button)
 * - Backdrop click (clicking outside modal)
 * - ESC key
 * 
 * This script auto-detects and fixes modal close functionality issues
 * Works with both modern-modals.js and custom inline modals
 */

(function () {
    'use strict';

    console.log('🛡️ Universal Modal Close Fixer initialized');

    // ============================================
    // 1. FIX MODERN MODALS (.modern-modal-overlay)
    // ============================================
    function fixModernModals() {
        // Use event delegation on document for all modern modals
        document.addEventListener('click', function (e) {
            // Find if click is inside a modern modal overlay
            const overlay = e.target.closest('.modern-modal-overlay');

            if (!overlay || !overlay.classList.contains('active')) return;

            // Check if clicked on close button
            const closeBtn = e.target.closest('.modern-modal-close');
            if (closeBtn) {
                console.log('🔘 Close button clicked');
                e.preventDefault();
                e.stopPropagation();
                overlay.classList.remove('active');
                setTimeout(() => overlay.remove(), 300);
                return;
            }

            // Check if clicked on action button with data-action
            const actionBtn = e.target.closest('[data-action]');
            if (actionBtn) {
                const action = actionBtn.dataset.action;
                if (action === 'close' || action === 'cancel') {
                    console.log(`🔘 Action button clicked: ${action}`);
                    e.preventDefault();
                    e.stopPropagation();
                    overlay.classList.remove('active');
                    setTimeout(() => overlay.remove(), 300);
                    return;
                }
            }

            // Check if clicked on backdrop (overlay itself, not modal content)
            if (e.target === overlay) {
                console.log('🖱️ Backdrop clicked');
                e.preventDefault();
                e.stopPropagation();
                overlay.classList.remove('active');
                setTimeout(() => overlay.remove(), 300);
                return;
            }
        }, true); // Use capture phase

        console.log('✅ Modern modals close handler attached');
    }

    // ============================================
    // 2. FIX CUSTOM CONFIRM MODALS (.confirm-modal-overlay)
    // ============================================
    function fixConfirmModals() {
        document.addEventListener('click', function (e) {
            const overlay = e.target.closest('.confirm-modal-overlay');

            if (!overlay || overlay.style.display === 'none') return;

            // Check for cancel button
            const cancelBtn = e.target.closest('.btn-confirm-cancel, #confirmCancelBtn');
            if (cancelBtn) {
                console.log('🔘 Confirm cancel button clicked');
                e.preventDefault();
                e.stopPropagation();
                overlay.style.display = 'none';
                overlay.classList.add('closing');
                setTimeout(() => {
                    overlay.classList.remove('closing');
                }, 300);
                return;
            }

            // Check for close button (X)
            const closeBtn = e.target.closest('.modal-close, [data-dismiss="modal"]');
            if (closeBtn) {
                console.log('🔘 Modal close button clicked');
                e.preventDefault();
                e.stopPropagation();
                overlay.style.display = 'none';
                return;
            }

            // Backdrop click
            if (e.target === overlay || e.target.classList.contains('confirm-modal-overlay')) {
                console.log('🖱️ Confirm modal backdrop clicked');
                e.preventDefault();
                e.stopPropagation();
                overlay.style.display = 'none';
                overlay.classList.add('closing');
                setTimeout(() => {
                    overlay.classList.remove('closing');
                }, 300);
                return;
            }
        }, true);

        console.log('✅ Confirm modals close handler attached');
    }

    // ============================================
    // 3. FIX STANDARD MODAL OVERLAYS (.modal-overlay)
    // ============================================
    function fixStandardModals() {
        document.addEventListener('click', function (e) {
            const overlay = e.target.closest('.modal-overlay');

            if (!overlay) return;

            // Check for close button
            const closeBtn = e.target.closest('.modal-close, [onclick*="closeModal"]');
            if (closeBtn) {
                console.log('🔘 Standard modal close button clicked');
                e.preventDefault();
                e.stopPropagation();
                // FIX: Remove active class and clear inline styles
                overlay.classList.remove('active');
                overlay.style.display = '';
                overlay.style.visibility = '';
                return;
            }

            // Backdrop click (clicked on overlay, not on .modal)
            if (e.target === overlay || (e.target.classList.contains('modal-overlay') && !e.target.closest('.modal'))) {
                console.log('🖱️ Standard modal backdrop clicked');
                e.preventDefault();
                e.stopPropagation();
                // FIX: Remove active class and clear inline styles
                overlay.classList.remove('active');
                overlay.style.display = '';
                overlay.style.visibility = '';
                return;
            }
        }, true);

        console.log('✅ Standard modals close handler attached');
    }

    // ============================================
    // 4. ESC KEY HANDLER (Global)
    // ============================================
    function setupEscapeKey() {
        document.addEventListener('keydown', function (e) {
            if (e.key !== 'Escape') return;

            // Find any visible modal
            const modernModal = document.querySelector('.modern-modal-overlay.active');
            if (modernModal) {
                console.log('⌨️ ESC pressed - closing modern modal');
                modernModal.classList.remove('active');
                setTimeout(() => modernModal.remove(), 300);
                return;
            }

            const confirmModal = document.querySelector('.confirm-modal-overlay[style*="display: block"], .confirm-modal-overlay:not([style*="display: none"])');
            if (confirmModal && confirmModal.style.display !== 'none') {
                console.log('⌨️ ESC pressed - closing confirm modal');
                confirmModal.style.display = 'none';
                return;
            }

            const standardModal = document.querySelector('.modal-overlay[style*="display: block"], .modal-overlay.active');
            if (standardModal && (standardModal.style.display !== 'none' || standardModal.classList.contains('active'))) {
                console.log('⌨️ ESC pressed - closing standard modal');
                // FIX: Remove active class and clear inline styles
                standardModal.classList.remove('active');
                standardModal.style.display = '';
                standardModal.style.visibility = '';
                return;
            }
        });

        console.log('✅ ESC key handler attached');
    }

    // ============================================
    // 5. FORCE Z-INDEX FIX FOR ALL MODALS
    // ============================================
    function forceZIndexFix() {
        const style = document.createElement('style');
        style.id = 'universal-modal-fix-styles';
        style.textContent = `
            /* Force z-index and pointer-events for all modal types */
            .modern-modal-overlay,
            .confirm-modal-overlay,
            .modal-overlay {
                z-index: 999999 !important;
                pointer-events: auto !important;
            }
            
            .modern-modal-overlay.active,
            .confirm-modal-overlay[style*="display: block"],
            .modal-overlay[style*="display: block"] {
                pointer-events: auto !important;
            }
            
            /* Ensure all close buttons are clickable */
            .modern-modal-close,
            .modal-close,
            .btn-confirm-cancel,
            .btn-confirm,
            [data-action="close"],
            [data-action="cancel"],
            [data-dismiss="modal"],
            button[onclick*="closeModal"],
            button[onclick*="close"] {
                pointer-events: auto !important;
                cursor: pointer !important;
                z-index: 10 !important;
                position: relative;
            }
            
            /* Ensure modal content doesn't block clicks on overlay */
            .modern-modal,
            .confirm-modal,
            .modal {
                pointer-events: auto !important;
                cursor: default;
            }
        `;

        // Remove existing style if present
        const existingStyle = document.getElementById('universal-modal-fix-styles');
        if (existingStyle) {
            existingStyle.remove();
        }

        document.head.appendChild(style);
        console.log('✅ Z-index and pointer-events styles injected');
    }

    // ============================================
    // INITIALIZE ALL FIXES
    // ============================================
    function initialize() {
        // Wait for DOM to be ready
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', initialize);
            return;
        }

        try {
            forceZIndexFix();
            fixModernModals();
            fixConfirmModals();
            fixStandardModals();
            setupEscapeKey();

            console.log('✅ Universal Modal Close Fixer - ALL SYSTEMS OPERATIONAL');
            console.log('📋 All modals are now closeable via:');
            console.log('   • X button (close button)');
            console.log('   • Backdrop click');
            console.log('   • ESC key');
        } catch (error) {
            console.error('❌ Error initializing modal fix:', error);
        }
    }

    // Start initialization
    initialize();

})();


/* ===== Module: 10-universal-modal-fix-debug.js ===== */

// Make functions available globally for debugging
window.debugModals = function () {
    console.log('🔍 Active modals:');
    console.log('Modern modals:', document.querySelectorAll('.modern-modal-overlay.active'));
    console.log('Confirm modals:', document.querySelectorAll('.confirm-modal-overlay[style*="display: block"]'));
    console.log('Standard modals:', document.querySelectorAll('.modal-overlay[style*="display: block"]'));
};
