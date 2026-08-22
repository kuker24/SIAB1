/**
 * Media Library Module
 * Centralized media file management
 */

function escapeHtml(value) {
    const text = value == null ? '' : String(value);
    return text.replace(/[&<>"'`]/g, (char) => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;',
        '`': '&#96;'
    }[char] || char));
}

function escapeAttribute(value) {
    return escapeHtml(value).replace(/\n/g, '&#10;');
}

function sanitizeMediaUrl(rawUrl, options = {}) {
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

function renderSafeImageMarkup(url, altText, extraAttributes = '') {
    const safeUrl = sanitizeMediaUrl(url);
    if (!safeUrl) {
        return '';
    }
    return `<img src="${escapeAttribute(safeUrl)}" alt="${escapeAttribute(altText)}"${extraAttributes}>`;
}
