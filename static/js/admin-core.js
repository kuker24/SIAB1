/**
 * AUTO-GENERATED FILE.
 * Source modules: static/js/admin-core/modules/*.js
 * Use scripts/build_admin_core_bundle.sh after editing modules.
 */

/* ===== Module: 00-admin-core-object.js ===== */

/**
 * Admin Core Logic
 * Handles Sidebar UI, Mobile Navigation, Role Visibility, and Auth Checks
 * Replaces: sidebar-loader.js, mobile-nav.js, header-user.js (partial)
 */

const AdminCore = {
    user: null,
    sidebar: null,
    overlay: null,

    init() {
        console.log('🚀 AdminCore initializing...');

        // 1. Check Auth & Load User
        if (!window.auth) {
            console.error('Auth module not found!');
            return;
        }

        this.user = window.auth.getUser();
        if (!this.user) {
            // Let specific pages handle redirect if needed,
            // but generally we want to know who is logged in
        }

        // 2. Cache DOM Elements
        this.sidebar = document.getElementById('main-sidebar');

        // 3. Setup UI
        this.loadDependencies();
        this.setupRoleVisibility();
        this.setupActiveState();
        this.setupMobileNav();
        this.setupLogout();

        console.log('✅ AdminCore initialized');
    },

    loadDependencies() {
        // Ensure custom-confirm.js is loaded for unified logout UI
        if (!document.querySelector('script[src="/static/js/custom-confirm.js"]')) {
            const script = document.createElement('script');
            script.src = '/static/js/custom-confirm.js';
            document.head.appendChild(script);
        }
    },

    /**
     * Show/Hide menu items based on user role
     */
    setupRoleVisibility() {
        if (!this.user) return;

        const role = this.user.role; // 'developer' | 'admin' | 'teacher'
        const isAdminScope = role === 'admin' || role === 'developer';

        // Items marked .admin-only are hidden for teachers
        if (!isAdminScope) {
            document.querySelectorAll('.admin-only').forEach(el => {
                el.style.display = 'none';
            });
        }

        // Items marked .teacher-only are visible for both (usually)
        // If we had student role accessing this layout, we'd hide them too
    },

    /**
     * Highlight current menu item based on URL
     */
    setupActiveState() {
        const path = window.location.pathname;
        let currentPage = path.split('/').pop().replace('.html', '');
        if (!currentPage) currentPage = 'dashboard';

        // Map tricky pages to sidebar keys
        const pageMap = {
            'exam-templates': 'exam-templates',
            'grading': 'grading',
            'analytics': 'analytics',
            'exam-analytics': 'exam-analytics',
            'system-monitor': 'system-monitor',
            'monitoring': 'monitoring',
            'violations': 'violations',
            'account-security': 'account-security',
            'seb-builder': 'seb-builder',
            'activity': 'activity',
            'bulk-users': 'users' // Map bulk-users to users menu
        };

        const targetKey = pageMap[currentPage] || currentPage;

        // Find link
        const link = document.querySelector(`.nav-link[data-page="${targetKey}"]`) ||
                     document.querySelector(`.nav-link[href*="${currentPage}"]`);

        if (link) {
            link.classList.add('active');

            // Open parent submenu
            const parentSubmenu = link.closest('.has-submenu');
            if (parentSubmenu) {
                parentSubmenu.classList.add('open');
                const toggle = parentSubmenu.querySelector('.submenu-toggle');
                if (toggle) toggle.classList.add('active');
            }
        }

        // Setup Submenu Toggles
        document.querySelectorAll('.submenu-toggle').forEach(toggle => {
            toggle.addEventListener('click', (e) => {
                e.preventDefault();
                const parent = toggle.closest('.has-submenu');
                parent.classList.toggle('open');
            });
        });
    },

    /**
     * Modern Mobile Navigation
     */
    setupMobileNav() {
        const toggleBtn = document.getElementById('mobile-menu-toggle');
        if (!toggleBtn || !this.sidebar) return;

        // Create Overlay
        this.overlay = document.createElement('div');
        this.overlay.className = 'mobile-overlay';
        document.body.appendChild(this.overlay);

        // Open/Close Logic
        const toggleMenu = () => {
            const isOpen = this.sidebar.classList.contains('mobile-open');
            if (isOpen) {
                this.closeMenu();
            } else {
                this.openMenu();
            }
        };

        toggleBtn.addEventListener('click', toggleMenu);
        this.overlay.addEventListener('click', () => this.closeMenu());

        // Close on link click (mobile only)
        this.sidebar.querySelectorAll('a:not(.submenu-toggle)').forEach(link => {
            link.addEventListener('click', () => {
                if (window.innerWidth < 1024) {
                    this.closeMenu();
                }
            });
        });
    },

    openMenu() {
        this.sidebar.classList.add('mobile-open');
        this.overlay.classList.add('active');
        document.body.style.overflow = 'hidden'; // Lock scroll

        const btn = document.getElementById('mobile-menu-toggle');
        if(btn) btn.classList.add('active');
    },

    closeMenu() {
        this.sidebar.classList.remove('mobile-open');
        this.overlay.classList.remove('active');
        document.body.style.overflow = ''; // Unlock scroll

        const btn = document.getElementById('mobile-menu-toggle');
        if(btn) btn.classList.remove('active');
    },

    /**
     * Handle Logout
     */
    setupLogout() {
        const btn = document.getElementById('logout-btn');
        if (btn) {
            btn.onclick = (e) => {
                e.preventDefault();
                if (window.auth) window.auth.confirmLogout();
            };
        }
    }
};

/* ===== Module: 10-admin-core-bootstrap.js ===== */

// Auto-init on load
document.addEventListener('DOMContentLoaded', () => {
    AdminCore.init();
});
