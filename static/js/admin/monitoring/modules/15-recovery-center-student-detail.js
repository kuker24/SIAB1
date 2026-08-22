        // ============== RECOVERY CENTER & STUDENT DETAIL ==============
        async function openRecoveryCenter(examId = null) {
            const targetExamId = Number(examId || currentExamIdForModal || 0);
            if (!targetExamId) {
                UIComponents.showToast('Exam ID tidak valid untuk Recovery Center', 'warning');
                return;
            }
            recoveryCenterExamId = targetExamId;
            recoveryCenterData = [];
            recoveryCenterFilter = 'all';
            recoveryCenterSearch = '';
            recoveryCenterActionableOnly = false;

            const modalEl = document.getElementById('recovery-center-modal');
            if (typeof showOverlayModal === 'function') {
                showOverlayModal(modalEl);
            } else if (modalEl) {
                modalEl.style.display = 'flex';
                modalEl.classList.add('active');
            }

            const searchInput = document.getElementById('recovery-search');
            if (searchInput) searchInput.value = '';
            setRecoveryFilter('all');
            toggleRecoveryActionableOnly(false);

            try {
                const exam = await getExamByIdCached(targetExamId);
                const titleEl = document.getElementById('recovery-exam-title');
                if (titleEl) titleEl.textContent = exam?.title || `Ujian #${targetExamId}`;
            } catch (_err) {
                const titleEl = document.getElementById('recovery-exam-title');
                if (titleEl) titleEl.textContent = `Ujian #${targetExamId}`;
            }

            await loadRecoveryCenterData();

            if (recoveryCenterRefreshInterval) {
                clearInterval(recoveryCenterRefreshInterval);
            }
            recoveryCenterRefreshInterval = setInterval(
                loadRecoveryCenterData,
                Math.max(15000, Number(runtimePolicy?.monitor_modal_poll_interval_ms || 15000))
            );
        }

        function closeRecoveryCenter() {
            const modalEl = document.getElementById('recovery-center-modal');
            if (typeof hideOverlayModal === 'function') {
                hideOverlayModal(modalEl);
            } else if (modalEl) {
                modalEl.classList.remove('active');
                modalEl.style.display = 'none';
            }
            if (recoveryCenterRefreshInterval) {
                clearInterval(recoveryCenterRefreshInterval);
                recoveryCenterRefreshInterval = null;
            }
            recoveryCenterExamId = null;
            recoveryCenterData = [];
        }

        function setRecoveryFilter(filter) {
            recoveryCenterFilter = String(filter || 'all');
            document.querySelectorAll('[data-recovery-filter]').forEach(btn => {
                const key = btn.dataset.recoveryFilter;
                if (key === 'only_actionable') return;
                btn.classList.toggle('active', key === recoveryCenterFilter);
            });
            renderRecoveryCenterTable();
        }

        function toggleRecoveryActionableOnly(forceValue = null) {
            recoveryCenterActionableOnly = typeof forceValue === 'boolean'
                ? forceValue
                : !recoveryCenterActionableOnly;
            const actionableBtn = document.querySelector('[data-recovery-filter="only_actionable"]');
            if (actionableBtn) {
                actionableBtn.classList.toggle('active', recoveryCenterActionableOnly);
            }
            renderRecoveryCenterTable();
        }

        function setRecoverySearch(value) {
            recoveryCenterSearch = String(value || '').trim().toLowerCase();
            renderRecoveryCenterTable();
        }

        function _recoveryReasonClass(reasonBucket) {
            const normalized = String(reasonBucket || 'unknown').toLowerCase();
            if (['network_issue', 'cheating_detected', 'admin_decision', 'user_submit'].includes(normalized)) {
                return normalized;
            }
            return 'unknown';
        }

        function _recoveryStatusLabel(status) {
            const normalized = String(status || '').toLowerCase();
            const labels = {
                submitted: 'Submitted',
                completed: 'Completed',
                terminated: 'Terminated',
                kicked: 'Kicked',
                abandoned: 'Abandoned',
            };
            return labels[normalized] || normalized || '-';
        }

        async function loadRecoveryCenterData() {
            if (!recoveryCenterExamId) return;
            try {
                const response = await api.getRecoveryCandidates(recoveryCenterExamId, 500);
                recoveryCenterData = Array.isArray(response?.candidates) ? response.candidates : [];

                const countEl = document.getElementById('recovery-count-label');
                if (countEl) {
                    countEl.textContent = `${recoveryCenterData.length} kandidat`;
                }
                const summary = response?.summary || {};
                const summaryLine = document.getElementById('recovery-summary-line');
                if (summaryLine) {
                    summaryLine.textContent = [
                        `Jaringan: ${summary.network_issue || 0}`,
                        `Pelanggaran: ${summary.cheating_detected || 0}`,
                        `Submit Normal: ${summary.user_submit || 0}`,
                        `Pengawas: ${summary.admin_decision || 0}`,
                        `Bisa Dibuka: ${summary.allow_continue || 0}`,
                    ].join(' • ');
                }
                const tsEl = document.getElementById('recovery-last-update');
                if (tsEl) {
                    const now = new Date();
                    tsEl.textContent = `Diperbarui ${now.toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}`;
                }
                renderRecoveryCenterTable();
            } catch (error) {
                console.error('[Recovery Center] Failed to load candidates:', error);
                const rawDetail = error?.detail || error?.message || '';
                const detail = typeof rawDetail === 'object'
                    ? (rawDetail.message || JSON.stringify(rawDetail))
                    : String(rawDetail || '');
                const summaryLine = document.getElementById('recovery-summary-line');
                if (summaryLine) {
                    summaryLine.textContent = `Gagal memuat recovery: ${detail || 'backend sedang bermasalah.'}`;
                }
                const tbody = document.getElementById('recovery-candidates-tbody');
                if (tbody) {
                    const safeDetail = (typeof escapeHtml === 'function')
                        ? escapeHtml(detail || 'Terjadi kesalahan saat memuat kandidat recovery.')
                        : String(detail || 'Terjadi kesalahan saat memuat kandidat recovery.');
                    tbody.innerHTML = `
                        <tr>
                            <td colspan="5" style="text-align: center; padding: 1.75rem; color: var(--text-secondary);">
                                <i class="fas fa-heart-crack" style="font-size: 1.7rem; opacity: 0.6; margin-bottom: 0.55rem;"></i>
                                <div style="font-weight: 600; color: #fca5a5;">Recovery Center gagal dimuat</div>
                                <div style="margin-top: 0.35rem; font-size: 0.8rem;">${safeDetail}</div>
                                <button class="btn btn-sm btn-primary" style="margin-top: 0.8rem;" onclick="loadRecoveryCenterData()">
                                    <i class="fas fa-rotate"></i> Coba Lagi
                                </button>
                            </td>
                        </tr>
                    `;
                }
                UIComponents.showToast(`Gagal memuat Recovery Center${detail ? `: ${detail}` : ''}`, 'danger');
            }
        }

        function renderRecoveryCenterTable() {
            const tbody = document.getElementById('recovery-candidates-tbody');
            if (!tbody) return;

            const normalizedSearch = String(recoveryCenterSearch || '').toLowerCase();
            let rows = Array.isArray(recoveryCenterData) ? [...recoveryCenterData] : [];

            if (recoveryCenterFilter !== 'all') {
                rows = rows.filter(row => String(row.reason_bucket || '').toLowerCase() === recoveryCenterFilter);
            }
            if (recoveryCenterActionableOnly) {
                rows = rows.filter(row => !!row.allow_continue || !!row.can_override);
            }
            if (normalizedSearch) {
                rows = rows.filter(row => {
                    const haystack = [
                        row.user_name,
                        row.user_class,
                        row.reason_label,
                        row.status,
                    ].join(' ').toLowerCase();
                    return haystack.includes(normalizedSearch);
                });
            }

            if (rows.length === 0) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="5" style="text-align: center; padding: 2rem; color: var(--text-secondary);">
                            <i class="fas fa-heart-crack" style="font-size: 1.8rem; opacity: 0.5; margin-bottom: 0.5rem;"></i>
                            <div>Tidak ada kandidat pada filter ini</div>
                        </td>
                    </tr>
                `;
                return;
            }

            tbody.innerHTML = rows.map((row) => {
                const reasonClass = _recoveryReasonClass(row.reason_bucket);
                const safeName = _escapeJsString(row.user_name || 'Siswa');
                const canOverride = !!row.can_override;
                let actionHtml = `<span style="color: var(--text-secondary); font-size: 0.75rem;">-</span>`;
                if (row.allow_continue) {
                    actionHtml = `
                        <button class="recovery-action-btn reset"
                                onclick="recoverCandidateSession(${row.session_id}, '${safeName}')"
                                title="Reset policy-normal: izinkan siswa lanjut dari jawaban terakhir">
                            <i class="fas fa-rotate"></i> Buka Lagi
                        </button>
                    `;
                } else if (canOverride) {
                    actionHtml = `
                        <button class="recovery-action-btn override"
                                onclick="overrideRecoverCandidateSession(${row.session_id}, '${safeName}')"
                                title="Override pengawas untuk kasus yang diblokir policy">
                            <i class="fas fa-unlock"></i> Override
                        </button>
                    `;
                }

                return `
                    <tr>
                        <td>
                            <div class="student-info">
                                <div class="student-avatar">${String(row.user_name || 'S').charAt(0).toUpperCase()}</div>
                                <div class="student-details">
                                    <div class="student-name">${row.user_name || '-'}</div>
                                    <div class="student-username">${row.user_class || '-'}</div>
                                </div>
                            </div>
                        </td>
                        <td><span class="status-badge finished">${_recoveryStatusLabel(row.status)}</span></td>
                        <td>
                            <div class="recovery-reason-pill ${reasonClass}">${row.reason_label || 'Perlu verifikasi'}</div>
                            <div style="margin-top: 0.35rem; color: var(--text-secondary); font-size: 0.75rem;">
                                ${row.recovery_message || '-'}
                            </div>
                        </td>
                        <td>
                            <span class="badge badge-${Number(row.violation_count || 0) > 0 ? 'danger' : 'secondary'}">${Number(row.violation_count || 0)}</span>
                        </td>
                        <td>${actionHtml}</td>
                    </tr>
                `;
            }).join('');
        }

        async function recoverCandidateSession(sessionId, studentName) {
            const confirmed = await showConfirmDialog(
                'Buka Lagi Sesi',
                `Buka lagi sesi <strong>${studentName}</strong> berdasarkan policy recovery?<br><br>Siswa akan bisa login ulang dan lanjut dari jawaban terakhir.`,
                'warning'
            );
            if (!confirmed) return;
            try {
                await api.resetSessionAfterDisconnect(
                    sessionId,
                    'Reset dari Recovery Center (policy allow_continue)'
                );
                UIComponents.showToast(`Sesi ${studentName} berhasil dibuka lagi`, 'success');
                await loadRecoveryCenterData();
                if (currentExamIdForModal) {
                    await loadSessionStatusData();
                }
            } catch (error) {
                const detail = error?.detail || error?.message || String(error);
                const message = typeof detail === 'object' ? (detail.message || 'Reset sesi ditolak') : detail;
                UIComponents.showToast(`Gagal buka sesi: ${message}`, 'danger');
            }
        }

        async function overrideRecoverCandidateSession(sessionId, studentName) {
            const confirmed = await showConfirmDialog(
                'Override Reopen (Pengawas)',
                `<div style="margin-bottom:0.5rem; color:#fecaca;">Aksi ini akan mengabaikan policy blokir.</div>
                 Buka lagi sesi <strong>${studentName}</strong> dengan mode override pengawas?`,
                'danger'
            );
            if (!confirmed) return;
            try {
                await api.reopenSessionOverride(
                    sessionId,
                    'Override pengawas dari Recovery Center',
                    true
                );
                UIComponents.showToast(`Override reopen berhasil untuk ${studentName}`, 'success');
                await loadRecoveryCenterData();
                if (currentExamIdForModal) {
                    await loadSessionStatusData();
                }
            } catch (error) {
                const detail = error?.detail || error?.message || String(error);
                const message = typeof detail === 'object' ? (detail.message || 'Override ditolak server') : detail;
                UIComponents.showToast(`Override gagal: ${message}`, 'danger');
            }
        }

        // ========================================
        // STUDENT DETAIL MODAL FUNCTIONS
        // ========================================
        let currentStudentData = null;

        // Open student detail modal
        async function openStudentDetailModal(studentId, examId) {
            currentStudentIdForModal = studentId;
            currentExamIdForModal = examId;

            // Show modal
            const modalEl = document.getElementById('student-detail-modal');
            if (!modalEl) {
                UIComponents.showToast('Fitur detail siswa dinonaktifkan. Gunakan Live Monitor.', 'info');
                return;
            }
            if (typeof showOverlayModal === 'function') {
                showOverlayModal(modalEl);
            } else if (modalEl) {
                modalEl.style.display = 'flex';
                modalEl.classList.add('active');
            }

            // Load initial data
            await loadStudentDetailData();

            // Start auto-refresh using runtime policy
            startStudentDetailRefreshLoop();

            console.log(`[Student Detail] Opened for student ${studentId}, exam ${examId}`);
        }

        // Close student detail modal
        function closeStudentDetailModal() {
            const modalEl = document.getElementById('student-detail-modal');
            if (typeof hideOverlayModal === 'function') {
                hideOverlayModal(modalEl);
            } else if (modalEl) {
                modalEl.classList.remove('active');
                modalEl.style.display = 'none';
            }

            // Stop auto-refresh
            if (studentDetailUpdateInterval) {
                clearInterval(studentDetailUpdateInterval);
                studentDetailUpdateInterval = null;
            }

            currentStudentIdForModal = null;
            currentStudentData = null;

            console.log('[Student Detail] Closed');
        }

        // Force submit student's exam
        async function forceSubmitStudent() {
            if (!currentStudentIdForModal || !currentExamIdForModal || !currentStudentData) {
                UIComponents.showToast('Data siswa tidak lengkap', 'danger');
                return;
            }

            const studentName = currentStudentData.student?.full_name || currentStudentData.full_name || 'Siswa';
            const sessionId = currentStudentData.session?.session_id || currentStudentData.session?.id || currentStudentData.session_id;

            const confirmed = await showConfirmDialog(
                'Force Submit Ujian',
                `Apakah Anda yakin ingin mengumpulkan paksa ujian <strong>${studentName}</strong>?<br><br>Ujian akan langsung dikumpulkan dan siswa tidak dapat melanjutkan.`,
                'warning'
            );

            if (!confirmed) return;

            try {
                // Send force submit via WebSocket (to notify student)
                let wsSent = false;
                if (monitorSocket && monitorSocket.readyState === WebSocket.OPEN) {
                    monitorSocket.send(JSON.stringify({
                        type: 'force_submit',
                        user_id: currentStudentIdForModal,
                        reason: 'Dikumpulkan paksa oleh pengawas'
                    }));
                    wsSent = true;
                }

                // Give student's device a short window to flush latest answers
                // before server-side force submit fallback.
                if (wsSent) {
                    await new Promise(resolve => setTimeout(resolve, 2500));
                }

                // Also call REST API for force submit (more reliable)
                if (sessionId) {
                    const response = await fetch(`/api/exams/sessions/${sessionId}/force-submit`, {
                        method: 'POST',
                        headers: getAuthHeaders()
                    });

                    if (response.ok) {
                        UIComponents.showToast(`✅ Ujian ${studentName} telah dikumpulkan`, 'success');
                    } else {
                        const error = await response.json().catch(() => ({}));
                        const detail = (error && (error.detail || error.message)) || '';
                        if (String(detail).toLowerCase().includes('sudah')) {
                            UIComponents.showToast(`✅ Ujian ${studentName} sudah terkumpul`, 'success');
                        } else {
                            UIComponents.showToast('Perintah submit dikirim: ' + (detail || 'via WebSocket'), 'info');
                        }
                    }
                } else {
                    UIComponents.showToast(`✅ Perintah submit dikirim ke ${studentName}`, 'success');
                }

                closeStudentDetailModal();

                // Refresh data
                setTimeout(() => loadSessionStatusData(), 1000);
            } catch (error) {
                console.error('Force submit error:', error);
                UIComponents.showToast('Gagal mengumpulkan ujian: ' + error.message, 'danger');
            }
        }

        // Force kick student from exam
        async function forceKickStudent() {
            console.log('🔴 [DEBUG] forceKickStudent called');
            console.log('🔴 [DEBUG] currentStudentIdForModal:', currentStudentIdForModal);
            console.log('🔴 [DEBUG] currentExamIdForModal:', currentExamIdForModal);
            console.log('🔴 [DEBUG] currentStudentData:', currentStudentData);

            if (!currentStudentIdForModal || !currentExamIdForModal || !currentStudentData) {
                UIComponents.showToast('Data siswa tidak lengkap', 'danger');
                return;
            }

            const studentName = currentStudentData.student?.full_name || currentStudentData.full_name || 'Siswa';
            const sessionId = currentStudentData.session?.session_id || currentStudentData.session?.id || currentStudentData.session_id;

            console.log('🔴 [DEBUG] Extracted sessionId:', sessionId);
            console.log('🔴 [DEBUG] monitorSocket state:', monitorSocket?.readyState);

            const confirmed = await showConfirmDialog(
                'Keluarkan Siswa dari Ujian',
                `<div style="color: #ef4444; font-weight: 600; margin-bottom: 0.5rem;">⚠️ PERINGATAN</div>
                 Apakah Anda yakin ingin mengeluarkan <strong>${studentName}</strong> dari ujian?<br><br>
                 <ul style="margin: 0.5rem 0; padding-left: 1.5rem; color: #94a3b8;">
                    <li>Siswa akan langsung logout dari ujian</li>
                    <li>APK akan logout otomatis</li>
                    <li>Session akan ditandai sebagai 'terminated (admin kick)'</li>
                 </ul>`,
                'danger'
            );

            if (!confirmed) return;

            try {
                // Send WebSocket notification to student device (for immediate logout)
                if (monitorSocket && monitorSocket.readyState === WebSocket.OPEN) {
                    const wsMessage = {
                        type: 'force_kick',
                        user_id: currentStudentIdForModal,
                        reason: 'Dikeluarkan oleh pengawas'
                    };
                    console.log('🔴 [DEBUG] Sending WebSocket force_kick:', wsMessage);
                    monitorSocket.send(JSON.stringify(wsMessage));
                    console.log('🔴 [DEBUG] WebSocket message sent successfully');
                } else {
                    console.warn('🔴 [DEBUG] monitorSocket NOT available or not OPEN');
                }

                // Call REST API to update session status in database
                if (sessionId) {
                    console.log('🔴 [DEBUG] Calling REST API /api/monitoring/sessions/' + sessionId + '/kick');
                    const response = await fetch(`/api/monitoring/sessions/${sessionId}/kick`, {
                        method: 'POST',
                        headers: getAuthHeaders(),
                        body: JSON.stringify({ reason: 'Dikeluarkan oleh pengawas' })
                    });

                    console.log('🔴 [DEBUG] REST API response status:', response.status);

                    if (response.ok) {
                        const result = await response.json();
                        console.log('🔴 [DEBUG] REST API success:', result);
                        UIComponents.showToast(`🚫 ${studentName} telah dikeluarkan dari ujian`, 'success');
                    } else {
                        const error = await response.json();
                        console.error('🔴 [DEBUG] REST API error:', error);
                        // Still show success since WebSocket was sent
                        UIComponents.showToast('Perintah kick dikirim: ' + (error.detail || 'via WebSocket'), 'info');
                    }
                } else {
                    console.warn('🔴 [DEBUG] No sessionId, only WebSocket sent');
                    UIComponents.showToast(`🚫 Perintah kick dikirim ke ${studentName}`, 'success');
                }

                closeStudentDetailModal();

                // Refresh data
                setTimeout(() => loadSessionStatusData(), 1000);
            } catch (error) {
                console.error('🔴 [DEBUG] Force kick error:', error);
                UIComponents.showToast('Gagal mengeluarkan siswa: ' + error.message, 'danger');
            }
        }

        // Show confirm dialog helper
        async function showConfirmDialog(title, message, type = 'warning') {
            return new Promise((resolve) => {
                if (typeof showConfirm === 'function') {
                    // Fix: showConfirm expects (message, title, options)
                    showConfirm(message, title, {
                        confirmText: 'Ya, Lanjutkan',
                        cancelText: 'Batal',
                        type: type
                    }).then(result => resolve(result));
                } else if (typeof UIComponents !== 'undefined' && UIComponents.showConfirm) {
                    UIComponents.showConfirm(title, message,
                        () => resolve(true),
                        () => resolve(false)
                    );
                } else {
                    // Fallback to native confirm
                    const result = confirm(message.replace(/<[^>]*>/g, ''));
                    resolve(result);
                }
            });
        }

        // Load student detail data
        async function loadStudentDetailData() {
            if (!currentStudentIdForModal || !currentExamIdForModal) return;

            try {
                // Get exam details
                const exam = await api.getExam(currentExamIdForModal);

                // Get sessions for this exam
                const sessions = await getExamSessions(currentExamIdForModal);

                // Find student's session
                const studentSession = sessions.find(s => s.user_id === currentStudentIdForModal);

                // Get student info
                let student = null;
                if (studentSession) {
                    student = {
                        id: studentSession.user_id,
                        full_name: studentSession.user_name,
                        username: studentSession.user_name,
                        student_class: studentSession.user_class
                    };
                } else {
                    // Try to get from assigned students
                    const assignedStudents = await getAssignedStudents(exam);
                    student = assignedStudents.find(s => s.id === currentStudentIdForModal);
                }

                if (!student) {
                    console.error('[Student Detail] Student not found');
                    return;
                }

                // Get violations for this student
                const violations = await getViolationsForExam(currentExamIdForModal);
                const studentViolations = violations.filter(v => v.user_id === currentStudentIdForModal);

                let recoveryStatus = null;
                const sessionId = studentSession?.session_id || studentSession?.id;
                if (sessionId && api && typeof api.getSessionRecoveryStatus === 'function') {
                    try {
                        recoveryStatus = await api.getSessionRecoveryStatus(sessionId);
                    } catch (recoveryError) {
                        console.warn('[Student Detail] Failed to load recovery status:', recoveryError);
                    }
                }

                // Update UI
                updateStudentDetailUI(student, studentSession, studentViolations, exam, recoveryStatus);

                // Update last update time
                const now = new Date();
                const timeStr = now.toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
                document.getElementById('detail-last-update').textContent = `Diperbarui ${timeStr}`;

            } catch (error) {
                console.error('[Student Detail] Failed to load data:', error);
            }
        }

        // Update student detail UI
        function updateStudentDetailUI(student, session, violations, exam, recoveryStatus = null) {
            currentStudentData = { student, session, violations, exam, recoveryStatus };

            // Update student info
            document.getElementById('detail-student-name').textContent = student.full_name;
            document.getElementById('detail-student-username').textContent = `@${student.username}`;
            document.getElementById('detail-student-avatar').textContent = student.full_name.charAt(0).toUpperCase();

            // Determine connection status
            const connectionKey = getMonitorStudentKey(currentExamIdForModal, student.id);
            const connectionState = studentConnectionStatus[connectionKey]
                || (session?.is_online ? 'online' : 'offline');

            // Update connection status badge
            const statusBadge = document.getElementById('detail-connection-status');
            if (connectionState === 'online') {
                statusBadge.className = 'badge badge-success';
                statusBadge.innerHTML = '<i class="fas fa-circle" style="font-size: 0.5rem;"></i> 🟢 Online';
            } else {
                statusBadge.className = 'badge badge-secondary';
                statusBadge.innerHTML = '<i class="fas fa-circle" style="font-size: 0.5rem;"></i> 🔴 Offline';
            }

            // Update status cards
            let examStatus = 'Belum Mulai';
            let progress = 0;

            if (session) {
                if (session.status === 'completed' || session.status === 'ended') {
                    examStatus = 'Selesai';
                    progress = 100;
                } else if (session.status === 'in_progress') {
                    examStatus = 'Sedang Ujian';
                    progress = session.progress || 0;
                } else {
                    examStatus = 'Siap';
                    progress = 0;
                }
            }

            document.getElementById('detail-exam-status').textContent = examStatus;
            document.getElementById('detail-progress').textContent = `${progress}%`;
            document.getElementById('detail-violations').textContent = violations.length;

            const recoveryCategoryEl = document.getElementById('detail-recovery-category');
            const recoveryMessageEl = document.getElementById('detail-recovery-message');
            const resetBtn = document.getElementById('detail-reset-session-btn');
            const recoveryCategory = recoveryStatus?.recovery_category
                || session?.recovery_category
                || '-';
            const allowContinue = Boolean(
                recoveryStatus?.allow_continue ?? session?.allow_continue ?? false
            );
            const recoveryMessage = recoveryStatus?.message
                || session?.recovery_message
                || 'Status recovery belum tersedia.';

            if (recoveryCategoryEl) {
                recoveryCategoryEl.textContent = String(recoveryCategory).replace(/_/g, ' ').toUpperCase();
                recoveryCategoryEl.style.color = allowContinue ? '#22c55e' : '#f87171';
            }
            if (recoveryMessageEl) {
                recoveryMessageEl.textContent = recoveryMessage;
            }
            if (resetBtn) {
                resetBtn.disabled = !session || !allowContinue || session.status === 'in_progress';
                resetBtn.style.opacity = resetBtn.disabled ? '0.65' : '1';
                resetBtn.title = resetBtn.disabled
                    ? 'Reset hanya diizinkan untuk sesi yang boleh lanjut karena network issue'
                    : 'Reset sesi agar siswa bisa lanjut dari jawaban terakhir';
            }

            // Update device info
            document.getElementById('detail-device').textContent = session?.device_info || session?.user_agent || '-';
            document.getElementById('detail-ip').textContent = session?.ip_address || '-';
            document.getElementById('detail-browser').textContent = session?.browser || '-';
            document.getElementById('detail-start-time').textContent = session?.start_time ? formatWIB(session.start_time) : '-';

            // Update violations list
            const violationsList = document.getElementById('detail-violations-list');
            if (violations.length === 0) {
                violationsList.innerHTML = `
                    <div style="text-align: center; padding: 1rem; color: var(--text-secondary);">
                        <i class="fas fa-check-circle" style="font-size: 2rem; margin-bottom: 0.5rem; color: var(--success);"></i>
                        <div>Tidak ada pelanggaran</div>
                    </div>
                `;
            } else {
                violationsList.innerHTML = violations.map(v => `
                    <div style="background: rgba(239, 68, 68, 0.1); border-left: 3px solid var(--danger); padding: 0.75rem; border-radius: 4px;">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <span style="color: var(--danger); font-weight: 600;">
                                <i class="fas fa-exclamation-triangle"></i> ${getViolationDisplayMeta(v).label}
                            </span>
                            <span style="color: var(--text-secondary); font-size: 0.75rem;">
                                ${v.created_at ? formatWIB(v.created_at, { hour: '2-digit', minute: '2-digit' }) : '-'}
                            </span>
                        </div>
                        ${getViolationDisplayMeta(v).description ? `<div style="color: var(--text-secondary); font-size: 0.85rem; margin-top: 0.25rem;">${getViolationDisplayMeta(v).description}</div>` : ''}
                    </div>
                `).join('');
            }
        }

        async function resetStudentSession() {
            const sessionId = currentStudentData?.session?.session_id || currentStudentData?.session?.id;
            const studentName = currentStudentData?.student?.full_name || 'Siswa';
            if (!sessionId) {
                UIComponents.showToast('Session ID tidak ditemukan', 'danger');
                return;
            }

            const confirmed = await showConfirmDialog(
                'Reset Sesi Siswa',
                `Reset sesi <strong>${studentName}</strong> karena kendala jaringan?<br><br>Siswa akan diizinkan login kembali dan melanjutkan jawaban terakhir.`,
                'warning'
            );
            if (!confirmed) return;

            try {
                if (api && typeof api.resetSessionAfterDisconnect === 'function') {
                    await api.resetSessionAfterDisconnect(
                        sessionId,
                        'Reset dari Menu Sesi Aktif (gangguan jaringan)'
                    );
                } else {
                    await apiRequest(`/api/monitoring/sessions/${sessionId}/reset`, 'POST', {
                        reason: 'Reset dari Menu Sesi Aktif (gangguan jaringan)'
                    });
                }
                UIComponents.showToast('Sesi berhasil di-reset. Siswa dapat login kembali.', 'success');
                await loadStudentDetailData();
                setTimeout(() => loadSessionStatusData(), 1000);
            } catch (error) {
                const detail = error?.detail || error?.message || String(error);
                const message = typeof detail === 'object' ? (detail.message || 'Reset sesi ditolak oleh policy') : detail;
                UIComponents.showToast(`Reset sesi gagal: ${message}`, 'danger');
            }
        }
        // ========================================
