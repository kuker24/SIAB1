/**
 * SEB Builder JavaScript
 * Handles PC and Android SEB Builder functionality
 */

// Global state
let currentPlatform = 'pc';
let templates = [];
let builds = [];

// ============================================================================
// PLATFORM SWITCHING
// ============================================================================

function switchPlatform(platform) {
    currentPlatform = platform;

    // Update button states
    document.querySelectorAll('.platform-btn').forEach(btn => {
        btn.classList.remove('active');
        if (btn.dataset.platform === platform) {
            btn.classList.add('active');
        }
    });

    // Update section visibility
    document.querySelectorAll('.builder-section').forEach(section => {
        section.classList.remove('active');
    });
    document.getElementById(`${platform}-builder`).classList.add('active');

    // Load appropriate data
    if (platform === 'pc') {
        loadTemplates();
        loadBuilds();
    }
}

// ============================================================================
// CARD COLLAPSING
// ============================================================================

function toggleCard(headerElement) {
    const card = headerElement.parentElement;
    card.classList.toggle('collapsed');
}

// ============================================================================
// PRESET LOADING
// ============================================================================

async function loadPreset(presetType) {
    try {
        // Show loading state on button
        const button = document.querySelector(`.preset-btn.${presetType}`);
        if (button) {
            button.style.opacity = '0.6';
            button.style.pointerEvents = 'none';
            const originalHTML = button.innerHTML;
            button.innerHTML = `
                <div class="icon"><i class="fas fa-spinner fa-spin"></i></div>
                <div class="label">Loading...</div>
                <div class="desc">Please wait</div>
            `;

            // Restore button after 5 seconds max
            setTimeout(() => {
                button.innerHTML = originalHTML;
                button.style.opacity = '1';
                button.style.pointerEvents = 'auto';
            }, 5000);
        }

        // Fetch preset from new endpoint
        const response = await fetch(`/api/v1/seb-builder/presets/${presetType}`, {
            credentials: 'include'  // Use session cookies for authentication
        });

        if (!response.ok) {
            throw new Error(`Failed to load preset: ${response.status}`);
        }

        const preset = await response.json();

        if (preset && preset.config_data) {
            applyConfigToForm(preset.config_data);
            showNotification(`✓ Loaded ${preset.name} preset`, 'success');

            // Restore button immediately on success
            if (button) {
                button.innerHTML = button.getAttribute('data-original-html') || button.innerHTML;
                button.style.opacity = '1';
                button.style.pointerEvents = 'auto';
            }
        } else {
            throw new Error('Preset data is invalid');
        }
    } catch (error) {
        console.error('Error loading preset:', error);

        // Try fallback to default values
        const fallbackConfigs = {
            'strict': {
                browserWindowAllowReload: false,
                allowBrowsingBackForward: false,
                enableBrowserWindowToolbar: false,
                enableZoomPage: false,
                allowScreenShot: false,
                enableAltTab: false,
                killExplorerShell: true,
                enableF12: false,
                monitorProcesses: true
            },
            'standard': {
                browserWindowAllowReload: true,
                allowBrowsingBackForward: false,
                enableBrowserWindowToolbar: true,
                enableZoomPage: true,
                allowScreenShot: false,
                enableAltTab: false,
                killExplorerShell: false,
                enableF12: false,
                monitorProcesses: true
            },
            'permissive': {
                browserWindowAllowReload: true,
                allowBrowsingBackForward: true,
                enableBrowserWindowToolbar: true,
                enableZoomPage: true,
                allowScreenShot: true,
                enableAltTab: true,
                killExplorerShell: false,
                enableF12: true,
                monitorProcesses: false
            }
        };

        if (fallbackConfigs[presetType]) {
            applyConfigToForm(fallbackConfigs[presetType]);
            showNotification(`⚠ Loaded ${presetType} preset (offline mode)`, 'info');
        } else {
            showNotification(`✗ Failed to load preset. Please try again.`, 'error');
        }
    }
}

function applyConfigToForm(config) {
    // Browser settings
    document.getElementById('allow-reload').checked = config.browserWindowAllowReload || false;
    document.getElementById('allow-back-forward').checked = config.allowBrowsingBackForward || false;
    document.getElementById('show-toolbar').checked = config.enableBrowserWindowToolbar || false;
    document.getElementById('enable-zoom').checked = config.enableZoomPage || false;

    // Security settings
    document.getElementById('block-screenshot').checked = !config.allowScreenShot || false;
    document.getElementById('block-alt-tab').checked = !config.enableAltTab || false;
    document.getElementById('kiosk-mode').checked = config.killExplorerShell || false;
    document.getElementById('block-f12').checked = !config.enableF12 || false;
    document.getElementById('monitor-processes').checked = config.monitorProcesses || false;
}

// ============================================================================
// SEB FILE GENERATION
// ============================================================================

async function generateSebFile() {
    const buildName = document.getElementById('build-name').value;
    const startUrl = document.getElementById('start-url').value;
    const platform = document.getElementById('platform').value;
    const adminPassword = document.getElementById('admin-password').value || 'admin123';
    const quitPassword = document.getElementById('quit-password').value || 'quit123';
    const usePermissiveFilter = document.getElementById('use-permissive-filter').checked;

    if (!buildName || !startUrl) {
        showNotification('Please fill in Build Name and Start URL', 'error');
        return;
    }

    // Collect config data
    const configData = {
        browserWindowAllowReload: document.getElementById('allow-reload').checked,
        allowBrowsingBackForward: document.getElementById('allow-back-forward').checked,
        enableBrowserWindowToolbar: document.getElementById('show-toolbar').checked,
        enableZoomPage: document.getElementById('enable-zoom').checked,
        allowScreenShot: !document.getElementById('block-screenshot').checked,
        enableAltTab: !document.getElementById('block-alt-tab').checked,
        killExplorerShell: document.getElementById('kiosk-mode').checked,
        enableF12: !document.getElementById('block-f12').checked,
        monitorProcesses: document.getElementById('monitor-processes').checked,
    };

    try {
        showNotification('Generating legacy PC .seb file...', 'info');

        const formData = new FormData();
        formData.append('build_name', buildName);
        formData.append('start_url', startUrl);
        formData.append('platform', platform);
        formData.append('admin_password', adminPassword);
        formData.append('quit_password', quitPassword);
        formData.append('use_permissive_filter', usePermissiveFilter);
        formData.append('config_data', JSON.stringify(configData));

        const response = await fetch('/api/v1/seb-builder/build', {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${localStorage.getItem('access_token')}`
            },
            body: formData
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            if (response.status === 503) {
                throw new Error('SEB PC/Desktop legacy sedang dinonaktifkan. APK resmi tetap menjadi runtime utama. Aktifkan SEB_DESKTOP_LEGACY_ENABLED hanya jika diperlukan.');
            }
            throw new Error(errorData.detail || `Build failed with status ${response.status}`);
        }

        const result = await response.json();

        showNotification('Legacy SEB file generated successfully!', 'success');

        // Show download link
        document.getElementById('download-link').href = result.download_url;
        document.getElementById('download-link-container').style.display = 'block';

        // Reload builds list
        await loadBuilds();

    } catch (error) {
        console.error('Error generating SEB file:', error);
        showNotification(`Failed: ${error.message}`, 'error');
    }
}

// ============================================================================
// TEMPLATE MANAGEMENT
// ============================================================================

async function loadTemplates() {
    try {
        const response = await fetch('/api/v1/seb-builder/templates', {
            headers: {
                'Authorization': `Bearer ${localStorage.getItem('access_token')}`
            }
        });

        const data = await response.json();
        templates = data.templates;

        renderTemplates();
    } catch (error) {
        console.error('Error loading templates:', error);
    }
}

function renderTemplates() {
    const container = document.getElementById('templates-list');

    if (templates.length === 0) {
        container.innerHTML = '<p style="color: var(--text-secondary); text-align: center; padding: 1rem;">No saved templates yet</p>';
        return;
    }

    container.innerHTML = templates.map(template => `
        <div class="build-item">
            <div class="build-info">
                <div class="build-name">${template.name}</div>
                <div class="build-meta">${template.preset_type}</div>
            </div>
            <button onclick="loadTemplateById(${template.id})">
                <i class="fas fa-upload"></i> Load
            </button>
        </div>
    `).join('');
}

async function loadTemplateById(templateId) {
    try {
        const response = await fetch(`/api/v1/seb-builder/templates/${templateId}`, {
            headers: {
                'Authorization': `Bearer ${localStorage.getItem('access_token')}`
            }
        });

        const template = await response.json();
        applyConfigToForm(template.config_data);
        showNotification(`Loaded template: ${template.name}`, 'success');
    } catch (error) {
        console.error('Error loading template:', error);
        showNotification('Failed to load template', 'error');
    }
}

async function saveAsTemplate() {
    const name = await showPrompt('Enter template name:', '', '💾 Save Template');
    if (!name) return;

    const description = await showPrompt('Enter template description (optional):', '', '📝 Template Description') || '';

    // Collect current config
    const configData = {
        browserWindowAllowReload: document.getElementById('allow-reload').checked,
        allowBrowsingBackForward: document.getElementById('allow-back-forward').checked,
        enableBrowserWindowToolbar: document.getElementById('show-toolbar').checked,
        enableZoomPage: document.getElementById('enable-zoom').checked,
        allowScreenShot: !document.getElementById('block-screenshot').checked,
        enableAltTab: !document.getElementById('block-alt-tab').checked,
        killExplorerShell: document.getElementById('kiosk-mode').checked,
        enableF12: !document.getElementById('block-f12').checked,
        monitorProcesses: document.getElementById('monitor-processes').checked,
    };

    try {
        const formData = new FormData();
        formData.append('name', name);
        formData.append('description', description);
        formData.append('config_data', JSON.stringify(configData));
        formData.append('preset_type', 'custom');

        const response = await fetch('/api/v1/seb-builder/templates', {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${localStorage.getItem('access_token')}`
            },
            body: formData
        });

        if (!response.ok) {
            throw new Error('Failed to save template');
        }

        showNotification('Template saved successfully!', 'success');
        await loadTemplates();
    } catch (error) {
        console.error('Error saving template:', error);
        showNotification('Failed to save template', 'error');
    }
}
