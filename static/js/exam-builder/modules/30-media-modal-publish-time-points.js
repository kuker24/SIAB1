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

    listContainer.innerHTML = filtered.map(s => `
        <div class="student-item">
            <input type="checkbox" id="student-${s.id}"
                   ${publishState.selectedStudents.includes(s.id) ? 'checked' : ''}
                   onchange="toggleStudentSelection(${s.id})">
            <div class="student-info">
                <div class="student-name">${s.full_name}</div>
                <div class="student-class"><i class="fas fa-users" style="font-size:0.7em;"></i> ${s.student_class}</div>
            </div>
            <span class="badge badge-secondary" style="font-size:0.7em;">${s.username}</span>
        </div>
    `).join('');

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
