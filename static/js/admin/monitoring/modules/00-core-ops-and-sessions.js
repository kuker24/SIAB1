        if (!auth.requireAuth(['admin', 'developer', 'teacher', 'gurupengawas'])) {
            throw new Error('AUTH_REQUIRED');
        }

        let refreshInterval;
        let currentExamIdForModal = null;
        let modalUpdateInterval = null;
        let currentStudentIdForModal = null;
        let studentDetailUpdateInterval = null;
        let policyRefreshInterval = null;
        let runtimePolicy = {
            admin_refresh_interval_ms: 10000,
            monitor_modal_poll_interval_ms: 15000,
            student_detail_poll_interval_ms: 10000,
            fullscreen_monitor_poll_interval_ms: 10000
        };

        let currentUser = auth.getUser();
        const isTeacher = currentUser && currentUser.role === 'teacher';
        const isPengawas = currentUser && currentUser.role === 'gurupengawas';
        const hideOpsSummary = isTeacher || isPengawas;
        const monitorQueryParams = new URLSearchParams(window.location.search || '');
        const requestedMonitorExamId = Number.parseInt(
            String(monitorQueryParams.get('exam_id') || ''),
            10
        );
        const autoOpenMonitorRequested = monitorQueryParams.get('auto_open') === '1';
        let monitorQueryConsumed = false;
        let opsSummaryState = null;
        let opsAutoRestartToggleInFlight = false;
        let opsAutoControlInFlight = false;
        let opsAutoHealRunInFlight = false;
        let opsRestartInFlight = false;
        let opsAutoRestartDraftRows = [];
        let opsSummaryInFlight = false;
        let opsSummaryForceQueued = false;
        let refreshDataInFlight = false;
        let refreshQueuedWhileHidden = false;
        let lastVisibleRefreshAt = 0;
        const VISIBLE_REFRESH_MIN_GAP_MS = 5000;

        function applyRoleScopedVisibility() {
            const opsCardEl = document.getElementById('ops-summary-card');
            if (!opsCardEl) return;
            if (hideOpsSummary) {
                opsCardEl.remove();
                return;
            }
            opsCardEl.style.display = '';
        }

        const OPS_METRIC_LABELS = {
            status_code: 'HTTP',
            cf_ray: 'CF Ray',
            latency_ms: 'Latency',
            global_5xx_percent: '5xx (1m)',
            max_critical_p95_ms: 'Max p95',
            origin_status_code: 'Origin HTTP',
            origin_latency_ms: 'Origin Latency',
            connection_percent_used: 'DB Conn',
            slow_queries: 'Slow Query',
            db_pool_timeout_per_min: 'DB Timeout',
            blocked_clients: 'Blocked',
            redis_timeout_per_min: 'Redis Timeout',
            cache_hit_ratio_percent: 'Cache Hit',
            cache_hit_ratio_lifetime_percent: 'Cache Hit Lifetime',
            cache_lookup_window_seconds: 'Window',
            cache_ratio_source: 'Ratio Src',
            cache_eval_enabled: 'Cache Eval',
            memory_percent_used_of_maxmemory: 'Redis Memory',
            instantaneous_ops_per_sec: 'Redis OPS',
            redis_stability_score_percent: 'Redis Stability',
            cpu_percent: 'CPU',
            memory_percent: 'RAM',
            disk_percent: 'Disk'
        };

        function escapeHtml(value) {
            return String(value ?? '')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#39;');
        }

        function formatOpsMetricValue(key, value) {
            if (value === null || value === undefined || value === '') return '-';
            if (typeof value === 'boolean') return value ? 'Yes' : 'No';
            if (key === 'cache_ratio_source') return String(value).toUpperCase();
            const num = Number(value);
            if (!Number.isFinite(num)) return String(value);
            if (key.includes('percent')) return `${num.toFixed(2)}%`;
            if (key.endsWith('_ms') || key.includes('latency')) return `${num.toFixed(2)} ms`;
            if (key.endsWith('per_min')) return `${num.toFixed(2)}/min`;
            return `${num}`;
        }

        function opsStatusClass(status) {
            switch (String(status || '').toLowerCase()) {
                case 'healthy':
                    return 'healthy';
                case 'warning':
                    return 'warning';
                case 'critical':
                    return 'critical';
                default:
                    return 'unknown';
            }
        }

        function opsStatusLabel(status) {
            const normalized = String(status || '').toLowerCase();
            if (normalized === 'healthy') return 'Healthy';
            if (normalized === 'warning') return 'Warning';
            if (normalized === 'critical') return 'Critical';
            return 'Unknown';
        }

        function getAutoRestartVisual(isEnabled, state) {
            if (!isEnabled) {
                return { chipClass: 'warning', chipLabel: 'OFF' };
            }
            const normalized = String(state || 'scheduled').toLowerCase();
            if (normalized === 'idle') return { chipClass: 'warning', chipLabel: 'ON • IDLE' };
            if (normalized === 'due') return { chipClass: 'warning', chipLabel: 'ON • DUE' };
            if (normalized === 'scheduled') return { chipClass: 'healthy', chipLabel: 'ON • SCHEDULED' };
            if (normalized === 'running') return { chipClass: 'warning', chipLabel: 'ON • RUNNING' };
            if (normalized === 'success') return { chipClass: 'healthy', chipLabel: 'ON • OK' };
            if (normalized === 'blocked') return { chipClass: 'warning', chipLabel: 'ON • BLOCKED' };
            if (normalized === 'failed') return { chipClass: 'critical', chipLabel: 'ON • FAILED' };
            return { chipClass: 'unknown', chipLabel: `ON • ${normalized.toUpperCase()}` };
        }

        function getRestartBackendVisual(summary) {
            const restartBackend = summary && typeof summary === 'object'
                ? (summary.restart_backend || {})
                : {};
            const fullRestartAvailable = !!restartBackend.full_restart_available;
            return {
                fullRestartAvailable,
                label: fullRestartAvailable ? 'Restart Full Antar Sesi' : 'Reset Runtime Antar Sesi',
                pendingLabel: fullRestartAvailable ? 'Restarting Full...' : 'Resetting Runtime...',
                confirmTitle: fullRestartAvailable ? 'Restart Full Antar Sesi' : 'Reset Runtime Antar Sesi',
                confirmText: fullRestartAvailable ? 'Ya, Restart' : 'Ya, Reset',
                confirmBody: fullRestartAvailable
                    ? 'Jalankan RESTART FULL antar sesi?\nSemua service utama Docker akan di-restart. Sistem hanya jalan jika tidak ada ujian/sesi aktif dan tidak ada jadwal dekat.'
                    : 'Full restart backend belum dikonfigurasi aman pada API ini.\nJalankan RESET RUNTIME antar sesi saja?\nMode ini tetap aman: cache runtime dibersihkan, mode dipaksa kembali ke NORMAL, tanpa akses host Docker.',
                note: fullRestartAvailable
                    ? 'Restart antar sesi FULL tersedia dari panel ini.'
                    : 'Full restart backend belum dikonfigurasi aman. Tombol restart akan menjalankan reset runtime antar sesi.',
                hint: String(restartBackend.hint || '').trim(),
            };
        }

        function getDefaultOpsAutoRestartParts(offsetMinutes = 10) {
            const value = new Date(Date.now() + offsetMinutes * 60 * 1000).toLocaleString('sv-SE', {
                timeZone: 'Asia/Jakarta',
                year: 'numeric',
                month: '2-digit',
                day: '2-digit',
                hour: '2-digit',
                minute: '2-digit',
                hour12: false
            });
            const match = String(value || '').match(/^(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})/);
            return {
                date: match ? match[1] : '',
                time: match ? match[2] : '00:30'
            };
        }

        function extractOpsAutoRestartParts(value) {
            const raw = String(value || '').trim();
            const direct = raw.match(/^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2})/);
            if (direct) {
                return { date: direct[1], time: direct[2] };
            }
            return getDefaultOpsAutoRestartParts();
        }

        function shiftOpsAutoRestartParts(parts, offsetMinutes = 30) {
            const base = new Date(`${parts?.date || ''}T${parts?.time || '00:30'}:00+07:00`);
            if (Number.isNaN(base.getTime())) {
                return getDefaultOpsAutoRestartParts(offsetMinutes);
            }
            const value = new Date(base.getTime() + offsetMinutes * 60 * 1000).toLocaleString('sv-SE', {
                timeZone: 'Asia/Jakarta',
                year: 'numeric',
                month: '2-digit',
                day: '2-digit',
                hour: '2-digit',
                minute: '2-digit',
                hour12: false
            });
            const match = String(value || '').match(/^(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})/);
            return {
                date: match ? match[1] : parts?.date || '',
                time: match ? match[2] : parts?.time || '00:30'
            };
        }

        function seedOpsAutoRestartDraftRows() {
            const autoRestart = opsSummaryState?.auto_restart || {};
            const entries = Array.isArray(autoRestart.entries) ? autoRestart.entries : [];
            const pendingEntries = entries.filter(entry => String(entry?.status || '').toLowerCase() === 'pending');
            opsAutoRestartDraftRows = pendingEntries.map((entry) => {
                const parts = extractOpsAutoRestartParts(entry?.scheduled_at_wib || entry?.scheduled_at_utc);
                return {
                    id: String(entry?.id || `${Date.now()}_${Math.random()}`),
                    date: parts.date,
                    time: parts.time
                };
            });
            if (opsAutoRestartDraftRows.length === 0) {
                const parts = getDefaultOpsAutoRestartParts();
                opsAutoRestartDraftRows = [{
                    id: `draft_${Date.now()}`,
                    date: parts.date,
                    time: parts.time
                }];
            }
        }

        function renderOpsAutoRestartScheduleRows() {
            const listEl = document.getElementById('ops-auto-restart-schedule-list');
            if (!listEl) return;

            if (!Array.isArray(opsAutoRestartDraftRows) || opsAutoRestartDraftRows.length === 0) {
                listEl.innerHTML = `
                    <div class="auto-restart-empty">
                        Belum ada jadwal pending. Klik <strong>Tambah Jadwal</strong> untuk membuat jadwal baru.
                    </div>
                `;
                return;
            }

            listEl.innerHTML = opsAutoRestartDraftRows.map((row, index) => `
                <div class="auto-restart-schedule-row">
                    <div class="auto-restart-field">
                        <label>Tanggal WIB</label>
                        <input type="date" value="${escapeHtml(row.date)}"
                            onchange="updateOpsAutoRestartScheduleRow(${index}, 'date', this.value)">
                    </div>
                    <div class="auto-restart-field">
                        <label>Jam WIB</label>
                        <input type="time" value="${escapeHtml(row.time)}" step="60"
                            onchange="updateOpsAutoRestartScheduleRow(${index}, 'time', this.value)">
                    </div>
                    <button type="button" class="btn btn-outline-danger"
                        onclick="removeOpsAutoRestartScheduleRow(${index})">
                        <i class="fas fa-trash"></i> Hapus
                    </button>
                </div>
            `).join('');
        }

        function updateOpsAutoRestartScheduleRow(index, field, value) {
            if (!opsAutoRestartDraftRows[index]) return;
            opsAutoRestartDraftRows[index][field] = String(value || '').trim();
        }

        function addOpsAutoRestartScheduleRow() {
            const lastRow = opsAutoRestartDraftRows[opsAutoRestartDraftRows.length - 1];
            const parts = lastRow && lastRow.date && lastRow.time
                ? shiftOpsAutoRestartParts(lastRow, 30)
                : getDefaultOpsAutoRestartParts(20);
            opsAutoRestartDraftRows.push({
                id: `draft_${Date.now()}_${opsAutoRestartDraftRows.length}`,
                date: parts.date,
                time: parts.time
            });
            renderOpsAutoRestartScheduleRows();
        }

        function removeOpsAutoRestartScheduleRow(index) {
            opsAutoRestartDraftRows = opsAutoRestartDraftRows.filter((_, rowIndex) => rowIndex !== index);
            renderOpsAutoRestartScheduleRows();
        }

        function showOverlayModal(modalEl) {
            if (!modalEl) return;
            modalEl.style.display = 'flex';
            modalEl.style.alignItems = 'center';
            modalEl.style.justifyContent = 'center';
            modalEl.classList.add('active');
            modalEl.setAttribute('aria-hidden', 'false');
            const modalCard = modalEl.querySelector('.modal');
            if (modalCard) {
                modalCard.style.position = 'relative';
                modalCard.style.left = 'auto';
                modalCard.style.right = 'auto';
                modalCard.style.top = 'auto';
                modalCard.style.margin = '0 auto';
            }
        }

        function hideOverlayModal(modalEl) {
            if (!modalEl) return;
            modalEl.classList.remove('active');
            modalEl.style.display = 'none';
            modalEl.setAttribute('aria-hidden', 'true');
        }

        function openOpsAutoRestartModal() {
            const modalEl = document.getElementById('ops-auto-restart-modal');
            const modeChipEl = document.getElementById('ops-auto-restart-mode-chip');
            const modeHintEl = document.getElementById('ops-auto-restart-mode-hint');
            const restartBackendVisual = getRestartBackendVisual(opsSummaryState);

            seedOpsAutoRestartDraftRows();
            renderOpsAutoRestartScheduleRows();

            if (modeChipEl) {
                modeChipEl.className = `auto-restart-mode-chip ${restartBackendVisual.fullRestartAvailable ? 'full' : 'soft'}`;
                modeChipEl.textContent = restartBackendVisual.fullRestartAvailable
                    ? 'FULL RESTART ANTAR SESI'
                    : 'RESET RUNTIME ANTAR SESI';
            }
            if (modeHintEl) {
                modeHintEl.textContent = restartBackendVisual.fullRestartAvailable
                    ? 'Scheduler ini akan menjalankan jalur full restart antar sesi yang sama dengan tombol restart full di Monitoring Inti Sistem.'
                    : 'Backend full restart belum tersedia, jadi scheduler akan memakai reset runtime antar sesi yang aman.';
            }
            syncOpsAutoRestartModalActionState();
            if (modalEl) {
                showOverlayModal(modalEl);
            }
        }

        function closeOpsAutoRestartModal() {
            const modalEl = document.getElementById('ops-auto-restart-modal');
            hideOverlayModal(modalEl);
        }

        function collectOpsAutoRestartScheduleItems() {
            if (!Array.isArray(opsAutoRestartDraftRows) || opsAutoRestartDraftRows.length === 0) {
                throw new Error('Tambahkan minimal satu jadwal auto restart.');
            }

            const normalized = opsAutoRestartDraftRows.map((row, index) => {
                const date = String(row?.date || '').trim();
                const time = String(row?.time || '').trim();
                if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) {
                    throw new Error(`Tanggal pada baris ${index + 1} belum valid.`);
                }
                if (!/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(time)) {
                    throw new Error(`Jam pada baris ${index + 1} belum valid.`);
                }
                return `${date} ${time}`;
            });

            const unique = [];
            const seen = new Set();
            normalized.forEach((item) => {
                if (seen.has(item)) return;
                seen.add(item);
                unique.push(item);
            });
            unique.sort();
            return unique;
        }

        function syncOpsAutoRestartModalActionState() {
            const saveBtn = document.getElementById('ops-auto-restart-save-btn');
            if (!saveBtn) return;
            saveBtn.disabled = opsAutoRestartToggleInFlight;
            saveBtn.innerHTML = opsAutoRestartToggleInFlight
                ? '<i class="fas fa-spinner fa-spin"></i> Menyimpan...'
                : '<i class="fas fa-floppy-disk"></i> Simpan Jadwal';
        }

        function formatOpsTime(isoString) {
            if (!isoString) return '-';
            const date = new Date(isoString);
            if (Number.isNaN(date.getTime())) return '-';
            return date.toLocaleString('id-ID', {
                timeZone: 'Asia/Jakarta',
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit'
            });
        }

        function renderOpsSummary(summary) {
            opsSummaryState = summary || null;

            const overallEl = document.getElementById('ops-overall-status');
            const resourceModeEl = document.getElementById('ops-resource-mode-status');
            const autoRestartEl = document.getElementById('ops-auto-restart-status');
            const updatedEl = document.getElementById('ops-updated-at');
            const messageEl = document.getElementById('ops-summary-message');
            const resourceNotesEl = document.getElementById('ops-resource-mode-notes');
            const autoRestartDetailEl = document.getElementById('ops-autorestart-detail');
            const layerGridEl = document.getElementById('ops-layer-grid');
            const hintsEl = document.getElementById('ops-hints-list');
            const autoRestartToggleBtn = document.getElementById('ops-toggle-auto-restart-btn');
            const autoModeBtn = document.getElementById('ops-auto-mode-btn');
            const autoHealBtn = document.getElementById('ops-auto-heal-btn');
            const autoHealRunBtn = document.getElementById('ops-auto-heal-run-btn');
            const restartBtn = document.getElementById('ops-restart-safe-btn');

            if (!summary || typeof summary !== 'object') {
                if (messageEl) messageEl.textContent = 'Data ops belum tersedia.';
                return;
            }

            const overallStatus = opsStatusClass(summary.status);
            if (overallEl) {
                overallEl.className = `ops-chip ${overallStatus}`;
                overallEl.textContent = `Overall: ${opsStatusLabel(summary.status)}`;
            }

            const resourceMode = String(summary?.policy?.resource_mode || 'normal').toLowerCase();
            const autoRestart = summary.auto_restart || {};
            const autoRestartStatus = autoRestart.status || {};
            const autoRestartEnabled = !!autoRestart.enabled;
            const autoRestartVisual = getAutoRestartVisual(autoRestartEnabled, autoRestartStatus.state);
            const restartBackendVisual = getRestartBackendVisual(summary);
            const autoIntel = summary.auto_intelligence || {};
            const autoIntelControls = autoIntel.controls || {};
            const autoIntelRuntime = autoIntel.runtime || {};
            const autoIntelDecision = autoIntelRuntime.last_mode_decision || {};
            const autoIntelHeal = autoIntelRuntime.last_heal || {};
            const autoModeEnabled = !!autoIntelControls.auto_mode_enabled;
            const autoHealEnabled = !!autoIntelControls.auto_heal_enabled;
            if (resourceModeEl) {
                let modeClass = 'healthy';
                if (resourceMode === 'high') modeClass = 'warning';
                if (resourceMode === 'extreme') modeClass = 'critical';
                resourceModeEl.className = `ops-chip ${modeClass}`;
                resourceModeEl.textContent = `Mode: ${resourceMode.toUpperCase()} • ${autoModeEnabled ? 'AUTO' : 'MANUAL'}`;
            }
            if (autoRestartEl) {
                autoRestartEl.className = `ops-chip ${autoRestartVisual.chipClass}`;
                autoRestartEl.textContent = `Auto Restart WIB: ${autoRestartVisual.chipLabel}`;
            }

            if (updatedEl) {
                updatedEl.textContent = `Update ${formatOpsTime(summary.updated_at)}`;
            }

            const keyMetrics = summary.key_metrics || {};
            if (messageEl) {
                const g5xx = formatOpsMetricValue('global_5xx_percent', keyMetrics.global_5xx_percent);
                const cpu = formatOpsMetricValue('cpu_percent', keyMetrics.cpu_percent);
                const dbConn = formatOpsMetricValue('db_connection_percent', keyMetrics.db_connection_percent);
                const redisStability = formatOpsMetricValue(
                    'redis_stability_score_percent',
                    keyMetrics.redis_stability_score_percent
                );
                messageEl.textContent = `5xx ${g5xx} • CPU ${cpu} • DB Conn ${dbConn} • Redis Stability ${redisStability}`;
            }
            if (resourceNotesEl) {
                const modeLabel = summary?.policy?.resource_mode_label || resourceMode.toUpperCase();
                const modeDescription = summary?.policy?.resource_mode_description || 'Mode resource aktif.';
                const delayed = Array.isArray(summary?.policy?.delayed_features)
                    ? summary.policy.delayed_features
                    : [];
                const decisionConfidence = Number(autoIntelDecision.confidence);
                const confidenceText = Number.isFinite(decisionConfidence)
                    ? `${(decisionConfidence * 100).toFixed(1)}%`
                    : '-';
                const decisionScore = Number(autoIntelDecision.score);
                const scoreText = Number.isFinite(decisionScore) ? decisionScore.toFixed(1) : '-';
                const decisionTarget = String(autoIntelDecision.target_mode || resourceMode || '-').toUpperCase();
                const decisionReasons = Array.isArray(autoIntelDecision.reasons) ? autoIntelDecision.reasons : [];
                const healStatus = String(autoIntelHeal.status || 'idle').toUpperCase();
                const healSummary = String(autoIntelHeal.summary || 'Belum ada aksi healing');
                const healTime = formatOpsTime(autoIntelHeal.at);
                const delayedText = delayed.length > 0
                    ? `Fitur terdampak: ${delayed.join(' • ')}`
                    : 'Tidak ada fitur yang dibatasi.';
                resourceNotesEl.innerHTML = `
                    <div><strong>Mode ${escapeHtml(modeLabel)}:</strong> ${escapeHtml(modeDescription)}</div>
                    <div>${escapeHtml(delayedText)}</div>
                    <div><strong>Auto Performa:</strong> ${autoModeEnabled ? 'ON' : 'OFF'} • Target ${escapeHtml(decisionTarget)} • Score ${escapeHtml(scoreText)} • Confidence ${escapeHtml(confidenceText)}</div>
                    <div><strong>Alasan Auto:</strong> ${escapeHtml(decisionReasons.slice(0, 3).join(' • ') || 'Belum ada evaluasi')}</div>
                    <div><strong>Auto Healing:</strong> ${autoHealEnabled ? 'ON' : 'OFF'} • Status ${escapeHtml(healStatus)} • ${escapeHtml(healSummary)} • ${escapeHtml(healTime)}</div>
                    <div>${escapeHtml(restartBackendVisual.note)}</div>
                `;
            }
            if (autoRestartDetailEl) {
                const summaryText = autoRestartStatus.summary || (autoRestartEnabled
                    ? 'Auto restart terjadwal aktif.'
                    : 'Auto restart terjadwal nonaktif.');
                const scheduleMode = autoRestart.full_restart !== false
                    ? 'Full Restart Antar Sesi'
                    : 'Reset Runtime Antar Sesi';
                const nextRun = formatWIB(
                    autoRestartStatus.next_run_at_wib || autoRestartStatus.next_run_at_utc,
                    { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }
                );
                const lastTriggered = formatOpsTime(autoRestartStatus.last_triggered_at);
                const lastResult = formatOpsTime(autoRestartStatus.last_result_at);
                const stateText = String(autoRestartStatus.state || 'disabled').toUpperCase();
                const errorText = autoRestartStatus.last_error ? String(autoRestartStatus.last_error) : '';
                const entries = Array.isArray(autoRestart.entries) ? autoRestart.entries : [];
                const pendingEntries = entries.filter(entry => String(entry?.status || '').toLowerCase() === 'pending');
                const pendingHtml = pendingEntries.length > 0
                    ? pendingEntries
                        .slice(0, 8)
                        .map((entry) => {
                            const when = formatWIB(entry?.scheduled_at_wib || entry?.scheduled_at_utc, {
                                day: '2-digit',
                                month: '2-digit',
                                year: 'numeric',
                                hour: '2-digit',
                                minute: '2-digit'
                            });
                            return `<li>${escapeHtml(when)} WIB</li>`;
                        })
                        .join('')
                    : '<li>Tidak ada jadwal pending.</li>';
                autoRestartDetailEl.innerHTML = `
                    <div><strong>Status:</strong> ${escapeHtml(summaryText)}</div>
                    <div><strong>State:</strong> ${escapeHtml(stateText)} • <strong>Pending:</strong> ${escapeHtml(String(autoRestartStatus.pending_count ?? pendingEntries.length))}</div>
                    <div><strong>Mode:</strong> ${escapeHtml(scheduleMode)} • <strong>Backend:</strong> ${escapeHtml(restartBackendVisual.label)}</div>
                    <div><strong>Next Run:</strong> ${escapeHtml(nextRun)} • <strong>Last Trigger:</strong> ${escapeHtml(lastTriggered)}</div>
                    <div><strong>Last Result:</strong> ${escapeHtml(lastResult)} • <strong>Buffer:</strong> ${escapeHtml(String(autoRestart.restart_buffer_minutes ?? '-'))} menit</div>
                    <div><strong>Daftar Jadwal WIB:</strong><ul style="margin: 0.35rem 0 0 1rem;">${pendingHtml}</ul></div>
                    ${errorText ? `<div><strong>Error:</strong> ${escapeHtml(errorText)}</div>` : ''}
                `;
            }

            if (autoRestartToggleBtn) {
                autoRestartToggleBtn.disabled = hideOpsSummary || opsAutoRestartToggleInFlight || opsAutoControlInFlight || opsRestartInFlight || opsAutoHealRunInFlight;
                autoRestartToggleBtn.innerHTML = opsAutoRestartToggleInFlight
                    ? '<i class="fas fa-spinner fa-spin"></i> Menyimpan Jadwal...'
                    : '<i class="fas fa-calendar-plus"></i> Jadwalkan Auto Restart';
            }
            if (autoModeBtn) {
                autoModeBtn.disabled = hideOpsSummary || opsAutoControlInFlight || opsRestartInFlight || opsAutoRestartToggleInFlight || opsAutoHealRunInFlight;
                autoModeBtn.classList.remove('btn-primary', 'btn-outline-success', 'btn-outline-warning');
                autoModeBtn.classList.add(autoModeEnabled ? 'btn-primary' : 'btn-outline-success');
                autoModeBtn.innerHTML = opsAutoControlInFlight
                    ? '<i class="fas fa-spinner fa-spin"></i> Menyimpan...'
                    : `<i class="fas fa-brain"></i> Auto Performa: ${autoModeEnabled ? 'ON' : 'OFF'}`;
            }
            if (autoHealBtn) {
                autoHealBtn.disabled = hideOpsSummary || opsAutoControlInFlight || opsRestartInFlight || opsAutoRestartToggleInFlight || opsAutoHealRunInFlight;
                autoHealBtn.classList.remove('btn-primary', 'btn-outline-info', 'btn-outline-secondary');
                autoHealBtn.classList.add(autoHealEnabled ? 'btn-primary' : 'btn-outline-info');
                autoHealBtn.innerHTML = opsAutoControlInFlight
                    ? '<i class="fas fa-spinner fa-spin"></i> Menyimpan...'
                    : `<i class="fas fa-heart-pulse"></i> Auto Healing: ${autoHealEnabled ? 'ON' : 'OFF'}`;
            }
            if (autoHealRunBtn) {
                autoHealRunBtn.disabled = hideOpsSummary || opsAutoControlInFlight || opsRestartInFlight || opsAutoRestartToggleInFlight || opsAutoHealRunInFlight || !autoHealEnabled;
                autoHealRunBtn.innerHTML = opsAutoHealRunInFlight
                    ? '<i class="fas fa-spinner fa-spin"></i> Menjalankan...'
                    : '<i class="fas fa-wand-magic-sparkles"></i> Heal Sekarang';
            }
            if (restartBtn) {
                restartBtn.disabled = hideOpsSummary || opsRestartInFlight || opsAutoControlInFlight || opsAutoRestartToggleInFlight || opsAutoHealRunInFlight;
                restartBtn.classList.remove('btn-danger', 'btn-outline-warning');
                restartBtn.classList.add(
                    restartBackendVisual.fullRestartAvailable ? 'btn-danger' : 'btn-outline-warning'
                );
                restartBtn.innerHTML = opsRestartInFlight
                    ? `<i class="fas fa-spinner fa-spin"></i> ${escapeHtml(restartBackendVisual.pendingLabel)}`
                    : `<i class="fas fa-power-off"></i> ${escapeHtml(restartBackendVisual.label)}`;
                restartBtn.title = restartBackendVisual.fullRestartAvailable
                    ? 'Restart penuh antar sesi'
                    : (restartBackendVisual.hint || restartBackendVisual.note);
            }

            const layers = Array.isArray(summary.layers) ? summary.layers : [];
            if (layerGridEl) {
                layerGridEl.innerHTML = layers.map(layer => {
                    const metrics = layer.metrics || {};
                    const metricKeys = Object.keys(metrics).slice(0, 4);
                    const metricsHtml = metricKeys.length > 0
                        ? metricKeys.map(key => `
                            <div class="ops-metric-item">
                                <span class="ops-metric-label">${escapeHtml(OPS_METRIC_LABELS[key] || key)}</span>
                                <span class="ops-metric-value">${escapeHtml(formatOpsMetricValue(key, metrics[key]))}</span>
                            </div>
                        `).join('')
                        : '<div class="ops-metric-item"><span class="ops-metric-label">No metric</span><span class="ops-metric-value">-</span></div>';

                    return `
                        <div class="ops-layer-card">
                            <div class="ops-layer-title">
                                <span>${escapeHtml(layer.label || layer.id || 'Layer')}</span>
                                <span class="ops-chip ${opsStatusClass(layer.status)}">${opsStatusLabel(layer.status)}</span>
                            </div>
                            <div class="ops-layer-summary">${escapeHtml(layer.summary || '-')}</div>
                            <div class="ops-metric-list">${metricsHtml}</div>
                        </div>
                    `;
                }).join('');
            }

            const hints = Array.isArray(summary.hints) ? summary.hints : [];
            if (hintsEl) {
                hintsEl.innerHTML = hints.length > 0
                    ? hints.map(hint => `<li>${escapeHtml(hint)}</li>`).join('')
                    : '<li>Tidak ada hint.</li>';
            }
        }

        async function loadOpsSummary(force = false) {
            if (opsSummaryInFlight) {
                opsSummaryForceQueued = opsSummaryForceQueued || !!force;
                return;
            }
            opsSummaryInFlight = true;

            const cardEl = document.getElementById('ops-summary-card');
            const messageEl = document.getElementById('ops-summary-message');
            const autoRestartToggleBtn = document.getElementById('ops-toggle-auto-restart-btn');
            const autoModeBtn = document.getElementById('ops-auto-mode-btn');
            const autoHealBtn = document.getElementById('ops-auto-heal-btn');
            const autoHealRunBtn = document.getElementById('ops-auto-heal-run-btn');
            const restartBtn = document.getElementById('ops-restart-safe-btn');

            if (hideOpsSummary) {
                if (cardEl) cardEl.remove();
                return;
            }
            if (cardEl) cardEl.style.display = '';
            if (autoRestartToggleBtn) autoRestartToggleBtn.style.display = '';
            if (autoModeBtn) autoModeBtn.style.display = '';
            if (autoHealBtn) autoHealBtn.style.display = '';
            if (autoHealRunBtn) autoHealRunBtn.style.display = '';
            if (restartBtn) restartBtn.style.display = '';

            try {
                if (messageEl && force) {
                    messageEl.textContent = 'Memuat ulang ringkasan monitoring...';
                }
                let summary;
                if (api && typeof api.getOpsSummary === 'function') {
                    summary = await api.getOpsSummary();
                } else {
                    summary = await apiRequest('/api/monitoring/system/ops-summary', 'GET');
                }
                renderOpsSummary(summary);
            } catch (error) {
                const message = error?.message || String(error);
                if (messageEl) {
                    messageEl.textContent = `Gagal memuat ops summary: ${message}`;
                }
                if (cardEl) {
                    cardEl.style.borderColor = 'rgba(239, 68, 68, 0.35)';
                }
            } finally {
                opsSummaryInFlight = false;
                if (opsSummaryForceQueued) {
                    opsSummaryForceQueued = false;
                    loadOpsSummary(true);
                }
            }
        }

        async function toggleAutoRestartFromOps() {
            if (hideOpsSummary || opsAutoRestartToggleInFlight) return;
            if (!opsSummaryState || !opsSummaryState.policy) {
                showAlert('Status ops belum siap, coba refresh dulu', 'warning');
                return;
            }
            openOpsAutoRestartModal();
        }

        async function saveOpsAutoRestartSchedule() {
            if (hideOpsSummary || opsAutoRestartToggleInFlight) return;
            if (!opsSummaryState || !opsSummaryState.policy) {
                showAlert('Status ops belum siap, coba refresh dulu', 'warning');
                return;
            }

            const autoRestart = opsSummaryState.auto_restart || {};
            const restartBackendVisual = getRestartBackendVisual(opsSummaryState);
            try {
                const rawItems = collectOpsAutoRestartScheduleItems();
                const message = `Simpan ${rawItems.length} jadwal restart one-off WIB?\nDaftar pending sebelumnya akan diganti dengan daftar baru ini.`;
                const confirmed = await showConfirm(message, {
                    title: 'Simpan Jadwal Auto Restart',
                    type: 'info',
                    confirmText: 'Simpan Jadwal',
                    cancelText: 'Batal'
                });
                if (!confirmed) return;

                opsAutoRestartToggleInFlight = true;
                syncOpsAutoRestartModalActionState();
                const payload = {
                    enabled: true,
                    time_wib: String(autoRestart.time_wib || opsSummaryState?.policy?.auto_restart_time_wib || '00:30'),
                    restart_buffer_minutes: Number(autoRestart.restart_buffer_minutes || 30),
                    full_restart: restartBackendVisual.fullRestartAvailable,
                    include_data_services: restartBackendVisual.fullRestartAvailable,
                    restart_timeout_seconds: restartBackendVisual.fullRestartAvailable
                        ? Number(autoRestart.restart_timeout_seconds || 300)
                        : 120,
                    scheduled_runs_wib: rawItems.map(item => item.replace(/\s+/, ' ')),
                    replace_runs: true,
                    reason: `Sinkronkan ${rawItems.length} jadwal auto restart WIB dari dashboard monitoring`
                };
                if (api && typeof api.setAutoRestartSchedule === 'function') {
                    await api.setAutoRestartSchedule(payload);
                } else {
                    await apiRequest('/api/monitoring/system/auto-restart-schedule', 'POST', payload);
                }
                await loadRuntimePolicy();
                startMainRefreshLoop();
                await loadOpsSummary(true);
                closeOpsAutoRestartModal();
                showAlert(`${rawItems.length} jadwal auto restart berhasil disimpan`, 'success');
            } catch (error) {
                showAlert(`Gagal menyimpan jadwal auto restart: ${error?.message || error}`, 'danger');
            } finally {
                opsAutoRestartToggleInFlight = false;
                syncOpsAutoRestartModalActionState();
            }
        }

        async function toggleAutoModeFromOps() {
            if (hideOpsSummary || opsAutoControlInFlight) return;
            const controls = opsSummaryState?.auto_intelligence?.controls || {};
            const currentEnabled = !!controls.auto_mode_enabled;
            const nextEnabled = !currentEnabled;

            const confirmed = await showConfirm(
                nextEnabled
                    ? 'Aktifkan Auto Performa?\nSistem akan memilih mode Normal/High/Extreme secara cerdas berdasarkan kondisi realtime.'
                    : 'Nonaktifkan Auto Performa?\nMode saat ini akan dipertahankan sampai diubah manual oleh sistem lain.',
                {
                    title: 'Auto Performa',
                    type: nextEnabled ? 'info' : 'warning',
                    confirmText: nextEnabled ? 'Aktifkan' : 'Nonaktifkan',
                    cancelText: 'Batal'
                }
            );
            if (!confirmed) return;

            opsAutoControlInFlight = true;
            try {
                const payload = {
                    auto_mode_enabled: nextEnabled,
                    reason: nextEnabled
                        ? 'Auto performa diaktifkan dari Monitoring Inti Sistem'
                        : 'Auto performa dinonaktifkan dari Monitoring Inti Sistem',
                    force_tick: true
                };
                if (api && typeof api.updateAutoIntelligenceControl === 'function') {
                    await api.updateAutoIntelligenceControl(payload);
                } else {
                    await apiRequest('/api/monitoring/system/auto-intelligence', 'POST', payload);
                }
                await loadRuntimePolicy();
                startMainRefreshLoop();
                await loadOpsSummary(true);
                showAlert(`Auto Performa ${nextEnabled ? 'aktif' : 'nonaktif'}`, 'success');
            } catch (error) {
                showAlert(`Gagal update Auto Performa: ${error?.message || error}`, 'danger');
            } finally {
                opsAutoControlInFlight = false;
            }
        }

        async function toggleAutoHealingFromOps() {
            if (hideOpsSummary || opsAutoControlInFlight) return;
            const controls = opsSummaryState?.auto_intelligence?.controls || {};
            const currentEnabled = !!controls.auto_heal_enabled;
            const nextEnabled = !currentEnabled;

            const confirmed = await showConfirm(
                nextEnabled
                    ? 'Aktifkan Auto Healing?\nSaat backend API down/degradasi, sistem akan menjalankan healing aman otomatis.'
                    : 'Nonaktifkan Auto Healing?\nSistem tidak akan menjalankan command healing otomatis.',
                {
                    title: 'Auto Healing',
                    type: nextEnabled ? 'info' : 'warning',
                    confirmText: nextEnabled ? 'Aktifkan' : 'Nonaktifkan',
                    cancelText: 'Batal'
                }
            );
            if (!confirmed) return;

            opsAutoControlInFlight = true;
            try {
                const payload = {
                    auto_heal_enabled: nextEnabled,
                    reason: nextEnabled
                        ? 'Auto healing diaktifkan dari Monitoring Inti Sistem'
                        : 'Auto healing dinonaktifkan dari Monitoring Inti Sistem',
                    force_tick: true
                };
                if (api && typeof api.updateAutoIntelligenceControl === 'function') {
                    await api.updateAutoIntelligenceControl(payload);
                } else {
                    await apiRequest('/api/monitoring/system/auto-intelligence', 'POST', payload);
                }
                await loadRuntimePolicy();
                startMainRefreshLoop();
                await loadOpsSummary(true);
                showAlert(`Auto Healing ${nextEnabled ? 'aktif' : 'nonaktif'}`, 'success');
            } catch (error) {
                showAlert(`Gagal update Auto Healing: ${error?.message || error}`, 'danger');
            } finally {
                opsAutoControlInFlight = false;
            }
        }

        async function runAutoHealingNowFromOps() {
            if (hideOpsSummary || opsAutoHealRunInFlight) return;
            const controls = opsSummaryState?.auto_intelligence?.controls || {};
            if (!controls.auto_heal_enabled) {
                showAlert('Auto Healing masih OFF. Aktifkan dulu.', 'warning');
                return;
            }

            const confirmed = await showConfirm(
                'Jalankan Auto Healing sekarang?\nSistem akan menjalankan prosedur healing backend API yang aman.',
                {
                    title: 'Heal Sekarang',
                    type: 'warning',
                    confirmText: 'Jalankan',
                    cancelText: 'Batal'
                }
            );
            if (!confirmed) return;

            opsAutoHealRunInFlight = true;
            try {
                let response;
                if (api && typeof api.runAutoIntelligence === 'function') {
                    response = await api.runAutoIntelligence(
                        'Manual heal now dari Monitoring Inti Sistem',
                        true,
                        true
                    );
                } else {
                    response = await apiRequest('/api/monitoring/system/auto-intelligence/run', 'POST', {
                        reason: 'Manual heal now dari Monitoring Inti Sistem',
                        force: true,
                        force_heal: true
                    });
                }
                await loadRuntimePolicy();
                startMainRefreshLoop();
                await loadOpsSummary(true);
                const healSummary = response?.tick?.healing?.summary || 'Auto healing dieksekusi.';
                showAlert(healSummary, 'success');
            } catch (error) {
                showAlert(`Gagal menjalankan auto healing: ${error?.message || error}`, 'danger');
            } finally {
                opsAutoHealRunInFlight = false;
            }
        }

        async function restartSystemSafelyFromOps() {
            if (hideOpsSummary || opsRestartInFlight || opsAutoControlInFlight || opsAutoHealRunInFlight) return;
            const restartBackendVisual = getRestartBackendVisual(opsSummaryState);

            const confirmed = await showConfirm(
                restartBackendVisual.confirmBody,
                {
                    title: restartBackendVisual.confirmTitle,
                    type: 'warning',
                    confirmText: restartBackendVisual.confirmText,
                    cancelText: 'Batal'
                }
            );
            if (!confirmed) return;

            opsRestartInFlight = true;
            try {
                let result;
                if (api && typeof api.restartSystemSafely === 'function') {
                    result = await api.restartSystemSafely(
                        restartBackendVisual.fullRestartAvailable
                            ? 'Manual FULL restart antar sesi dari Monitoring Inti Sistem'
                            : 'Manual runtime reset antar sesi dari Monitoring Inti Sistem',
                        30,
                        false,
                        restartBackendVisual.fullRestartAvailable,
                        restartBackendVisual.fullRestartAvailable,
                        restartBackendVisual.fullRestartAvailable ? 300 : 120
                    );
                } else {
                    result = await apiRequest('/api/monitoring/system/restart-safe', 'POST', {
                        reason: restartBackendVisual.fullRestartAvailable
                            ? 'Manual FULL restart antar sesi dari Monitoring Inti Sistem'
                            : 'Manual runtime reset antar sesi dari Monitoring Inti Sistem',
                        restart_buffer_minutes: 30,
                        full_restart: restartBackendVisual.fullRestartAvailable,
                        include_data_services: restartBackendVisual.fullRestartAvailable,
                        restart_timeout_seconds: restartBackendVisual.fullRestartAvailable ? 300 : 120,
                        dry_run: false
                    });
                }
                await loadRuntimePolicy();
                startMainRefreshLoop();
                await loadOpsSummary(true);
                const restarted = result?.full_restart?.services_restarted || [];
                if (restartBackendVisual.fullRestartAvailable) {
                    showAlert(
                        `Restart FULL selesai. Redis key dibersihkan: ${result?.redis_deleted_keys || 0}. Service di-restart: ${restarted.length}`,
                        'success'
                    );
                } else {
                    showAlert(
                        `Reset runtime selesai. Redis key dibersihkan: ${result?.redis_deleted_keys || 0}. Mode sistem kembali ke NORMAL.`,
                        'success'
                    );
                }
            } catch (error) {
                const detail = error?.detail || error?.message || String(error);
                if (typeof detail === 'object') {
                    const message = detail.message
                        || detail.hint
                        || `Guard gagal (aktif: ${detail.active_sessions_count || 0}, berjalan: ${detail.running_exams_count || 0}, terjadwal dekat: ${detail.upcoming_exams_count || 0})`;
                    showAlert(message, 'warning');
                } else {
                    showAlert(`Restart diblokir/gagal: ${detail}`, 'warning');
                }
            } finally {
                opsRestartInFlight = false;
            }
        }

        // ========================================
        // TIMEZONE FORMATTER (WIB - Asia/Jakarta)
        // ========================================
        function formatWIB(dateString, options = {}) {
            if (!dateString) return '-';
            const date = new Date(dateString);
            const defaultOptions = {
                timeZone: 'Asia/Jakarta',
                day: 'numeric',
                month: 'short',
                year: 'numeric',
                hour: '2-digit',
                minute: '2-digit'
            };
            return date.toLocaleString('id-ID', { ...defaultOptions, ...options });
        }
        // ========================================

        // Helper function to get auth headers
        function getAuthHeaders() {
            const token = localStorage.getItem('access_token');
            return {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            };
        }

        function clampIntervalMs(value, fallback, min = 3000, max = 120000) {
            const parsed = Number(value);
            if (!Number.isFinite(parsed)) return fallback;
            return Math.min(max, Math.max(min, parsed));
        }

        async function loadRuntimePolicy() {
            try {
                const policy = await api.getRuntimePolicy();
                if (!policy || typeof policy !== 'object') return;

                runtimePolicy.admin_refresh_interval_ms = clampIntervalMs(
                    policy.admin_refresh_interval_ms,
                    runtimePolicy.admin_refresh_interval_ms,
                    10000,
                    30000
                );
                runtimePolicy.monitor_modal_poll_interval_ms = clampIntervalMs(
                    policy.monitor_modal_poll_interval_ms,
                    runtimePolicy.monitor_modal_poll_interval_ms,
                    15000,
                    60000
                );
                runtimePolicy.student_detail_poll_interval_ms = clampIntervalMs(
                    policy.student_detail_poll_interval_ms,
                    runtimePolicy.student_detail_poll_interval_ms,
                    10000,
                    60000
                );
                runtimePolicy.fullscreen_monitor_poll_interval_ms = clampIntervalMs(
                    policy.fullscreen_monitor_poll_interval_ms,
                    runtimePolicy.fullscreen_monitor_poll_interval_ms,
                    10000,
                    60000
                );
            } catch (error) {
                console.warn('Runtime policy fetch failed, fallback to defaults:', error?.message || error);
            }
        }

        function runIfVisible(task) {
            if (document.hidden) {
                refreshQueuedWhileHidden = true;
                return;
            }
            task();
        }

        function refreshSummaryOnceWhenVisible() {
            if (document.hidden) return;
            const now = Date.now();
            if ((now - lastVisibleRefreshAt) < VISIBLE_REFRESH_MIN_GAP_MS) return;
            lastVisibleRefreshAt = now;
            refreshQueuedWhileHidden = false;
            refreshData();
        }

        function startMainRefreshLoop() {
            if (refreshInterval) {
                clearInterval(refreshInterval);
            }
            refreshInterval = setInterval(
                () => runIfVisible(refreshData),
                runtimePolicy.admin_refresh_interval_ms
            );
        }

        function startModalRefreshLoop() {
            if (modalUpdateInterval) {
                clearInterval(modalUpdateInterval);
            }
            modalUpdateInterval = setInterval(
                () => runIfVisible(loadSessionStatusData),
                runtimePolicy.monitor_modal_poll_interval_ms
            );
        }

        function startStudentDetailRefreshLoop() {
            if (studentDetailUpdateInterval) {
                clearInterval(studentDetailUpdateInterval);
            }
            studentDetailUpdateInterval = setInterval(
                () => runIfVisible(loadStudentDetailData),
                runtimePolicy.student_detail_poll_interval_ms
            );
        }

        function normalizeExamSummary(exam) {
            const activeParticipants = Number(exam?.active_participants ?? exam?.in_progress_count ?? 0);
            const completedParticipants = Number(exam?.completed_count ?? exam?.completed_participants ?? 0);
            const totalSessions = Number(exam?.total_sessions ?? (activeParticipants + completedParticipants));
            return {
                ...exam,
                active_participants: activeParticipants,
                in_progress_count: activeParticipants,
                completed_count: completedParticipants,
                completed_participants: completedParticipants,
                total_sessions: totalSessions,
                total_violations: Number(exam?.total_violations ?? 0)
            };
        }

        async function loadActiveExams() {
            try {
                const payload = await api.getActiveExams();
                const activeExams = (Array.isArray(payload?.active_exams) ? payload.active_exams : [])
                    .map(normalizeExamSummary);

                const select = document.getElementById('exam-filter');
                select.innerHTML = '<option value="">Semua Ujian Aktif</option>' +
                    activeExams.map(e => `<option value="${e.id}">${e.title}</option>`).join('');

                document.getElementById('total-exams').textContent = activeExams.length;
                renderSessions(activeExams, { summaryMode: true });
                tryAutoOpenMonitorFromQuery(activeExams);
            } catch (error) {
                const rawDetail = error?.detail || error?.message || '';
                const detail = typeof rawDetail === 'object'
                    ? (rawDetail.message || JSON.stringify(rawDetail))
                    : String(rawDetail || '');
                const shortDetail = detail ? ` (${detail.slice(0, 140)})` : '';
                showAlert(`Gagal memuat data monitoring${shortDetail}`, 'danger');
                renderMonitoringLoadError(detail || 'Terjadi gangguan saat memuat data sesi aktif.');
            }
        }

        function tryAutoOpenMonitorFromQuery(activeExams) {
            if (monitorQueryConsumed) return;
            if (!autoOpenMonitorRequested) return;
            if (!Number.isFinite(requestedMonitorExamId) || requestedMonitorExamId <= 0) return;

            const targetExam = (Array.isArray(activeExams) ? activeExams : []).find(
                (exam) => Number(exam?.id) === requestedMonitorExamId
            );
            if (!targetExam) return;

            monitorQueryConsumed = true;
            const select = document.getElementById('exam-filter');
            if (select) {
                select.value = String(requestedMonitorExamId);
            }
            if (typeof openSessionStatusModal === 'function') {
                setTimeout(() => openSessionStatusModal(requestedMonitorExamId), 0);
            }

            const cleanUrl = window.location.pathname;
            window.history.replaceState({}, document.title, cleanUrl);
        }

        function renderMonitoringLoadError(message) {
            const container = document.getElementById('sessions-container');
            if (!container) return;
            const safeMessage = escapeHtml(message || 'Terjadi gangguan pada backend monitoring.');
            container.innerHTML = `
                <div class="empty-state">
                    <i class="fas fa-triangle-exclamation"></i>
                    <h3>Data Monitoring Belum Tersedia</h3>
                    <p>${safeMessage}</p>
                    <button class="btn btn-sm btn-primary" onclick="refreshData()">
                        <i class="fas fa-rotate"></i> Coba Muat Ulang
                    </button>
                </div>
            `;
        }

        // Get real sessions from API
        async function getRealSessions(exams) {
            if (exams.length === 0) return [];

            const sessions = [];
            for (const exam of exams) {
                try {
                    // Use api.getExamSessions which calls /monitoring/exam/{id}/sessions
                    const response = await api.getExamSessions(exam.id);

                    // Backend returns { sessions: [...] }, extract the array
                    const examSessions = response?.sessions || [];

                    console.log(`[DEBUG] Exam ${exam.id} response:`, response);
                    console.log(`[DEBUG] Extracted ${examSessions.length} sessions`);

                    if (examSessions && Array.isArray(examSessions)) {
                        examSessions.forEach(s => {
                            sessions.push({
                                id: s.session_id,  // Backend uses session_id
                                user: { full_name: s.user_name || 'Unknown', username: s.user_name || 'unknown' },
                                exam: exam,
                                start_time: s.start_time,
                                progress: s.progress || 0,
                                violations: s.violation_count || 0,
                                status: s.status || 'in_progress',
                                ip_address: s.ip_address || 'N/A'
                            });
                        });
                    }
                } catch (e) {
                    console.error(`Failed to get sessions for exam ${exam.id}:`, e);
                }
            }
            return sessions;
        }

        function renderSessions(sessions, options = {}) {
            const container = document.getElementById('sessions-container');
            const summaryMode = !!options.summaryMode;
            const sourceList = Array.isArray(sessions) ? sessions : [];
            let activeCount = 0;
            let violationsCount = 0;
            let completedCount = 0;
            const examGroups = {};

            if (summaryMode) {
                sourceList.forEach(exam => {
                    const examId = exam.id;
                    if (!examId) return;
                    const totalActive = Number(exam.in_progress_count ?? exam.active_participants ?? 0);
                    const totalCompleted = Number(exam.completed_count ?? exam.completed_participants ?? 0);
                    const totalViolations = Number(exam.total_violations ?? 0);
                    const totalSessions = Number(exam.total_sessions ?? (totalActive + totalCompleted));

                    examGroups[examId] = {
                        exam,
                        sessions: [],
                        totalSessions,
                        totalActive,
                        totalViolations,
                        totalCompleted
                    };
                    activeCount += totalActive;
                    completedCount += totalCompleted;
                    violationsCount += totalViolations;
                });
            } else {
                // Calculate stats for detailed session list mode
                activeCount = sourceList.filter(s => s.status === 'in_progress').length;
                violationsCount = sourceList.reduce((sum, s) => sum + (s.violation_count || s.violations || 0), 0);
                completedCount = sourceList.filter(s => s.status === 'completed' || s.status === 'submitted').length;

                // Group sessions by exam
                sourceList.forEach(s => {
                    const examId = s.exam.id;
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
                    examGroups[examId].sessions.push(s);
                    examGroups[examId].totalSessions += 1;
                    if (s.status === 'in_progress') examGroups[examId].totalActive += 1;
                    if (s.status === 'completed' || s.status === 'submitted') examGroups[examId].totalCompleted += 1;
                    examGroups[examId].totalViolations += s.violation_count || s.violations || 0;
                });
            }

            // Update main stats cards
            document.getElementById('total-active').textContent = activeCount;
            document.getElementById('total-violations').textContent = violationsCount;
            document.getElementById('total-completed').textContent = completedCount;

            if (sourceList.length === 0) {
                container.innerHTML = `
                    <div style="text-align: center; padding: 3rem;">
                        <i class="fas fa-satellite-dish" style="font-size: 3rem; color: var(--text-secondary); margin-bottom: 1rem;"></i>
                        <h3 style="margin-bottom: 0.5rem; color: white;">Tidak Ada Sesi Aktif</h3>
                        <p style="color: var(--text-secondary); margin-bottom: 1.5rem;">Belum ada peserta yang sedang mengerjakan ujian saat ini.</p>
                        <div style="display: flex; justify-content: center; gap: 1rem; flex-wrap: wrap;">
                            <div style="background: rgba(34, 197, 94, 0.1); padding: 0.75rem 1.25rem; border-radius: 0.5rem; color: white;">
                                <i class="fas fa-info-circle" style="color: var(--success);"></i>
                                Halaman ini akan update otomatis setiap 10 detik
                            </div>
                        </div>
                    </div>
                `;
                return;
            }

            container.innerHTML = `
                <div style="display: grid; gap: 1rem;">
                    ${Object.values(examGroups).map(group => {
                const violationClass = group.totalViolations > 5 ? 'danger' : group.totalViolations > 0 ? 'warning' : '';

                return `
                            <div class="card session-card ${violationClass}"
                                 onclick="openSessionStatusModal(${group.exam.id})"
                                 style="padding: 1.5rem; cursor: pointer; transition: all 0.3s ease;">
                                <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 1.5rem;">
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

                                <div style="margin-top: 1rem; padding-top: 1rem; border-top: 1px solid var(--border-color); display: flex; align-items: center; justify-content: space-between; gap: 0.5rem; font-size: 0.85rem; color: var(--text-secondary); flex-wrap: wrap;">
                                    <div style="display: inline-flex; align-items: center; gap: 0.5rem;">
                                        <i class="fas fa-circle-info"></i>
                                        Klik card untuk melihat detail real-time per siswa
                                    </div>
                                    <button class="exam-recovery-quick-btn"
                                            onclick="event.stopPropagation(); openRecoveryCenter(${group.exam.id});"
                                            title="Recovery Center: buka ulang sesi siswa yang bermasalah">
                                        <i class="fas fa-heart"></i>
                                        Recovery
                                        <span class="badge badge-danger" style="padding: 0.15rem 0.35rem; font-size: 0.68rem;">
                                            ${group.totalCompleted}
                                        </span>
                                    </button>
                                </div>
                            </div>
                        `;
            }).join('')}
                </div>
            `;
        }

        async function kickUser(sessionId) {
            const confirmed = await showConfirm('Apakah Anda yakin ingin mengeluarkan peserta ini dari ujian?', {
                title: 'Keluarkan Peserta',
                type: 'danger',
                confirmText: 'Ya, Keluarkan',
                cancelText: 'Batal'
            });
            if (confirmed) {
                showAlert('Peserta berhasil dikeluarkan dari ujian', 'success');
                refreshData();
            }
        }

        async function refreshData() {
            if (refreshDataInFlight) return;
            refreshDataInFlight = true;
            try {
                if (hideOpsSummary) {
                    await loadActiveExams();
                    return;
                }
                await Promise.all([
                    loadActiveExams(),
                    loadOpsSummary()
                ]);
            } finally {
                refreshDataInFlight = false;
            }
        }
