/**
 * AUTO-GENERATED FILE.
 * Source modules: static/js/alarm-system/modules/*.js
 * Use scripts/build_alarm_system_bundle.sh after editing modules.
 */

/* ===== Module: 00-alarm-core.js ===== */

/**
 * Cheat Detection & Alarm System
 * Aggressive anti-cheating with audio alerts
 */

class CheatDetectionAlarm {
    constructor(sessionId, examId) {
        this.sessionId = sessionId;
        this.examId = examId;
        this.violationCount = 0;
        this.audioContext = null;
        this.alarmBuffer = null;
        this.isPlaying = false;

        this.init();
    }

    async init() {
        console.log('Cheat Detection System initialized');

        // Initialize audio context on first user interaction
        document.addEventListener('click', () => this.initAudio(), { once: true });
        document.addEventListener('keydown', () => this.initAudio(), { once: true });

        // Setup all detection methods
        this.setupTabSwitchDetection();
        this.setupWindowBlurDetection();
        this.setupScreenshotDetection();
        this.setupCopyPasteDetection();
        this.setupDevToolsDetection();
        this.setupContextMenuPrevention();
        this.setupTextSelectionPrevention();
    }

    async initAudio() {
        if (this.audioContext) return;

        try {
            this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
            await this.generateAlarmSound();
            console.log('Audio system ready');
        } catch (error) {
            console.error('Failed to initialize audio:', error);
        }
    }

    async generateAlarmSound() {
        // Generate a 2-second siren sound
        const sampleRate = this.audioContext.sampleRate;
        const duration = 2;
        const buffer = this.audioContext.createBuffer(1, sampleRate * duration, sampleRate);
        const data = buffer.getChannelData(0);

        // Generate aggressive siren waveform
        for (let i = 0; i < buffer.length; i++) {
            const t = i / sampleRate;
            // Siren frequency oscillates between 600Hz and 1200Hz
            const freq = 900 + 300 * Math.sin(2 * Math.PI * 4 * t);
            data[i] = Math.sin(2 * Math.PI * freq * t) * 0.8;
        }

        this.alarmBuffer = buffer;
    }

    playAlarm() {
        if (!this.audioContext || !this.alarmBuffer || this.isPlaying) return;

        this.isPlaying = true;

        // Play alarm 3 times with 100% volume
        const playOnce = (delay) => {
            setTimeout(() => {
                const source = this.audioContext.createBufferSource();
                const gainNode = this.audioContext.createGain();

                source.buffer = this.alarmBuffer;
                gainNode.gain.value = 1.0; // MAXIMUM VOLUME

                source.connect(gainNode);
                gainNode.connect(this.audioContext.destination);
                source.start();
            }, delay);
        };

        playOnce(0);
        playOnce(500);
        playOnce(1000);

        setTimeout(() => {
            this.isPlaying = false;
        }, 3000);
    }

    setupTabSwitchDetection() {
        document.addEventListener('visibilitychange', () => {
            if (document.hidden) {
                this.triggerViolation('TAB_SWITCH', {
                    message: 'Terdeteksi perpindahan tab/aplikasi!'
                });
            }
        });
    }

    setupWindowBlurDetection() {
        window.addEventListener('blur', () => {
            this.triggerViolation('WINDOW_BLUR', {
                message: 'Window kehilangan fokus!'
            });
        });
    }

    setupScreenshotDetection() {
        // Screenshot key combinations
        const screenshotCombos = [
            ['PrintScreen'],
            ['Meta', 'Shift', 's'],     // Windows Snip
            ['Meta', 'Shift', '3'],     // macOS Screenshot
            ['Meta', 'Shift', '4'],     // macOS Selection
            ['Meta', 'Shift', '5'],     // macOS Screenshot menu
        ];

        let pressedKeys = new Set();

        document.addEventListener('keydown', (e) => {
            pressedKeys.add(e.key);

            // Check for screenshot combos
            for (const combo of screenshotCombos) {
                if (combo.every(key =>
                    pressedKeys.has(key) ||
                    (key === 'Meta' && (pressedKeys.has('Meta') || pressedKeys.has('Control')))
                )) {
                    e.preventDefault();
                    this.triggerViolation('SCREENSHOT_ATTEMPT', {
                        message: 'Percobaan screenshot terdeteksi!',
                        keys: Array.from(pressedKeys)
                    });
                    break;
                }
            }

            // Block PrintScreen specifically
            if (e.key === 'PrintScreen') {
                e.preventDefault();
                this.triggerViolation('SCREENSHOT_ATTEMPT', {
                    message: 'Tombol PrintScreen terdeteksi!'
                });
            }
        });

        document.addEventListener('keyup', (e) => {
            pressedKeys.delete(e.key);
        });
    }

    setupCopyPasteDetection() {
        const actions = ['copy', 'cut', 'paste'];

        actions.forEach(action => {
            document.addEventListener(action, (e) => {
                e.preventDefault();
                this.triggerViolation('COPY_PASTE_ATTEMPT', {
                    message: `Percobaan ${action} terdeteksi!`,
                    action: action
                });
            });
        });
    }

    setupDevToolsDetection() {
        // DevTools key combinations
        const devToolsCombos = [
            ['F12'],
            ['Control', 'Shift', 'I'],
            ['Control', 'Shift', 'J'],
            ['Control', 'Shift', 'C'],
            ['Control', 'U'],           // View source
            ['Control', 'Shift', 'K'],  // Firefox console
        ];

        let pressedKeys = new Set();

        document.addEventListener('keydown', (e) => {
            pressedKeys.add(e.key);

            // Check for DevTools combos
            for (const combo of devToolsCombos) {
                if (combo.every(key => pressedKeys.has(key))) {
                    e.preventDefault();
                    this.triggerViolation('DEVTOOLS_ATTEMPT', {
                        message: 'Percobaan membuka Developer Tools!',
                        keys: Array.from(pressedKeys)
                    });
                    break;
                }
            }

            // Block F12 specifically
            if (e.key === 'F12') {
                e.preventDefault();
                this.triggerViolation('DEVTOOLS_ATTEMPT', {
                    message: 'Tombol F12 terdeteksi!'
                });
            }
        });

        document.addEventListener('keyup', (e) => {
            pressedKeys.delete(e.key);
        });

        // Detect window resize (DevTools opening)
        let lastWidth = window.innerWidth;
        let lastHeight = window.innerHeight;

        setInterval(() => {
            const widthDiff = Math.abs(window.innerWidth - lastWidth);
            const heightDiff = Math.abs(window.innerHeight - lastHeight);

            // Suspicious resize (DevTools typically takes 200+ pixels)
            if (widthDiff > 150 || heightDiff > 150) {
                this.triggerViolation('WINDOW_RESIZE_SUSPICIOUS', {
                    message: 'Perubahan ukuran window yang mencurigakan!',
                    widthChange: widthDiff,
                    heightChange: heightDiff
                });
            }

            lastWidth = window.innerWidth;
            lastHeight = window.innerHeight;
        }, 2000);
    }

    setupContextMenuPrevention() {
        document.addEventListener('contextmenu', (e) => {
            e.preventDefault();
            this.triggerViolation('CONTEXT_MENU_ATTEMPT', {
                message: 'Klik kanan dinonaktifkan!'
            });
        });
    }

    setupTextSelectionPrevention() {
        document.addEventListener('selectstart', (e) => {
            // Allow selection in text inputs
            if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
                return;
            }
            e.preventDefault();
        });

        // CSS-based prevention as backup
        document.body.style.userSelect = 'none';
        document.body.style.webkitUserSelect = 'none';
    }

    async triggerViolation(eventType, eventData) {
        this.violationCount++;

        console.warn(`VIOLATION #${this.violationCount}: ${eventType}`, eventData);

        // 1. Play alarm sound at maximum volume
        this.playAlarm();

        // 2. Show visual warning
        this.showVisualWarning(eventData.message);

        // 3. Log to server
        await this.logToServer(eventType, eventData);

        // 4. Auto-submit if too many violations
        if (this.violationCount >= 5) {
            setTimeout(() => {
                alert('UJIAN DIKUMPULKAN OTOMATIS karena terlalu banyak pelanggaran!');
                if (window.examSystem) {
                    window.examSystem.submitExam(true);
                }
            }, 2000);
        }
    }

    showVisualWarning(message) {
        // Remove existing warning if any
        const existing = document.getElementById('violation-warning');
        if (existing) existing.remove();

        let severeMessage = '';
        if (this.violationCount >= 5) {
            severeMessage = 'Batas pelanggaran tercapai. Ujian akan dikumpulkan otomatis.';
        } else if (this.violationCount === 4) {
            severeMessage = 'PERINGATAN TERAKHIR! Pelanggaran berikutnya akan mengumpulkan ujian otomatis.';
        } else if (this.violationCount >= 3) {
            severeMessage = 'Batas auto-submit adalah 5 pelanggaran.';
        }

        // Create full-screen warning overlay
        const warning = document.createElement('div');
        warning.id = 'violation-warning';
        warning.className = 'warning-overlay';
        warning.innerHTML = `
            <div class="warning-icon">⚠️</div>
            <div class="warning-title">PERINGATAN!</div>
            <div class="warning-message">${message}</div>
            <div class="warning-count">Pelanggaran ke-${this.violationCount}</div>
            ${severeMessage ? `<div class="warning-severe" style="margin-top: 1rem; font-size: 1.2rem;">${severeMessage}</div>` : ''}
        `;

        document.body.appendChild(warning);

        // Auto-remove after 2.5 seconds
        setTimeout(() => {
            if (warning.parentNode) {
                warning.remove();
            }
        }, 2500);
    }

    async logToServer(eventType, eventData) {
        try {
            await fetch('/api/exams/log-violation', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.getToken()}`
                },
                body: JSON.stringify({
                    session_id: this.sessionId,
                    exam_id: this.examId,
                    event_type: eventType,
                    event_data: eventData,
                    timestamp: new Date().toISOString(),
                    user_agent: navigator.userAgent,
                    screen_resolution: `${screen.width}x${screen.height}`
                })
            });
        } catch (error) {
            console.error('Failed to log violation:', error);
        }
    }

    getToken() {
        return localStorage.getItem('access_token') || localStorage.getItem('token') || '';
    }
}

/* ===== Module: 10-alarm-bootstrap.js ===== */

// Initialize on exam pages
document.addEventListener('DOMContentLoaded', () => {
    const examContainer = document.getElementById('exam-container');
    if (examContainer) {
        const sessionId = parseInt(examContainer.dataset.sessionId);
        const examId = parseInt(examContainer.dataset.examId);

        window.cheatAlarm = new CheatDetectionAlarm(sessionId, examId);
        return;
    }

    const savedSession = localStorage.getItem('active_exam_session');
    if (savedSession) {
        try {
            const sessionData = JSON.parse(savedSession);
            if (sessionData?.sessionId && sessionData?.examId) {
                window.cheatAlarm = new CheatDetectionAlarm(
                    parseInt(sessionData.sessionId, 10),
                    parseInt(sessionData.examId, 10)
                );
            }
        } catch (error) {
            console.warn('Failed to restore cheat alarm session:', error);
        }
    }
});
