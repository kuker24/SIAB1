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
