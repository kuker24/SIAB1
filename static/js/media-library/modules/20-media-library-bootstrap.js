// Global instance
let mediaLibrary;

function initMediaLibrary() {
    mediaLibrary = new MediaLibrary();
    mediaLibrary.init();
}

function closeUploadModal() {
    const modal = document.getElementById('upload-modal');
    if (modal) modal.remove();
}

function copyFileUrl() {
    const input = document.getElementById('file-url-input');
    if (input) {
        input.select();
        document.execCommand('copy');
        UIComponents.showToast('Tautan berhasil disalin ke clipboard.', 'success');
    }
}
