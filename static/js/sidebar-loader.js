/**
 * AUTO-GENERATED FILE.
 * Source modules: static/js/sidebar-loader/modules/*.js
 * Use scripts/build_sidebar_loader_bundle.sh after editing modules.
 */

/* ===== Module: 00-sidebar-loader-core.js ===== */

/**
 * Sidebar Loader Module
 * Dynamically loads the sidebar component into pages
 */

class SidebarLoader {
    static async load(containerId = 'sidebar-container') {
        const container = document.getElementById(containerId);
        if (!container) {
            console.error('[SIDEBAR-LOADER] Container not found:', containerId);
            return;
        }

        console.log('%c[SIDEBAR-LOADER] 🚀 Starting sidebar load', 'color: #673AB7; font-weight: bold');

        try {
            // Stable versioned cache: avoids a fresh sidebar network request on every admin page.
            const componentVersion = '20260430-perf1';
            const cacheKey = `sidebar_html_${componentVersion}`;
            let html = null;

            try {
                html = sessionStorage.getItem(cacheKey);
            } catch (_) {
                html = null;
            }

            // Ensure custom-confirm.js is loaded for unified logout UI
            SidebarLoader.loadScript('/static/js/custom-confirm.js');

            if (!html) {
                const response = await fetch(`/static/components/sidebar.html?v=${componentVersion}`, {
                    cache: 'force-cache'
                });
                if (!response.ok) {
                    console.error('[SIDEBAR-LOADER] ❌ Fetch failed with status:', response.status);
                    SidebarLoader.loadFallback(container);
                    return;
                }
                html = await response.text();
                try {
                    sessionStorage.setItem(cacheKey, html);
                } catch (_) {
                    // Storage can be unavailable in locked-down WebViews; the fetch cache is still useful.
                }
            }

            container.innerHTML = html;

            // Execute inline scripts
            const scripts = container.querySelectorAll('script');
            console.log(`[SIDEBAR-LOADER] Found ${scripts.length} inline scripts to execute`);
            scripts.forEach((script, index) => {
                const newScript = document.createElement('script');
                newScript.textContent = script.textContent;
                document.body.appendChild(newScript);
                console.log(`[SIDEBAR-LOADER] Executed script ${index + 1}/${scripts.length}`);
                script.remove();
            });

            console.log('%c[SIDEBAR-LOADER] ✅ Sidebar loaded successfully', 'color: #4CAF50; font-weight: bold');
            // REMOVED: SidebarLoader.initSidebar();
            // Reason: sidebar.html already contains inline script that initializes the sidebar.
            // Calling it again here causes double event listeners on toggles.

            // Hide admin-only elements for teachers
            SidebarLoader.hideAdminOnlyElements();
        } catch (error) {
            console.error('[SIDEBAR-LOADER] ❌ Error loading sidebar:', error);
            SidebarLoader.loadFallback(container);
        }
    }

    static loadFallback(container) {
        // Ensure custom-confirm.js is loaded for unified logout UI in fallback mode too
        SidebarLoader.loadScript('/static/js/custom-confirm.js');

        console.warn('%c[SIDEBAR-LOADER] ⚠️ Loading FALLBACK sidebar', 'color: #FF9800; font-weight: bold; font-size: 14px');
        const user = JSON.parse(localStorage.getItem('user') || 'null');
        console.log('[SIDEBAR-FALLBACK] User role:', user?.role); // Debug log

        const isAdmin = user && (user.role === 'admin' || user.role === 'developer');
        const isTeacher = user && (user.role === 'admin' || user.role === 'developer' || user.role === 'teacher');

        container.innerHTML = `
        <aside class="sidebar" id="main-sidebar">
            <div class="sidebar-header">
                <i class="fas fa-graduation-cap"></i>
                <h1>Ujian Online</h1>
            </div>

            <ul class="nav-menu" id="nav-menu">
                <!-- 1. Dashboard - All Roles -->
                <li class="nav-item">
                    <a href="/admin/dashboard.html" class="nav-link" data-page="dashboard">
                        <i class="fas fa-gauge-high"></i>
                        <span>Dashboard</span>
                    </a>
                </li>

                <!-- 2. Ujian & Soal - Admin & Teacher -->
                ${isTeacher ? `
                <li class="nav-item has-submenu">
                    <a href="#" class="nav-link submenu-toggle" data-page="exams">
                        <i class="fas fa-folder-open"></i>
                        <span>Ujian & Soal</span>
                        <i class="fas fa-chevron-down submenu-arrow"></i>
                    </a>
                    <ul class="submenu">
                        <li><a href="/admin/exams.html" data-page="exams"><i class="fas fa-list-check"></i> Manajemen Ujian</a></li>
                        <li><a href="/admin/exam-templates.html" data-page="exam-templates"><i class="fas fa-file-circle-plus"></i> Template Ujian</a></li>
                    </ul>
                </li>
                ` : ''}

                <!-- 3. Hasil & Analitik - Admin & Teacher -->
                ${isTeacher ? `
                <li class="nav-item has-submenu">
                    <a href="#" class="nav-link submenu-toggle" data-page="results">
                        <i class="fas fa-chart-column"></i>
                        <span>Hasil & Analitik</span>
                        <i class="fas fa-chevron-down submenu-arrow"></i>
                    </a>
                    <ul class="submenu">
                        <li><a href="/admin/results.html" data-page="results"><i class="fas fa-square-poll-vertical"></i> Semua Hasil</a></li>
                        <li><a href="/admin/grading.html" data-page="grading"><i class="fas fa-pen-to-square"></i> Penilaian Manual</a></li>
                        ${isAdmin ? '<li><a href="/admin/analytics.html" data-page="analytics"><i class="fas fa-chart-pie"></i> Statistik & Laporan</a></li>' : ''}
                        <li><a href="/admin/exam-analytics.html" data-page="exam-analytics"><i class="fas fa-magnifying-glass-chart"></i> Analitik Ujian</a></li>
                    </ul>
                </li>
                ` : ''}

                <!-- 4. Pengguna & Monitoring - Admin Only -->
                ${isTeacher ? `
                <li class="nav-item has-submenu">
                    <a href="#" class="nav-link submenu-toggle" data-page="users">
                        <i class="fas fa-users-gear"></i>
                        <span>Pengguna & Monitor</span>
                        <i class="fas fa-chevron-down submenu-arrow"></i>
                    </a>
                    <ul class="submenu">
                        ${isAdmin ? '<li><a href="/admin/users.html" data-page="users"><i class="fas fa-users"></i> Manajemen User</a></li>' : ''}
                        ${isAdmin ? '<li><a href="/admin/system-monitor.html" data-page="system-monitor"><i class="fas fa-server"></i> Monitor Sistem</a></li>' : ''}
                        <li><a href="/admin/monitoring.html" data-page="monitoring"><i class="fas fa-computer"></i> Sesi Aktif</a></li>
                        ${isAdmin ? '<li><a href="/admin/violations.html" data-page="violations"><i class="fas fa-triangle-exclamation"></i> Pelanggaran</a></li>' : ''}
                    </ul>
                </li>
                ` : ''}

                <!-- 5. Pengaturan - Admin Only -->
                ${isAdmin ? `
                <li class="nav-item has-submenu" id="settings-menu-container">
                    <a href="#" class="nav-link submenu-toggle" data-page="settings">
                        <i class="fas fa-gears"></i>
                        <span>Pengaturan</span>
                        <i class="fas fa-chevron-down submenu-arrow"></i>
                    </a>
                    <ul class="submenu">
                        <li id="settings-general-item" style="display: none;"><a href="/admin/settings.html" data-page="settings"><i class="fas fa-sliders"></i> Umum</a></li>
                        <li><a href="/admin/account-security.html" data-page="account-security"><i class="fas fa-user-shield"></i> Keamanan Akun</a></li>
                        <li><a href="/admin/seb-builder.html" data-page="seb-builder"><i class="fas fa-screwdriver-wrench"></i> SEB Legacy PC</a></li>
                        <li><a href="/admin/activity.html" data-page="activity"><i class="fas fa-clock-rotate-left"></i> Log Aktivitas</a></li>
                    </ul>
                </li>
                ` : ''}

                <!-- 6. Logout -->
                <!-- Moved to footer -->
            </ul>

            <div class="sidebar-footer">
                <a href="#" class="nav-link logout-link" id="logout-btn" onclick="auth.confirmLogout(); return false;">
                    <i class="fas fa-right-from-bracket"></i>
                    <span>Logout</span>
                </a>
            </div>
        </aside>
        <button class="mobile-menu-toggle" id="mobile-menu-toggle">
            <i class="fas fa-bars"></i>
        </button>
        `;

        SidebarLoader.initSidebar();
        SidebarLoader.hideAdminOnlyElements();
    }

    static hideAdminOnlyElements() {
        const user = JSON.parse(localStorage.getItem('user') || 'null');
        if (!user) return;

        const isPengawas = user.role === 'gurupengawas';
        if (isPengawas) {
            const removePages = ['dashboard', 'exam-templates', 'results', 'grading', 'analytics', 'exam-analytics', 'settings', 'seb-builder', 'activity'];
            removePages.forEach((page) => {
                document.querySelector(`a[data-page="${page}"]`)?.closest('.nav-item')?.remove();
                document.querySelector(`a[data-page="${page}"]`)?.closest('li')?.remove();
            });

            const usersToggle = document.querySelector('.nav-link.submenu-toggle[data-page="users"]');
            const usersMenuItem = usersToggle?.closest('.nav-item');
            if (usersToggle && usersMenuItem) {
                const iconEl = usersToggle.querySelector('i');
                const textEl = usersToggle.querySelector('span');
                if (iconEl) iconEl.className = 'fas fa-shield-halved';
                if (textEl) textEl.textContent = 'Monitor Ujian';
                const submenu = usersMenuItem.querySelector('.submenu');
                if (submenu) {
                    submenu.innerHTML = `
                        <li><a href="/admin/exams.html" data-page="exams"><i class="fas fa-list-check"></i> Manajemen Ujian</a></li>
                        <li><a href="/admin/monitoring.html" data-page="monitoring"><i class="fas fa-computer"></i> Sesi Aktif</a></li>
                        <li><a href="/admin/results.html" data-page="results"><i class="fas fa-square-poll-vertical"></i> Semua Hasil</a></li>
                        <li><a href="/admin/violations.html" data-page="violations"><i class="fas fa-triangle-exclamation"></i> Pelanggaran</a></li>
                        <li><a href="/admin/account-security.html" data-page="account-security"><i class="fas fa-user-shield"></i> Keamanan Akun</a></li>
                    `;
                }
                usersMenuItem.classList.add('open');
            }
        }

        if (!user || (user.role !== 'admin' && user.role !== 'developer')) {
            console.log('[SIDEBAR-LOADER] Hiding admin-only elements for non-admin user');
            document.querySelectorAll('.admin-only').forEach(el => {
                el.style.display = 'none';
            });
        }
    }

    static loadScript(src) {
        if (document.querySelector(`script[src="${src}"]`)) return;
        const script = document.createElement('script');
        script.src = src;
        document.head.appendChild(script);
        console.log(`[SIDEBAR-LOADER] Injected script: ${src}`);
    }

    static initSidebar() {
        console.log('%c[SIDEBAR-FALLBACK] 📌 Initializing fallback sidebar', 'color: #FF6F00; font-weight: bold');

        // Prevent double initialization in fallback mode too
        if (window.sidebarInitialized) {
            console.warn('%c[SIDEBAR-FALLBACK] ⚠️ Already initialized, ABORTING', 'color: #FF5722; font-weight: bold');
            return;
        }
        window.sidebarInitialized = true;

        const sidebar = document.getElementById('main-sidebar');
        const mobileToggle = document.getElementById('mobile-menu-toggle');
        const currentPath = window.location.pathname;
        const submenuToggles = document.querySelectorAll('.submenu-toggle');

        console.log(`[SIDEBAR-FALLBACK] Found ${submenuToggles.length} submenu toggles`);

        // Mobile toggle
        if (mobileToggle) {
            mobileToggle.addEventListener('click', () => {
                sidebar.classList.toggle('active');
            });
        }

        // Close sidebar on outside click (mobile)
        const outsideClickHandler = (e) => {
            if (window.innerWidth <= 768 && sidebar) {
                if (!sidebar.contains(e.target) && !mobileToggle?.contains(e.target)) {
                    sidebar.classList.remove('active');
                }
            }
        };
        document.addEventListener('click', outsideClickHandler);

        // Submenu toggles
        console.log(`%c[SIDEBAR-FALLBACK] 📌 Attaching ${submenuToggles.length} submenu toggle listeners`, 'color: #E91E63; font-weight: bold');
        submenuToggles.forEach((toggle, index) => {
            // Mark to prevent double attachment
            if (toggle.dataset.listenerAttached) {
                console.warn(`[SIDEBAR-FALLBACK] ⚠️ Listener already attached to toggle ${index}, SKIPPING`);
                return;
            }
            toggle.dataset.listenerAttached = 'true';

            toggle.addEventListener('click', (e) => {
                console.log(`%c[SIDEBAR-FALLBACK] 🖱️ Click on toggle ${index}`, 'color: #00BCD4; font-weight: bold');
                e.preventDefault();
                e.stopPropagation(); // Stop event bubbling
                const parent = toggle.parentElement;

                // ACCORDION BEHAVIOR REMOVED COMPLETELY

                const wasOpen = parent.classList.contains('open');
                parent.classList.toggle('open');
                const isNowOpen = parent.classList.contains('open');
                console.log(`%c[SIDEBAR-FALLBACK] 🔄 Toggle: ${wasOpen ? 'CLOSING' : 'OPENING'} → Now: ${isNowOpen ? 'OPEN' : 'CLOSED'}`, 'color: #4CAF50; font-weight: bold');
            });
            console.log(`[SIDEBAR-FALLBACK] ✓ Listener attached to toggle ${index}`);
        });

        // Active state
        const currentPage = currentPath.split('/').pop().replace('.html', '') || 'dashboard';
        console.log('[SIDEBAR-FALLBACK] Current page:', currentPage);

        let activeFound = false;
        document.querySelectorAll('.nav-link[data-page]').forEach(link => {
            const page = link.getAttribute('data-page');
            // Use exact match to prevent false positives
            if (currentPage === page) {
                link.classList.add('active');
                activeFound = true;
                // Open parent submenu if exists
                const parentSubmenu = link.closest('.has-submenu');
                if (parentSubmenu) {
                    parentSubmenu.classList.add('open');
                    // FIX: Also highlight the parent toggle link to ensure visual consistency
                    const parentToggle = parentSubmenu.querySelector('.nav-link.submenu-toggle');
                    if (parentToggle) {
                        parentToggle.classList.add('active');
                    }
                }
            }
        });

        // Extra robustness for fallback
        if (!activeFound) {
            console.log('[SIDEBAR-FALLBACK] No exact match, attempting fallback map');
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
                'activity': 'activity'
            };

            const targetPage = pageMap[currentPage] || currentPage;
            const targetLink = document.querySelector(`a[data-page="${targetPage}"]`);

            if (targetLink) {
                targetLink.classList.add('active');
                const parent = targetLink.closest('.has-submenu');
                if (parent) {
                    parent.classList.add('open');
                    const parentToggle = parent.querySelector('.nav-link.submenu-toggle');
                    if (parentToggle) parentToggle.classList.add('active');
                }
            } else if (currentPage.startsWith('exam-')) {
                // Try prefix match for exams
                const examsToggle = document.querySelector('.nav-link[data-page="exams"]');
                if (examsToggle) {
                    const parent = examsToggle.closest('.has-submenu');
                    if (parent) parent.classList.add('open');
                }
            }
        }

        // Ensure logout button in fallback has event handler if rendered
        const logoutBtn = document.getElementById('logout-btn');
        if (logoutBtn && !logoutBtn.onclick) {
            logoutBtn.onclick = function () { auth.confirmLogout(); return false; };
        }
    }
}

// SECURITY LAYER: Handled by api.js
// (function initSecurityLayer() { ... })();

/* ===== Module: 10-sidebar-loader-bootstrap.js ===== */

// Auto-load when DOM ready
document.addEventListener('DOMContentLoaded', () => {
    SidebarLoader.load();
});
