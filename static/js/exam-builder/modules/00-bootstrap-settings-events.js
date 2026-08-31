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
    default_mc_key_only: false,
    default_pgk_key_only: false,
    default_image_layout_mode: 'model1',
    smart_auto_shuffle_options: false,
    smart_auto_shuffle_questions: false
});

function normalizeBuilderSettings(rawSettings = {}) {
    const raw = rawSettings && typeof rawSettings === 'object' ? rawSettings : {};
    return {
        default_mc_key_only: raw.default_mc_key_only === true,
        default_pgk_key_only: raw.default_pgk_key_only === true,
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
        if (question.image_url) {
            question.allow_table_statement_shuffle = false;
            question.table_statement_shuffle_user_set = false;
        } else if (question.table_statement_shuffle_user_set !== true) {
            question.allow_table_statement_shuffle = true;
        }
    }
    refreshTableStatementShuffleState(question);

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

            const inferredKeyOnlyMode = isKeyOnlyEligible
                ? (settings.use_key_only_mode === true)
                : false;
            const effectiveLayoutMode = 'model1';
            const effectiveModel2Slots = [];
            const inferredTableStatementShuffle = resolvedPgkType === 'table_validation'
                ? (
                    q.image_url
                        ? false
                        : (settings.allow_table_statement_shuffle !== false)
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
                if (!Array.isArray(pgkStatements) || pgkStatements.length < 2) {
                    pgkStatements = ['', '', '', ''];
                    pgkAnswers = [true, false, true, false];
                } else if (!Array.isArray(pgkAnswers) || pgkAnswers.length < pgkStatements.length) {
                    pgkAnswers = pgkStatements.map((_, idx) => pgkAnswers[idx] === true);
                }
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
                table_statement_shuffle_user_set: settings.table_statement_shuffle_user_set === true,
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
