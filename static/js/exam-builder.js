/**
 * AUTO-GENERATED FILE.
 * Source modules: static/js/exam-builder/modules/*.js
 * Use scripts/build_exam_builder_bundle.sh after editing modules.
 */

/* ===== Module: 00-bootstrap-settings-events.js ===== */

/**
 * Exam Builder JavaScript - Main Controller
 * Handles exam creation, question management, and publishing workflow
 */

// ============== HELPER FUNCTIONS ==============

// Show alert notification
function showAlert(message, type = 'info') {
    // FIX: Prioritize 'toast-container' which exists in HTML, fallback to 'alert-container'
    const alertContainer = document.getElementById('toast-container') || document.getElementById('alert-container');

    if (!alertContainer) {
        console.error('[ALERT] No toast-container found, using console fallback');
        console.log(`[${type.toUpperCase()}] ${message}`);
        return;
    }

    const borderColors = {
        success: '#22c55e',
        danger: '#ef4444',
        warning: '#f59e0b',
        info: '#6366f1'
    };

    const iconMap = {
        success: 'fa-check-circle',
        danger: 'fa-times-circle',
        warning: 'fa-exclamation-triangle',
        info: 'fa-info-circle'
    };

    const alert = document.createElement('div');
    alert.className = `alert alert-${type}`;
    // Dark Theme Solid Style (Matches Admin Dashboard)
    alert.style.cssText = `
        padding: 1rem 1.25rem;
        margin-bottom: 1rem;
        border-radius: 0.75rem;
        background-color: #1e293b; /* Solid Dark Blue-Grey (Slate 800) */
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-left: 4px solid ${borderColors[type] || borderColors.info};
        color: #f8fafc; /* Light Text */
        box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.3), 0 10px 10px -5px rgba(0, 0, 0, 0.2);
        display: flex;
        align-items: flex-start;
        gap: 0.75rem;
        animation: slideInDown 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        opacity: 1;
        min-width: 320px;
        max-width: 450px;
        z-index: 9999;
        font-size: 0.95rem;
        line-height: 1.5;
        pointer-events: auto;
    `;

    // Add icon for better visual cue
    const iconColor = borderColors[type] || borderColors.info;

    alert.innerHTML = `
        <i class="fas ${iconMap[type] || iconMap.info}" style="color: ${iconColor}; font-size: 1.25rem; margin-top: 0.15rem;"></i>
        <div style="flex: 1;">${message}</div>
        <button type="button" class="close-alert-btn" style="
            background: rgba(255,255,255,0.1);
            border: none;
            color: #94a3b8;
            cursor: pointer;
            width: 24px;
            height: 24px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all 0.2s;
            flex-shrink: 0;
        " title="Tutup">
            <i class="fas fa-times" style="font-size: 0.9rem;"></i>
        </button>
    `;

    // Add click event listener to the close button specifically
    const closeBtn = alert.querySelector('.close-alert-btn');
    if (closeBtn) {
        // Add hover effect via JS since inline styles make hover tricky
        closeBtn.onmouseenter = () => {
            closeBtn.style.background = 'rgba(255,255,255,0.2)';
            closeBtn.style.color = '#fff';
        };
        closeBtn.onmouseleave = () => {
            closeBtn.style.background = 'rgba(255,255,255,0.1)';
            closeBtn.style.color = '#94a3b8';
        };

        closeBtn.onclick = function (e) {
            e.stopPropagation(); // Prevent bubbling
            const parentAlert = this.closest('.alert');
            if (parentAlert) {
                // Animation out
                parentAlert.style.transition = 'all 0.3s ease-out';
                parentAlert.style.opacity = '0';
                parentAlert.style.transform = 'translateY(-10px)';
                setTimeout(() => parentAlert.remove(), 300);
            }
        };
    }

    alertContainer.appendChild(alert);

    // Auto-remove after 5 seconds
    setTimeout(() => {
        if (alert.parentElement) {
            alert.style.animation = 'slideOutUp 0.3s ease';
            setTimeout(() => alert.remove(), 300);
        }
    }, 5000);
}

// Show success message (shorthand)
function showSuccess(message) {
    showAlert(message, 'success');
}

// Format date for datetime-local input
function formatDateTimeLocal(date) {
    const d = new Date(date);
    const year = d.getFullYear();
    const month = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    const hours = String(d.getHours()).padStart(2, '0');
    const minutes = String(d.getMinutes()).padStart(2, '0');
    return `${year}-${month}-${day}T${hours}:${minutes}`;
}

// Update empty state visibility
function updateEmptyState() {
    const emptyState = document.getElementById('empty-state');
    const questionsContainer = document.getElementById('questions-container');

    if (emptyState) {
        if (examData.questions.length === 0) {
            emptyState.style.display = 'block';
            if (questionsContainer) questionsContainer.style.display = 'none';
        } else {
            emptyState.style.display = 'none';
            if (questionsContainer) questionsContainer.style.display = 'block';
        }
    }
}

// Escape HTML to prevent XSS in both text nodes and quoted HTML attributes.
function escapeHtml(text) {
    if (text === null || text === undefined) return '';
    return String(text)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function renderBuilderRichText(text) {
    const source = text == null ? '' : String(text);
    if (!source) return '';

    const escaped = escapeHtml(source);
    return escaped
        .replace(/\[b\]([\s\S]*?)\[\/b\]/gi, '<strong>$1</strong>')
        .replace(/\[i\]([\s\S]*?)\[\/i\]/gi, '<em>$1</em>')
        .replace(/\[u\]([\s\S]*?)\[\/u\]/gi, '<u>$1</u>')
        .replace(/\[(?:ar|arabic)\]([\s\S]*?)\[\/(?:ar|arabic)\]/gi, '<span class="rich-arabic">$1</span>')
        .replace(/\r?\n/g, '<br>');
}

// Auto-resize textarea based on content
function autoResize(textarea) {
    if (!textarea) return;
    textarea.style.height = 'auto';
    textarea.style.height = textarea.scrollHeight + 'px';
}

// Show loader helper
function showLoader(message) {
    const status = document.getElementById('save-status');
    if (status) {
        status.innerHTML = `<i class="fas fa-spinner fa-spin"></i> ${message}`;
        status.classList.add('saving');
    }
}

// Hide loader helper
function hideLoader() {
    const status = document.getElementById('save-status');
    if (status) {
        status.innerHTML = '<i class="fas fa-check-circle"></i> Tersimpan';
        status.classList.remove('saving');
    }
}

// Show error helper
function showError(message) {
    showAlert(message, 'danger');
}

// ============== MAIN APPLICATION CODE ==============

// Global error handler for unhandled promise rejections
window.addEventListener('unhandledrejection', (event) => {
    console.error('Unhandled promise rejection:', event.reason);
    showAlert('Terjadi kesalahan. Silakan coba lagi.', 'danger');
    event.preventDefault(); // Prevent default logging
});

// Check auth
if (!auth.requireAuth(['admin', 'developer', 'teacher'])) { }

const DEFAULT_BUILDER_SETTINGS = Object.freeze({
    default_mc_key_only: true,
    default_pgk_key_only: true,
    default_image_layout_mode: 'model1',
    smart_auto_shuffle_options: false,
    smart_auto_shuffle_questions: false
});

function normalizeBuilderSettings(rawSettings = {}) {
    const raw = rawSettings && typeof rawSettings === 'object' ? rawSettings : {};
    return {
        default_mc_key_only: raw.default_mc_key_only !== false,
        default_pgk_key_only: raw.default_pgk_key_only !== false,
        default_image_layout_mode: 'model1',
        smart_auto_shuffle_options: raw.smart_auto_shuffle_options === true,
        smart_auto_shuffle_questions: raw.smart_auto_shuffle_questions === true
    };
}

function getBuilderSettings() {
    examData.builder_settings = normalizeBuilderSettings(examData.builder_settings || DEFAULT_BUILDER_SETTINGS);
    return examData.builder_settings;
}

function setShuffleToggleUi(toggleId, checked) {
    const el = document.getElementById(toggleId);
    if (el) el.checked = Boolean(checked);
}

function syncShuffleTogglesWithBuilderSettings(showNotice = false) {
    const settings = getBuilderSettings();
    const desiredShuffleOptions = settings.smart_auto_shuffle_options === true;
    const desiredShuffleQuestions = settings.smart_auto_shuffle_questions === true;
    let changed = false;

    if (examData.shuffle_options !== desiredShuffleOptions) {
        examData.shuffle_options = desiredShuffleOptions;
        setShuffleToggleUi('shuffle-options', desiredShuffleOptions);
        changed = true;
    }
    if (examData.shuffle_questions !== desiredShuffleQuestions) {
        examData.shuffle_questions = desiredShuffleQuestions;
        setShuffleToggleUi('shuffle-questions', desiredShuffleQuestions);
        changed = true;
    }

    if (changed && showNotice) {
        showAlert('Toggle Acak Soal/Opsi sudah sinkron dengan Pengaturan Default Soal.', 'info');
    }
    return changed;
}

function alignBuilderSettingsWithExamToggles() {
    const settings = getBuilderSettings();
    settings.smart_auto_shuffle_options = examData.shuffle_options === true;
    settings.smart_auto_shuffle_questions = examData.shuffle_questions === true;
}

function applyBuilderDefaultsToQuestion(question) {
    if (!question) return;
    const settings = getBuilderSettings();
    const resolvedPgkType = question.pgk_type || 'checkbox';
    const isMc = question.type === 'multiple_choice';
    const isPgkCheckbox = question.type === 'multiple_choice_complex' && resolvedPgkType === 'checkbox';
    const isPgkTable = question.type === 'multiple_choice_complex' && resolvedPgkType === 'table_validation';

    if (isMc) {
        question.use_key_only_mode = settings.default_mc_key_only;
    } else if (isPgkCheckbox) {
        question.use_key_only_mode = settings.default_pgk_key_only;
    }

    question.preferred_image_layout_mode = 'model1';

    if (question.image_url) {
        question.answer_layout_mode = 'model1';
        question.model2_slots = [];
        question.allow_placeholder_shuffle = false;
        question.placeholder_shuffle_user_set = false;
    } else if (isMc || isPgkCheckbox) {
        question.allow_placeholder_shuffle = settings.smart_auto_shuffle_options === true;
        question.placeholder_shuffle_user_set = false;
    }
    if (isPgkTable) {
        question.table_statement_shuffle_user_set = false;
    }
    refreshTableStatementShuffleState(question, { forceDefault: isPgkTable });

    refreshQuestionPlaceholderState(question);
}

function formatBuilderSettingsSummary(settings = getBuilderSettings()) {
    return [
        `PG default cepat: ${settings.default_mc_key_only ? 'ON' : 'OFF'}`,
        `PGK default cepat: ${settings.default_pgk_key_only ? 'ON' : 'OFF'}`,
        'Default soal gambar: Mode 1',
        `Default Acak Opsi: ${settings.smart_auto_shuffle_options ? 'ON' : 'OFF'}`,
        `Default Acak Soal: ${settings.smart_auto_shuffle_questions ? 'ON' : 'OFF'}`
    ].join(' | ');
}

function updateBuilderDefaultsSummaryText() {
    const target = document.getElementById('builder-defaults-summary');
    if (!target) return;
    target.textContent = formatBuilderSettingsSummary();
}

function openBuilderDefaultsModal() {
    const settings = getBuilderSettings();
    const mc = document.getElementById('default-mc-key-only');
    const pgk = document.getElementById('default-pgk-key-only');
    const imageMode = document.getElementById('default-image-layout-mode');
    const autoOpt = document.getElementById('smart-auto-shuffle-options');
    const autoQ = document.getElementById('smart-auto-shuffle-questions');
    const applyExisting = document.getElementById('apply-defaults-existing');

    if (mc) mc.checked = settings.default_mc_key_only;
    if (pgk) pgk.checked = settings.default_pgk_key_only;
    if (imageMode) imageMode.value = settings.default_image_layout_mode;
    if (autoOpt) autoOpt.checked = settings.smart_auto_shuffle_options;
    if (autoQ) autoQ.checked = settings.smart_auto_shuffle_questions;
    if (applyExisting) applyExisting.checked = true;

    [mc, pgk, imageMode, autoOpt, autoQ, applyExisting].forEach((el) => {
        if (!el) return;
        el.onchange = () => updateBuilderDefaultsSummaryPreview();
    });

    updateBuilderDefaultsSummaryPreview();
    openModal('builder-defaults-modal');
}

function updateBuilderDefaultsSummaryPreview() {
    const target = document.getElementById('builder-defaults-summary');
    if (!target) return;
    const draft = normalizeBuilderSettings({
        default_mc_key_only: document.getElementById('default-mc-key-only')?.checked,
        default_pgk_key_only: document.getElementById('default-pgk-key-only')?.checked,
        default_image_layout_mode: document.getElementById('default-image-layout-mode')?.value,
        smart_auto_shuffle_options: document.getElementById('smart-auto-shuffle-options')?.checked,
        smart_auto_shuffle_questions: document.getElementById('smart-auto-shuffle-questions')?.checked
    });
    target.textContent = formatBuilderSettingsSummary(draft);
}

function saveBuilderDefaults() {
    const applyToExisting = document.getElementById('apply-defaults-existing')?.checked === true;
    examData.builder_settings = normalizeBuilderSettings({
        default_mc_key_only: document.getElementById('default-mc-key-only')?.checked,
        default_pgk_key_only: document.getElementById('default-pgk-key-only')?.checked,
        default_image_layout_mode: document.getElementById('default-image-layout-mode')?.value,
        smart_auto_shuffle_options: document.getElementById('smart-auto-shuffle-options')?.checked,
        smart_auto_shuffle_questions: document.getElementById('smart-auto-shuffle-questions')?.checked
    });

    syncShuffleTogglesWithBuilderSettings(true);

    if (applyToExisting) {
        (examData.questions || []).forEach((q) => applyBuilderDefaultsToQuestion(q));
    } else {
        (examData.questions || []).forEach((q) => {
            if (!q) return;
            if (!q.image_url) {
                q.preferred_image_layout_mode = examData.builder_settings.default_image_layout_mode;
            }
            refreshQuestionPlaceholderState(q);
        });
    }

    closeModal('builder-defaults-modal');
    updateBuilderDefaultsSummaryText();
    renderQuestions();
    triggerAutoSave();
    showAlert(
        applyToExisting
            ? 'Default soal tersimpan dan diterapkan ke soal yang sudah ada.'
            : 'Default soal berhasil disimpan.',
        'success'
    );
}

function applySmartShuffleDefaultsAfterQuestionAdd() {
    syncShuffleTogglesWithBuilderSettings(false);
}

// State
let examId = null;
let examData = {
    title: 'Ujian Tanpa Judul',
    duration_minutes: 60,
    passing_score: 70,
    shuffle_questions: false,
    shuffle_options: false,  // Toggle untuk mengacak opsi jawaban (hanya untuk soal dengan opsi)
    show_results: false,  // ✅ DEFAULT: false - matches checkbox unchecked state in HTML
    allow_review: false,
    start_time: null,
    end_time: null,
    subject: '',
    exam_type: '',
    academic_year: '',
    show_teacher_name: true,
    teacher_name: '',
    builder_settings: normalizeBuilderSettings(DEFAULT_BUILDER_SETTINGS),
    questions: []
};
let saveTimeout = null;
let isSaving = false;
let activeQuestionIndex = null;
let tutorialStepIndex = 0;
let lastSavedExamSignature = null;
const AUTO_SAVE_DEBOUNCE_MS = 3500;
const AUTO_SAVE_RETRY_MS = 1500;

// Initialize
document.addEventListener('DOMContentLoaded', async () => {
    console.log('🚀 Exam Builder: Initializing...');

    // Check if editing existing exam
    const urlParams = new URLSearchParams(window.location.search);
    examId = urlParams.get('id');

    if (examId) {
        await loadExam(examId);
    } else {
        // 🕐 NEW EXAM: Initialize default times and sync all inputs
        const now = new Date();
        const duration = examData.duration_minutes || 60;
        const endTime = new Date(now.getTime() + duration * 60 * 1000);

        // Sync duration input with examData
        const durationInput = document.getElementById('exam-duration');
        if (durationInput) {
            durationInput.value = duration;
            console.log(`⏰ Duration input synced: ${duration} minutes`);
        }

        // Set time inputs
        document.getElementById('start-time').value = formatDateTimeLocal(now);
        document.getElementById('end-time').value = formatDateTimeLocal(endTime);
        examData.start_time = now.toISOString();
        examData.end_time = endTime.toISOString();
        console.log(`⏰ Default time set: ${duration}min (${now.toLocaleTimeString()} - ${endTime.toLocaleTimeString()})`);

        // 🔧 FIX: Initialize show_results from checkbox state for NEW exams
        const showResultsCheckbox = document.getElementById('show-results');
        if (showResultsCheckbox) {
            examData.show_results = showResultsCheckbox.checked;
            console.log('🔧 INIT (new exam): show_results =', examData.show_results);
        }
        examData.builder_settings = normalizeBuilderSettings(DEFAULT_BUILDER_SETTINGS);
        alignBuilderSettingsWithExamToggles();
    }

    // Bind events FIRST
    bindEvents();
    updateEmptyState();

    // Initialize academic year dropdown (sync - no API call)
    initAcademicYear();

    // Load subjects for dropdown (async with loading state)
    await loadSubjects();

    // Load and display teacher name
    await loadTeacherName();

    updateBuilderDefaultsSummaryText();

    console.log('✅ Exam Builder: Initialization complete');
});

function bindEvents() {
    // Title input
    document.getElementById('exam-title').addEventListener('input', (e) => {
        examData.title = e.target.value;
        triggerAutoSave();
    });

    // Duration input
    document.getElementById('exam-duration').addEventListener('input', (e) => {
        examData.duration_minutes = parseInt(e.target.value) || 60;

        // Auto-sync: Update end_time if start_time is set
        const startTimeInput = document.getElementById('start-time');
        const endTimeInput = document.getElementById('end-time');
        if (startTimeInput && startTimeInput.value && endTimeInput) {
            const startTime = new Date(startTimeInput.value);
            const duration = examData.duration_minutes || 60;
            const endTime = new Date(startTime.getTime() + duration * 60 * 1000);
            endTimeInput.value = formatDateTimeLocal(endTime);
        }

        triggerAutoSave();
    });

    // Start time input - auto-calculate end time
    document.addEventListener('change', (e) => {
        if (e.target.id === 'start-time') {
            const startTimeInput = document.getElementById('start-time');
            const endTimeInput = document.getElementById('end-time');
            if (startTimeInput && startTimeInput.value && endTimeInput) {
                const startTime = new Date(startTimeInput.value);
                const duration = examData.duration_minutes || 60;
                const endTime = new Date(startTime.getTime() + duration * 60 * 1000);
                endTimeInput.value = formatDateTimeLocal(endTime);
            }
        }
    });

    // Passing score input
    document.getElementById('exam-passing').addEventListener('input', (e) => {
        examData.passing_score = parseInt(e.target.value) || 70;
        triggerAutoSave();
    });

    // Shuffle toggle
    document.getElementById('shuffle-questions').addEventListener('change', (e) => {
        examData.shuffle_questions = e.target.checked;
        getBuilderSettings().smart_auto_shuffle_questions = e.target.checked;
        updateBuilderDefaultsSummaryText();
        triggerAutoSave();
    });

    // Shuffle options toggle (hanya untuk soal dengan opsi: PG, PGK, Benar/Salah, Menjodohkan)
    document.getElementById('shuffle-options').addEventListener('change', (e) => {
        examData.shuffle_options = e.target.checked;
        getBuilderSettings().smart_auto_shuffle_options = e.target.checked;
        (examData.questions || []).forEach((question) => {
            refreshQuestionPlaceholderState(question);
            refreshTableStatementShuffleState(question);
        });
        renderQuestions();
        updateBuilderDefaultsSummaryText();
        console.log(`🎲 Exam shuffle_options set to: ${e.target.checked}`);
        triggerAutoSave();
    });

    // Subject dropdown
    document.getElementById('exam-subject').addEventListener('change', (e) => {
        examData.subject = e.target.value;
        triggerAutoSave();
    });

    // Exam type custom input
    document.getElementById('exam-type-custom').addEventListener('input', (e) => {
        examData.exam_type = e.target.value;
        triggerAutoSave();
    });

    // Teacher name checkbox
    document.getElementById('show-teacher-name').addEventListener('change', (e) => {
        examData.show_teacher_name = e.target.checked;
        triggerAutoSave();
    });

    // Show results checkbox
    document.getElementById('show-results').addEventListener('change', (e) => {
        examData.show_results = e.target.checked;
        console.log('🔵 show_results checkbox changed:', e.target.checked);
        console.log('🔵 examData.show_results updated to:', examData.show_results);
        triggerAutoSave();
    });

    // Academic year dropdown
    document.getElementById('academic-year').addEventListener('change', (e) => {
        examData.academic_year = e.target.value;
        triggerAutoSave();
    });
}

// Initialize academic year dropdown with auto-generated options
function initAcademicYear() {
    const select = document.getElementById('academic-year');
    const currentYear = new Date().getFullYear();
    const currentMonth = new Date().getMonth(); // 0-11

    // Generate academic years (current year -1 to +2)
    const years = [];
    for (let i = -1; i <= 2; i++) {
        const startYear = currentYear + i;
        const endYear = startYear + 1;
        years.push(`${startYear}/${endYear}`);
    }

    // Build options
    select.innerHTML = years.map(year =>
        `<option value="${year}">📚 ${year}</option>`
    ).join('');

    // Auto-select current academic year
    // If month >= July (6), use current year as start, otherwise use previous year
    const academicStartYear = currentMonth >= 6 ? currentYear : currentYear - 1;
    const defaultYear = `${academicStartYear}/${academicStartYear + 1}`;

    select.value = defaultYear;
    examData.academic_year = defaultYear;
}

// Load subjects from API
// loadSubjects moved to end of file
// Load and display teacher name
async function loadTeacherName() {
    try {
        const user = await api.getMe();
        if (user) {
            examData.teacher_name = user.full_name || user.username;
            document.getElementById('teacher-name-display').textContent = examData.teacher_name;
        }
    } catch (error) {
        console.error('Failed to load teacher name:', error);
        // Use cached auth data as fallback
        const cachedUser = localStorage.getItem('user');
        if (cachedUser) {
            try {
                const user = JSON.parse(cachedUser);
                examData.teacher_name = user.full_name || user.username || 'Guru';
                document.getElementById('teacher-name-display').textContent = examData.teacher_name;
            } catch (e) {
                // Keep default
            }
        }
    }
}

// Handle exam type dropdown change
function handleExamTypeChange() {
    const select = document.getElementById('exam-type');
    const customInput = document.getElementById('exam-type-custom');

    if (select.value === 'custom') {
        // Show custom input
        customInput.style.display = 'block';
        customInput.focus();
        examData.exam_type = customInput.value || '';
    } else {
        // Hide custom input, use selected value
        customInput.style.display = 'none';
        examData.exam_type = select.value;
    }

    triggerAutoSave();
}

// Load existing exam
async function loadExam(id) {
    try {
        const exam = await api.getExam(id);
        console.log('📥 API Response from getExam:', {
            id: exam.id,
            title: exam.title,
            shuffle_questions: exam.shuffle_questions,
            shuffle_options: exam.shuffle_options,
            raw_response: exam
        });
        examData = {
            ...examData,
            title: exam.title,
            duration_minutes: exam.duration_minutes,
            passing_score: exam.passing_score || 70,
            shuffle_questions: exam.shuffle_questions || false,
            shuffle_options: exam.shuffle_options || false,  // Toggle untuk mengacak opsi jawaban
            show_results: exam.show_results === true, // FIX: Explicit true check
            start_time: exam.start_time,
            end_time: exam.end_time,
            subject: exam.subject || '',
            exam_type: exam.exam_type || '',
            academic_year: exam.academic_year || '',
            show_teacher_name: exam.show_teacher_name !== false,
            teacher_name: exam.teacher_name || '',
            builder_settings: normalizeBuilderSettings(exam.builder_settings || DEFAULT_BUILDER_SETTINGS),
            allowed_classes: exam.allowed_classes, // Persist for wizard
            allowed_students: exam.allowed_students // Persist for wizard
        };

        // Update UI
        document.getElementById('exam-title').value = examData.title;
        document.getElementById('exam-duration').value = examData.duration_minutes;
        document.getElementById('exam-passing').value = examData.passing_score;
        document.getElementById('shuffle-questions').checked = examData.shuffle_questions;
        document.getElementById('shuffle-options').checked = examData.shuffle_options;  // Toggle acak opsi
        alignBuilderSettingsWithExamToggles();

        console.log('📋 loadExam() - UI Updated:', {
            title: examData.title,
            shuffle_questions: examData.shuffle_questions,
            shuffle_options: examData.shuffle_options,
            'shuffle-options checkbox checked': document.getElementById('shuffle-options').checked
        });

        // Subject will be set after loadSubjects() runs
        if (examData.subject) {
            document.getElementById('exam-subject').value = examData.subject;
        }

        // Exam type
        if (examData.exam_type) {
            const typeSelect = document.getElementById('exam-type');
            const customInput = document.getElementById('exam-type-custom');

            // Check if exam_type matches a preset option
            const presetValues = ['Ujian Harian', 'Ujian Mingguan', 'Ujian Bulanan',
                'Ujian Tengah Semester', 'Ujian Semester Ganjil', 'Ujian Semester Genap', 'Ujian Akhir Madrasah'];

            if (presetValues.includes(examData.exam_type)) {
                typeSelect.value = examData.exam_type;
                customInput.style.display = 'none';
            } else {
                // It's a custom value
                typeSelect.value = 'custom';
                customInput.style.display = 'block';
                customInput.value = examData.exam_type;
            }
        }

        // Handle draft exam schedule - check if time is in the past and auto-update
        const now = new Date();
        let startTime, endTime;

        if (examData.start_time) {
            startTime = new Date(examData.start_time);
            endTime = new Date(examData.end_time);

            // Check if draft time is in the past - auto update to current time
            if (startTime < now) {
                console.log('[DRAFT] Waktu ujian sudah lewat, auto-update ke waktu sekarang');
                startTime = now;
                endTime = new Date(now.getTime() + (examData.duration_minutes || 60) * 60 * 1000);

                // Update examData with new times
                examData.start_time = startTime.toISOString();
                examData.end_time = endTime.toISOString();

                // Show notification to user
                showAlert('Waktu ujian telah diperbarui ke jadwal terkini (waktu sebelumnya sudah lewat)', 'info');
            }

            // Format for datetime-local input (converts UTC to local time)
            document.getElementById('start-time').value = formatDateTimeLocal(startTime);
            document.getElementById('end-time').value = formatDateTimeLocal(endTime);
        }

        // Academic year
        if (examData.academic_year) {
            document.getElementById('academic-year').value = examData.academic_year;
        }

        // Show teacher name checkbox
        document.getElementById('show-teacher-name').checked = examData.show_teacher_name;
        if (examData.teacher_name) {
            document.getElementById('teacher-name-display').textContent = examData.teacher_name;
        }

        // Show results checkbox
        document.getElementById('show-results').checked = examData.show_results;

        // Load questions
        const questions = await api.getQuestions(id);
        console.log('📥 [LOAD] Raw questions from server:', questions.map(q => ({
            id: q.id,
            type: q.question_type,
            pgk_type: q.pgk_type,
            stimulus: q.stimulus ? q.stimulus.substring(0, 30) + '...' : 'NULL',
            settings_pgk_type: q.question_settings?.pgk_type,
            settings_stimulus: q.question_settings?.stimulus ? q.question_settings.stimulus.substring(0, 30) + '...' : 'NULL',
            settings_statements: q.question_settings?.statements
        })));
        examData.questions = questions.map((q, i) => {
            // Initialize options based on question type
            let processedOptions = [];
            let correctAnswerIndex = null;
            let correctAnswersIndices = []; // For PGK checkbox

            // Extract settings safely
            const settings = q.question_settings || {};
            const globalDefaults = getBuilderSettings();
            // Resolve PGK Type immediately with fallback
            const resolvedPgkType = q.pgk_type || (settings && settings.pgk_type) || 'checkbox';
            const isPlaceholder = settings.is_placeholder === true;
            const placeholderSource = settings.placeholder_source || null;
            const isImagePlaceholder = isPlaceholder && (placeholderSource === 'image' || !!q.image_url);
            const answerLayoutMode = 'model1';
            const model2Slots = [];
            const allowPlaceholderShuffle = (
                isPlaceholder &&
                (!isImagePlaceholder && settings.allow_placeholder_shuffle === true)
            );
            const isKeyOnlyEligible = (
                q.question_type === 'multiple_choice' ||
                (q.question_type === 'multiple_choice_complex' && resolvedPgkType === 'checkbox')
            );

            // --- 1. HANDLE OPTIONS & CORRECT ANSWERS ---
            if (Array.isArray(q.options)) {
                if (q.question_type === 'multiple_choice_complex') {
                    // PGK Type A (Checkbox)
                    processedOptions = q.options.map((opt, idx) => {
                        if (opt.is_correct === true) correctAnswersIndices.push(idx);
                        return typeof opt === 'string' ? opt : (opt.option_text || '');
                    });
                } else {
                    // Standard single choice (MC / TF)
                    processedOptions = q.options.map((opt, idx) => {
                        if (opt.is_correct === true) correctAnswerIndex = idx;
                        return typeof opt === 'string' ? opt : (opt.option_text || '');
                    });
                }
            }

            // Pad options array if it's multiple choice or PGK checkbox to ensure UI always shows options for correct answer selection
            if (q.question_type === 'multiple_choice' || (q.question_type === 'multiple_choice_complex' && resolvedPgkType === 'checkbox')) {
                // If it was saved as placeholder (e.g., mode foto), we don't want 'A','B','C' showing up in text boxes
                if (isPlaceholder) {
                    processedOptions = processedOptions.map((opt) => (
                        isGeneratedPlaceholderOption(opt) ? '' : opt
                    ));
                }

                const highestSelectedIndex = q.question_type === 'multiple_choice'
                    ? (Number.isInteger(correctAnswerIndex) ? correctAnswerIndex : -1)
                    : (correctAnswersIndices.length > 0 ? Math.max(...correctAnswersIndices) : -1);
                const minimumOptionCount = Math.max(
                    getMinimumOptionCountByType(q.question_type, resolvedPgkType),
                    highestSelectedIndex + 1
                );

                // Ensure minimum options are visible for teacher to pick the correct answer
                while (processedOptions.length < minimumOptionCount) {
                    processedOptions.push('');
                }
            }

            // Default mode cepat aktif untuk PG/PGK-checkbox, kecuali eksplisit dimatikan.
            const inferredKeyOnlyMode = isKeyOnlyEligible
                ? (settings.use_key_only_mode !== false)
                : false;
            const effectiveLayoutMode = 'model1';
            const effectiveModel2Slots = [];
            const inferredTableStatementShuffle = resolvedPgkType === 'table_validation'
                ? (
                    typeof settings.allow_table_statement_shuffle === 'boolean'
                        ? settings.allow_table_statement_shuffle
                        : (globalDefaults.smart_auto_shuffle_options === true)
                )
                : false;

            // --- 2. RESTORE SHORT ANSWER ---
            let shortAnswerKey = '';
            if (q.question_type === 'short_answer') {
                // Try to get from settings first (new standard)
                if (settings.acceptable_answers && settings.acceptable_answers.length > 0) {
                    shortAnswerKey = settings.acceptable_answers[0];
                }
                // Fallback to older format if specific correct_answer field existed (though backend usually doesn't send it)
                else if (q.correct_answer) {
                    shortAnswerKey = q.correct_answer;
                }
            }

            // --- 3. RESTORE PGK TABLE DATA ---
            let pgkStatements = [];
            let pgkAnswers = [];
            if (q.question_type === 'multiple_choice_complex' && resolvedPgkType === 'table_validation') {
                pgkStatements = settings.statements || [];
                pgkAnswers = settings.statement_answers || [];
            }

            // --- 4. CONSTRUCT FRONTEND QUESTION OBJECT ---
            return {
                id: q.id,
                type: q.question_type,
                pgk_type: resolvedPgkType, // Important for PGK switch
                text: q.question_text,
                stimulus: q.stimulus || (q.question_settings && q.question_settings.stimulus) || '', // Important for HOTS
                options: processedOptions,

                // Correct Answers Mapping
                correct_answer: q.question_type === 'short_answer' ? shortAnswerKey :
                    (q.question_type === 'true_false' ? (correctAnswerIndex === 0 ? 'true' : 'false') : correctAnswerIndex),
                correct_answers: correctAnswersIndices, // For PGK Checkbox

                // PGK Table Data
                statements: pgkStatements,
                statement_answers: pgkAnswers,

                points: q.points || 1,
                difficulty: q.difficulty_level || 'medium',
                image_url: q.image_url || null,
                video_url: q.video_url || null,
                audio_url: q.audio_url || null,
                require_manual_grading: settings.require_manual_grading || false,
                is_placeholder: isPlaceholder,
                placeholder_source: placeholderSource,
                allow_placeholder_shuffle: allowPlaceholderShuffle,
                placeholder_shuffle_user_set: true,
                allow_table_statement_shuffle: inferredTableStatementShuffle,
                table_statement_shuffle_user_set: typeof settings.allow_table_statement_shuffle === 'boolean',
                use_key_only_mode: inferredKeyOnlyMode,
                answer_layout_mode: effectiveLayoutMode,
                model2_slots: effectiveModel2Slots,
                preferred_image_layout_mode: 'model1'
            };
        });

        console.log('✅ [LOAD] Processed questions for frontend:', examData.questions.map(q => ({
            id: q.id,
            type: q.type,
            pgk_type: q.pgk_type,
            stimulus: q.stimulus ? q.stimulus.substring(0, 30) + '...' : 'NULL',
            statements: q.statements,
            statement_answers: q.statement_answers
        })));

        // Initialize signatures so first autosave after load does not re-update unchanged exam/questions.
        lastSavedExamSignature = stableStringify(buildExamPayloadFromState());
        examData.questions.forEach((q, i) => {
            if (!q || !q.id) return;
            try {
                const { questionPayloadSignature } = buildQuestionPayloadFromState(q, i, id);
                q._last_saved_signature = questionPayloadSignature;
            } catch (signatureError) {
                console.warn(`Signature init skipped for question index ${i}:`, signatureError);
            }
        });

        renderQuestions();
    } catch (error) {
        showAlert('Gagal memuat ujian', 'danger');
        console.error(error);
    }
}


// Save functions moved to end of file to prevent duplication
// Set active question highlight

/* ===== Module: 10-question-core-rendering.js ===== */

function setActiveQuestion(index) {
    // Remove active class from all questions
    document.querySelectorAll('.question-card').forEach(card => {
        card.classList.remove('active');
    });

    // Add active class to selected question
    const activeCard = document.querySelector(`.question-card[data-index="${index}"]`);
    if (activeCard) {
        activeCard.classList.add('active');
        activeCard.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }

    activeQuestionIndex = index;
}

function getQuestionRichInput(index) {
    return document.querySelector(`.question-card[data-index="${index}"] .question-rich-input`);
}

function getQuestionFormatButtons(index) {
    return document.querySelectorAll(`.question-card[data-index="${index}"] .question-format-btn[data-format]`);
}

function isQuestionArabicInputMode(index) {
    const question = examData.questions?.[index];
    return question?.arabic_input_mode === true;
}

function setQuestionArabicInputMode(index, enabled) {
    const question = examData.questions?.[index];
    if (!question) return;
    question.arabic_input_mode = Boolean(enabled);
}

function applyQuestionInputMode(index, inputEl) {
    const input = inputEl || getQuestionRichInput(index);
    if (!input) return;
    const arabicMode = isQuestionArabicInputMode(index);
    input.classList.toggle('arabic-typing-mode', arabicMode);
    input.setAttribute('dir', arabicMode ? 'rtl' : 'ltr');
}

function safeQueryCommandState(command) {
    try {
        return document.queryCommandState(command);
    } catch (error) {
        return false;
    }
}

function isArabicSelectionActive(input) {
    const selection = window.getSelection();
    if (!selection || selection.rangeCount === 0) return false;
    const range = selection.getRangeAt(0);
    if (!input.contains(range.commonAncestorContainer)) return false;

    const anchorNode = selection.anchorNode;
    const anchorEl = anchorNode && (anchorNode.nodeType === 1 ? anchorNode : anchorNode.parentElement);
    if (anchorEl && input.contains(anchorEl) && anchorEl.closest('.rich-arabic')) return true;

    const startNode = range.startContainer;
    const startEl = startNode && (startNode.nodeType === 1 ? startNode : startNode.parentElement);
    if (startEl && input.contains(startEl) && startEl.closest('.rich-arabic')) return true;

    return false;
}

function wrapSelectionAsArabic(input) {
    const selection = window.getSelection();
    if (!selection || selection.rangeCount === 0) return false;
    const range = selection.getRangeAt(0);
    if (!input.contains(range.commonAncestorContainer) || range.collapsed) return false;

    const fragment = range.extractContents();
    const span = document.createElement('span');
    span.className = 'rich-arabic';
    span.appendChild(fragment);
    range.insertNode(span);
    range.selectNodeContents(span);
    selection.removeAllRanges();
    selection.addRange(range);
    return true;
}

function toggleArabicInputMode(index, inputEl) {
    const input = inputEl || getQuestionRichInput(index);
    if (!input) return;

    const willEnable = !isQuestionArabicInputMode(index);
    setQuestionArabicInputMode(index, willEnable);
    applyQuestionInputMode(index, input);

    if (willEnable) {
        wrapSelectionAsArabic(input);
        input.focus();
        normalizeQuestionRichInput(index, input);
    } else {
        syncQuestionRichInput(index, input);
    }
}

function updateQuestionFormatToolbarState(index, inputEl) {
    const input = inputEl || getQuestionRichInput(index);
    if (!input) return;

    const buttons = getQuestionFormatButtons(index);
    if (!buttons || buttons.length === 0) return;

    const selection = window.getSelection();
    const hasSelection = !!selection && selection.rangeCount > 0;
    const insideInput = hasSelection && input.contains(selection.getRangeAt(0).commonAncestorContainer);

    const states = {
        bold: insideInput ? safeQueryCommandState('bold') : false,
        italic: insideInput ? safeQueryCommandState('italic') : false,
        underline: insideInput ? safeQueryCommandState('underline') : false,
        arabic: isQuestionArabicInputMode(index) || (insideInput ? isArabicSelectionActive(input) : false)
    };

    buttons.forEach((button) => {
        const format = button.dataset.format || '';
        const isActive = states[format] === true;
        button.classList.toggle('is-active', isActive);
        button.setAttribute('aria-pressed', isActive ? 'true' : 'false');
    });
}

function clearQuestionFormatToolbarState(index) {
    const buttons = getQuestionFormatButtons(index);
    if (!buttons || buttons.length === 0) return;
    buttons.forEach((button) => {
        button.classList.remove('is-active');
        button.setAttribute('aria-pressed', 'false');
    });
}

let questionToolbarSelectionSyncBound = false;
function bindQuestionToolbarSelectionSync() {
    if (questionToolbarSelectionSyncBound) return;
    questionToolbarSelectionSyncBound = true;

    document.addEventListener('selectionchange', () => {
        const activeEl = document.activeElement;
        if (!activeEl || !activeEl.classList || !activeEl.classList.contains('question-rich-input')) {
            return;
        }
        const index = Number(activeEl.getAttribute('data-index'));
        if (Number.isInteger(index)) {
            updateQuestionFormatToolbarState(index, activeEl);
        }
    });
}

function focusQuestionRichInputAtEnd(input) {
    if (!input) return;
    input.focus();
    const selection = window.getSelection();
    if (!selection) return;
    const range = document.createRange();
    range.selectNodeContents(input);
    range.collapse(false);
    selection.removeAllRanges();
    selection.addRange(range);
}

function storedQuestionTextToRichHtml(text) {
    const source = text == null ? '' : String(text);
    if (!source) return '';
    return escapeHtml(source)
        .replace(/\[b\]([\s\S]*?)\[\/b\]/gi, '<strong>$1</strong>')
        .replace(/\[i\]([\s\S]*?)\[\/i\]/gi, '<em>$1</em>')
        .replace(/\[u\]([\s\S]*?)\[\/u\]/gi, '<u>$1</u>')
        .replace(/\[(?:ar|arabic)\]([\s\S]*?)\[\/(?:ar|arabic)\]/gi, '<span class="rich-arabic">$1</span>')
        .replace(/\r?\n/g, '<br>');
}

function serializeRichQuestionNode(node) {
    if (!node) return '';
    if (node.nodeType === 3) {
        return node.textContent || '';
    }
    if (node.nodeType !== 1) {
        return '';
    }

    const tag = (node.tagName || '').toLowerCase();
    if (tag === 'br') {
        return '\n';
    }

    const children = Array.from(node.childNodes || []).map((child) => serializeRichQuestionNode(child)).join('');

    if (tag === 'strong' || tag === 'b') {
        return `[b]${children}[/b]`;
    }
    if (tag === 'em' || tag === 'i') {
        return `[i]${children}[/i]`;
    }
    if (tag === 'u') {
        return `[u]${children}[/u]`;
    }
    if (tag === 'span') {
        const className = typeof node.className === 'string' ? node.className : '';
        const isArabic = /\brich-arabic\b/.test(className) || node.getAttribute('dir') === 'rtl';
        if (isArabic) {
            return `[ar]${children}[/ar]`;
        }
    }
    if (tag === 'div' || tag === 'p') {
        return `${children}\n`;
    }
    return children;
}

function normalizeRichQuestionHtmlToStoredText(html) {
    const container = document.createElement('div');
    container.innerHTML = html == null ? '' : String(html);

    let serialized = '';
    Array.from(container.childNodes || []).forEach((node) => {
        serialized += serializeRichQuestionNode(node);
    });

    return serialized
        .replace(/\u00a0/g, ' ')
        .replace(/\r/g, '')
        .replace(/[ \t]+\n/g, '\n')
        .replace(/\n{3,}/g, '\n\n')
        .trim();
}

function ensureArabicModeStoredText(index, storedText) {
    const text = storedText == null ? '' : String(storedText);
    if (!isQuestionArabicInputMode(index)) return text;
    if (!text.trim()) return text;
    if (/^\[(?:ar|arabic)\][\s\S]*\[\/(?:ar|arabic)\]$/i.test(text.trim())) return text;
    return `[ar]${text}[/ar]`;
}

function updateQuestionRichText(index, richHtml) {
    const question = examData.questions[index];
    if (!question) return;
    const normalizedStoredText = normalizeRichQuestionHtmlToStoredText(richHtml);
    const storedText = ensureArabicModeStoredText(index, normalizedStoredText);
    question.text = storedText;
    triggerAutoSave();
}

function normalizeQuestionRichInput(index, inputEl) {
    const input = inputEl || getQuestionRichInput(index);
    if (!input) return;
    const normalizedStoredText = normalizeRichQuestionHtmlToStoredText(input.innerHTML);
    const storedText = ensureArabicModeStoredText(index, normalizedStoredText);
    const normalizedHtml = storedQuestionTextToRichHtml(storedText);
    if (input.innerHTML !== normalizedHtml) {
        input.innerHTML = normalizedHtml;
    }
    updateQuestionText(index, storedText);
}

function syncQuestionRichInput(index, input) {
    const target = input || getQuestionRichInput(index);
    if (!target) return;
    updateQuestionRichText(index, target.innerHTML);
}

function handleQuestionRichPaste(event, index) {
    if (event) {
        event.preventDefault();
        event.stopPropagation();
    }
    const clipboard = event?.clipboardData || window.clipboardData;
    const plainText = clipboard ? (clipboard.getData('text/plain') || '') : '';
    if (!plainText) return;

    const safeHtml = escapeHtml(plainText).replace(/\r?\n/g, '<br>');
    if (typeof document.execCommand === 'function') {
        document.execCommand('insertHTML', false, safeHtml);
    }
    const input = getQuestionRichInput(index);
    syncQuestionRichInput(index, input);
    updateQuestionFormatToolbarState(index, input);
}

function applyArabicSelectionFormatting(index, input) {
    wrapSelectionAsArabic(input);
    syncQuestionRichInput(index, input);
    updateQuestionFormatToolbarState(index, input);
}

function applyQuestionTextFormat(index, format, event) {
    if (event) {
        event.preventDefault();
        event.stopPropagation();
    }

    const input = getQuestionRichInput(index);
    if (!input) return;
    input.focus();

    const selection = window.getSelection();
    if (selection && (selection.rangeCount === 0 || !input.contains(selection.anchorNode))) {
        focusQuestionRichInputAtEnd(input);
    }

    if (format === 'arabic') {
        toggleArabicInputMode(index, input);
        applyArabicSelectionFormatting(index, input);
        updateQuestionFormatToolbarState(index, input);
        return;
    }

    const commandMap = {
        bold: 'bold',
        italic: 'italic',
        underline: 'underline'
    };
    const command = commandMap[format];
    if (!command) return;

    if (typeof document.execCommand === 'function') {
        document.execCommand(command, false, null);
    }
    syncQuestionRichInput(index, input);
    updateQuestionFormatToolbarState(index, input);
}

// Add new question
function addQuestion(type = 'multiple_choice') {
    console.log('🆕 addQuestion called with type:', type);
    const builderDefaults = getBuilderSettings();

    // Initialize options based on question type
    let options = [];
    let correct_answer = '';
    let correct_answers = undefined;
    // Use configured points from pointsConfig (loaded from localStorage or defaults)
    let points = getPointsForType(type);
    let stimulus = null;
    let pgk_type = null;
    let statements = null;
    let statement_answers = null;
    let use_key_only_mode = false;

    if (type === 'multiple_choice') {
        options = Array(getDefaultOptionCountByType('multiple_choice')).fill('');
        correct_answer = '0';
        use_key_only_mode = builderDefaults.default_mc_key_only;
    } else if (type === 'multiple_choice_complex') {
        console.log('✅ PGK mode activated!');
        options = Array(getDefaultOptionCountByType('multiple_choice_complex', 'checkbox')).fill('');
        correct_answers = [];  // Array for multiple correct answers
        stimulus = '';  // Wajib untuk PGK
        pgk_type = 'checkbox';  // Default: checkbox (Tipe A)
        use_key_only_mode = builderDefaults.default_pgk_key_only;
    } else if (type === 'true_false') {
        correct_answer = 'true';
    }

    const question = {
        id: null,
        type: type,
        text: '',
        stimulus: stimulus,  // Tambahan untuk PGK
        pgk_type: pgk_type,  // Tambahan untuk PGK (checkbox/table_validation)
        statements: statements,  // Untuk PGK tabel validasi
        statement_answers: statement_answers,  // Untuk PGK tabel validasi
        image_url: null,
        video_url: null,
        audio_url: null,
        options: options,
        correct_answer: correct_answer,
        correct_answers: correct_answers,
        points: points,
        is_placeholder: false,
        placeholder_source: null,
        allow_placeholder_shuffle: false,
        placeholder_shuffle_user_set: false,
        allow_table_statement_shuffle: builderDefaults.smart_auto_shuffle_options === true,
        table_statement_shuffle_user_set: false,
        use_key_only_mode: use_key_only_mode,
        arabic_input_mode: false,
        answer_layout_mode: 'model1',
        model2_slots: [],
        preferred_image_layout_mode: builderDefaults.default_image_layout_mode
    };

    refreshQuestionPlaceholderState(question);
    examData.questions.push(question);
    renderQuestions();
    updateEmptyState();

    // Focus on new question
    const newIndex = examData.questions.length - 1;
    setActiveQuestion(newIndex);

    setTimeout(() => {
        const input = getQuestionRichInput(newIndex);
        if (input) {
            applyQuestionInputMode(newIndex, input);
            focusQuestionRichInputAtEnd(input);
            updateQuestionFormatToolbarState(newIndex, input);
        }
    }, 100);

    applySmartShuffleDefaultsAfterQuestionAdd();
    triggerAutoSave();
}

function countRealOptionTexts(options = []) {
    return (options || []).filter((opt) => {
        const text = (typeof opt === 'string' ? opt : (opt?.option_text || opt?.text || '')).trim();
        if (!text) return false;
        // Placeholder auto (A, B, C ... Z, A2, B2, dst) tidak dihitung sebagai teks opsi manual.
        return !isGeneratedPlaceholderOption(text);
    }).length;
}

function refreshQuestionPlaceholderState(question) {
    if (!question) return;
    const builderDefaults = getBuilderSettings();
    question.preferred_image_layout_mode = 'model1';

    const resolvedPgkType = question.pgk_type || 'checkbox';
    const isMc = question.type === 'multiple_choice';
    const isPgkCheckbox = question.type === 'multiple_choice_complex' && resolvedPgkType === 'checkbox';

    if (!isMc && !isPgkCheckbox) {
        question.is_placeholder = false;
        question.placeholder_source = null;
        question.allow_placeholder_shuffle = false;
        question.placeholder_shuffle_user_set = false;
        return;
    }

    const hasValidOptions = countRealOptionTexts(question.options || []) > 0;
    const hasEmbeddedOptions = hasEmbeddedOptionsFromQuestionText(question.text);
    const hasImage = !!question.image_url;

    let hasSelectedKey = false;
    if (isMc) {
        const parsed = parseInt(question.correct_answer, 10);
        hasSelectedKey = (
            question.correct_answer !== null &&
            question.correct_answer !== undefined &&
            question.correct_answer !== '' &&
            question.correct_answer !== -1 &&
            !Number.isNaN(parsed)
        );
    } else if (isPgkCheckbox) {
        hasSelectedKey = Array.isArray(question.correct_answers) && question.correct_answers.length >= 2;
    }

    const isPlaceholder = !hasValidOptions && (hasImage || hasEmbeddedOptions || hasSelectedKey);
    let placeholderSource = null;
    if (isPlaceholder) {
        if (hasImage) {
            placeholderSource = 'image';
        } else if (hasEmbeddedOptions) {
            placeholderSource = 'question_text';
        } else {
            placeholderSource = 'auto_no_option';
        }
    }

    const normalizedLayoutMode = 'model1';
    const normalizedModel2Slots = [];
    const allowImageShuffle = false;
    const autoDefaultShuffle = builderDefaults.smart_auto_shuffle_options === true;
    const userSetShuffle = question.placeholder_shuffle_user_set === true;
    let requestedNonImageShuffle = question.allow_placeholder_shuffle === true;
    if (isPlaceholder && placeholderSource !== 'image' && !userSetShuffle) {
        requestedNonImageShuffle = autoDefaultShuffle;
    }
    const allowPlaceholderShuffle = (
        isPlaceholder &&
        (
            allowImageShuffle ||
            (placeholderSource !== 'image' && requestedNonImageShuffle === true)
        )
    );

    question.is_placeholder = isPlaceholder;
    question.placeholder_source = placeholderSource;
    question.answer_layout_mode = normalizedLayoutMode;
    question.model2_slots = normalizedModel2Slots;
    question.allow_placeholder_shuffle = allowPlaceholderShuffle;
}

function refreshTableStatementShuffleState(question, options = {}) {
    if (!question) return;
    const resolvedPgkType = question.pgk_type || 'checkbox';
    const isTableType = question.type === 'multiple_choice_complex' && resolvedPgkType === 'table_validation';
    if (!isTableType) return;

    const autoDefault = getBuilderSettings().smart_auto_shuffle_options === true;
    const forceDefault = options.forceDefault === true;
    const userSet = question.table_statement_shuffle_user_set === true;

    if (forceDefault || !userSet) {
        question.allow_table_statement_shuffle = autoDefault;
        if (forceDefault) {
            question.table_statement_shuffle_user_set = false;
        }
        return;
    }

    if (typeof question.allow_table_statement_shuffle !== 'boolean') {
        question.allow_table_statement_shuffle = autoDefault;
    }
}

function getOptionLabel(index) {
    const safeIndex = Math.max(0, Number(index) || 0);
    const letter = String.fromCharCode(65 + (safeIndex % 26));
    const cycle = Math.floor(safeIndex / 26);
    return cycle === 0 ? letter : `${letter}${cycle + 1}`;
}

function buildPlaceholderLabels(count) {
    const safeCount = Math.max(0, Number(count) || 0);
    return Array.from({ length: safeCount }, (_, idx) => getOptionLabel(idx));
}

function isGeneratedPlaceholderOption(value) {
    const text = String(value || '').trim().toUpperCase();
    if (!text) return false;
    return /^[A-Z](?:[2-9][0-9]*)?$/.test(text);
}

function getMinimumOptionCountByType(type, pgkType = 'checkbox') {
    if (type === 'multiple_choice') return 3; // A, B, C minimum
    if (type === 'multiple_choice_complex' && (pgkType || 'checkbox') === 'checkbox') return 4; // A, B, C, D minimum
    return 0;
}

function getDefaultOptionCountByType(type, pgkType = 'checkbox') {
    if (type === 'multiple_choice') return 4; // Default A-D
    if (type === 'multiple_choice_complex' && (pgkType || 'checkbox') === 'checkbox') return 5; // Default A-E
    return getMinimumOptionCountByType(type, pgkType);
}

function getMinimumOptionCount(question) {
    if (!question) return 0;
    const type = question.type || question.question_type || '';
    const pgkType = question.pgk_type || question?.question_settings?.pgk_type || 'checkbox';
    return getMinimumOptionCountByType(type, pgkType);
}

function ensureOptionSlots(question, minimum = null) {
    if (!question) return;
    if (!Array.isArray(question.options)) {
        question.options = [];
    }
    const resolvedMinimum = (
        Number.isFinite(minimum)
            ? Math.max(0, Number(minimum))
            : getMinimumOptionCount(question)
    );
    while (question.options.length < resolvedMinimum) {
        question.options.push('');
    }
}

function isModel2Eligible(question) {
    return false;
}

function getDefaultModel2Slots(slotCount) {
    const count = Math.max(slotCount || 0, 4);
    if (count <= 4) {
        return [
            { slot: 0, x: 20, y: 20 },
            { slot: 1, x: 80, y: 20 },
            { slot: 2, x: 20, y: 78 },
            { slot: 3, x: 80, y: 78 }
        ];
    }
    if (count === 5) {
        return [
            { slot: 0, x: 18, y: 18 },
            { slot: 1, x: 82, y: 18 },
            { slot: 2, x: 18, y: 50 },
            { slot: 3, x: 82, y: 50 },
            { slot: 4, x: 50, y: 82 }
        ];
    }
    const slots = [];
    const cols = 3;
    const rows = Math.ceil(count / cols);
    for (let i = 0; i < count; i++) {
        const col = i % cols;
        const row = Math.floor(i / cols);
        slots.push({
            slot: i,
            x: 12 + (col * (76 / Math.max(cols - 1, 1))),
            y: 14 + (row * (72 / Math.max(rows - 1, 1)))
        });
    }
    return slots;
}

function normalizeModel2Slots(question) {
    if (!question) return [];
    const optionCount = Math.max((question.options || []).length, 4);
    let slots = Array.isArray(question.model2_slots) ? question.model2_slots : [];
    if (slots.length < optionCount) {
        slots = getDefaultModel2Slots(optionCount);
    }
    return slots
        .slice(0, optionCount)
        .map((item, index) => ({
            slot: index,
            x: Number(item?.x ?? 50),
            y: Number(item?.y ?? 50)
        }));
}

function getPlaceholderSource(question) {
    if (question && question.placeholder_source) {
        return question.placeholder_source;
    }
    if (question && question.is_placeholder && question.image_url) {
        return 'image';
    }
    return null;
}

function getPlaceholderShuffleState(question) {
    const isPlaceholder = question?.is_placeholder === true;
    const source = getPlaceholderSource(question);
    const isImagePlaceholder = isPlaceholder && (source === 'image' || !!question?.image_url);
    const model2Active = false;
    const canToggle = isPlaceholder && !isImagePlaceholder;
    const allowShuffle = canToggle && question?.allow_placeholder_shuffle === true;
    return { isPlaceholder, source, isImagePlaceholder, canToggle, allowShuffle, model2Active };
}

function getPlaceholderShuffleNoticeHtml(question, index) {
    const state = getPlaceholderShuffleState(question);
    if (!state.isPlaceholder) return '';

    const sourceLabelMap = {
        image: 'Soal pakai foto + teks opsi kosong',
        question_text: 'Asal opsi: dari teks soal (A/B/C...)',
        auto_no_option: 'Asal opsi: dari kunci jawaban'
    };
    const sourceLabel = sourceLabelMap[state.source] || 'Asal opsi: otomatis';
    const statusText = state.isImagePlaceholder
        ? 'Opsi otomatis tidak diacak pada soal bergambar ini.'
        : (state.allowShuffle
            ? 'Opsi otomatis ini ikut diacak saat "Acak Opsi" aktif.'
            : 'Opsi otomatis ini tidak diacak.');
    const statusColor = state.allowShuffle ? 'var(--success)' : 'var(--warning)';
    const statusIcon = state.allowShuffle ? 'fa-check-circle' : 'fa-triangle-exclamation';

    let toggleHtml = '';
    if (state.canToggle) {
        const defaultAutoShuffle = getBuilderSettings().smart_auto_shuffle_options === true;
        toggleHtml = `
            <label style="display:flex; align-items:center; gap:0.45rem; margin-top:0.4rem; cursor:pointer;">
                <input type="checkbox"
                       ${state.allowShuffle ? 'checked' : ''}
                       onchange="togglePlaceholderShuffle(${index}, this.checked)"
                       onclick="event.stopPropagation()">
                <span style="font-size:0.78rem; color: var(--text-secondary);">Centang jika opsi otomatis ini ingin diacak</span>
            </label>
            <small style="display:block; margin-top:0.25rem; color: var(--text-secondary);">
                ${defaultAutoShuffle
                ? 'Default Acak Opsi sedang ON, jadi biasanya ini otomatis tercentang.'
                : 'Aktifkan Auto Acak Opsi di Pengaturan Default Soal jika ingin centang otomatis.'}
            </small>
        `;
    } else {
        toggleHtml = `
            <small style="display:block; margin-top:0.4rem; color: var(--text-secondary);">
                Karena soal pakai gambar dan teks opsi kosong, sistem membuat label otomatis (A/B/C/...) dengan urutan tetap.
            </small>
            <small style="display:block; margin-top:0.2rem; color: var(--text-secondary);">
                Jika Anda mengisi teks opsi manual, status "opsi otomatis" ini hilang dan pengacakan akan mengikuti toggle global.
            </small>
        `;
    }

    return `
        <div style="margin-bottom:0.6rem; padding:0.55rem 0.65rem; border:1px solid rgba(245, 158, 11, 0.35); border-radius:0.45rem; background:rgba(245, 158, 11, 0.08);">
            <div style="display:flex; align-items:center; gap:0.45rem; font-size:0.8rem; color:${statusColor};">
                <i class="fas ${statusIcon}"></i>
                <strong>${statusText}</strong>
                <span style="color: var(--text-secondary); font-weight:500;">(${sourceLabel})</span>
            </div>
            ${toggleHtml}
        </div>
    `;
}

function getLayoutModeControlsHtml(question, index) {
    const hasImage = !!question?.image_url;
    return `
        <div style="margin-bottom:0.55rem; padding:0.55rem 0.65rem; border:1px solid rgba(59,130,246,0.35); border-radius:0.45rem; background:rgba(59,130,246,0.08);">
            <div style="display:flex; align-items:center; gap:0.5rem; margin-bottom:0.45rem;">
                <i class="fas fa-layer-group" style="color: #60a5fa;"></i>
                <strong style="font-size:0.82rem; color: var(--text-primary);">Mode Tampilan Jawaban</strong>
            </div>
            <small style="color:var(--text-secondary);">
                Sistem disederhanakan: hanya <strong style="color:var(--text-primary);">Mode 1 (normal)</strong> yang digunakan.${hasImage ? ' Pada soal gambar, urutan tetap hanya berlaku jika opsi masih otomatis/teks kosong.' : ''}
            </small>
        </div>
    `;
}

function getTableValidationShuffleNoticeHtml(question, index) {
    if (!question || question.type !== 'multiple_choice_complex' || (question.pgk_type || 'checkbox') !== 'table_validation') {
        return '';
    }
    const hasImage = !!question.image_url;
    const allowed = question.allow_table_statement_shuffle !== false;
    const statusText = allowed
        ? 'Urutan pernyataan soal ini ikut diacak.'
        : 'Urutan pernyataan soal ini tidak diacak.';
    const statusColor = allowed ? 'var(--success)' : 'var(--warning)';
    const statusIcon = allowed ? 'fa-check-circle' : 'fa-triangle-exclamation';

    if (hasImage) {
        return `
            <div style="margin-bottom:0.6rem; padding:0.55rem 0.65rem; border:1px solid rgba(245, 158, 11, 0.35); border-radius:0.45rem; background:rgba(245, 158, 11, 0.08);">
                <div style="display:flex; align-items:center; gap:0.45rem; font-size:0.8rem; color:var(--warning);">
                    <i class="fas fa-info-circle"></i>
                    <strong>Soal tabel berbasis gambar tidak diacak.</strong>
                </div>
                <small style="display:block; margin-top:0.35rem; color: var(--text-secondary);">
                    Urutan baris dibuat tetap supaya titik/jawaban gambar tidak tertukar.
                </small>
            </div>
        `;
    }

    return `
        <div style="margin-bottom:0.6rem; padding:0.55rem 0.65rem; border:1px solid rgba(245, 158, 11, 0.35); border-radius:0.45rem; background:rgba(245, 158, 11, 0.08);">
            <div style="display:flex; align-items:center; gap:0.45rem; font-size:0.8rem; color:${statusColor};">
                <i class="fas ${statusIcon}"></i>
                <strong>${statusText}</strong>
                <span style="color: var(--text-secondary); font-weight:500;">(Tipe B - Tabel Validasi)</span>
            </div>
            <label style="display:flex; align-items:center; gap:0.45rem; margin-top:0.4rem; cursor:pointer;">
                <input type="checkbox"
                       ${allowed ? 'checked' : ''}
                       onchange="toggleTableStatementShuffle(${index}, this.checked)"
                       onclick="event.stopPropagation()">
                <span style="font-size:0.78rem; color: var(--text-secondary);">Centang kalau urutan pernyataan ingin diacak</span>
            </label>
            <small style="display:block; margin-top:0.25rem; color: var(--text-secondary);">
                Berlaku jika toggle global "Acak Opsi" aktif.
            </small>
        </div>
    `;
}

function togglePlaceholderShuffle(questionIndex, isEnabled) {
    const question = examData.questions[questionIndex];
    if (!question) return;

    if (question.is_placeholder !== true) {
        showAlert('Soal ini tidak memakai opsi otomatis.', 'warning');
        return;
    }

    const state = getPlaceholderShuffleState(question);
    if (!state.canToggle) {
        question.allow_placeholder_shuffle = false;
        question.placeholder_shuffle_user_set = true;
        showAlert('Soal bergambar: opsi otomatis tidak bisa diacak.', 'info');
        renderQuestions();
        triggerAutoSave();
        return;
    }

    question.allow_placeholder_shuffle = Boolean(isEnabled);
    question.placeholder_shuffle_user_set = true;
    renderQuestions();
    triggerAutoSave();
}

function toggleTableStatementShuffle(questionIndex, isEnabled) {
    const question = examData.questions[questionIndex];
    if (!question) return;

    const isTableType = question.type === 'multiple_choice_complex' && (question.pgk_type || 'checkbox') === 'table_validation';
    if (!isTableType) {
        showAlert('Pengaturan ini hanya untuk PGK Tipe B (Tabel Validasi).', 'warning');
        return;
    }
    if (question.image_url) {
        showAlert('Soal tabel berbasis gambar tidak diacak demi keamanan mapping.', 'info');
        return;
    }

    question.allow_table_statement_shuffle = Boolean(isEnabled);
    question.table_statement_shuffle_user_set = true;
    renderQuestions();
    triggerAutoSave();
}

// Render all questions
// Render all questions
function renderQuestions() {
    console.log('🔄 Rendering questions...');
    const container = document.getElementById('questions-container');

    if (!container) {
        console.error('❌ FATAL: questions-container not found in DOM!');
        return;
    }

    console.log('📊 Current questions:', examData.questions);

    const html = examData.questions.map((q, index) => {
        refreshQuestionPlaceholderState(q);
        refreshTableStatementShuffleState(q);
        try {
            return generateQuestionCard(q, index);
        } catch (e) {
            console.error('❌ Error generating card for question', index, e);
            return `<div class="error-card">Error rendering question ${index + 1}</div>`;
        }
    }).join('');

    console.log('📝 Generated HTML length:', html.length);
    if (html.length === 0 && examData.questions.length > 0) {
        console.warn('⚠️ HTML is empty but questions exist!');
    }

    container.innerHTML = html;
    console.log('✅ HTML injected into container');
    bindQuestionToolbarSelectionSync();

    // Auto-resize semua textarea pertanyaan setelah render
    // (termasuk soal yang sudah ada teks panjang dari load sebelumnya)
    requestAnimationFrame(() => {
        container.querySelectorAll('textarea').forEach(ta => autoResize(ta));
    });

    updateEmptyState();
}

// Generate question card HTML
function generateQuestionCard(question, index) {
    const typeOptions = `
        <option value="multiple_choice" ${question.type === 'multiple_choice' ? 'selected' : ''}>Pilihan Ganda</option>
        <option value="multiple_choice_complex" ${question.type === 'multiple_choice_complex' ? 'selected' : ''}>Pilihan Ganda Kompleks</option>
        <option value="short_answer" ${question.type === 'short_answer' ? 'selected' : ''}>Isian Singkat</option>
        <option value="essay" ${question.type === 'essay' ? 'selected' : ''}>Essay</option>
        <option value="true_false" ${question.type === 'true_false' ? 'selected' : ''}>Benar/Salah</option>
    `;

    let optionsHtml = '';

    if (question.type === 'multiple_choice') {
        const hasImage = !!question.image_url;
        const useKeyOnlyMode = question.use_key_only_mode === true;
        ensureOptionSlots(question, getMinimumOptionCount(question));
        const imageUsesAutoOptions = hasImage && question.is_placeholder === true;
        const imageOptionBadge = hasImage
            ? (imageUsesAutoOptions
                ? '<span style="color: var(--success); font-size: 0.75rem;"><i class="fas fa-check-circle"></i> Opsi otomatis dari foto (teks opsi kosong)</span>'
                : '<span style="color: var(--info); font-size: 0.75rem;"><i class="fas fa-list-check"></i> Soal foto + teks opsi manual</span>')
            : '';
        const placeholderShuffleNotice = getPlaceholderShuffleNoticeHtml(question, index);
        const model2Controls = getLayoutModeControlsHtml(question, index);
        optionsHtml = `
            <div class="options-header" style="margin-bottom: 0.5rem; display: flex; align-items: center; justify-content: space-between;">
                <label style="font-weight: 600; font-size: 0.9rem; color: var(--text-primary);">
                    <i class="fas fa-list-ul" style="color: var(--primary); margin-right: 0.5rem;"></i>
                    Opsi Jawaban ${imageOptionBadge}
                </label>
                <small style="color: ${hasImage ? 'var(--warning)' : 'var(--danger)'};">
                    Wajib pilih 1 kunci jawaban
                </small>
            </div>
            <label style="display:flex; align-items:center; gap:0.5rem; margin-bottom:0.55rem; cursor:pointer;">
                <input type="checkbox"
                       ${useKeyOnlyMode ? 'checked' : ''}
                       onchange="toggleKeyOnlyMode(${index}, this.checked)"
                       onclick="event.stopPropagation()">
                <span style="font-size:0.82rem; color: var(--text-secondary);">Mode cepat: pilih kunci saja (teks opsi opsional)</span>
            </label>
            ${placeholderShuffleNotice}
            ${model2Controls}
            <div class="options-container">
                ${question.options.map((opt, optIndex) => `
                    <div class="option-item ${question.correct_answer == optIndex ? 'correct-answer' : ''}">
                        <div class="option-label">${getOptionLabel(optIndex)}</div>
                        <div class="option-radio ${question.correct_answer == optIndex ? 'correct' : ''}"
                             onclick="setCorrectAnswer(${index}, ${optIndex})"
                             title="Klik untuk tandai sebagai jawaban benar">
                            ${question.correct_answer == optIndex ? '<i class="fas fa-check"></i>' : ''}
                        </div>
                        ${useKeyOnlyMode
                ? `<div style="flex:1; color: var(--text-secondary); font-size:0.82rem;">Label ${getOptionLabel(optIndex)} (tanpa teks opsi)</div>`
                : `<input type="text" class="option-input" value="${escapeHtml(opt)}"
                               placeholder="Tulis isi opsinya..."
                               oninput="updateOption(${index}, ${optIndex}, this.value)">`
            }
                        <button class="option-delete" onclick="deleteOption(${index}, ${optIndex})" title="Hapus opsi">
                            <i class="fas fa-times"></i>
                        </button>
                    </div>
                `).join('')}
                <button class="add-option-btn" onclick="addOption(${index})">
                    <i class="fas fa-plus"></i> ${useKeyOnlyMode ? 'Tambah label opsi' : 'Tambah opsi'}
                </button>
                ${useKeyOnlyMode ? '<small style="color: var(--text-secondary); display:block; margin-top:0.45rem;">Guru cukup pilih kunci jawaban. Isi teks opsi tidak wajib.</small>' : ''}
            </div>
        `;
    } else if (question.type === 'essay') {
        optionsHtml = `
            <div class="essay-preview">
                <i class="fas fa-align-left"></i> Siswa akan menjawab dengan teks panjang
            </div>
        `;
    } else if (question.type === 'true_false') {
        optionsHtml = `
            <div class="tf-options">
                <div class="tf-option true ${question.correct_answer === 'true' ? 'correct' : ''}"
                     onclick="setTFAnswer(${index}, 'true')">
                    <i class="fas fa-check"></i>
                    <div>Benar</div>
                </div>
                <div class="tf-option false ${question.correct_answer === 'false' ? 'correct' : ''}"
                     onclick="setTFAnswer(${index}, 'false')">
                    <i class="fas fa-times"></i>
                    <div>Salah</div>
                </div>
            </div>
        `;
    } else if (question.type === 'short_answer') {
        const isManualMode = question.require_manual_grading || false;
        optionsHtml = `
            <div class="short-answer-preview">
                <label style="font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 0.5rem; display: block;">Kunci Jawaban:</label>
                <input type="text" class="form-control" value="${escapeHtml(question.correct_answer || '')}"
                       placeholder="Ketik kunci jawaban..."
                       oninput="updateShortAnswer(${index}, this.value)"
                       onclick="event.stopPropagation()"
                       style="background: var(--dark); border: 1px solid var(--border-color); margin-bottom: 1rem;">

                <!-- Toggle Manual Grading -->
                <div style="background: rgba(99, 102, 241, 0.05); border: 1px solid rgba(99, 102, 241, 0.2); border-radius: 0.5rem; padding: 0.75rem; margin-top: 1rem;">
                    <label style="display: flex; align-items: center; gap: 0.75rem; cursor: pointer; margin: 0;">
                        <input type="checkbox"
                               ${isManualMode ? 'checked' : ''}
                               onchange="toggleManualGrading(${index}, this.checked)"
                               onclick="event.stopPropagation()"
                               style="width: 18px; height: 18px; accent-color: var(--primary); cursor: pointer;">
                        <div style="flex: 1;">
                            <div style="font-weight: 600; color: var(--text-primary); font-size: 0.9rem;">Periksa Manual</div>
                            <small style="color: var(--text-secondary); display: block; margin-top: 0.25rem;">
                                ${isManualMode
                ? '✅ Soal ini akan diperiksa manual meskipun ada kunci jawaban'
                : 'Sistem akan memeriksa otomatis berdasarkan kunci jawaban'}
                            </small>
                        </div>
                        <i class="fas ${isManualMode ? 'fa-user-check' : 'fa-robot'}" style="font-size: 1.25rem; color: ${isManualMode ? 'var(--warning)' : 'var(--primary)'};"></i>
                    </label>
                </div>

                <small style="color: var(--text-secondary); margin-top: 0.5rem; display: block;">Siswa akan mengetik jawaban singkat</small>
            </div>
        `;
    } else if (question.type === 'multiple_choice_complex') {
        // Multiple Choice Complex - Professional AKM Style
        const currentPgkType = question.pgk_type || 'checkbox';
        const pgkKeyOnlyMode = question.use_key_only_mode === true;
        if (currentPgkType === 'checkbox') {
            ensureOptionSlots(question, getMinimumOptionCount(question));
        }
        // Stimulus dianggap sudah terisi ("aman") jika teks stimulus ada ATAU jika sudah upload foto soal
        const needsStimulus = (!question.stimulus || question.stimulus.trim() === '') && !question.image_url;

        optionsHtml = `
            <div class="complex-choice-builder">
                <!-- Header dengan badge HOTS -->
                <div class="complex-choice-header" style="margin-bottom: 1rem; padding: 0.75rem; background: linear-gradient(135deg, rgba(139, 92, 246, 0.1), rgba(139, 92, 246, 0.05)); border-radius: 0.5rem; border: 1px solid rgba(139, 92, 246, 0.2);">
                    <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 0.5rem; margin-bottom: 0.5rem;">
                        <div style="display: flex; align-items: center; gap: 0.5rem; color: #a78bfa;">
                            <i class="fas fa-check-double"></i>
                            <span style="font-weight: 600;">Pilihan Ganda Kompleks (PGK)</span>
                            <span style="background: linear-gradient(135deg, #f093fb, #f5576c); padding: 0.15rem 0.5rem; border-radius: 0.25rem; font-size: 0.7rem; color: white;">HOTS</span>
                        </div>
                        <select onchange="changePGKType(${index}, this.value)"
                                onclick="event.stopPropagation()"
                                style="padding: 0.35rem 0.75rem; background: var(--dark-lighter); border: 1px solid var(--border-color); border-radius: 0.375rem; color: var(--text-primary); font-size: 0.85rem; cursor: pointer;">
                            <option value="checkbox" ${currentPgkType === 'checkbox' ? 'selected' : ''}>📋 Tipe A: Multiple Response</option>
                            <option value="table_validation" ${currentPgkType === 'table_validation' ? 'selected' : ''}>✅ Tipe B: Tabel Validasi</option>
                        </select>
                    </div>
                    <small style="color: var(--text-secondary); display: block;">
                        ${currentPgkType === 'checkbox' ? 'Siswa memilih semua jawaban yang benar (min. 2 jawaban benar)' : 'Siswa menilai setiap pernyataan Benar/Salah'}
                    </small>
                    ${currentPgkType === 'checkbox'
                ? `<small style="display:block; margin-top:0.35rem; color:${pgkKeyOnlyMode ? 'var(--success)' : 'var(--warning)'};">
                            <i class="fas ${pgkKeyOnlyMode ? 'fa-check-circle' : 'fa-exclamation-circle'}"></i>
                            Mode cepat PGK: ${pgkKeyOnlyMode ? 'AKTIF' : 'NONAKTIF'}
                        </small>`
                : ''}
                </div>

                <!-- Stimulus (WAJIB untuk PGK) -->
                <div style="margin-bottom: 1rem;">
                    <label style="display: flex; align-items: center; gap: 0.5rem; font-weight: 600; margin-bottom: 0.5rem; font-size: 0.9rem;">
                        <i class="fas fa-book-open" style="color: var(--warning);"></i>
                        <span>Stimulus / Konteks (Wajib)</span>
                        ${needsStimulus ? '<span style="color: var(--danger); font-size: 0.75rem; font-weight: 500;">⚠ Belum diisi</span>' : '<span style="color: var(--success); font-size: 0.75rem;"><i class="fas fa-check-circle"></i></span>'}
                    </label>
                    <textarea
                        class="form-control"
                        placeholder="Berikan konteks/bacaan/data untuk soal HOTS. Contoh: grafik, tabel, kasus, atau bacaan singkat..."
                        oninput="updateStimulus(${index}, this.value); autoResize(this)"
                        onclick="event.stopPropagation()"
                        rows="3"
                        style="background: var(--dark-lighter); border: ${needsStimulus ? '2px solid var(--danger)' : '1px solid var(--border-color)'}; font-size: 0.9rem; min-height: 80px; max-height: 200px; overflow-y: auto;"
                    >${escapeHtml(question.stimulus || '')}</textarea>
                    ${needsStimulus ? '<small style="color: var(--danger); margin-top: 0.25rem; display: block;"><i class="fas fa-exclamation-triangle"></i> PGK memerlukan stimulus untuk mengukur HOTS</small>' : ''}
                </div>

                <!-- Content based on PGK Type -->
                ${currentPgkType === 'checkbox' ? `
                <!-- TIPE A: Multiple Response (Checkbox) -->
                    <!-- Options List -->
                    <label style="display: block; font-weight: 600; margin-bottom: 0.5rem; font-size: 0.9rem; margin-top: 1rem;">
                        <i class="fas fa-list-check"></i> Opsi Jawaban (Centang yang benar)
                        ${question.image_url
                ? (question.is_placeholder === true
                    ? '<span style="color: var(--success); font-size: 0.75rem; margin-left: 0.5rem;"><i class="fas fa-check-circle"></i> Opsi otomatis dari foto (teks opsi kosong)</span>'
                    : '<span style="color: var(--info); font-size: 0.75rem; margin-left: 0.5rem;"><i class="fas fa-list-check"></i> Soal foto + teks opsi manual</span>')
                : ''}
                    </label>
                    <label style="display:flex; align-items:center; gap:0.5rem; margin-bottom:0.55rem; cursor:pointer;">
                        <input type="checkbox"
                               ${question.use_key_only_mode === true ? 'checked' : ''}
                               onchange="toggleKeyOnlyMode(${index}, this.checked)"
                               onclick="event.stopPropagation()">
                        <span style="font-size:0.82rem; color: var(--text-secondary);">Mode cepat: centang kunci saja (teks opsi opsional)</span>
                    </label>
                    ${getLayoutModeControlsHtml(question, index)}
                    ${getPlaceholderShuffleNoticeHtml(question, index)}
                    <div class="pgk-checkbox-options">
                    ${(question.options || []).map((opt, optIndex) => `
                        <div class="option-item" style="display: flex; align-items: center; gap: 0.75rem; padding: 0.75rem; background: var(--dark-lighter); border-radius: 0.5rem; margin-bottom: 0.5rem; ${(question.correct_answers || []).includes(optIndex) ? 'border: 2px solid var(--success);' : 'border: 1px solid var(--border-color);'}">
                            <input type="checkbox"
                                   id="complex_opt_${index}_${optIndex}"
                                   ${(question.correct_answers || []).includes(optIndex) ? 'checked' : ''}
                                   onclick="toggleComplexAnswer(${index}, ${optIndex}); event.stopPropagation();"
                                   style="width: 20px; height: 20px; accent-color: #22c55e; cursor: pointer; flex-shrink: 0;">
                            <div style="display: flex; align-items: center; gap: 0.5rem; flex: 1;">
                                <span style="font-weight: 600; color: var(--text-secondary); min-width: 24px;">${getOptionLabel(optIndex)}.</span>
                                ${question.use_key_only_mode === true
                ? `<div style="flex:1; color: var(--text-secondary); font-size:0.82rem;">Label ${getOptionLabel(optIndex)} (tanpa teks opsi)</div>`
                : `<input type="text" class="option-input" value="${escapeHtml(typeof opt === 'string' ? opt : (opt.text || ''))}"
                                       placeholder="Tulis isi opsinya..."
                                       oninput="updateComplexOption(${index}, ${optIndex}, this.value)"
                                       onclick="event.stopPropagation()"
                                       style="flex: 1; background: transparent; border: none; color: var(--text-primary); outline: none; padding: 0;">`}
                            </div>
                            <button class="option-delete" onclick="event.stopPropagation(); deleteComplexOption(${index}, ${optIndex})" title="Hapus opsi" style="background: rgba(239,68,68,0.1); color: var(--danger); border: none; width: 28px; height: 28px; border-radius: 4px; cursor: pointer; flex-shrink: 0;">
                                <i class="fas fa-times"></i>
                            </button>
                        </div>
                    `).join('')}
                    <button class="add-option-btn" onclick="event.stopPropagation(); addComplexOption(${index})" style="margin-top: 0.5rem; width: 100%; padding: 0.75rem; background: rgba(99,102,241,0.1); border: 1px dashed rgba(99,102,241,0.3); border-radius: 0.5rem; color: var(--primary); font-size: 0.9rem; font-weight: 500; cursor: pointer;">
                        <i class="fas fa-plus"></i> ${question.use_key_only_mode === true ? 'Tambah Label Opsi' : 'Tambah Opsi'}
                    </button>
                    ${question.use_key_only_mode === true ? '<small style="color: var(--text-secondary); margin-top:0.45rem; display:block;">Centang saja jawaban yang benar. Isi teks opsi tidak wajib.</small>' : ''}
                    ${(question.correct_answers || []).length < 2 ? '<small style="color: var(--danger); margin-top: 0.5rem; display: block;"><i class="fas fa-exclamation-triangle"></i> Minimal 2 jawaban harus benar untuk PGK</small>' : ''}
                    ${(question.correct_answers || []).length === (question.options || []).length && (question.options || []).length > 0 ? '<small style="color: var(--warning); margin-top: 0.5rem; display: block;"><i class="fas fa-exclamation-triangle"></i> Semua opsi benar - bukan PGK yang baik</small>' : ''}
                </div>
                ` : `
                <!-- TIPE B: Tabel Validasi (Benar/Salah) -->
                <div class="table-validation-container">
                    <div style="font-size: 0.85rem; font-weight: 600; margin-bottom: 0.75rem; color: var(--text-secondary); display: flex; align-items: center; justify-content: space-between;">
                        <div>
                            <i class="fas fa-table"></i> Tabel Pernyataan (Tentukan Benar/Salah)
                            ${question.image_url ? '<span style="color: var(--success); font-size: 0.75rem; margin-left: 0.5rem;"><i class="fas fa-check-circle"></i> Teks pernyataan diabaikan (pakai foto)</span>' : ''}
                        </div>
                    </div>
                    ${getTableValidationShuffleNoticeHtml(question, index)}

                    <!-- Table Header -->
                    <div style="display: grid; grid-template-columns: 40px 1fr 70px 70px 40px; gap: 0.5rem; padding: 0.75rem; background: rgba(99, 102, 241, 0.15); border-radius: 0.5rem 0.5rem 0 0; font-weight: 600; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.5px;">
                        <div style="text-align: center;">No</div>
                        <div>Pernyataan</div>
                        <div style="text-align: center; color: #22c55e;">Benar</div>
                        <div style="text-align: center; color: #ef4444;">Salah</div>
                        <div></div>
                    </div>

                    <!-- Table Rows -->
                    ${(question.statements || ['', '', '', '']).map((stmt, stmtIndex) => `
                        <div class="statement-row" style="display: grid; grid-template-columns: 40px 1fr 70px 70px 40px; gap: 0.5rem; padding: 0.75rem; background: var(--dark-lighter); border: 1px solid var(--border-color); border-top: none; align-items: center; ${stmtIndex === (question.statements || []).length - 1 ? 'border-radius: 0 0 0.5rem 0.5rem;' : ''}">
                            <div style="text-align: center; font-weight: 600; color: var(--text-secondary);">${stmtIndex + 1}</div>
                            <input type="text"
                                   value="${escapeHtml(stmt)}"
                                   placeholder="Tulis pernyataan ${stmtIndex + 1}..."
                                   oninput="updateStatement(${index}, ${stmtIndex}, this.value)"
                                   onclick="event.stopPropagation()"
                                   style="width: 100%; padding: 0.5rem; background: var(--dark); border: 1px solid var(--border-color); border-radius: 0.375rem; color: var(--text-primary); font-size: 0.9rem;">
                            <div style="text-align: center;">
                                <input type="radio"
                                       name="stmt_${index}_${stmtIndex}"
                                       ${(question.statement_answers || [])[stmtIndex] === true ? 'checked' : ''}
                                       onclick="setStatementAnswer(${index}, ${stmtIndex}, true); event.stopPropagation();"
                                       style="width: 20px; height: 20px; accent-color: #22c55e; cursor: pointer;">
                            </div>
                            <div style="text-align: center;">
                                <input type="radio"
                                       name="stmt_${index}_${stmtIndex}"
                                       ${(question.statement_answers || [])[stmtIndex] === false ? 'checked' : ''}
                                       onclick="setStatementAnswer(${index}, ${stmtIndex}, false); event.stopPropagation();"
                                       style="width: 20px; height: 20px; accent-color: #ef4444; cursor: pointer;">
                            </div>
                            <button onclick="event.stopPropagation(); deleteStatement(${index}, ${stmtIndex})"
                                    title="Hapus pernyataan"
                                    style="background: rgba(239,68,68,0.1); color: var(--danger); border: none; width: 28px; height: 28px; border-radius: 4px; cursor: pointer;">
                                <i class="fas fa-times"></i>
                            </button>
                        </div>
                    `).join('')}

                    <!-- Add Statement Button -->
                    <button onclick="event.stopPropagation(); addStatement(${index})"
                            style="margin-top: 0.75rem; width: 100%; padding: 0.75rem; background: rgba(99,102,241,0.1); border: 1px dashed rgba(99,102,241,0.3); border-radius: 0.5rem; color: var(--primary); font-size: 0.9rem; font-weight: 500; cursor: pointer;">
                        <i class="fas fa-plus"></i> Tambah Pernyataan
                    </button>

                    ${(question.statements || []).length < 2 ? '<small style="color: var(--danger); margin-top: 0.5rem; display: block;"><i class="fas fa-exclamation-triangle"></i> Minimal 2 pernyataan untuk tabel validasi</small>' : ''}
                </div>
                `}
            </div>
        `;
    }

    // Media preview HTML (image or video)
    let mediaHtml = '';

    if (question.image_url) {
        mediaHtml += `
            <div class="question-image-preview" style="margin: 0.75rem 0; position: relative; display: inline-block;">
                <img src="${question.image_url}" alt="Question image" style="max-width: 100%; max-height: 400px; border-radius: 0.5rem; box-shadow: 0 4px 12px rgba(0,0,0,0.3);">
                <button onclick="removeImage(${index})" style="position: absolute; top: 0.25rem; right: 0.25rem; background: rgba(0,0,0,0.6); border: none; color: white; width: 24px; height: 24px; border-radius: 50%; cursor: pointer;">
                    <i class="fas fa-times"></i>
                </button>
            </div>
        `;
    }

    if (question.video_url) {
        const videoId = extractYouTubeId(question.video_url);
        if (videoId) {
            mediaHtml += `
                <div class="question-video-preview" style="margin: 0.75rem 0; position: relative;">
                    <div style="position: relative; padding-bottom: 56.25%; height: 0; overflow: hidden; border-radius: 0.5rem; max-width: 700px; box-shadow: 0 4px 12px rgba(0,0,0,0.3);">
                        <iframe src="https://www.youtube.com/embed/${videoId}"
                                style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; border: none;"
                                allowfullscreen></iframe>
                    </div>
                    <button onclick="removeVideo(${index})" style="position: absolute; top: 0.25rem; right: 0.25rem; background: rgba(0,0,0,0.6); border: none; color: white; width: 24px; height: 24px; border-radius: 50%; cursor: pointer; z-index: 10;">
                        <i class="fas fa-times"></i>
                    </button>
                </div>
            `;
        }
    }

    // Render audio if present
    if (question.audio_url) {
        mediaHtml += `
            <div class="question-audio-preview" style="margin: 0.75rem 0; position: relative;">
                <audio controls style="width: 100%; max-width: 500px; border-radius: 0.5rem; box-shadow: 0 4px 12px rgba(0,0,0,0.3);">
                    <source src="${question.audio_url}" type="audio/mpeg">
                    <source src="${question.audio_url}" type="audio/wav">
                    <source src="${question.audio_url}" type="audio/ogg">
                    Your browser does not support the audio element.
                </audio>
                <button onclick="removeAudio(${index})" style="position: absolute; top: 0.25rem; right: calc(100% - 520px); background: rgba(0,0,0,0.6); border: none; color: white; width: 24px; height: 24px; border-radius: 50%; cursor: pointer;">
                    <i class="fas fa-times"></i>
                </button>
            </div>
        `;
    }

    return `
        <div class="question-card ${activeQuestionIndex === index ? 'active' : ''}"
             data-index="${index}"
             onclick="setActiveQuestion(${index})"
             draggable="true"
             ondragstart="handleDragStart(event, ${index})"
             ondragover="handleDragOver(event)"
             ondrop="handleDrop(event, ${index})">
            <div class="drag-handle">
                <i class="fas fa-grip-vertical"></i>
            </div>
            <div class="question-header">
                <div class="question-number">${index + 1}</div>
                <div class="question-input-wrapper">
                    <div class="question-format-toolbar" onclick="event.stopPropagation()">
                        <button type="button"
                                class="question-format-btn"
                                data-format="bold"
                                aria-pressed="false"
                                title="Huruf Tebal"
                                onmousedown="applyQuestionTextFormat(${index}, 'bold', event)">
                            <strong>B</strong>
                        </button>
                        <button type="button"
                                class="question-format-btn"
                                data-format="italic"
                                aria-pressed="false"
                                title="Huruf Miring"
                                onmousedown="applyQuestionTextFormat(${index}, 'italic', event)">
                            <em>I</em>
                        </button>
                        <button type="button"
                                class="question-format-btn"
                                data-format="underline"
                                aria-pressed="false"
                                title="Garis Bawah"
                                onmousedown="applyQuestionTextFormat(${index}, 'underline', event)">
                            <u>U</u>
                        </button>
                        <button type="button"
                                class="question-format-btn arabic"
                                data-format="arabic"
                                aria-pressed="false"
                                title="Mode ketik Arab ON/OFF"
                                onmousedown="applyQuestionTextFormat(${index}, 'arabic', event)">
                            AR
                        </button>
                    </div>
                    <div class="question-format-hint">
                        Blok teks untuk B/I/U. Klik AR untuk ON/OFF mode ketik Arab langsung.
                    </div>
                    <div class="question-rich-input ${question.arabic_input_mode === true ? 'arabic-typing-mode' : ''}"
                         contenteditable="true"
                         role="textbox"
                         aria-label="Teks pertanyaan"
                         data-index="${index}"
                         dir="${question.arabic_input_mode === true ? 'rtl' : 'ltr'}"
                         data-placeholder="Tulis pertanyaan di sini..."
                         oninput="updateQuestionRichText(${index}, this.innerHTML)"
                         onpaste="handleQuestionRichPaste(event, ${index})"
                         onfocus="updateQuestionFormatToolbarState(${index}, this)"
                         onkeyup="updateQuestionFormatToolbarState(${index}, this)"
                         onmouseup="updateQuestionFormatToolbarState(${index}, this)"
                         onblur="normalizeQuestionRichInput(${index}, this); updateQuestionFormatToolbarState(${index}, this)"
                         onclick="event.stopPropagation()">${storedQuestionTextToRichHtml(question.text)}</div>
                </div>
                <div class="question-controls">
                    <select class="type-selector" onclick="event.stopPropagation()" onchange="changeQuestionType(${index}, this.value)">
                        ${typeOptions}
                    </select>
                    <div class="points-wrapper" style="display: flex; align-items: center; gap: 0.25rem;" title="Bobot nilai soal ini">
                        <input type="number" class="points-input" value="${question.points}"
                               min="0.1" step="0.1" onclick="event.stopPropagation()"
                               onchange="updatePoints(${index}, this.value)">
                        <span style="font-size: 0.75rem; color: var(--text-secondary);">poin</span>
                    </div>
                    <div class="question-actions">
                        <button onclick="event.stopPropagation(); simulateSingleQuestion(${index})" title="Simulasi soal ini (mode siswa)">
                            <i class="fas fa-shuffle"></i>
                        </button>
                        <button onclick="event.stopPropagation(); triggerImageUpload(${index})" title="Tambah Gambar">
                            <i class="fas fa-image"></i>
                        </button>
                        <button onclick="event.stopPropagation(); promptVideoUrl(${index})" title="Tambah Video YouTube">
                            <i class="fab fa-youtube"></i>
                        </button>
                        <button onclick="event.stopPropagation(); triggerAudioUpload(${index})" title="Tambah Audio (MP3, WAV, OGG)">
                            <i class="fas fa-volume-up"></i>
                        </button>
                        <button onclick="event.stopPropagation(); duplicateQuestion(${index})" title="Duplikat">
                            <i class="fas fa-copy"></i>
                        </button>
                        <button class="delete" onclick="event.stopPropagation(); deleteQuestion(${index})" title="Hapus">
                            <i class="fas fa-trash"></i>
                        </button>
                    </div>
                </div>
            </div>
            ${mediaHtml}
            ${optionsHtml}
        </div>
    `;
}

// Question operations
function updateQuestionText(index, text) {
    examData.questions[index].text = text;
    triggerAutoSave();
}

function changeQuestionType(index, type) {
    const question = examData.questions[index];
    const builderDefaults = getBuilderSettings();
    question.type = type;
    question.is_placeholder = false;
    question.placeholder_source = null;
    question.allow_placeholder_shuffle = false;
    question.placeholder_shuffle_user_set = false;
    question.use_key_only_mode = false;
    question.answer_layout_mode = 'model1';
    question.model2_slots = [];
    question.preferred_image_layout_mode = builderDefaults.default_image_layout_mode;

    // Update points based on configured values
    question.points = getPointsForType(type);

    if (type === 'multiple_choice' && (!question.options || question.options.length === 0 || typeof question.options[0] !== 'string')) {
        question.options = Array(getDefaultOptionCountByType('multiple_choice')).fill('');
        question.correct_answer = '0';
        question.use_key_only_mode = builderDefaults.default_mc_key_only;
    } else if (type === 'multiple_choice') {
        ensureOptionSlots(question, getMinimumOptionCountByType('multiple_choice'));
        if (question.correct_answer === null || question.correct_answer === undefined || question.correct_answer === '') {
            question.correct_answer = '0';
        }
        question.use_key_only_mode = builderDefaults.default_mc_key_only;
    } else if (type === 'true_false') {
        question.options = [];
        question.correct_answer = 'true';
    } else if (type === 'essay') {
        question.options = [];
        question.correct_answer = '';
    } else if (type === 'short_answer') {
        question.options = [];
        question.correct_answer = '';
        question.require_manual_grading = false;  // Default: auto-grading enabled
    } else if (type === 'multiple_choice_complex' && (!question.options || question.options.length === 0)) {
        // Initialize PGK with all required fields
        question.options = Array(getDefaultOptionCountByType('multiple_choice_complex', 'checkbox')).fill('');
        question.correct_answers = [];  // Array of correct option indices
        question.correct_answer = '';   // Not used for this type
        question.stimulus = '';  // WAJIB untuk PGK
        question.pgk_type = 'checkbox';  // Default: Tipe A
        question.use_key_only_mode = builderDefaults.default_pgk_key_only;
    } else if (type === 'multiple_choice_complex') {
        ensureOptionSlots(question, getMinimumOptionCountByType('multiple_choice_complex', question.pgk_type || 'checkbox'));
        if (!Array.isArray(question.correct_answers)) {
            question.correct_answers = [];
        }
        question.use_key_only_mode = (question.pgk_type || 'checkbox') === 'checkbox'
            ? builderDefaults.default_pgk_key_only
            : false;
    }

    renderQuestions();
    triggerAutoSave();
}

function updatePoints(index, points) {
    examData.questions[index].points = parseFloat(points) || 1;
    triggerAutoSave();
}

function duplicateQuestion(index) {
    const original = examData.questions[index];
    const duplicate = JSON.parse(JSON.stringify(original));
    duplicate.id = null;
    examData.questions.splice(index + 1, 0, duplicate);
    renderQuestions();
    triggerAutoSave();
}


async function deleteQuestion(index) {
    const confirmed = await showConfirmModal(
        'Hapus Soal',
        'Yakin ingin menghapus soal ini? Tindakan ini tidak dapat dibatalkan.',
        'Ya, Hapus',
        'btn-danger'
    );
    if (!confirmed) return;

    const question = examData.questions[index];

    // FIX: If question has ID (exists on server), delete from server first
    if (question && question.id) {
        try {
            await api.deleteQuestion(question.id);
            console.log(`✅ Question ${question.id} deleted from server`);
        } catch (error) {
            console.error('Failed to delete question from server:', error);
            showAlert('Gagal menghapus soal dari server: ' + (error.message || 'Unknown error'), 'danger');
            return; // Don't remove locally if server delete failed
        }
    }

    examData.questions.splice(index, 1);
    activeQuestionIndex = null;
    renderQuestions();
    // No need to triggerAutoSave - question is already deleted from server
    showAlert('Soal berhasil dihapus', 'success');
}

function toggleKeyOnlyMode(questionIndex, enabled) {
    const question = examData.questions[questionIndex];
    if (!question) return;

    const resolvedPgkType = question.pgk_type || 'checkbox';
    const eligible = (
        question.type === 'multiple_choice' ||
        (question.type === 'multiple_choice_complex' && resolvedPgkType === 'checkbox')
    );
    if (!eligible) {
        showAlert('Mode ini hanya untuk Pilihan Ganda / PGK tipe checkbox.', 'warning');
        return;
    }

    question.use_key_only_mode = Boolean(enabled);
    question.placeholder_shuffle_user_set = false;
    ensureOptionSlots(question, getMinimumOptionCount(question));
    refreshQuestionPlaceholderState(question);
    renderQuestions();
    triggerAutoSave();
}

function toggleModel2Mode(questionIndex, enabled) {
    const question = examData.questions[questionIndex];
    if (!question) return;
    question.answer_layout_mode = 'model1';
    question.preferred_image_layout_mode = 'model1';
    question.model2_slots = [];
    question.allow_placeholder_shuffle = false;
    question.placeholder_shuffle_user_set = false;
    showAlert('Fitur titik gambar dinonaktifkan. Sistem memakai mode normal.', 'info');

    renderQuestions();
    triggerAutoSave();
}

function setAnswerLayoutMode(questionIndex, mode) {
    const question = examData.questions[questionIndex];
    if (!question) return;
    question.preferred_image_layout_mode = 'model1';
    question.answer_layout_mode = 'model1';
    question.model2_slots = [];
    question.allow_placeholder_shuffle = false;
    question.placeholder_shuffle_user_set = false;
    renderQuestions();
    triggerAutoSave();
}

function regenerateModel2Slots(questionIndex) {
    showAlert('Fitur titik gambar dinonaktifkan. Menu ini tidak digunakan.', 'info');
}

// Option operations
function addOption(questionIndex) {
    const question = examData.questions[questionIndex];
    question.options.push('');
    if (question.answer_layout_mode === 'model2' && isModel2Eligible(question)) {
        question.model2_slots = normalizeModel2Slots(question);
    }
    renderQuestions();
    triggerAutoSave();
}

function updateOption(questionIndex, optionIndex, value) {
    const question = examData.questions[questionIndex];
    if (!question) return;
    const previousState = {
        is_placeholder: question.is_placeholder === true,
        placeholder_source: question.placeholder_source || null,
        allow_placeholder_shuffle: question.allow_placeholder_shuffle === true
    };
    question.options[optionIndex] = value;
    refreshQuestionPlaceholderState(question);
    const placeholderStateChanged = (
        previousState.is_placeholder !== (question.is_placeholder === true) ||
        previousState.placeholder_source !== (question.placeholder_source || null) ||
        previousState.allow_placeholder_shuffle !== (question.allow_placeholder_shuffle === true)
    );
    if (placeholderStateChanged) {
        renderQuestions();
    }
    triggerAutoSave();
}

function deleteOption(questionIndex, optionIndex) {
    const question = examData.questions[questionIndex];
    const minimumOptions = getMinimumOptionCount(question);
    if (question.options.length <= minimumOptions) {
        showAlert(`Pilihan Ganda minimal harus punya ${minimumOptions} opsi (A sampai ${getOptionLabel(minimumOptions - 1)})`, 'warning');
        return;
    }
    question.options.splice(optionIndex, 1);

    // Update correct answer if needed
    const correctIdx = parseInt(question.correct_answer);
    if (optionIndex === correctIdx) {
        question.correct_answer = '0';
    } else if (optionIndex < correctIdx) {
        question.correct_answer = String(correctIdx - 1);
    }
    if (question.answer_layout_mode === 'model2' && isModel2Eligible(question)) {
        question.model2_slots = normalizeModel2Slots(question);
    }

    renderQuestions();
    triggerAutoSave();
}

function setCorrectAnswer(questionIndex, optionIndex) {
    const question = examData.questions[questionIndex];
    if (!question) return;
    ensureOptionSlots(question, getMinimumOptionCount(question));
    const previousState = {
        is_placeholder: question.is_placeholder === true,
        placeholder_source: question.placeholder_source || null,
        allow_placeholder_shuffle: question.allow_placeholder_shuffle === true
    };
    question.correct_answer = String(optionIndex);
    refreshQuestionPlaceholderState(question);
    const placeholderStateChanged = (
        previousState.is_placeholder !== (question.is_placeholder === true) ||
        previousState.placeholder_source !== (question.placeholder_source || null) ||
        previousState.allow_placeholder_shuffle !== (question.allow_placeholder_shuffle === true)
    );
    // Re-render jika status placeholder berubah agar panel bantuan langsung terlihat.
    if (question.use_key_only_mode === true || placeholderStateChanged) {
        renderQuestions();
    } else {
        updateCorrectAnswerUI(questionIndex, optionIndex);
    }
    triggerAutoSave();
}

function setTFAnswer(questionIndex, value) {
    examData.questions[questionIndex].correct_answer = value;
    // Update only the visual state without full re-render
    updateTFAnswerUI(questionIndex, value);
    triggerAutoSave();
}

// Short Answer
function updateShortAnswer(questionIndex, value) {
    examData.questions[questionIndex].correct_answer = value;
    triggerAutoSave();
}

// Toggle Manual Grading for Short Answer
function toggleManualGrading(questionIndex, isManual) {
    examData.questions[questionIndex].require_manual_grading = isManual;
    // Update only the checkbox state and feedback text without full re-render
    updateManualGradingUI(questionIndex, isManual);
    triggerAutoSave();
}

/* ===== Module: 20-advanced-preview-publish-validate.js ===== */

// ============== PERFORMANCE OPTIMIZATION: TARGETED UI UPDATE HELPERS ==============

// Update correct answer UI for multiple choice without re-rendering entire question list
function updateCorrectAnswerUI(questionIndex, optionIndex) {
    const questionCard = document.querySelector(`.question-card[data-index="${questionIndex}"]`);
    if (!questionCard) return;

    // Remove 'correct' class from all option radios and option items
    questionCard.querySelectorAll('.option-radio').forEach(radio => {
        radio.classList.remove('correct');
        radio.innerHTML = ''; // Remove check icon
    });
    questionCard.querySelectorAll('.option-item').forEach(item => {
        item.classList.remove('correct-answer');
    });

    // Add 'correct' class to selected option
    const optionItems = questionCard.querySelectorAll('.option-item');
    const selectedItem = optionItems[optionIndex];
    const selectedRadio = selectedItem?.querySelector('.option-radio');

    if (selectedItem && selectedRadio) {
        selectedItem.classList.add('correct-answer');
        selectedRadio.classList.add('correct');
        selectedRadio.innerHTML = '<i class="fas fa-check"></i>';
    }
}

// Update true/false answer UI without re-rendering
function updateTFAnswerUI(questionIndex, value) {
    const questionCard = document.querySelector(`.question-card[data-index="${questionIndex}"]`);
    if (!questionCard) return;

    // Remove 'correct' class from both TF options
    questionCard.querySelectorAll('.tf-option').forEach(opt => {
        opt.classList.remove('correct');
    });

    // Add 'correct' class to selected option
    const selectedOption = questionCard.querySelector(`.tf-option.${value}`);
    if (selectedOption) {
        selectedOption.classList.add('correct');
    }
}

// Update manual grading UI without re-rendering
function updateManualGradingUI(questionIndex, isManual) {
    const questionCard = document.querySelector(`.question-card[data-index="${questionIndex}"]`);
    if (!questionCard) return;

    // Find the checkbox by its onchange attribute
    const checkbox = questionCard.querySelector('input[type="checkbox"][onchange*="toggleManualGrading"]');
    const feedbackText = checkbox?.parentElement.querySelector('small');
    const icon = checkbox?.parentElement.querySelector('i.fa-user-check, i.fa-robot');

    if (checkbox) checkbox.checked = isManual;
    if (feedbackText) {
        feedbackText.textContent = isManual
            ? '✅ Soal ini akan diperiksa manual meskipun ada kunci jawaban'
            : 'Sistem akan memeriksa otomatis berdasarkan kunci jawaban';
    }
    if (icon) {
        icon.className = isManual ? 'fas fa-user-check' : 'fas fa-robot';
        icon.style.color = isManual ? 'var(--warning)' : 'var(--primary)';
    }
}

// Update complex answer UI (checkbox) without re-rendering
function updateComplexAnswerUI(questionIndex, optionIndex, isCorrect) {
    const questionCard = document.querySelector(`.question-card[data-index="${questionIndex}"]`);
    if (!questionCard) return;

    const checkbox = questionCard.querySelector(`#complex_opt_${questionIndex}_${optionIndex}`);
    const optionItem = checkbox?.closest('.option-item');

    if (checkbox) checkbox.checked = isCorrect;
    if (optionItem) {
        optionItem.style.border = isCorrect
            ? '2px solid var(--success)'
            : '1px solid var(--border-color)';
    }
}

// ============== MULTIPLE CHOICE COMPLEX FUNCTIONS ==============

// Toggle a correct answer for complex choice
function toggleComplexAnswer(questionIndex, optionIndex) {
    const question = examData.questions[questionIndex];
    if (!question) return;
    const previousState = {
        is_placeholder: question.is_placeholder === true,
        placeholder_source: question.placeholder_source || null,
        allow_placeholder_shuffle: question.allow_placeholder_shuffle === true
    };
    ensureOptionSlots(question, getMinimumOptionCount(question));
    if (!question.correct_answers) {
        question.correct_answers = [];
    }

    const idx = question.correct_answers.indexOf(optionIndex);
    const isNowCorrect = idx === -1;

    if (isNowCorrect) {
        question.correct_answers.push(optionIndex);
    } else {
        question.correct_answers.splice(idx, 1);
    }

    // Sort for consistency
    question.correct_answers.sort((a, b) => a - b);
    refreshQuestionPlaceholderState(question);
    const placeholderStateChanged = (
        previousState.is_placeholder !== (question.is_placeholder === true) ||
        previousState.placeholder_source !== (question.placeholder_source || null) ||
        previousState.allow_placeholder_shuffle !== (question.allow_placeholder_shuffle === true)
    );

    // Key-only mode uses compact UI, so refresh card for clear state.
    if (question.use_key_only_mode === true || placeholderStateChanged) {
        renderQuestions();
    } else {
        // Update only the checkbox and border styling without full re-render
        updateComplexAnswerUI(questionIndex, optionIndex, isNowCorrect);
    }
    triggerAutoSave();
}

// Add an option for complex choice
function addComplexOption(questionIndex) {
    const question = examData.questions[questionIndex];
    if (!question.options) {
        question.options = [];
    }
    question.options.push('');
    if (question.answer_layout_mode === 'model2' && isModel2Eligible(question)) {
        question.model2_slots = normalizeModel2Slots(question);
    }
    renderQuestions();
    triggerAutoSave();
}

// Update an option text for complex choice
function updateComplexOption(questionIndex, optionIndex, value) {
    const question = examData.questions[questionIndex];
    if (!question) return;
    const previousState = {
        is_placeholder: question.is_placeholder === true,
        placeholder_source: question.placeholder_source || null,
        allow_placeholder_shuffle: question.allow_placeholder_shuffle === true
    };
    question.options[optionIndex] = value;
    refreshQuestionPlaceholderState(question);
    const placeholderStateChanged = (
        previousState.is_placeholder !== (question.is_placeholder === true) ||
        previousState.placeholder_source !== (question.placeholder_source || null) ||
        previousState.allow_placeholder_shuffle !== (question.allow_placeholder_shuffle === true)
    );
    if (placeholderStateChanged) {
        renderQuestions();
    }
    triggerAutoSave();
}

// Delete an option for complex choice
function deleteComplexOption(questionIndex, optionIndex) {
    const question = examData.questions[questionIndex];
    const minimumOptions = getMinimumOptionCount(question);
    if (question.options.length <= minimumOptions) {
        showAlert(`PGK Tipe A minimal harus punya ${minimumOptions} opsi (A sampai ${getOptionLabel(minimumOptions - 1)})`, 'warning');
        return;
    }

    question.options.splice(optionIndex, 1);

    // Update correct_answers to reflect removed option
    if (question.correct_answers) {
        question.correct_answers = question.correct_answers
            .filter(idx => idx !== optionIndex)
            .map(idx => idx > optionIndex ? idx - 1 : idx);
    }
    if (question.answer_layout_mode === 'model2' && isModel2Eligible(question)) {
        question.model2_slots = normalizeModel2Slots(question);
    }

    renderQuestions();
    triggerAutoSave();
}

// Update stimulus for PGK
function updateStimulus(questionIndex, value) {
    examData.questions[questionIndex].stimulus = value;
    triggerAutoSave();

    // Update validation indicator WITHOUT full re-render (prevents scroll jump)
    const card = document.querySelector(`.question-card[data-index="${questionIndex}"]`);
    if (card) {
        const stimulusLabel = card.querySelector('.complex-choice-builder label');
        const stimulusTextarea = card.querySelector('.complex-choice-builder textarea');
        const warningSmall = card.querySelector('.complex-choice-builder > div:nth-child(2) > small');

        if (value && value.trim() !== '') {
            // Stimulus filled - show green check
            if (stimulusLabel) {
                const indicator = stimulusLabel.querySelector('span:last-child');
                if (indicator) {
                    indicator.innerHTML = '<i class="fas fa-check-circle"></i>';
                    indicator.style.color = 'var(--success)';
                    indicator.style.fontWeight = 'normal';
                }
            }
            if (stimulusTextarea) {
                stimulusTextarea.style.border = '1px solid var(--border-color)';
            }
            if (warningSmall) {
                warningSmall.style.display = 'none';
            }
        } else {
            // Stimulus empty - show warning
            if (stimulusLabel) {
                const indicator = stimulusLabel.querySelector('span:last-child');
                if (indicator) {
                    indicator.innerHTML = '⚠ Belum diisi';
                    indicator.style.color = 'var(--danger)';
                    indicator.style.fontWeight = '500';
                }
            }
            if (stimulusTextarea) {
                stimulusTextarea.style.border = '2px solid var(--danger)';
            }
            if (warningSmall) {
                warningSmall.style.display = 'block';
            }
        }
    }
}

// Change PGK sub-type
function changePGKType(questionIndex, newType) {
    const question = examData.questions[questionIndex];
    const builderDefaults = getBuilderSettings();
    question.pgk_type = newType;
    question.use_key_only_mode = newType === 'checkbox'
        ? builderDefaults.default_pgk_key_only
        : false;

    if (newType === 'table_validation') {
        // Initialize table validation data if needed
        if (!question.statements) {
            question.statements = ['', '', '', ''];
            question.statement_answers = [true, false, true, false];
        }
        question.answer_layout_mode = 'model1';
        question.model2_slots = [];
        question.allow_placeholder_shuffle = false;
        question.placeholder_shuffle_user_set = false;
        refreshTableStatementShuffleState(question);
    } else {
        ensureOptionSlots(question, getMinimumOptionCount(question));
        if (!Array.isArray(question.correct_answers)) {
            question.correct_answers = [];
        }
        question.placeholder_shuffle_user_set = false;
        refreshQuestionPlaceholderState(question);
    }

    renderQuestions();
    triggerAutoSave();
}

// ============== TYPE B: TABLE VALIDATION FUNCTIONS ==============

// Add a new statement for table validation
function addStatement(questionIndex) {
    const question = examData.questions[questionIndex];
    if (!question.statements) {
        question.statements = [];
        question.statement_answers = [];
    }
    question.statements.push('');
    question.statement_answers.push(true); // Default to "Benar"
    renderQuestions();
    triggerAutoSave();
}

// Update statement text
function updateStatement(questionIndex, statementIndex, value) {
    const question = examData.questions[questionIndex];
    if (!question.statements) {
        question.statements = ['', '', '', ''];
    }
    question.statements[statementIndex] = value;
    triggerAutoSave();
}

// Delete a statement
function deleteStatement(questionIndex, statementIndex) {
    const question = examData.questions[questionIndex];
    if (!question.statements || question.statements.length <= 2) {
        showAlert('Minimal 2 pernyataan untuk tabel validasi', 'warning');
        return;
    }
    question.statements.splice(statementIndex, 1);
    if (question.statement_answers) {
        question.statement_answers.splice(statementIndex, 1);
    }
    renderQuestions();
    triggerAutoSave();
}

// Set statement answer (true = Benar, false = Salah)
function setStatementAnswer(questionIndex, statementIndex, isCorrect) {
    const question = examData.questions[questionIndex];
    if (!question.statement_answers) {
        question.statement_answers = [];
    }
    question.statement_answers[statementIndex] = isCorrect;
    triggerAutoSave();
}

// Matching pairs - Modern Version (DEPRECATED)
function addMatchingPairModern(questionIndex) {
    if (!examData.questions[questionIndex].options) {
        examData.questions[questionIndex].options = [];
    }
    examData.questions[questionIndex].options.push({ left: '', right: '' });
    renderQuestions();
    triggerAutoSave();

    // Show success animation
    showAlert('Pasangan baru ditambahkan', 'success');
}

function updateMatchingPairModern(questionIndex, pairIndex, side, value) {
    examData.questions[questionIndex].options[pairIndex][side] = value;

    // Real-time validation
    const inputWrapper = event.target.closest('.matching-input-wrapper');
    if (inputWrapper) {
        if (value.trim() === '') {
            inputWrapper.classList.add('error');
            inputWrapper.classList.remove('success');
        } else {
            inputWrapper.classList.remove('error');
            inputWrapper.classList.add('success');
        }
    }

    triggerAutoSave();
}

// Backward compatibility - Keep old function names but call new versions
function addMatchingPair(questionIndex) {
    addMatchingPairModern(questionIndex);
}

function updateMatchingPair(questionIndex, pairIndex, side, value) {
    updateMatchingPairModern(questionIndex, pairIndex, side, value);
}

function deleteMatchingPair(questionIndex, pairIndex) {
    deleteMatchingPairModern(questionIndex, pairIndex);
}

// Image upload for question
function triggerImageUpload(questionIndex) {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/*';
    input.onchange = async (e) => {
        const file = e.target.files[0];
        if (!file) return;

        try {
            showAlert('Mengupload gambar...', 'info');
            const formData = new FormData();
            formData.append('file', file);

            const response = await fetch('/api/upload/image', {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${localStorage.getItem('access_token')}`
                },
                body: formData
            });

            if (!response.ok) throw new Error('Upload failed');

            const result = await response.json();
            const question = examData.questions[questionIndex];
            question.image_url = result.url;
            question.preferred_image_layout_mode = 'model1';
            question.answer_layout_mode = 'model1';
            question.model2_slots = [];
            question.allow_placeholder_shuffle = false;
            question.placeholder_shuffle_user_set = false;
            refreshTableStatementShuffleState(question);
            renderQuestions();
            triggerAutoSave();
            showAlert('Gambar berhasil diupload', 'success');
        } catch (error) {
            console.error('Upload error:', error);
            showAlert('Gagal upload gambar', 'danger');
        }
    };
    input.click();
}

function removeImage(questionIndex) {
    const question = examData.questions[questionIndex];
    question.image_url = null;
    question.answer_layout_mode = 'model1';
    question.preferred_image_layout_mode = 'model1';
    question.model2_slots = [];
    question.allow_placeholder_shuffle = false;
    question.placeholder_shuffle_user_set = false;
    refreshTableStatementShuffleState(question);
    renderQuestions();
    triggerAutoSave();
}

// Drag and Drop
let draggedIndex = null;

function handleDragStart(event, index) {
    draggedIndex = index;
    event.target.classList.add('dragging');
    event.dataTransfer.effectAllowed = 'move';
}

function handleDragOver(event) {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
}

function handleDrop(event, targetIndex) {
    event.preventDefault();

    if (draggedIndex === null || draggedIndex === targetIndex) return;

    const [draggedQuestion] = examData.questions.splice(draggedIndex, 1);
    examData.questions.splice(targetIndex, 0, draggedQuestion);

    draggedIndex = null;
    renderQuestions();
    triggerAutoSave();
}

document.addEventListener('dragend', () => {
    document.querySelectorAll('.question-card').forEach(card => {
        card.classList.remove('dragging');
    });
    draggedIndex = null;
});

// ============== VIDEO/IMAGE MANAGEMENT ==============
// (Functions defined below in the modal helpers section: extractYouTubeId, promptVideoUrl, removeVideo, removeImage)

function stableStringify(value) {
    if (value === null || typeof value !== 'object') {
        return JSON.stringify(value);
    }
    if (Array.isArray(value)) {
        return `[${value.map((item) => stableStringify(item)).join(',')}]`;
    }
    const keys = Object.keys(value).sort();
    return `{${keys.map((key) => `${JSON.stringify(key)}:${stableStringify(value[key])}`).join(',')}}`;
}

function buildExamPayloadFromState() {
    return {
        title: examData.title || 'Ujian Tanpa Judul',
        description: '',
        duration_minutes: examData.duration_minutes || 60,
        passing_score: examData.passing_score || 70,
        shuffle_questions: examData.shuffle_questions || false,
        shuffle_options: examData.shuffle_options || false,
        show_results: examData.show_results === true,
        allow_review: examData.allow_review || false,
        start_time: examData.start_time,
        end_time: examData.end_time,
        subject: examData.subject || null,
        exam_type: examData.exam_type || null,
        academic_year: examData.academic_year || null,
        show_teacher_name: examData.show_teacher_name !== false,
        builder_settings: getBuilderSettings(),
        is_published: false
    };
}

function buildQuestionPayloadFromState(q, orderIndex, currentExamId) {
    // Build options in correct format for API
    let formattedOptions = [];
    let isPlaceholder = false; // track if options are generated automatically
    let placeholderSource = null;
    let allowPlaceholderShuffle = false;
    const useKeyOnlyMode = q.use_key_only_mode === true;
    const currentPgkType = q.type === 'multiple_choice_complex' ? (q.pgk_type || 'checkbox') : null;

    if (q.type === 'multiple_choice') {
        const minOptionCount = getMinimumOptionCountByType('multiple_choice');
        const selectedKeyIndex = parseInt(q.correct_answer, 10);
        const requiredOptionCount = Math.max(
            q.options?.length || 0,
            minOptionCount,
            Number.isInteger(selectedKeyIndex) && selectedKeyIndex >= 0 ? selectedKeyIndex + 1 : 0
        );
        ensureOptionSlots(q, requiredOptionCount);

        const hasValidOptions = countRealOptionTexts(q.options || []) > 0;
        let optionsSource = [];
        if (hasValidOptions) {
            optionsSource = q.options;
        } else {
            const hasEmbeddedOptions = hasEmbeddedOptionsFromQuestionText(q.text);
            const hasSelectedKey = q.correct_answer !== null
                && q.correct_answer !== undefined
                && q.correct_answer !== ''
                && q.correct_answer !== -1
                && !Number.isNaN(parseInt(q.correct_answer, 10));
            if (q.image_url || hasEmbeddedOptions || hasSelectedKey) {
                optionsSource = buildPlaceholderLabels(requiredOptionCount);
                isPlaceholder = true;
                if (q.image_url) {
                    placeholderSource = 'image';
                } else if (hasEmbeddedOptions) {
                    placeholderSource = 'question_text';
                } else {
                    placeholderSource = 'auto_no_option';
                }
            } else {
                optionsSource = Array(requiredOptionCount).fill('');
            }
        }

        formattedOptions = optionsSource.map((opt, idx) => ({
            option_text: typeof opt === 'string' ? opt : (opt.text || opt.option_text || ''),
            is_correct: parseInt(q.correct_answer, 10) === idx,
            order_index: idx,
            option_group: 'standard',
            pair_id: null
        }));
    } else if (q.type === 'multiple_choice_complex') {
        if (currentPgkType === 'checkbox') {
            const minOptionCount = getMinimumOptionCountByType('multiple_choice_complex', 'checkbox');
            const correctAnswersArray = q.correct_answers || [];
            const highestCorrectIndex = correctAnswersArray.length > 0
                ? Math.max(...correctAnswersArray)
                : -1;
            const requiredOptionCount = Math.max(
                q.options?.length || 0,
                minOptionCount,
                highestCorrectIndex + 1
            );
            ensureOptionSlots(q, requiredOptionCount);

            const hasValidOptionsPgk = countRealOptionTexts(q.options || []) > 0;
            let optionsSourcePgk = [];
            if (hasValidOptionsPgk) {
                optionsSourcePgk = q.options;
            } else {
                const hasEmbeddedOptions = hasEmbeddedOptionsFromQuestionText(q.text);
                const hasSelectedKeys = Array.isArray(correctAnswersArray) && correctAnswersArray.length >= 2;
                if (q.image_url || hasEmbeddedOptions || hasSelectedKeys) {
                    optionsSourcePgk = buildPlaceholderLabels(requiredOptionCount);
                    isPlaceholder = true;
                    if (q.image_url) {
                        placeholderSource = 'image';
                    } else if (hasEmbeddedOptions) {
                        placeholderSource = 'question_text';
                    } else {
                        placeholderSource = 'auto_no_option';
                    }
                } else {
                    optionsSourcePgk = Array(requiredOptionCount).fill('');
                }
            }

            formattedOptions = optionsSourcePgk.map((opt, idx) => ({
                option_text: typeof opt === 'string' ? opt : (opt.text || opt.option_text || ''),
                is_correct: correctAnswersArray.includes(idx),
                order_index: idx,
                option_group: 'standard',
                pair_id: null
            }));
        } else {
            // Tipe B: Table Validation (Empty options)
            formattedOptions = [];
        }
    } else if (q.type === 'true_false') {
        formattedOptions = [
            { option_text: 'Benar', is_correct: q.correct_answer === true || q.correct_answer === 'true', order_index: 0, option_group: 'standard', pair_id: null },
            { option_text: 'Salah', is_correct: q.correct_answer === false || q.correct_answer === 'false', order_index: 1, option_group: 'standard', pair_id: null }
        ];
    }

    if (!isPlaceholder) {
        placeholderSource = null;
    }
    const normalizedLayoutMode = 'model1';
    const normalizedModel2Slots = [];
    const isModel2ImageShuffle = false;
    allowPlaceholderShuffle = (
        isPlaceholder &&
        (
            isModel2ImageShuffle ||
            (placeholderSource !== 'image' && q.allow_placeholder_shuffle === true)
        )
    );
    q.is_placeholder = isPlaceholder;
    q.placeholder_source = placeholderSource;
    q.allow_placeholder_shuffle = allowPlaceholderShuffle;
    q.use_key_only_mode = (
        q.type === 'multiple_choice' ||
        (q.type === 'multiple_choice_complex' && currentPgkType === 'checkbox')
    ) ? useKeyOnlyMode : false;
    q.answer_layout_mode = normalizedLayoutMode;
    q.model2_slots = normalizedModel2Slots;

    const questionPayload = {
        exam_id: currentExamId,
        question_text: q.text || 'Pertanyaan baru',
        question_type: q.type || 'multiple_choice',
        stimulus: q.stimulus || null,
        pgk_type: currentPgkType,
        difficulty_level: q.difficulty || 'medium',
        points: q.points || 1,
        order_index: orderIndex,
        options: formattedOptions,
        question_settings: {
            stimulus: q.stimulus,
            pgk_type: currentPgkType,
            acceptable_answers: q.type === 'short_answer' && q.correct_answer ? [q.correct_answer.trim()] : [],
            require_manual_grading: q.type === 'short_answer' ? (q.require_manual_grading || false) : undefined,
            case_sensitive: false,
            statements: currentPgkType === 'table_validation' ? (q.statements || []) : undefined,
            statement_answers: currentPgkType === 'table_validation' ? (q.statement_answers || []) : undefined,
            allow_table_statement_shuffle: currentPgkType === 'table_validation'
                ? (q.allow_table_statement_shuffle !== false)
                : undefined,
            is_placeholder: isPlaceholder,
            placeholder_source: placeholderSource,
            allow_placeholder_shuffle: allowPlaceholderShuffle,
            use_key_only_mode: (
                q.type === 'multiple_choice' ||
                (q.type === 'multiple_choice_complex' && currentPgkType === 'checkbox')
            ) ? useKeyOnlyMode : undefined,
            preferred_image_layout_mode: 'model1',
            answer_layout_mode: normalizedLayoutMode,
            model2_slots: undefined
        },
        tag_ids: [],
        category_id: null,
        image_url: q.image_url || null,
        video_url: q.video_url || null,
        audio_url: q.audio_url || null
    };
    const questionPayloadSignature = stableStringify(questionPayload);

    return { questionPayload, questionPayloadSignature };
}

// Auto-save - triggers after last change (debounced)
function triggerAutoSave() {
    // Prevent stacking saves if one is already in progress
    if (isSaving) {
        // If saving, just reschedule checks
        if (saveTimeout) clearTimeout(saveTimeout);
        saveTimeout = setTimeout(triggerAutoSave, AUTO_SAVE_RETRY_MS);
        return;
    }

    const status = document.getElementById('save-status');
    if (status) {
        status.innerHTML = '<i class="fas fa-sync-alt fa-spin"></i> Menyimpan...';
        status.classList.add('saving');
        status.style.color = '#f59e0b';
    }

    if (saveTimeout) clearTimeout(saveTimeout);

    saveTimeout = setTimeout(async () => {
        await saveExam();
    }, AUTO_SAVE_DEBOUNCE_MS);
}

// Manual Save - immediate save with button feedback
async function manualSave() {
    if (isSaving) return; // Prevent double click

    const btn = document.getElementById('save-draft-btn');
    const status = document.getElementById('save-status');

    // Show saving state
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Menyimpan...';
    }
    if (status) {
        status.innerHTML = '<i class="fas fa-sync-alt fa-spin"></i> Menyimpan...';
        status.style.color = '#f59e0b';
    }

    try {
        await saveExam();

        // Success feedback
        if (btn) {
            btn.innerHTML = '<i class="fas fa-check"></i> Tersimpan!';
            btn.classList.remove('btn-warning');
            btn.classList.add('btn-success');
        }
        if (status) {
            status.innerHTML = '<i class="fas fa-check-circle"></i> Tersimpan';
            status.style.color = '#22c55e';
        }

        showAlert('Draft berhasil disimpan!', 'success');

        // Reset button after 2 seconds
        setTimeout(() => {
            if (btn) {
                btn.innerHTML = '<i class="fas fa-save"></i> Simpan Draft';
                btn.classList.remove('btn-success');
                btn.classList.add('btn-warning');
                btn.disabled = false;
            }
        }, 2000);
    } catch (error) {
        // Error feedback
        if (btn) {
            btn.innerHTML = '<i class="fas fa-times"></i> Gagal!';
            btn.classList.remove('btn-warning');
            btn.classList.add('btn-danger');
        }
        if (status) {
            status.innerHTML = '<i class="fas fa-exclamation-circle"></i> Gagal simpan';
            status.style.color = '#ef4444';
        }

        showAlert('Gagal menyimpan draft: ' + (error.message || 'Unknown error'), 'danger');

        // Reset button after 2 seconds
        setTimeout(() => {
            if (btn) {
                btn.innerHTML = '<i class="fas fa-save"></i> Simpan Draft';
                btn.classList.remove('btn-danger');
                btn.classList.add('btn-warning');
                btn.disabled = false;
            }
        }, 2000);
    }
}
async function saveExam() {
    if (isSaving) {
        console.log('⏳ Save already in progress, skipping...');
        return;
    }
    isSaving = true;
    const saveStatus = document.getElementById('save-status');

    try {
        // Get time values from inputs
        const startTimeInput = document.getElementById('start-time');
        const endTimeInput = document.getElementById('end-time');

        if (startTimeInput && startTimeInput.value) {
            examData.start_time = new Date(startTimeInput.value).toISOString();
        }
        if (endTimeInput && endTimeInput.value) {
            examData.end_time = new Date(endTimeInput.value).toISOString();
        }

        // Ensure we have valid dates based on duration
        if (!examData.start_time || !examData.end_time) {
            const now = new Date();
            const duration = examData.duration_minutes || 60;
            const endTime = new Date(now.getTime() + duration * 60 * 1000);
            examData.start_time = now.toISOString();
            examData.end_time = endTime.toISOString();
            console.log(`⏰ Auto-set times: ${duration}min (${now.toLocaleTimeString()} - ${endTime.toLocaleTimeString()})`);
        }

        const examPayload = buildExamPayloadFromState();
        const examPayloadSignature = stableStringify(examPayload);

        // Save exam first
        if (examId) {
            if (lastSavedExamSignature !== examPayloadSignature) {
                await api.updateExam(examId, examPayload);
                lastSavedExamSignature = examPayloadSignature;
            }
        } else {
            const result = await api.createExam(examPayload);
            if (result && result.id) {
                examId = result.id;
                lastSavedExamSignature = examPayloadSignature;
                // Update URL without reload
                window.history.replaceState({}, '', `/admin/exam-builder.html?id=${examId}`);
            } else {
                throw new Error('Failed to create exam - no ID returned');
            }
        }

        // VALIDATION: Don't save questions if examId is not set
        if (!examId) {
            throw new Error('Cannot save questions: Exam ID is not set');
        }

        // Save questions with individual error handling
        const questionErrors = [];

        for (let i = 0; i < examData.questions.length; i++) {
            const q = examData.questions[i];

            try {
                const { questionPayload, questionPayloadSignature } = buildQuestionPayloadFromState(q, i, examId);

                if (q.id && q._last_saved_signature === questionPayloadSignature) {
                    continue;
                }

                if (q.id) {
                    await api.updateQuestion(q.id, questionPayload);
                } else {
                    const result = await api.createQuestion(questionPayload);
                    q.id = result.id;
                }
                q._last_saved_signature = questionPayloadSignature;
            } catch (questionError) {
                console.error(`Failed to save question ${i + 1}:`, questionError);
                questionErrors.push({ index: i + 1, error: questionError.message || 'Unknown error' });
            }
        }

        // Report any question errors
        if (questionErrors.length > 0) {
            const errorMsg = questionErrors.map(e => `Soal ${e.index}: ${e.error}`).join('\n');
            console.warn('Some questions failed to save:', errorMsg);
            throw new Error(`Beberapa soal gagal disimpan:\n${errorMsg}`);
        }

        // Success state
        if (saveStatus) {
            saveStatus.innerHTML = '<i class="fas fa-check-circle"></i> Tersimpan';
            saveStatus.classList.remove('saving');
            saveStatus.style.color = '#22c55e';
        }

    } catch (e) {
        console.error('Save failed:', e);
        if (saveStatus) {
            saveStatus.innerHTML = '<i class="fas fa-exclamation-triangle"></i> Gagal';
            saveStatus.classList.remove('saving');
            saveStatus.style.color = '#ef4444';
        }
        throw e; // Re-throw to be caught by manualSave caller
    } finally {
        isSaving = false;
    }
}

// Time modal functions
function openTimeModal() {
    openModal('time-modal');
}

function setTimeNow() {
    const now = new Date();
    const duration = examData.duration_minutes || 60; // Use exam duration
    const endTime = new Date(now.getTime() + duration * 60 * 1000);
    document.getElementById('start-time').value = formatDateTimeLocal(now);
    document.getElementById('end-time').value = formatDateTimeLocal(endTime);
}

function setTimeTomorrow() {
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    tomorrow.setHours(8, 0, 0, 0);
    const duration = examData.duration_minutes || 60; // Use exam duration
    const endTime = new Date(tomorrow.getTime() + duration * 60 * 1000);
    document.getElementById('start-time').value = formatDateTimeLocal(tomorrow);
    document.getElementById('end-time').value = formatDateTimeLocal(endTime);
}

function saveTimeSettings() {
    examData.start_time = document.getElementById('start-time').value;
    examData.end_time = document.getElementById('end-time').value;
    closeModal('time-modal');
    triggerAutoSave();
}

// Preview
async function togglePreview(mode = 'builder') {
    const content = document.getElementById('preview-content');
    const title = document.getElementById('preview-modal-title');

    if (!content) return;

    if (mode === 'simulate') {
        if (!examId) {
            showAlert('Simpan draft dulu sebelum preview simulasi siswa.', 'warning');
            return;
        }

        try {
            await saveExam();
        } catch (error) {
            showAlert('Gagal menyimpan sebelum preview simulasi: ' + (error.message || 'Unknown error'), 'danger');
            return;
        }

        if (title) {
            title.innerHTML = '<i class="fas fa-random"></i> Preview Simulasi Siswa';
        }
        content.innerHTML = '<div style="padding:1rem; color: var(--text-secondary);"><i class="fas fa-spinner fa-spin"></i> Menyiapkan simulasi urutan siswa...</div>';
        openModal('preview-modal');

        try {
            const simulationBundle = await fetchSimulationComparison(examId);
            renderSimulatedPreview(simulationBundle.normalData, simulationBundle.simulatedData);
        } catch (error) {
            content.innerHTML = '<div style="padding:1rem; color: var(--danger);"><i class="fas fa-triangle-exclamation"></i> Gagal memuat simulasi preview.</div>';
            showAlert('Preview simulasi gagal: ' + (error.message || 'Unknown error'), 'danger');
        }
        return;
    }

    if (title) {
        title.innerHTML = '<i class="fas fa-eye"></i> Preview Builder';
    }

    let html = '<div style="padding: 1rem; background: var(--dark-lighter); border-radius: 0.5rem; margin-bottom: 1rem;">';
    html += '<h2 style="margin-bottom: 0.5rem;">' + escapeHtml(examData.title) + '</h2>';
    html += '<p style="color: var(--text-secondary);">';
    html += '<i class="fas fa-clock"></i> ' + examData.duration_minutes + ' menit &nbsp;|&nbsp;';
    html += '<i class="fas fa-check-circle"></i> KKM: ' + examData.passing_score + ' &nbsp;|&nbsp;';
    html += '<i class="fas fa-list"></i> ' + examData.questions.length + ' soal';
    html += '</p></div>';

    examData.questions.forEach((q, i) => {
        html += '<div class="preview-question" style="padding: 1rem; background: var(--dark-card); border-radius: 0.5rem; margin-bottom: 1rem; border-left: 3px solid var(--primary);">';
        html += '<div class="preview-question-text" style="margin-bottom: 0.75rem;">';
        html += '<span style="color: var(--primary); font-weight: 600;">' + (i + 1) + '.</span> ';
        html += (renderBuilderRichText(q.text) || '<em style="color: var(--text-secondary);">Pertanyaan kosong</em>');
        html += '<span style="color: var(--text-secondary); font-size: 0.8rem; margin-left: 0.5rem;">(' + q.points + ' poin)</span>';
        html += '<span style="background: var(--primary); color: white; padding: 2px 8px; border-radius: 4px; font-size: 0.7rem; margin-left: 0.5rem;">' + getQuestionTypeLabel(q.type) + '</span>';
        html += '</div>';

        if (q.image_url) {
            html += '<img src="' + q.image_url + '" style="max-width: 200px; border-radius: 0.5rem; margin-bottom: 0.5rem;">';
        }

        if (q.video_url) {
            html += '<div style="color: var(--text-secondary); margin-bottom: 0.5rem;"><i class="fab fa-youtube" style="color: #ff0000;"></i> Video YouTube terlampir</div>';
        }

        // Preview Pilihan Ganda Biasa
        if (q.type === 'multiple_choice' && q.options) {
            q.options.forEach((opt, j) => {
                const isCorrect = q.correct_answer == j;
                html += '<div class="preview-option" style="display: flex; align-items: center; gap: 0.5rem; padding: 0.5rem; margin-bottom: 0.25rem; background: var(--dark); border-radius: 0.25rem;">';
                html += '<div style="width: 18px; height: 18px; border: 2px solid ' + (isCorrect ? 'var(--success)' : 'var(--border-color)') + '; border-radius: 50%;' + (isCorrect ? ' background: var(--success);' : '') + '"></div>';
                html += '<span>' + (escapeHtml(opt) || '<em style="color: var(--text-secondary);">Opsi kosong</em>') + '</span>';
                html += '</div>';
            });
        }

        // Preview Essay
        if (q.type === 'essay') {
            html += '<div style="padding: 1rem; background: var(--dark); border-radius: 0.5rem; color: var(--text-secondary); border: 1px dashed var(--border-color);"><i class="fas fa-keyboard"></i> Area jawaban essay (teks panjang)</div>';
        }

        // Preview Benar/Salah
        if (q.type === 'true_false') {
            html += '<div style="display: flex; gap: 1rem;">';
            html += '<div class="preview-option" style="display: flex; align-items: center; gap: 0.5rem; padding: 0.5rem 1rem; background: var(--dark); border-radius: 0.25rem; border: 2px solid ' + (q.correct_answer === 'true' ? 'var(--success)' : 'var(--border-color)') + ';">';
            html += '<i class="fas fa-check" style="color: var(--success);"></i> Benar</div>';
            html += '<div class="preview-option" style="display: flex; align-items: center; gap: 0.5rem; padding: 0.5rem 1rem; background: var(--dark); border-radius: 0.25rem; border: 2px solid ' + (q.correct_answer === 'false' ? 'var(--danger)' : 'var(--border-color)') + ';">';
            html += '<i class="fas fa-times" style="color: var(--danger);"></i> Salah</div>';
            html += '</div>';
        }

        // Preview Isian Singkat
        if (q.type === 'short_answer') {
            html += '<div style="padding: 0.75rem; background: var(--dark); border-radius: 0.5rem; border: 1px dashed var(--border-color);">';
            html += '<div style="color: var(--text-secondary); margin-bottom: 0.5rem;"><i class="fas fa-pen"></i> Jawaban singkat</div>';
            if (q.correct_answer) {
                html += '<div style="color: var(--success);"><i class="fas fa-key"></i> Kunci: ' + escapeHtml(q.correct_answer) + '</div>';
            }
            html += '</div>';
        }

        // Preview PGK (Pilihan Ganda Kompleks)
        if (q.type === 'multiple_choice_complex') {
            html += '<div style="padding: 1rem; background: var(--dark); border-radius: 0.5rem; border: 1px solid var(--border-color);">';
            html += '<div style="margin-bottom: 0.75rem; display: flex; align-items: center; gap: 0.5rem;">';
            html += '<span style="background: linear-gradient(135deg, #f093fb, #f5576c); padding: 0.15rem 0.5rem; border-radius: 0.25rem; font-size: 0.7rem; color: white; font-weight: bold;">HOTS</span>';
            html += '<span style="color: #a78bfa; font-size: 0.85rem; font-weight: 600;">' + (q.pgk_type === 'table_validation' ? 'Tabel Validasi (Benar/Salah)' : 'Multiple Response (Pilihan Jamak)') + '</span>';
            html += '</div>';

            if (q.stimulus) {
                html += '<div style="margin-bottom: 1rem; padding: 0.75rem; background: var(--dark-lighter); border-left: 3px solid #f59e0b; font-style: italic; color: var(--text-primary);">';
                html += renderBuilderRichText(q.stimulus);
                html += '</div>';
            }

            if (q.pgk_type === 'checkbox') {
                html += '<div style="margin-bottom: 0.5rem; font-size: 0.9rem; color: var(--text-secondary);"><i class="fas fa-check-square"></i> Pilihlah jawaban-jawaban yang benar:</div>';
                if (q.options) {
                    q.options.forEach((opt, j) => {
                        const isCorrect = (q.correct_answers || []).includes(j);
                        const optText = typeof opt === 'object' ? opt.text : opt;
                        html += '<div class="preview-option" style="display: flex; align-items: center; gap: 0.75rem; padding: 0.5rem; margin-bottom: 0.25rem; background: var(--dark-lighter); border-radius: 0.25rem; border: 1px solid ' + (isCorrect ? 'var(--success)' : 'transparent') + ';">';
                        html += '<div style="width: 20px; height: 20px; border: 2px solid ' + (isCorrect ? 'var(--success)' : 'var(--text-secondary)') + '; border-radius: 4px;' + (isCorrect ? ' background: var(--success);' : '') + ' display: flex; align-items: center; justify-content: center;">';
                        if (isCorrect) html += '<i class="fas fa-check" style="color: white; font-size: 12px;"></i>';
                        html += '</div>';
                        html += '<span>' + (escapeHtml(optText) || '<em style="color: var(--text-secondary);">Opsi kosong</em>') + '</span>';
                        html += '</div>';
                    });
                }
            } else if (q.pgk_type === 'table_validation') {
                html += '<div style="margin-bottom: 0.5rem; font-size: 0.9rem; color: var(--text-secondary);"><i class="fas fa-table"></i> Tentukan Benar/Salah untuk setiap pernyataan:</div>';
                html += '<table style="width: 100%; border-collapse: collapse; font-size: 0.9rem;">';
                html += '<tr style="background: rgba(99, 102, 241, 0.15); color: var(--text-primary);">';
                html += '<th style="padding: 0.5rem; text-align: left; border: 1px solid var(--border-color);">Pernyataan</th>';
                html += '<th style="padding: 0.5rem; text-align: center; width: 80px; border: 1px solid var(--border-color);">Benar</th>';
                html += '<th style="padding: 0.5rem; text-align: center; width: 80px; border: 1px solid var(--border-color);">Salah</th>';
                html += '</tr>';

                if (q.statements) {
                    q.statements.forEach((stmt, j) => {
                        const answer = (q.statement_answers || [])[j];
                        html += '<tr>';
                        html += '<td style="padding: 0.5rem; border: 1px solid var(--border-color);">' + (escapeHtml(stmt) || '-') + '</td>';
                        html += '<td style="padding: 0.5rem; text-align: center; border: 1px solid var(--border-color);">';
                        if (answer === true) html += '<div style="color: var(--success); font-weight: bold;"><i class="fas fa-check-circle"></i></div>';
                        html += '</td>';
                        html += '<td style="padding: 0.5rem; text-align: center; border: 1px solid var(--border-color);">';
                        if (answer === false) html += '<div style="color: var(--danger); font-weight: bold;"><i class="fas fa-times-circle"></i></div>';
                        html += '</td>';
                        html += '</tr>';
                    });
                }
                html += '</table>';
            }

            html += '</div>';
        }

        html += '</div>';
    });

    content.innerHTML = html;
    openModal('preview-modal');
}

async function fetchSimulationComparison(currentExamId) {
    const [normalData, simulatedData] = await Promise.all([
        api.previewExam(currentExamId, false),
        api.previewExam(currentExamId, true)
    ]);
    return { normalData, simulatedData };
}

function getPreviewOptionLabels(question) {
    return (question?.options || []).map((opt, idx) => {
        const text = typeof opt === 'string'
            ? opt
            : (opt?.option_text || opt?.text || '');
        const trimmed = String(text || '').trim();
        return trimmed || getOptionLabel(idx);
    });
}

function isSimulationModel2Active(question) {
    return false;
}

function getSimulationModel2Slots(question, optionCount = 0) {
    const settings = question?.question_settings || {};
    const rawSlots = settings.model2_runtime_slots || settings.model2_slots || [];
    if (!Array.isArray(rawSlots) || rawSlots.length < 2) {
        return [];
    }
    const limited = rawSlots.slice(0, Math.max(optionCount, 2));
    return limited.map((slot, idx) => ({
        slot: idx,
        x: Number(slot?.x ?? 50),
        y: Number(slot?.y ?? 50)
    }));
}

function renderSimulationModel2Block(question) {
    return '';
}

function getPreviewOptionIdentity(question) {
    return (question?.options || []).map((opt, idx) => {
        const id = (typeof opt === 'object' && opt !== null)
            ? String(opt.id ?? `idx:${idx}`)
            : `text:${idx}`;
        const text = typeof opt === 'string'
            ? opt
            : (opt?.option_text || opt?.text || '');
        return `${id}::${String(text || '').trim()}`;
    });
}

function getPreviewStatementIdentity(question) {
    const statements = (question?.question_settings && question.question_settings.statements) || [];
    return (statements || []).map((stmt, idx) => {
        const isObject = typeof stmt === 'object' && stmt !== null;
        const originalIndex = isObject && Number.isInteger(stmt.original_index)
            ? stmt.original_index
            : idx;
        const text = isObject ? stmt.text : stmt;
        return `${originalIndex}::${String(text || '').trim()}`;
    });
}

function getPreviewStatementOrderMap(question) {
    const statements = (question?.question_settings && question.question_settings.statements) || [];
    return (statements || []).map((stmt, idx) => {
        if (typeof stmt === 'object' && stmt !== null && Number.isInteger(stmt.original_index)) {
            return stmt.original_index + 1;
        }
        return idx + 1;
    });
}

function getPreviewStatementLabels(question) {
    const statements = (question?.question_settings && question.question_settings.statements) || [];
    return (statements || []).map((stmt) => {
        if (typeof stmt === 'object' && stmt !== null) {
            return String(stmt.text || '-').trim() || '-';
        }
        return String(stmt || '-').trim() || '-';
    });
}

function getPreviewStatementIndexedLabels(question) {
    const statements = (question?.question_settings && question.question_settings.statements) || [];
    return (statements || []).map((stmt, idx) => {
        const isObject = typeof stmt === 'object' && stmt !== null;
        const sourceIndex = isObject && Number.isInteger(stmt.original_index)
            ? stmt.original_index + 1
            : idx + 1;
        const text = isObject ? stmt.text : stmt;
        const normalizedText = String(text || '-').trim() || '-';
        return `[#${sourceIndex}] ${normalizedText}`;
    });
}

function getPreviewQuestionGrading(question) {
    const type = question?.question_type;
    const settings = question?.question_settings || {};
    if (type === 'essay') {
        return {
            mode: 'manual',
            label: 'Manual',
            detail: 'Essay selalu diperiksa guru (manual).'
        };
    }
    if (type === 'short_answer') {
        const isManual = settings.require_manual_grading === true;
        return isManual
            ? {
                mode: 'manual',
                label: 'Manual',
                detail: 'Isian singkat ini diperiksa manual.'
            }
            : {
                mode: 'automatic',
                label: 'Otomatis',
                detail: 'Isian singkat ini dinilai otomatis dari kunci jawaban.'
            };
    }
    return {
        mode: 'automatic',
        label: 'Otomatis',
        detail: 'Tipe soal ini dinilai otomatis.'
    };
}

function buildSimulationAnalysis(normalData, simulatedData) {
    const normalQuestions = Array.isArray(normalData?.questions) ? normalData.questions : [];
    const simulatedQuestions = Array.isArray(simulatedData?.questions) ? simulatedData.questions : [];
    const normalById = new Map();
    normalQuestions.forEach((question, idx) => {
        normalById.set(question.id, { question, index: idx });
    });

    const shuffleQuestionsEnabled = Boolean(simulatedData?.shuffle_questions ?? examData.shuffle_questions);
    const shuffleOptionsEnabled = Boolean(simulatedData?.shuffle_options ?? examData.shuffle_options);

    const impacts = simulatedQuestions.map((question, simIndex) => {
        const match = normalById.get(question.id);
        const baseQuestion = match ? match.question : null;
        const baseIndex = match ? match.index : null;
        const settings = question.question_settings || {};
        const pgkType = question.pgk_type || settings.pgk_type || 'checkbox';
        const isTableValidation = question.question_type === 'multiple_choice_complex' && pgkType === 'table_validation';
        const tableShuffleAllowed = settings.allow_table_statement_shuffle !== false;
        const optionEligible = (
            question.question_type === 'multiple_choice' ||
            question.question_type === 'true_false' ||
            (question.question_type === 'multiple_choice_complex' && pgkType === 'checkbox')
        );

        const beforeOptionIdentity = getPreviewOptionIdentity(baseQuestion || question);
        const afterOptionIdentity = getPreviewOptionIdentity(question);
        const beforeStatementIdentity = getPreviewStatementIdentity(baseQuestion || question);
        const afterStatementIdentity = getPreviewStatementIdentity(question);
        const statementBeforeLabels = getPreviewStatementLabels(baseQuestion || question);
        const statementAfterLabels = getPreviewStatementLabels(question);
        const statementBeforeIndexedLabels = getPreviewStatementIndexedLabels(baseQuestion || question);
        const statementAfterIndexedLabels = getPreviewStatementIndexedLabels(question);
        const statementBeforeOrder = getPreviewStatementOrderMap(baseQuestion || question);
        const statementAfterOrder = getPreviewStatementOrderMap(question);

        const optionsChanged = optionEligible &&
            beforeOptionIdentity.length >= 2 &&
            afterOptionIdentity.length >= 2 &&
            beforeOptionIdentity.join('|') !== afterOptionIdentity.join('|');
        const statementsChangedTechnical = isTableValidation &&
            beforeStatementIdentity.length >= 2 &&
            afterStatementIdentity.length >= 2 &&
            beforeStatementIdentity.join('|') !== afterStatementIdentity.join('|');
        const statementsChangedVisible = isTableValidation &&
            statementBeforeLabels.length >= 2 &&
            statementAfterLabels.length >= 2 &&
            statementBeforeLabels.join('|') !== statementAfterLabels.join('|');
        const statementsChangedOrderMap = isTableValidation &&
            statementBeforeOrder.length >= 2 &&
            statementAfterOrder.length >= 2 &&
            statementBeforeOrder.join('|') !== statementAfterOrder.join('|');
        const statementsChanged = statementsChangedOrderMap || statementsChangedTechnical;

        const gradingInfo = getPreviewQuestionGrading(question);
        let optionReason = 'Tipe soal ini tidak memakai pengacakan opsi.';
        if (!shuffleOptionsEnabled) {
            optionReason = 'Acak Opsi OFF, jadi urutan opsi/pernyataan tetap.';
        } else if (isTableValidation) {
            if (!tableShuffleAllowed) {
                optionReason = 'Acak pernyataan pada soal ini dimatikan, jadi urutan tetap.';
            } else if (statementsChangedVisible) {
                optionReason = 'Urutan pernyataan tabel berubah karena Acak Opsi ON.';
            } else if (statementsChanged) {
                optionReason = 'Urutan sebenarnya berubah, tapi teks pernyataannya sama sehingga terlihat tetap.';
            } else if (question.image_url) {
                optionReason = 'Tabel berbasis gambar tidak diacak agar mapping tetap aman.';
            } else {
                optionReason = 'Acak pernyataan aktif, tetapi urutan tetap pada simulasi ini.';
            }
        } else if (optionEligible) {
            const isPlaceholder = settings.is_placeholder === true;
            const placeholderSource = String(settings.placeholder_source || '').toLowerCase();

            if (isPlaceholder && placeholderSource === 'image') {
                optionReason = 'Soal gambar masih Mode 1, jadi opsi otomatis tidak diacak.';
            } else if (isPlaceholder && settings.allow_placeholder_shuffle !== true) {
                optionReason = 'Opsi otomatis belum diizinkan ikut acak.';
            } else {
                optionReason = optionsChanged
                    ? 'Urutan opsi berubah karena Acak Opsi ON.'
                    : 'Acak Opsi ON, namun urutan opsi tetap pada simulasi ini.';
            }
        }

        return {
            question,
            baseQuestion,
            simulatedPosition: simIndex + 1,
            normalPosition: baseIndex !== null ? baseIndex + 1 : null,
            orderChanged: baseIndex !== null ? baseIndex !== simIndex : false,
            optionEligible,
            isTableValidation,
            optionsChanged,
            statementsChanged,
            statementsChangedVisible,
            optionReason,
            gradingInfo,
            optionBeforeLabels: getPreviewOptionLabels(baseQuestion || question),
            optionAfterLabels: getPreviewOptionLabels(question),
            statementBeforeLabels,
            statementAfterLabels,
            statementBeforeIndexedLabels,
            statementAfterIndexedLabels,
            statementBeforeOrder,
            statementAfterOrder
        };
    });

    return {
        normalData,
        simulatedData,
        shuffleQuestionsEnabled,
        shuffleOptionsEnabled,
        impacts,
        questionOrderChangedCount: impacts.filter((item) => item.orderChanged).length,
        optionChangedCount: impacts.filter((item) => item.optionsChanged).length,
        statementChangedCount: impacts.filter((item) => item.statementsChanged).length,
        manualCount: impacts.filter((item) => item.gradingInfo.mode === 'manual').length
    };
}

function renderSimulationSummary(analysis, focusPosition = null) {
    const total = analysis.impacts.length;
    const builderDefaults = getBuilderSettings();
    const toggleDefaultSync = (
        examData.shuffle_questions === builderDefaults.smart_auto_shuffle_questions &&
        examData.shuffle_options === builderDefaults.smart_auto_shuffle_options
    );

    return `
        <div style="padding:0.95rem; background: var(--dark-lighter); border-radius:0.6rem; margin-bottom:0.85rem; border:1px solid rgba(59,130,246,0.25);">
            <h2 style="margin:0 0 0.45rem 0;">${escapeHtml(examData.title)}</h2>
            <p style="margin:0; color: var(--text-secondary); font-size:0.84rem;">
                <i class="fas fa-clock"></i> ${analysis.simulatedData?.duration_minutes || examData.duration_minutes} menit
                &nbsp;|&nbsp;
                <i class="fas fa-list"></i> ${focusPosition ? '1 soal fokus' : `${total} soal`}
                &nbsp;|&nbsp;
                <i class="fas fa-arrows-rotate"></i> Perbandingan: mode normal vs mode siswa
            </p>
        </div>
        <div style="margin-bottom:0.85rem; padding:0.85rem; border:1px solid rgba(148,163,184,0.28); border-radius:0.6rem; background:rgba(15,23,42,0.55);">
            <div style="display:flex; flex-wrap:wrap; gap:0.45rem; margin-bottom:0.55rem;">
                <span style="padding:0.2rem 0.55rem; border-radius:999px; border:1px solid ${analysis.shuffleQuestionsEnabled ? 'rgba(34,197,94,0.5)' : 'rgba(148,163,184,0.45)'}; color:${analysis.shuffleQuestionsEnabled ? '#86efac' : '#cbd5e1'}; font-size:0.76rem;">
                    Acak Soal: ${analysis.shuffleQuestionsEnabled ? 'ON' : 'OFF'}
                </span>
                <span style="padding:0.2rem 0.55rem; border-radius:999px; border:1px solid ${analysis.shuffleOptionsEnabled ? 'rgba(34,197,94,0.5)' : 'rgba(148,163,184,0.45)'}; color:${analysis.shuffleOptionsEnabled ? '#86efac' : '#cbd5e1'}; font-size:0.76rem;">
                    Acak Opsi: ${analysis.shuffleOptionsEnabled ? 'ON' : 'OFF'}
                </span>
                <span style="padding:0.2rem 0.55rem; border-radius:999px; border:1px solid rgba(56,189,248,0.45); color:#bae6fd; font-size:0.76rem;">
                    Sinkron Toggle-Default: ${toggleDefaultSync ? 'YA' : 'BELUM'}
                </span>
            </div>
            <div style="display:grid; gap:0.35rem; color: var(--text-secondary); font-size:0.82rem;">
                <div><i class="fas fa-arrow-right-arrow-left"></i> Urutan soal berubah: <strong style="color:var(--text-primary);">${analysis.questionOrderChangedCount}/${total}</strong></div>
                <div><i class="fas fa-random"></i> Urutan opsi berubah: <strong style="color:var(--text-primary);">${analysis.optionChangedCount}/${total}</strong></div>
                <div><i class="fas fa-table"></i> Urutan pernyataan tabel berubah: <strong style="color:var(--text-primary);">${analysis.statementChangedCount}/${total}</strong></div>
                <div><i class="fas fa-user-check"></i> Soal manual: <strong style="color:var(--text-primary);">${analysis.manualCount}</strong> | Otomatis: <strong style="color:var(--text-primary);">${Math.max(total - analysis.manualCount, 0)}</strong></div>
            </div>
        </div>
    `;
}

function renderSimulatedPreview(normalData, simulatedData, focusQuestionId = null) {
    const content = document.getElementById('preview-content');
    if (!content) return;

    const analysis = buildSimulationAnalysis(normalData, simulatedData);
    const allImpacts = analysis.impacts;
    let previewImpacts = allImpacts;
    let focusPosition = null;
    if (focusQuestionId !== null && focusQuestionId !== undefined) {
        const idx = allImpacts.findIndex((item) => item.question.id === focusQuestionId);
        if (idx >= 0) {
            focusPosition = idx + 1;
            previewImpacts = [allImpacts[idx]];
        } else {
            showAlert('Soal ini belum ditemukan di data simulasi. Coba simpan draft lagi.', 'warning');
            previewImpacts = [];
        }
    }
    let html = renderSimulationSummary(analysis, focusPosition);
    if (focusPosition) {
        html += '<div style="margin-bottom:0.75rem; padding:0.6rem 0.7rem; border:1px solid rgba(59,130,246,0.35); border-radius:0.45rem; background:rgba(59,130,246,0.08); color:var(--text-secondary); font-size:0.82rem;"><i class="fas fa-map-marker-alt"></i> Soal ini ada di urutan <strong style="color:var(--text-primary);">' + focusPosition + '</strong> pada simulasi penuh.</div>';
    }

    previewImpacts.forEach((impact, i) => {
        const q = impact.question;
        const type = q.question_type;
        const pgkType = q.pgk_type || (q.question_settings && q.question_settings.pgk_type) || 'checkbox';
        const orderBadgeColor = impact.orderChanged ? '#f59e0b' : '#22c55e';
        const optionsChangedFlag = impact.isTableValidation ? impact.statementsChanged : impact.optionsChanged;
        const optionsChangedLabel = (
            impact.isTableValidation && optionsChangedFlag && impact.statementsChangedVisible === false
        ) ? 'BERUBAH*' : (optionsChangedFlag ? 'BERUBAH' : 'TETAP');
        const optionsBadgeColor = optionsChangedFlag ? '#f59e0b' : '#22c55e';
        const gradingBadgeColor = impact.gradingInfo.mode === 'manual' ? '#f59e0b' : '#22c55e';

        html += '<div class="preview-question" style="padding: 1rem; background: var(--dark-card); border-radius: 0.5rem; margin-bottom: 1rem; border-left: 3px solid var(--primary);">';
        html += '<div class="preview-question-text" style="margin-bottom: 0.75rem;">';
        html += '<span style="color: var(--primary); font-weight: 600;">' + (i + 1) + '.</span> ';
        html += (renderBuilderRichText(q.question_text) || '<em style="color: var(--text-secondary);">Pertanyaan kosong</em>');
        html += '<span style="color: var(--text-secondary); font-size: 0.8rem; margin-left: 0.5rem;">(' + (q.points || 1) + ' poin)</span>';
        html += '<span style="background: var(--primary); color: white; padding: 2px 8px; border-radius: 4px; font-size: 0.7rem; margin-left: 0.5rem;">' + getQuestionTypeLabel(type) + '</span>';
        html += '</div>';
        html += `
            <div style="display:flex; flex-wrap:wrap; gap:0.4rem; margin-bottom:0.6rem;">
                <span style="font-size:0.75rem; padding:0.2rem 0.5rem; border-radius:999px; border:1px solid ${orderBadgeColor}; color:${orderBadgeColor};">
                    Urutan Soal: ${impact.orderChanged ? 'BERUBAH' : 'TETAP'}
                </span>
                <span style="font-size:0.75rem; padding:0.2rem 0.5rem; border-radius:999px; border:1px solid ${optionsBadgeColor}; color:${optionsBadgeColor};">
                    ${impact.isTableValidation ? 'Urutan Pernyataan' : 'Urutan Opsi'}: ${optionsChangedLabel}
                </span>
                <span style="font-size:0.75rem; padding:0.2rem 0.5rem; border-radius:999px; border:1px solid ${gradingBadgeColor}; color:${gradingBadgeColor};">
                    Penilaian: ${escapeHtml(impact.gradingInfo.label)}
                </span>
            </div>
        `;
        html += `
            <div style="margin-bottom:0.55rem; padding:0.55rem 0.65rem; background:rgba(15,23,42,0.5); border:1px solid rgba(148,163,184,0.25); border-radius:0.45rem; color:var(--text-secondary); font-size:0.8rem;">
                <div><i class="fas fa-location-crosshairs"></i> Posisi normal: <strong style="color:var(--text-primary);">${impact.normalPosition || '-'}</strong> | Posisi simulasi: <strong style="color:var(--text-primary);">${impact.simulatedPosition}</strong></div>
                <div style="margin-top:0.3rem;"><i class="fas fa-circle-info"></i> ${escapeHtml(impact.optionReason)}</div>
                <div style="margin-top:0.3rem;"><i class="fas fa-graduation-cap"></i> ${escapeHtml(impact.gradingInfo.detail)}</div>
            </div>
        `;

        if (q.image_url) {
            html += '<img src="' + q.image_url + '" style="max-width: 200px; border-radius: 0.5rem; margin-bottom: 0.5rem;">';
        }
        if (q.video_url) {
            html += '<div style="color: var(--text-secondary); margin-bottom: 0.5rem;"><i class="fab fa-youtube" style="color: #ff0000;"></i> Video YouTube terlampir</div>';
        }
        if (q.stimulus) {
            html += '<div style="margin-bottom: 1rem; padding: 0.75rem; background: var(--dark); border-left: 3px solid #f59e0b; font-style: italic;">' + renderBuilderRichText(q.stimulus) + '</div>';
        }

        if (type === 'multiple_choice' || type === 'true_false' || (type === 'multiple_choice_complex' && pgkType === 'checkbox')) {
            const beforeLabels = impact.optionBeforeLabels.join(' -> ') || '-';
            const afterLabels = impact.optionAfterLabels.join(' -> ') || '-';
            html += `
                <div style="margin-bottom:0.55rem; padding:0.5rem 0.6rem; border:1px solid rgba(59,130,246,0.25); border-radius:0.45rem; background:rgba(59,130,246,0.08); color:var(--text-secondary); font-size:0.78rem;">
                    <div><strong style="color:#bfdbfe;">Normal:</strong> ${escapeHtml(beforeLabels)}</div>
                    <div style="margin-top:0.25rem;"><strong style="color:#bfdbfe;">Simulasi:</strong> ${escapeHtml(afterLabels)}</div>
                </div>
            `;
            (q.options || []).forEach((opt, j) => {
                const text = typeof opt === 'string'
                    ? opt
                    : (opt?.option_text || opt?.text || '');
                const rowLabel = getOptionLabel(j);
                html += '<div class="preview-option" style="display:flex; align-items:center; gap:0.6rem; padding:0.5rem; margin-bottom:0.25rem; background: var(--dark); border-radius:0.25rem;">';
                html += '<span style="font-weight:600; color: var(--text-secondary); min-width:20px;">' + rowLabel + '.</span>';
                html += '<span>' + (escapeHtml(text) || '<em style="color: var(--text-secondary);">Opsi kosong</em>') + '</span>';
                html += '</div>';
            });
        } else if (type === 'multiple_choice_complex' && pgkType === 'table_validation') {
            const rawStatements = (q.question_settings && q.question_settings.statements) || [];
            const beforeStmt = impact.statementBeforeIndexedLabels.join(' | ') || '-';
            const afterStmt = impact.statementAfterIndexedLabels.join(' | ') || '-';
            const beforeOrder = (impact.statementBeforeOrder || []).join(' -> ') || '-';
            const afterOrder = (impact.statementAfterOrder || []).join(' -> ') || '-';
            html += `
                <div style="margin-bottom:0.55rem; padding:0.5rem 0.6rem; border:1px solid rgba(59,130,246,0.25); border-radius:0.45rem; background:rgba(59,130,246,0.08); color:var(--text-secondary); font-size:0.78rem;">
                    <div><strong style="color:#bfdbfe;">Normal:</strong> ${escapeHtml(beforeStmt)}</div>
                    <div style="margin-top:0.25rem;"><strong style="color:#bfdbfe;">Simulasi:</strong> ${escapeHtml(afterStmt)}</div>
                    <div style="margin-top:0.25rem;"><strong style="color:#bfdbfe;">Urutan indeks asli:</strong> Normal ${escapeHtml(beforeOrder)} | Simulasi ${escapeHtml(afterOrder)}</div>
                </div>
            `;
            html += '<table style="width: 100%; border-collapse: collapse; font-size: 0.9rem;">';
            html += '<tr style="background: rgba(99, 102, 241, 0.15); color: var(--text-primary);">';
            html += '<th style="padding: 0.5rem; text-align: left; border: 1px solid var(--border-color);">Pernyataan</th>';
            html += '<th style="padding: 0.5rem; text-align: center; width: 80px; border: 1px solid var(--border-color);">Benar</th>';
            html += '<th style="padding: 0.5rem; text-align: center; width: 80px; border: 1px solid var(--border-color);">Salah</th>';
            html += '</tr>';
            rawStatements.forEach((stmt) => {
                const text = typeof stmt === 'object' ? (stmt.text || '-') : stmt;
                const sourceIndex = (typeof stmt === 'object' && stmt !== null && Number.isInteger(stmt.original_index))
                    ? stmt.original_index + 1
                    : null;
                html += '<tr>';
                html += '<td style="padding: 0.5rem; border: 1px solid var(--border-color);">' +
                    (sourceIndex ? `<span style="color:#93c5fd; font-weight:600; margin-right:0.35rem;">[#${sourceIndex}]</span>` : '') +
                    (escapeHtml(String(text || '-')) || '-') +
                    '</td>';
                html += '<td style="padding: 0.5rem; text-align: center; border: 1px solid var(--border-color);"><input type="radio" disabled></td>';
                html += '<td style="padding: 0.5rem; text-align: center; border: 1px solid var(--border-color);"><input type="radio" disabled></td>';
                html += '</tr>';
            });
            html += '</table>';
        } else if (type === 'essay') {
            html += '<div style="padding: 1rem; background: var(--dark); border-radius: 0.5rem; color: var(--text-secondary); border: 1px dashed var(--border-color);"><i class="fas fa-keyboard"></i> Area jawaban essay (teks panjang)</div>';
        } else if (type === 'short_answer') {
            html += '<div style="padding: 0.75rem; background: var(--dark); border-radius: 0.5rem; border: 1px dashed var(--border-color); color: var(--text-secondary);"><i class="fas fa-pen"></i> Jawaban singkat</div>';
        }

        html += '</div>';
    });

    content.innerHTML = html;
}

async function simulateSingleQuestion(questionIndex) {
    if (!examId) {
        showAlert('Simpan draft dulu sebelum simulasi per soal.', 'warning');
        return;
    }

    const question = examData.questions[questionIndex];
    if (!question) {
        showAlert('Soal tidak ditemukan.', 'warning');
        return;
    }

    try {
        await saveExam();
    } catch (error) {
        showAlert('Gagal menyimpan sebelum simulasi soal: ' + (error.message || 'Unknown error'), 'danger');
        return;
    }

    const title = document.getElementById('preview-modal-title');
    const content = document.getElementById('preview-content');
    if (title) {
        title.innerHTML = '<i class="fas fa-shuffle"></i> Simulasi Soal ' + (questionIndex + 1);
    }
    if (content) {
        content.innerHTML = '<div style="padding:1rem; color: var(--text-secondary);"><i class="fas fa-spinner fa-spin"></i> Menyiapkan simulasi soal ini...</div>';
    }
    openModal('preview-modal');

    try {
        const persistedQuestionId = question.id;
        if (!persistedQuestionId) {
            showAlert('ID soal belum tersedia. Coba simpan lagi.', 'warning');
            return;
        }
        const simulationBundle = await fetchSimulationComparison(examId);
        renderSimulatedPreview(
            simulationBundle.normalData,
            simulationBundle.simulatedData,
            persistedQuestionId
        );
    } catch (error) {
        if (content) {
            content.innerHTML = '<div style="padding:1rem; color: var(--danger);"><i class="fas fa-triangle-exclamation"></i> Gagal memuat simulasi soal.</div>';
        }
        showAlert('Simulasi soal gagal: ' + (error.message || 'Unknown error'), 'danger');
    }
}

/* ===== Module: 30-media-modal-publish-time-points.js ===== */

function getQuestionTypeLabel(type) {
    const labels = {
        'multiple_choice': 'Pilihan Ganda',
        'multiple_choice_complex': 'Pilihan Ganda Kompleks',
        'essay': 'Essay',
        'true_false': 'Benar/Salah',
        'short_answer': 'Isian Singkat'
    };
    return labels[type] || type;
}

function hasEmbeddedOptionsFromQuestionText(text = '') {
    const normalized = String(text || '')
        .replace(/<br\s*\/?>/gi, '\n')
        .replace(/<\/(p|div|li)>/gi, '\n')
        .replace(/<[^>]*>/g, ' ');
    const labels = new Set();
    const matches = normalized.matchAll(/\b([A-Za-z])[.):]\s+\S+/g);
    for (const match of matches) {
        labels.add(match[1].toUpperCase());
    }
    return labels.size >= 2;
}

// Helper: Validate exam completeness before publishing
function validateForPublish() {
    const errors = [];
    let firstErrorIndex = -1;

    const countRealOptions = (options = []) => {
        return countRealOptionTexts(options);
    };

    examData.questions.forEach((q, index) => {
        const num = index + 1;

        // 1. Cek Konten Soal (Teks atau Media wajib ada)
        // Strip HTML tags
        const div = document.createElement('div');
        div.innerHTML = q.text || '';
        const textContent = div.textContent.trim();
        const hasMedia = q.image_url || q.video_url || q.audio_url;

        if (!textContent && !hasMedia) {
            errors.push(`Soal No. ${num}: Pertanyaan masih kosong`);
            if (firstErrorIndex === -1) firstErrorIndex = index;
        }

        // 2. Validasi Spesifik per Tipe Soal
        if (q.type === 'multiple_choice') {
            const minimumOptions = getMinimumOptionCountByType('multiple_choice');
            const hasCorrectAnswer = q.correct_answer !== null && q.correct_answer !== undefined && q.correct_answer !== '' && q.correct_answer !== -1;
            const realOptions = countRealOptions(q.options || []);
            const isImageMode = !!q.image_url;
            const hasEmbeddedOptions = hasEmbeddedOptionsFromQuestionText(q.text);
            const permissiveKeyOnlyMode = hasCorrectAnswer && !isImageMode && !hasEmbeddedOptions;

            if (realOptions < minimumOptions && !isImageMode && !hasEmbeddedOptions && !permissiveKeyOnlyMode) {
                errors.push(`Soal No. ${num} (Pilihan Ganda): Minimal harus ada ${minimumOptions} opsi jawaban`);
                if (firstErrorIndex === -1) firstErrorIndex = index;
            }

            if (!hasCorrectAnswer) {
                errors.push(`Soal No. ${num} (Pilihan Ganda): Kunci jawaban belum dipilih`);
                if (firstErrorIndex === -1) firstErrorIndex = index;
            }
        }
        else if (q.type === 'true_false') {
            if (q.correct_answer === null || q.correct_answer === undefined || q.correct_answer === '') {
                errors.push(`Soal No. ${num}: Belum menentukan jawaban Benar/Salah`);
                if (firstErrorIndex === -1) firstErrorIndex = index;
            }
        }
        else if (q.type === 'short_answer') {
            const settings = q.question_settings || {};
            const key = q.correct_answer || (settings.acceptable_answers && settings.acceptable_answers[0]);
            const isManual = q.require_manual_grading || settings.require_manual_grading;

            if (!isManual && (!key || !key.toString().trim())) {
                errors.push(`Soal No. ${num}: Kunci jawaban isian singkat belum diisi`);
                if (firstErrorIndex === -1) firstErrorIndex = index;
            }
        }
        else if (q.type === 'multiple_choice_complex') {
            if (!q.image_url) {
                if (!q.stimulus || !q.stimulus.trim()) {
                    errors.push(`Soal No. ${num} (PGK): Stimulus/bacaan wajib diisi untuk soal HOTS`);
                    if (firstErrorIndex === -1) firstErrorIndex = index;
                }
            }

            const resolvedPgkType = q.pgk_type || (q.question_settings && q.question_settings.pgk_type) || 'checkbox';

            if (resolvedPgkType === 'checkbox') {
                const minimumOptions = getMinimumOptionCountByType('multiple_choice_complex', 'checkbox');
                const realOptions = countRealOptions(q.options || []);
                const isImageMode = !!q.image_url;
                const hasEmbeddedOptions = hasEmbeddedOptionsFromQuestionText(q.text);
                const permissiveKeyOnlyMode = !!(q.correct_answers && q.correct_answers.length >= 2 && !isImageMode && !hasEmbeddedOptions);

                if (realOptions < minimumOptions && !isImageMode && !hasEmbeddedOptions && !permissiveKeyOnlyMode) {
                    errors.push(`Soal No. ${num} (PGK): Minimal harus ada ${minimumOptions} opsi jawaban`);
                    if (firstErrorIndex === -1) firstErrorIndex = index;
                }

                if (!q.correct_answers || q.correct_answers.length < 2) {
                    errors.push(`Soal No. ${num}: Minimal 2 kunci jawaban harus dicentang`);
                    if (firstErrorIndex === -1) firstErrorIndex = index;
                }
            } else if (resolvedPgkType === 'table_validation') {
                const statements = q.statements || (q.question_settings && q.question_settings.statements) || [];
                const statementAnswers = q.statement_answers || (q.question_settings && q.question_settings.statement_answers) || [];
                const validStatements = statements.filter((s) => (s || '').trim().length > 0);
                const hasImageMode = !!q.image_url;

                if (!hasImageMode && validStatements.length < 2) {
                    errors.push(`Soal No. ${num} (PGK Tabel): Minimal harus ada 2 pernyataan`);
                    if (firstErrorIndex === -1) firstErrorIndex = index;
                }
                if (hasImageMode && validStatements.length < 2 && (statementAnswers || []).length < 2) {
                    errors.push(`Soal No. ${num} (PGK Tabel): Minimal harus ada 2 pernyataan`);
                    if (firstErrorIndex === -1) firstErrorIndex = index;
                }

                const requiredAnswersCount = hasImageMode
                    ? Math.max(validStatements.length, 2)
                    : validStatements.length;
                if ((statementAnswers || []).length < requiredAnswersCount) {
                    errors.push(`Soal No. ${num} (PGK Tabel): Jawaban Benar/Salah belum lengkap`);
                    if (firstErrorIndex === -1) firstErrorIndex = index;
                }
            }
        }
    });

    if (errors.length > 0) {
        let messageHtml = `
            <div style="text-align: left">
                <strong>Ujian belum siap dipublish:</strong>
                <ul style="margin: 5px 0 0 20px; padding: 0; list-style-type: disc; max-height: 200px; overflow-y: auto;">
                    ${errors.map(e => `<li style="margin-bottom: 4px;">${e}</li>`).join('')}
                </ul>
                <div style="margin-top: 8px; font-size: 0.9em; color: #cbd5e1;">Silakan lengkapi soal-soal tersebut terlebih dahulu.</div>
            </div>
        `;

        showAlert(messageHtml, 'warning');

        if (firstErrorIndex !== -1) {
            setActiveQuestion(firstErrorIndex);
        }
        return false;
    }

    return true;
}

// Publish
async function publishExam() {
    if (examData.questions.length === 0) {
        showAlert('Tambahkan minimal 1 soal sebelum publish', 'warning');
        return;
    }

    // Jalankan validasi lengkap
    if (!validateForPublish()) {
        return;
    }

    // Open the new Multi-step Publish Wizard
    openPublishModal();
}

// Helpers
function formatDateTimeLocal(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    const hours = String(date.getHours()).padStart(2, '0');
    const minutes = String(date.getMinutes()).padStart(2, '0');
    return `${year}-${month}-${day}T${hours}:${minutes}`;
}

// Escape HTML to prevent XSS in both text nodes and quoted HTML attributes.
function escapeHtml(text) {
    if (text === null || text === undefined) return '';
    return String(text)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

// YouTube video helpers
async function promptVideoUrl(questionIndex) {
    const url = await showInputModal(
        'Tambah Video YouTube',
        'Paste link video YouTube untuk ditampilkan dalam soal ini:',
        'https://www.youtube.com/watch?v=',
        'https://www.youtube.com/watch?v=xxxxx'
    );
    if (!url) return;

    const videoId = extractYouTubeId(url);
    if (!videoId) {
        showAlert('URL YouTube tidak valid. Pastikan format link benar.', 'danger');
        return;
    }

    examData.questions[questionIndex].video_url = url;
    renderQuestions();
    triggerAutoSave();
    showAlert('Video berhasil ditambahkan', 'success');
}

function extractYouTubeId(url) {
    if (!url) return null;

    // Match patterns:
    // youtube.com/watch?v=ID
    // youtu.be/ID
    // youtube.com/embed/ID
    const patterns = [
        /youtube\.com\/watch\?v=([a-zA-Z0-9_-]{11})/,
        /youtu\.be\/([a-zA-Z0-9_-]{11})/,
        /youtube\.com\/embed\/([a-zA-Z0-9_-]{11})/
    ];

    for (const pattern of patterns) {
        const match = url.match(pattern);
        if (match) return match[1];
    }

    return null;
}

function removeVideo(questionIndex) {
    examData.questions[questionIndex].video_url = null;
    renderQuestions();
    triggerAutoSave();
}

function hasTutorialValue(value) {
    if (value === null || value === undefined) return false;
    return String(value).trim().length > 0;
}

function getTutorialKeyProgress() {
    let total = 0;
    let completed = 0;

    for (const q of examData.questions || []) {
        const pgkType = q.pgk_type || 'checkbox';

        if (q.type === 'multiple_choice' || q.type === 'true_false') {
            total += 1;
            const hasKey = q.correct_answer !== null && q.correct_answer !== undefined && q.correct_answer !== '';
            if (hasKey) completed += 1;
            continue;
        }

        if (q.type === 'multiple_choice_complex' && pgkType === 'checkbox') {
            total += 1;
            if (Array.isArray(q.correct_answers) && q.correct_answers.length >= 2) {
                completed += 1;
            }
            continue;
        }

        if (q.type === 'short_answer' && q.require_manual_grading !== true) {
            total += 1;
            if (hasTutorialValue(q.correct_answer)) {
                completed += 1;
            }
        }
    }

    return { total, completed };
}

function getTutorialSteps() {
    const builderDefaults = getBuilderSettings();
    const hasTitle = hasTutorialValue(examData.title) && examData.title !== 'Ujian Tanpa Judul';
    const hasSubject = hasTutorialValue(examData.subject);
    const hasType = hasTutorialValue(examData.exam_type);
    const hasAcademicYear = hasTutorialValue(examData.academic_year);
    const hasBasicInfo = hasTitle && hasSubject && hasType && hasAcademicYear;

    const hasDuration = Number(examData.duration_minutes) > 0;
    const hasStart = hasTutorialValue(examData.start_time) || hasTutorialValue(document.getElementById('start-time')?.value);
    const hasEnd = hasTutorialValue(examData.end_time) || hasTutorialValue(document.getElementById('end-time')?.value);
    const hasSchedule = hasDuration && hasStart && hasEnd;

    const totalQuestions = (examData.questions || []).length;
    const hasQuestions = totalQuestions > 0;

    const keyProgress = getTutorialKeyProgress();
    const hasKeys = keyProgress.total === 0 ? true : keyProgress.completed === keyProgress.total;

    const eligibleImageQuestions = (examData.questions || []).filter((q) => !!q.image_url);
    const imageModeReady = true;

    const shuffleReady = examData.shuffle_questions === true || examData.shuffle_options === true;
    const toggleDefaultSync = (
        examData.shuffle_questions === builderDefaults.smart_auto_shuffle_questions &&
        examData.shuffle_options === builderDefaults.smart_auto_shuffle_options
    );
    const nonImagePlaceholderQuestions = (examData.questions || []).filter((q) => {
        const pgkType = q.pgk_type || 'checkbox';
        const eligible = q.type === 'multiple_choice' || (q.type === 'multiple_choice_complex' && pgkType === 'checkbox');
        return eligible && q.is_placeholder === true && q.placeholder_source !== 'image';
    });
    const nonImagePlaceholderShuffleOn = nonImagePlaceholderQuestions.filter((q) => q.allow_placeholder_shuffle === true).length;
    const placeholderAutoReady = (
        nonImagePlaceholderQuestions.length === 0 ||
        nonImagePlaceholderShuffleOn === nonImagePlaceholderQuestions.length
    );
    const tableShuffleQuestions = (examData.questions || []).filter((q) => {
        const pgkType = q.pgk_type || 'checkbox';
        return q.type === 'multiple_choice_complex' && pgkType === 'table_validation' && !q.image_url;
    });
    const tableShuffleOn = tableShuffleQuestions.filter((q) => q.allow_table_statement_shuffle !== false).length;
    const tableShuffleReady = (
        tableShuffleQuestions.length === 0 ||
        tableShuffleOn === tableShuffleQuestions.length
    );
    const canSimulate = Boolean(examId) && hasQuestions;
    const publishReady = hasBasicInfo && hasSchedule && hasQuestions && hasKeys;

    return [
        {
            title: 'Isi data ujian dulu',
            icon: 'fa-id-card',
            done: hasBasicInfo,
            description: 'Langkah awal paling penting: isi informasi ujian supaya siswa tidak bingung.',
            checks: [
                { label: 'Judul ujian sudah diisi', ok: hasTitle },
                { label: 'Bidang studi sudah dipilih', ok: hasSubject },
                { label: 'Tipe ujian sudah dipilih', ok: hasType },
                { label: 'Tahun ajaran sudah dipilih', ok: hasAcademicYear }
            ],
            tips: [
                'Gunakan judul yang singkat dan jelas.',
                'Pilih tipe ujian sesuai kebutuhan agar rekap lebih rapi.'
            ],
            action: hasBasicInfo
                ? 'Data dasar sudah aman. Lanjut ke langkah berikutnya.'
                : 'Isi judul, bidang studi, tipe ujian, dan tahun ajaran di bar atas.'
        },
        {
            title: 'Atur waktu dan durasi',
            icon: 'fa-clock',
            done: hasSchedule,
            description: 'Pastikan waktu mulai, waktu selesai, dan durasi sesuai rencana pelaksanaan.',
            checks: [
                { label: 'Durasi ujian sudah valid', ok: hasDuration },
                { label: 'Waktu mulai sudah terisi', ok: hasStart },
                { label: 'Waktu selesai sudah terisi', ok: hasEnd }
            ],
            tips: [
                'Klik tombol "Atur Jadwal" agar waktu lebih presisi.',
                'Gunakan durasi yang realistis sesuai jumlah soal.'
            ],
            action: hasSchedule
                ? 'Jadwal sudah siap dipakai.'
                : 'Klik tombol "Atur Jadwal", lalu cek lagi start/end time.'
        },
        {
            title: 'Atur default soal (sekali saja)',
            icon: 'fa-gears',
            done: true,
            description: 'Gunakan tombol Pengaturan untuk menentukan default mode soal baru agar kerja lebih cepat.',
            checks: [
                { label: `PG default cepat: ${builderDefaults.default_mc_key_only ? 'ON' : 'OFF'}`, ok: true },
                { label: `PGK default cepat: ${builderDefaults.default_pgk_key_only ? 'ON' : 'OFF'}`, ok: true },
                { label: 'Default soal gambar: Mode 1 (normal)', ok: true }
            ],
            tips: [
                'Klik tombol "Pengaturan" di bar atas untuk ubah default kapan saja.',
                'Untuk soal gambar, sistem memakai mode normal (Mode 1).'
            ],
            action: 'Default saat ini sudah tersimpan per ujian. Anda bisa ubah kapan saja.'
        },
        {
            title: 'Tambah soal yang dibutuhkan',
            icon: 'fa-square-plus',
            done: hasQuestions,
            description: 'Buat soal sesuai tipe yang diinginkan: PG, PGK, Isian, Essay, atau Benar/Salah.',
            checks: [
                { label: `Jumlah soal saat ini: ${totalQuestions}`, ok: hasQuestions }
            ],
            tips: [
                'Mulai dari tipe soal yang paling sering dipakai.',
                'Default PG: 4 opsi (A-D), boleh dikurangi sampai 3 (A-C).',
                'Default PGK Tipe A: 5 opsi (A-E), boleh dikurangi sampai 4 (A-D).',
                'Gunakan poin yang konsisten agar penilaian adil.'
            ],
            action: hasQuestions
                ? 'Soal sudah ada. Lanjut ke kunci jawaban.'
                : 'Klik salah satu tombol tambah soal di bagian bawah.'
        },
        {
            title: 'Pastikan kunci jawaban terisi',
            icon: 'fa-key',
            done: hasKeys,
            description: 'Sistem butuh kunci jawaban untuk penilaian otomatis yang akurat.',
            checks: [
                {
                    label: keyProgress.total > 0
                        ? `Kunci terisi: ${keyProgress.completed}/${keyProgress.total} soal`
                        : 'Belum ada soal yang butuh kunci otomatis',
                    ok: hasKeys
                }
            ],
            tips: [
                'Untuk PGK checkbox, centang minimal 2 jawaban benar.',
                'Untuk isian singkat, isi kata kunci jika bukan manual grading.'
            ],
            action: hasKeys
                ? 'Kunci jawaban sudah lengkap.'
                : 'Buka soal yang belum lengkap lalu pilih kunci jawabannya.'
        },
        {
            title: 'Pastikan soal gambar jelas',
            icon: 'fa-image',
            done: imageModeReady,
            description: 'Soal gambar sekarang selalu memakai mode normal agar sederhana dan konsisten.',
            checks: [
                {
                    label: `Total soal bergambar: ${eligibleImageQuestions.length}`,
                    ok: true
                }
            ],
            tips: [
                'Gunakan gambar yang jelas dan mudah dibaca.',
                'Pastikan kunci jawaban per opsi sudah diverifikasi admin.'
            ],
            action: 'Semua soal gambar otomatis menggunakan Mode 1 (normal).'
        },
        {
            title: 'Nyalakan acak soal/opsi bila perlu',
            icon: 'fa-shuffle',
            done: shuffleReady && placeholderAutoReady && tableShuffleReady,
            description: 'Fitur acak membantu mencegah pola jawaban yang sama antar siswa.',
            checks: [
                { label: 'Acak Soal aktif', ok: examData.shuffle_questions === true },
                { label: 'Acak Opsi aktif', ok: examData.shuffle_options === true },
                { label: `Auto Acak Opsi default: ${builderDefaults.smart_auto_shuffle_options ? 'ON' : 'OFF'}`, ok: true },
                { label: `Auto Acak Soal default: ${builderDefaults.smart_auto_shuffle_questions ? 'ON' : 'OFF'}`, ok: true },
                { label: `Sinkron toggle & default: ${toggleDefaultSync ? 'YA' : 'BELUM'}`, ok: toggleDefaultSync },
                { label: `Placeholder non-gambar ikut acak: ${nonImagePlaceholderShuffleOn}/${nonImagePlaceholderQuestions.length}`, ok: placeholderAutoReady },
                { label: `PGK Tipe B (non-gambar) ikut acak: ${tableShuffleOn}/${tableShuffleQuestions.length}`, ok: tableShuffleReady }
            ],
            tips: [
                'Minimal aktifkan salah satu: Acak Soal atau Acak Opsi.',
                'Untuk soal bergambar: jika opsi masih otomatis (teks kosong), urutan dibuat tetap.',
                'Kalau teks opsi diisi manual, pengacakan mengikuti toggle global Acak Opsi.',
                'Untuk mode cepat (opsi kosong non-gambar), default-nya akan ikut tercentang jika Auto Acak Opsi ON.',
                'Untuk PGK Tipe B, centang acak pernyataan bisa diatur per soal.'
            ],
            action: shuffleReady && placeholderAutoReady && tableShuffleReady
                ? 'Mode acak sudah aktif dan default placeholder/PGK Tipe B sudah sinkron.'
                : 'Aktifkan acak, lalu pastikan placeholder non-gambar dan PGK Tipe B ikut tercentang.'
        },
        {
            title: 'Cek simulasi lalu publish',
            icon: 'fa-rocket',
            done: publishReady,
            description: 'Langkah akhir: simpan draft, uji simulasi, lalu publish.',
            checks: [
                { label: 'Draft ujian sudah pernah tersimpan', ok: canSimulate },
                { label: 'Syarat publish sudah terpenuhi', ok: publishReady }
            ],
            tips: [
                'Gunakan tombol "Simulasi" untuk melihat panel dampak: normal vs mode siswa.',
                'Lihat badge "Urutan Soal/Opsi" agar cepat tahu apa yang berubah.',
                'Gunakan simulasi per soal untuk cek soal tertentu lebih cepat.'
            ],
            action: publishReady
                ? 'Semua siap. Lanjut klik Publish.'
                : 'Lengkapi ceklis langkah sebelumnya sampai status siap.'
        }
    ];
}

function renderTutorialStep() {
    const slide = document.getElementById('tutorial-slide');
    const counter = document.getElementById('tutorial-step-counter');
    const progressBar = document.getElementById('tutorial-progress-bar');
    const prevBtn = document.getElementById('tutorial-prev-btn');
    const nextBtn = document.getElementById('tutorial-next-btn');
    if (!slide || !counter || !progressBar || !prevBtn || !nextBtn) return;

    const steps = getTutorialSteps();
    if (steps.length === 0) return;

    tutorialStepIndex = Math.min(Math.max(tutorialStepIndex, 0), steps.length - 1);
    const step = steps[tutorialStepIndex];
    const progress = ((tutorialStepIndex + 1) / steps.length) * 100;
    const statusClass = step.done ? 'done' : 'todo';
    const statusText = step.done ? 'Sudah siap' : 'Perlu dicek';
    const statusIcon = step.done ? 'fa-check-circle' : 'fa-triangle-exclamation';
    const statusColor = step.done ? '#22c55e' : '#f59e0b';

    counter.textContent = `Langkah ${tutorialStepIndex + 1} dari ${steps.length}`;
    progressBar.style.width = `${progress}%`;

    const checksHtml = (step.checks || []).map((item) => `
        <div class="tutorial-check-row ${item.ok ? 'ok' : 'missing'}">
            <i class="fas ${item.ok ? 'fa-check' : 'fa-xmark'}"></i>
            <span>${escapeHtml(item.label)}</span>
        </div>
    `).join('');

    const tipsHtml = (step.tips || []).map((tip) => `<li>${escapeHtml(tip)}</li>`).join('');
    const actionHtml = step.action
        ? `<div class="tutorial-action-box"><i class="fas fa-bolt"></i><span>${escapeHtml(step.action)}</span></div>`
        : '';

    slide.classList.remove('animate');
    slide.innerHTML = `
        <div class="tutorial-card-title">
            <h4><i class="fas ${step.icon}" style="color:${statusColor};"></i> ${escapeHtml(step.title)}</h4>
            <span class="tutorial-status-pill ${statusClass}"><i class="fas ${statusIcon}"></i> ${statusText}</span>
        </div>
        <p class="tutorial-desc">${escapeHtml(step.description)}</p>
        <div class="tutorial-check-list">${checksHtml}</div>
        <div class="tutorial-tips">
            <h5><i class="fas fa-lightbulb"></i> Tips cepat</h5>
            <ul>${tipsHtml}</ul>
        </div>
        ${actionHtml}
    `;
    requestAnimationFrame(() => {
        slide.classList.add('animate');
    });

    prevBtn.disabled = tutorialStepIndex === 0;
    prevBtn.style.opacity = tutorialStepIndex === 0 ? '0.55' : '1';

    if (tutorialStepIndex === steps.length - 1) {
        nextBtn.innerHTML = '<i class="fas fa-check"></i> Selesai';
    } else {
        nextBtn.innerHTML = 'Lanjut <i class="fas fa-arrow-right"></i>';
    }
}

function openTutorialModal(stepIndex = 0) {
    const parsedIndex = Number(stepIndex);
    tutorialStepIndex = Number.isFinite(parsedIndex) ? parsedIndex : 0;
    openModal('tutorial-modal');
    renderTutorialStep();
}

function closeTutorialModal() {
    closeModal('tutorial-modal');
}

function nextTutorialStep() {
    const steps = getTutorialSteps();
    if (tutorialStepIndex >= steps.length - 1) {
        closeTutorialModal();
        showAlert('Tutorial selesai. Lanjutkan cek simulasi lalu publish.', 'success');
        return;
    }
    tutorialStepIndex += 1;
    renderTutorialStep();
}

function prevTutorialStep() {
    if (tutorialStepIndex <= 0) return;
    tutorialStepIndex -= 1;
    renderTutorialStep();
}

// Modal helpers
function openModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.style.display = ''; // FIX: Clear potential inline style from other scripts
        modal.classList.add('active');
        document.body.style.overflow = 'hidden';
    }
}

function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.remove('active');
        document.body.style.overflow = '';
    }
}

// Close modal on overlay click
document.addEventListener('click', (e) => {
    if (e.target.classList.contains('modal-overlay')) {
        // Don't close input/confirm modals on overlay click
        if (e.target.id === 'input-modal' || e.target.id === 'confirm-modal') {
            return;
        }
        e.target.classList.remove('active');
        document.body.style.overflow = '';
    }
});

// Close modal on Escape key
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        document.querySelectorAll('.modal-overlay.active').forEach(modal => {
            // Handle input/confirm modals specially
            if (modal.id === 'input-modal') {
                closeInputModal();
            } else if (modal.id === 'confirm-modal') {
                closeConfirmModal(false);
            } else {
                modal.classList.remove('active');
            }
        });
        document.body.style.overflow = '';
    }
});

document.addEventListener('keydown', (e) => {
    const tutorialModal = document.getElementById('tutorial-modal');
    if (!tutorialModal || !tutorialModal.classList.contains('active')) return;

    if (e.key === 'ArrowRight') {
        e.preventDefault();
        nextTutorialStep();
    } else if (e.key === 'ArrowLeft') {
        e.preventDefault();
        prevTutorialStep();
    }
});

// ============== AUDIO UPLOAD FUNCTIONS ==============

// Trigger audio upload
function triggerAudioUpload(questionIndex) {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'audio/mpeg,audio/wav,audio/ogg,audio/mp3,.mp3,.wav,.ogg';
    input.onchange = async (e) => {
        const file = e.target.files[0];
        if (!file) return;

        // Validate file type - support more audio formats
        const validTypes = ['audio/mpeg', 'audio/wav', 'audio/wave', 'audio/x-wav', 'audio/ogg', 'audio/mp3', 'audio/aac', 'audio/mp4', 'audio/x-m4a', 'audio/webm'];
        if (!validTypes.includes(file.type) && !file.name.match(/\.(mp3|wav|ogg|aac|m4a|webm)$/i)) {
            alert('Format audio tidak didukung. Gunakan MP3, WAV, OGG, AAC, M4A, atau WebM.');
            return;
        }

        // Validate file size (max 50MB for audio)
        if (file.size > 50 * 1024 * 1024) {
            alert('File terlalu besar. Maksimal 50MB.');
            return;
        }

        showLoader('Mengupload audio...');
        try {
            const formData = new FormData();
            formData.append('file', file);

            const response = await fetch('/api/upload/image', {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${localStorage.getItem('access_token')}`
                },
                body: formData
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Upload gagal');
            }

            const result = await response.json();
            examData.questions[questionIndex].audio_url = result.url;
            renderQuestions();
            triggerAutoSave();
            showSuccess('Audio berhasil diupload!');
        } catch (error) {
            showError('Gagal upload audio: ' + error.message);
        } finally {
            hideLoader();
        }
    };
    input.click();
}

// Remove audio from question
function removeAudio(questionIndex) {
    examData.questions[questionIndex].audio_url = null;
    renderQuestions();
    triggerAutoSave();
}

// ============== CUSTOM MODAL DIALOGS ==============

// Input Modal - Callback storage
let inputModalCallback = null;

function showInputModal(title, message, defaultValue = '', placeholder = '') {
    return new Promise((resolve) => {
        inputModalCallback = resolve;
        document.getElementById('input-modal-title').innerHTML = '<i class="fas fa-edit"></i> ' + title;
        document.getElementById('input-modal-message').textContent = message;
        const input = document.getElementById('input-modal-input');
        input.value = defaultValue;
        input.placeholder = placeholder;
        openModal('input-modal');
        setTimeout(() => input.focus(), 100);
    });
}

function closeInputModal() {
    closeModal('input-modal');
    if (inputModalCallback) {
        inputModalCallback(null);
        inputModalCallback = null;
    }
}

function submitInputModal() {
    const value = document.getElementById('input-modal-input').value;
    closeModal('input-modal');
    if (inputModalCallback) {
        inputModalCallback(value);
        inputModalCallback = null;
    }
}

// Enter key submits input modal
document.getElementById('input-modal-input')?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
        submitInputModal();
    }
});

// Confirm Modal - Callback storage
let confirmModalCallback = null;

function showConfirmModal(title, message, confirmText = 'Ya, Lanjutkan', confirmClass = 'btn-danger') {
    return new Promise((resolve) => {
        confirmModalCallback = resolve;
        document.getElementById('confirm-modal-title').innerHTML = '<i class="fas fa-question-circle"></i> ' + title;
        document.getElementById('confirm-modal-message').textContent = message;
        const btn = document.getElementById('confirm-modal-btn');
        btn.innerHTML = '<i class="fas fa-check"></i> ' + confirmText;
        btn.className = 'btn ' + confirmClass;
        openModal('confirm-modal');
    });
}

function closeConfirmModal(result) {
    closeModal('confirm-modal');
    if (confirmModalCallback) {
        confirmModalCallback(result);
        confirmModalCallback = null;
    }
}

// ============== SUBJECTS (BIDANG STUDI) ==============

async function loadSubjects() {
    const select = document.getElementById('exam-subject');

    try {
        console.log('📚 Loading subjects...');

        // Set loading state
        select.disabled = true;
        select.innerHTML = '<option value="">⏳ Memuat bidang studi...</option>';

        // Check if api.getSubjects exists
        if (typeof api.getSubjects !== 'function') {
            console.warn('⚠️ api.getSubjects not available');
            throw new Error('API method not available');
        }

        const subjects = await api.getSubjects();
        console.log('✅ Subjects loaded:', subjects);

        // Clear loading state and rebuild dropdown
        select.innerHTML = '<option value="">-- Pilih --</option>';

        if (Array.isArray(subjects) && subjects.length > 0) {
            subjects.forEach(subject => {
                const option = document.createElement('option');
                option.value = subject.name;
                option.textContent = subject.name;
                option.selected = examData.subject === subject.name;
                select.appendChild(option);
            });
            console.log(`✅ Added ${subjects.length} subjects to dropdown`);
        } else {
            // No subjects found - add default subjects as fallback
            console.warn('⚠️ No subjects found, using defaults');
            const defaultSubjects = [
                'Matematika', 'Bahasa Indonesia', 'Bahasa Inggris',
                'IPA', 'IPS', 'PKN', 'Agama', 'Seni Budaya',
                'Pendidikan Jasmani', 'TIK'
            ];
            defaultSubjects.forEach(name => {
                const option = document.createElement('option');
                option.value = name;
                option.textContent = name;
                option.selected = examData.subject === name;
                select.appendChild(option);
            });
        }

        // Re-enable dropdown
        select.disabled = false;

    } catch (error) {
        console.error('❌ Failed to load subjects:', error);

        // Show error state with fallback subjects
        select.innerHTML = '<option value="">-- Pilih --</option>';

        const fallbackSubjects = [
            'Matematika', 'Bahasa Indonesia', 'Bahasa Inggris',
            'IPA', 'IPS', 'PKN'
        ];
        fallbackSubjects.forEach(name => {
            const option = document.createElement('option');
            option.value = name;
            option.textContent = name;
            option.selected = examData.subject === name;
            select.appendChild(option);
        });

        // Re-enable dropdown even on error
        select.disabled = false;

        // Show non-intrusive warning (optional - commented out to avoid spam)
        // showAlert('Gagal memuat daftar bidang studi, menggunakan daftar default', 'warning');
    }
}

async function addNewSubject() {
    const name = await showInputModal(
        'Tambah Bidang Studi',
        'Masukkan nama bidang studi/mata pelajaran baru:',
        '',
        'Contoh: Matematika, Fisika, Sejarah'
    );

    if (!name || !name.trim()) return;

    try {
        await api.createSubject(name.trim());
        showAlert('Bidang studi berhasil ditambahkan', 'success');

        // Reload subjects and select the new one
        await loadSubjects();
        document.getElementById('exam-subject').value = name.trim();
        examData.subject = name.trim();
        triggerAutoSave();
    } catch (error) {
        if (error.message.includes('sudah ada')) {
            showAlert('Bidang studi dengan nama ini sudah ada', 'warning');
        } else {
            showAlert('Gagal menambahkan bidang studi', 'danger');
        }
    }
}

// ================= PUBLISH WIZARD LOGIC =================
let publishState = {
    currentStep: 1,
    selectedClasses: [],
    selectedStudents: [],
    studentData: {}, // Cache: class -> [students]
    allStudents: [] // Flattened list for confirming
};

function openPublishModal() {
    // Reset State
    publishState = {
        currentStep: 1,
        selectedClasses: [],
        selectedStudents: [],
        studentData: {},
        allStudents: []
    };

    // UI Reset
    document.getElementById('publish-exam-title').textContent = examData.title || 'Ujian Tanpa Judul';
    document.getElementById('publish-exam-info').textContent = `${examData.questions.length} Soal • ${examData.duration_minutes} Menit`;

    // Clear selections (ONLY within publish modal, not all page checkboxes!)
    const publishModal = document.getElementById('publish-modal');
    publishModal.querySelectorAll('.class-checkbox-item').forEach(el => el.classList.remove('selected'));
    publishModal.querySelectorAll('input[type="checkbox"]').forEach(el => el.checked = false);

    // Pre-select logic if re-publishing
    // Convert allowed_classes/students string to array if exists in examData
    if (examData.allowed_classes) {
        publishState.selectedClasses = examData.allowed_classes.split(',').map(c => c.trim());
    }
    // allowed_students handled when loading student list

    // Load available classes
    loadClassListForPublish();

    // Show step 1
    updatePublishSteps(1);
    openModal('publish-modal');
}

function closePublishModal() {
    closeModal('publish-modal');
}

async function loadClassListForPublish() {
    const container = document.getElementById('class-list-container');
    container.innerHTML = '<div class="loading"><div class="spinner"></div></div>';

    try {
        const classes = await api.getStudentClasses();

        container.innerHTML = classes.map(cls => {
            const isSelected = publishState.selectedClasses.includes(cls);
            return `
            <label class="class-checkbox-item ${isSelected ? 'selected' : ''}" onclick="toggleClassSelection(this, '${cls}')">
                <input type="checkbox" value="${cls}" ${isSelected ? 'checked' : ''} onchange="event.stopPropagation(); toggleClassSelection(this.parentElement, '${cls}')">
                <span style="font-weight: 500;">${cls}</span>
            </label>
            `;
        }).join('');
    } catch (error) {
        console.error(error);
        container.innerHTML = '<p class="error-text">Gagal memuat kelas</p>';
    }
}

function toggleClassSelection(element, className) {
    const checkbox = element.querySelector('input[type="checkbox"]');
    // Prevent double toggle if clicked directly on checkbox (handled by onchange)
    // But onclick is on label, so clicking label toggles checkbox natively?
    // If I click label, checkbox toggles. onclick fires.
    // If I click checkbox, onchange fires.

    // Simplified logic: Just check the checkbox state after the event
    // actually, let's rely on the visual class update matching the checkbox

    setTimeout(() => {
        if (checkbox.checked) {
            element.classList.add('selected');
            if (!publishState.selectedClasses.includes(className)) {
                publishState.selectedClasses.push(className);
            }
        } else {
            element.classList.remove('selected');
            publishState.selectedClasses = publishState.selectedClasses.filter(c => c !== className);
        }
    }, 0);
}

// Wizard Navigation
function updatePublishSteps(step) {
    publishState.currentStep = step;

    // Update Indicators
    document.querySelectorAll('.publish-step').forEach((el, index) => {
        el.classList.remove('active', 'completed');
        if (index + 1 < step) el.classList.add('completed');
        if (index + 1 === step) el.classList.add('active');
    });

    // Show Content
    document.querySelectorAll('.publish-step-content').forEach(el => el.style.display = 'none');
    document.getElementById(`publish-step-${step}`).style.display = 'block';

    // Buttons
    const backBtn = document.getElementById('publish-back-btn');
    const nextBtn = document.getElementById('publish-next-btn');
    const confirmBtn = document.getElementById('publish-confirm-btn');

    backBtn.style.display = step === 1 ? 'none' : 'block';

    if (step === 3) {
        nextBtn.style.display = 'none';
        confirmBtn.style.display = 'block';
        updateSummary();
    } else {
        nextBtn.style.display = 'block';
        confirmBtn.style.display = 'none';
        nextBtn.innerHTML = 'Lanjut <i class="fas fa-arrow-right"></i>';
    }
}

async function publishStepNext() {
    if (publishState.currentStep === 1) {
        // Validation
        if (publishState.selectedClasses.length === 0) {
            showAlert('Pilih minimal satu kelas', 'warning');
            return;
        }

        // Load students for Step 2
        await loadStudentListForPublish();
        updatePublishSteps(2);
    } else if (publishState.currentStep === 2) {
        // Validation
        if (publishState.selectedStudents.length === 0) {
            showAlert('Pilih minimal satu siswa', 'warning');
            return;
        }
        updatePublishSteps(3);
    }
}

function publishStepBack() {
    if (publishState.currentStep > 1) {
        updatePublishSteps(publishState.currentStep - 1);
    }
}

async function loadStudentListForPublish() {
    const listContainer = document.getElementById('student-list-container');
    listContainer.innerHTML = '<div class="loading"><div class="spinner"></div></div>';

    publishState.allStudents = []; // Reset flattened list

    // Fetch students for selected classes
    const promises = publishState.selectedClasses.map(async cls => {
        if (!publishState.studentData[cls]) {
            publishState.studentData[cls] = await api.getStudentsByClass(cls);
        }
        return publishState.studentData[cls];
    });

    try {
        const results = await Promise.all(promises);
        // Flatten results
        publishState.allStudents = results.flat();

        // Initial Selection Logic:
        // If NO students are currently selected (first time loading step 2), Select All by default.
        // OR if editing and we have persisted allowed_students/allowed_classes.
        // If allowed_classes contains the class -> Select all in that class.
        // If allowed_classes doesn't contain the class -> Select only those in allowed_students.

        // Parse current permissions from examData if not yet set in publishState
        let preSelectedIds = [];
        if (examData.allowed_students) {
            preSelectedIds = examData.allowed_students.split(',').map(id => parseInt(id.trim()));
        }
        // Also check classes
        let fullClassPermissions = [];
        if (examData.allowed_classes) {
            fullClassPermissions = examData.allowed_classes.split(',').map(c => c.trim());
        }

        // Logic to determine initial `selectedStudents` state if empty
        if (publishState.selectedStudents.length === 0) {
            publishState.allStudents.forEach(s => {
                // If the student's class is Fully Allowed OR the student ID is explicitly allowed
                if (fullClassPermissions.includes(s.student_class) || preSelectedIds.includes(s.id)) {
                    publishState.selectedStudents.push(s.id);
                } else if (publishState.selectedClasses.length > 0 && !examData.allowed_classes && !examData.allowed_students) {
                    // New publish attempt (no prior permissions) -> Default Select All
                    publishState.selectedStudents.push(s.id);
                }
            });

            // Fallback: If absolutely no selection logic found (e.g. brand new), select all
            if (!examData.allowed_classes && !examData.allowed_students && publishState.selectedStudents.length === 0) {
                publishState.selectedStudents = publishState.allStudents.map(s => s.id);
            }
        }

        renderStudentList();
    } catch (error) {
        console.error(error);
        listContainer.innerHTML = '<p class="error-text">Gagal memuat data siswa</p>';
    }
}

function renderStudentList() {
    const listContainer = document.getElementById('student-list-container');
    const searchTerm = document.getElementById('student-search').value.toLowerCase();

    // Group by class
    // But displaying flat list sorted by class + name usually better
    const filtered = publishState.allStudents.filter(s =>
        s.full_name.toLowerCase().includes(searchTerm) ||
        s.username.toLowerCase().includes(searchTerm)
    ).sort((a, b) => a.student_class.localeCompare(b.student_class) || a.full_name.localeCompare(b.full_name));

    if (filtered.length === 0) {
        listContainer.innerHTML = '<div style="padding:1rem; text-align:center; color:var(--text-secondary);">Tidak ada siswa ditemukan</div>';
        return;
    }

    listContainer.innerHTML = filtered.map(s => {
        const safeName = escapeHtml(s.full_name);
        const safeClass = escapeHtml(s.student_class);
        const safeUsername = escapeHtml(s.username);
        return `
            <div class="student-item">
                <input type="checkbox" id="student-${s.id}"
                       ${publishState.selectedStudents.includes(s.id) ? 'checked' : ''}
                       onchange="toggleStudentSelection(${s.id})">
                <div class="student-info">
                    <div class="student-name">${safeName}</div>
                    <div class="student-class"><i class="fas fa-users" style="font-size:0.7em;"></i> ${safeClass}</div>
                </div>
                <span class="badge badge-secondary" style="font-size:0.7em;">${safeUsername}</span>
            </div>
        `;
    }).join('');

    document.getElementById('selected-count').textContent = `${publishState.selectedStudents.length} siswa dipilih`;
}

function toggleStudentSelection(id) {
    if (publishState.selectedStudents.includes(id)) {
        publishState.selectedStudents = publishState.selectedStudents.filter(sid => sid !== id);
    } else {
        publishState.selectedStudents.push(id);
    }
    document.getElementById('selected-count').textContent = `${publishState.selectedStudents.length} siswa dipilih`;
}

function selectAllStudents() {
    const searchTerm = document.getElementById('student-search').value.toLowerCase();
    const visibleStudents = publishState.allStudents.filter(s =>
        s.full_name.toLowerCase().includes(searchTerm) ||
        s.username.toLowerCase().includes(searchTerm)
    );

    visibleStudents.forEach(s => {
        if (!publishState.selectedStudents.includes(s.id)) {
            publishState.selectedStudents.push(s.id);
        }
    });
    renderStudentList();
}

function deselectAllStudents() {
    // Only deselect visible if searching? Or all?
    // Usually "Deselect All" means all.
    const searchTerm = document.getElementById('student-search').value.toLowerCase();
    if (searchTerm) {
        const visibleIds = publishState.allStudents.filter(s =>
            s.full_name.toLowerCase().includes(searchTerm)
        ).map(s => s.id);

        publishState.selectedStudents = publishState.selectedStudents.filter(id => !visibleIds.includes(id));
    } else {
        publishState.selectedStudents = [];
    }
    renderStudentList();
}

function filterStudentList() {
    renderStudentList();
}

function updateSummary() {
    document.getElementById('confirm-exam-title').textContent = examData.title;
    document.getElementById('confirm-classes').textContent = publishState.selectedClasses.join(', ');
    document.getElementById('confirm-student-count').textContent = `${publishState.selectedStudents.length} Siswa`;
}

async function confirmPublish() {
    const btn = document.getElementById('publish-confirm-btn');
    const originalText = btn.innerHTML;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Publishing...';
    btn.disabled = true;

    try {
        // Hybrid permissions calculation
        const finalAllowedClasses = [];
        const finalAllowedStudents = [];

        for (const cls of publishState.selectedClasses) {
            const studentsInClass = publishState.allStudents.filter(s => s.student_class === cls);
            const totalInClass = studentsInClass.length;
            const selectedInClass = studentsInClass.filter(s => publishState.selectedStudents.includes(s.id));

            if (totalInClass > 0 && selectedInClass.length === totalInClass) {
                finalAllowedClasses.push(cls);
            } else {
                selectedInClass.forEach(s => finalAllowedStudents.push(s.id));
            }
        }

        // Save current changes first just in case
        await saveExam();

        // Prepare FULL update payload (PUT requires all fields)
        const payload = {
            title: examData.title || 'Ujian Tanpa Judul',
            description: '',
            duration_minutes: examData.duration_minutes || 60,
            passing_score: examData.passing_score || 70,
            shuffle_questions: examData.shuffle_questions || false,
            shuffle_options: examData.shuffle_options || false,
            show_results: examData.show_results === true,  // FIX: Include show_results!
            allow_review: examData.allow_review || false,
            max_attempts: examData.max_attempts || 1,
            start_time: examData.start_time,
            end_time: examData.end_time,
            subject: examData.subject || null,
            exam_type: examData.exam_type || null,
            academic_year: examData.academic_year || null,
            show_teacher_name: examData.show_teacher_name !== false,
            builder_settings: getBuilderSettings(),

            // Updated permissions
            allowed_classes: finalAllowedClasses.length > 0 ? finalAllowedClasses.join(',') : null,
            allowed_students: finalAllowedStudents.length > 0 ? finalAllowedStudents.join(',') : null,
            is_published: true
        };

        await api.updateExam(examId, payload);

        closePublishModal();
        showAlert('🎉 Ujian berhasil dipublish!', 'success');

        // Redirect after delay
        setTimeout(() => {
            window.location.href = '/admin/exams.html';
        }, 1500);

    } catch (error) {
        console.error(error);
        showAlert(error.message || 'Gagal publish ujian', 'danger');
    } finally {
        btn.innerHTML = originalText;
        btn.disabled = false;
    }
}

// ================= TIME MODAL FUNCTIONS =================

function openTimeModal() {
    const durationInput = document.getElementById('exam-duration');
    const durationDisplay = document.getElementById('duration-display');
    const startTimeInput = document.getElementById('start-time');
    const endTimeInput = document.getElementById('end-time');

    // Sync duration display
    if (durationDisplay) {
        durationDisplay.textContent = durationInput.value;
    }

    // Set current start/end times or defaults
    const now = new Date();
    let startTime, endTime;

    if (examData.start_time) {
        startTime = new Date(examData.start_time);
        endTime = new Date(examData.end_time);

        // Check if draft time is in the past - auto update to current time
        if (startTime < now) {
            console.log('[TIMEMODAL] Waktu ujian sudah lewat, auto-update ke waktu sekarang');
            startTime = now;
            const duration = parseInt(durationInput.value) || 60;
            endTime = new Date(now.getTime() + duration * 60 * 1000);

            // Update examData with new times
            examData.start_time = startTime.toISOString();
            examData.end_time = endTime.toISOString();

            showAlert('Waktu ujian telah diperbarui ke jadwal terkini', 'info');
        }

        startTimeInput.value = formatDateTimeLocal(startTime);
        endTimeInput.value = formatDateTimeLocal(endTime);
    } else {
        // Default to now
        startTimeInput.value = formatDateTimeLocal(now);
        autoUpdateEndTime();
    }

    openModal('time-modal');
}

function setDuration(minutes) {
    const durationInput = document.getElementById('exam-duration');
    const durationDisplay = document.getElementById('duration-display');

    durationInput.value = minutes;
    if (durationDisplay) {
        durationDisplay.textContent = minutes;
    }

    // Auto-update end time if start time is set
    autoUpdateEndTime();
}

function setTimeNow() {
    const now = new Date();
    const startTimeInput = document.getElementById('start-time');
    startTimeInput.value = formatDateTimeLocal(now);
    autoUpdateEndTime();
}

function setTimeTomorrow() {
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    tomorrow.setHours(8, 0, 0, 0); // 08:00

    const startTimeInput = document.getElementById('start-time');
    startTimeInput.value = formatDateTimeLocal(tomorrow);
    autoUpdateEndTime();
}

function autoUpdateEndTime() {
    const startTimeInput = document.getElementById('start-time');
    const endTimeInput = document.getElementById('end-time');
    const durationInput = document.getElementById('exam-duration');

    if (!startTimeInput.value) return;

    const duration = parseInt(durationInput.value) || 60;
    const startTime = new Date(startTimeInput.value);
    const endTime = new Date(startTime.getTime() + duration * 60 * 1000);

    endTimeInput.value = formatDateTimeLocal(endTime);
    checkDurationMismatch();
}

function checkDurationMismatch() {
    const startTimeInput = document.getElementById('start-time');
    const endTimeInput = document.getElementById('end-time');
    const durationInput = document.getElementById('exam-duration');
    const warning = document.getElementById('duration-warning');
    const calculatedDurationEl = document.getElementById('calculated-duration');

    if (!startTimeInput.value || !endTimeInput.value || !warning) return;

    const startTime = new Date(startTimeInput.value);
    const endTime = new Date(endTimeInput.value);
    const expectedDuration = parseInt(durationInput.value) || 60;

    const actualDuration = Math.floor((endTime - startTime) / (1000 * 60));

    if (calculatedDurationEl) {
        calculatedDurationEl.textContent = actualDuration;
    }

    // Show warning if mismatch > 5 minutes
    if (Math.abs(actualDuration - expectedDuration) > 5) {
        warning.style.display = 'block';
    } else {
        warning.style.display = 'none';
    }
}

function saveTimeSettings() {
    const startTimeInput = document.getElementById('start-time');
    const endTimeInput = document.getElementById('end-time');

    if (!startTimeInput.value || !endTimeInput.value) {
        alert('⚠️ Mohon atur waktu mulai dan selesai');
        return;
    }

    // Save to examData
    examData.start_time = new Date(startTimeInput.value).toISOString();
    examData.end_time = new Date(endTimeInput.value).toISOString();

    closeModal('time-modal');
    triggerAutoSave();
}

// ============== POINTS CONFIGURATION FUNCTIONS ==============

// Default points configuration
const defaultPointsConfig = {
    multiple_choice: 2,
    multiple_choice_complex: 3.2,
    true_false: 3,
    short_answer: 2.5,
    essay: 5
};

// Current points configuration (loaded from localStorage or defaults)
let pointsConfig = { ...defaultPointsConfig };

// Load points config from localStorage on init
function loadPointsConfig() {
    const saved = localStorage.getItem('examBuilder_pointsConfig');
    if (saved) {
        try {
            pointsConfig = JSON.parse(saved);
        } catch (e) {
            console.warn('Failed to load points config, using defaults');
            pointsConfig = { ...defaultPointsConfig };
        }
    }
}

// Save points config to localStorage
function savePointsConfig() {
    localStorage.setItem('examBuilder_pointsConfig', JSON.stringify(pointsConfig));
}

// Open points configuration modal
function openPointsConfigModal() {
    // Load current config into form
    document.getElementById('points-multiple_choice').value = pointsConfig.multiple_choice;
    document.getElementById('points-multiple_choice_complex').value = pointsConfig.multiple_choice_complex;
    document.getElementById('points-true_false').value = pointsConfig.true_false;
    document.getElementById('points-short_answer').value = pointsConfig.short_answer;
    document.getElementById('points-essay').value = pointsConfig.essay;

    // Update summary
    updatePointsSummary();

    // Add event listeners for real-time summary update
    ['multiple_choice', 'multiple_choice_complex', 'true_false', 'short_answer', 'essay'].forEach(type => {
        const input = document.getElementById(`points-${type}`);
        input.addEventListener('input', updatePointsSummary);
    });

    openModal('points-config-modal');
}

// Update points summary in modal
function updatePointsSummary() {
    const config = {
        multiple_choice: parseFloat(document.getElementById('points-multiple_choice').value) || 0,
        multiple_choice_complex: parseFloat(document.getElementById('points-multiple_choice_complex').value) || 0,
        true_false: parseFloat(document.getElementById('points-true_false').value) || 0,
        short_answer: parseFloat(document.getElementById('points-short_answer').value) || 0,
        essay: parseFloat(document.getElementById('points-essay').value) || 0
    };

    // Count questions by type
    const counts = {
        multiple_choice: 0,
        multiple_choice_complex: 0,
        true_false: 0,
        short_answer: 0,
        essay: 0
    };

    examData.questions.forEach(q => {
        if (counts.hasOwnProperty(q.type)) {
            counts[q.type]++;
        }
    });

    // Calculate totals
    let totalPoints = 0;
    let summaryHtml = '<div style="display: grid; grid-template-columns: 1fr auto auto; gap: 0.5rem; align-items: center;">';

    const typeLabels = {
        multiple_choice: 'Pilihan Ganda',
        multiple_choice_complex: 'PG Kompleks',
        true_false: 'Benar/Salah',
        short_answer: 'Isian Singkat',
        essay: 'Essay'
    };

    Object.keys(counts).forEach(type => {
        const count = counts[type];
        const points = config[type];
        const subtotal = count * points;
        totalPoints += subtotal;

        if (count > 0) {
            summaryHtml += `
                <span>${typeLabels[type]}</span>
                <span style="text-align: right;">${count} × ${points}</span>
                <span style="text-align: right; font-weight: 600;">= ${subtotal.toFixed(1)}</span>
            `;
        }
    });

    summaryHtml += '</div>';

    if (examData.questions.length > 0) {
        summaryHtml += `
            <div style="margin-top: 0.75rem; padding-top: 0.75rem; border-top: 1px solid rgba(34, 197, 94, 0.3); display: flex; justify-content: space-between; align-items: center;">
                <strong>Total Nilai Maksimal:</strong>
                <strong style="font-size: 1.25rem; color: #22c55e;">${totalPoints.toFixed(1)} poin</strong>
            </div>
            <small style="color: var(--text-secondary); margin-top: 0.5rem; display: block;">
                <i class="fas fa-info-circle"></i> ${examData.questions.length} soal akan diperbarui
            </small>
        `;
    } else {
        summaryHtml = `
            <div style="text-align: center; color: var(--text-secondary);">
                <i class="fas fa-info-circle"></i> Belum ada soal. Konfigurasi ini akan diterapkan ke soal baru yang ditambahkan.
            </div>
        `;
    }

    const summaryElement = document.getElementById('points-summary-content');
    if (summaryElement) {
        summaryElement.innerHTML = summaryHtml;
    }
}

// Reset points config to defaults
function resetPointsConfig() {
    document.getElementById('points-multiple_choice').value = defaultPointsConfig.multiple_choice;
    document.getElementById('points-multiple_choice_complex').value = defaultPointsConfig.multiple_choice_complex;
    document.getElementById('points-true_false').value = defaultPointsConfig.true_false;
    document.getElementById('points-short_answer').value = defaultPointsConfig.short_answer;
    document.getElementById('points-essay').value = defaultPointsConfig.essay;

    updatePointsSummary();
    showAlert('Konfigurasi direset ke nilai default', 'info');
}

// Apply points configuration to all questions
function applyPointsConfig() {
    // Get values from form
    pointsConfig = {
        multiple_choice: parseFloat(document.getElementById('points-multiple_choice').value) || defaultPointsConfig.multiple_choice,
        multiple_choice_complex: parseFloat(document.getElementById('points-multiple_choice_complex').value) || defaultPointsConfig.multiple_choice_complex,
        true_false: parseFloat(document.getElementById('points-true_false').value) || defaultPointsConfig.true_false,
        short_answer: parseFloat(document.getElementById('points-short_answer').value) || defaultPointsConfig.short_answer,
        essay: parseFloat(document.getElementById('points-essay').value) || defaultPointsConfig.essay
    };

    // Save to localStorage
    savePointsConfig();

    // Apply to all existing questions
    let updatedCount = 0;
    examData.questions.forEach(q => {
        if (pointsConfig.hasOwnProperty(q.type)) {
            q.points = pointsConfig[q.type];
            updatedCount++;
        }
    });

    // Re-render questions
    renderQuestions();
    triggerAutoSave();

    // Close modal
    closeModal('points-config-modal');

    // Show success message
    if (updatedCount > 0) {
        showAlert(`✅ Bobot nilai berhasil diterapkan ke ${updatedCount} soal`, 'success');
    } else {
        showAlert('✅ Konfigurasi bobot nilai tersimpan. Akan diterapkan ke soal baru.', 'success');
    }
}

// Get points for a question type (used when adding new questions)
function getPointsForType(type) {
    return pointsConfig[type] || 1;
}

// Save configuration only (without applying to existing questions)
function savePointsConfigOnly() {
    // Get values from form
    pointsConfig = {
        multiple_choice: parseFloat(document.getElementById('points-multiple_choice').value) || defaultPointsConfig.multiple_choice,
        multiple_choice_complex: parseFloat(document.getElementById('points-multiple_choice_complex').value) || defaultPointsConfig.multiple_choice_complex,
        true_false: parseFloat(document.getElementById('points-true_false').value) || defaultPointsConfig.true_false,
        short_answer: parseFloat(document.getElementById('points-short_answer').value) || defaultPointsConfig.short_answer,
        essay: parseFloat(document.getElementById('points-essay').value) || defaultPointsConfig.essay
    };

    // Save to localStorage
    savePointsConfig();

    // Show success message
    showAlert('✅ Konfigurasi bobot nilai berhasil disimpan. Pengaturan akan diterapkan ke soal baru.', 'success');
}

// Initialize points config on page load
loadPointsConfig();
