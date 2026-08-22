/**
 * AUTO-GENERATED FILE.
 * Source modules: static/js/profile-modal/modules/*.js
 * Use scripts/build_profile_modal_bundle.sh after editing modules.
 */

/* ===== Module: 00-sanitize-template-assets.js ===== */

/**
 * Profile Modal - User profile editing with photo upload and cropping
 * Uses Cropper.js for intuitive image cropping
 */

(function () {
    'use strict';

    function sanitizeAvatarUrl(rawUrl, options = {}) {
        const { allowDataImage = false, allowBlob = false } = options;
        const value = rawUrl == null ? '' : String(rawUrl).trim();
        if (!value) {
            return '';
        }

        if (allowDataImage && /^data:image\/[a-z0-9.+-]+;base64,[a-z0-9+/=]+$/i.test(value)) {
            return value;
        }

        if (allowBlob && value.startsWith('blob:')) {
            return value;
        }

        if (/^(\/|\.\/|\.\.\/)/.test(value)) {
            return value;
        }

        try {
            const parsed = new URL(value, window.location.origin);
            if (parsed.protocol === 'http:' || parsed.protocol === 'https:') {
                return parsed.href;
            }
        } catch (error) {
            return '';
        }

        return '';
    }

    function setAvatarPreview(previewImg, initialSpan, removeBtn, profilePicture, fallbackText) {
        const safeUrl = sanitizeAvatarUrl(profilePicture);
        if (safeUrl) {
            previewImg.src = safeUrl;
            previewImg.style.display = 'block';
            initialSpan.style.display = 'none';
            if (removeBtn) {
                removeBtn.style.display = 'inline-flex';
            }
            return;
        }

        previewImg.style.display = 'none';
        previewImg.removeAttribute('src');
        initialSpan.style.display = 'flex';
        initialSpan.textContent = fallbackText;
        if (removeBtn) {
            removeBtn.style.display = 'none';
        }
    }

    function updateAvatarContainer(container, profilePicture, fallbackText) {
        if (!container) return;

        const safeUrl = sanitizeAvatarUrl(profilePicture);
        container.replaceChildren();

        if (safeUrl) {
            const image = document.createElement('img');
            image.src = safeUrl;
            image.alt = 'Profile';
            image.style.width = '100%';
            image.style.height = '100%';
            image.style.objectFit = 'cover';
            image.style.borderRadius = '50%';
            container.appendChild(image);
            return;
        }

        container.textContent = fallbackText;
    }

    // Modal HTML template
    const modalHTML = `
    <div class="profile-modal-overlay" id="profile-modal-overlay">
        <div class="profile-modal">
            <div class="profile-modal-header">
                <h3><i class="fas fa-camera"></i> Ubah Foto Profil</h3>
                <button class="profile-modal-close" onclick="ProfileModal.close()">&times;</button>
            </div>
            <div class="profile-modal-body">
                <!-- Profile Photo Section -->
                <div class="profile-photo-section">
                    <div class="profile-photo-preview" id="profile-photo-preview">
                        <span class="profile-photo-initial" id="profile-photo-initial">?</span>
                        <img id="profile-photo-img" src="" alt="Profile" style="display: none;">
                    </div>
                    <div class="profile-photo-actions">
                        <button class="btn btn-primary btn-sm" onclick="ProfileModal.selectPhoto()">
                            <i class="fas fa-camera"></i> Ubah Foto
                        </button>
                        <button class="btn btn-secondary btn-sm" onclick="ProfileModal.removePhoto()" id="btn-remove-photo" style="display: none;">
                            <i class="fas fa-trash"></i> Hapus
                        </button>
                    </div>
                    <input type="file" id="profile-photo-input" accept="image/*" style="display: none;">
                </div>

                <!-- Cropper Section (hidden by default) -->
                <div class="profile-cropper-section" id="profile-cropper-section" style="display: none;">
                    <div class="cropper-container-wrapper">
                        <img id="cropper-image" src="" alt="Crop">
                    </div>
                    <div class="cropper-controls">
                        <div class="cropper-ratio-buttons">
                            <button class="btn btn-sm btn-secondary active" onclick="ProfileModal.setAspectRatio(1)" title="Kotak 1:1">
                                <i class="fas fa-square"></i> 1:1
                            </button>
                            <button class="btn btn-sm btn-secondary" onclick="ProfileModal.setAspectRatio(NaN)" title="Bebas">
                                <i class="fas fa-expand"></i> Bebas
                            </button>
                        </div>
                        <div class="cropper-action-buttons">
                            <button class="btn btn-sm btn-secondary" onclick="ProfileModal.rotateCrop(-90)" title="Putar Kiri">
                                <i class="fas fa-undo"></i>
                            </button>
                            <button class="btn btn-sm btn-secondary" onclick="ProfileModal.rotateCrop(90)" title="Putar Kanan">
                                <i class="fas fa-redo"></i>
                            </button>
                            <button class="btn btn-sm btn-secondary" onclick="ProfileModal.zoomCrop(0.1)" title="Zoom In">
                                <i class="fas fa-search-plus"></i>
                            </button>
                            <button class="btn btn-sm btn-secondary" onclick="ProfileModal.zoomCrop(-0.1)" title="Zoom Out">
                                <i class="fas fa-search-minus"></i>
                            </button>
                        </div>
                    </div>
                    <div class="cropper-footer">
                        <button class="btn btn-secondary" onclick="ProfileModal.cancelCrop()">
                            <i class="fas fa-times"></i> Batal
                        </button>
                        <button class="btn btn-primary" onclick="ProfileModal.applyCrop()">
                            <i class="fas fa-check"></i> Terapkan
                        </button>
                    </div>
                </div>

                <!-- User info is managed by admin, not editable here -->
            </div>
            <div class="profile-modal-footer">
                <button class="btn btn-secondary" onclick="ProfileModal.close()">
                    <i class="fas fa-times"></i> Batal
                </button>
                <button class="btn btn-primary" onclick="ProfileModal.save()" id="btn-save-profile">
                    <i class="fas fa-save"></i> Simpan
                </button>
            </div>
        </div>
    </div>

    <style>
        .profile-modal-overlay {
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0, 0, 0, 0.7);
            backdrop-filter: blur(4px);
            z-index: 100000;
            display: flex;
            align-items: center;
            justify-content: center;
            opacity: 0;
            visibility: hidden;
            transition: all 0.3s ease;
        }
        .profile-modal-overlay.active {
            opacity: 1;
            visibility: visible;
        }
        .profile-modal {
            background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
            border: 1px solid rgba(99, 102, 241, 0.3);
            border-radius: 16px;
            width: 95%;
            max-width: 480px;
            max-height: 90vh;
            overflow: hidden;
            transform: scale(0.9) translateY(-20px);
            transition: transform 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
            box-shadow: 0 25px 50px rgba(0, 0, 0, 0.5), 0 0 40px rgba(99, 102, 241, 0.2);
        }
        .profile-modal-overlay.active .profile-modal {
            transform: scale(1) translateY(0);
        }
        .profile-modal-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 1.25rem 1.5rem;
            background: rgba(99, 102, 241, 0.1);
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
        }
        .profile-modal-header h3 {
            margin: 0;
            color: #f8fafc;
            font-size: 1.1rem;
            font-weight: 600;
        }
        .profile-modal-header h3 i {
            color: #6366f1;
            margin-right: 0.5rem;
        }
        .profile-modal-close {
            background: none;
            border: none;
            color: #94a3b8;
            font-size: 1.5rem;
            cursor: pointer;
            padding: 0;
            line-height: 1;
            transition: color 0.2s;
        }
        .profile-modal-close:hover {
            color: #f8fafc;
        }
        .profile-modal-body {
            padding: 1.5rem;
            max-height: 60vh;
            overflow-y: auto;
        }
        .profile-photo-section {
            display: flex;
            flex-direction: column;
            align-items: center;
            margin-bottom: 1.5rem;
            padding-bottom: 1.5rem;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
        }
        .profile-photo-preview {
            width: 120px;
            height: 120px;
            border-radius: 50%;
            background: linear-gradient(135deg, #6366f1 0%, #4f46e5 100%);
            display: flex;
            align-items: center;
            justify-content: center;
            overflow: hidden;
            border: 4px solid rgba(99, 102, 241, 0.3);
            box-shadow: 0 8px 24px rgba(99, 102, 241, 0.3);
            margin-bottom: 1rem;
        }
        .profile-photo-initial {
            font-size: 3rem;
            font-weight: 700;
            color: white;
            text-transform: uppercase;
        }
        .profile-photo-preview img {
            width: 100%;
            height: 100%;
            object-fit: cover;
        }
        .profile-photo-actions {
            display: flex;
            gap: 0.5rem;
        }
        .profile-cropper-section {
            background: rgba(0, 0, 0, 0.3);
            padding: 1rem;
            border-radius: 12px;
            margin-bottom: 1.5rem;
        }
        .cropper-container-wrapper {
            max-height: 300px;
            overflow: hidden;
            border-radius: 8px;
            margin-bottom: 1rem;
        }
        .cropper-container-wrapper img {
            max-width: 100%;
            display: block;
        }
        .cropper-controls {
            display: flex;
            justify-content: space-between;
            flex-wrap: wrap;
            gap: 0.5rem;
            margin-bottom: 1rem;
        }
        .cropper-ratio-buttons, .cropper-action-buttons {
            display: flex;
            gap: 0.25rem;
        }
        .cropper-footer {
            display: flex;
            justify-content: flex-end;
            gap: 0.5rem;
        }
        .profile-info-section .form-group {
            margin-bottom: 1rem;
        }
        .profile-info-section .form-label {
            display: block;
            color: #94a3b8;
            font-size: 0.85rem;
            margin-bottom: 0.5rem;
        }
        .profile-info-section .form-control {
            width: 100%;
            padding: 0.75rem 1rem;
            background: rgba(15, 23, 42, 0.8);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 8px;
            color: #f8fafc;
            font-size: 0.95rem;
            transition: all 0.2s;
        }
        .profile-info-section .form-control:focus {
            outline: none;
            border-color: #6366f1;
            box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.2);
        }
        .profile-modal-footer {
            display: flex;
            justify-content: flex-end;
            gap: 0.75rem;
            padding: 1rem 1.5rem;
            background: rgba(0, 0, 0, 0.2);
            border-top: 1px solid rgba(255, 255, 255, 0.05);
        }

        /* Cropper.js custom styles */
        .cropper-view-box,
        .cropper-face {
            border-radius: 50%;
        }
        .cropper-view-box {
            box-shadow: 0 0 0 1px #6366f1;
            outline: 0;
        }
        .cropper-line {
            background-color: #6366f1;
        }
        .cropper-point {
            background-color: #6366f1;
        }
    </style>
    `;

    let cropperAssetsPromise = null;

    function loadCropperAssets() {
        if (typeof Cropper !== 'undefined') {
            return Promise.resolve();
        }
        if (cropperAssetsPromise) {
            return cropperAssetsPromise;
        }

        cropperAssetsPromise = new Promise((resolve, reject) => {
            if (!document.querySelector('link[href*="cropper.min.css"]')) {
                const cropperCSS = document.createElement('link');
                cropperCSS.rel = 'stylesheet';
                cropperCSS.href = 'https://cdnjs.cloudflare.com/ajax/libs/cropperjs/1.6.1/cropper.min.css';
                document.head.appendChild(cropperCSS);
            }

            const existingScript = document.querySelector('script[src*="cropper.min.js"]');
            if (existingScript) {
                existingScript.addEventListener('load', () => resolve(), { once: true });
                existingScript.addEventListener('error', reject, { once: true });
                return;
            }

            const cropperScript = document.createElement('script');
            cropperScript.src = 'https://cdnjs.cloudflare.com/ajax/libs/cropperjs/1.6.1/cropper.min.js';
            cropperScript.async = true;
            cropperScript.onload = () => resolve();
            cropperScript.onerror = reject;
            document.head.appendChild(cropperScript);
        });

        return cropperAssetsPromise;
    }

/* ===== Module: 10-profile-modal-core.js ===== */


    // Profile Modal Controller
    window.ProfileModal = {
        cropper: null,
        currentUser: null,
        croppedBlob: null,

        init() {
            // Inject modal HTML if not present
            if (!document.getElementById('profile-modal-overlay')) {
                document.body.insertAdjacentHTML('beforeend', modalHTML);
            }

            // File input change handler
            document.getElementById('profile-photo-input').addEventListener('change', (e) => {
                const file = e.target.files[0];
                if (file) {
                    this.openCropper(file);
                }
            });
        },

        async open() {
            this.init();

            // Get current user data
            this.currentUser = JSON.parse(localStorage.getItem('user') || '{}');

            // Reset cropped blob
            this.croppedBlob = null;

            // Set photo preview
            this.updatePhotoPreview();

            // Show modal
            document.getElementById('profile-modal-overlay').classList.add('active');
            document.body.style.overflow = 'hidden';
        },

        close() {
            document.getElementById('profile-modal-overlay').classList.remove('active');
            document.body.style.overflow = '';

            // Destroy cropper if exists
            if (this.cropper) {
                this.cropper.destroy();
                this.cropper = null;
            }
        },

        updatePhotoPreview() {
            const previewImg = document.getElementById('profile-photo-img');
            const initialSpan = document.getElementById('profile-photo-initial');
            const removeBtn = document.getElementById('btn-remove-photo');
            const fallbackText = (this.currentUser.full_name || 'U').charAt(0).toUpperCase();

            setAvatarPreview(previewImg, initialSpan, removeBtn, this.currentUser.profile_picture, fallbackText);
        },

        selectPhoto() {
            document.getElementById('profile-photo-input').click();
        },

        openCropper(file) {
            const reader = new FileReader();
            reader.onload = (e) => {
                // Hide photo section, show cropper
                document.getElementById('profile-cropper-section').style.display = 'block';
                document.querySelector('.profile-photo-section').style.display = 'none';
                document.querySelector('.profile-modal-footer').style.display = 'none';

                // Set image source
                const cropperImg = document.getElementById('cropper-image');
                cropperImg.src = e.target.result;

                const initCropper = () => {
                    // Destroy existing cropper
                    if (this.cropper) {
                        this.cropper.destroy();
                    }

                    // Initialize Cropper
                    this.cropper = new Cropper(cropperImg, {
                        aspectRatio: 1,
                        viewMode: 1,
                        dragMode: 'move',
                        autoCropArea: 0.9,
                        responsive: true,
                        restore: false,
                        guides: true,
                        center: true,
                        highlight: false,
                        cropBoxMovable: true,
                        cropBoxResizable: true,
                        toggleDragModeOnDblclick: false
                    });
                };

                loadCropperAssets()
                    .then(initCropper)
                    .catch((error) => {
                        console.error('Failed to load Cropper.js:', error);
                        alert('Gagal memuat editor foto. Coba lagi nanti.');
                        this.cancelCrop();
                    });
            };
            reader.readAsDataURL(file);
        },

        setAspectRatio(ratio) {
            if (this.cropper) {
                this.cropper.setAspectRatio(ratio);

                // Update active button
                document.querySelectorAll('.cropper-ratio-buttons .btn').forEach(btn => {
                    btn.classList.remove('active');
                });
                event.target.closest('.btn').classList.add('active');
            }
        },

        rotateCrop(degrees) {
            if (this.cropper) {
                this.cropper.rotate(degrees);
            }
        },

        zoomCrop(ratio) {
            if (this.cropper) {
                this.cropper.zoom(ratio);
            }
        },

        cancelCrop() {
            if (this.cropper) {
                this.cropper.destroy();
                this.cropper = null;
            }

            // Show photo section, hide cropper
            document.getElementById('profile-cropper-section').style.display = 'none';
            document.querySelector('.profile-photo-section').style.display = 'flex';
            document.querySelector('.profile-modal-footer').style.display = 'flex';

            // Clear file input
            document.getElementById('profile-photo-input').value = '';
        },

        async applyCrop() {
            if (!this.cropper) return;

            // Get cropped canvas
            const canvas = this.cropper.getCroppedCanvas({
                width: 256,
                height: 256,
                imageSmoothingEnabled: true,
                imageSmoothingQuality: 'high'
            });

            // Convert to blob
            canvas.toBlob(async (blob) => {
                this.croppedBlob = blob;

                // Update preview
                const previewImg = document.getElementById('profile-photo-img');
                const initialSpan = document.getElementById('profile-photo-initial');

                previewImg.src = canvas.toDataURL();
                previewImg.style.display = 'block';
                initialSpan.style.display = 'none';
                document.getElementById('btn-remove-photo').style.display = 'inline-flex';

                // Cancel cropper and return to main view
                this.cancelCrop();
            }, 'image/jpeg', 0.9);
        },

        async removePhoto() {
            // Clear cropped blob and profile picture
            this.croppedBlob = null;
            this.currentUser.profile_picture = null;

            // Update preview to show initial
            const previewImg = document.getElementById('profile-photo-img');
            const initialSpan = document.getElementById('profile-photo-initial');
            const removeBtn = document.getElementById('btn-remove-photo');

            previewImg.style.display = 'none';
            previewImg.src = '';
            initialSpan.style.display = 'flex';
            initialSpan.textContent = (this.currentUser.full_name || 'U').charAt(0).toUpperCase();
            removeBtn.style.display = 'none';
        },

        async save() {
            const btn = document.getElementById('btn-save-profile');
            const originalText = btn.innerHTML;
            btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Menyimpan...';
            btn.disabled = true;

            try {
                let profilePictureUrl = this.currentUser.profile_picture;
                let hasChanges = false;

                // Upload cropped image if exists
                if (this.croppedBlob) {
                    const formData = new FormData();
                    formData.append('file', this.croppedBlob, 'profile.jpg');

                    const uploadResponse = await fetch('/api/upload/image', {
                        method: 'POST',
                        headers: {
                            'Authorization': `Bearer ${localStorage.getItem('access_token')}`
                        },
                        body: formData
                    });

                    if (!uploadResponse.ok) {
                        const errorData = await uploadResponse.json().catch(() => ({}));
                        throw new Error(errorData.detail || 'Gagal upload foto');
                    }

                    const uploadResult = await uploadResponse.json();
                    profilePictureUrl = sanitizeAvatarUrl(uploadResult.url);
                    if (!profilePictureUrl) {
                        throw new Error('URL foto profil tidak valid');
                    }
                    hasChanges = true;
                }

                // Check if photo was deleted (profile_picture set to null in removePhoto)
                const originalUser = JSON.parse(localStorage.getItem('user') || '{}');
                if (originalUser.profile_picture && this.currentUser.profile_picture === null) {
                    profilePictureUrl = null;
                    hasChanges = true;
                }

                // If no changes, just close
                if (!hasChanges) {
                    this.close();
                    return;
                }

                // Update only profile picture (name/email/password managed by admin)
                const updateData = {
                    profile_picture: profilePictureUrl
                };

                await api.updateUser(this.currentUser.id, updateData);

                // Update local storage
                this.currentUser.profile_picture = profilePictureUrl;
                localStorage.setItem('user', JSON.stringify(this.currentUser));

                // Update sidebar display
                this.updateSidebarDisplay();

                // Update header avatar if exists
                this.updateHeaderAvatar();

                // Show success
                if (typeof showSuccess === 'function') {
                    showSuccess('Profil berhasil diperbarui!');
                } else {
                    alert('Profil berhasil diperbarui!');
                }

                this.close();

            } catch (error) {
                console.error('Error saving profile:', error);
                if (typeof showError === 'function') {
                    showError('Gagal menyimpan profil: ' + error.message);
                } else {
                    alert('Gagal menyimpan profil: ' + error.message);
                }
            } finally {
                btn.innerHTML = originalText;
                btn.disabled = false;
            }

/* ===== Module: 20-avatar-sync-and-bootstrap.js ===== */

        },

        updateSidebarDisplay() {
            // Update sidebar avatar (simplified - photo only)
            const sidebarAvatarImg = document.getElementById('sidebar-avatar-img');
            const sidebarAvatarInitial = document.getElementById('sidebar-avatar-initial');

            if (sidebarAvatarImg && sidebarAvatarInitial) {
                const safeUrl = sanitizeAvatarUrl(this.currentUser.profile_picture);
                if (safeUrl) {
                    sidebarAvatarImg.src = safeUrl;
                    sidebarAvatarImg.style.display = 'block';
                    sidebarAvatarInitial.style.display = 'none';
                } else {
                    sidebarAvatarImg.style.display = 'none';
                    sidebarAvatarImg.removeAttribute('src');
                    sidebarAvatarInitial.style.display = 'flex';
                    sidebarAvatarInitial.textContent = (this.currentUser.full_name || 'U').charAt(0).toUpperCase();
                }
            }
        },

        updateHeaderAvatar() {
            // Update header avatar (top-right dropdown)
            const headerAvatarEl = document.getElementById('user-avatar');
            if (headerAvatarEl) {
                updateAvatarContainer(
                    headerAvatarEl,
                    this.currentUser.profile_picture,
                    (this.currentUser.full_name || 'U').charAt(0).toUpperCase()
                );
            }
        }
    };

    // Initialize on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => ProfileModal.init());
    } else {
        ProfileModal.init();
    }
})();
