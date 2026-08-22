        // ============== FULLSCREEN LIVE MONITOR ==============
        let fmSelectedExams = new Set();
        let fmWebSockets = {};
        let fmStudentsData = {};
        let fmViolationsHistory = [];
        let fmSoundEnabled = true;
        let fmDataRefreshInterval = null;
        let fmPingIntervals = {};
        let fmRefreshInFlight = false;

        function startFmRefreshLoop() {
            if (fmDataRefreshInterval) {
                clearInterval(fmDataRefreshInterval);
            }
            fmDataRefreshInterval = setInterval(
                () => {
                    if (!document.hidden) refreshFmData();
                },
                runtimePolicy.fullscreen_monitor_poll_interval_ms
            );
        }

        // Checkbox handler for exam selection
        function toggleExamSelection(examId, event) {
            event.stopPropagation(); // Don't trigger card click

            if (fmSelectedExams.has(examId)) {
                fmSelectedExams.delete(examId);
            } else {
                fmSelectedExams.add(examId);
            }

            updateLaunchButton();
        }

        function updateLaunchButton() {
            const btn = document.getElementById('fm-launch-btn');
            const countSpan = document.getElementById('fm-selected-count');

            countSpan.textContent = fmSelectedExams.size;

            if (fmSelectedExams.size > 0) {
                btn.classList.add('visible');
            } else {
                btn.classList.remove('visible');
            }
        }

        // Launch fullscreen monitor
        async function launchFullscreenMonitor() {
            if (fmSelectedExams.size === 0) {
                UIComponents.showToast('Pilih minimal 1 ujian untuk di-monitor', 'warning');
                return;
            }

            // Show overlay
            const overlay = document.getElementById('fullscreen-monitor');
            overlay.classList.add('active');

            // Clear previous data
            fmStudentsData = {};
            fmViolationsHistory = [];

            // Load data and connect WebSockets for each selected exam
            const examNames = [];
            for (const examId of fmSelectedExams) {
                // Connect WebSocket
                connectFmWebSocket(examId);

                // Load initial data
                try {
                    const sessions = await api.getExamSessions(examId);
                    examNames.push(sessions.exam_title || `Ujian #${examId}`);

                    // Merge students data
                    if (sessions.sessions) {
                        sessions.sessions.forEach(s => {
                            const studentKey = getMonitorStudentKey(examId, s.user_id);
                            fmStudentsData[studentKey] = {
                                ...s,
                                examId: examId,
                                examTitle: sessions.exam_title,
                                is_online: s.is_online ?? false
                            };
                        });
                    }

                    // Seed violations feed from persistent DB logs
                    await seedFmViolationHistoryFromDashboard(examId);
                } catch (e) {
                    console.error(`Failed to load exam ${examId}:`, e);
                }
            }

            // Update exam names in header
            document.getElementById('fm-exam-names').textContent = examNames.join(' | ');

            // Render initial data
            renderFmStudentGrid();
            updateFmStats();

            // Start periodic refresh as fallback
            startFmRefreshLoop();

            console.log('🖥️ Fullscreen Monitor launched for exams:', [...fmSelectedExams]);
        }

        async function seedFmViolationHistoryFromDashboard(examId) {
            try {
                const dashboard = await api.getViolationsDashboard(examId);
                const violations = Array.isArray(dashboard?.violations) ? dashboard.violations : [];
                const seeded = violations.slice(0, 80).map((item) => {
                    const meta = getViolationDisplayMeta(item);
                    return {
                        user_id: item.user_id,
                        exam_id: item.exam_id || examId,
                        username: item.name || item.username || 'Unknown',
                        type: meta.type,
                        label: meta.label,
                        severity: meta.severity,
                        description: meta.description,
                        count: item.violation_count || 1,
                        timestamp: item.created_at || new Date().toISOString()
                    };
                });
                fmViolationsHistory = [...seeded, ...fmViolationsHistory]
                    .sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp))
                    .slice(0, 120);
                renderFmViolationsFeed();
            } catch (error) {
                console.warn('Failed to seed fullscreen violation history:', error);
            }
        }

        // Close fullscreen monitor
        function closeFullscreenMonitor() {
            const overlay = document.getElementById('fullscreen-monitor');
            overlay.classList.remove('active');

            // Disconnect all WebSockets
            Object.values(fmWebSockets).forEach(ws => {
                if (ws && ws.readyState === WebSocket.OPEN) {
                    ws.close();
                }
            });
            fmWebSockets = {};
            Object.values(fmPingIntervals).forEach(intervalId => clearInterval(intervalId));
            fmPingIntervals = {};

            // Clear refresh interval
            if (fmDataRefreshInterval) {
                clearInterval(fmDataRefreshInterval);
                fmDataRefreshInterval = null;
            }

            console.log('🖥️ Fullscreen Monitor closed');
        }

        // Connect WebSocket for fullscreen monitor
        function connectFmWebSocket(examId) {
            if (fmWebSockets[examId]) {
                fmWebSockets[examId].close();
            }

            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = `${protocol}//${window.location.host}/ws/monitor/${examId}`;

            const wsToken = localStorage.getItem('access_token');
            const socket = new WebSocket(wsUrl + `?token=${wsToken}`);

            socket.onopen = () => {
                console.log(`✅ FM WebSocket connected for exam ${examId}`);
            };

            socket.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    handleFmRealtimeEvent(data, examId);
                } catch (e) {
                    console.error('FM WebSocket message error:', e);
                }
            };

            socket.onclose = () => {
                console.log(`⚠️ FM WebSocket disconnected for exam ${examId}`);
                // Auto-reconnect if monitor is still open
                if (document.getElementById('fullscreen-monitor').classList.contains('active')) {
                    setTimeout(() => connectFmWebSocket(examId), 3000);
                }
            };

            socket.onerror = (error) => {
                console.error('FM WebSocket error:', error);
            };

            fmWebSockets[examId] = socket;

            // Send ping every 25s
            if (fmPingIntervals[examId]) {
                clearInterval(fmPingIntervals[examId]);
            }
            fmPingIntervals[examId] = setInterval(() => {
                if (socket.readyState === WebSocket.OPEN) {
                    socket.send(JSON.stringify({ type: 'ping' }));
                }
            }, 25000);
        }

        // Handle real-time events in fullscreen monitor
        function handleFmRealtimeEvent(event, examId) {
            console.log('⚡ FM Event:', event.type, event);
            const studentKey = getFmStudentKeyFromEvent(event, examId);

            switch (event.type) {
                case 'student_connected':
                    if (fmStudentsData[studentKey]) {
                        fmStudentsData[studentKey].is_online = true;
                    }
                    updateFmStudentCard(studentKey);
                    updateFmStats();
                    break;

                case 'student_disconnected':
                    if (fmStudentsData[studentKey]) {
                        fmStudentsData[studentKey].is_online = false;
                    }
                    updateFmStudentCard(studentKey);
                    updateFmStats();
                    break;

                case 'progress_update':
                    if (fmStudentsData[studentKey]) {
                        fmStudentsData[studentKey].progress = event.progress || 0;
                        fmStudentsData[studentKey].is_online = true;
                    }
                    updateFmStudentCard(studentKey);
                    updateFmStats();
                    break;

                case 'violation':
                case 'violation_detected':
                    const violationMeta = getViolationDisplayMeta(event);
                    addFmViolation({
                        user_id: event.user_id,
                        exam_id: event.exam_id || examId,
                        username: event.username || fmStudentsData[studentKey]?.user_name || fmStudentsData[studentKey]?.username || 'Unknown',
                        type: violationMeta.type,
                        label: violationMeta.label,
                        severity: violationMeta.severity,
                        description: violationMeta.description,
                        count: event.violation_count || 1,
                        timestamp: event.timestamp || new Date().toISOString()
                    });

                    // Update student violation count
                    if (fmStudentsData[studentKey]) {
                        fmStudentsData[studentKey].violation_count = event.violation_count ||
                            (fmStudentsData[studentKey].violation_count || 0) + 1;
                        fmStudentsData[studentKey].is_online = true;
                    }
                    updateFmStudentCard(studentKey);
                    updateFmStats();
                    break;

                case 'student_submitted':
                    if (fmStudentsData[studentKey]) {
                        fmStudentsData[studentKey].status = 'submitted';
                    }
                    updateFmStudentCard(studentKey);
                    updateFmStats();
                    break;

                case 'student_started':
                    // Refresh data to get new student
                    refreshFmData();
                    break;
            }
        }

        // Render student grid
        function renderFmStudentGrid() {
            const grid = document.getElementById('fm-students-grid');
            const students = Object.values(fmStudentsData);

            if (students.length === 0) {
                grid.innerHTML = `
                    <div style="text-align: center; padding: 3rem; grid-column: 1 / -1;">
                        <i class="fas fa-user-slash" style="font-size: 3rem; color: #64748b; margin-bottom: 1rem;"></i>
                        <p style="color: #94a3b8;">Belum ada siswa yang mengikuti ujian</p>
                    </div>
                `;
                return;
            }

            // Sort: online first, then by violations (desc), then by name
            students.sort((a, b) => {
                const aOnline = a.is_online ?? a.isOnline ?? false;
                const bOnline = b.is_online ?? b.isOnline ?? false;
                if (aOnline !== bOnline) return bOnline ? 1 : -1;
                if ((b.violation_count || b.violations || 0) !== (a.violation_count || a.violations || 0)) return (b.violation_count || b.violations || 0) - (a.violation_count || a.violations || 0);
                return (a.user_name || a.username || '').localeCompare(b.user_name || b.username || '');
            });

            grid.innerHTML = students.map(student => createFmStudentCardHtml(student)).join('');
        }

        // Create HTML for a single student card
        function createFmStudentCardHtml(student) {
            const violations = student.violation_count || student.violations || 0;
            const progress = student.progress || 0;
            const isOnline = student.is_online ?? student.isOnline ?? false;
            const isSubmitted = student.status === 'submitted' || student.status === 'completed';

            let cardClass = 'fm-student-card';
            let dotClass = 'fm-student-status-dot';

            if (isSubmitted) {
                cardClass += ' submitted';
            } else if (violations >= 3) {
                cardClass += ' danger';
            } else if (violations > 0) {
                cardClass += ' warning';
            } else if (isOnline) {
                cardClass += ' online';
            } else {
                cardClass += ' offline';
            }

            dotClass += isOnline ? ' online' : ' offline';

            const displayName = student.user_name || student.full_name || student.username || 'Siswa';
            const initials = displayName
                .split(' ')
                .map(n => n[0])
                .slice(0, 2)
                .join('')
                .toUpperCase();

            const sessionId = student.id || student.session_id;
            const examId = student.examId || student.exam_id;
            const studentKey = getMonitorStudentKey(examId, student.user_id);

            return `
                <div id="${getMonitorStudentDomId(studentKey)}" class="${cardClass}" data-session-id="${sessionId}" data-exam-id="${examId}">
                    <div class="${dotClass}"></div>
                    <div class="fm-student-avatar">${initials}</div>
                    <div class="fm-student-name" title="${displayName}">${displayName}</div>
                    <div class="fm-student-progress">
                        <div class="fm-student-progress-bar" style="width: ${progress}%"></div>
                    </div>
                    <div class="fm-student-info">
                        <span>${progress}%</span>
                        <span class="fm-student-violations ${violations > 0 ? 'has-violations' : ''}">⚠️ ${violations}</span>
                    </div>
                    ${!isSubmitted ? `
                    <div class="fm-student-actions">
                        <button class="fm-action-btn submit" onclick="fmForceSubmit(${sessionId}, ${student.user_id}, ${examId})" title="Force Submit">
                            <i class="fas fa-paper-plane"></i>
                        </button>
                        <button class="fm-action-btn kick" onclick="fmForceKick(${sessionId}, '${displayName}', ${student.user_id}, ${examId})" title="Force Kick">
                            <i class="fas fa-user-slash"></i>
                        </button>
                    </div>
                    ` : `
                    <div class="fm-student-submitted">
                        <i class="fas fa-check-circle"></i> Selesai
                    </div>
                    `}
                </div>
            `;
        }

        // Update single student card
        function updateFmStudentCard(studentKey) {
            const student = fmStudentsData[studentKey];
            if (!student) return;

            const existingCard = document.getElementById(getMonitorStudentDomId(studentKey));
            if (existingCard) {
                existingCard.outerHTML = createFmStudentCardHtml(student);
            }
        }

        // Update stats bar
        function updateFmStats() {
            const students = Object.values(fmStudentsData);

            document.getElementById('fm-stat-total').textContent = students.length;
            document.getElementById('fm-stat-online').textContent =
                students.filter(s => (s.is_online ?? s.isOnline ?? false) && s.status !== 'submitted').length;
            document.getElementById('fm-stat-violations').textContent =
                students.reduce((sum, s) => sum + (s.violation_count || s.violations || 0), 0);
            document.getElementById('fm-stat-submitted').textContent =
                students.filter(s => s.status === 'submitted' || s.status === 'completed').length;
        }

        // Force submit from fullscreen monitor
        async function fmForceSubmit(sessionId, userId, examId) {
            console.log('🔴 [DEBUG] fmForceSubmit called:', { sessionId, userId, examId });

            if (!sessionId) {
                UIComponents.showToast('Session ID tidak valid', 'danger');
                return;
            }

            const confirmed = await showConfirmDialog(
                'Force Submit Ujian',
                'Apakah Anda yakin ingin mengumpulkan ujian siswa ini?',
                'Ya, Submit',
                'btn-warning'
            );

            if (!confirmed) return;

            try {
                // Send via WebSocket to all connected exam sockets
                let wsSent = false;
                Object.values(fmWebSockets).forEach(ws => {
                    if (ws.readyState === WebSocket.OPEN) {
                        const wsMessage = {
                            type: 'force_submit',
                            user_id: userId,  // CRITICAL: Backend needs user_id to route to student
                            session_id: sessionId,
                            reason: 'Dikumpulkan paksa oleh pengawas'
                        };
                        console.log('🔴 [DEBUG] Sending WebSocket force_submit:', wsMessage);
                        ws.send(JSON.stringify(wsMessage));
                        wsSent = true;
                    }
                });

                if (wsSent) {
                    await new Promise(resolve => setTimeout(resolve, 2500));
                }

                // Also call REST endpoint so server status is authoritative
                // even when student's WebSocket is offline.
                let restOk = false;
                try {
                    const response = await fetch(`/api/exams/sessions/${sessionId}/force-submit`, {
                        method: 'POST',
                        headers: getAuthHeaders()
                    });
                    restOk = response.ok;
                    if (!response.ok) {
                        const error = await response.json().catch(() => ({}));
                        console.warn('🔴 [DEBUG] Force-submit REST failed:', error);
                    }
                } catch (e) {
                    console.warn('🔴 [DEBUG] Force-submit REST error:', e);
                }

                if (restOk) {
                    UIComponents.showToast('Ujian siswa berhasil di-force submit', 'success');
                } else {
                    UIComponents.showToast(
                        wsSent ? 'Perintah force submit dikirim (WebSocket)' : 'Force submit belum terkonfirmasi',
                        wsSent ? 'warning' : 'danger'
                    );
                }

                // Refresh data after a short delay
                setTimeout(() => refreshFmData(), 1000);
            } catch (error) {
                console.error('Force submit error:', error);
                UIComponents.showToast('Gagal mengirim perintah', 'danger');
            }
        }

        // Force kick from fullscreen monitor
        async function fmForceKick(sessionId, studentName, userId, examId) {
            console.log('🔴 [DEBUG] fmForceKick called:', { sessionId, studentName, userId, examId });

            if (!sessionId) {
                UIComponents.showToast('Session ID tidak valid', 'danger');
                return;
            }

            const confirmed = await showConfirmDialog(
                'Force Kick Siswa',
                `Apakah Anda yakin ingin mengeluarkan <strong>${studentName}</strong> dari ujian?<br><br><span style="color: #ef4444;">⚠️ Tindakan ini tidak dapat dibatalkan!</span>`,
                'Ya, Keluarkan',
                'btn-danger'
            );

            if (!confirmed) return;

            try {
                // Send via WebSocket first (for immediate response)
                Object.values(fmWebSockets).forEach(ws => {
                    if (ws.readyState === WebSocket.OPEN) {
                        const wsMessage = {
                            type: 'force_kick',
                            user_id: userId,  // CRITICAL: Backend needs user_id, not session_id
                            session_id: sessionId,
                            reason: 'Dikeluarkan oleh pengawas'
                        };
                        console.log('🔴 [DEBUG] Sending WebSocket force_kick:', wsMessage);
                        ws.send(JSON.stringify(wsMessage));
                    }
                });

                // Also send via REST API as backup
                const response = await fetch(`/api/monitoring/sessions/${sessionId}/kick`, {
                    method: 'POST',
                    headers: getAuthHeaders(),
                    body: JSON.stringify({ reason: 'Dikeluarkan oleh pengawas' })
                });

                if (response.ok) {
                    UIComponents.showToast(`${studentName} telah dikeluarkan dari ujian`, 'success');
                } else {
                    UIComponents.showToast('Perintah kick dikirim via WebSocket', 'info');
                }

                // Refresh data after a short delay
                setTimeout(() => refreshFmData(), 1000);
            } catch (error) {
                console.error('Force kick error:', error);
                UIComponents.showToast('Gagal mengirim perintah kick', 'danger');
            }
        }
        function addFmViolation(violation) {
            // Add to history (max 50 items)
            fmViolationsHistory.unshift(violation);
            if (fmViolationsHistory.length > 50) {
                fmViolationsHistory.pop();
            }

            // Play sound if enabled
            if (fmSoundEnabled) {
                playViolationSound();
            }

            // Render
            renderFmViolationsFeed();
        }

        // Render violations feed
        function renderFmViolationsFeed() {
            const container = document.getElementById('fm-violations-list');

            if (fmViolationsHistory.length === 0) {
                container.innerHTML = `
                    <div style="text-align: center; padding: 2rem; color: #64748b;">
                        <i class="fas fa-shield-check" style="font-size: 2rem; margin-bottom: 0.5rem;"></i>
                        <p>Belum ada pelanggaran</p>
                    </div>
                `;
                return;
            }

            // Severity color mapping
            const severityColors = {
                'critical': { bg: 'rgba(220, 38, 38, 0.2)', border: '#dc2626', text: '#fca5a5', badge: '#dc2626' },
                'high': { bg: 'rgba(245, 158, 11, 0.2)', border: '#f59e0b', text: '#fcd34d', badge: '#f59e0b' },
                'medium': { bg: 'rgba(59, 130, 246, 0.2)', border: '#3b82f6', text: '#93c5fd', badge: '#3b82f6' },
                'low': { bg: 'rgba(34, 197, 94, 0.2)', border: '#22c55e', text: '#86efac', badge: '#22c55e' }
            };

            container.innerHTML = fmViolationsHistory.map(v => {
                const time = v.timestamp ? new Date(v.timestamp).toLocaleTimeString('id-ID') : '-';
                const vInfo = getViolationDisplayMeta(v);
                const colors = severityColors[vInfo.severity] || severityColors['medium'];

                return `
                    <div class="fm-violation-item" style="background: ${colors.bg}; border-left: 3px solid ${colors.border}; padding: 0.75rem; margin-bottom: 0.5rem; border-radius: 6px;">
                        <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 0.25rem;">
                            <div class="fm-violation-name" style="font-weight: 600; color: #fff;">${v.username}</div>
                            <span style="background: ${colors.badge}; color: #fff; font-size: 0.65rem; padding: 2px 6px; border-radius: 4px; text-transform: uppercase;">
                                ${vInfo.severity}
                            </span>
                        </div>
                        <div class="fm-violation-type" style="display: flex; align-items: center; gap: 0.5rem; color: ${colors.text}; font-weight: 500;">
                            <i class="fas ${formatViolationType(vInfo.type).icon}"></i>
                            ${vInfo.label}
                            <span style="background: rgba(255,255,255,0.2); padding: 1px 6px; border-radius: 10px; font-size: 0.75rem;">×${v.count}</span>
                        </div>
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 0.35rem;">
                            <div style="font-size: 0.7rem; color: #94a3b8;">${vInfo.description}</div>
                            <div class="fm-violation-time" style="font-size: 0.7rem; color: #64748b;">${time}</div>
                        </div>
                    </div>
                `;
            }).join('');
        }

        // Format violation type for display with comprehensive mapping
        function formatViolationType(type) {
            // Normalize type to lowercase for matching
            const normalizedType = (type || '').toLowerCase().replace('violation_', '');

            // Comprehensive violation type mapping with icons, severity, and descriptions
            const violationMap = {
                // PC/Browser violations
                'tab_switch': { label: 'Pindah Tab', icon: 'fa-window-restore', severity: 'medium', desc: 'Berpindah tab browser' },
                'window_blur': { label: 'Fokus Hilang', icon: 'fa-eye-slash', severity: 'medium', desc: 'Jendela kehilangan fokus' },
                'copy': { label: 'Copy', icon: 'fa-copy', severity: 'high', desc: 'Menyalin teks' },
                'paste': { label: 'Paste', icon: 'fa-paste', severity: 'high', desc: 'Menempelkan teks' },
                'cut': { label: 'Cut', icon: 'fa-scissors', severity: 'medium', desc: 'Memotong teks' },
                'screenshot': { label: 'Screenshot', icon: 'fa-camera', severity: 'high', desc: 'Tangkapan layar' },
                'screenshot_attempt': { label: 'Screenshot', icon: 'fa-mobile-screen', severity: 'high', desc: 'Percobaan screenshot' },
                'browser_minimize': { label: 'Minimize', icon: 'fa-window-minimize', severity: 'low', desc: 'Browser diminimize' },
                'focus_lost': { label: 'Fokus Hilang', icon: 'fa-eye-slash', severity: 'medium', desc: 'Jendela kehilangan fokus' },
                'devtools_open': { label: 'Dev Tools', icon: 'fa-code', severity: 'critical', desc: 'Membuka inspect element' },
                'devtools_attempt': { label: 'Dev Tools', icon: 'fa-code', severity: 'critical', desc: 'Percobaan membuka inspect element' },
                'right_click': { label: 'Klik Kanan', icon: 'fa-arrow-pointer', severity: 'low', desc: 'Klik kanan mouse' },
                'clipboard_violation': { label: 'Copy/Paste', icon: 'fa-clipboard', severity: 'high', desc: 'Akses clipboard' },
                'copy_paste_attempt': { label: 'Copy/Paste', icon: 'fa-clipboard', severity: 'high', desc: 'Percobaan akses clipboard' },
                'context_menu_attempt': { label: 'Klik Kanan', icon: 'fa-arrow-pointer', severity: 'low', desc: 'Percobaan membuka menu konteks' },
                'window_resize_suspicious': { label: 'Resize Mencurigakan', icon: 'fa-up-right-and-down-left-from-center', severity: 'medium', desc: 'Perubahan ukuran jendela mencurigakan' },

                // Mobile/Android violations (from Flutter APK)
                'overlay_app': { label: 'Overlay App', icon: 'fa-layer-group', severity: 'critical', desc: 'Aplikasi floating terdeteksi' },
                'screen_recording': { label: 'Rekam Layar', icon: 'fa-video', severity: 'critical', desc: 'Screen recording aktif' },
                'external_display': { label: 'Display Eksternal', icon: 'fa-tv', severity: 'high', desc: 'HDMI/USB/Miracast' },
                'accessibility_risk': { label: 'Aksesibilitas', icon: 'fa-universal-access', severity: 'high', desc: 'Auto-clicker/bot terdeteksi' },
                'apk_tampering': { label: 'APK Dimodifikasi', icon: 'fa-shield-halved', severity: 'critical', desc: 'APK tidak resmi' },
                'security_warning': { label: 'Peringatan', icon: 'fa-triangle-exclamation', severity: 'medium', desc: 'Masalah keamanan' }
            };

            return violationMap[normalizedType] || {
                label: type.replace(/_/g, ' ').replace(/violation/gi, '').trim() || 'Pelanggaran',
                icon: 'fa-exclamation-triangle',
                severity: 'medium',
                desc: 'Pelanggaran terdeteksi'
            };
        }

        // Toggle violation sound
        function toggleViolationSound() {
            fmSoundEnabled = !fmSoundEnabled;
            const btn = document.getElementById('fm-sound-btn');

            if (fmSoundEnabled) {
                btn.classList.add('active');
                btn.innerHTML = '<i class="fas fa-volume-high"></i> Suara';
            } else {
                btn.classList.remove('active');
                btn.innerHTML = '<i class="fas fa-volume-xmark"></i> Muted';
            }
        }

        // Play violation sound - enhanced version
        function playViolationSound() {
            try {
                const audio = document.getElementById('violation-sound');
                if (audio) {
                    audio.volume = 1.0; // Max volume
                    audio.currentTime = 0;

                    // Try to play with promise handling
                    const playPromise = audio.play();
                    if (playPromise !== undefined) {
                        playPromise.catch(e => {
                            console.log('⚠️ Audio autoplay blocked, trying Web Audio API fallback');
                            // Fallback: Generate beep using Web Audio API
                            playBeepFallback();
                        });
                    }
                } else {
                    // No audio element, use fallback
                    playBeepFallback();
                }
            } catch (e) {
                console.error('Audio error:', e);
                playBeepFallback();
            }
        }

        // Web Audio API fallback for notification beep
        function playBeepFallback() {
            try {
                const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
                const oscillator = audioCtx.createOscillator();
                const gainNode = audioCtx.createGain();

                oscillator.connect(gainNode);
                gainNode.connect(audioCtx.destination);

                oscillator.frequency.value = 800; // Frequency in Hz
                oscillator.type = 'sine';
                gainNode.gain.value = 0.5;

                oscillator.start();

                // Beep pattern: on-off-on
                setTimeout(() => gainNode.gain.value = 0, 150);
                setTimeout(() => gainNode.gain.value = 0.5, 200);
                setTimeout(() => oscillator.stop(), 400);
            } catch (e) {
                console.log('Web Audio API not available');
            }
        }

        // Refresh fullscreen monitor data
        async function refreshFmData() {
            if (fmRefreshInFlight) return;
            fmRefreshInFlight = true;

            try {
                const examIds = Array.from(fmSelectedExams);
                if (examIds.length === 0) {
                    fmStudentsData = {};
                    renderFmStudentGrid();
                    updateFmStats();
                    return;
                }

                const seenKeys = new Set();
                const changedKeys = new Set();
                let hasStructuralChange = false;

                const responses = await Promise.all(
                    examIds.map(async (examId) => {
                        try {
                            const sessions = await api.getExamSessions(examId);
                            return { examId, sessions };
                        } catch (error) {
                            console.error(`Failed to refresh exam ${examId}:`, error);
                            return null;
                        }
                    })
                );

                responses
                    .filter(Boolean)
                    .forEach(({ examId, sessions }) => {
                        const rows = Array.isArray(sessions?.sessions) ? sessions.sessions : [];
                        rows.forEach((s) => {
                            const studentKey = getMonitorStudentKey(examId, s.user_id);
                            seenKeys.add(studentKey);
                            const existing = fmStudentsData[studentKey];
                            const existingOnline = existing?.is_online ?? existing?.isOnline;
                            const merged = {
                                ...s,
                                examId: examId,
                                examTitle: sessions?.exam_title,
                                is_online: existingOnline !== undefined ? existingOnline : (s.is_online ?? false)
                            };

                            if (!existing) {
                                hasStructuralChange = true;
                                fmStudentsData[studentKey] = merged;
                                return;
                            }

                            fmStudentsData[studentKey] = merged;
                            if (
                                existing.progress !== merged.progress ||
                                existing.violation_count !== merged.violation_count ||
                                existing.status !== merged.status ||
                                (existing.is_online ?? existing.isOnline) !== merged.is_online
                            ) {
                                changedKeys.add(studentKey);
                            }
                        });
                    });

                Object.keys(fmStudentsData).forEach((studentKey) => {
                    const [rawExamId] = String(studentKey).split(':');
                    const examId = Number(rawExamId);
                    if (!fmSelectedExams.has(examId) || !seenKeys.has(studentKey)) {
                        delete fmStudentsData[studentKey];
                        hasStructuralChange = true;
                    }
                });

                if (hasStructuralChange) {
                    renderFmStudentGrid();
                } else {
                    changedKeys.forEach((studentKey) => updateFmStudentCard(studentKey));
                }
                updateFmStats();
            } finally {
                fmRefreshInFlight = false;
            }
        }

        // Override renderSessions to add checkbox
        const originalRenderSessions = renderSessions;
        renderSessions = function (sessions, options = {}) {
            const container = document.getElementById('sessions-container');
            const summaryMode = !!options.summaryMode;
            const sourceList = Array.isArray(sessions) ? sessions : [];
            const examGroups = {};
            let totalActive = 0;
            let totalCompleted = 0;
            let totalViolations = 0;

            if (summaryMode) {
                sourceList.forEach((exam) => {
                    const examId = exam?.id;
                    if (!examId) return;
                    const group = {
                        exam,
                        sessions: [],
                        totalSessions: Number(exam.total_sessions ?? 0),
                        totalActive: Number(exam.in_progress_count ?? exam.active_participants ?? 0),
                        totalCompleted: Number(exam.completed_count ?? exam.completed_participants ?? 0),
                        totalViolations: Number(exam.total_violations ?? 0)
                    };
                    examGroups[examId] = group;
                    totalActive += group.totalActive;
                    totalCompleted += group.totalCompleted;
                    totalViolations += group.totalViolations;
                });
            } else {
                sourceList.forEach((s) => {
                    const examId = s?.exam?.id;
                    if (!examId) return;
                    if (!examGroups[examId]) {
                        examGroups[examId] = {
                            exam: s.exam,
                            sessions: [],
                            totalSessions: 0,
                            totalActive: 0,
                            totalViolations: 0,
                            totalCompleted: 0
                        };
                    }
                    const group = examGroups[examId];
                    group.sessions.push(s);
                    group.totalSessions += 1;
                    if (s.status === 'in_progress') {
                        group.totalActive += 1;
                        totalActive += 1;
                    }
                    if (s.status === 'completed' || s.status === 'submitted') {
                        group.totalCompleted += 1;
                        totalCompleted += 1;
                    }
                    const violations = Number(s.violation_count || s.violations || 0);
                    group.totalViolations += violations;
                    totalViolations += violations;
                });
            }

            document.getElementById('total-active').textContent = totalActive;
            document.getElementById('total-violations').textContent = totalViolations;
            document.getElementById('total-completed').textContent = totalCompleted;

            if (sourceList.length === 0) {
                container.innerHTML = `
                    <div style="text-align: center; padding: 3rem;">
                        <i class="fas fa-satellite-dish" style="font-size: 3rem; color: var(--text-secondary); margin-bottom: 1rem;"></i>
                        <h3 style="margin-bottom: 0.5rem; color: white;">Tidak Ada Sesi Aktif</h3>
                        <p style="color: var(--text-secondary); margin-bottom: 1.5rem;">Belum ada peserta yang sedang mengerjakan ujian saat ini.</p>
                    </div>
                `;
                return;
            }

            container.innerHTML = `
                <div style="display: grid; gap: 1rem;">
                    ${Object.values(examGroups).map(group => {
                const violationClass = group.totalViolations > 5 ? 'danger' : group.totalViolations > 0 ? 'warning' : '';
                const isChecked = fmSelectedExams.has(group.exam.id);

                return `
                            <div class="card session-card ${violationClass}" style="padding: 1.5rem; cursor: pointer;">
                                <div class="exam-checkbox-wrapper">
                                    <input type="checkbox"
                                           class="exam-checkbox"
                                           id="checkbox-exam-${group.exam.id}"
                                           ${isChecked ? 'checked' : ''}
                                           onclick="toggleExamSelection(${group.exam.id}, event)"
                                           title="Pilih untuk Live Monitor">
                                </div>
                                <div onclick="openSessionStatusModal(${group.exam.id})"
                                     style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 1.5rem; padding-left: 2.5rem;">
                                    <div style="flex: 1; min-width: 200px;">
                                        <div style="display: flex; align-items: center; gap: 1rem; margin-bottom: 0.75rem;">
                                            <i class="fas fa-file-lines" style="font-size: 1.5rem; color: var(--primary);"></i>
                                            <div>
                                                <strong style="font-size: 1.1rem; color: white;">${group.exam.title}</strong>
                                                <div style="font-size: 0.75rem; color: var(--text-secondary); margin-top: 0.25rem;">
                                                    <i class="fas fa-clock"></i> ${formatWIB(group.exam.start_time)}
                                                </div>
                                            </div>
                                        </div>
                                    </div>

                                    <div style="display: flex; gap: 2rem; flex-wrap: wrap;">
                                        <div style="text-align: center;">
                                            <div style="font-size: 0.75rem; color: var(--text-secondary); margin-bottom: 0.25rem;">Total Sesi</div>
                                            <strong style="font-size: 1.5rem; color: white;">${group.totalSessions}</strong>
                                        </div>
                                        <div style="text-align: center;">
                                            <div style="font-size: 0.75rem; color: var(--text-secondary); margin-bottom: 0.25rem;">Sedang Ujian</div>
                                            <strong style="font-size: 1.5rem; color: var(--success);">${group.totalActive}</strong>
                                        </div>
                                        <div style="text-align: center;">
                                            <div style="font-size: 0.75rem; color: var(--text-secondary); margin-bottom: 0.25rem;">Selesai</div>
                                            <strong style="font-size: 1.5rem; color: var(--info);">${group.totalCompleted}</strong>
                                        </div>
                                        <div style="text-align: center;">
                                            <div style="font-size: 0.75rem; color: var(--text-secondary); margin-bottom: 0.25rem;">Pelanggaran</div>
                                            <span class="badge badge-${group.totalViolations > 2 ? 'danger' : group.totalViolations > 0 ? 'warning' : 'success'}" style="font-size: 1.25rem; padding: 0.5rem 0.75rem;">
                                                ${group.totalViolations}
                                            </span>
                                        </div>
                                    </div>
                                </div>

                                <div style="margin-top: 1rem; padding-top: 1rem; border-top: 1px solid var(--border-color); display: flex; align-items: center; gap: 0.5rem; font-size: 0.85rem; color: var(--text-secondary); padding-left: 2.5rem;">
                                    <i class="fas fa-circle-info"></i>
                                    Centang untuk Live Monitor • Gunakan tombol aksi untuk kontrol cepat
                                </div>
                            </div>
                        `;
            }).join('')}
                </div>
            `;

            // Update launch button state
            updateLaunchButton();
        };
        // ============== END FULLSCREEN LIVE MONITOR ==============

        // Expose handlers explicitly for inline onclick bindings.
        // This avoids silent failures when browser scope behavior differs.
        if (typeof window !== 'undefined') {
            Object.assign(window, {
                refreshData,
                loadOpsSummary,
                toggleAutoRestartFromOps,
                openOpsAutoRestartModal,
                closeOpsAutoRestartModal,
                saveOpsAutoRestartSchedule,
                addOpsAutoRestartScheduleRow,
                removeOpsAutoRestartScheduleRow,
                updateOpsAutoRestartScheduleRow,
                toggleAutoModeFromOps,
                toggleAutoHealingFromOps,
                runAutoHealingNowFromOps,
                restartSystemSafelyFromOps,
                toggleExamPause,
                openSessionStatusModal,
                closeSessionStatusModal,
                cleanupSessionsModal,
                openStudentDetailModal,
                closeStudentDetailModal,
                resetStudentSession,
                forceSubmitStudent,
                forceKickStudent,
                kickStudentFromExam,
                allowEmergencyExit,
                launchFullscreenMonitor,
                closeFullscreenMonitor,
                toggleExamSelection,
                toggleViolationSound,
                fmForceSubmit,
                fmForceKick
            });
        }

        // Cleanup on page leave
        window.addEventListener('beforeunload', () => {
            clearInterval(refreshInterval);
            if (policyRefreshInterval) {
                clearInterval(policyRefreshInterval);
            }
            stopPauseTimer();
            if (studentDetailUpdateInterval) {
                clearInterval(studentDetailUpdateInterval);
            }
            // Close fullscreen monitor if open
            closeFullscreenMonitor();
        });
