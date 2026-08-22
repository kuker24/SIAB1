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
