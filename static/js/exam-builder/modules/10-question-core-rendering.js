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

    const forceDefault = options.forceDefault === true;
    const userSet = question.table_statement_shuffle_user_set === true;

    if (question.image_url) {
        question.allow_table_statement_shuffle = false;
        return;
    }

    if (forceDefault || !userSet) {
        question.allow_table_statement_shuffle = true;
        if (forceDefault) {
            question.table_statement_shuffle_user_set = false;
        }
        return;
    }

    if (typeof question.allow_table_statement_shuffle !== 'boolean') {
        question.allow_table_statement_shuffle = true;
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
                Jika "Acak Opsi" aktif, baris pernyataan diacak. Kunci Benar/Salah tetap menempel pada pernyataan.
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
                <span style="font-size:0.82rem; color: var(--text-secondary);">Mode cepat (opsional): pilih kunci saja tanpa isi teks opsi</span>
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
                                style="padding: 0.35rem 0.75rem; background: var(--dark-lighter); border: 1px solid var(--border-color); border-radius: 0.375rem; color: var(--text-primary); font-size: 0.85rem; cursor: pointer; min-width: 240px;">
                            <option value="checkbox" ${currentPgkType === 'checkbox' ? 'selected' : ''}>📋 Tipe A: Pilih beberapa opsi</option>
                            <option value="table_validation" ${currentPgkType === 'table_validation' ? 'selected' : ''}>✅ Tipe B: Tabel Benar/Salah</option>
                        </select>
                    </div>
                    <small style="color: var(--text-secondary); display: block;">
                        ${currentPgkType === 'checkbox'
                ? 'Tipe A: isi teks opsi A-E, lalu centang semua jawaban yang benar (min. 2). Ganti ke Tipe B untuk pernyataan Benar/Salah.'
                : 'Tipe B: isi setiap pernyataan, lalu pilih Benar atau Salah di kolom kanan.'}
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
                        <span style="font-size:0.82rem; color: var(--text-secondary);">Mode cepat (opsional): centang kunci saja tanpa isi teks opsi</span>
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
                            <i class="fas fa-table"></i> Tabel Pernyataan — pilih Benar atau Salah per baris
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
                    ${((Array.isArray(question.statements) && question.statements.length >= 2)
                ? question.statements
                : (question.statements = ['', '', '', ''], question.statement_answers = [true, false, true, false], question.statements)
            ).map((stmt, stmtIndex) => `
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
