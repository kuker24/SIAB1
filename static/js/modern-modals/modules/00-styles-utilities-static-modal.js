/**
 * 🎨 MODERN MODAL LIBRARY v2.1 - STANDALONE (No Bootstrap Required)
 * Universal replacements for confirm(), alert(), prompt()
 * Premium glassmorphism design, smooth animations
 * 
 * Usage:
 *   await showConfirm('Delete this item?')
 *   await showAlert('Success!', 'success')
 *   const input = await showPrompt('Enter name:', 'John Doe')
 */

// ============================================
// MODAL STYLES (Injected once on load)
// ============================================
(function injectModalStyles() {
    if (document.getElementById('modern-modal-styles')) return;

    const styles = document.createElement('style');
    styles.id = 'modern-modal-styles';
    styles.textContent = `
        /* Modal Overlay */
        .modern-modal-overlay {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(15, 23, 42, 0.75);
            backdrop-filter: blur(8px);
            -webkit-backdrop-filter: blur(8px);
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 999999 !important;
            opacity: 0;
            visibility: hidden;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            pointer-events: auto !important;
        }
        
        .modern-modal-overlay.active {
            opacity: 1;
            visibility: visible;
        }
        
        /* Modal Container */
        .modern-modal {
            background: linear-gradient(145deg, rgba(30, 41, 59, 0.98) 0%, rgba(15, 23, 42, 0.98) 100%);
            border: 1px solid rgba(148, 163, 184, 0.15);
            border-radius: 20px;
            box-shadow: 
                0 25px 50px -12px rgba(0, 0, 0, 0.5),
                0 0 0 1px rgba(255, 255, 255, 0.05) inset,
                0 -1px 0 0 rgba(255, 255, 255, 0.1) inset;
            min-width: 380px;
            max-width: 480px;
            width: 90%;
            transform: scale(0.95) translateY(10px);
            transition: all 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
            overflow: hidden;
            pointer-events: auto !important;
        }
        
        .modern-modal-overlay.active .modern-modal {
            transform: scale(1) translateY(0);
        }
        
        /* Modal Header */
        .modern-modal-header {
            padding: 24px 24px 16px;
            display: flex;
            align-items: flex-start;
            justify-content: space-between;
            gap: 16px;
        }
        
        .modern-modal-title {
            font-size: 1.125rem;
            font-weight: 700;
            color: #f1f5f9;
            display: flex;
            align-items: center;
            gap: 14px;
            margin: 0;
            line-height: 1.4;
        }
        
        .modern-modal-title .icon {
            font-size: 1.5rem;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 44px;
            height: 44px;
            background: rgba(255, 255, 255, 0.08);
            border-radius: 12px;
            border: 1px solid rgba(255, 255, 255, 0.08);
            flex-shrink: 0;
        }
        
        .modern-modal-close {
            background: rgba(255, 255, 255, 0.08);
            border: 1px solid rgba(255, 255, 255, 0.08);
            color: #94a3b8;
            width: 36px;
            height: 36px;
            border-radius: 10px;
            cursor: pointer !important;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all 0.2s;
            font-size: 20px;
            flex-shrink: 0;
            pointer-events: auto !important;
        }
        
        .modern-modal-close:hover {
            background: rgba(239, 68, 68, 0.2);
            border-color: rgba(239, 68, 68, 0.3);
            color: #f87171;
            transform: rotate(90deg);
        }
        
        /* Modal Body */
        .modern-modal-body {
            padding: 8px 24px 24px;
            color: #cbd5e1;
            font-size: 0.95rem;
            line-height: 1.7;
        }
        
        .modern-modal-body strong {
            color: #fb923c;
            font-weight: 600;
        }
        
        /* Modal Footer */
        .modern-modal-footer {
            padding: 16px 24px 24px;
            display: flex;
            justify-content: flex-end;
            gap: 12px;
            background: rgba(0, 0, 0, 0.15);
            border-top: 1px solid rgba(255, 255, 255, 0.05);
        }
        
        /* Buttons */
        .modern-modal-btn {
            padding: 12px 24px;
            border-radius: 12px;
            border: none;
            font-size: 0.9rem;
            font-weight: 600;
            cursor: pointer !important;
            display: inline-flex;
            align-items: center;
            gap: 8px;
            transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
            pointer-events: auto !important;
            position: relative;
        }
        
        .modern-modal-btn:active {
            transform: scale(0.97);
        }
        
        .modern-modal-btn-secondary {
            background: rgba(71, 85, 105, 0.5);
            color: #cbd5e1;
            border: 1px solid rgba(148, 163, 184, 0.2);
        }
        
        .modern-modal-btn-secondary:hover {
            background: rgba(71, 85, 105, 0.7);
            color: #f1f5f9;
        }
        
        .modern-modal-btn-primary {
            background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
            color: #fff;
            box-shadow: 0 4px 14px rgba(99, 102, 241, 0.4);
        }
        
        .modern-modal-btn-primary:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(99, 102, 241, 0.5);
        }
        
        .modern-modal-btn-danger {
            background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
            color: #fff;
            box-shadow: 0 4px 14px rgba(239, 68, 68, 0.4);
        }
        
        .modern-modal-btn-danger:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(239, 68, 68, 0.5);
        }
        
        .modern-modal-btn-success {
            background: linear-gradient(135deg, #10b981 0%, #059669 100%);
            color: #fff;
            box-shadow: 0 4px 14px rgba(16, 185, 129, 0.4);
        }
        
        .modern-modal-btn-success:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(16, 185, 129, 0.5);
        }
        
        .modern-modal-btn-warning {
            background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%);
            color: #fff;
            box-shadow: 0 4px 14px rgba(245, 158, 11, 0.4);
        }
        
        .modern-modal-btn-warning:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(245, 158, 11, 0.5);
        }
        
        /* Input field */
        .modern-modal-input {
            width: 100%;
            padding: 14px 18px;
            background: rgba(15, 23, 42, 0.6);
            border: 1px solid rgba(148, 163, 184, 0.2);
            border-radius: 12px;
            color: #f1f5f9;
            font-size: 0.95rem;
            margin-top: 16px;
            transition: all 0.2s;
        }
        
        .modern-modal-input:focus {
            outline: none;
            border-color: #6366f1;
            box-shadow: 0 0 0 4px rgba(99, 102, 241, 0.15);
            background: rgba(15, 23, 42, 0.8);
        }
        
        .modern-modal-input::placeholder {
            color: rgba(148, 163, 184, 0.6);
        }
        
        /* Type variants - Header backgrounds */
        .modern-modal.type-danger .modern-modal-header {
            background: linear-gradient(135deg, rgba(239, 68, 68, 0.15) 0%, rgba(239, 68, 68, 0.02) 100%);
        }
        
        .modern-modal.type-danger .modern-modal-title .icon {
            background: rgba(239, 68, 68, 0.2);
            border-color: rgba(239, 68, 68, 0.3);
        }
        
        .modern-modal.type-warning .modern-modal-header {
            background: linear-gradient(135deg, rgba(245, 158, 11, 0.15) 0%, rgba(245, 158, 11, 0.02) 100%);
        }
        
        .modern-modal.type-warning .modern-modal-title .icon {
            background: rgba(245, 158, 11, 0.2);
            border-color: rgba(245, 158, 11, 0.3);
        }
        
        .modern-modal.type-success .modern-modal-header {
            background: linear-gradient(135deg, rgba(16, 185, 129, 0.15) 0%, rgba(16, 185, 129, 0.02) 100%);
        }
        
        .modern-modal.type-success .modern-modal-title .icon {
            background: rgba(16, 185, 129, 0.2);
            border-color: rgba(16, 185, 129, 0.3);
        }
        
        .modern-modal.type-info .modern-modal-header {
            background: linear-gradient(135deg, rgba(59, 130, 246, 0.15) 0%, rgba(59, 130, 246, 0.02) 100%);
        }
        
        .modern-modal.type-info .modern-modal-title .icon {
            background: rgba(59, 130, 246, 0.2);
            border-color: rgba(59, 130, 246, 0.3);
        }
    `;
    document.head.appendChild(styles);
})();

// ============================================
// UTILITY FUNCTIONS
// ============================================
function createModal(content, type = 'info') {
    const overlay = document.createElement('div');
    overlay.className = 'modern-modal-overlay';
    overlay.innerHTML = `<div class="modern-modal type-${type}">${content}</div>`;
    document.body.appendChild(overlay);

    // Force reflow then add active class for animation
    requestAnimationFrame(() => {
        overlay.classList.add('active');
    });

    return overlay;
}

function closeModal(overlayOrId, callback) {
    let overlay = overlayOrId;
    if (typeof overlayOrId === 'string') {
        overlay = document.getElementById(overlayOrId);
    }

    if (!overlay) return;

    // Check if it's a static modal (exists in DOM initially) or dynamic
    const isStatic = overlay.id && document.getElementById(overlay.id) === overlay && !overlay.classList.contains('modern-modal-overlay');

    overlay.classList.remove('active');

    if (isStatic) {
        // Static modal: Just hide, don't remove
        setTimeout(() => {
            overlay.style.visibility = 'hidden';
            overlay.style.display = '';
            if (callback) callback();
        }, 300);
    } else {
        // Dynamic modal: Remove from DOM
        setTimeout(() => {
            overlay.remove();
            if (callback) callback();
        }, 300);
    }
}

// ============================================
// 5. STATIC MODAL SUPPORT (Legacy/HTML Modals)
// ============================================
function openModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.style.visibility = '';
        modal.style.display = '';
        modal.classList.add('active');
    } else {
        console.error(`Modal with ID '${modalId}' not found.`);
    }
}

// ============================================
