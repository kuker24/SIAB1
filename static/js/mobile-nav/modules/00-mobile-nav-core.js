/**
 * Mobile Navigation Component
 * Hamburger menu with slide-in sidebar for mobile devices
 */

// Mobile Navigation State
const MobileNav = {
    isOpen: false,
    sidebar: null,
    overlay: null,
    hamburger: null,

    /**
     * Initialize mobile navigation
     */
    init() {
        this.sidebar = document.querySelector('.sidebar');
        this.createHamburger();
        this.createOverlay();
        this.setupListeners();
        this.checkViewport();

        console.log('📱 Mobile Navigation initialized');
    },

    /**
     * Create hamburger button - DISABLED
     * Mobile header removed - using mobile-menu-toggle from sidebar component
     */
    createHamburger() {
        // Hamburger creation disabled - using existing mobile-menu-toggle
        this.hamburger = document.getElementById('mobile-menu-toggle');
    },

    /**
     * Create overlay for mobile menu
     */
    createOverlay() {
        if (document.querySelector('.mobile-overlay')) return;

        const overlay = document.createElement('div');
        overlay.className = 'mobile-overlay';
        document.body.appendChild(overlay);
        this.overlay = overlay;
    },

    /**
     * Setup event listeners
     */
    setupListeners() {
        // Hamburger click
        if (this.hamburger) {
            this.hamburger.addEventListener('click', () => this.toggle());
        }

        // Overlay click to close
        if (this.overlay) {
            this.overlay.addEventListener('click', () => this.close());
        }

        // Escape key to close
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.isOpen) {
                this.close();
            }
        });

        // Window resize
        window.addEventListener('resize', () => this.checkViewport());

        // Close on navigation
        document.querySelectorAll('.sidebar a').forEach(link => {
            link.addEventListener('click', () => {
                if (window.innerWidth < 768) {
                    this.close();
                }
            });
        });
    },

    /**
     * Toggle menu
     */
    toggle() {
        if (this.isOpen) {
            this.close();
        } else {
            this.open();
        }
    },

    /**
     * Open mobile menu
     */
    open() {
        this.isOpen = true;

        if (this.sidebar) {
            this.sidebar.classList.add('mobile-open');
        }

        if (this.overlay) {
            this.overlay.classList.add('active');
        }

        if (this.hamburger) {
            this.hamburger.classList.add('active');
            this.hamburger.setAttribute('aria-expanded', 'true');
        }

        // Prevent body scroll
        document.body.style.overflow = 'hidden';
    },

    /**
     * Close mobile menu
     */
    close() {
        this.isOpen = false;

        if (this.sidebar) {
            this.sidebar.classList.remove('mobile-open');
        }

        if (this.overlay) {
            this.overlay.classList.remove('active');
        }

        if (this.hamburger) {
            this.hamburger.classList.remove('active');
            this.hamburger.setAttribute('aria-expanded', 'false');
        }

        // Restore body scroll
        document.body.style.overflow = '';
    },

    /**
     * Check viewport and adjust
     */
    checkViewport() {
        const width = window.innerWidth;

        // Hide hamburger on desktop
        if (this.hamburger) {
            if (width >= 768) {
                this.hamburger.style.display = 'none';
                this.close(); // Close if was open
            } else {
                this.hamburger.style.display = 'flex';
            }
        }

        // Hide overlay on desktop
        if (this.overlay) {
            if (width >= 768) {
                this.overlay.style.display = 'none';
            }
        }
    }
};
