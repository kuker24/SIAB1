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
