/* exam/reconnect.js — websocket pause/kick/reconnect */

    // ============================================================================
    // WEBSOCKET FOR REAL-TIME PAUSE/RESUME AND HEARTBEAT
    // ============================================================================

    initWebSocket() {
        if (!this.wsReconnectEnabled) {
            return;
        }

        // Get user ID from localStorage
        let user = {};
        try {
            user = JSON.parse(localStorage.getItem('user') || '{}');
        } catch (error) {
            console.warn('Invalid user data in localStorage for WebSocket init');
        }
        const userId = user.id;
        const wsToken = localStorage.getItem('access_token');

        if (!userId || !this.examId || !wsToken) {
            console.warn('⚠️ WebSocket not initialized: missing userId, examId, or token');
            this.scheduleWebSocketReconnect('missing_context', 1500);
            return;
        }

        if (
            this.examSocket &&
            (this.examSocket.readyState === WebSocket.OPEN || this.examSocket.readyState === WebSocket.CONNECTING)
        ) {
            return;
        }

        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/exam/${this.examId}/${userId}?token=${wsToken}`;

        console.log(`🔌 Connecting to Exam WebSocket`);

        try {
            this.examSocket = new WebSocket(wsUrl);

            this.examSocket.onopen = () => {
                console.log('✅ Exam WebSocket Connected');
                this.wsReconnectAttempts = 0;
                this.wsAuthFailed = false;
                // Start heartbeat every 30 seconds
                this.wsHeartbeatInterval = setInterval(() => {
                    if (this.examSocket && this.examSocket.readyState === WebSocket.OPEN) {
                        this.examSocket.send(JSON.stringify({ type: 'heartbeat', timestamp: new Date().toISOString() }));
                    }
                }, 30000);
            };

            this.examSocket.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    this.handleWebSocketMessage(data);
                } catch (e) {
                    console.error('WebSocket message parse error:', e);
                }
            };

            this.examSocket.onclose = (e) => {
                console.warn('⚠️ Exam WebSocket Disconnected:', e.reason);
                this.clearWsHeartbeat();
                this.examSocket = null;

                if (!this.wsReconnectEnabled) {
                    return;
                }

                // Authentication/authorization close code: do not loop reconnect forever
                if ([4401, 4403, 4404].includes(Number(e.code))) {
                    this.wsAuthFailed = true;
                    console.warn(`🛑 WebSocket reconnect stopped due to auth/permission close code ${e.code}`);
                    return;
                }

                this.scheduleWebSocketReconnect(`close_${e.code}`);
            };

            this.examSocket.onerror = (error) => {
                console.error('Exam WebSocket Error:', error);
            };

        } catch (error) {
            console.error('Failed to initialize WebSocket:', error);
            this.scheduleWebSocketReconnect('init_exception');
        }
    }

    scheduleWebSocketReconnect(reason = 'unknown', forcedDelayMs = null) {
        if (!this.wsReconnectEnabled || this.wsAuthFailed) {
            return;
        }
        if (this.wsReconnectTimer) {
            return;
        }

        this.wsReconnectAttempts += 1;
        if (this.wsReconnectAttempts > 12) {
            console.warn('🛑 WebSocket reconnect stopped after max attempts');
            return;
        }

        const delayMs = forcedDelayMs ?? Math.min(30000, 1000 * (2 ** (this.wsReconnectAttempts - 1)));
        console.log(`🔄 WebSocket reconnect attempt ${this.wsReconnectAttempts} in ${delayMs}ms (reason=${reason})`);

        this.wsReconnectTimer = setTimeout(() => {
            this.wsReconnectTimer = null;
            this.initWebSocket();
        }, delayMs);
    }

    handleWebSocketMessage(data) {
        console.log('📨 WebSocket Message:', data.type, data);

        switch (data.type) {
            case 'exam_paused':
                // Exam paused by admin
                console.log('⏸️ Exam paused via WebSocket');
                this.handlePauseState(true, data.message, data.paused_by);
                break;

            case 'exam_resumed':
                // Exam resumed by admin
                console.log('▶️ Exam resumed via WebSocket');
                this.handlePauseState(false);
                // Sync time immediately to get accurate remaining time
                this.syncTime();
                break;

            case 'force_submit':
                // Admin forced submission
                console.warn('🚨 Force submit from admin:', data.reason);
                showNotification(data.reason || 'Ujian dikumpulkan oleh pengawas', 'warning');

                // Notify Flutter app if running in APK
                try {
                    if (window.flutter_inappwebview) {
                        window.flutter_inappwebview.callHandler('forceSubmit', data.reason || 'Dikumpulkan oleh pengawas');
                        console.log('📱 Notified Flutter: force submit');
                    }
                } catch (e) {
                    console.log('Not running in Flutter WebView');
                }

                setTimeout(async () => {
                    await this.flushPendingAnswersForForceSubmit();
                    await this.submitExam(false);
                }, 1200);
                break;

            case 'force_kick':
                // Admin forced kick - logout student immediately
                console.error('🚫 [DEBUG] force_kick received via WebSocket!');
                console.error('🚫 [DEBUG] data:', JSON.stringify(data));
                console.error('🚫 [DEBUG] reason:', data.reason);
                this.handleForceKick(data.reason || 'Anda telah dikeluarkan dari ujian oleh pengawas');
                break;

            case 'exam_cancelled':
                // Exam was unpublished/cancelled by admin
                console.warn('🚫 Exam cancelled by admin:', data.cancelled_by);
                this.handleExamCancelled(data.reason, data.cancelled_by);
                break;

            case 'admin_message':
                // Message from admin
                showNotification(data.message, 'info');
                break;

            default:
                // Ignore unknown message types
                break;
        }
    }

    // Handle force kick - show notification and redirect
    handleForceKick(reason) {
        console.log('🔴 [DEBUG] handleForceKick called with reason:', reason);

        // Stop all intervals
        this.cleanup();

        // Show prominent notification
        showNotification(`🚫 ${reason}`, 'error');

        // Show modal overlay
        this.showKickedModal(reason);

        // Notify Flutter app if running in APK
        console.log('🔴 [DEBUG] Checking for Flutter WebView...');
        console.log('🔴 [DEBUG] window.flutter_inappwebview exists:', !!window.flutter_inappwebview);

        try {
            if (window.flutter_inappwebview) {
                console.log('🔴 [DEBUG] Calling Flutter forceKicked handler...');
                window.flutter_inappwebview.callHandler('forceKicked', reason);
                console.log('📱 [DEBUG] Notified Flutter: force kicked SUCCESS');
            } else {
                console.log('📱 [DEBUG] Not running in Flutter WebView (flutter_inappwebview not found)');
            }
        } catch (e) {
            console.error('🔴 [DEBUG] Error calling Flutter handler:', e);
        }

        // Redirect to dashboard after 5 seconds
        setTimeout(() => {
            ExamSystem.clearSessionStorage();
            window.location.href = '/student/dashboard.html?kicked=1';
        }, 5000);
    }

    // Show kicked modal overlay
    showKickedModal(reason) {
        // Remove any existing modal
        const existingModal = document.getElementById('kicked-modal');
        if (existingModal) existingModal.remove();

        const modal = document.createElement('div');
        modal.id = 'kicked-modal';
        modal.innerHTML = `
            <div style="
                position: fixed;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                background: rgba(0, 0, 0, 0.95);
                z-index: 99999;
                display: flex;
                align-items: center;
                justify-content: center;
                flex-direction: column;
                padding: 2rem;
                animation: fadeIn 0.3s ease;
            ">
                <div style="
                    text-align: center;
                    max-width: 500px;
                    background: linear-gradient(135deg, #1e293b, #0f172a);
                    border: 2px solid #ef4444;
                    border-radius: 1.5rem;
                    padding: 3rem;
                    box-shadow: 0 0 60px rgba(239, 68, 68, 0.3);
                ">
                    <div style="font-size: 5rem; margin-bottom: 1rem;">🚫</div>
                    <h1 style="
                        color: #ef4444;
                        font-size: 2rem;
                        margin-bottom: 1rem;
                        font-weight: 700;
                    ">Anda Dikeluarkan dari Ujian</h1>
                    <p style="
                        color: #94a3b8;
                        font-size: 1.1rem;
                        margin-bottom: 1.5rem;
                        line-height: 1.6;
                    ">${reason}</p>
                    <div style="
                        background: rgba(239, 68, 68, 0.1);
                        border: 1px solid rgba(239, 68, 68, 0.3);
                        border-radius: 0.75rem;
                        padding: 1rem;
                        color: #f87171;
                        font-size: 0.9rem;
                    ">
                        <i class="fas fa-info-circle"></i>
                        Anda akan dialihkan ke dashboard dalam 5 detik...
                    </div>
                </div>
            </div>
            <style>
                @keyframes fadeIn {
                    from { opacity: 0; }
                    to { opacity: 1; }
                }
            </style>
        `;
        document.body.appendChild(modal);
    }

    // Handle exam cancelled - show professional dialog and redirect to login
    handleExamCancelled(reason, cancelledBy) {
        console.warn('🚫 Exam cancelled - cleaning up...');

        // Clear any pause overlay first
        this.hidePauseOverlay();
        this.globallyPaused = false;

        // Stop all timers and intervals
        this.cleanup();

        // Remove any existing cancelled modal
        const existingModal = document.getElementById('cancelled-modal');
        if (existingModal) existingModal.remove();

        const modal = document.createElement('div');
        modal.id = 'cancelled-modal';
        modal.innerHTML = `
            <div style="
                position: fixed;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                background: rgba(0, 0, 0, 0.95);
                z-index: 999999;
                display: flex;
                align-items: center;
                justify-content: center;
                flex-direction: column;
                padding: 2rem;
                animation: fadeIn 0.3s ease;
            ">
                <div style="
                    text-align: center;
                    max-width: 500px;
                    background: linear-gradient(135deg, #1e293b, #0f172a);
                    border: 2px solid #f59e0b;
                    border-radius: 1.5rem;
                    padding: 3rem;
                    box-shadow: 0 0 60px rgba(245, 158, 11, 0.3);
                ">
                    <div style="font-size: 5rem; margin-bottom: 1rem;">⏸️</div>
                    <h1 style="
                        color: #f59e0b;
                        font-size: 1.8rem;
                        margin-bottom: 1rem;
                        font-weight: 700;
                    ">Ujian Ditunda / Dibatalkan</h1>
                    <p style="
                        color: #94a3b8;
                        font-size: 1.1rem;
                        margin-bottom: 1rem;
                        line-height: 1.6;
                    ">${reason || 'Ujian telah dibatalkan atau ditunda oleh pengawas.'}</p>
                    ${cancelledBy ? `<p style="
                        color: #64748b;
                        font-size: 0.9rem;
                        margin-bottom: 1.5rem;
                    ">Oleh: <strong>${cancelledBy}</strong></p>` : ''}
                    <div style="
                        background: rgba(245, 158, 11, 0.1);
                        border: 1px solid rgba(245, 158, 11, 0.3);
                        border-radius: 0.75rem;
                        padding: 1rem;
                        color: #fbbf24;
                        font-size: 0.9rem;
                        margin-bottom: 1.5rem;
                    ">
                        <i class="fas fa-info-circle"></i>
                        Silakan hubungi pengawas untuk informasi lebih lanjut.
                    </div>
                    <button id="cancelled-ok-btn" style="
                        background: linear-gradient(135deg, #f59e0b, #d97706);
                        color: white;
                        border: none;
                        padding: 1rem 3rem;
                        font-size: 1.1rem;
                        font-weight: 600;
                        border-radius: 0.75rem;
                        cursor: pointer;
                        transition: all 0.3s ease;
                        box-shadow: 0 4px 15px rgba(245, 158, 11, 0.3);
                    ">OK, SAYA MENGERTI</button>
                </div>
            </div>
            <style>
                @keyframes fadeIn {
                    from { opacity: 0; }
                    to { opacity: 1; }
                }
                #cancelled-ok-btn:hover {
                    transform: translateY(-2px);
                    box-shadow: 0 6px 20px rgba(245, 158, 11, 0.4);
                }
            </style>
        `;
        document.body.appendChild(modal);

        // Handle OK button click
        document.getElementById('cancelled-ok-btn').addEventListener('click', () => {
            // Notify Flutter app if running in APK
            try {
                if (window.flutter_inappwebview) {
                    window.flutter_inappwebview.callHandler('examCancelled', reason);
                    console.log('📱 Notified Flutter: exam cancelled');
                }
            } catch (e) {
                console.log('Not running in Flutter WebView');
            }

            // Clear session and redirect to login
            ExamSystem.clearSessionStorage();
            window.location.href = '/login.html?cancelled=1';
        });

        // Also notify Flutter immediately (in case WebView handles it differently)
        try {
            if (window.flutter_inappwebview) {
                window.flutter_inappwebview.callHandler('examCancelled', reason);
            }
        } catch (e) {
            // Ignore
        }
    }

    // Cleanup method to stop all intervals
    cleanup() {
        if (this.timerInterval) clearInterval(this.timerInterval);
        if (this.autoSaveInterval) clearInterval(this.autoSaveInterval);
        if (this.timeSyncInterval) clearInterval(this.timeSyncInterval);
        if (this.pauseSyncInterval) clearInterval(this.pauseSyncInterval);
        if (this.pauseElapsedInterval) clearInterval(this.pauseElapsedInterval);
        if (this.pendingSyncTimeout) clearTimeout(this.pendingSyncTimeout);
        if (this.textAnswerTimeout) clearTimeout(this.textAnswerTimeout);
        this.clearWsHeartbeat();
        this.wsReconnectEnabled = false;
        this.wsAuthFailed = false;
        this.wsReconnectAttempts = 0;
        if (this.wsReconnectTimer) {
            clearTimeout(this.wsReconnectTimer);
            this.wsReconnectTimer = null;
        }
        if (this.examSocket) {
            this.examSocket.close();
            this.examSocket = null;
        }
    }

    clearWsHeartbeat() {
        if (this.wsHeartbeatInterval) {
            clearInterval(this.wsHeartbeatInterval);
            this.wsHeartbeatInterval = null;
        }
    }
