
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
