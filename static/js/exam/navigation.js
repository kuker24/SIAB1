/* exam/navigation.js — soal, nav, submit */

    setupKeyboardNavigation() {
        document.addEventListener('keydown', (e) => {
            if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
                e.preventDefault();
                this.nextQuestion();
            } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
                e.preventDefault();
                this.prevQuestion();
            }

            if (['1', '2', '3', '4', '5'].includes(e.key)) {
                const options = document.querySelectorAll('.option-item');
                const index = parseInt(e.key) - 1;
                if (options[index]) {
                    options[index].click();
                }
            }
        });
    }

    setQuestions(questions) {
        this.questions = questions;
        // Ensure sync worker always has active session context.
        if (syncWorker && this.sessionId && syncWorker.sessionId !== this.sessionId) {
            syncWorker.start(this.sessionId);
        }
        if (journalWorker && this.sessionId && journalWorker.sessionId !== this.sessionId) {
            journalWorker.start(this.sessionId);
        }
        this.renderQuestion(0);
        this.updateNavigator();
    }

    // Fix 3: Load previous answers from database
    async loadPreviousAnswers() {
        try {
            const response = await api.request('GET', `/exams/session/${this.sessionId}/answers`);
            if (response.answers && Object.keys(response.answers).length > 0) {
                console.log('📥 Restoring', response.answered_count, 'previous answers');

                // Restore to local storage and UI
                for (const [questionId, answerData] of Object.entries(response.answers)) {
                    const qId = parseInt(questionId);
                    this.answers[qId] = answerData;

                    // Also save to IndexedDB for offline support
                    if (storageManager) {
                        await storageManager.saveAnswer(this.sessionId, qId, answerData);
                    }
                }

                showNotification(`Memulihkan ${response.answered_count} jawaban sebelumnya`, 'success');
            }
        } catch (error) {
            console.warn('⚠️ No previous answers to restore:', error.message);
        }
    }

    renderQuestion(index) {
        if (index < 0 || index >= this.questions.length) return;

        this.currentQuestionIndex = index;
        const question = this.questions[index];

        const container = document.getElementById('question-container');
        if (!container) return;

        let questionHtml = '';
        switch (question.question_type) {
            case 'multiple_choice':
            case 'true_false':
                questionHtml = this.renderMultipleChoice(question, index);
                break;
            case 'multiple_choice_complex':
                questionHtml = this.renderComplexChoice(question, index);
                break;
            case 'essay':
                questionHtml = this.renderEssay(question, index);
                break;
            case 'short_answer':
                questionHtml = this.renderShortAnswer(question, index);
                break;
            default:
                questionHtml = this.renderMultipleChoice(question, index);
        }

        container.innerHTML = questionHtml;
        this.updateNavigator();
        this.saveSessionToStorage();
        this.pushRuntimeStateToNative(false);
    }

    isManualGradingQuestion(question) {
        if (!question) return false;
        const settings = question.question_settings || {};
        if (question.question_type === 'essay') return true;
        if (question.question_type === 'short_answer') {
            return settings.require_manual_grading === true;
        }
        return false;
    }

    renderQuestionBehaviorHint(question) {
        return '';
    }

    isModel2Enabled(question, options = []) {
        return false;
    }

    getModel2Slots(question, options = []) {
        const settings = question.question_settings || {};
        const rawSlots = settings.model2_runtime_slots || settings.model2_slots || [];
        if (Array.isArray(rawSlots) && rawSlots.length >= 2) {
            return rawSlots.slice(0, options.length).map((slot, idx) => ({
                slot: idx,
                x: Number(slot?.x ?? 50),
                y: Number(slot?.y ?? 50)
            }));
        }

        // Fallback safe layout if slot data unavailable
        const count = Math.max(options.length, 4);
        if (count <= 4) {
            return [
                { slot: 0, x: 20, y: 20 },
                { slot: 1, x: 80, y: 20 },
                { slot: 2, x: 20, y: 78 },
                { slot: 3, x: 80, y: 78 }
            ].slice(0, options.length);
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
        const rows = Math.ceil(options.length / cols);
        for (let i = 0; i < options.length; i++) {
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

    renderModel2Layout(question, options, selectedValue, isMulti = false) {
        const letters = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H'];
        const slots = this.getModel2Slots(question, options);
        const selectedIds = isMulti
            ? (Array.isArray(selectedValue) ? selectedValue.map(v => String(v)) : [])
            : [String(selectedValue ?? '')];
        const safeImageMarkup = renderQuestionImage(
            question.image_url,
            'Question image',
            ' style="display:block; max-width:100%; border-radius:0.5rem;"'
        );

        const hotspotsHtml = options.map((opt, idx) => {
            const slot = slots[idx] || { x: 50, y: 50 };
            const optionId = String(opt.id);
            const isSelected = selectedIds.includes(optionId);
            const rawLabel = (opt.option_text || '').trim();
            const fallbackLabel = letters[idx] || `${idx + 1}`;
            const displayLabel = rawLabel ? rawLabel : fallbackLabel;
            const safeLabel = escapeHtml(displayLabel);
            const clickHandler = isMulti
                ? `window.examSystem.toggleComplexOption(${question.id}, '${optionId}', ${!isSelected})`
                : `window.examSystem.selectOption(${question.id}, '${optionId}')`;

            return `
                <button type="button"
                        class="model2-hotspot ${isSelected ? 'selected' : ''} ${isMulti ? 'multi' : 'single'}"
                        data-option-id="${escapeAttribute(optionId)}"
                        data-label="${escapeAttribute(displayLabel)}"
                        onclick="event.stopPropagation(); ${clickHandler}"
                        style="position:absolute; left:${slot.x}%; top:${slot.y}%; transform:translate(-50%, -50%); width:44px; height:44px; border-radius:999px; border:2px solid ${isSelected ? '#22c55e' : 'rgba(148,163,184,0.75)'}; background:${isSelected ? 'linear-gradient(135deg,#22c55e,#16a34a)' : 'rgba(15,23,42,0.8)'}; color:white; font-weight:700; display:flex; align-items:center; justify-content:center; cursor:pointer; box-shadow:0 8px 20px rgba(0,0,0,0.35); z-index:3;">
                    <span class="model2-hotspot-badge">${isSelected ? '✓' : safeLabel}</span>
                </button>
            `;
        }).join('');

        const legendHtml = options.map((opt, idx) => {
            const rawLabel = (opt.option_text || '').trim();
            const fallbackLabel = letters[idx] || `${idx + 1}`;
            const displayLabel = rawLabel ? rawLabel : fallbackLabel;
            return `<span style="padding:0.2rem 0.45rem; border:1px solid rgba(148,163,184,0.35); border-radius:0.35rem; background:rgba(15,23,42,0.45); color:#cbd5e1; font-size:0.74rem;">${escapeHtml(displayLabel)}</span>`;
        }).join('');

        return `
            <div style="margin-bottom:0.65rem; padding:0.5rem 0.6rem; border:1px solid rgba(59,130,246,0.3); border-radius:0.45rem; background:rgba(59,130,246,0.1); color:#bfdbfe; font-size:0.8rem;">
                <i class="fas fa-image"></i> Soal bergambar ditampilkan dalam mode normal.
            </div>
            <div style="position:relative; display:inline-block; max-width:100%;">
                ${safeImageMarkup}
                ${hotspotsHtml}
            </div>
            <div style="display:flex; gap:0.35rem; flex-wrap:wrap; margin-top:0.55rem;">${legendHtml}</div>
        `;
    }

    renderMultipleChoice(question, index) {
        const savedAnswer = this.answers[question.id];
        let optionsHtml = '';
        const letters = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H'];

        // Null safety for options
        const options = question.options || [];
        const model2Enabled = this.isModel2Enabled(question, options);

        if (model2Enabled) {
            optionsHtml = this.renderModel2Layout(question, options, savedAnswer, false);
        } else {
            options.forEach((opt, i) => {
                const isSelected = savedAnswer == opt.id;
                const letter = letters[i] || (i + 1);
                optionsHtml += `
                    <div class="option-item ${isSelected ? 'selected' : ''}"
                         data-option-id="${opt.id}"
                         onclick="window.examSystem.selectOption(${question.id}, '${opt.id}')">
                        <div class="option-letter">${isSelected ? '✓' : letter}</div>
                        <span class="option-text">${escapeHtml(opt.option_text)}</span>
                    </div>
                `;
            });
        }

        // Render video if present
        const videoHtml = renderQuestionVideo(question.video_url);

        // Render audio if present
        const audioHtml = renderQuestionAudio(question.audio_url);

        // Determine Badge Label and Color based on type
        const isTrueFalse = question.question_type === 'true_false';
        const typeLabel = isTrueFalse ? 'Benar / Salah' : 'Pilihan Ganda';
        // Blue (#3b82f6) for Multiple Choice, Orange (#f59e0b) for True/False to distinguish
        const badgeColor = isTrueFalse ? '#f59e0b' : '#3b82f6';

        return `
            <div class="question-card fade-in">
                <div class="question-header">
                    <span class="question-number">Soal ${index + 1} dari ${this.questions.length}</span>
                    <span class="question-badge" style="background: ${badgeColor}; padding: 0.25rem 0.5rem; border-radius: 0.25rem; font-size: 0.75rem; color: white;">${typeLabel}</span>
                </div>
                <div class="question-text">${renderExamRichText(question.question_text)}</div>
                ${this.renderQuestionBehaviorHint(question)}
                ${question.image_url && !model2Enabled ? renderQuestionImage(question.image_url) : ''}
                ${videoHtml}
                ${audioHtml}
                <div class="options-list">${optionsHtml}</div>
            </div>
            ${this.renderNavigationButtons(index)}
        `;
    }

    renderComplexChoice(question, index) {
        const savedAnswers = this.answers[question.id] || [];
        const settings = question.question_settings || {};
        const minCorrect = settings.min_correct || 1;
        const letters = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H'];

        // Null safety for options
        const options = question.options || [];
        const maxCorrect = settings.max_correct || options.length;

        // Render stimulus if available (AKM-style)
        let stimulusHtml = '';
        if (question.stimulus && question.stimulus.trim()) {
            stimulusHtml = `
                <div class="stimulus-card">
                    <div class="stimulus-label">
                        <i class="fas fa-book-open"></i>
                        <span>Stimulus / Konteks</span>
                    </div>
                    <div class="stimulus-text">${renderExamRichText(question.stimulus)}</div>
                </div>
            `;
        }

        // Get pgk_type from question settings or direct field
        const pgkType = question.pgk_type || settings.pgk_type || 'checkbox';
        const model2Enabled = pgkType !== 'table_validation' && this.isModel2Enabled(question, options);

        let contentHtml = '';

        if (pgkType === 'table_validation') {
            // TYPE B: Table Validation (Benar/Salah statements)
            const statements = settings.statements || question.statements || [];
            const savedStatementAnswers = typeof savedAnswers === 'object' && !Array.isArray(savedAnswers)
                ? savedAnswers : {};

            let tableRowsHtml = '';
            statements.forEach((stmt, displayIndex) => {
                // Handle shuffled statements (objects) or legacy/unshuffled (strings)
                const isObject = typeof stmt === 'object' && stmt !== null;
                const text = isObject ? stmt.text : stmt;
                const logicIndex = isObject ? stmt.original_index : displayIndex;

                // Use logicIndex (original DB index) for retrieving saved answer
                const savedValue = savedStatementAnswers[logicIndex];
                const isBenarSelected = savedValue === true;
                const isSalahSelected = savedValue === false;

                tableRowsHtml += `
                    <div class="statement-row" data-statement-index="${logicIndex}">
                        <div class="statement-num">${displayIndex + 1}</div>
                        <div class="statement-text">${renderExamRichText(text)}</div>
                        <div>
                            <label class="radio-btn benar ${isBenarSelected ? 'selected' : ''}">
                                <input type="radio" name="stmt_${question.id}_${logicIndex}" value="true"
                                       ${isBenarSelected ? 'checked' : ''}
                                       onchange="window.examSystem.setStatementAnswer(${question.id}, ${logicIndex}, true)"
                                       style="display: none;">
                                <span>Benar</span>
                            </label>
                        </div>
                        <div>
                            <label class="radio-btn salah ${isSalahSelected ? 'selected' : ''}">
                                <input type="radio" name="stmt_${question.id}_${logicIndex}" value="false"
                                       ${isSalahSelected ? 'checked' : ''}
                                       onchange="window.examSystem.setStatementAnswer(${question.id}, ${logicIndex}, false)"
                                       style="display: none;">
                                <span>Salah</span>
                            </label>
                        </div>
                    </div>
                `;
            });

	            contentHtml = `
	                <div class="table-hint">
	                    <i class="fas fa-table"></i>
	                    <span>Tentukan setiap pernyataan Benar atau Salah</span>
	                </div>
	                <div class="table-validation">
	                    <div class="table-header">
                        <div>No</div>
                        <div>Pernyataan</div>
                        <div>Benar</div>
                        <div>Salah</div>
                    </div>
                    ${tableRowsHtml}
                </div>
            `;
        } else {
            // TYPE A: Multiple Response (Checkbox)
            if (model2Enabled) {
                contentHtml = this.renderModel2Layout(question, options, savedAnswers, true);
            } else {
                let optionsHtml = '';
                options.forEach((opt, i) => {
                    const isSelected = Array.isArray(savedAnswers) && savedAnswers.some(id => id == opt.id);
                    const letter = letters[i] || (i + 1);
                    optionsHtml += `
                        <div class="option-item checkbox-option ${isSelected ? 'selected' : ''}"
                             data-option-id="${opt.id}"
                             onclick="document.getElementById('opt_${opt.id}').click()">
                            <div class="option-letter">${isSelected ? '✓' : letter}</div>
                            <input type="checkbox"
                                   id="opt_${opt.id}"
                                   value="${opt.id}"
                                   ${isSelected ? 'checked' : ''}
                                   onchange="event.stopPropagation(); window.examSystem.toggleComplexOption(${question.id}, '${opt.id}', this.checked)"
                                   style="display: none;">
                            <span class="option-text">${escapeHtml(opt.option_text)}</span>
                        </div>
                    `;
                });

                contentHtml = `
                    <div class="table-hint">
                        <i class="fas fa-info-circle"></i>
                        <span>Pilih semua jawaban yang benar</span>
                    </div>
                    <div class="options-list">${optionsHtml}</div>
                `;
            }
        }

        // Render video if present
        const videoHtml = renderQuestionVideo(question.video_url);

        // Render audio if present
        const audioHtml = renderQuestionAudio(question.audio_url);

        return `
            <div class="question-card fade-in">
                <div class="question-header">
                    <span class="question-number">Soal ${index + 1} dari ${this.questions.length}</span>
                    <span class="question-badge">HOTS - ${pgkType === 'table_validation' ? 'Tabel' : 'PGK'}</span>
                </div>
                ${stimulusHtml}
                <div class="question-text">${renderExamRichText(question.question_text)}</div>
                ${this.renderQuestionBehaviorHint(question)}
                ${question.image_url && !model2Enabled ? renderQuestionImage(question.image_url) : ''}
                ${videoHtml}
                ${audioHtml}
                ${contentHtml}
            </div>
            ${this.renderNavigationButtons(index)}
        `;
    }


    renderEssay(question, index) {
        const savedAnswer = this.answers[question.id] || '';
        const settings = question.question_settings || {};
        const minWords = settings.min_words || 0;

        // Render video if present
        const videoHtml = renderQuestionVideo(question.video_url);

        // Render audio if present
        const audioHtml = renderQuestionAudio(
            question.audio_url,
            'margin: 1.5rem 0;',
            'width: 100%; max-width: 600px; border-radius: 0.5rem; box-shadow: 0 4px 12px rgba(0,0,0,0.3);'
        );

        return `
            <div class="question-card fade-in essay">
                <div class="question-header">
                    <span class="question-number">Soal ${index + 1} dari ${this.questions.length}</span>
                    <span class="question-badge" style="background: #6366f1; padding: 0.25rem 0.5rem; border-radius: 0.25rem; font-size: 0.75rem; color: white;">Essay</span>
                </div>
                <div class="question-text">${renderExamRichText(question.question_text)}</div>
                ${this.renderQuestionBehaviorHint(question)}
                ${question.image_url ? renderQuestionImage(question.image_url) : ''}
                ${videoHtml}
                ${audioHtml}
                <div class="answer-input-wrapper" style="margin-top: 1rem;">
                    <textarea
                        class="essay-input form-control"
                        style="min-height: 200px; width: 100%; resize: vertical;"
                        placeholder="Ketik jawaban Anda di sini..."
                        oninput="window.examSystem.updateTextAnswer(${question.id}, this.value)">${escapeHtml(savedAnswer)}</textarea>
                    ${minWords > 0 ? `<small style="color: #888;">Minimal ${minWords} kata</small>` : ''}
                </div>
            </div>
            ${this.renderNavigationButtons(index)}
        `;
    }

    renderShortAnswer(question, index) {
        const savedAnswer = this.answers[question.id] || '';

        // Render video if present
        const videoHtml = renderQuestionVideo(question.video_url);

        // Render audio if present
        const audioHtml = renderQuestionAudio(
            question.audio_url,
            'margin: 1.5rem 0;',
            'width: 100%; max-width: 600px; border-radius: 0.5rem; box-shadow: 0 4px 12px rgba(0,0,0,0.3);'
        );

        return `
            <div class="question-card fade-in short-answer">
                <div class="question-header">
                    <span class="question-number">Soal ${index + 1} dari ${this.questions.length}</span>
                    <span class="question-badge" style="background: #10b981; padding: 0.25rem 0.5rem; border-radius: 0.25rem; font-size: 0.75rem; color: white;">Isian Singkat</span>
                </div>
                <div class="question-text">${renderExamRichText(question.question_text)}</div>
                ${this.renderQuestionBehaviorHint(question)}
                ${question.image_url ? renderQuestionImage(question.image_url) : ''}
                ${videoHtml}
                ${audioHtml}
                <div class="answer-input-wrapper" style="margin-top: 1rem;">
                    <input type="text"
                           class="short-answer-input form-control"
                           style="padding: 0.75rem; width: 100%;"
                           placeholder="Ketik jawaban Anda di sini..."
                           value="${escapeAttribute(savedAnswer)}"
                           oninput="window.examSystem.updateTextAnswer(${question.id}, this.value)">
                </div>
            </div>
            ${this.renderNavigationButtons(index)}
        `;
    }

    renderNavigationButtons(index) {
        // Navigation is now handled by fixed footer, return empty string
        // Update flag button state in footer
        const questionId = this.questions[index]?.id;
        const isFlagged = this.flagged.has(questionId);
        const flagBtn = document.getElementById('flag-btn');
        if (flagBtn) {
            flagBtn.classList.toggle('flagged', isFlagged);
            const icon = flagBtn.querySelector('i');
            if (icon) {
                icon.className = isFlagged ? 'fas fa-flag' : 'far fa-flag';
            }
        }
        return '';
    }

    async selectOption(questionId, optionId) {
        const finalId = /^\d+$/.test(optionId) ? parseInt(optionId) : optionId;
        this.answers[questionId] = finalId;

        // UI Update (Faster feedback)
        const container = document.getElementById('question-container');
        if (container) {
            container.querySelectorAll('.option-item').forEach(item => {
                const isSelected = item.dataset.optionId == String(optionId);
                item.classList.toggle('selected', isSelected);
                const radio = item.querySelector('.option-radio');
                if (radio) radio.textContent = isSelected ? '✓' : radio.textContent.replace('✓', '').trim() || '-';
            });
            container.querySelectorAll('.model2-hotspot').forEach((item) => {
                const isSelected = item.dataset.optionId == String(optionId);
                item.classList.toggle('selected', isSelected);
                item.style.border = isSelected ? '2px solid #22c55e' : '2px solid rgba(148,163,184,0.75)';
                item.style.background = isSelected
                    ? 'linear-gradient(135deg,#22c55e,#16a34a)'
                    : 'rgba(15,23,42,0.8)';
                const badge = item.querySelector('.model2-hotspot-badge');
                if (badge) badge.textContent = isSelected ? '✓' : (item.dataset.label || '?');
            });
        }

        try {
            await this.submitAnswer(questionId, { selected_option_id: finalId });
        } catch (error) { console.error(error); }
        this.updateNavigator();
    }

    async toggleComplexOption(questionId, optionId, isChecked) {
        if (!this.answers[questionId]) this.answers[questionId] = [];
        const finalId = /^\d+$/.test(optionId) ? parseInt(optionId) : optionId;

        if (isChecked) {
            if (!this.answers[questionId].some(id => String(id) === String(finalId))) {
                this.answers[questionId].push(finalId);
            }
        } else {
            this.answers[questionId] = this.answers[questionId].filter(id => String(id) !== String(finalId));
        }

        // UI Update - Instant visual feedback (same pattern as selectOption)
        const container = document.getElementById('question-container');
        if (container) {
            container.querySelectorAll('.option-item.checkbox-option').forEach(item => {
                const itemOptionId = item.dataset.optionId;
                const isThisSelected = this.answers[questionId].some(id => String(id) === String(itemOptionId));

                // Update selected class
                item.classList.toggle('selected', isThisSelected);

                // Update visual styling directly
                item.style.background = isThisSelected
                    ? 'linear-gradient(135deg, rgba(34, 197, 94, 0.15), rgba(34, 197, 94, 0.05))'
                    : 'rgba(30, 41, 59, 0.6)';
                item.style.border = isThisSelected
                    ? '2px solid #22c55e'
                    : '2px solid rgba(99, 102, 241, 0.3)';

                // Update letter/checkmark indicator
                const letterDiv = item.querySelector('div[style*="width: 44px"]');
                if (letterDiv) {
                    const letters = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H'];
                    const itemIndex = Array.from(container.querySelectorAll('.option-item.checkbox-option')).indexOf(item);
                    letterDiv.textContent = isThisSelected ? '✓' : (letters[itemIndex] || (itemIndex + 1));
                    letterDiv.style.background = isThisSelected
                        ? 'linear-gradient(135deg, #22c55e, #16a34a)'
                        : 'rgba(99, 102, 241, 0.2)';
                    letterDiv.style.color = isThisSelected ? 'white' : '#a5b4fc';
                }

                // Update hidden checkbox state
                const checkbox = item.querySelector('input[type="checkbox"]');
                if (checkbox) {
                    checkbox.checked = isThisSelected;
                }
            });

            container.querySelectorAll('.model2-hotspot.multi').forEach((item) => {
                const itemOptionId = item.dataset.optionId;
                const isThisSelected = this.answers[questionId].some(id => String(id) === String(itemOptionId));
                item.classList.toggle('selected', isThisSelected);
                item.style.border = isThisSelected ? '2px solid #22c55e' : '2px solid rgba(148,163,184,0.75)';
                item.style.background = isThisSelected
                    ? 'linear-gradient(135deg,#22c55e,#16a34a)'
                    : 'rgba(15,23,42,0.8)';
                const badge = item.querySelector('.model2-hotspot-badge');
                if (badge) badge.textContent = isThisSelected ? '✓' : (item.dataset.label || '?');
            });
        }

        // Defensive: Pastikan array jawaban tidak kosong sebelum submit
        const currentAnswers = this.answers[questionId] || [];
        if (currentAnswers.length > 0) {
            try {
                await this.submitAnswer(questionId, { selected_option_ids: currentAnswers });
            } catch (error) { console.error(error); }
        } else {
            console.warn('⚠️ toggleComplexOption: Tidak ada jawaban untuk Q', questionId);
        }

        this.updateNavigator();
    }

    // Type B: Table Validation - Set statement answer (Benar/Salah)
    async setStatementAnswer(questionId, statementIndex, isBenar) {
        // Initialize as object if not exists or if wrong type
        if (!this.answers[questionId] || typeof this.answers[questionId] !== 'object' || Array.isArray(this.answers[questionId])) {
            this.answers[questionId] = {};
        }

        // Set the boolean value for this statement
        this.answers[questionId][statementIndex] = isBenar;

        // UI Update - Instant visual feedback using CSS classes
        const container = document.getElementById('question-container');
        if (container) {
            const statementRow = container.querySelector(`.statement-row[data-statement-index="${statementIndex}"]`);
            if (statementRow) {
                // Get benar and salah labels using their specific classes
                const benarLabel = statementRow.querySelector('label.radio-btn.benar');
                const salahLabel = statementRow.querySelector('label.radio-btn.salah');

                // Toggle selected class based on answer
                if (benarLabel) {
                    benarLabel.classList.toggle('selected', isBenar === true);
                }
                if (salahLabel) {
                    salahLabel.classList.toggle('selected', isBenar === false);
                }
            }
        }

        // Defensive: Pastikan object jawaban tidak kosong sebelum submit
        const currentStatementAnswers = this.answers[questionId] || {};
        const hasAnswers = Object.keys(currentStatementAnswers).length > 0;

        // Submit to server - use statement_answers format
        if (hasAnswers) {
            try {
                await this.submitAnswer(questionId, { statement_answers: currentStatementAnswers });
            } catch (error) { console.error(error); }
        } else {
            console.warn('⚠️ setStatementAnswer: Tidak ada jawaban untuk Q', questionId);
        }

        this.updateNavigator();
    }

    async updateTextAnswer(questionId, text) {
        this.answers[questionId] = text;
        if (this.textAnswerTimeout) clearTimeout(this.textAnswerTimeout);

        this.textAnswerTimeout = setTimeout(async () => {
            // Defensive: Pastikan text tidak kosong sebelum submit
            if (!text || text.trim() === '') {
                console.warn('⚠️ updateTextAnswer: Text kosong, skip submit untuk Q', questionId);
                return;
            }
            const textToSubmit = String(text).trim();
            console.log('📝 updateTextAnswer: Submitting text untuk Q', questionId, ':', textToSubmit.substring(0, 50) + '...');
            try {
                await this.submitAnswer(questionId, { answer_text: textToSubmit });
            } catch (error) { console.error(error); }
        }, 2000);
        this.updateNavigator();
    }

    async updateMatchingPair(pairId, rightOptionId, questionId) {
        if (!this.answers[questionId]) this.answers[questionId] = {};

        // Smart Cast Value
        let finalValue = rightOptionId;
        if (typeof rightOptionId === 'string' && /^\d+$/.test(rightOptionId)) {
            finalValue = parseInt(rightOptionId);
        }

        if (rightOptionId && rightOptionId !== "") {
            this.answers[questionId][pairId] = finalValue;
        } else {
            delete this.answers[questionId][pairId];
        }

        try {
            await this.submitAnswer(questionId, { matching_pairs: this.answers[questionId] });
        } catch (error) { console.error(error); }
        this.updateNavigator();
    }

    async submitAnswer(questionId, answerData) {
        // DEBUG: Log data yang akan dikirim
        console.log('🔍 DEBUG submitAnswer:', {
            questionId,
            answerData,
            currentAnswers: this.answers[questionId],
            sessionId: this.sessionId
        });

        // Defensive check: Pastikan data tidak kosong
        if (!answerData || Object.keys(answerData).length === 0) {
            console.warn('⚠️ submitAnswer: answerData kosong, skip submit');
            return;
        }

        // Defensive check: Pastikan tidak ada nilai undefined/null yang tidak perlu
        const cleanedAnswerData = {};
        for (const [key, value] of Object.entries(answerData)) {
            if (value !== undefined && value !== null) {
                cleanedAnswerData[key] = value;
            }
        }

        // Jika setelah cleaning data kosong, skip submit
        if (Object.keys(cleanedAnswerData).length === 0) {
            console.warn('⚠️ submitAnswer: cleanedAnswerData kosong, skip submit');
            return;
        }

        if (!this.answerRevisions[questionId]) {
            this.answerRevisions[questionId] = 0;
        }
        this.answerRevisions[questionId] += 1;

        const metadata = (typeof cleanedAnswerData.answer_metadata === 'object' && cleanedAnswerData.answer_metadata !== null)
            ? { ...cleanedAnswerData.answer_metadata }
            : {};
        metadata.client_revision = this.answerRevisions[questionId];
        metadata.client_answer_ts = Date.now();
        cleanedAnswerData.answer_metadata = metadata;

        const journalPayload = {
            session_id: this.sessionId,
            exam_id: this.examId,
            question_id: parseInt(questionId) || 0,
            ...cleanedAnswerData
        };
        notifyNativeAnswerJournal(journalPayload);
        if (journalWorker) {
            journalWorker.enqueue(journalPayload);
        }
        this.pushRuntimeStateToNative(false);

        // Legacy matching payloads still use the old direct endpoint.
        if (cleanedAnswerData.matching_pairs !== undefined) {
            try {
                await api.submitAnswer(this.sessionId, questionId, cleanedAnswerData);
                if (storageManager) {
                    await storageManager.saveAnswer(this.sessionId, questionId, cleanedAnswerData);
                }
                console.log('✅ submitAnswer berhasil untuk Q', questionId);
            } catch (error) {
                console.error('❌ submitAnswer error:', error);
                throw error;
            }
            return;
        }

        if (storageManager) {
            await storageManager.saveAnswerLocal(this.sessionId, questionId, cleanedAnswerData);
        }

        this.scheduleAnswerSync();
    }

    scheduleAnswerSync() {
        if (this.pendingSyncTimeout) {
            clearTimeout(this.pendingSyncTimeout);
        }

        this.pendingSyncTimeout = setTimeout(async () => {
            this.pendingSyncTimeout = null;
            if (!navigator.onLine || !syncWorker) return;

            try {
                await syncWorker.syncNow();
            } catch (error) {
                console.warn('⚠️ Debounced sync failed:', error?.message || error);
            }
        }, this.runtimePolicy.answer_sync_debounce_ms || 5000);
    }

    async autoSave() {
        try {
            if (syncWorker) {
                if (!syncWorker.sessionId && this.sessionId) {
                    syncWorker.start(this.sessionId);
                }
                await syncWorker.syncNow();
                if (storageManager && this.sessionId) {
                    const pendingAnswers = await storageManager.getUnsyncedAnswers(this.sessionId);
                    if (pendingAnswers.length > 0) {
                        await this.flushPendingAnswersForForceSubmit();
                    }
                }
            } else {
                await this.flushPendingAnswersForForceSubmit();
            }
            if (journalWorker) {
                if (!journalWorker.sessionId && this.sessionId) {
                    journalWorker.start(this.sessionId);
                }
                await journalWorker.flushNow();
            }
        } catch (error) { console.error('Auto-save failed:', error); }
    }

    /**
     * Notify Flutter that exam is submitted
     * This disables the kiosk mode and security features
     */
    notifyFlutterExamSubmitted() {
        try {
            if (window.flutter_inappwebview && window.flutter_inappwebview.callHandler) {
                console.log('Notifying Flutter: exam submitted');
                window.flutter_inappwebview.callHandler('examSubmitted');
            }
        } catch (e) { console.log('Flutter handler not available'); }
    }

    /**
     * Record violation from Flutter/Native
     * Called by injected JS from Flutter
     */
    recordViolation(type, count) {
        const label = this.getViolationLabel(type);
        console.warn(`Violation recorded: ${type} (${count})`);
        showNotification(`PERINGATAN: ${label} terdeteksi! (${count})`, count >= 3 ? 'error' : 'warning');
    }

    /**
     * Force submit triggered by Flutter (e.g. enhanced security violation)
     * Called by injected JS from Flutter
     */
    async forceSubmitDueToViolations() {
        console.error('FORCE SUBMIT triggered due to violations');
        showNotification('Ujian dihentikan paksa karena pelanggaran keamanan!', 'error');

        // Wait a small moment to ensure user sees the notification
        await new Promise(r => setTimeout(r, 1500));

        await this.flushPendingAnswersForForceSubmit();
        await this.submitExam(false); // Submit without confirmation
    }

    buildBatchAnswersPayload() {
        const items = [];

        for (const [questionIdRaw, value] of Object.entries(this.answers || {})) {
            const questionId = parseInt(questionIdRaw, 10);
            if (!questionId || Number.isNaN(questionId)) continue;

            let answerObj = null;
            if (Array.isArray(value)) {
                answerObj = { selected_option_ids: value };
            } else if (typeof value === 'number') {
                answerObj = { selected_option_id: value };
            } else if (typeof value === 'string') {
                const trimmed = value.trim();
                if (!trimmed) continue;
                answerObj = { answer_text: trimmed };
            } else if (value && typeof value === 'object') {
                // True/False table answers (all boolean-like values)
                const entries = Object.entries(value);
                const isStatementAnswers = entries.length > 0 && entries.every(([_, v]) =>
                    typeof v === 'boolean' || typeof v === 'number' || typeof v === 'string'
                );
                answerObj = isStatementAnswers
                    ? { statement_answers: value }
                    : value;
            } else {
                continue;
            }

            const normalized = api.normalizeAnswerPayload(answerObj || {});
            if (!normalized || Object.keys(normalized).length === 0) continue;

            items.push({
                question_id: questionId,
                ...normalized
            });
        }

        return items;
    }

    async flushPendingAnswersForForceSubmit() {
        try {
            if (this.pendingSyncTimeout) {
                clearTimeout(this.pendingSyncTimeout);
                this.pendingSyncTimeout = null;
            }
            if (this.textAnswerTimeout) {
                clearTimeout(this.textAnswerTimeout);
                this.textAnswerTimeout = null;
            }

            const answers = this.buildBatchAnswersPayload();
            if (!answers.length) return;

            await api.request('POST', '/exams/auto-save-batch', {
                session_id: parseInt(this.sessionId) || 0,
                answers
            });
            console.log(`💾 Force-submit flush saved ${answers.length} answers`);
        } catch (e) {
            console.warn('⚠️ Force-submit flush failed:', e?.message || e);
        }
    }

    async submitExam(shouldShowConfirm = true) {
        if (this.submitInProgress) {
            return;
        }
        this.submitInProgress = true;

        // Note: shouldShowConfirm is a boolean flag, not a modal function
        // The confirmation is handled by the submit modal in HTML, not here
        // This method is called with shouldShowConfirm=false for auto-submit (timer expired, force submit)

        try {
            const submitModal = document.getElementById('submit-modal');
            if (submitModal) submitModal.classList.remove('active');

            await this.autoSave();
            await this.flushPendingAnswersForForceSubmit();
            const result = await api.submitExam(this.sessionId);

            console.log('📊 Submit Result:', result);
            console.log('📊 Show Results Flag:', this.showResults);
            console.log('📊 Score:', result.score);

            clearInterval(this.timerInterval);
            clearInterval(this.autoSaveInterval);
            if (syncWorker) syncWorker.stop();
            if (journalWorker) journalWorker.stop();
            if (storageManager) await storageManager.clearSessionAnswers(this.sessionId);
            ExamSystem.clearSessionStorage();

            // 🔓 CRITICAL: Notify Flutter app to disable security features
            this.notifyFlutterExamSubmitted();
            // Wait for Flutter to process unlock before navigating
            await new Promise(resolve => setTimeout(resolve, 500));

            // DECISION POINT: Show results or skip?
            // FIX: Check for both undefined AND null to handle show_results=False properly
            if (this.showResults && result.score !== undefined && result.score !== null) {
                // ✅ SHOW RESULTS with 10-second timer
                console.log('✅ Showing results with timer');
                this.showResultsWithTimer(result.score);
            } else {
                // ❌ SKIP RESULTS, redirect immediately
                console.log('❌ Skipping results, redirecting...');
                showNotification('Ujian berhasil dikumpulkan! Nilai akan diumumkan oleh guru.', 'success');
                setTimeout(() => {
                    window.location.href = '/student/';
                }, 2000);  // Small delay to show notification
            }
        } catch (error) {
            console.error('Submit error:', error);

            // Check if exam was already submitted
            if (error.message && error.message.includes('sudah dikumpulkan')) {
                console.log('✅ Exam already submitted, redirecting to dashboard...');
                showNotification('Ujian sudah dikumpulkan sebelumnya. Mengarahkan ke dashboard...', 'info');
                setTimeout(() => {
                    window.location.href = '/student/';
                }, 2000);
                return;
            }

            const errorMsg = 'Gagal mengumpulkan ujian: ' + error.message;
            showNotification(errorMsg, 'error');
        } finally {
            this.submitInProgress = false;
        }
    }

    showResultsWithTimer(score) {
        // 🛡️ DEFENSE IN DEPTH: Safety check to prevent showing results when disabled
        // Even if this method is called incorrectly, we validate again
        if (!this.showResults || score === null || score === undefined) {
            console.warn('⚠️ showResultsWithTimer called but show_results=false or score invalid');
            console.log('showResults flag:', this.showResults, 'score:', score);
            showNotification('Ujian berhasil dikumpulkan! Nilai akan diumumkan oleh guru.', 'success');
            setTimeout(() => {
                window.location.href = '/student/';
            }, 2000);
            return;
        }

        const successModal = document.getElementById('success-modal');
        if (!successModal) {
            // Prepare result data for result.html page
            const resultData = {
                score: score,
                correct: 0, // Will be calculated by server
                total: this.questions.length,
                passed: true, // Will be recalculated
                // Include metadata for result page display
                subject: this.examMetadata?.subject || null,
                exam_type: this.examMetadata?.exam_type || null,
                exam_title: this.examMetadata?.exam_title || null
            };
            sessionStorage.setItem('exam_result', JSON.stringify(resultData));
            window.location.href = '/student/result.html';
            return;
        }

        // Display modal
        successModal.classList.add('active');

        // Update score display with professional styling
        const statusEl = document.getElementById('success-status');
        if (statusEl) {
            statusEl.innerHTML = `
                <div style="font-size: 2.5rem; font-weight: 700; margin-bottom: 0.5rem; background: linear-gradient(135deg, #22c55e, #10b981); background-clip: text; -webkit-background-clip: text; -webkit-text-fill-color: transparent;">
                    ${score}
                </div>
                <div style="font-size: 0.9rem; opacity: 0.9; color: var(--text-secondary);">Nilai Anda</div>
            `;
        }

        // Update button to show countdown
        const resultButton = document.getElementById('result-button');
        if (!resultButton) return;

        let countdown = 10;
        resultButton.innerHTML = `<i class="fas fa-chart-bar"></i> Kembali ke Dashboard (${countdown})`;

        // Countdown interval
        const countdownInterval = setInterval(() => {
            countdown--;
            if (countdown > 0) {
                resultButton.innerHTML = `<i class="fas fa-chart-bar"></i> Kembali ke Dashboard (${countdown})`;
            } else {
                clearInterval(countdownInterval);
                window.location.href = '/student/';
            }
        }, 1000);

        // Allow user to skip countdown by clicking button
        resultButton.onclick = () => {
            clearInterval(countdownInterval);
            window.location.href = '/student/';
        };
    }

    nextQuestion() {
        if (this.currentQuestionIndex < this.questions.length - 1) {
            this.renderQuestion(this.currentQuestionIndex + 1);
        }
    }

    prevQuestion() {
        if (this.currentQuestionIndex > 0) {
            this.renderQuestion(this.currentQuestionIndex - 1);
        }
    }

    jumpToQuestion(index) {
        if (index >= 0 && index < this.questions.length) {
            this.renderQuestion(index);
        }
    }

    toggleFlag() {
        const questionId = this.questions[this.currentQuestionIndex]?.id;
        if (!questionId) return;

        if (this.flagged.has(questionId)) {
            this.flagged.delete(questionId);
        } else {
            this.flagged.add(questionId);
        }
        this.renderQuestion(this.currentQuestionIndex);
        this.updateNavigator();
    }

    updateNavigator() {
        const navigator = document.getElementById('question-navigator');
        if (!navigator) return;

        let navHtml = '';
        this.questions.forEach((q, i) => {
            let isAnswered = false;
            const ans = this.answers[q.id];
            if (ans !== undefined && ans !== null && ans !== '') {
                if (Array.isArray(ans)) isAnswered = ans.length > 0;
                else if (typeof ans === 'object') isAnswered = Object.keys(ans).length > 0;
                else isAnswered = true;
            }

            const isCurrent = i === this.currentQuestionIndex;
            const isFlagged = this.flagged.has(q.id);

            navHtml += `
                <button class="question-nav-btn ${isAnswered ? 'answered' : ''} ${isCurrent ? 'current' : ''} ${isFlagged ? 'flagged' : ''}"
                     onclick="window.examSystem.jumpToQuestion(${i}); toggleNavigator();"
                     title="Soal ${i + 1}">
                    ${i + 1}
                </button>
            `;
        });
        navigator.innerHTML = navHtml;

        const answeredCount = this.questions.reduce((count, q) => {
            const ans = this.answers[q.id];
            let hasAnswer = false;
            if (ans !== undefined && ans !== null && ans !== '') {
                if (Array.isArray(ans)) hasAnswer = ans.length > 0;
                else if (typeof ans === 'object') hasAnswer = Object.keys(ans).length > 0;
                else hasAnswer = true;
            }
            return count + (hasAnswer ? 1 : 0);
        }, 0);

        const countEl = document.getElementById('answered-count');
        if (countEl) countEl.textContent = `${answeredCount}/${this.questions.length}`;

        const flaggedEl = document.getElementById('flagged-count');
        if (flaggedEl) flaggedEl.textContent = this.flagged.size;

        const remainingEl = document.getElementById('remaining-count');
        if (remainingEl) remainingEl.textContent = this.questions.length - answeredCount;

        // Update progress bar with dynamic color
        const progressBar = document.getElementById('progress-bar');
        if (progressBar && this.questions.length > 0) {
            const percentage = (answeredCount / this.questions.length) * 100;
            progressBar.style.width = `${percentage}%`;

            // Remove all color classes
            progressBar.classList.remove('low', 'medium', 'high', 'complete');

            // Add appropriate color class based on percentage
            if (percentage >= 100) {
                progressBar.classList.add('complete');
            } else if (percentage >= 75) {
                progressBar.classList.add('high');
            } else if (percentage >= 40) {
                progressBar.classList.add('medium');
            } else {
                progressBar.classList.add('low');
            }
        }
    }

    getToken() {
        return localStorage.getItem('access_token');
    }
}

window.examSystem = null;
