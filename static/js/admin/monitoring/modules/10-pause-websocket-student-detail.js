        // ============== PAUSE CONTROL SYSTEM ==============
        let selectedExamId = null;
        let isPaused = false;
        let pauseTimerInterval = null;
        let pauseStartTime = null;
        let sessionTableStatusFilter = 'all';
        let sessionTableSearchTerm = '';
        let latestSessionTableData = [];
        let recoveryCenterExamId = null;
        let recoveryCenterData = [];
        let recoveryCenterFilter = 'all';
        let recoveryCenterSearch = '';
        let recoveryCenterActionableOnly = false;
        let recoveryCenterRefreshInterval = null;

        // Handle exam filter change
        document.getElementById('exam-filter').addEventListener('change', async (e) => {
            selectedExamId = e.target.value ? parseInt(e.target.value) : null;
            updatePauseControlPanel();
        });

        async function updatePauseControlPanel() {
            const panel = document.getElementById('pause-control-panel');
            const btn = document.getElementById('pause-btn');
            const timerDisplay = document.getElementById('pause-timer-display');

            if (!selectedExamId) {
                panel.style.display = 'none';
                return;
            }

            panel.style.display = 'block';

            try {
                const response = await fetch(`/api/exams/${selectedExamId}/pause-status`, {
                    headers: getAuthHeaders()
                });

                if (response.ok) {
                    const data = await response.json();
                    isPaused = data.is_paused;

                    if (isPaused) {
                        panel.classList.add('paused');
                        btn.className = 'pause-btn resume';
                        btn.innerHTML = '<i class="fas fa-play"></i><span>LANJUTKAN UJIAN</span>';
                        timerDisplay.style.display = 'block';

                        // Start pause timer
                        pauseStartTime = new Date(data.paused_at);
                        startPauseTimer();
                    } else {
                        panel.classList.remove('paused');
                        btn.className = 'pause-btn pause';
                        btn.innerHTML = '<i class="fas fa-pause"></i><span>PAUSE UJIAN</span>';
                        timerDisplay.style.display = 'none';
                        stopPauseTimer();
                    }
                }
            } catch (error) {
                console.error('Failed to get pause status:', error);
            }
        }

        function startPauseTimer() {
            stopPauseTimer();
            pauseTimerInterval = setInterval(() => {
                const elapsed = Math.floor((new Date() - pauseStartTime) / 1000);
                const mins = Math.floor(elapsed / 60).toString().padStart(2, '0');
                const secs = (elapsed % 60).toString().padStart(2, '0');
                document.getElementById('pause-timer').textContent = `${mins}:${secs}`;
            }, 1000);
        }

        function stopPauseTimer() {
            if (pauseTimerInterval) {
                clearInterval(pauseTimerInterval);
                pauseTimerInterval = null;
            }
        }

        async function toggleExamPause() {
            if (!selectedExamId) {
                showAlert('Pilih ujian terlebih dahulu', 'warning');
                return;
            }

            const action = isPaused ? 'resume' : 'pause';
            const confirmMsg = isPaused
                ? 'Lanjutkan ujian untuk semua siswa? Timer akan dilanjutkan dengan waktu yang sudah disesuaikan.'
                : 'PAUSE ujian untuk semua siswa? Semua timer akan dihentikan sementara.';

            const confirmed = await showConfirm(confirmMsg, {
                title: isPaused ? 'Lanjutkan Ujian' : '⚠️ PAUSE Ujian',
                type: isPaused ? 'success' : 'danger',
                confirmText: isPaused ? 'Ya, Lanjutkan' : 'Ya, PAUSE Sekarang',
                cancelText: 'Batal'
            });

            if (!confirmed) return;

            try {
                const endpoint = isPaused ? 'resume-all' : 'pause-all';
                const response = await fetch(`/api/exams/${selectedExamId}/${endpoint}`, {
                    method: 'POST',
                    headers: getAuthHeaders()
                });

                if (response.ok) {
                    const data = await response.json();
                    showAlert(data.message, 'success');
                    updatePauseControlPanel();
                } else {
                    const error = await response.json();
                    showAlert(error.detail || 'Gagal mengubah status pause', 'danger');
                }
            } catch (error) {
                showAlert('Terjadi kesalahan jaringan', 'danger');
            }
        }

        async function bootstrapMonitoringPage() {
            applyRoleScopedVisibility();
            await loadRuntimePolicy();
            startMainRefreshLoop();
            await refreshData();

            if (policyRefreshInterval) {
                clearInterval(policyRefreshInterval);
            }
            policyRefreshInterval = setInterval(async () => {
                if (document.hidden) return;
                await loadRuntimePolicy();
                startMainRefreshLoop();
                if (!hideOpsSummary) {
                    await loadOpsSummary();
                }

                if (currentExamIdForModal) {
                    startModalRefreshLoop();
                }
                if (currentStudentIdForModal) {
                    startStudentDetailRefreshLoop();
                }
                if (document.getElementById('fullscreen-monitor').classList.contains('active')) {
                    startFmRefreshLoop();
                }
            }, 60000);

            document.addEventListener('visibilitychange', () => {
                if (document.hidden) {
                    refreshQueuedWhileHidden = true;
                    return;
                }
                refreshSummaryOnceWhenVisible();
            });
        }

        bootstrapMonitoringPage();

        // ============== REAL-TIME WEBSOCKET MONITORING ==============
        let monitorSocket = null;
        let wsReconnectInterval = null;
        let wsPingInterval = null;
        let wsReconnectAttempts = 0;
        const WS_MAX_RECONNECT_ATTEMPTS = 10;
        const WS_INITIAL_RECONNECT_DELAY = 1000; // 1 second
        const WS_MAX_RECONNECT_DELAY = 30000; // 30 seconds

        function getReconnectDelay() {
            // Exponential backoff: 1s, 2s, 4s, 8s, 16s, 30s, 30s...
            const delay = Math.min(
                WS_INITIAL_RECONNECT_DELAY * Math.pow(2, wsReconnectAttempts),
                WS_MAX_RECONNECT_DELAY
            );
            return delay;
        }

        function connectMonitorWebSocket(examId) {
            if (monitorSocket) {
                monitorSocket.close();
            }

            // Clear any existing ping interval
            if (wsPingInterval) {
                clearInterval(wsPingInterval);
                wsPingInterval = null;
            }

            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            // Correct Path: Directly /ws/monitor/{id} without /api prefix
            const wsToken = localStorage.getItem('access_token');
            const wsUrl = `${protocol}//${window.location.host}/ws/monitor/${examId}?token=${wsToken}`;

            console.log(`🔌 Connecting to Monitor WebSocket: ${wsUrl.replace(wsToken, '***')}`);

            monitorSocket = new WebSocket(wsUrl);

            monitorSocket.onopen = () => {
                console.log('✅ Monitor WebSocket Connected');
                document.querySelector('.online-indicator').style.background = '#10b981'; // Green
                document.querySelector('.online-indicator').title = "Real-time Connected";

                // Reset reconnect attempts on successful connection
                wsReconnectAttempts = 0;

                // Clear reconnect interval if exists
                if (wsReconnectInterval) {
                    clearInterval(wsReconnectInterval);
                    wsReconnectInterval = null;
                }

                // Start Ping/Heartbeat (every 25 seconds)
                wsPingInterval = setInterval(() => {
                    if (monitorSocket && monitorSocket.readyState === WebSocket.OPEN) {
                        // console.log('💓 Sending WebSocket Ping');
                        monitorSocket.send(JSON.stringify({ type: 'ping' }));
                    }
                }, 25000);
            };

            monitorSocket.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    handleRealtimeEvent(data);
                } catch (e) {
                    console.error('WebSocket message error:', e);
                }
            };

            monitorSocket.onclose = (e) => {
                console.warn('⚠️ Monitor WebSocket Disconnected', e.reason);
                document.querySelector('.online-indicator').style.background = '#ef4444'; // Red
                document.querySelector('.online-indicator').title = "Disconnected (Reconnecting...)";

                // Clear ping interval
                if (wsPingInterval) {
                    clearInterval(wsPingInterval);
                    wsPingInterval = null;
                }

                // Try to reconnect with exponential backoff if modal is still open
                if (document.getElementById('session-status-modal').style.display !== 'none') {
                    if (wsReconnectAttempts < WS_MAX_RECONNECT_ATTEMPTS) {
                        const delay = getReconnectDelay();
                        console.log(`🔄 Attempting WebSocket Reconnect in ${delay / 1000}s (attempt ${wsReconnectAttempts + 1}/${WS_MAX_RECONNECT_ATTEMPTS})...`);

                        if (!wsReconnectInterval) {
                            wsReconnectInterval = setTimeout(() => {
                                connectMonitorWebSocket(examId);
                                wsReconnectInterval = null;
                            }, delay);
                            wsReconnectAttempts++;
                        }
                    } else {
                        console.warn('⚠️ Max WebSocket reconnect attempts reached. Switching to HTTP polling only.');
                        document.querySelector('.online-indicator').title = "Offline (Polling Mode)";
                    }
                }
            };

            monitorSocket.onerror = (error) => {
                console.error('WebSocket Error:', error);
            };
        }

        // Student connection status map
        let studentConnectionStatus = {};

        function getMonitorStudentKey(examId, userId) {
            return `${examId || 0}:${userId || 0}`;
        }

        function getMonitorStudentDomId(studentKey) {
            return `fm-student-${String(studentKey).replace(/[^a-zA-Z0-9_-]/g, '-')}`;
        }

        function getFmStudentKeyFromEvent(event, fallbackExamId = null) {
            return getMonitorStudentKey(event?.exam_id || fallbackExamId, event?.user_id);
        }

        function getViolationDisplayMeta(item = {}) {
            const rawType = item.violation_type || item.event_type || item.type || 'violation';
            const fallback = formatViolationType(rawType);
            return {
                type: rawType,
                label: item.violation_label || item.label || fallback.label,
                severity: item.violation_severity || item.severity || fallback.severity,
                description: item.description || fallback.desc
            };
        }

        function handleRealtimeEvent(event) {
            console.log('⚡ Real-time Event:', event.type, event);
            const studentKey = getMonitorStudentKey(currentExamIdForModal || event.exam_id, event.user_id);

            // Handle Connection Status Events
            if (event.type === 'student_connected') {
                studentConnectionStatus[studentKey] = 'online';
                updateStudentStatusIndicator(event.user_id, 'online');
            } else if (event.type === 'student_disconnected') {
                studentConnectionStatus[studentKey] = 'offline';
                updateStudentStatusIndicator(event.user_id, 'offline');
            }

            // Also mark as online if we receive any activity
            if (event.type === 'student_activity' || event.type === 'student_started') {
                studentConnectionStatus[studentKey] = 'online';
                updateStudentStatusIndicator(event.user_id, 'online');
            }

            // Handle real-time progress updates
            if (event.type === 'progress_update') {
                updateStudentProgress(event.user_id, event.progress, event.answered_count, event.total_questions);
                studentConnectionStatus[studentKey] = 'online';
                updateStudentStatusIndicator(event.user_id, 'online');
            }

            // Update timestamp
            updateLastUpdateTime();

            // Refresh data on critical events
            // Idealnya kita update UI parsial, tapi untuk konsistensi data awal,
            // kita trigger refresh data tabel yang sudah ada logic-nya.
            if (['student_started', 'student_submitted', 'violation', 'violation_detected', 'force_submit'].includes(event.type)) {
                loadSessionStatusData();
            }

            // Show toast for violations
            if (event.type === 'violation' || event.type === 'violation_detected') {
                const userName = event.username || 'Siswa';
                const violationMeta = getViolationDisplayMeta(event);
                UIComponents.showToast(`⚠️ ${userName}: ${violationMeta.label}`, 'warning');
            }
        }

        function updateStudentStatusIndicator(userId, status) {
            const indicator = document.getElementById(`status-indicator-${userId}`);
            const statusText = document.getElementById(`status-text-${userId}`);

            if (indicator) {
                indicator.className = `student-status-indicator ${status}`;
                indicator.title = status === 'online' ? 'Online' : 'Offline';
            }

            if (statusText) {
                // Optional: Update text label if needed, currently using visual dot
            }
        }

        // Real-time progress update for a student
        function updateStudentProgress(userId, progress, answeredCount, totalQuestions) {
            console.log(`📊 Progress Update: User ${userId} = ${progress}%`);

            // Update in session status table (modal)
            const progressBar = document.querySelector(`#session-row-${userId} .progress-bar`);
            const progressText = document.querySelector(`#session-row-${userId} .progress-text`);

            if (progressBar) {
                progressBar.style.width = `${progress}%`;
            }
            if (progressText) {
                progressText.textContent = `${progress}%`;
            }

            // Update in fullscreen monitor if active
            const fmStudentKey = getMonitorStudentKey(currentExamIdForModal, userId);
            if (fmStudentsData[fmStudentKey]) {
                fmStudentsData[fmStudentKey].progress = progress;
                updateFmStudentCard(fmStudentKey);
            }
        }

        // Open session status modal for specific exam
        async function openSessionStatusModal(examId) {
            currentExamIdForModal = examId;
            sessionTableStatusFilter = 'all';
            sessionTableSearchTerm = '';
            latestSessionTableData = [];

            // Show modal
            const modalEl = document.getElementById('session-status-modal');
            if (typeof showOverlayModal === 'function') {
                showOverlayModal(modalEl);
            } else if (modalEl) {
                modalEl.style.display = 'flex';
                modalEl.classList.add('active');
            }
            const tableSearchInput = document.getElementById('session-table-search');
            if (tableSearchInput) tableSearchInput.value = '';
            setSessionTableStatusFilter('all');

            // Load initial data
            await loadSessionStatusData();

            // Connect WebSocket for Real-time updates
            connectMonitorWebSocket(examId);

            // Keep polling as fallback to ensure data consistency
            startModalRefreshLoop();

            console.log(`[Modal] Opened for exam ${examId}, WebSocket + Polling started`);
        }

        // Close modal and cleanup
        function closeSessionStatusModal() {
            const modalEl = document.getElementById('session-status-modal');
            if (typeof hideOverlayModal === 'function') {
                hideOverlayModal(modalEl);
            } else if (modalEl) {
                modalEl.classList.remove('active');
                modalEl.style.display = 'none';
            }

            // Close WebSocket
            if (monitorSocket) {
                monitorSocket.close();
                monitorSocket = null;
            }

            if (wsReconnectInterval) {
                clearInterval(wsReconnectInterval);
                wsReconnectInterval = null;
            }

            // Stop auto-refresh
            if (modalUpdateInterval) {
                clearInterval(modalUpdateInterval);
                modalUpdateInterval = null;
            }
            closeRecoveryCenter();

            currentExamIdForModal = null;
            console.log('[Modal] Closed, monitoring stopped');
        }

        const EXAM_CACHE_TTL_MS = 30 * 1000;
        const ASSIGNED_STUDENTS_CACHE_TTL_MS = 2 * 60 * 1000;
        const ALL_STUDENTS_CACHE_TTL_MS = 2 * 60 * 1000;
        const examCache = new Map();
        const assignedStudentsCache = new Map();
        let allStudentsCache = { expiresAt: 0, data: [] };

        // Load session status data
        async function loadSessionStatusData() {
            if (!currentExamIdForModal) return;

            try {
                const exam = await getExamByIdCached(currentExamIdForModal);
                const [assignedStudents, sessions, violations] = await Promise.all([
                    getAssignedStudents(exam),
                    getExamSessions(currentExamIdForModal),
                    getViolationsForExam(currentExamIdForModal)
                ]);

                updateModalUI(exam, assignedStudents, sessions, violations);
                updateLastUpdateTime();
            } catch (error) {
                console.error('[Modal] Failed to load session status:', error);
            }
        }

        function parseCsvList(value) {
            return String(value || '')
                .split(',')
                .map(item => item.trim())
                .filter(Boolean);
        }

        function parseAllowedStudentIds(value) {
            return parseCsvList(value)
                .map(id => parseInt(id, 10))
                .filter(id => Number.isInteger(id) && id > 0);
        }

        function normalizeStudentList(students = []) {
            const studentsMap = new Map();
            students.forEach(student => {
                if (!student?.id || studentsMap.has(student.id)) return;
                studentsMap.set(student.id, {
                    id: student.id,
                    full_name: student.full_name || student.username,
                    username: student.username || student.full_name,
                    student_class: student.student_class || null
                });
            });
            return Array.from(studentsMap.values());
        }

        function buildAssignedStudentsCacheKey(exam) {
            const allowedClasses = parseCsvList(exam?.allowed_classes).sort().join(',');
            const allowedStudentIds = parseAllowedStudentIds(exam?.allowed_students).sort((a, b) => a - b).join(',');
            return `${exam?.id || 0}|${allowedClasses}|${allowedStudentIds}`;
        }

        async function getExamByIdCached(examId) {
            const now = Date.now();
            const cached = examCache.get(examId);
            if (cached && cached.expiresAt > now) {
                return cached.data;
            }
            const exam = await api.getExam(examId);
            examCache.set(examId, { expiresAt: now + EXAM_CACHE_TTL_MS, data: exam });
            return exam;
        }

        async function getAllStudentsCached() {
            const now = Date.now();
            if (allStudentsCache.expiresAt > now && Array.isArray(allStudentsCache.data)) {
                return allStudentsCache.data;
            }
            const allStudents = await api.getStudentsByClass();
            allStudentsCache = {
                expiresAt: now + ALL_STUDENTS_CACHE_TTL_MS,
                data: Array.isArray(allStudents) ? allStudents : []
            };
            return allStudentsCache.data;
        }

        async function getAssignedStudents(examOrId) {
            try {
                const exam = (
                    typeof examOrId === 'object' && examOrId !== null
                ) ? examOrId : await getExamByIdCached(examOrId);
                const now = Date.now();
                const cacheKey = buildAssignedStudentsCacheKey(exam);
                const cached = assignedStudentsCache.get(cacheKey);
                if (cached && cached.expiresAt > now) {
                    return cached.data;
                }

                const allowedClasses = parseCsvList(exam?.allowed_classes);
                const allowedStudentIds = parseAllowedStudentIds(exam?.allowed_students);
                const studentsMap = new Map();
                const appendStudents = (students = []) => {
                    normalizeStudentList(students).forEach(student => {
                        if (!studentsMap.has(student.id)) {
                            studentsMap.set(student.id, student);
                        }
                    });
                };

                if (allowedClasses.length === 0 && allowedStudentIds.length === 0) {
                    appendStudents(await getAllStudentsCached());
                } else {
                    if (allowedClasses.length > 0) {
                        const classBuckets = await Promise.all(
                            allowedClasses.map(className => api.getStudentsByClass(className).catch(() => []))
                        );
                        classBuckets.forEach(bucket => appendStudents(bucket));
                    }

                    if (allowedStudentIds.length > 0) {
                        const allStudents = await getAllStudentsCached();
                        appendStudents(
                            allStudents.filter(student => allowedStudentIds.includes(student.id))
                        );
                    }
                }

                if (studentsMap.size === 0 && exam?.id) {
                    const response = await api.getExamSessions(exam.id);
                    const sessions = response?.sessions || [];
                    sessions.forEach(s => {
                        if (s.user_id && !studentsMap.has(s.user_id)) {
                            studentsMap.set(s.user_id, {
                                id: s.user_id,
                                full_name: s.user_name,
                                username: s.user_name,
                                student_class: s.user_class
                            });
                        }
                    });
                }

                const students = Array.from(studentsMap.values());
                assignedStudentsCache.set(cacheKey, {
                    expiresAt: now + ASSIGNED_STUDENTS_CACHE_TTL_MS,
                    data: students
                });
                return students;
            } catch (error) {
                console.error('[Modal] Failed to get assigned students:', error);
                return [];
            }
        }

        // Get exam sessions using API method
        async function getExamSessions(examId) {
            try {
                const response = await api.getExamSessions(examId);

                // Ensure we return an array - handle both { sessions: [...] } and [...] formats
                if (Array.isArray(response)) {
                    return response;
                } else if (response && Array.isArray(response.sessions)) {
                    return response.sessions;
                } else if (response && typeof response === 'object') {
                    // Handle other response formats
                    console.warn('[Modal] Unexpected response format from getExamSessions:', response);
                    return [];
                } else {
                    console.error('[Modal] Invalid response from getExamSessions:', response);
                    return [];
                }
            } catch (error) {
                console.error('[Modal] Failed to get exam sessions:', error);
                return [];
            }
        }

        // Get violations using violations dashboard API
        async function getViolationsForExam(examId) {
            try {
                return await api.getViolationsDashboard(examId, null, null, { summaryOnly: true });
            } catch (error) {
                console.error('[Modal] Failed to get violations:', error);
                return { by_user: {}, violations: [] };
            }
        }

        function setSessionTableStatusFilter(status) {
            sessionTableStatusFilter = String(status || 'all');
            document.querySelectorAll('[data-status-filter]').forEach(btn => {
                btn.classList.toggle('active', btn.dataset.statusFilter === sessionTableStatusFilter);
            });
            renderStudentTable(latestSessionTableData);
        }

        function setSessionTableSearch(query) {
            sessionTableSearchTerm = String(query || '').trim().toLowerCase();
            renderStudentTable(latestSessionTableData);
        }

        function _escapeJsString(value) {
            return String(value || '')
                .replace(/\\/g, '\\\\')
                .replace(/'/g, "\\'")
                .replace(/\n/g, ' ')
                .replace(/\r/g, ' ');
        }

        function _statusLabelFromSession(session) {
            const rawStatus = String(session?.status || '').toLowerCase();
            if (rawStatus === 'in_progress' || rawStatus === 'active') return { key: 'active', label: 'Sedang Ujian' };
            if (rawStatus === 'paused') return { key: 'active', label: 'Di-pause' };
            if (rawStatus === 'completed' || rawStatus === 'submitted' || rawStatus === 'ended') {
                return { key: 'finished', label: 'Selesai' };
            }
            if (rawStatus === 'terminated' || rawStatus === 'kicked' || rawStatus === 'abandoned') {
                return { key: 'ready', label: 'Terhenti' };
            }
            return { key: 'ready', label: 'Siap' };
        }

        // Update modal UI
        function updateModalUI(exam, assignedStudents, sessions, violations) {
            // Ensure sessions is an array - FIX for "sessions.find is not a function" error
            let sessionsArray = [];
            if (Array.isArray(sessions)) {
                sessionsArray = sessions;
            } else if (sessions && Array.isArray(sessions.sessions)) {
                // Handle API response format { sessions: [...] }
                sessionsArray = sessions.sessions;
            } else if (sessions && typeof sessions === 'object') {
                // Fallback: try to extract sessions from response object
                console.warn('[Modal] Sessions data format unexpected:', sessions);
                sessionsArray = [];
            } else {
                console.error('[Modal] Sessions is not an array:', sessions);
                sessionsArray = [];
            }

            // Ensure assignedStudents is an array
            const studentsArray = Array.isArray(assignedStudents) ? assignedStudents : [];

            const violationsPayload = (violations && typeof violations === 'object') ? violations : {};
            const violationsArray = Array.isArray(violationsPayload.violations)
                ? violationsPayload.violations
                : (Array.isArray(violations) ? violations : []);
            const violationsByUserMap = new Map(
                Object.entries(violationsPayload.by_user || {})
                    .map(([userId, count]) => [Number(userId), Number(count || 0)])
                    .filter(([userId]) => Number.isInteger(userId) && userId > 0)
            );
            const sessionByUserId = new Map();
            sessionsArray.forEach(session => {
                const userId = Number(session?.user_id || session?.user?.id || 0);
                if (userId > 0 && !sessionByUserId.has(userId)) {
                    sessionByUserId.set(userId, session);
                }
            });
            const violationsBySessionId = new Map();
            if (violationsByUserMap.size === 0 && violationsArray.length > 0) {
                violationsArray.forEach(v => {
                    const sessionId = Number(v?.exam_session_id || v?.session_id || 0);
                    if (sessionId > 0) {
                        violationsBySessionId.set(sessionId, (violationsBySessionId.get(sessionId) || 0) + 1);
                    }
                });
            }

            // Update exam info
            document.getElementById('modal-exam-title').textContent = exam.title;
            document.getElementById('modal-student-count').textContent = ` • ${studentsArray.length} siswa total`;

            // Calculate status counts
            const counts = {
                active: 0,      // SEDANG UJIAN
                ready: 0,       // SIAP / MENUNGGU
                pending: 0,     // BELUM MULAI
                finished: 0     // SELESAI
            };

            // Build student data with status
            const studentData = studentsArray.map(student => {
                const session = sessionByUserId.get(student.id);
                const sessionId = Number(session?.session_id || session?.id || 0);
                const violationsCount = violationsByUserMap.has(student.id)
                    ? violationsByUserMap.get(student.id)
                    : (sessionId > 0 ? (violationsBySessionId.get(sessionId) || 0) : 0);

                let status = 'pending'; // Default: BELUM MULAI
                let statusLabel = 'Belum Masuk';
                let deviceInfo = '-';

                if (session) {
                    const statusInfo = _statusLabelFromSession(session);
                    status = statusInfo.key;
                    statusLabel = statusInfo.label;
                    if (status === 'finished') counts.finished++;
                    else if (status === 'active') counts.active++;
                    else counts.ready++;

                    deviceInfo = session.user_agent || session.device_info || 'Unknown Device';
                } else {
                    counts.pending++;
                }

                return {
                    student,
                    session,
                    status,
                    statusLabel,
                    deviceInfo,
                    violationsCount: Number(violationsCount || 0)
                };
            });

            // Update status cards
            document.getElementById('count-active').textContent = counts.active;
            document.getElementById('count-ready').textContent = counts.ready;
            document.getElementById('count-pending').textContent = counts.pending;
            document.getElementById('count-finished').textContent = counts.finished;

            // Render student table
            latestSessionTableData = studentData;
            renderStudentTable(studentData);
        }

        // Render student table
        function renderStudentTable(studentData) {
            const tbody = document.getElementById('session-students-tbody');
            const sourceRows = Array.isArray(studentData) ? studentData : [];
            const normalizedSearch = String(sessionTableSearchTerm || '').trim().toLowerCase();
            const filteredRows = sourceRows.filter((data) => {
                if (!data || !data.student) return false;
                if (sessionTableStatusFilter !== 'all' && data.status !== sessionTableStatusFilter) {
                    return false;
                }
                if (!normalizedSearch) return true;
                const haystack = [
                    data.student.full_name,
                    data.student.username,
                    data.student.student_class,
                ].join(' ').toLowerCase();
                return haystack.includes(normalizedSearch);
            });

            if (filteredRows.length === 0) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="4" style="text-align: center; padding: 2rem; color: var(--text-secondary);">
                            <i class="fas fa-user-slash" style="font-size: 2rem; margin-bottom: 0.5rem; opacity: 0.5;"></i>
                            <div>Tidak ada data siswa pada filter saat ini</div>
                        </td>
                    </tr>
                `;
                return;
            }

            tbody.innerHTML = filteredRows.map(data => {
                const { student, session, status, statusLabel, deviceInfo, violationsCount } = data;

                // Truncate device info if too long
                const shortDevice = deviceInfo.length > 30 ? deviceInfo.substring(0, 27) + '...' : deviceInfo;
                const sessionId = Number(session?.session_id || session?.id || 0);
                const rawSessionStatus = String(session?.status || '').toLowerCase();
                const allowRowActions = sessionId > 0 && !['completed', 'submitted', 'ended'].includes(rawSessionStatus);
                const studentName = String(student.full_name || 'Siswa');
                const safeStudentName = escapeHtml(studentName);
                const safeStudentNameArg = escapeHtml(JSON.stringify(studentName));
                const safeStudentInitial = escapeHtml(studentName.charAt(0).toUpperCase());
                const safeUsername = escapeHtml(student.username);
                const safeStudentClass = escapeHtml(student.student_class);
                const safeDeviceInfo = escapeHtml(deviceInfo);
                const safeShortDevice = escapeHtml(shortDevice);

                const connectionKey = getMonitorStudentKey(currentExamIdForModal, student.id);
                const connectionState = studentConnectionStatus[connectionKey]
                    || (session?.is_online ? 'online' : 'offline');

                return `
                    <tr>
                        <td>
                            <div class="student-info">
                                <div class="student-avatar">
                                    ${safeStudentInitial}
                                </div>
                                <div class="student-details">
                                    <div class="student-name">
                                        ${safeStudentName}
                                        <span id="status-indicator-${student.id}"
                                              class="student-status-indicator ${connectionState}"
                                              title="${connectionState === 'online' ? '🟢 Online' : '🔴 Offline'}">
                                        </span>
                                    </div>
                                    <div class="student-username">
                                        ${safeUsername}
                                        ${student.student_class ? `<span style="margin: 0 4px; color: var(--border-color);">|</span> <i class="fas fa-graduation-cap" style="font-size: 0.7rem;"></i> ${safeStudentClass}` : ''}
                                    </div>
                                </div>
                            </div>
                        </td>
                        <td>
                            <span class="status-badge ${status}">${escapeHtml(statusLabel)}</span>
                            ${violationsCount > 0 ? `
                                <span class="badge badge-danger" style="margin-left: 0.5rem;" title="${violationsCount} pelanggaran">
                                    <i class="fas fa-triangle-exclamation"></i> ${violationsCount}
                                </span>
                            ` : ''}
                        </td>
                        <td>
                            <code style="font-size: 0.75rem; color: var(--text-secondary);" title="${safeDeviceInfo}">${safeShortDevice}</code>
                        </td>
                        <td>
                            ${allowRowActions ? `
                                <div class="monitor-row-actions">
                                    <button class="monitor-action-btn emergency"
                                            onclick="allowEmergencyExit(${sessionId}, ${safeStudentNameArg})"
                                            title="Izinkan keluar (bypass kiosk)">
                                        <i class="fas fa-door-open"></i>
                                    </button>
                                    <button class="monitor-action-btn kick"
                                            onclick="kickStudentFromExam(${sessionId}, ${safeStudentNameArg})"
                                            title="Keluarkan paksa dari ujian">
                                        <i class="fas fa-ban"></i>
                                    </button>
                                </div>
                            ` : `
                                <span style="color: var(--text-secondary); font-size: 0.75rem;">-</span>
                            `}
                        </td>
                    </tr>
                `;
            }).join('');
        }

        // Update last update time
        function updateLastUpdateTime() {
            const now = new Date();
            const timeStr = now.toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
            document.getElementById('last-update-time').textContent = `Diperbarui ${timeStr}`;
        }

        // Kick student from exam (terminate session)
        async function kickStudentFromExam(sessionId, studentName) {
            const confirmed = await showConfirm(
                `Keluarkan ${studentName} dari ujian?\n\nSiswa akan dipaksa keluar dan sesi ujian akan diakhiri.`,
                'Keluarkan Siswa',
                { type: 'danger', confirmText: 'Ya, Keluarkan', cancelText: 'Batal' }
            );

            if (!confirmed) return;

            try {
                // Use monitoring kick endpoint (accessible to teachers)
                const response = await fetch(`/api/monitoring/sessions/${sessionId}/kick`, {
                    method: 'POST',
                    headers: getAuthHeaders(),
                    body: JSON.stringify({ reason: 'Dikeluarkan oleh pengawas' })
                });

                if (response.ok) {
                    showAlert(`🚫 ${studentName} berhasil dikeluarkan dari ujian`, 'success');
                    loadSessionStatusData(); // Refresh data
                } else {
                    const error = await response.json();
                    showAlert(error.detail || 'Gagal mengeluarkan siswa', 'danger');
                }
            } catch (error) {
                console.error('[Modal] Failed to kick student:', error);
                showAlert('Terjadi kesalahan jaringan', 'danger');
            }
        }

        // Allow emergency exit (bypass kiosk mode)
        async function allowEmergencyExit(sessionId, studentName) {
            const confirmed = await showConfirm(
                `Izinkan ${studentName} keluar dari aplikasi?\n\nFitur ini digunakan jika aplikasi siswa macet dan perlu di-restart.\nSiswa tetap bisa melanjutkan ujian setelah masuk kembali.`,
                'Emergency Exit',
                { type: 'warning', confirmText: 'Ya, Izinkan Keluar', cancelText: 'Batal' }
            );

            if (!confirmed) return;

            try {
                const response = await fetch(`/api/exams/sessions/${sessionId}/emergency-exit`, {
                    method: 'POST',
                    headers: getAuthHeaders()
                });

                if (response.ok) {
                    showAlert(`🚨 Emergency exit diaktifkan untuk ${studentName}. Siswa dapat keluar dari aplikasi.`, 'success');
                    loadSessionStatusData(); // Refresh data
                } else {
                    const error = await response.json();
                    showAlert(error.detail || 'Gagal mengaktifkan emergency exit', 'danger');
                }
            } catch (error) {
                console.error('[Modal] Failed to enable emergency exit:', error);
                showAlert('Terjadi kesalahan jaringan', 'danger');
            }
        }

        // Cleanup sessions for current exam
        async function cleanupSessionsModal() {
            if (!currentExamIdForModal) return;

            const confirmed = await showConfirm(
                'Hapus semua sesi sementara untuk ujian ini?\n\nHanya sesi yang belum selesai (temporary sessions) yang akan dihapus.',
                'Cleanup Sesi',
                { type: 'warning', confirmText: 'Ya, Cleanup', cancelText: 'Batal' }
            );

            if (!confirmed) return;

            try {
                const response = await fetch(`/api/exams/${currentExamIdForModal}/cleanup-sessions`, {
                    method: 'POST',
                    headers: getAuthHeaders()
                });

                if (response.ok) {
                    const data = await response.json();
                    showAlert(`Cleanup selesai. ${data.cleaned_count || 0} sesi sementara dihapus, ${data.saved_count || 0} hasil ujian tersimpan.`, 'success');
                    loadSessionStatusData(); // Refresh data
                } else {
                    const error = await response.json();
                    showAlert(error.detail || 'Gagal cleanup sesi', 'danger');
                }
            } catch (error) {
                console.error('[Modal] Failed to cleanup sessions:', error);
                showAlert('Terjadi kesalahan jaringan', 'danger');
            }
        }
