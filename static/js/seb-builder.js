/**
 * AUTO-GENERATED FILE.
 * Source modules: static/js/seb-builder/modules/*.js
 * Use scripts/build_seb_builder_bundle.sh after editing modules.
 */

/* ===== Module: 00-seb-pc-core.js ===== */

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

/* ===== Module: 10-seb-pc-history-utils-init.js ===== */

// ============================================================================
// BUILD HISTORY
// ============================================================================

async function loadBuilds() {
    try {
        const response = await fetch('/api/v1/seb-builder/builds?limit=20', {
            headers: {
                'Authorization': `Bearer ${localStorage.getItem('access_token')}`
            }
        });

        const data = await response.json();
        builds = data.builds;

        renderBuilds();
    } catch (error) {
        console.error('Error loading builds:', error);
    }
}

function renderBuilds() {
    const container = document.getElementById('pc-builds-list');

    if (builds.length === 0) {
        container.innerHTML = '<p style="color: var(--text-secondary); text-align: center; padding: 2rem;">No builds yet. Create your first SEB configuration above.</p>';
        return;
    }

    container.innerHTML = builds.map(build => `
        <div class="build-item">
            <div class="build-info">
                <div class="build-name">
                    ${build.build_name}
                    <span class="status-badge ${build.status}">${build.status}</span>
                </div>
                <div class="build-meta">
                    ${build.platform} • ${new Date(build.created_at).toLocaleDateString()} • ${formatFileSize(build.file_size)}
                </div>
            </div>
            <div class="build-actions">
                ${build.status === 'success' ? `
                    <button onclick="downloadBuild(${build.id})">
                        <i class="fas fa-download"></i> Download
                    </button>
                ` : ''}
                <button class="delete" onclick="deleteBuild(${build.id})">
                    <i class="fas fa-trash"></i> Delete
                </button>
            </div>
        </div>
    `).join('');
}

async function downloadBuild(buildId) {
    try {
        const response = await fetch(`/api/v1/seb-builder/download/${buildId}`, {
            headers: {
                'Authorization': `Bearer ${localStorage.getItem('access_token')}`
            }
        });

        if (!response.ok) {
            throw new Error('Download failed');
        }

        // Get filename from Content-Disposition header or use default
        const contentDisposition = response.headers.get('Content-Disposition');
        let filename = 'config.seb';
        if (contentDisposition) {
            const matches = /filename="?([^"]+)"?/.exec(contentDisposition);
            if (matches && matches[1]) {
                filename = matches[1];
            }
        }

        // Download the file
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    } catch (error) {
        console.error('Download error:', error);
        // Use showAlert if available, otherwise fallback to native alert
        if (typeof showAlert === 'function') {
            await showAlert('Download failed. Please try again.', 'error', '❌ Download Error');
        } else {
            alert('❌ Download failed. Please try again.');
        }
    }
}

async function deleteBuild(buildId) {
    // Use showConfirm if available, otherwise fallback to native confirm
    const confirmed = typeof showConfirm === 'function'
        ? await showConfirm('Build akan dihapus permanent.', '⚠️ Delete Build', { type: 'danger', confirmText: 'Delete', cancelText: 'Cancel' })
        : confirm('⚠️ Build akan dihapus permanent. Lanjutkan?');

    if (!confirmed) {
        return;
    }

    try {
        const response = await fetch(`/api/v1/seb-builder/builds/${buildId}`, {
            method: 'DELETE',
            headers: {
                'Authorization': `Bearer ${localStorage.getItem('access_token')}`
            }
        });

        if (!response.ok) {
            throw new Error('Failed to delete build');
        }

        showNotification('Build deleted successfully', 'success');
        await loadBuilds();
    } catch (error) {
        console.error('Error deleting build:', error);
        showNotification('Failed to delete build', 'error');
    }
}

// ============================================================================
// UTILITIES
// ============================================================================

function formatFileSize(bytes) {
    if (!bytes) return 'N/A';
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

function showNotification(message, type = 'info') {
    // Simple notification - can be enhanced with a proper notification system
    const colors = {
        success: '#10b981',
        error: '#ef4444',
        info: '#3b82f6'
    };

    const notification = document.createElement('div');
    notification.style.cssText = `
        position: fixed;
        top: 2rem;
        right: 2rem;
        padding: 1rem 1.5rem;
        background: ${colors[type]};
        color: white;
        border-radius: 0.5rem;
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
        z-index: 10000;
        animation: slideIn 0.3s ease;
    `;
    notification.textContent = message;

    document.body.appendChild(notification);

    setTimeout(() => {
        notification.style.animation = 'slideOut 0.3s ease';
        setTimeout(() => notification.remove(), 300);
    }, 3000);
}

// ============================================================================
// INITIALIZATION
// ============================================================================

document.addEventListener('DOMContentLoaded', () => {
    // Store original HTML for preset buttons (for loading state restoration)
    document.querySelectorAll('.preset-btn').forEach(btn => {
        btn.setAttribute('data-original-html', btn.innerHTML);
    });

    // Load initial data for PC builder
    if (currentPlatform === 'pc') {
        loadTemplates();
        loadBuilds();
    }

    // Set default values
    document.getElementById('admin-password').value = 'admin123';
    document.getElementById('quit-password').value = 'quit123';
    document.getElementById('use-permissive-filter').checked = true;
});

// Add CSS animations
const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn {
        from {
            transform: translateX(100%);
            opacity: 0;
        }
        to {
            transform: translateX(0);
            opacity: 1;
        }
    }

    @keyframes slideOut {
        from {
            transform: translateX(0);
            opacity: 1;
        }
        to {
            transform: translateX(100%);
            opacity: 0;
        }
    }
`;
document.head.appendChild(style);

/* ===== Module: 20-seb-android-apk.js ===== */

// ============================================================================
// APK BUILDER FUNCTIONS (Android)
// ============================================================================

async function buildAPK() {
    const appName = document.getElementById('apk-app-name').value;
    const packageName = document.getElementById('apk-package-name').value;
    const serverUrl = document.getElementById('apk-server-url-input').value;

    if (!appName || !packageName || !serverUrl) {
        showNotification('Please fill in all required fields', 'error');
        return;
    }

    // Collect security settings
    const kioskMode = document.getElementById('apk-kiosk-mode').checked;
    const blockScreenshot = document.getElementById('apk-block-screenshot').checked;
    const detectRoot = document.getElementById('apk-detect-root').checked;
    const blockTaskSwitch = document.getElementById('apk-block-task-switch').checked;

    // Get UI elements
    const progressContainer = document.getElementById('apk-build-progress');
    const progressBar = document.getElementById('apk-progress-bar');
    const statusText = document.getElementById('apk-build-status');
    const percentageEl = document.getElementById('apk-build-percentage');
    const elapsedEl = document.getElementById('apk-build-elapsed');
    const estimateEl = document.getElementById('apk-build-estimate');
    const buildLogEl = document.getElementById('apk-build-log');
    const stepsContainer = document.getElementById('apk-steps-container');

    // Show progress container and reset
    progressContainer.style.display = 'block';
    progressBar.style.width = '0%';
    percentageEl.textContent = '0%';
    statusText.innerHTML = '<i class="fas fa-circle-notch fa-spin" style="margin-right: 0.5rem;"></i> Preparing build...';
    buildLogEl.textContent = 'Starting build process...\n';

    // Reset step indicators
    stepsContainer.querySelectorAll('.build-step').forEach(step => {
        step.style.opacity = '0.5';
        step.querySelector('i').className = 'fas fa-circle';
        step.querySelector('i').style.color = '#64748b';
    });

    // Start elapsed timer
    const startTime = Date.now();
    const timerInterval = setInterval(() => {
        const elapsed = Math.floor((Date.now() - startTime) / 1000);
        const mins = Math.floor(elapsed / 60);
        const secs = elapsed % 60;
        elapsedEl.textContent = `⏱️ Elapsed: ${mins}:${secs.toString().padStart(2, '0')}`;
    }, 1000);

    // Helper function to update step indicator
    function updateStep(stepNum, status) {
        const stepEl = stepsContainer.querySelector(`[data-step="${stepNum}"]`);
        if (stepEl) {
            const icon = stepEl.querySelector('i');
            if (status === 'active') {
                stepEl.style.opacity = '1';
                icon.className = 'fas fa-spinner fa-spin';
                icon.style.color = '#3b82f6';
            } else if (status === 'done') {
                stepEl.style.opacity = '1';
                icon.className = 'fas fa-check-circle';
                icon.style.color = '#10b981';
            } else if (status === 'error') {
                stepEl.style.opacity = '1';
                icon.className = 'fas fa-times-circle';
                icon.style.color = '#ef4444';
            }
        }
    }

    try {
        const formData = new FormData();
        formData.append('app_name', appName);
        formData.append('package_name', packageName);
        formData.append('server_url', serverUrl);
        formData.append('enable_kiosk', kioskMode);
        formData.append('block_screenshot', blockScreenshot);
        formData.append('detect_root', detectRoot);
        formData.append('block_task_switch', blockTaskSwitch);

        // Icon upload if exists
        const iconUpload = document.getElementById('apk-icon-upload');
        if (iconUpload.files.length > 0) {
            formData.append('icon', iconUpload.files[0]);
        }

        // Update UI
        progressBar.style.width = '5%';
        percentageEl.textContent = '5%';
        statusText.innerHTML = '<i class="fas fa-upload" style="margin-right: 0.5rem;"></i> Uploading configuration to server...';
        buildLogEl.textContent += 'Uploading configuration...\n';

        const response = await fetch('/api/v1/apk-builder/build', {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${localStorage.getItem('access_token')}`
            },
            body: formData
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || 'Build request failed');
        }

        const result = await response.json();
        const buildId = result.build_id;

        progressBar.style.width = '10%';
        percentageEl.textContent = '10%';
        statusText.innerHTML = '<i class="fas fa-cog fa-spin" style="margin-right: 0.5rem;"></i> Build started, waiting for server...';
        buildLogEl.textContent += `Build ID: ${buildId}\nWaiting for build progress...\n`;

        // Poll build status with detailed updates
        const pollInterval = setInterval(async () => {
            try {
                const statusResponse = await fetch(`/api/v1/apk-builder/status/${buildId}`, {
                    headers: {
                        'Authorization': `Bearer ${localStorage.getItem('access_token')}`
                    }
                });

                if (!statusResponse.ok) {
                    console.error('Status check failed');
                    return;
                }

                const statusData = await statusResponse.json();

                // Parse build log to determine current step
                const buildLog = statusData.build_log || '';
                let progress = 10;
                let currentStep = 0;
                let stepMessage = 'Processing...';

                if (buildLog.includes('[1/5]')) {
                    currentStep = 1;
                    progress = 15;
                    stepMessage = 'Checking Flutter SDK...';
                    estimateEl.textContent = '⏳ Est. remaining: ~8-10 min';
                }
                if (buildLog.includes('✓ Flutter found')) {
                    updateStep(1, 'done');
                    progress = 20;
                }
                if (buildLog.includes('[2/5]')) {
                    currentStep = 2;
                    progress = 25;
                    stepMessage = 'Updating pubspec.yaml...';
                    estimateEl.textContent = '⏳ Est. remaining: ~7-9 min';
                }
                if (buildLog.includes('✓ pubspec.yaml updated')) {
                    updateStep(2, 'done');
                    progress = 35;
                }
                if (buildLog.includes('[3/5]')) {
                    currentStep = 3;
                    progress = 40;
                    stepMessage = 'Processing app icon...';
                    estimateEl.textContent = '⏳ Est. remaining: ~6-8 min';
                }
                if (buildLog.includes('✓ Custom icon applied') || buildLog.includes('✓ Using default icon')) {
                    updateStep(3, 'done');
                    progress = 45;
                }
                if (buildLog.includes('[4/5]')) {
                    currentStep = 4;
                    progress = 50;
                    stepMessage = 'Compiling APK (this is the longest step)...';
                    estimateEl.textContent = '⏳ Est. remaining: ~5-8 min';
                }
                if (buildLog.includes('✓ APK build completed')) {
                    updateStep(4, 'done');
                    progress = 85;
                }
                if (buildLog.includes('[5/5]')) {
                    currentStep = 5;
                    progress = 90;
                    stepMessage = 'Packaging and finalizing...';
                    estimateEl.textContent = '⏳ Est. remaining: ~30 sec';
                }
                if (buildLog.includes('✓ APK saved')) {
                    updateStep(5, 'done');
                    progress = 100;
                }

                // Update current step indicator
                if (currentStep > 0) {
                    updateStep(currentStep, 'active');
                }

                // Update UI
                progressBar.style.width = progress + '%';
                percentageEl.textContent = progress + '%';
                statusText.innerHTML = `<i class="fas fa-cog fa-spin" style="margin-right: 0.5rem;"></i> ${stepMessage}`;

                // Update build log
                if (buildLog) {
                    buildLogEl.textContent = buildLog;
                    buildLogEl.scrollTop = buildLogEl.scrollHeight;
                }

                if (statusData.status === 'success') {
                    clearInterval(pollInterval);
                    clearInterval(timerInterval);

                    // Mark all steps as done
                    for (let i = 1; i <= 5; i++) {
                        updateStep(i, 'done');
                    }

                    progressBar.style.width = '100%';
                    percentageEl.textContent = '100%';
                    statusText.innerHTML = '<i class="fas fa-check-circle" style="margin-right: 0.5rem; color: #10b981;"></i> Build completed successfully!';
                    estimateEl.textContent = '✅ Complete!';

                    showNotification('APK built successfully!', 'success');

                    // Show download section
                    document.getElementById('apk-download-link').href = statusData.download_url || `/api/v1/apk-builder/download/${buildId}`;
                    document.getElementById('apk-download-section').style.display = 'block';

                    // Update file size
                    if (statusData.file_size) {
                        const sizeMB = (statusData.file_size / (1024 * 1024)).toFixed(1);
                        document.getElementById('apk-size').textContent = sizeMB + 'MB';
                    }

                    // Hide progress after delay
                    setTimeout(() => {
                        progressContainer.style.display = 'none';
                    }, 3000);

                    loadAPKBuilds();

                } else if (statusData.status === 'failed') {
                    clearInterval(pollInterval);
                    clearInterval(timerInterval);

                    // Mark current step as error
                    if (currentStep > 0) {
                        updateStep(currentStep, 'error');
                    }

                    statusText.innerHTML = `<i class="fas fa-times-circle" style="margin-right: 0.5rem; color: #ef4444;"></i> Build failed: ${statusData.error_message || 'Unknown error'}`;
                    estimateEl.textContent = '❌ Failed';

                    showNotification('Build failed: ' + (statusData.error_message || 'Unknown error'), 'error');
                }
            } catch (pollError) {
                console.error('Polling error:', pollError);
            }
        }, 2000);

    } catch (error) {
        clearInterval(timerInterval);
        console.error('Error building APK:', error);
        statusText.innerHTML = `<i class="fas fa-times-circle" style="margin-right: 0.5rem; color: #ef4444;"></i> ${error.message}`;
        showNotification('Failed to build APK: ' + error.message, 'error');
    }
}

function syncFromSEB() {
    // Sync SEB configuration to APK builder
    const serverUrl = document.getElementById('start-url').value;

    if (serverUrl) {
        document.getElementById('apk-server-url-input').value = serverUrl;
        showNotification('Server URL synced from SEB config', 'success');
    } else {
        showNotification('No SEB configuration to sync', 'error');
    }
}

async function loadAPKBuilds() {
    try {
        const response = await fetch('/api/v1/apk-builder/builds?limit=10', {
            headers: {
                'Authorization': `Bearer ${localStorage.getItem('access_token')}`
            }
        });

        const data = await response.json();
        const builds = data.builds || [];

        const container = document.getElementById('apk-builds-list');

        if (builds.length === 0) {
            container.innerHTML = '<p style="color: var(--text-secondary); text-align: center; padding: 2rem;">No builds yet. Create your first APK configuration above.</p>';
            return;
        }

        container.innerHTML = builds.map(build => `
            <div class="build-item">
                <div class="build-info">
                    <div class="build-name">
                        ${build.app_name}
                        <span class="status-badge ${build.status}">${build.status}</span>
                    </div>
                    <div class="build-meta">
                        ${build.package_name} • ${new Date(build.created_at).toLocaleDateString()}
                    </div>
                </div>
                <div class="build-actions">
                    ${build.status === 'success' ? `
                        <button onclick="window.location.href='/api/v1/apk-builder/download/${build.id}'">
                            <i class="fas fa-download"></i> Download
                        </button>
                    ` : ''}
                    <button class="delete" onclick="deleteAPKBuild(${build.id})">
                        <i class="fas fa-trash"></i> Delete
                    </button>
                </div>
            </div>
        `).join('');
    } catch (error) {
        console.error('Error loading APK builds:', error);
    }
}

async function deleteAPKBuild(buildId) {
    // Use showConfirm if available, otherwise fallback to native confirm
    const confirmed = typeof showConfirm === 'function'
        ? await showConfirm('Build akan dihapus permanent.', '⚠️ Delete Build', { type: 'danger', confirmText: 'Delete', cancelText: 'Cancel' })
        : confirm('⚠️ Build akan dihapus permanent. Lanjutkan?');

    if (!confirmed) {
        return;
    }

    try {
        const response = await fetch(`/api/v1/apk-builder/builds/${buildId}`, {
            method: 'DELETE',
            headers: {
                'Authorization': `Bearer ${localStorage.getItem('access_token')}`
            }
        });

        if (!response.ok) {
            throw new Error('Failed to delete build');
        }

        showNotification('Build deleted successfully', 'success');
        loadAPKBuilds();
    } catch (error) {
        console.error('Error deleting build:', error);
        showNotification('Failed to delete build', 'error');
    }
}
