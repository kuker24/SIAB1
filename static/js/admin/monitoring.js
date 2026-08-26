/**
 * AUTO-GENERATED FILE.
 * Source modules: static/js/admin/monitoring/modules/*.js
 * Use scripts/build_monitoring_bundle.sh after editing modules.
 */

/* ===== Module: 00-core-ops-and-sessions.js ===== */

        if (!auth.requireAuth(['admin', 'developer', 'teacher'])) {
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
            if (isTeacher) {
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
                autoRestartToggleBtn.disabled = isTeacher || opsAutoRestartToggleInFlight || opsAutoControlInFlight || opsRestartInFlight || opsAutoHealRunInFlight;
                autoRestartToggleBtn.innerHTML = opsAutoRestartToggleInFlight
                    ? '<i class="fas fa-spinner fa-spin"></i> Menyimpan Jadwal...'
                    : '<i class="fas fa-calendar-plus"></i> Jadwalkan Auto Restart';
            }
            if (autoModeBtn) {
                autoModeBtn.disabled = isTeacher || opsAutoControlInFlight || opsRestartInFlight || opsAutoRestartToggleInFlight || opsAutoHealRunInFlight;
                autoModeBtn.classList.remove('btn-primary', 'btn-outline-success', 'btn-outline-warning');
                autoModeBtn.classList.add(autoModeEnabled ? 'btn-primary' : 'btn-outline-success');
                autoModeBtn.innerHTML = opsAutoControlInFlight
                    ? '<i class="fas fa-spinner fa-spin"></i> Menyimpan...'
                    : `<i class="fas fa-brain"></i> Auto Performa: ${autoModeEnabled ? 'ON' : 'OFF'}`;
            }
            if (autoHealBtn) {
                autoHealBtn.disabled = isTeacher || opsAutoControlInFlight || opsRestartInFlight || opsAutoRestartToggleInFlight || opsAutoHealRunInFlight;
                autoHealBtn.classList.remove('btn-primary', 'btn-outline-info', 'btn-outline-secondary');
                autoHealBtn.classList.add(autoHealEnabled ? 'btn-primary' : 'btn-outline-info');
                autoHealBtn.innerHTML = opsAutoControlInFlight
                    ? '<i class="fas fa-spinner fa-spin"></i> Menyimpan...'
                    : `<i class="fas fa-heart-pulse"></i> Auto Healing: ${autoHealEnabled ? 'ON' : 'OFF'}`;
            }
            if (autoHealRunBtn) {
                autoHealRunBtn.disabled = isTeacher || opsAutoControlInFlight || opsRestartInFlight || opsAutoRestartToggleInFlight || opsAutoHealRunInFlight || !autoHealEnabled;
                autoHealRunBtn.innerHTML = opsAutoHealRunInFlight
                    ? '<i class="fas fa-spinner fa-spin"></i> Menjalankan...'
                    : '<i class="fas fa-wand-magic-sparkles"></i> Heal Sekarang';
            }
            if (restartBtn) {
                restartBtn.disabled = isTeacher || opsRestartInFlight || opsAutoControlInFlight || opsAutoRestartToggleInFlight || opsAutoHealRunInFlight;
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

            if (isTeacher) {
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
            if (isTeacher || opsAutoRestartToggleInFlight) return;
            if (!opsSummaryState || !opsSummaryState.policy) {
                showAlert('Status ops belum siap, coba refresh dulu', 'warning');
                return;
            }
            openOpsAutoRestartModal();
        }

        async function saveOpsAutoRestartSchedule() {
            if (isTeacher || opsAutoRestartToggleInFlight) return;
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
            if (isTeacher || opsAutoControlInFlight) return;
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
            if (isTeacher || opsAutoControlInFlight) return;
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
            if (isTeacher || opsAutoHealRunInFlight) return;
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
            if (isTeacher || opsRestartInFlight || opsAutoControlInFlight || opsAutoHealRunInFlight) return;
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
                if (isTeacher) {
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

/* ===== Module: 10-pause-websocket-student-detail.js ===== */

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
                if (!isTeacher) {
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

/* ===== Module: 15-recovery-center-student-detail.js ===== */

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

/* ===== Module: 20-fullscreen-and-cleanup.js ===== */

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
